"""
DataViz Pro — Dataset Service

Handles all dataset operations: upload, validation,
profiling, deletion, and retrieval. Integrates with
existing connectors/ and core/data_quality.py modules.
"""

import os
import json
import uuid
import shutil
import logging
from typing import Optional, List, Dict, Any, Tuple

import pandas as pd
import requests

from werkzeug.utils import secure_filename

from auth.database import DatasetDB, get_session
from app.domain.dataset import DatasetDomain, ColumnProfile
from connectors.domain.enums import DataSourceType
from connectors.domain.entities import ConnectionConfig, QueryConfig
logger = logging.getLogger(__name__)


# ── Magic byte signatures for binary file validation ───────
MAGIC_SIGNATURES = {
    "xlsx": b"PK\x03\x04",          # ZIP archive (xlsx is a ZIP)
    "xls": b"\xD0\xCF\x11\xE0",    # OLE2 compound document
    "parquet": b"PAR1",               # Parquet magic bytes
}


def _validate_file_magic_bytes(file_storage, declared_format: str) -> Tuple[bool, str]:
    """Validate file content using magic bytes for binary formats.

    Returns (is_valid, error_message).
    """
    try:
        pos = file_storage.tell()
        header = file_storage.read(8)
        file_storage.seek(pos)

        if not header:
            return False, "Could not read file content."

        expected_sig = MAGIC_SIGNATURES.get(declared_format)
        if expected_sig and not header.startswith(expected_sig):
            return False, f"File magic bytes do not match expected '{declared_format}' format."

        return True, ""
    except Exception:
        return True, ""  # Don't block on read errors


# ── Supported file formats ──────────────────────────────────────
ALLOWED_EXTENSIONS = {"csv", "xlsx", "xls", "json", "parquet"}
ALLOWED_MIME_TYPES = {
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel"},
    "xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    "xls": {"application/vnd.ms-excel"},
    "json": {"application/json", "text/plain"},
    "parquet": {"application/octet-stream", "application/x-parquet"},
}
FORMAT_LABELS = {
    "csv": "CSV",
    "xlsx": "Excel (.xlsx)",
    "xls": "Excel (.xls)",
    "json": "JSON",
    "parquet": "Parquet",
}


