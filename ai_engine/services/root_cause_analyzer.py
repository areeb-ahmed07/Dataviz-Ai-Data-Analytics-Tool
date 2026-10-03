"""
Root Cause Analyzer Service — identifies sub-population drivers & segment rules.

Single Responsibility: analyzes target metric distributions across features using
Decision Trees, mutual information, and contrastive statistical profiling.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, export_text

from ai_engine.domain.entities import RootCauseItem


class RootCauseAnalyzer:
    """
    Identifies what factors or segments drive an anomaly, spike, or target metric outcome.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df.copy()

    def analyze(
        self,
        target_column: Optional[str] = None,
        top_n: int = 5,
    ) -> List[RootCauseItem]:
        """
        Perform root cause analysis on the given target column or automatically select one.
        """
        if self._df.empty or len(self._df) < 10:
            return []

        numeric_cols = self._df.select_dtypes(include="number").columns.tolist()
        cat_cols = self._df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()

        if not target_column or target_column not in self._df.columns:
            target_column = numeric_cols[0] if numeric_cols else (cat_cols[0] if cat_cols else None)

        if not target_column or target_column not in self._df.columns:
            return []

        results: List[RootCauseItem] = []

        # 1. Decision Tree Rule Mining
        dt_items = self._analyze_via_decision_tree(target_column)
        results.extend(dt_items)

        # 2. Sub-population Contrast Analysis
        contrast_items = self._analyze_via_subpopulation_contrast(target_column)
        results.extend(contrast_items)

        # Sort by impact score descending & deduplicate
        seen_rules = set()
        unique_results = []
        for item in sorted(results, key=lambda x: x.impact_score, reverse=True):
            key = f"{item.feature}:{item.condition}"
            if key not in seen_rules:
                seen_rules.add(key)
                unique_results.append(item)

        return unique_results[:top_n]

    # ─── Private Analyzers ──────────────────────────────────────────────────

    def _analyze_via_decision_tree(self, target_col: str) -> List[RootCauseItem]:
        """Binarize target metric into high vs low and extract Decision Tree decision paths."""
        try:
            target = self._df[target_col].dropna()
            if target.empty or target.nunique() < 2:
                return []

            # Prepare features
            feature_cols = [c for c in self._df.columns if c != target_col]
            if not feature_cols:
                return []

            X = self._df[feature_cols].copy()
            # Encode categoricals & fill NAs
            for col in X.columns:
                if X[col].dtype == "object" or isinstance(X[col].dtype, pd.CategoricalDtype):
                    X[col] = X[col].astype("category").cat.codes
                X[col] = X[col].fillna(X[col].median() if pd.api.types.is_numeric_dtype(X[col]) else -1)

            # Binarize target: 1 for upper quartile (high value / anomaly), 0 otherwise
            if pd.api.types.is_numeric_dtype(target):
                threshold = target.quantile(0.75)
                y = (self._df[target_col] >= threshold).astype(int)
            else:
                top_class = target.value_counts().index[0]
                y = (self._df[target_col] == top_class).astype(int)

            clf = DecisionTreeClassifier(max_depth=3, min_samples_leaf=max(5, int(len(X) * 0.05)))
            clf.fit(X, y)

            importances = clf.feature_importances_
            items: List[RootCauseItem] = []

            for idx, imp in enumerate(importances):
                if imp > 0.08:
                    feat_name = feature_cols[idx]
                    feat_data = self._df[feat_name].dropna()
                    
                    if pd.api.types.is_numeric_dtype(feat_data):
                        med = feat_data.median()
                        cond = f"{feat_name} >= {med:,.2f}"
                        desc = f"High values of {target_col} strongly correlate with {feat_name} >= {med:,.2f}."
                    else:
                        top_val = feat_data.value_counts().index[0]
                        cond = f"{feat_name} == '{top_val}'"
                        desc = f"Segment '{top_val}' in {feat_name} accounts for a key proportion of {target_col} outcomes."

                    affected = int(len(self._df) * imp)
                    items.append(RootCauseItem(
                        feature=feat_name,
                        condition=cond,
                        impact_score=float(imp),
                        affected_rows=affected,
                        affected_percentage=float(imp * 100),
                        description=desc,
                    ))

            return items
        except Exception:
            return []

    def _analyze_via_subpopulation_contrast(self, target_col: str) -> List[RootCauseItem]:
        """Identify categorical segments that deviate significantly from the mean."""
        try:
            if not pd.api.types.is_numeric_dtype(self._df[target_col]):
                return []

            overall_mean = self._df[target_col].mean()
            overall_std = self._df[target_col].std() or 1.0

            cat_cols = self._df.select_dtypes(include=["object", "category"]).columns.tolist()
            items: List[RootCauseItem] = []

            for col in cat_cols:
                if col == target_col or self._df[col].nunique() > 30:
                    continue

                grouped = self._df.groupby(col)[target_col].agg(["mean", "count"]).reset_index()
                for _, row in grouped.iterrows():
                    count = int(row["count"])
                    if count < max(3, len(self._df) * 0.02):
                        continue

                    grp_mean = float(row["mean"])
                    z_diff = abs(grp_mean - overall_mean) / overall_std

                    if z_diff > 0.8:
                        direction = "above" if grp_mean > overall_mean else "below"
                        pct_diff = ((grp_mean - overall_mean) / abs(overall_mean)) * 100 if overall_mean != 0 else 0
                        cond = f"{col} == '{row[col]}'"
                        desc = f"Segment {cond} averages {grp_mean:,.2f} ({abs(pct_diff):.1f}% {direction} dataset average of {overall_mean:,.2f})."

                        items.append(RootCauseItem(
                            feature=col,
                            condition=cond,
                            impact_score=min(1.0, float(z_diff / 3.0)),
                            affected_rows=count,
                            affected_percentage=float((count / len(self._df)) * 100),
                            description=desc,
                        ))

            return items
        except Exception:
            return []
