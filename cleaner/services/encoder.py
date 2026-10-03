"""
Service: Categorical Encoding (One-Hot, Ordinal/Label, Frequency/Count, Target Encoding)
"""
from datetime import datetime
from typing import Tuple, List, Dict, Any
import pandas as pd
import numpy as np

from cleaner.domain.cleaning_config import EncodingConfig
from cleaner.domain.cleaning_result import AuditEntry

class EncoderService:
    """Service for Categorical Feature Encoding"""

    def process(self, df: pd.DataFrame, config: EncodingConfig) -> Tuple[pd.DataFrame, AuditEntry]:
        df_cleaned = df.copy()
        rows_before, cols_before = df_cleaned.shape

        cat_cols = config.columns if config.columns else df_cleaned.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
        if not cat_cols:
            audit_entry = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Categorical Encoding",
                details="No categorical columns found for encoding.",
                rows_before=rows_before, rows_after=rows_before,
                cols_before=cols_before, cols_after=cols_before,
                affected_columns=[]
            )
            return df_cleaned, audit_entry

        affected_cols = list(cat_cols)
        strategy = config.strategy.lower()

        # Strategy 1: One-Hot Encoding
        if strategy == 'onehot':
            df_cleaned = pd.get_dummies(
                df_cleaned,
                columns=cat_cols,
                drop_first=config.drop_first,
                dtype=int
            )
            details = f"One-Hot encoded {len(cat_cols)} column(s) (drop_first={config.drop_first})"

        # Strategy 2: Ordinal / Label Encoding
        elif strategy in ['ordinal', 'label']:
            for col in cat_cols:
                # Convert to category codes
                cat_type = pd.CategoricalDtype(categories=df_cleaned[col].dropna().unique())
                df_cleaned[col] = df_cleaned[col].astype(cat_type).cat.codes
            details = f"Ordinal/Label encoded {len(cat_cols)} column(s)"

        # Strategy 3: Frequency / Count Encoding
        elif strategy in ['frequency', 'count']:
            for col in cat_cols:
                freq = df_cleaned[col].value_counts(normalize=(strategy == 'frequency'))
                df_cleaned[col] = df_cleaned[col].map(freq)
            details = f"{strategy.title()} encoded {len(cat_cols)} column(s)"

        # Strategy 4: Target Encoding
        elif strategy == 'target':
            if not config.target_col or config.target_col not in df_cleaned.columns:
                # Fallback to ordinal if target_col missing
                for col in cat_cols:
                    cat_type = pd.CategoricalDtype(categories=df_cleaned[col].dropna().unique())
                    df_cleaned[col] = df_cleaned[col].astype(cat_type).cat.codes
                details = f"Target encoding failed (missing target column '{config.target_col}'). Fallback to Ordinal encoding."
            else:
                target_series = df_cleaned[config.target_col]
                for col in cat_cols:
                    if col == config.target_col:
                        continue
                    means = df_cleaned.groupby(col)[config.target_col].mean()
                    df_cleaned[col] = df_cleaned[col].map(means)
                details = f"Target encoded {len(cat_cols)} column(s) using target column '{config.target_col}'"

        rows_after, cols_after = df_cleaned.shape

        audit_entry = AuditEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation="Categorical Encoding",
            details=details,
            rows_before=rows_before,
            rows_after=rows_after,
            cols_before=cols_before,
            cols_after=cols_after,
            affected_columns=affected_cols
        )

        return df_cleaned, audit_entry