class DatasetService:
    """Service layer for dataset management operations."""

    # ── Validation ──────────────────────────────────────────────

    @staticmethod
    def validate_file(filename: str, file_size: int, max_size: int,
                      file_storage=None) -> Tuple[bool, str]:
        """
        Validate uploaded file before processing.

        Phase 14 hardening:
        - Extension allowlist
        - File size limit
        - Empty file check
        - MIME type validation (optional file_storage for content check)
        - Magic-byte validation for binary formats

        Returns:
            (is_valid, error_message)
        """
        if not filename:
            return False, "No file provided."

        # Check extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EXTENSIONS:
            return False, (
                f"Unsupported file format '.{ext}'. "
                f"Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
            )

        # Check file size
        if file_size > max_size:
            max_mb = max_size / (1024 * 1024)
            return False, f"File too large ({file_size / (1024*1024):.1f} MB). Maximum size is {max_mb:.0f} MB."

        # Check empty file
        if file_size == 0:
            return False, "The uploaded file is empty."

        # ── MIME type validation (Phase 14) ──────────────────
        if file_storage is not None and ext in ALLOWED_MIME_TYPES:
            declared_mime = file_storage.content_type or ""
            allowed = ALLOWED_MIME_TYPES[ext]
            # text/plain is too generic — skip strict MIME check for csv/json
            # (many browsers send text/plain for these)
            if declared_mime and declared_mime not in ("text/plain", "application/octet-stream"):
                if allowed and declared_mime not in allowed:
                    # Don't hard-block on MIME mismatch (browsers often misreport),
                    # but log a warning
                    logger.warning(
                        "[security] MIME mismatch for '%s': declared='%s', expected=%s",
                        filename, declared_mime, allowed,
                    )

        # ── Magic-byte validation for binary formats (Phase 14) ──
        if file_storage is not None and ext in ("xlsx", "xls", "parquet"):
            is_valid_content, _ = _validate_file_magic_bytes(file_storage, ext)
            if not is_valid_content:
                return False, (
                    f"File content does not match the '.{ext}' format. "
                    "The file may be corrupted or renamed."
                )

        return True, ""

    @staticmethod
    def detect_format(filename: str) -> Optional[str]:
        """Detect file format from extension."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ext if ext in ALLOWED_EXTENSIONS else None

    # ── Storage ──────────────────────────────────────────────────

    @staticmethod
    def save_file(file_storage, user_id: int, base_upload_dir: str) -> Tuple[str, str]:
        """
        Save uploaded file to secure storage.

        Returns:
            (storage_path, dataset_uuid)
        """
        dataset_uuid = str(uuid.uuid4())[:8]
        user_dir = os.path.join(base_upload_dir, f"user_{user_id}", dataset_uuid)
        os.makedirs(user_dir, exist_ok=True)

        original_filename = secure_filename(file_storage.filename or "unknown_file")
        storage_path = os.path.join(user_dir, original_filename)

        file_storage.save(storage_path)
        return storage_path, dataset_uuid

    @staticmethod
    def save_dataframe(df: pd.DataFrame, user_id: int, base_upload_dir: str, file_format: str = "parquet") -> Tuple[str, str]:
        """
        Save a pandas DataFrame securely to storage as a snapshot file.
        Returns:
            (storage_path, dataset_uuid)
        """
        dataset_uuid = str(uuid.uuid4())[:8]
        user_dir = os.path.join(base_upload_dir, f"user_{user_id}", dataset_uuid)
        os.makedirs(user_dir, exist_ok=True)
        
        filename = f"dataset_snapshot.{file_format}"
        storage_path = os.path.join(user_dir, filename)
        
        if file_format == "parquet":
            df.to_parquet(storage_path, index=False)
        elif file_format == "csv":
            df.to_csv(storage_path, index=False)
        else:
            raise ValueError(f"Unsupported format for save_dataframe: {file_format}")
            
        return storage_path, dataset_uuid

    @staticmethod
    def delete_storage(storage_path: str) -> bool:
        """Remove stored file and its parent directory."""
        try:
            parent_dir = os.path.dirname(storage_path)
            if os.path.exists(parent_dir):
                shutil.rmtree(parent_dir)
            return True
        except Exception:
            return False

    # ── Data Loading ─────────────────────────────────────────────

    @staticmethod
    def load_dataframe(file_path: str, file_format: str, _cache_key: str = None) -> Tuple[Optional[pd.DataFrame], str]:
        """
        Load a file into a pandas DataFrame using existing connectors.

        When _cache_key is provided, checks the in-memory DataFrame cache
        before loading from disk. Eliminates redundant file I/O for repeated
        chart/analysis operations on the same dataset.

        Returns:
            (df, error_message) — df is None on failure.
        """
        # ── Check DataFrame cache ──────────────────────────
        if _cache_key:
            from app.core.cache import dataframe_cache
            cached_df = dataframe_cache.get(_cache_key)
            if cached_df is not None:
                return cached_df, ""

        try:
            source_type_map = {
                "csv": DataSourceType.CSV,
                "xlsx": DataSourceType.EXCEL,
                "xls": DataSourceType.EXCEL,
                "json": DataSourceType.JSON,
            }

            if file_format == "parquet":
                # Parquet is not in existing connectors — use pandas directly
                try:
                    df = pd.read_parquet(file_path)
                    return df, ""
                except Exception as exc:
                    return None, f"Invalid Parquet file: {str(exc)[:200]}"

            source_type = source_type_map.get(file_format)
            if not source_type:
                return None, f"Unsupported format: {file_format}"

            config = ConnectionConfig(source_type=source_type, file_path=file_path)

            if file_format == "csv":
                from connectors.file_connectors.csv_connector import CSVConnector
                connector = CSVConnector(config)
            elif file_format in ("xlsx", "xls"):
                from connectors.file_connectors.excel_connector import ExcelConnector
                connector = ExcelConnector(config)
            elif file_format == "json":
                from connectors.file_connectors.json_connector import JSONConnector
                connector = JSONConnector(config)
            else:
                return None, f"No connector for format: {file_format}"

            result = connector.test_connection()
            if result.success:
                return result.df, ""
            else:
                return None, result.message or f"Failed to load {file_format} file."

        except FileNotFoundError:
            return None, "File not found. It may have been moved or deleted."
        except pd.errors.EmptyDataError:
            return None, "The file contains no data."
        except pd.errors.ParserError:
            return None, "The file could not be parsed. It may be corrupted or have an invalid format."
        except UnicodeDecodeError:
            return None, "Encoding error: could not read the file with the detected encoding."
        except MemoryError:
            return None, "The file is too large to fit in available memory."
        except Exception as exc:
            return None, f"Error reading file: {str(exc)[:200]}"

        # ── Store in DataFrame cache ────────────────────────
        if _cache_key and df is not None:
            try:
                from app.core.cache import dataframe_cache
                dataframe_cache.set(_cache_key, df)
            except Exception:
                pass  # Non-critical — cache miss is acceptable
        return df, ""

    @staticmethod
    def ingest_from_database(
        user_id: int,
        config: ConnectionConfig,
        query: QueryConfig,
        dataset_name: str,
        base_upload_dir: str
    ) -> Tuple[Optional[DatasetDomain], str]:
        """
        Connect to a database, execute a query, snapshot the data as parquet,
        and create a dataset record.
        """
        try:
            # Instantiate appropriate connector
            if config.source_type == DataSourceType.MYSQL:
                from connectors.database_connectors.mysql_connector import MySQLConnector
                connector = MySQLConnector(config)
            elif config.source_type == DataSourceType.POSTGRESQL:
                from connectors.database_connectors.postgresql_connector import PostgreSQLConnector
                connector = PostgreSQLConnector(config)
            elif config.source_type == DataSourceType.SQLITE:
                from connectors.database_connectors.sqlite_connector import SQLiteConnector
                connector = SQLiteConnector(config)
            else:
                return None, f"Unsupported database type: {config.source_type}"

            # Test connection first
            test_res = connector.test_connection()
            if not test_res.success:
                return None, test_res.message or "Connection failed."

            # Load DataFrame
            try:
                df = connector.load_data(query_config=query)
            except Exception as load_exc:
                return None, f"Failed to execute query: {str(load_exc)}"

            if df is None or df.empty:
                return None, "The query returned no data."

            # Snapshot the data as Parquet
            file_format = "parquet"
            storage_path, _ = DatasetService.save_dataframe(df, user_id, base_upload_dir, file_format)
            
            # File size approximation
            file_size = os.path.getsize(storage_path) if os.path.exists(storage_path) else 0

            # Profile data
            profile = DatasetService.profile_dataframe(df)
            del df  # Free memory
            
            # Use table name or custom name if provided
            original_filename = query.table_name or "custom_query"
            if not dataset_name:
                dataset_name = original_filename

            dataset = DatasetService.create_dataset(
                user_id=user_id,
                name=dataset_name,
                original_filename=f"{original_filename}.{file_format}",
                file_format=file_format,
                file_size=file_size,
                storage_path=storage_path,
                profile=profile,
            )
            return dataset, ""

        except Exception as exc:
            return None, f"Database ingestion error: {str(exc)[:200]}"

    @staticmethod
    def ingest_from_api(
        user_id: int,
        config: ConnectionConfig,
        dataset_name: str,
        base_upload_dir: str
    ) -> Tuple[Optional[DatasetDomain], str]:
        """
        Connect to a REST API, fetch JSON data, snapshot as parquet, and create dataset.
        """
        try:
            from connectors.api_connectors.rest_api_connector import RESTAPIConnector
            connector = RESTAPIConnector(config)

            # Test connection first
            test_res = connector.test_connection()
            if not test_res.success:
                return None, test_res.message or "API Connection failed."

            # Load DataFrame
            try:
                df = connector.load_data()
            except requests.exceptions.RequestException as req_exc:
                return None, f"API Request failed: {str(req_exc)}"
            except json.JSONDecodeError:
                return None, "API returned invalid or malformed JSON."
            except Exception as load_exc:
                return None, f"Failed to process API data: {str(load_exc)}"

            if df is None or df.empty:
                return None, "The API returned no data."

            # Snapshot the data as Parquet
            file_format = "parquet"
            storage_path, _ = DatasetService.save_dataframe(df, user_id, base_upload_dir, file_format)
            
            # File size approximation
            file_size = os.path.getsize(storage_path) if os.path.exists(storage_path) else 0

            # Profile data
            profile = DatasetService.profile_dataframe(df)
            del df
            
            if not dataset_name:
                dataset_name = "API_Dataset"

            dataset = DatasetService.create_dataset(
                user_id=user_id,
                name=dataset_name,
                original_filename=f"{dataset_name}.{file_format}",
                file_format=file_format,
                file_size=file_size,
                storage_path=storage_path,
                profile=profile,
            )
            return dataset, ""

        except Exception as exc:
            return None, f"API ingestion error: {str(exc)[:200]}"

    # ── Profiling ────────────────────────────────────────────────

    @staticmethod
    def profile_dataframe(df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate basic dataset profile from a DataFrame.

        Returns dict with row_count, column_count, memory_bytes,
        duplicate_count, total_missing, columns (list of per-column dicts).
        """
        if df is None or df.empty:
            return {}

        total_cells = df.shape[0] * df.shape[1]
        total_missing = int(df.isnull().sum().sum())
        duplicate_count = int(df.duplicated().sum())

        columns = []
        for col in df.columns:
            col_data = df[col]
            col_info: Dict[str, Any] = {
                "name": col,
                "dtype": str(col_data.dtype),
                "missing_count": int(col_data.isnull().sum()),
                "missing_pct": round(col_data.isnull().sum() / len(df) * 100, 2) if len(df) > 0 else 0,
                "unique_count": int(col_data.nunique()),
            }

            # Numeric stats
            if pd.api.types.is_numeric_dtype(col_data):
                col_info["min_val"] = float(col_data.min()) if not col_data.isnull().all() else None
                col_info["max_val"] = float(col_data.max()) if not col_data.isnull().all() else None
                col_info["mean_val"] = round(float(col_data.mean()), 4) if not col_data.isnull().all() else None
                col_info["median_val"] = round(float(col_data.median()), 4) if not col_data.isnull().all() else None
                col_info["std_val"] = round(float(col_data.std()), 4) if not col_data.isnull().all() else None

            # Categorical top values
            if col_data.dtype == "object" or pd.api.types.is_categorical_dtype(col_data):
                top_vals = col_data.value_counts().head(5).index.tolist()
                col_info["top_values"] = [str(v) for v in top_vals]

            # Sample values
            non_null = col_data.dropna().head(3).tolist()
            col_info["sample_values"] = [str(v)[:50] for v in non_null]

            columns.append(col_info)

        # Compute quality info using existing DataQualityAnalyzer if available
        quality_info = {}
        try:
            from core.data_quality import DataQualityAnalyzer
            analyzer = DataQualityAnalyzer(df)
            quality_info["quality_score"] = analyzer.generate_data_quality_score()
            quality_info["consistency_issues"] = analyzer.check_data_consistency()
            quality_info["anomalies_detected"] = int(analyzer.detect_anomalies().sum()) if len(analyzer.detect_anomalies()) > 0 else 0
            quality_info["duplicate_rows"] = duplicate_count
            quality_info["missing_values"] = total_missing
            quality_info["missing_pct"] = round(total_missing / total_cells * 100, 2) if total_cells > 0 else 0
        except Exception:
            # If DataQualityAnalyzer fails, provide basic quality info
            quality_info["duplicate_rows"] = duplicate_count
            quality_info["missing_values"] = total_missing
            quality_info["missing_pct"] = round(total_cells / max(total_cells, 1) * 100, 2)

        return {
            "row_count": len(df),
            "column_count": len(df.columns),
            "memory_bytes": int(df.memory_usage(deep=True).sum()),
            "duplicate_count": duplicate_count,
            "total_missing": total_missing,
            "total_cells": total_cells,
            "columns": columns,
            "quality_info": quality_info,
        }

    # ── CRUD Operations ──────────────────────────────────────────

    @staticmethod
    def create_dataset(
        user_id: int,
        name: str,
        original_filename: str,
        file_format: str,
        file_size: int,
        storage_path: str,
        profile: Dict[str, Any],
        encoding: Optional[str] = None,
        delimiter: Optional[str] = None,
    ) -> DatasetDomain:
        """Persist a new dataset to the database."""
        db = get_session()
        try:
            column_info_json = json.dumps(profile.get("columns", [])) if profile.get("columns") else None
            quality_info_json = json.dumps(profile.get("quality_info", {})) if profile.get("quality_info") else None

            dataset_db = DatasetDB(
                user_id=user_id,
                name=name,
                original_filename=original_filename,
                file_format=file_format,
                file_size=file_size,
                storage_path=storage_path,
                row_count=profile.get("row_count"),
                column_count=profile.get("column_count"),
                encoding=encoding,
                delimiter=delimiter,
                column_info=column_info_json,
                quality_info=quality_info_json,
            )
            db.add(dataset_db)
            db.commit()
            db.refresh(dataset_db)
            # Invalidate dataset list cache for this user
            try:
                from app.core.cache import dataset_list_cache
                dataset_list_cache.invalidate_prefix(f"u:{user_id}:")
            except Exception:
                pass
            return DatasetService._to_domain(dataset_db, profile)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def get_dataset(dataset_id: int, user_id: int) -> Optional[DatasetDomain]:
        """Get a dataset by ID, enforcing user ownership. Results are cached (120s TTL)."""
        from app.core.cache import dataset_meta_cache, _make_key
        cache_key = _make_key(user_id, dataset_id, "get")
        cached = dataset_meta_cache.get(cache_key)
        if cached is not None:
            return cached
        db = get_session()
        try:
            dataset_db = db.query(DatasetDB).filter(
                DatasetDB.id == dataset_id,
                DatasetDB.user_id == user_id,
            ).first()
            if not dataset_db:
                return None
            profile = DatasetService._build_profile(dataset_db)
            domain = DatasetService._to_domain(dataset_db, profile)
            dataset_meta_cache.set(cache_key, domain, ttl=120)
            return domain
        finally:
            db.close()

    @staticmethod
    def get_user_datasets(user_id: int, search: Optional[str] = None) -> List[DatasetDomain]:
        """Get all datasets for a user, optionally filtered by search term.
        Cached for 15 seconds to avoid repeated JSON parsing on dashboard loads."""
        from app.core.cache import dataset_list_cache
        cache_key = f"u:{user_id}:list:{search or ''}"
        cached = dataset_list_cache.get(cache_key)
        if cached is not None:
            return cached
        db = get_session()
        try:
            query = db.query(DatasetDB).filter(DatasetDB.user_id == user_id)
            if search:
                pattern = f"%{search}%"
                query = query.filter(
                    (DatasetDB.name.ilike(pattern)) |
                    (DatasetDB.original_filename.ilike(pattern)) |
                    (DatasetDB.file_format.ilike(pattern))
                )
            datasets_db = query.order_by(DatasetDB.created_at.desc()).all()
            result = [DatasetService._to_domain(d, DatasetService._build_profile(d)) for d in datasets_db]
            dataset_list_cache.set(cache_key, result, ttl=15)
            return result
        finally:
            db.close()

    @staticmethod
    def get_recent_datasets(user_id: int, limit: int = 5) -> List[DatasetDomain]:
        """Get most recent datasets for a user."""
        db = get_session()
        try:
            datasets_db = (
                db.query(DatasetDB)
                .filter(DatasetDB.user_id == user_id)
                .order_by(DatasetDB.created_at.desc())
                .limit(limit)
                .all()
            )
            return [DatasetService._to_domain(d) for d in datasets_db]
        finally:
            db.close()

    @staticmethod
    def count_user_datasets(user_id: int) -> int:
        """Count datasets belonging to a user."""
        db = get_session()
        try:
            return db.query(DatasetDB).filter(DatasetDB.user_id == user_id).count()
        finally:
            db.close()

    @staticmethod
    def delete_dataset(dataset_id: int, user_id: int) -> Tuple[bool, str]:
        """Delete a dataset and its stored file. Enforces ownership."""
        db = get_session()
        try:
            dataset_db = db.query(DatasetDB).filter(
                DatasetDB.id == dataset_id,
                DatasetDB.user_id == user_id,
            ).first()
            if not dataset_db:
                return False, "Dataset not found."

            storage_path = dataset_db.storage_path
            db.delete(dataset_db)
            db.commit()

            # Invalidate all caches for this user
            try:
                from app.core.cache import invalidate_user_caches
                invalidate_user_caches(user_id)
            except Exception:
                pass

            # Remove stored file
            DatasetService.delete_storage(storage_path)

            return True, "Dataset deleted successfully."
        except Exception as exc:
            db.rollback()
            return False, f"Failed to delete dataset: {str(exc)[:200]}"
        finally:
            db.close()

    @staticmethod
    def update_dataset(dataset_id: int, user_id: int, name: str, description: Optional[str] = None) -> Tuple[bool, str]:
        """Update dataset metadata (name, description)."""
        db = get_session()
        try:
            dataset_db = db.query(DatasetDB).filter(
                DatasetDB.id == dataset_id,
                DatasetDB.user_id == user_id,
            ).first()
            if not dataset_db:
                return False, "Dataset not found."
            
            if name and name.strip():
                dataset_db.name = name.strip()
            
            if description is not None:
                dataset_db.description = description.strip()
                
            db.commit()
            # Invalidate cached dataset metadata
            try:
                from app.core.cache import invalidate_dataset
                invalidate_dataset(user_id, dataset_id)
            except Exception:
                pass
            return True, "Dataset updated successfully."
        except Exception as exc:
            db.rollback()
            return False, f"Failed to update dataset: {str(exc)[:200]}"
        finally:
            db.close()

    @staticmethod
    def get_dataset_versions(dataset_id: int, user_id: int) -> List[DatasetDomain]:
        """Get all datasets derived from this parent dataset."""
        db = get_session()
        try:
            datasets_db = db.query(DatasetDB).filter(
                DatasetDB.parent_dataset_id == dataset_id,
                DatasetDB.user_id == user_id,
            ).order_by(DatasetDB.created_at.desc()).all()
            return [DatasetService._to_domain(d, DatasetService._build_profile(d)) for d in datasets_db]
        finally:
            db.close()

    @staticmethod
    def get_preview_data(dataset_id: int, user_id: int, page: int = 1, per_page: int = 100) -> Tuple[Optional[pd.DataFrame], Optional[DatasetDomain]]:
        """
        Load dataset preview data with pagination to support large datasets.
        Returns (df_preview, dataset_domain).
        """
        dataset = DatasetService.get_dataset(dataset_id, user_id)
        if not dataset or not dataset.storage_path:
            return None, None

        if not os.path.exists(dataset.storage_path):
            return None, dataset

        try:
            # Fast path for CSV/Excel/Parquet to prevent loading huge files completely
            skip = (page - 1) * per_page
            
            if dataset.file_format == 'csv':
                # Read header
                df_head = pd.read_csv(dataset.storage_path, nrows=0)
                # Read only required rows
                if skip > 0:
                    df = pd.read_csv(dataset.storage_path, skiprows=range(1, skip + 1), nrows=per_page, names=df_head.columns, header=0)
                else:
                    df = pd.read_csv(dataset.storage_path, nrows=per_page)
                return df, dataset
                
            elif dataset.file_format in ('xlsx', 'xls'):
                # xlsx parsing in pandas requires reading the whole file typically, 
                # but we can specify nrows/skiprows if supported by engine.
                df = pd.read_excel(dataset.storage_path, skiprows=range(1, skip + 1) if skip > 0 else None, nrows=per_page)
                return df, dataset
                
            elif dataset.file_format == 'parquet':
                # pyarrow/fastparquet can read chunks but pandas read_parquet doesn't easily support limit/offset directly.
                # However, for memory safety on massive files, we'd use pyarrow natively.
                # For now, if we must load, we can load columns or use pyarrow Dataset.
                import pyarrow.parquet as pq
                parquet_file = pq.ParquetFile(dataset.storage_path)
                # Naive chunking: read the whole thing if small, or just load via pandas if we don't have PyArrow Dataset API handy.
                # Since we want to support large datasets, we use pyarrow to read a specific slice.
                # Note: `read_parquet` reads everything. `ParquetFile.read()` allows selecting chunks.
                # This is a bit complex, so we'll just read everything and slice for Parquet, assuming Parquet is already very efficient.
                # A robust approach uses pyarrow datasets:
                import pyarrow.dataset as ds
                dataset_pa = ds.dataset(dataset.storage_path, format="parquet")
                # PyArrow 14+ supports .take() or .head() - we will just load all for preview if it fits, or use head.
                # We'll use the pandas fallback, assuming snapshot parquet files fit in memory (unlike raw CSV).
                pass

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Fast path failed: {e}")

        # Fallback to load_dataframe
        df, error = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format)
        if df is not None and not df.empty:
            skip = (page - 1) * per_page
            return df.iloc[skip:skip + per_page], dataset
        return None, dataset

    # ── Internal Helpers ──────────────────────────────────────────

    @staticmethod
    def _to_domain(dataset_db: DatasetDB, profile: Optional[Dict] = None) -> DatasetDomain:
        """Convert a DatasetDB ORM object to a DatasetDomain."""
        column_info = None
        quality_info = None
        if profile:
            column_info = profile.get("columns")
            quality_info = profile.get("quality_info")
        elif dataset_db.column_info:
            try:
                column_info = json.loads(dataset_db.column_info)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
        if not quality_info and dataset_db.quality_info:
            try:
                quality_info = json.loads(dataset_db.quality_info)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
        cleaning_pipeline = None
        if dataset_db.cleaning_pipeline:
            try:
                cleaning_pipeline = json.loads(dataset_db.cleaning_pipeline)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        return DatasetDomain(
            id=dataset_db.id,
            user_id=dataset_db.user_id,
            name=dataset_db.name,
            original_filename=dataset_db.original_filename,
            file_format=dataset_db.file_format,
            file_size=dataset_db.file_size,
            storage_path=dataset_db.storage_path,
            row_count=dataset_db.row_count,
            column_count=dataset_db.column_count,
            description=dataset_db.description,
            encoding=dataset_db.encoding,
            delimiter=dataset_db.delimiter,
            column_info=column_info,
            quality_info=quality_info,
            parent_dataset_id=dataset_db.parent_dataset_id,
            cleaning_pipeline=cleaning_pipeline,
            created_at=dataset_db.created_at,
            updated_at=dataset_db.updated_at,
        )

    @staticmethod
    def _build_profile(dataset_db: DatasetDB) -> Dict:
        """Build a profile dict from stored JSON columns."""
        profile = {}
        if dataset_db.column_info:
            try:
                profile["columns"] = json.loads(dataset_db.column_info)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
        if dataset_db.quality_info:
            try:
                profile["quality_info"] = json.loads(dataset_db.quality_info)
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
        profile["row_count"] = dataset_db.row_count
        profile["column_count"] = dataset_db.column_count
        return profile
