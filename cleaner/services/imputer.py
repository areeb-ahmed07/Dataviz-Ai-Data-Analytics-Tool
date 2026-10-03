"""
Service: Missing Value Imputation (Statistical, Groupby, KNN, and Threshold Dropping)
"""
from datetime import datetime
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np
from sklearn.impute import KNNImputer

from cleaner.domain.cleaning_config import ImputationConfig
from cleaner.domain.cleaning_result import AuditEntry

class ImputerService:
    """Service for missing value imputation and missingness handling"""

    def process(self, df: pd.DataFrame, config: ImputationConfig) -> Tuple[pd.DataFrame, AuditEntry]:
        df_cleaned = df.copy()
        rows_before, cols_before = df_cleaned.shape
        affected_cols = []

        # 1. Drop columns exceeding missing threshold
        if config.drop_threshold_cols is not None and 0.0 < config.drop_threshold_cols <= 1.0:
            missing_ratio = df_cleaned.isnull().mean()
            cols_to_drop = missing_ratio[missing_ratio > config.drop_threshold_cols].index.tolist()
            if cols_to_drop:
                df_cleaned = df_cleaned.drop(columns=cols_to_drop)
                affected_cols.extend(cols_to_drop)

        # 2. Drop rows exceeding missing threshold
        if config.drop_threshold_rows is not None and 0.0 < config.drop_threshold_rows <= 1.0:
            row_missing_ratio = df_cleaned.isnull().mean(axis=1)
            rows_to_keep = row_missing_ratio <= config.drop_threshold_rows
            df_cleaned = df_cleaned[rows_to_keep]

        # 3. Column-by-column or automated imputation
        for col in df_cleaned.columns:
            if df_cleaned[col].isnull().sum() == 0:
                continue

            strategy = config.column_strategies.get(col, None)
            is_numeric = pd.api.types.is_numeric_dtype(df_cleaned[col])

            if not strategy:
                strategy = config.default_numeric_strategy if is_numeric else config.default_categorical_strategy

            affected_cols.append(col)

            # Check if group_by_col is available and requested for numeric/categorical columns
            if config.group_by_col and config.group_by_col in df_cleaned.columns and config.group_by_col != col:
                try:
                    if is_numeric:
                        if strategy == 'mean':
                            df_cleaned[col] = df_cleaned.groupby(config.group_by_col)[col].transform(lambda x: x.fillna(x.mean()))
                        elif strategy == 'median':
                            df_cleaned[col] = df_cleaned.groupby(config.group_by_col)[col].transform(lambda x: x.fillna(x.median()))
                    else:
                        if strategy == 'mode':
                            df_cleaned[col] = df_cleaned.groupby(config.group_by_col)[col].transform(
                                lambda x: x.fillna(x.mode()[0] if not x.mode().empty else config.constant_value)
                            )
                except Exception:
                    pass  # Fallback to standard global strategy if groupby fails

            # Standard global imputation strategies if missing values still remain
            if df_cleaned[col].isnull().sum() > 0:
                if strategy == 'mean' and is_numeric:
                    df_cleaned[col] = df_cleaned[col].fillna(df_cleaned[col].mean())
                elif strategy == 'median' and is_numeric:
                    df_cleaned[col] = df_cleaned[col].fillna(df_cleaned[col].median())
                elif strategy == 'mode':
                    mode_val = df_cleaned[col].mode()
                    fill_val = mode_val.iloc[0] if not mode_val.empty else (config.numeric_constant if is_numeric else config.constant_value)
                    df_cleaned[col] = df_cleaned[col].fillna(fill_val)
                elif strategy == 'constant':
                    fill_val = config.numeric_constant if is_numeric else config.constant_value
                    df_cleaned[col] = df_cleaned[col].fillna(fill_val)
                elif strategy == 'ffill':
                    df_cleaned[col] = df_cleaned[col].ffill().bfill()
                elif strategy == 'bfill':
                    df_cleaned[col] = df_cleaned[col].bfill().ffill()

        # 4. KNN Imputation for remaining numeric columns if requested
        knn_requested = any(s == 'knn' for s in config.column_strategies.values()) or config.default_numeric_strategy == 'knn'
        numeric_cols_with_na = [c for c in df_cleaned.select_dtypes(include=[np.number]).columns if df_cleaned[c].isnull().sum() > 0]
        
        if knn_requested and numeric_cols_with_na:
            try:
                knn = KNNImputer(n_neighbors=config.knn_neighbors)
                df_cleaned[numeric_cols_with_na] = knn.fit_transform(df_cleaned[numeric_cols_with_na])
                affected_cols.extend(numeric_cols_with_na)
            except Exception:
                # Fallback to median for numeric
                for c in numeric_cols_with_na:
                    df_cleaned[c] = df_cleaned[c].fillna(df_cleaned[c].median())

        rows_after, cols_after = df_cleaned.shape
        affected_cols = list(set(affected_cols))

        audit_entry = AuditEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation="Missing Value Imputation",
            details=f"Imputed missing values across {len(affected_cols)} column(s). Default numeric: {config.default_numeric_strategy}, default cat: {config.default_categorical_strategy}.",
            rows_before=rows_before,
            rows_after=rows_after,
            cols_before=cols_before,
            cols_after=cols_after,
            affected_columns=affected_cols
        )

        return df_cleaned, audit_entry

    def inspect_missing(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Inspect missing values by column"""
        missing_count = df.isnull().sum()
        total_rows = len(df)
        missing_pct = (missing_count / total_rows * 100.0) if total_rows > 0 else missing_count * 0.0

        df_summary = pd.DataFrame({
            'missing_count': missing_count,
            'missing_percentage': missing_pct.round(2),
            'dtype': df.dtypes.astype(str)
        })

        return {
            'total_cells': int(df.size),
            'missing_cells': int(missing_count.sum()),
            'missing_ratio': round((missing_count.sum() / df.size * 100.0) if df.size > 0 else 0.0, 2),
            'columns_summary': df_summary[df_summary['missing_count'] > 0].to_dict(orient='index')
        }
