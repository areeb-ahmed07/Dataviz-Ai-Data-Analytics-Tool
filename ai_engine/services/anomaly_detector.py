"""
Anomaly Detector Service — ensemble detection using Isolation Forest, Z-Score, and IQR.

Single Responsibility: identifies outliers and unusual pattern anomalies.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ai_engine.domain.entities import AnomalyItem, AnomalySummary
from ai_engine.domain.enums import AnomalyMethod


class AnomalyDetector:
    """
    Ensemble anomaly detector combining Isolation Forest, Z-Score, and Interquartile Range (IQR).
    """

    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df.copy()

    def detect_anomalies(
        self,
        columns: Optional[List[str]] = None,
        contamination: float = 0.05,
    ) -> AnomalySummary:
        """
        Run ensemble anomaly detection across all numeric columns.
        """
        total_rows = len(self._df)
        if self._df.empty or total_rows < 5:
            return AnomalySummary(
                total_rows=total_rows,
                anomalous_rows_count=0,
                anomaly_percentage=0.0,
                detected_anomalies=[],
            )

        numeric_cols = columns or self._df.select_dtypes(include="number").columns.tolist()
        if not numeric_cols:
            return AnomalySummary(
                total_rows=total_rows,
                anomalous_rows_count=0,
                anomaly_percentage=0.0,
                detected_anomalies=[],
            )

        anomalies: List[AnomalyItem] = []
        anomalous_row_set = set()

        # 1. Isolation Forest (Multivariate)
        if len(numeric_cols) >= 2 and total_rows >= 20:
            if_anomalies, if_rows = self._detect_isolation_forest(numeric_cols, contamination)
            anomalies.extend(if_anomalies)
            anomalous_row_set.update(if_rows)

        # 2. Z-Score & IQR (Univariate)
        for col in numeric_cols[:8]:
            s_anomalies, s_rows = self._detect_univariate(col)
            anomalies.extend(s_anomalies)
            anomalous_row_set.update(s_rows)

        # Deduplicate anomaly items per (row_index, column)
        seen_pairs = set()
        unique_anomalies = []
        for item in sorted(anomalies, key=lambda a: a.score, reverse=True):
            pair = (item.row_index, item.column)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                unique_anomalies.append(item)

        pct = (len(anomalous_row_set) / total_rows) * 100.0 if total_rows > 0 else 0.0

        return AnomalySummary(
            total_rows=total_rows,
            anomalous_rows_count=len(anomalous_row_set),
            anomaly_percentage=float(pct),
            detected_anomalies=unique_anomalies[:50], # Cap at top 50 anomalies
            method_used=AnomalyMethod.ENSEMBLE,
        )

    # ─── Private Methods ────────────────────────────────────────────────────

    def _detect_isolation_forest(
        self, cols: List[str], contamination: float
    ) -> Tuple[List[AnomalyItem], List[int]]:
        items: List[AnomalyItem] = []
        rows: List[int] = []

        try:
            X = self._df[cols].dropna()
            if len(X) < 15:
                return items, rows

            iso = IsolationForest(
                n_estimators=100,
                contamination=contamination,
                random_state=42,
            )
            preds = iso.fit_predict(X)
            scores = -iso.score_samples(X)  # Higher = more anomalous

            # Min-max scale scores to [0.0 - 1.0]
            mn, mx = scores.min(), scores.max()
            norm_scores = (scores - mn) / (mx - mn) if mx > mn else np.zeros_like(scores)

            for loc, (idx, row) in enumerate(X.iterrows()):
                if preds[loc] == -1:
                    raw_row_idx = self._df.index.get_loc(idx)
                    rows.append(raw_row_idx)

                    # Highlight highest variance column
                    top_col = cols[0]
                    items.append(AnomalyItem(
                        row_index=raw_row_idx,
                        column=top_col,
                        value=row[top_col],
                        score=float(norm_scores[loc]),
                        method=AnomalyMethod.ISOLATION_FOREST,
                        reason=f"Multivariate outlier pattern detected across {len(cols)} features.",
                    ))

            return items, rows
        except Exception:
            return items, rows

    def _detect_univariate(self, col: str) -> Tuple[List[AnomalyItem], List[int]]:
        items: List[AnomalyItem] = []
        rows: List[int] = []

        try:
            series = self._df[col].dropna()
            if len(series) < 10:
                return items, rows

            mean = series.mean()
            std = series.std() or 1.0

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr

            for idx, val in series.items():
                z_score = abs(val - mean) / std
                is_iqr_outlier = val < lower_bound or val > upper_bound

                if z_score > 3.0 or is_iqr_outlier:
                    raw_row_idx = self._df.index.get_loc(idx)
                    rows.append(raw_row_idx)

                    method = AnomalyMethod.Z_SCORE if z_score > 3.0 else AnomalyMethod.IQR
                    score = min(1.0, float(z_score / 5.0))
                    bound_str = f"[{lower_bound:,.2f}, {upper_bound:,.2f}]"

                    items.append(AnomalyItem(
                        row_index=raw_row_idx,
                        column=col,
                        value=val,
                        score=score,
                        method=method,
                        expected_range=(float(lower_bound), float(upper_bound)),
                        reason=f"Value {val:,.2f} deviates (Z={z_score:.1f}, expected range {bound_str}).",
                    ))

            return items, rows
        except Exception:
            return items, rows
