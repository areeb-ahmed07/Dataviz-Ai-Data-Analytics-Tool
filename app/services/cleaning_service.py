"""
DataViz Pro — Cleaning Service

Orchestration layer for the Data Cleaning & Preparation Studio.
Wraps the existing cleaner/ module (CleaningPipeline, ImputerService,
DuplicateRemoverService, OutlierDetectorService, EncoderService, ScalerService).

Handles:
  - Loading datasets into a working copy
  - Detecting data quality problems
  - Previewing and applying cleaning operations
  - Column management (rename, remove, reorder, type conversion)
  - Constant column detection
  - Feature/target selection
  - Saving cleaned datasets as new versions
  - Pipeline reproducibility
"""

import os
import json
import uuid
import shutil
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd
import numpy as np

from app.services.dataset_service import DatasetService
from auth.database import DatasetDB, get_session

# ── Import existing cleaner engines ──────────────────────────────
from cleaner.services.cleaning_pipeline import CleaningPipeline
from cleaner.services.duplicate_remover import DuplicateRemoverService
from cleaner.services.imputer import ImputerService
from cleaner.services.outlier_detector import OutlierDetectorService
from cleaner.services.encoder import EncoderService
from cleaner.services.scaler import ScalerService
from cleaner.domain.cleaning_config import (
    DuplicateConfig,
    ImputationConfig,
    OutlierConfig,
    EncodingConfig,
    ScalingConfig,
)
from cleaner.domain.cleaning_result import AuditEntry
from datetime import datetime

import sys
import os as _os
# Add project root to path for cleaner imports
_project_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


