"""
DataViz Pro — Analysis Service

Orchestrates all data analysis operations for the Analysis Workspace.
Reuses existing modules: core/data_analyzer.py, core/data_quality.py,
ai_engine/services/, nlg/insights_generator.py.

All methods load data via DatasetService.load_dataframe() and enforce
user ownership through the routes layer (dataset.user_id == current_user.id).
"""

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

from app.services.dataset_service import DatasetService


# ── In-memory analysis cache ────────────────────────────────────
# Keyed by (user_id, dataset_id, analysis_type, cache_key)
_analysis_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL = 300  # seconds


def _cache_key(user_id: int, dataset_id: int, analysis_type: str,
               extra: str = "") -> str:
    """Build a deterministic cache key."""
    raw = f"{user_id}:{dataset_id}:{analysis_type}:{extra}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_cache(key: str) -> Optional[Dict[str, Any]]:
    """Return cached result if still fresh, else None."""
    entry = _analysis_cache.get(key)
    if entry and (time.time() - entry.get("_ts", 0)) < CACHE_TTL:
        return entry
    return None


def _set_cache(key: str, data: Dict[str, Any]) -> None:
    """Store a result in the cache with a timestamp."""
    data["_ts"] = time.time()
    _analysis_cache[key] = data


def clear_dataset_cache(user_id: int, dataset_id: int) -> None:
    """Clear all cached analyses for a specific dataset."""
    prefix = _cache_key(user_id, dataset_id, "")
    keys_to_remove = [k for k in _analysis_cache if k.startswith(prefix)]
    for k in keys_to_remove:
        del _analysis_cache[k]


# ── DataFrame loading helpers ───────────────────────────────────

# Maximum rows used for heavy analysis (correlation, distributions, outliers)
MAX_ANALYSIS_ROWS = 50_000
# Maximum rows for preview in UI tables
MAX_PREVIEW_ROWS = 100


def _load_dataset(dataset_id: int, user_id: int,
                  max_rows: Optional[int] = None) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """
    Load a dataset DataFrame, enforcing ownership.
    Returns (df, error_message). If max_rows is set, samples the data.
    """
    dataset = DatasetService.get_dataset(dataset_id, user_id)
    if not dataset:
        return None, "Dataset not found or access denied."
    if not dataset.storage_path:
        return None, "Dataset has no stored file."

    df, error = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format)
    if df is None:
        return None, error or "Failed to load dataset."

    # Sample if dataset is large and max_rows is specified
    sampled = False
    if max_rows and len(df) > max_rows:
        df = df.sample(n=max_rows, random_state=42)
        sampled = True

    return df, None


def _classify_column(dtype: str) -> str:
    """Classify a pandas dtype into a high-level type for analysis."""
    if "int" in dtype or "float" in dtype:
        return "numeric"
    elif "datetime" in dtype or "timedelta" in dtype:
        return "datetime"
    elif "bool" in dtype:
        return "boolean"
    elif "object" in dtype or "category" in dtype or "string" in dtype or "str" == dtype:
        return "categorical"
    return "text"


def _detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """Return {column_name: type_label} for every column."""
    return {col: _classify_column(str(df[col].dtype)) for col in df.columns}


# ── Analysis Service ────────────────────────────────────────────


