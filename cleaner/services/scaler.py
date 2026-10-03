"""
Service: Feature Scaling & Normalization (Standard, MinMax, Robust, MaxAbs, Quantile, Power)
"""
from datetime import datetime
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np
from sklearn.preprocessing import (
    StandardScaler,
    MinMaxScaler,
    RobustScaler,
    MaxAbsScaler,
    QuantileTransformer,
    PowerTransformer
)

from cleaner.domain.cleaning_config import ScalingConfig
from cleaner.domain.cleaning_result import AuditEntry

class ScalerService:
    """Service for Feature Scaling and Transformation"""

    def process(self, df: pd.DataFrame, config: ScalingConfig) -> Tuple[pd.DataFrame, AuditEntry]:
        df_cleaned = df.copy()
        rows_before, cols_before = df_cleaned.shape

        numeric_cols = config.columns if config.columns else df_cleaned.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            audit_entry = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Feature Scaling",
                details="No numeric columns found for feature scaling.",
                rows_before=rows_before, rows_after=rows_before,
                cols_before=cols_before, cols_after=cols_before,
                affected_columns=[]
            )
            return df_cleaned, audit_entry

        affected_cols = list(numeric_cols)
        strategy = config.strategy.lower()

        # Select Scaler instance
        if strategy == 'standard':
            scaler = StandardScaler()
        elif strategy == 'minmax':
            scaler = MinMaxScaler(feature_range=config.feature_range)
        elif strategy == 'robust':
            scaler = RobustScaler()
        elif strategy == 'maxabs':
            scaler = MaxAbsScaler()
        elif strategy == 'quantile':
            scaler = QuantileTransformer(output_distribution='normal', random_state=42)
        elif strategy == 'power':
            scaler = PowerTransformer(method='yeo-johnson')
        else:
            scaler = StandardScaler()
            strategy = 'standard'

        try:
            # Handle potential NaNs before scaling
            df_sub = df_cleaned[numeric_cols].copy()
            for col in numeric_cols:
                if df_sub[col].isnull().sum() > 0:
                    df_sub[col] = df_sub[col].fillna(df_sub[col].median())

            scaled_values = scaler.fit_transform(df_sub)
            df_cleaned[numeric_cols] = scaled_values
            details = f"Applied {strategy.title()} Scaler across {len(numeric_cols)} numeric column(s)."
        except Exception as e:
            details = f"Scaling using {strategy.title()} failed: {str(e)}"

        rows_after, cols_after = df_cleaned.shape

        audit_entry = AuditEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation="Feature Scaling",
            details=details,
            rows_before=rows_before,
            rows_after=rows_after,
            cols_before=cols_before,
            cols_after=cols_after,
            affected_columns=affected_cols
        )

        return df_cleaned, audit_entry
