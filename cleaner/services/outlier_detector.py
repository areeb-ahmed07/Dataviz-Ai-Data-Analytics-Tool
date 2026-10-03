"""
Service: Outlier Detection and Capping / Trimming (IQR, Z-Score, Isolation Forest, LOF)
"""
from datetime import datetime
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

from cleaner.domain.cleaning_config import OutlierConfig
from cleaner.domain.cleaning_result import AuditEntry

class OutlierDetectorService:
    """Service for Outlier Detection and Handling (Capping / Trimming)"""

    def process(self, df: pd.DataFrame, config: OutlierConfig) -> Tuple[pd.DataFrame, AuditEntry]:
        df_cleaned = df.copy()
        rows_before, cols_before = df_cleaned.shape

        numeric_cols = config.columns if config.columns else df_cleaned.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            audit_entry = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Outlier Detection",
                details="No numeric columns found for outlier detection.",
                rows_before=rows_before, rows_after=rows_before,
                cols_before=cols_before, cols_after=cols_before,
                affected_columns=[]
            )
            return df_cleaned, audit_entry

        affected_cols = []
        outliers_handled = 0

        # Method 1: IQR (Interquartile Range)
        if config.method == 'iqr':
            for col in numeric_cols:
                series = df_cleaned[col].dropna()
                if len(series) == 0:
                    continue

                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                if iqr == 0:
                    continue

                lower_bound = q1 - (config.iqr_multiplier * iqr)
                upper_bound = q3 + (config.iqr_multiplier * iqr)

                outlier_mask = (df_cleaned[col] < lower_bound) | (df_cleaned[col] > upper_bound)
                num_outliers = int(outlier_mask.sum())

                if num_outliers > 0:
                    affected_cols.append(col)
                    outliers_handled += num_outliers
                    if config.action == 'cap':
                        df_cleaned[col] = np.where(df_cleaned[col] < lower_bound, lower_bound, df_cleaned[col])
                        df_cleaned[col] = np.where(df_cleaned[col] > upper_bound, upper_bound, df_cleaned[col])
                    elif config.action == 'drop':
                        df_cleaned = df_cleaned[~outlier_mask]

        # Method 2: Z-Score
        elif config.method == 'zscore':
            for col in numeric_cols:
                series = df_cleaned[col].dropna()
                if len(series) < 2:
                    continue

                mean_val = series.mean()
                std_val = series.std()
                if std_val == 0:
                    continue

                z_scores = (df_cleaned[col] - mean_val) / std_val
                outlier_mask = z_scores.abs() > config.zscore_threshold
                num_outliers = int(outlier_mask.sum())

                if num_outliers > 0:
                    affected_cols.append(col)
                    outliers_handled += num_outliers
                    if config.action == 'cap':
                        lower_bound = mean_val - (config.zscore_threshold * std_val)
                        upper_bound = mean_val + (config.zscore_threshold * std_val)
                        df_cleaned[col] = np.where(df_cleaned[col] < lower_bound, lower_bound, df_cleaned[col])
                        df_cleaned[col] = np.where(df_cleaned[col] > upper_bound, upper_bound, df_cleaned[col])
                    elif config.action == 'drop':
                        df_cleaned = df_cleaned[~outlier_mask]

        # Method 3: Isolation Forest
        elif config.method == 'isolation_forest':
            clean_sub = df_cleaned[numeric_cols].dropna()
            if len(clean_sub) > 10:
                iso = IsolationForest(contamination=config.contamination, random_state=42)
                preds = iso.fit_predict(clean_sub)
                anomaly_indices = clean_sub.index[preds == -1]
                outliers_handled = len(anomaly_indices)
                affected_cols = numeric_cols
                if config.action == 'drop':
                    df_cleaned = df_cleaned.drop(index=anomaly_indices)

        # Method 4: Local Outlier Factor (LOF)
        elif config.method == 'lof':
            clean_sub = df_cleaned[numeric_cols].dropna()
            if len(clean_sub) > 10:
                lof = LocalOutlierFactor(contamination=config.contamination)
                preds = lof.fit_predict(clean_sub)
                anomaly_indices = clean_sub.index[preds == -1]
                outliers_handled = len(anomaly_indices)
                affected_cols = numeric_cols
                if config.action == 'drop':
                    df_cleaned = df_cleaned.drop(index=anomaly_indices)

        rows_after, cols_after = df_cleaned.shape

        audit_entry = AuditEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation="Outlier Detection & Action",
            details=f"Method: {config.method.upper()}, Action: {config.action.upper()}. Flagged/handled {outliers_handled:,} outlier values across {len(affected_cols)} column(s).",
            rows_before=rows_before,
            rows_after=rows_after,
            cols_before=cols_before,
            cols_after=cols_after,
            affected_columns=affected_cols
        )

        return df_cleaned, audit_entry

    def detect_outliers_summary(self, df: pd.DataFrame, multiplier: float = 1.5) -> Dict[str, Dict[str, Any]]:
        """Inspect outlier stats per numeric column using IQR"""
        summary = {}
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            q1 = series.quantile(0.25)
            q3 = series.quantile(0.75)
            iqr = q3 - q1
            lower_bound = q1 - (multiplier * iqr)
            upper_bound = q3 + (multiplier * iqr)
            outliers = series[(series < lower_bound) | (series > upper_bound)]
            summary[col] = {
                'outlier_count': len(outliers),
                'outlier_percentage': round((len(outliers) / len(series) * 100.0) if len(series) > 0 else 0.0, 2),
                'lower_bound': float(lower_bound),
                'upper_bound': float(upper_bound)
            }
        return summary
