"""
Service: Duplicate Removal (Exact and Fuzzy Duplicate Detection)
"""
import time
import difflib
from datetime import datetime
from typing import Tuple, List
import pandas as pd
import numpy as np

from cleaner.domain.cleaning_config import DuplicateConfig
from cleaner.domain.cleaning_result import AuditEntry

class DuplicateRemoverService:
    """Service to handle exact and fuzzy duplicate detection and removal"""

    def process(self, df: pd.DataFrame, config: DuplicateConfig) -> Tuple[pd.DataFrame, AuditEntry]:
        """
        Execute duplicate removal based on DuplicateConfig
        """
        df_cleaned = df.copy()
        rows_before, cols_before = df_cleaned.shape
        affected_cols = config.subset if config.subset else list(df_cleaned.columns)

        # 1. Exact Duplicate Removal
        if not config.fuzzy_enable:
            df_cleaned = df_cleaned.drop_duplicates(subset=config.subset, keep=config.keep)
            details = f"Exact duplicate removal (subset={config.subset if config.subset else 'ALL'}, keep={config.keep})"
        else:
            # 2. Fuzzy Duplicate Removal for Text Columns
            fuzzy_cols = config.fuzzy_columns if config.fuzzy_columns else df_cleaned.select_dtypes(include=['object', 'string']).columns.tolist()
            if not fuzzy_cols:
                # Fallback to exact if no text columns
                df_cleaned = df_cleaned.drop_duplicates(subset=config.subset, keep=config.keep)
                details = "Exact duplicate removal (Fuzzy requested but no text columns available)"
            else:
                drop_indices = set()
                threshold = config.fuzzy_threshold
                
                for col in fuzzy_cols:
                    values = df_cleaned[col].dropna().astype(str).tolist()
                    indices = df_cleaned[col].dropna().index.tolist()
                    n = len(values)
                    
                    # For performance on large datasets, limit pairwise comparison sample if needed
                    # Compare pairs
                    for i in range(n):
                        if indices[i] in drop_indices:
                            continue
                        for j in range(i + 1, min(i + 500, n)): # window comparison to optimize speed
                            if indices[j] in drop_indices:
                                continue
                            ratio = difflib.SequenceMatcher(None, values[i].lower().strip(), values[j].lower().strip()).ratio()
                            if ratio >= threshold:
                                drop_indices.add(indices[j])
                                
                df_cleaned = df_cleaned.drop(index=list(drop_indices))
                details = f"Fuzzy duplicate removal on columns={fuzzy_cols} (threshold={config.fuzzy_threshold:.2f})"

        rows_after, cols_after = df_cleaned.shape
        rows_removed = rows_before - rows_after

        audit_entry = AuditEntry(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            operation="Duplicate Removal",
            details=f"{details}. Removed {rows_removed:,} duplicate row(s).",
            rows_before=rows_before,
            rows_after=rows_after,
            cols_before=cols_before,
            cols_after=cols_after,
            affected_columns=affected_cols
        )

        return df_cleaned, audit_entry

    def inspect_duplicates(self, df: pd.DataFrame, subset: List[str] = None) -> dict:
        """
        Inspect duplicate stats without mutating DataFrame
        """
        num_exact_duplicates = df.duplicated(subset=subset).sum()
        total_rows = len(df)
        return {
            "total_rows": total_rows,
            "duplicate_count": int(num_exact_duplicates),
            "duplicate_percentage": round((num_exact_duplicates / total_rows * 100.0) if total_rows > 0 else 0.0, 2),
            "subset": subset
        }