class CleaningService:
    """Service layer for data cleaning and preparation operations."""

    # ── Session cache: store pipeline state per (user_id, dataset_id) ──
    _pipelines: Dict[str, CleaningPipeline] = {}
    _raw_dataframes: Dict[str, pd.DataFrame] = {}

    @classmethod
    def _cache_key(cls, user_id: int, dataset_id: int) -> str:
        return f"{user_id}:{dataset_id}"

    # ── Load / Cache Management ──────────────────────────────────

    @classmethod
    def load_pipeline(cls, user_id: int, dataset_id: int) -> Tuple[Optional[CleaningPipeline], Optional[pd.DataFrame], Optional[str]]:
        """
        Load or create a cleaning pipeline for a dataset.
        Returns (pipeline, raw_df, error).
        """
        dataset = DatasetService.get_dataset(dataset_id, user_id)
        if not dataset:
            return None, None, "Dataset not found or access denied."

        if not dataset.storage_path or not os.path.exists(dataset.storage_path):
            return None, None, "Source file not found."

        key = cls._cache_key(user_id, dataset_id)
        if key in cls._pipelines:
            return cls._pipelines[key], cls._raw_dataframes[key], None

        df, error = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format)
        if df is None or df.empty:
            return None, None, error or "Failed to load dataset."

        pipeline = CleaningPipeline(df)
        cls._pipelines[key] = pipeline
        cls._raw_dataframes[key] = df.copy()
        return pipeline, df, None

    @classmethod
    def get_pipeline(cls, user_id: int, dataset_id: int) -> Optional[CleaningPipeline]:
        key = cls._cache_key(user_id, dataset_id)
        return cls._pipelines.get(key)

    @classmethod
    def clear_pipeline(cls, user_id: int, dataset_id: int):
        key = cls._cache_key(user_id, dataset_id)
        cls._pipelines.pop(key, None)
        cls._raw_dataframes.pop(key, None)

    @classmethod
    def clear_all_pipelines(cls):
        cls._pipelines.clear()
        cls._raw_dataframes.clear()

    # ── Detection ─────────────────────────────────────────────────

    @classmethod
    def detect_problems(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Detect all data quality problems in the current working state."""
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        df = pipeline.current_df
        result = {
            "rows": len(df),
            "columns": len(df.columns),
            "column_names": list(df.columns),
        }

        # Missing values
        imputer_svc = ImputerService()
        missing = imputer_svc.inspect_missing(df)
        result["missing"] = missing

        # Duplicates
        dup_svc = DuplicateRemoverService()
        dup_info = dup_svc.inspect_duplicates(df)
        result["duplicates"] = dup_info

        # Outliers (IQR)
        outlier_svc = OutlierDetectorService()
        outlier_summary = outlier_svc.detect_outliers_summary(df)
        result["outliers"] = outlier_summary

        # Constant columns
        constant_cols = [col for col in df.columns if df[col].nunique() <= 1]
        result["constant_columns"] = constant_cols

        # Column types
        col_types = []
        for col in df.columns:
            inferred = cls._detect_inferred_type(df[col])
            col_types.append({
                "name": col,
                "current_type": str(df[col].dtype),
                "inferred_type": inferred,
                "unique_count": int(df[col].nunique()),
                "null_count": int(df[col].isnull().sum()),
            })
        result["column_types"] = col_types

        return result, None

    @staticmethod
    def _detect_inferred_type(series: pd.Series) -> str:
        """Detect inferred type for a column."""
        if pd.api.types.is_numeric_dtype(series):
            return "numeric"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        if series.dtype == "object" or pd.api.types.is_string_dtype(series):
            # Try to detect datetime strings
            if series.dropna().head(100).apply(lambda x: True if pd.to_datetime(x, errors='coerce') is not pd.NaT else False).mean() > 0.8:
                return "datetime"
            return "categorical"
        if pd.api.types.is_bool_dtype(series):
            return "boolean"
        return "unknown"

    # ── Operations ────────────────────────────────────────────────

    @classmethod
    def preview_operation(cls, user_id: int, dataset_id: int, operation: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Preview a single cleaning operation on a temporary copy.
        Returns preview metrics and sample before/after data.
        """
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        df_before = pipeline.current_df.copy()
        op_type = operation.get("type", "")

        try:
            df_after, audit_entry = cls._apply_operation(df_before, operation)
        except Exception as e:
            return None, f"Operation failed: {str(e)[:200]}"

        # Compute before/after metrics
        metrics = {
            "rows_before": len(df_before),
            "rows_after": len(df_after),
            "columns_before": len(df_before.columns),
            "columns_after": len(df_after.columns),
            "missing_before": int(df_before.isnull().sum().sum()),
            "missing_after": int(df_after.isnull().sum().sum()),
            "duplicates_before": int(df_before.duplicated().sum()),
            "duplicates_after": int(df_after.duplicated().sum()),
            "operation": op_type,
            "details": audit_entry.details if audit_entry else "",
        }

        # Sample before/after for changed rows
        sample = cls._generate_preview_sample(df_before, df_after, operation, max_rows=5)
        metrics["sample"] = sample

        return metrics, None

    @classmethod
    def apply_operation(cls, user_id: int, dataset_id: int, operation: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Apply a cleaning operation to the pipeline (mutates current state).
        Returns result metrics.
        """
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        op_type = operation.get("type", "")

        try:
            df_result, audit_entry = cls._apply_operation(pipeline.current_df, operation)
        except Exception as e:
            return None, f"Operation failed: {str(e)[:200]}"

        # Replace pipeline current state with result
        rows_before, cols_before = pipeline.current_df.shape
        pipeline.current_df = df_result
        pipeline.audit_log.append(audit_entry)
        pipeline.history.append((df_result.copy(), audit_entry, f"# {op_type}"))

        # Add to code snippets for reproducibility
        pipeline.code_snippets.append(cls._operation_to_code(operation))

        metrics = {
            "rows_before": rows_before,
            "rows_after": len(df_result),
            "columns_before": cols_before,
            "columns_after": len(df_result.columns),
            "missing_before": int(pipeline.raw_df.isnull().sum().sum()),
            "missing_after": int(df_result.isnull().sum().sum()),
            "operation": op_type,
            "details": audit_entry.details if audit_entry else "",
            "history_length": len(pipeline.audit_log),
        }

        return metrics, None

    @classmethod
    def _apply_operation(cls, df: pd.DataFrame, operation: Dict) -> Tuple[pd.DataFrame, object]:
        """Apply a single operation and return (result_df, audit_entry)."""
        from cleaner.domain.cleaning_result import AuditEntry
        from datetime import datetime

        op_type = operation.get("type", "")
        rows_before, cols_before = df.shape

        if op_type == "remove_duplicates":
            config = DuplicateConfig(
                subset=operation.get("subset"),
                keep=operation.get("keep", "first"),
            )
            svc = DuplicateRemoverService()
            result_df, audit = svc.process(df, config)

        elif op_type == "impute":
            column_strategies = operation.get("column_strategies", {})
            if isinstance(column_strategies, dict):
                # Convert string values to actual dict
                col_strats = {}
                for k, v in column_strategies.items():
                    col_strats[k] = v
            else:
                col_strats = {}

            config = ImputationConfig(
                column_strategies=col_strats,
                default_numeric_strategy=operation.get("default_numeric_strategy", "median"),
                default_categorical_strategy=operation.get("default_categorical_strategy", "mode"),
                constant_value=operation.get("constant_value", "Missing"),
                numeric_constant=operation.get("numeric_constant", 0.0),
            )
            svc = ImputerService()
            result_df, audit = svc.process(df, config)

        elif op_type == "handle_outliers":
            config = OutlierConfig(
                method=operation.get("method", "iqr"),
                action=operation.get("action", "cap"),
                columns=operation.get("columns"),
                iqr_multiplier=operation.get("iqr_multiplier", 1.5),
            )
            svc = OutlierDetectorService()
            result_df, audit = svc.process(df, config)

        elif op_type == "encode":
            config = EncodingConfig(
                strategy=operation.get("strategy", "onehot"),
                columns=operation.get("columns"),
                drop_first=operation.get("drop_first", True),
            )
            svc = EncoderService()
            result_df, audit = svc.process(df, config)

        elif op_type == "scale":
            config = ScalingConfig(
                strategy=operation.get("strategy", "standard"),
                columns=operation.get("columns"),
            )
            svc = ScalerService()
            result_df, audit = svc.process(df, config)

        elif op_type == "rename_column":
            column = operation.get("column", "")
            new_name = operation.get("new_name", "")
            if not column or not new_name:
                raise ValueError("Column and new_name are required for rename.")
            if column not in df.columns:
                raise ValueError(f"Column '{column}' not found.")
            if new_name in df.columns:
                raise ValueError(f"Column '{new_name}' already exists.")
            result_df = df.rename(columns={column: new_name})
            audit = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Rename Column",
                details=f"Renamed '{column}' to '{new_name}'.",
                rows_before=rows_before, rows_after=len(result_df),
                cols_before=cols_before, cols_after=len(result_df.columns),
                affected_columns=[column, new_name],
            )

        elif op_type == "remove_columns":
            columns = operation.get("columns", [])
            missing = [c for c in columns if c not in df.columns]
            if missing:
                raise ValueError(f"Columns not found: {missing}")
            result_df = df.drop(columns=columns)
            audit = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Remove Columns",
                details=f"Removed {len(columns)} column(s): {columns}.",
                rows_before=rows_before, rows_after=len(result_df),
                cols_before=cols_before, cols_after=len(result_df.columns),
                affected_columns=columns,
            )

        elif op_type == "keep_columns":
            columns = operation.get("columns", [])
            if not columns:
                raise ValueError("No columns specified for keep operation.")
            missing = [c for c in columns if c not in df.columns]
            if missing:
                raise ValueError(f"Columns not found: {missing}")
            result_df = df[columns]
            removed = [c for c in df.columns if c not in columns]
            audit = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Keep Selected Columns",
                details=f"Kept {len(columns)} column(s). Removed {len(removed)}.",
                rows_before=rows_before, rows_after=len(result_df),
                cols_before=cols_before, cols_after=len(result_df.columns),
                affected_columns=removed,
            )

        elif op_type == "convert_dtype":
            column = operation.get("column", "")
            target_type = operation.get("target_type", "")
            if not column or not target_type:
                raise ValueError("Column and target_type are required.")
            if column not in df.columns:
                raise ValueError(f"Column '{column}' not found.")

            result_df = df.copy()
            fail_count = 0

            if target_type == "int":
                converted = pd.to_numeric(result_df[column], errors="coerce")
                fail_count = int(converted.isnull().sum() - result_df[column].isnull().sum())
                result_df[column] = converted
            elif target_type == "float":
                converted = pd.to_numeric(result_df[column], errors="coerce")
                fail_count = int(converted.isnull().sum() - result_df[column].isnull().sum())
                result_df[column] = converted
            elif target_type == "datetime":
                converted = pd.to_datetime(result_df[column], errors="coerce")
                fail_count = int(converted.isnull().sum() - result_df[column].isnull().sum())
                result_df[column] = converted
            elif target_type == "str":
                result_df[column] = result_df[column].astype(str).replace("nan", "").replace("NaT", "")
            elif target_type == "category":
                result_df[column] = result_df[column].astype("category")
            else:
                raise ValueError(f"Unsupported target type: {target_type}")

            audit = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Convert Data Type",
                details=f"Converted '{column}' to {target_type}. Failures: {fail_count}.",
                rows_before=rows_before, rows_after=len(result_df),
                cols_before=cols_before, cols_after=len(result_df.columns),
                affected_columns=[column],
            )

        elif op_type == "remove_constant_columns":
            constant_cols = [col for col in df.columns if df[col].nunique() <= 1]
            if not constant_cols:
                result_df = df.copy()
            else:
                result_df = df.drop(columns=constant_cols)
            audit = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation="Remove Constant Columns",
                details=f"Removed {len(constant_cols)} constant column(s): {constant_cols}.",
                rows_before=rows_before, rows_after=len(result_df),
                cols_before=cols_before, cols_after=len(result_df.columns),
                affected_columns=constant_cols,
            )

        elif op_type == "transform":
            column = operation.get("column", "")
            method = operation.get("method", "")
            if not column or column not in df.columns:
                raise ValueError(f"Column '{column}' not found.")
            result_df = df.copy()
            if method == "log":
                series = pd.to_numeric(result_df[column], errors="coerce")
                result_df[column] = np.log1p(series.abs()) * np.sign(series)
            elif method == "sqrt":
                series = pd.to_numeric(result_df[column], errors="coerce")
                result_df[column] = np.sqrt(series.abs()) * np.sign(series)
            elif method == "reciprocal":
                series = pd.to_numeric(result_df[column], errors="coerce")
                series = series.replace(0, np.nan)
                result_df[column] = 1.0 / series
            else:
                raise ValueError(f"Unsupported transform method: {method}")
            audit = AuditEntry(
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                operation=f"Transform ({method})",
                details=f"Applied {method} transform to '{column}'.",
                rows_before=rows_before, rows_after=len(result_df),
                cols_before=cols_before, cols_after=len(result_df.columns),
                affected_columns=[column],
            )

        else:
            raise ValueError(f"Unknown operation type: {op_type}")

        return result_df, audit

    @classmethod
    def _generate_preview_sample(cls, df_before: pd.DataFrame, df_after: pd.DataFrame, operation: Dict, max_rows: int = 5) -> List[Dict]:
        """Generate before/after sample for preview."""
        op_type = operation.get("type", "")
        samples = []

        if op_type == "impute":
            columns = operation.get("column_strategies", {}).keys() if isinstance(operation.get("column_strategies"), dict) else []
            if not columns:
                # Apply to all columns with missing values
                columns = [c for c in df_before.columns if df_before[c].isnull().sum() > 0]
            for col in list(columns)[:3]:
                null_indices = df_before[df_before[col].isnull()].index[:max_rows]
                for idx in null_indices:
                    before_val = None if pd.isnull(df_before.at[idx, col]) else str(df_before.at[idx, col])[:50]
                    after_val = None if pd.isnull(df_after.at[idx, col]) else str(df_after.at[idx, col])[:50]
                    samples.append({
                        "index": int(idx),
                        "column": col,
                        "before": before_val,
                        "after": after_val,
                    })

        elif op_type == "remove_duplicates":
            removed = df_before.index.difference(df_after.index)
            for idx in list(removed)[:max_rows]:
                row = df_before.loc[idx]
                samples.append({
                    "index": int(idx),
                    "column": "—",
                    "before": "Duplicate row",
                    "after": "Removed",
                })

        elif op_type == "handle_outliers":
            columns = operation.get("columns", [])
            if not columns:
                columns = list(df_before.select_dtypes(include=[np.number]).columns)
            for col in list(columns)[:2]:
                # Find rows where values changed
                if col in df_after.columns:
                    numeric_before = pd.to_numeric(df_before[col], errors="coerce")
                    numeric_after = pd.to_numeric(df_after[col], errors="coerce")
                    changed = (numeric_before != numeric_after) & numeric_before.notna()
                    for idx in list(df_before.index[changed])[:max_rows]:
                        samples.append({
                            "index": int(idx),
                            "column": col,
                            "before": str(df_before.at[idx, col])[:50],
                            "after": str(df_after.at[idx, col])[:50],
                        })

        elif op_type == "rename_column":
            old_name = operation.get("column", "")
            new_name = operation.get("new_name", "")
            samples.append({"index": 0, "column": old_name, "before": old_name, "after": new_name})

        elif op_type == "convert_dtype":
            col = operation.get("column", "")
            if col in df_after.columns:
                for idx in list(df_before.index[:max_rows]):
                    before_val = str(df_before.at[idx, col])[:50]
                    after_val = str(df_after.at[idx, col])[:50]
                    samples.append({"index": int(idx), "column": col, "before": before_val, "after": after_val})

        elif op_type == "scale":
            columns = operation.get("columns", [])
            if not columns:
                columns = list(df_before.select_dtypes(include=[np.number]).columns)
            for col in list(columns)[:2]:
                for idx in list(df_before.index[:3]):
                    samples.append({
                        "index": int(idx),
                        "column": col,
                        "before": str(round(df_before.at[idx, col], 4))[:50],
                        "after": str(round(df_after.at[idx, col], 4))[:50],
                    })

        elif op_type == "encode":
            samples.append({"index": 0, "column": "—", "before": f"Columns: {list(df_before.columns)}", "after": f"Columns: {list(df_after.columns)}"})

        elif op_type == "transform":
            col = operation.get("column", "")
            if col in df_after.columns:
                for idx in list(df_before.index[:max_rows]):
                    samples.append({
                        "index": int(idx),
                        "column": col,
                        "before": str(df_before.at[idx, col])[:50],
                        "after": str(df_after.at[idx, col])[:50],
                    })

        return samples

    @staticmethod
    def _operation_to_code(operation: Dict) -> str:
        """Generate a Python code snippet for a cleaning operation."""
        op_type = operation.get("type", "")
        if op_type == "remove_duplicates":
            return f"# Remove duplicates\ndf = df.drop_duplicates(keep='{operation.get('keep', 'first')}')"
        elif op_type == "impute":
            col_strats = operation.get("column_strategies", {})
            lines = ["# Impute missing values"]
            for col, strat in col_strats.items() if isinstance(col_strats, dict) else []:
                lines.append(f"df['{col}'] = df['{col}'].fillna(df['{col}'].{strat}())")
            return "\n".join(lines) if len(lines) > 1 else "# Impute missing values (see full pipeline)"
        elif op_type == "handle_outliers":
            return f"# Handle outliers ({operation.get('method')}, {operation.get('action')})"
        elif op_type == "encode":
            return f"# Encode categorical columns ({operation.get('strategy')})"
        elif op_type == "scale":
            return f"# Scale features ({operation.get('strategy')})"
        elif op_type == "rename_column":
            return f"df = df.rename(columns={{'{operation.get('column')}': '{operation.get('new_name')}'}})"
        elif op_type == "remove_columns":
            cols = operation.get("columns", [])
            return f"df = df.drop(columns={cols})"
        elif op_type == "keep_columns":
            cols = operation.get("columns", [])
            return f"df = df[{cols}]"
        elif op_type == "convert_dtype":
            return f"df['{operation.get('column')}'] = pd.to_{operation.get('target_type', '')}(df['{operation.get('column')}'])"
        elif op_type == "transform":
            return f"# Transform: {operation.get('method')} on '{operation.get('column')}'"
        elif op_type == "remove_constant_columns":
            return "# Remove constant columns"
        return f"# {op_type}"

    # ── Undo / Reset ─────────────────────────────────────────────

    @classmethod
    def undo_last(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Undo the last cleaning operation."""
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        if not pipeline.history:
            return None, "No operations to undo."

        pipeline.undo_last_step()

        return {
            "rows": len(pipeline.current_df),
            "columns": len(pipeline.current_df.columns),
            "history_length": len(pipeline.audit_log),
            "message": "Last operation undone.",
        }, None

    @classmethod
    def reset(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Reset all changes back to original dataset."""
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        pipeline.reset_to_raw()

        return {
            "rows": len(pipeline.current_df),
            "columns": len(pipeline.current_df.columns),
            "history_length": 0,
            "message": "Reset to original dataset.",
        }, None

    # ── History ───────────────────────────────────────────────────

    @classmethod
    def get_history(cls, user_id: int, dataset_id: int) -> Tuple[Optional[List], Optional[str]]:
        """Get cleaning operation history."""
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        history = []
        for i, audit in enumerate(pipeline.audit_log):
            history.append({
                "step": i + 1,
                "timestamp": audit.timestamp,
                "operation": audit.operation,
                "details": audit.details,
                "rows_before": audit.rows_before,
                "rows_after": audit.rows_after,
                "cols_before": audit.cols_before,
                "cols_after": audit.cols_after,
                "affected_columns": audit.affected_columns,
            })

        return history, None

    # ── Preview Data ─────────────────────────────────────────────

    @classmethod
    def get_preview_data(cls, user_id: int, dataset_id: int, max_rows: int = 50) -> Tuple[Optional[Dict], Optional[str]]:
        """Get current working state preview data."""
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        df = pipeline.current_df
        raw_df = pipeline.raw_df

        preview_df = df.head(max_rows)
        columns = list(df.columns)
        rows = []
        for idx, row in preview_df.iterrows():
            row_dict = {}
            for col in columns:
                val = row[col]
                if pd.isnull(val):
                    row_dict[col] = None
                elif hasattr(val, 'isoformat'):
                    row_dict[col] = val.isoformat()
                else:
                    try:
                        row_dict[col] = str(val)[:100]
                    except Exception:
                        row_dict[col] = ""
            rows.append(row_dict)

        return {
            "rows": rows,
            "columns": columns,
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "original_rows": len(raw_df),
            "original_columns": len(raw_df.columns),
            "missing_total": int(df.isnull().sum().sum()),
            "duplicates_total": int(df.duplicated().sum()),
            "history_length": len(pipeline.audit_log),
        }, None

    # ── Pipeline Serialization ────────────────────────────────────

    @classmethod
    def get_pipeline_operations(cls, user_id: int, dataset_id: int) -> List[Dict]:
        """Get list of applied operations as serializable dicts."""
        pipeline = cls.get_pipeline(user_id, dataset_id)
        if not pipeline:
            return []

        operations = []
        for audit in pipeline.audit_log:
            operations.append({
                "timestamp": audit.timestamp,
                "operation": audit.operation,
                "details": audit.details,
                "rows_before": audit.rows_before,
                "rows_after": audit.rows_after,
                "cols_before": audit.cols_before,
                "cols_after": audit.cols_after,
                "affected_columns": audit.affected_columns,
            })
        return operations

    # ── Save Cleaned Dataset ───────────────────────────────────────

    @classmethod
    def save_cleaned_dataset(cls, user_id: int, dataset_id: int, name: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Save the current cleaned state as a new dataset.
        Original dataset is never modified.
        """
        pipeline, raw_df, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        if not pipeline.audit_log:
            return None, "No cleaning operations to save."

        # Get original dataset info
        original_dataset = DatasetService.get_dataset(dataset_id, user_id)
        if not original_dataset:
            return None, "Original dataset not found."

        cleaned_df = pipeline.current_df

        # Validate result
        validation_error = cls._validate_cleaned_data(cleaned_df, raw_df)
        if validation_error:
            return None, f"Validation failed: {validation_error}"

        # Generate name
        if not name:
            base_name = original_dataset.name
            version_count = cls._count_child_datasets(dataset_id)
            name = f"{base_name}_cleaned_v{version_count + 1}"

        # Save file
        dataset_uuid = str(uuid.uuid4())[:8]
        upload_dir = original_dataset.storage_path.rsplit("user_", 1)[0] if "user_" in original_dataset.storage_path else os.path.join(os.path.dirname(original_dataset.storage_path), "..")
        user_dir = os.path.join(upload_dir, f"user_{user_id}", dataset_uuid)
        os.makedirs(user_dir, exist_ok=True)

        cleaned_filename = f"{name}.csv"
        storage_path = os.path.join(user_dir, cleaned_filename)
        cleaned_df.to_csv(storage_path, index=False)

        # Profile new dataset
        profile = DatasetService.profile_dataframe(cleaned_df)

        # Serialize pipeline operations for reproducibility
        pipeline_json = json.dumps(cls.get_pipeline_operations(user_id, dataset_id))

        # Persist to database
        db = get_session()
        try:
            column_info_json = json.dumps(profile.get("columns", [])) if profile.get("columns") else None
            quality_info_json = json.dumps(profile.get("quality_info", {})) if profile.get("quality_info") else None

            new_dataset = DatasetDB(
                user_id=user_id,
                name=name,
                original_filename=cleaned_filename,
                file_format="csv",
                file_size=os.path.getsize(storage_path),
                storage_path=storage_path,
                row_count=profile.get("row_count"),
                column_count=profile.get("column_count"),
                column_info=column_info_json,
                quality_info=quality_info_json,
                parent_dataset_id=dataset_id,
                cleaning_pipeline=pipeline_json,
            )
            db.add(new_dataset)
            db.commit()
            db.refresh(new_dataset)
            # Invalidate dataset caches for this user
            try:
                from app.core.cache import dataset_list_cache, dataset_meta_cache
                dataset_list_cache.invalidate_prefix(f"u:{user_id}:")
                dataset_meta_cache.invalidate_prefix(f"u:{user_id}:")
            except Exception:
                pass

            return {
                "id": new_dataset.id,
                "name": new_dataset.name,
                "rows": profile.get("row_count"),
                "columns": profile.get("column_count"),
                "operations_count": len(pipeline.audit_log),
                "parent_dataset_id": dataset_id,
                "message": f"Cleaned dataset '{name}' saved successfully.",
            }, None

        except Exception as e:
            db.rollback()
            # Clean up file on failure
            if os.path.exists(storage_path):
                os.remove(storage_path)
                parent = os.path.dirname(storage_path)
                if os.path.exists(parent):
                    shutil.rmtree(parent, ignore_errors=True)
            return None, f"Failed to save cleaned dataset: {str(e)[:200]}"
        finally:
            db.close()

    @staticmethod
    def _validate_cleaned_data(cleaned_df: pd.DataFrame, raw_df: pd.DataFrame) -> Optional[str]:
        """Validate cleaned data before saving."""
        if cleaned_df.empty:
            return "Cleaned dataset is empty. All rows were removed."

        if len(cleaned_df.columns) == 0:
            return "Cleaned dataset has no columns."

        # Check for unexpected explosion of nulls
        raw_null_pct = raw_df.isnull().sum().sum() / max(raw_df.size, 1)
        cleaned_null_pct = cleaned_df.isnull().sum().sum() / max(cleaned_df.size, 1)
        if cleaned_null_pct > raw_null_pct + 0.3:
            return f"Operation created excessive missing values ({cleaned_null_pct:.1%} vs {raw_null_pct:.1%} original)."

        return None

    @staticmethod
    def _count_child_datasets(parent_id: int) -> int:
        """Count existing child datasets for versioning."""
        db = get_session()
        try:
            return db.query(DatasetDB).filter(DatasetDB.parent_dataset_id == parent_id).count()
        finally:
            db.close()

    # ── Dataset Versions ──────────────────────────────────────────

    @classmethod
    def get_dataset_versions(cls, user_id: int, dataset_id: int) -> Tuple[Optional[List], Optional[str]]:
        """Get parent and all child versions of a dataset."""
        db = get_session()
        try:
            # Find root dataset
            root = db.query(DatasetDB).filter(
                DatasetDB.id == dataset_id,
                DatasetDB.user_id == user_id,
            ).first()

            if not root:
                return None, "Dataset not found."

            # If this is a child, find parent
            versions = []
            if root.parent_dataset_id:
                parent = db.query(DatasetDB).filter(DatasetDB.id == root.parent_dataset_id).first()
                if parent:
                    versions.append({
                        "id": parent.id,
                        "name": parent.name,
                        "original_filename": parent.original_filename,
                        "row_count": parent.row_count,
                        "column_count": parent.column_count,
                        "created_at": parent.created_at.isoformat() if parent.created_at else None,
                        "is_parent": True,
                    })

            # Add the dataset itself
            versions.append({
                "id": root.id,
                "name": root.name,
                "original_filename": root.original_filename,
                "row_count": root.row_count,
                "column_count": root.column_count,
                "created_at": root.created_at.isoformat() if root.created_at else None,
                "is_current": True,
            })

            # Find children
            children = db.query(DatasetDB).filter(
                DatasetDB.parent_dataset_id == dataset_id,
                DatasetDB.user_id == user_id,
            ).order_by(DatasetDB.created_at.asc()).all()

            for child in children:
                versions.append({
                    "id": child.id,
                    "name": child.name,
                    "original_filename": child.original_filename,
                    "row_count": child.row_count,
                    "column_count": child.column_count,
                    "created_at": child.created_at.isoformat() if child.created_at else None,
                    "is_child": True,
                    "operations_count": len(json.loads(child.cleaning_pipeline)) if child.cleaning_pipeline else 0,
                })

            return versions, None

        finally:
            db.close()

    # ── Column Metadata ───────────────────────────────────────────

    @classmethod
    def get_column_info(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get detailed column info for the current working state."""
        pipeline, _, error = cls.load_pipeline(user_id, dataset_id)
        if error or not pipeline:
            return None, error

        df = pipeline.current_df
        columns = []
        for col in df.columns:
            col_data = df[col]
            info = {
                "name": col,
                "dtype": str(col_data.dtype),
                "inferred_type": cls._detect_inferred_type(col_data),
                "null_count": int(col_data.isnull().sum()),
                "null_pct": round(col_data.isnull().sum() / len(df) * 100, 2) if len(df) > 0 else 0,
                "unique_count": int(col_data.nunique()),
                "is_constant": col_data.nunique() <= 1,
            }
            if pd.api.types.is_numeric_dtype(col_data):
                info["min"] = float(col_data.min()) if not col_data.isnull().all() else None
                info["max"] = float(col_data.max()) if not col_data.isnull().all() else None
                info["mean"] = round(float(col_data.mean()), 4) if not col_data.isnull().all() else None
            if col_data.nunique() <= 20:
                info["unique_values"] = [str(v)[:50] for v in col_data.dropna().unique()]
            columns.append(info)

        return {
            "columns": columns,
            "total_rows": len(df),
            "total_columns": len(df.columns),
        }, None