class AnalysisService:
    """
    Service layer for the Analysis Workspace.
    Each public method returns (result_dict, error_message).
    """

    # ── Overview ─────────────────────────────────────────────────

    @staticmethod
    def get_overview(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """Generate overview data: KPIs, schema, quality summary, top insights."""
        key = _cache_key(user_id, dataset_id, "overview")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        # KPIs
        total_cells = df.shape[0] * df.shape[1]
        total_missing = int(df.isnull().sum().sum())
        missing_pct = round(total_missing / total_cells * 100, 2) if total_cells > 0 else 0
        duplicate_count = int(df.duplicated().sum())
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        categorical_cols = [c for c in df.columns if df[c].dtype == "object" or str(df[c].dtype) in ("category", "string") or str(df[c].dtype) == "str"]
        datetime_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

        kpis = {
            "rows": len(df),
            "columns": len(df.columns),
            "total_cells": total_cells,
            "numeric_count": len(numeric_cols),
            "categorical_count": len(categorical_cols),
            "datetime_count": len(datetime_cols),
            "missing_values": total_missing,
            "missing_pct": missing_pct,
            "duplicate_rows": duplicate_count,
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 ** 2, 2),
        }

        # Schema
        schema = []
        for col in df.columns:
            col_data = df[col]
            col_type = _classify_column(str(col_data.dtype))
            schema.append({
                "name": col,
                "dtype": str(col_data.dtype),
                "type": col_type,
                "missing": int(col_data.isnull().sum()),
                "unique": int(col_data.nunique()),
                "sample": [str(v)[:60] for v in col_data.dropna().head(3).tolist()],
            })

        # Quality summary using existing DataQualityAnalyzer
        quality_summary = {}
        try:
            from core.data_quality import DataQualityAnalyzer
            qa = DataQualityAnalyzer(df)
            quality_summary = qa.get_quality_report()
            # Convert numpy types for JSON
            quality_summary = AnalysisService._json_safe(quality_summary)
        except Exception:
            quality_summary = {
                "quality_score": 0,
                "missing_values": {col: int(df[col].isnull().sum()) for col in df.columns},
                "duplicate_rows": duplicate_count,
            }

        # Top insights using NLGInsightsGenerator
        insights = []
        try:
            from nlg.insights_generator import NLGInsightsGenerator
            analysis_results = {
                "summary": {
                    "dataset_shape": df.shape,
                    "missing_percentage": missing_pct,
                    "duplicate_rows": duplicate_count,
                    "memory_usage": kpis["memory_mb"],
                },
            }
            generator = NLGInsightsGenerator(analysis_results)
            raw_insights, _ = generator.generate_insights()
            insights = [
                {
                    "type": i.get("type", "info"),
                    "message": i.get("message", ""),
                    "priority": "medium",
                }
                for i in raw_insights
            ]
        except Exception as _e:
            # Optional consistency analyzer is unavailable in minimal installs.
            consistency_issues = []

        result = {
            "kpis": kpis,
            "schema": schema,
            "quality_summary": quality_summary,
            "insights": insights,
        }
        _set_cache(key, result)
        return result, None

    # ── Quality ──────────────────────────────────────────────────

    @staticmethod
    def get_quality(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """Detailed quality analysis: missing values, duplicates, invalid values, type issues."""
        key = _cache_key(user_id, dataset_id, "quality")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        # Missing values per column
        missing_per_col = []
        for col in df.columns:
            miss_count = int(df[col].isnull().sum())
            if miss_count > 0:
                miss_pct = round(miss_count / len(df) * 100, 2)
                missing_per_col.append({
                    "column": col,
                    "missing_count": miss_count,
                    "missing_pct": miss_pct,
                })
        missing_per_col.sort(key=lambda x: x["missing_pct"], reverse=True)

        # Duplicate rows
        duplicate_count = int(df.duplicated().sum())

        # Consistency issues using DataQualityAnalyzer
        consistency_issues = []
        try:
            from core.data_quality import DataQualityAnalyzer
            qa = DataQualityAnalyzer(df)
            consistency_issues = qa.check_data_consistency()
        except Exception as _e:
            consistency_issues = []

        # Type issues
        type_issues = []
        for col in df.columns:
            # Check for mixed types in object columns
            if df[col].dtype == "object" or 'string' in str(df[col].dtype):
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    types_in_col = set(type(v).__name__ for v in non_null.head(1000))
                    if len(types_in_col) > 1 and "str" in types_in_col:
                        type_issues.append({
                            "column": col,
                            "issue": "Mixed data types detected",
                            "types": list(types_in_col),
                        })

        # Overall quality score
        quality_score = 0
        try:
            from core.data_quality import DataQualityAnalyzer
            qa = DataQualityAnalyzer(df)
            quality_score = qa.generate_data_quality_score()
        except Exception as _e:
            missing_pct = df.isnull().sum().sum() / max(1, df.size) * 100
            duplicate_pct = df.duplicated().sum() / max(1, len(df)) * 100
            quality_score = max(0.0, min(100.0, 100.0 - missing_pct - min(20.0, duplicate_pct)))

        result = {
            "quality_score": quality_score,
            "missing_per_column": missing_per_col,
            "total_missing": int(df.isnull().sum().sum()),
            "total_cells": df.shape[0] * df.shape[1],
            "missing_pct": round(df.isnull().sum().sum() / (df.shape[0] * df.shape[1]) * 100, 2) if df.shape[0] * df.shape[1] > 0 else 0,
            "duplicate_rows": duplicate_count,
            "consistency_issues": consistency_issues,
            "type_issues": type_issues,
        }
        _set_cache(key, result)
        return result, None

    # ── Statistics ────────────────────────────────────────────────

    @staticmethod
    def get_statistics(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """Descriptive statistics for numeric, categorical, and datetime columns."""
        key = _cache_key(user_id, dataset_id, "statistics")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        numeric_stats = []
        categorical_stats = []
        datetime_stats = []

        for col in df.columns:
            col_type = _classify_column(str(df[col].dtype))
            col_data = df[col].dropna()

            if col_type == "numeric" and len(col_data) > 0:
                numeric_stats.append({
                    "column": col,
                    "count": int(len(col_data)),
                    "mean": round(float(col_data.mean()), 4),
                    "std": round(float(col_data.std()), 4) if len(col_data) > 1 else 0,
                    "min": round(float(col_data.min()), 4),
                    "max": round(float(col_data.max()), 4),
                    "median": round(float(col_data.median()), 4),
                    "q1": round(float(col_data.quantile(0.25)), 4),
                    "q3": round(float(col_data.quantile(0.75)), 4),
                    "iqr": round(float(col_data.quantile(0.75) - col_data.quantile(0.25)), 4),
                    "skewness": round(float(col_data.skew()), 4) if len(col_data) > 2 else 0,
                    "kurtosis": round(float(col_data.kurtosis()), 4) if len(col_data) > 2 else 0,
                    "zeros_pct": round(float((col_data == 0).sum() / len(col_data) * 100), 2),
                })

            elif col_type == "categorical" and len(col_data) > 0:
                value_counts = col_data.value_counts()
                categorical_stats.append({
                    "column": col,
                    "count": int(len(col_data)),
                    "unique": int(col_data.nunique()),
                    "top_value": str(col_data.mode().iloc[0]) if not col_data.mode().empty else None,
                    "top_frequency": int(value_counts.iloc[0]) if len(value_counts) > 0 else 0,
                    "top_pct": round(float(value_counts.iloc[0] / len(col_data) * 100), 2) if len(value_counts) > 0 else 0,
                    "cardinality": "high" if col_data.nunique() > 20 else "low",
                })

            elif col_type == "datetime" and len(col_data) > 0:
                try:
                    datetime_stats.append({
                        "column": col,
                        "count": int(len(col_data)),
                        "min": str(col_data.min()),
                        "max": str(col_data.max()),
                        "range_days": int((col_data.max() - col_data.min()).days),
                        "missing": int(df[col].isnull().sum()),
                    })
                except Exception as _e:
                    import logging
                    logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

            elif col_type == "boolean":
                categorical_stats.append({
                    "column": col,
                    "count": int(len(col_data)),
                    "unique": int(col_data.nunique()),
                    "top_value": str(col_data.mode().iloc[0]) if not col_data.mode().empty else None,
                    "top_frequency": int(col_data.value_counts().iloc[0]) if len(col_data.value_counts()) > 0 else 0,
                    "top_pct": round(float(col_data.value_counts().iloc[0] / len(col_data) * 100), 2) if len(col_data.value_counts()) > 0 else 0,
                    "cardinality": "low",
                })

        result = {
            "numeric": numeric_stats,
            "categorical": categorical_stats,
            "datetime": datetime_stats,
            "numeric_columns_count": len(numeric_stats),
            "categorical_columns_count": len(categorical_stats),
            "datetime_columns_count": len(datetime_stats),
        }
        _set_cache(key, result)
        return result, None

    # ── Correlations ───────────────────────────────────────────────

    @staticmethod
    def get_correlations(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """Correlation matrix + strong correlations list."""
        key = _cache_key(user_id, dataset_id, "correlations")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        numeric_df = df.select_dtypes(include=[np.number])
        if len(numeric_df.columns) < 2:
            return {
                "matrix": [],
                "columns": [],
                "strong_correlations": [],
                "method": "pearson",
            }, None

        # Pearson correlation (always available)
        corr_matrix = numeric_df.corr(method="pearson")

        # Attempt Spearman if scipy supports it
        spearman_matrix = None
        try:
            spearman_matrix = numeric_df.corr(method="spearman")
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        columns = corr_matrix.columns.tolist()

        # Build matrix for JSON (list of lists)
        matrix_data = []
        for i, row_col in enumerate(columns):
            row = []
            for j, col_col in enumerate(columns):
                val = corr_matrix.iloc[i, j]
                row.append(round(float(val), 4) if pd.notna(val) else None)
            matrix_data.append(row)

        # Strong correlations (|r| >= 0.6)
        strong_correlations = []
        for i in range(len(columns)):
            for j in range(i + 1, len(columns)):
                val = corr_matrix.iloc[i, j]
                if pd.notna(val) and abs(val) >= 0.6:
                    spearman_val = None
                    if spearman_matrix is not None:
                        sp_val = spearman_matrix.iloc[i, j]
                        if pd.notna(sp_val):
                            spearman_val = round(float(sp_val), 4)
                    strong_correlations.append({
                        "var1": columns[i],
                        "var2": columns[j],
                        "pearson": round(float(val), 4),
                        "spearman": spearman_val,
                        "strength": "strong" if abs(val) >= 0.8 else "moderate",
                    })
        strong_correlations.sort(key=lambda x: abs(x["pearson"]), reverse=True)

        result = {
            "matrix": matrix_data,
            "columns": columns,
            "strong_correlations": strong_correlations,
            "method": "pearson",
        }
        _set_cache(key, result)
        return result, None

    # ── Distributions ──────────────────────────────────────────────

    @staticmethod
    def get_distribution(dataset_id: int, user_id: int,
                         column: str) -> Tuple[Dict[str, Any], Optional[str]]:
        """Histogram + box plot data for a single numeric column."""
        extra = column
        key = _cache_key(user_id, dataset_id, "distribution", extra)
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        if column not in df.columns:
            return {}, f"Column '{column}' not found in dataset."

        col_type = _classify_column(str(df[column].dtype))
        if col_type != "numeric":
            return {}, f"Column '{column}' is {col_type}, not numeric. Use the categorical analysis for this column."

        series = df[column].dropna()
        if len(series) == 0:
            return {}, f"Column '{column}' has no valid data."

        # Histogram data
        num_bins = min(50, max(10, int(np.sqrt(len(series)))))
        counts, bin_edges = np.histogram(series, bins=num_bins)
        # Build bin labels (midpoints)
        bin_labels = [round(float((bin_edges[i] + bin_edges[i + 1]) / 2), 4) for i in range(len(counts))]
        histogram = {
            "counts": counts.tolist(),
            "bins": bin_labels,
        }

        # Box plot data
        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        median_val = float(series.median())
        mean_val = float(series.mean())
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        whisker_low = float(series[series >= lower_fence].min()) if (series >= lower_fence).any() else float(series.min())
        whisker_high = float(series[series <= upper_fence].max()) if (series <= upper_fence).any() else float(series.max())

        box_plot = {
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "median": round(median_val, 4),
            "mean": round(mean_val, 4),
            "iqr": round(iqr, 4),
            "lower_fence": round(lower_fence, 4),
            "upper_fence": round(upper_fence, 4),
            "whisker_low": round(whisker_low, 4),
            "whisker_high": round(whisker_high, 4),
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
        }

        result = {
            "column": column,
            "dtype": str(df[column].dtype),
            "count": int(len(series)),
            "histogram": histogram,
            "box_plot": box_plot,
            "stats": {
                "mean": round(mean_val, 4),
                "std": round(float(series.std()), 4),
                "skewness": round(float(series.skew()), 4),
                "kurtosis": round(float(series.kurtosis()), 4),
            },
        }
        _set_cache(key, result)
        return result, None

    @staticmethod
    def get_numeric_columns(dataset_id: int, user_id: int) -> Tuple[List[str], Optional[str]]:
        """Return list of numeric column names."""
        key = _cache_key(user_id, dataset_id, "numeric_cols")
        cached = _get_cache(key)
        if cached and "columns" in cached:
            return cached["columns"], None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return [], error

        cols = df.select_dtypes(include=[np.number]).columns.tolist()
        _set_cache(key, {"columns": cols})
        return cols, None

    # ── Outliers ──────────────────────────────────────────────────

    @staticmethod
    def get_outliers(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """IQR-based outlier detection across all numeric columns."""
        key = _cache_key(user_id, dataset_id, "outliers")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        outlier_results = []
        total_outliers = 0
        columns_with_outliers = 0

        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) < 10:
                continue

            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower_fence = q1 - 1.5 * iqr
            upper_fence = q3 + 1.5 * iqr

            outliers_mask = (series < lower_fence) | (series > upper_fence)
            outlier_count = int(outliers_mask.sum())
            if outlier_count > 0:
                outlier_values = series[outliers_mask].tolist()
                outlier_indices = series[outliers_mask].index.tolist()
                columns_with_outliers += 1
                total_outliers += outlier_count
                outlier_results.append({
                    "column": col,
                    "outlier_count": outlier_count,
                    "outlier_pct": round(outlier_count / len(series) * 100, 2),
                    "q1": round(float(q1), 4),
                    "q3": round(float(q3), 4),
                    "iqr": round(float(iqr), 4),
                    "lower_fence": round(float(lower_fence), 4),
                    "upper_fence": round(float(upper_fence), 4),
                    "min_outlier": round(float(min(outlier_values)), 4),
                    "max_outlier": round(float(max(outlier_values)), 4),
                    "sample_outliers": [round(float(v), 4) for v in outlier_values[:10]],
                })

        # Sort by outlier count descending
        outlier_results.sort(key=lambda x: x["outlier_count"], reverse=True)

        # Box plot data for the top columns with outliers
        box_plot_data = []
        for item in outlier_results[:6]:
            col = item["column"]
            series = df[col].dropna()
            box_plot_data.append({
                "column": col,
                "q1": item["q1"],
                "q3": item["q3"],
                "median": round(float(series.median()), 4),
                "mean": round(float(series.mean()), 4),
                "whisker_low": item["min_outlier"],
                "whisker_high": item["max_outlier"],
                "lower_fence": item["lower_fence"],
                "upper_fence": item["upper_fence"],
                "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4),
            })

        result = {
            "columns_with_outliers": columns_with_outliers,
            "total_outlier_values": total_outliers,
            "outlier_details": outlier_results,
            "box_plot_data": box_plot_data,
        }
        _set_cache(key, result)
        return result, None

    # ── Categorical ───────────────────────────────────────────────

    @staticmethod
    def get_categorical_analysis(dataset_id: int, user_id: int,
                                column: Optional[str] = None) -> Tuple[Dict[str, Any], Optional[str]]:
        """Frequency analysis for categorical columns."""
        extra = column or "all"
        key = _cache_key(user_id, dataset_id, "categorical", extra)
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        cat_cols = [
            c for c in df.columns
            if df[c].dtype == "object" or str(df[c].dtype) in ("category", "string") or str(df[c].dtype) == "str"
            or _classify_column(str(df[c].dtype)) in ("boolean", "categorical")
        ]

        if not cat_cols:
            return {"categorical_columns": [], "analysis": None}, None

        if column:
            if column not in cat_cols:
                return {}, f"Column '{column}' is not a categorical column."
            cols_to_analyze = [column]
        else:
            cols_to_analyze = cat_cols[:20]  # limit

        analyses = []
        for col in cols_to_analyze:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            value_counts = series.value_counts()
            total = len(series)
            top_n = min(20, len(value_counts))
            freq_table = []
            for val, count in value_counts.head(top_n).items():
                freq_table.append({
                    "value": str(val)[:80],
                    "count": int(count),
                    "percentage": round(float(count / total * 100), 2),
                })
            analyses.append({
                "column": col,
                "unique": int(series.nunique()),
                "total": int(total),
                "top_value": str(value_counts.index[0]) if len(value_counts) > 0 else None,
                "top_count": int(value_counts.iloc[0]) if len(value_counts) > 0 else 0,
                "top_pct": round(float(value_counts.iloc[0] / total * 100), 2) if len(value_counts) > 0 else 0,
                "frequency_table": freq_table,
                "cardinality": "high" if series.nunique() > 20 else "low",
            })

        result = {
            "categorical_columns": cat_cols,
            "analysis": analyses[0] if column and analyses else analyses,
            "all_analyses": analyses if not column else [analyses[0]] if analyses else [],
        }
        _set_cache(key, result)
        return result, None

    @staticmethod
    def get_categorical_columns(dataset_id: int, user_id: int) -> Tuple[List[str], Optional[str]]:
        """Return list of categorical column names."""
        key = _cache_key(user_id, dataset_id, "cat_cols")
        cached = _get_cache(key)
        if cached and "columns" in cached:
            return cached["columns"], None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return [], error

        cols = [
            c for c in df.columns
            if df[c].dtype == "object" or str(df[c].dtype) in ("category", "string") or str(df[c].dtype) == "str"
            or _classify_column(str(df[c].dtype)) in ("boolean", "categorical")
        ]
        _set_cache(key, {"columns": cols})
        return cols, None

    # ── Insights ──────────────────────────────────────────────────

    @staticmethod
    def get_insights(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """
        Generate prioritized insights by combining quality, statistical,
        correlation, and trend data. Uses NLGInsightsGenerator.
        """
        key = _cache_key(user_id, dataset_id, "insights")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        all_insights = []

        # 1. Quality insights
        try:
            quality_score = max(0.0, 100.0 - (df.isnull().sum().sum() / max(1, df.size) * 100.0))
            issues = []

            if quality_score < 70:
                all_insights.append({
                    "type": "warning",
                    "message": f"Data quality score is {quality_score:.1f}/100, indicating significant data quality issues that should be addressed before analysis.",
                    "priority": "high",
                    "category": "quality",
                })
            elif quality_score < 90:
                all_insights.append({
                    "type": "info",
                    "message": f"Data quality score is {quality_score:.1f}/100. Some improvements could enhance analysis reliability.",
                    "priority": "medium",
                    "category": "quality",
                })

            missing_pct = df.isnull().sum().sum() / df.size * 100
            if missing_pct > 10:
                all_insights.append({
                    "type": "warning",
                    "message": f"High missing data rate ({missing_pct:.1f}%). Consider imputation or reviewing upstream data collection processes.",
                    "priority": "high",
                    "category": "quality",
                })

            if issues:
                for issue in issues[:3]:
                    all_insights.append({
                        "type": "warning",
                        "message": issue,
                        "priority": "medium",
                        "category": "quality",
                    })

            duplicate_count = int(df.duplicated().sum())
            if duplicate_count > 0:
                all_insights.append({
                    "type": "info",
                    "message": f"Found {duplicate_count:,} exact duplicate rows that may inflate statistical metrics.",
                    "priority": "low",
                    "category": "quality",
                })
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        # 2. Statistical insights (skewness, distribution)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols[:10]:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            skew = series.skew()
            if abs(skew) > 2:
                direction = "right" if skew > 0 else "left"
                all_insights.append({
                    "type": "info",
                    "message": f"'{col}' has a highly {direction}-skewed distribution (skewness={skew:.2f}), which may affect statistical tests and model performance.",
                    "priority": "medium",
                    "category": "statistics",
                })

        # 3. Correlation insights
        if len(numeric_cols) >= 2:
            corr_matrix = df[numeric_cols].corr(method="pearson")
            for i in range(len(numeric_cols)):
                for j in range(i + 1, len(numeric_cols)):
                    val = corr_matrix.iloc[i, j]
                    if pd.notna(val) and abs(val) >= 0.7:
                        direction = "positively" if val > 0 else "negatively"
                        strength = "strong" if abs(val) >= 0.8 else "moderate"
                        all_insights.append({
                            "type": "insight",
                            "message": f"'{numeric_cols[i]}' and '{numeric_cols[j]}' have a {strength} {direction} correlation (r={val:.3f}).",
                            "priority": "high" if abs(val) >= 0.8 else "medium",
                            "category": "correlation",
                        })

        # 4. Outlier insights
        outlier_count = 0
        for col in numeric_cols[:10]:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            outliers = ((series < q1 - 1.5 * iqr) | (series > q3 + 1.5 * iqr)).sum()
            if outliers > 0:
                outlier_count += int(outliers)
                if outliers / len(series) > 0.05:
                    all_insights.append({
                        "type": "warning",
                        "message": f"'{col}' contains {outliers} outlier values ({outliers / len(series) * 100:.1f}%) using IQR method.",
                        "priority": "medium",
                        "category": "outliers",
                    })

        if outlier_count > 0:
            all_insights.append({
                "type": "info",
                "message": f"A total of {outlier_count:,} outlier values were detected across numeric columns using the IQR method.",
                "priority": "low",
                "category": "outliers",
            })

        # 5. Trend insights (using existing TrendDetector)
        trends = []
        try:
            from ai_engine.services.trend_detector import TrendDetector
            td = TrendDetector(df)
            trends = td.detect_trends()
            for trend in trends[:5]:
                if trend.direction.value in ("upward", "downward"):
                    all_insights.append({
                        "type": "insight",
                        "message": trend.summary_text,
                        "priority": "high" if trend.direction.value == "downward" else "medium",
                        "category": "trends",
                    })
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        # 6. Anomalies (using AnomalyDetector)
        anomaly_payload = None
        anomaly_summary = None
        try:
            from ai_engine.services.anomaly_detector import AnomalyDetector
            ad = AnomalyDetector(df)
            anomaly_summary = ad.detect_anomalies()
            anomaly_payload = {
                "count": anomaly_summary.anomalous_rows_count,
                "percentage": anomaly_summary.anomaly_percentage,
                "items": [{"index": a.row_index, "score": a.score, "description": a.reason, "method": getattr(a.method, 'value', str(a.method))} for a in anomaly_summary.detected_anomalies[:5]]
            }
            if anomaly_summary.anomalous_rows_count > 0:
                all_insights.append({
                    "type": "warning",
                    "message": f"Detected {anomaly_summary.anomalous_rows_count} anomalous rows ({anomaly_summary.anomaly_percentage:.1f}%).",
                    "priority": "high",
                    "category": "anomalies",
                })
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        # 7. Root Causes (using RootCauseAnalyzer)
        root_causes_payload = []
        root_causes = []
        try:
            from ai_engine.services.root_cause_analyzer import RootCauseAnalyzer
            rca = RootCauseAnalyzer(df)
            root_causes = rca.analyze()
            root_causes_payload = [
                {"issue_type": r.feature, "description": r.description, "impact_level": getattr(r, 'impact_score', ''), "suggested_action": r.condition}
                for r in root_causes
            ]
            for rc in root_causes[:3]:
                all_insights.append({
                    "type": "insight",
                    "message": f"Root cause for {rc.feature}: {rc.description}",
                    "priority": "high",
                    "category": "root_causes",
                })
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
            
        # 8. Recommendations (using RecommendationEngine)
        recommendations_payload = []
        try:
            from ai_engine.services.recommendation_engine import RecommendationEngine
            re = RecommendationEngine()
            summary_data = {"dataset_name": "Dataset", "dataset_shape": df.shape,
                            "missing_percentage": float(df.isnull().sum().sum() / max(1, df.size) * 100),
                            "duplicate_rows": int(df.duplicated().sum())}
            recommendations = re.generate_recommendations(summary_data, trends, anomaly_summary, root_causes)
            recommendations_payload = [
                {"title": r.title, "description": r.description, "expected_impact": r.category, "priority": getattr(r.impact, 'value', str(r.impact))}
                for r in recommendations
            ]
            for rec in recommendations[:3]:
                all_insights.append({
                    "type": "insight",
                    "message": f"Recommendation: {rec.title} - {rec.description}",
                    "priority": "medium",
                    "category": "recommendations",
                })
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        # Sort by priority: high first, then medium, then low
        priority_order = {"high": 0, "medium": 1, "low": 2}
        all_insights.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))

        result = {
            "insights": all_insights,
            "total": len(all_insights),
            "high_priority": len([i for i in all_insights if i["priority"] == "high"]),
            "medium_priority": len([i for i in all_insights if i["priority"] == "medium"]),
            "low_priority": len([i for i in all_insights if i["priority"] == "low"]),
            "anomalies": anomaly_payload,
            "root_causes": root_causes_payload,
            "recommendations": recommendations_payload,
        }
        _set_cache(key, result)
        return result, None

    # ── Time Series ────────────────────────────────────────────────

    @staticmethod
    def get_timeseries_analysis(dataset_id: int, user_id: int, date_col: Optional[str] = None, value_col: Optional[str] = None) -> Tuple[Dict[str, Any], Optional[str]]:
        """Time series analysis for a date and value column."""
        key = _cache_key(user_id, dataset_id, "timeseries", f"{date_col}:{value_col}")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        # Auto select columns if not provided
        if not date_col:
            dt_cols = [c for c in df.columns if _classify_column(str(df[c].dtype)) == "datetime"]
            if not dt_cols:
                return {}, "No datetime column found."
            date_col = dt_cols[0]
            
        if not value_col:
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if not num_cols:
                return {}, "No numeric column found."
            value_col = num_cols[0]
            
        if date_col not in df.columns or value_col not in df.columns:
            return {}, "Selected columns not found in dataset."

        try:
            from timeseries.ts_analyzer import TimeSeriesAnalyzer
            tsa = TimeSeriesAnalyzer(df, date_col, value_col)
            
            stationarity = tsa.check_stationarity()
            seasonality = tsa.detect_seasonality()
            
            # Make seasonality JSON serializable
            if isinstance(seasonality, dict) and "error" not in seasonality:
                for k in ["trend", "seasonal", "residual"]:
                    if k in seasonality and isinstance(seasonality[k], dict):
                        seasonality[k] = {str(k_dt): float(v) for k_dt, v in seasonality[k].items()}
            
            forecast = tsa.forecast_prophet()
            if isinstance(forecast, pd.DataFrame):
                forecast_data = []
                for _, row in forecast.iterrows():
                    forecast_data.append({
                        "ds": str(row["ds"]),
                        "yhat": float(row["yhat"]),
                        "yhat_lower": float(row["yhat_lower"]),
                        "yhat_upper": float(row["yhat_upper"])
                    })
                forecast = {"data": forecast_data}
                
            # Original data for plotting
            ts_data = df[[date_col, value_col]].dropna().sort_values(date_col).tail(300)
            original_data = {
                "dates": [str(d) for d in ts_data[date_col]],
                "values": [float(v) for v in ts_data[value_col]]
            }
            
            # Anomalies
            anomalies = {}
            try:
                anoms = tsa.detect_anomalies_time_series()
                if isinstance(anoms, pd.Series):
                    anom_indices = anoms[anoms].index
                    anomalies = {
                        "count": int(anoms.sum()),
                        "dates": [str(d) for d in anom_indices]
                    }
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
                
            result = {
                "date_col": date_col,
                "value_col": value_col,
                "stationarity": stationarity,
                "seasonality": seasonality,
                "forecast": forecast,
                "original_data": original_data,
                "anomalies": anomalies,
                "numeric_cols": df.select_dtypes(include=[np.number]).columns.tolist(),
                "datetime_cols": [c for c in df.columns if _classify_column(str(df[c].dtype)) == "datetime"]
            }
            
            _set_cache(key, result)
            return result, None
        except Exception as e:
            return {}, str(e)

    # ── Utility ───────────────────────────────────────────────────

    @staticmethod
    def _json_safe(data: Any) -> Any:
        """Recursively convert numpy/pandas types to Python native types for JSON."""
        import json
        return json.loads(json.dumps(data, default=str))

    @staticmethod
    def get_dataset_columns(dataset_id: int, user_id: int) -> Tuple[Dict[str, Any], Optional[str]]:
        """Return all columns with their types for the column selector UI."""
        key = _cache_key(user_id, dataset_id, "columns")
        cached = _get_cache(key)
        if cached:
            return cached, None

        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return {}, error

        columns = []
        for col in df.columns:
            col_type = _classify_column(str(df[col].dtype))
            columns.append({
                "name": col,
                "type": col_type,
                "dtype": str(df[col].dtype),
            })

        result = {"columns": columns}
        _set_cache(key, result)
        return result, None
