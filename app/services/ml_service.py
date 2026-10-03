"""
Service: ML Studio (Phase 7)

Orchestration layer for the Machine Learning Studio.
Wraps the existing ml/ module (MLPipeline, ModelComparisonService,
CrossValidationService, HyperparameterTuningService, LeaderboardService,
ModelExporterService, ModelRegistry) into Flask-compatible operations.

Key principles:
- Never fabricate metrics
- Prevent data leakage (split BEFORE preprocessing)
- Validate ownership on every operation
- Cache pipeline state per (user_id, dataset_id)
- Support classification, regression, and clustering
"""

import os
import json
import time
import uuid
import traceback
import concurrent.futures
import threading
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler, OneHotEncoder, LabelEncoder, OrdinalEncoder
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline as SklearnPipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    r2_score, mean_squared_error, mean_absolute_error,
    silhouette_score, calinski_harabasz_score, davies_bouldin_score,
    confusion_matrix,
)
from sklearn.cluster import KMeans, AgglomerativeClustering, DBSCAN

from app.services.dataset_service import DatasetService
from auth.database import ModelDB, DatasetDB, get_session

# Import existing ML modules
from ml.services.model_registry import get_model_zoo, build_model, default_search_space, XGBOOST_AVAILABLE, LIGHTGBM_AVAILABLE
from ml.services.model_comparator import ModelComparisonService, TrainingCancelled
from ml.services.cross_validator import CrossValidationService
from ml.services.hyperparameter_tuner import HyperparameterTuningService
from ml.services.leaderboard import LeaderboardService
from ml.services.model_exporter import ModelExporterService
from ml.domain.ml_config import CrossValidationConfig, HyperparameterConfig, ModelExportConfig
from ml.domain.ml_result import ModelResult, LeaderboardEntry, TuningResult, ExportManifest

from app.domain.ml_model import MLWorkflowConfig, MLWorkflowResult, ClusteringConfig


class MLService:
    """Service layer for Machine Learning operations."""

    # ── Cache: store workflow state per (user_id, dataset_id) ──
    _pipelines: Dict[str, Any] = {}
    _configs: Dict[str, MLWorkflowConfig] = {}
    _results: Dict[str, MLWorkflowResult] = {}
    _training_locks: Dict[str, bool] = {}
    
    _executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    _jobs: Dict[str, Dict[str, Any]] = {}
    _job_guard = threading.RLock()

    MODEL_STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'ml_models_storage')

    @classmethod
    def has_active_job(cls, user_id, dataset_id):
        with cls._job_guard:
            return cls._training_locks.get(cls._cache_key(user_id, dataset_id), False) or any(
                job['user_id'] == user_id and job['dataset_id'] == dataset_id
                and job['status'] in ('running', 'cancelling') for job in cls._jobs.values())

    @classmethod
    def _cache_key(cls, user_id: int, dataset_id: int) -> str:
        return f"{user_id}:{dataset_id}"

    # ── Dataset Loading ──────────────────────────────────────────

    @classmethod
    def load_dataset(cls, user_id: int, dataset_id: int) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load dataset DataFrame with caching. Returns (df, error)."""
        from app.core.cache import _make_key
        dataset = DatasetService.get_dataset(dataset_id, user_id)
        if not dataset:
            return None, "Dataset not found or access denied."
        try:
            df_cache_key = _make_key(user_id, dataset_id, "ml_df")
            df, err = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format, _cache_key=df_cache_key)
            if err:
                return None, err
            return df, None
        except Exception as e:
            return None, f"Failed to load dataset: {str(e)}"

    @classmethod
    def get_dataset_info(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get dataset metadata for ML studio. Results are cached (120s TTL)."""
        from app.core.cache import ml_info_cache, _make_key
        cache_key = _make_key(user_id, dataset_id, "info")
        cached = ml_info_cache.get(cache_key)
        if cached is not None:
            return cached, None

        dataset = DatasetService.get_dataset(dataset_id, user_id)
        if not dataset:
            return None, "Dataset not found or access denied."

        df, err = cls.load_dataset(user_id, dataset_id)
        if err:
            return None, err

        # Column analysis — produce both column_info and column_types (JS uses column_types)
        total_rows = len(df)
        columns = []
        missing_cells = 0
        for col in df.columns:
            missing_count = int(df[col].isnull().sum())
            missing_cells += missing_count
            unique_count = int(df[col].nunique())
            is_numeric = pd.api.types.is_numeric_dtype(df[col])
            inferred_type = 'numeric' if is_numeric else 'categorical'

            col_info = {
                "name": col,
                "dtype": str(df[col].dtype),
                "inferred_type": inferred_type,
                "missing": missing_count,
                "missing_count": missing_count,
                "missing_pct": round(float(missing_count / total_rows * 100), 1) if total_rows > 0 else 0,
                "unique": unique_count,
                "unique_count": unique_count,
                "sample_values": [
                    _serialize_val(v) for v in df[col].dropna().head(5).tolist()
                ],
            }
            if is_numeric:
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    col_info["min"] = float(non_null.min())
                    col_info["max"] = float(non_null.max())
                    col_info["mean"] = round(float(non_null.mean()), 4)
            columns.append(col_info)

        has_cleaning_pipeline = bool(dataset.cleaning_pipeline)
        cleaning_ops = []
        if has_cleaning_pipeline:
            try:
                cleaning_ops = json.loads(dataset.cleaning_pipeline) if isinstance(dataset.cleaning_pipeline, str) else dataset.cleaning_pipeline
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        result = {
            "id": dataset.id,
            "name": dataset.name,
            "rows": total_rows,
            "columns": len(columns),
            # column_types is the JS-expected field name
            "column_types": columns,
            # column_info kept for backward compatibility
            "column_info": columns,
            "missing_cells": missing_cells,
            "has_cleaning_pipeline": has_cleaning_pipeline,
            "cleaning_operations": cleaning_ops,
            "parent_dataset_id": dataset.parent_dataset_id,
            "quality_info": dataset.quality_info,
        }
        ml_info_cache.set(cache_key, result, ttl=120)
        return result, None

    # ── Target Analysis ───────────────────────────────────────────

    @classmethod
    def analyze_target(cls, user_id: int, dataset_id: int, target_column: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Analyze a target column for ML suitability."""
        df, err = cls.load_dataset(user_id, dataset_id)
        if err:
            return None, err

        if target_column not in df.columns:
            return None, f"Column '{target_column}' not found in dataset."

        col = df[target_column]
        dtype = str(col.dtype)
        nunique = int(col.nunique())
        missing = int(col.isnull().sum())
        total = len(col)
        warnings_list = []

        is_numeric = pd.api.types.is_numeric_dtype(col)
        is_integer = pd.api.types.is_integer_dtype(col)
        is_binary = nunique == 2

        # Build distribution for categorical targets or classification targets
        distribution = None
        statistics = None
        suggested_problem_type = None
        problem_subtype = None

        if is_numeric:
            non_null = col.dropna()
            statistics = {
                "min": float(non_null.min()) if len(non_null) > 0 else None,
                "max": float(non_null.max()) if len(non_null) > 0 else None,
                "mean": round(float(non_null.mean()), 4) if len(non_null) > 0 else None,
                "median": round(float(non_null.median()), 4) if len(non_null) > 0 else None,
                "std": round(float(non_null.std()), 4) if len(non_null) > 1 else None,
            }
            if is_binary or (is_integer and nunique <= 20 and (nunique / total) < 0.05):
                suggested_problem_type = "classification"
                problem_subtype = "binary" if nunique == 2 else "multiclass"
                dist_counts = col.value_counts()
                distribution = {str(k): int(v) for k, v in dist_counts.items()}
                # Imbalance check
                min_pct = float(dist_counts.min() / dist_counts.sum() * 100)
                if min_pct < 10:
                    warnings_list.append(
                        f"Class imbalance detected: smallest class is {min_pct:.1f}% of data. "
                        "Consider F1, ROC-AUC metrics and stratified splitting."
                    )
            else:
                suggested_problem_type = "regression"
        else:
            dist_counts = col.value_counts()
            distribution = {str(k): int(v) for k, v in dist_counts.items()}
            suggested_problem_type = "classification"
            problem_subtype = "binary" if nunique == 2 else "multiclass"
            # Imbalance check
            min_pct = float(dist_counts.min() / dist_counts.sum() * 100)
            if min_pct < 10:
                warnings_list.append(
                    f"Class imbalance detected: smallest class is {min_pct:.1f}% of data. "
                    "Consider F1, ROC-AUC metrics and stratified splitting."
                )

        # Missing values warning
        missing_pct = round(missing / total * 100, 1) if total > 0 else 0
        if missing_pct > 20:
            warnings_list.append(
                f"Target column has {missing_pct}% missing values. Rows with missing target will be dropped."
            )

        return {
            "column": target_column,
            "dtype": dtype,
            # JS reads unique_count and missing_count
            "unique_count": nunique,
            "missing_count": missing,
            "missing_percentage": missing_pct,
            # Kept for backward compat
            "nunique": nunique,
            "missing": missing,
            "missing_pct": missing_pct,
            "sample_values": [_serialize_val(v) for v in col.dropna().head(10).tolist()],
            "suggested_problem_type": suggested_problem_type,
            "suggested_problem": suggested_problem_type,
            "problem_subtype": problem_subtype,
            "distribution": distribution,
            "statistics": statistics,
            "warnings": warnings_list,
            "is_numeric": is_numeric,
        }, None

    # ── Feature Validation ────────────────────────────────────────

    @classmethod
    def validate_features(cls, user_id: int, dataset_id: int, target_column: Optional[str],
                         feature_columns: List[str], problem_type: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Validate feature selection for ML training."""
        df, err = cls.load_dataset(user_id, dataset_id)
        if err:
            return None, err

        warnings = []
        errors = []

        # Check target in features
        if target_column and target_column in feature_columns:
            errors.append(f"Target leakage detected. The target column '{target_column}' cannot be used as an input feature.")

        # Check columns exist
        for col in feature_columns:
            if col not in df.columns:
                errors.append(f"Column '{col}' not found in dataset.")

        if errors:
            return {"valid": False, "errors": errors, "warnings": warnings}, None

        # Check for identifier-like columns
        id_patterns = ['id', 'identifier', 'uuid', 'key', 'index', '_id']
        for col in feature_columns:
            col_lower = col.lower().strip()
            if any(p == col_lower or col_lower.endswith(p) for p in id_patterns):
                if df[col].nunique() == len(df):
                    warnings.append(f"Column '{col}' appears to be an identifier (all unique values). Consider excluding it from features.")

        # Check for constant columns
        for col in feature_columns:
            if df[col].nunique() <= 1:
                warnings.append(f"Column '{col}' has only one unique value and provides no information for ML.")

        # Check for target-like duplicate columns
        if target_column:
            for col in feature_columns:
                if col != target_column and col.lower().replace('_', '').replace(' ', '') == target_column.lower().replace('_', '').replace(' ', ''):
                    warnings.append(f"Column '{col}' appears highly related to the target '{target_column}'. Review before training.")

        # Dataset size warnings
        n_rows = len(df)
        if n_rows < 200:
            warnings.append(f"Small dataset: only {n_rows} rows. Model performance estimates may have high variance. Consider using cross-validation and interpreting results cautiously.")

        # High-dimensionality warning
        if len(feature_columns) > n_rows:
            warnings.append(f"High-dimensional dataset: {len(feature_columns)} features and only {n_rows} rows. Some models may overfit. Consider feature selection or regularization.")

        return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}, None

    # ── Configuration ─────────────────────────────────────────────

    @classmethod
    def save_config(cls, user_id: int, dataset_id: int, config_data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """Save ML workflow configuration."""
        try:
            config = MLWorkflowConfig(
                dataset_id=dataset_id,
                target_column=config_data.get("target_column"),
                feature_columns=config_data.get("feature_columns", []),
                problem_type=config_data.get("problem_type"),
                test_size=float(config_data.get("test_size", 0.2)),
                random_state=int(config_data.get("random_state", 42)),
                cv_folds=int(config_data.get("cv_folds", 5)),
                cv_strategy=config_data.get("cv_strategy", "auto"),
                primary_metric=config_data.get("primary_metric"),
                scaling=config_data.get("scaling", "standard"),
                encoding=config_data.get("encoding", "onehot"),
                imputation=config_data.get("imputation", "median"),
                class_weights=config_data.get("class_weights"),
                selected_algorithms=config_data.get("selected_algorithms"),
                auto_mode=config_data.get("auto_mode", True),
                optimization_level=config_data.get("optimization_level", "off"),
                optimization_iterations=int(config_data.get("optimization_iterations", 20)),
                optimization_model=config_data.get("optimization_model"),
                experiment_config=config_data.get("experiment_config"),
            )
            key = cls._cache_key(user_id, dataset_id)
            if cls.has_active_job(user_id, dataset_id):
                return None, 'Wait for training to finish before changing configuration.'
            if config.problem_type not in {'classification', 'regression', 'clustering'}:
                return None, 'Choose classification, regression, or clustering.'
            if not 0 < config.test_size < 1 or config.cv_folds < 2:
                return None, 'Test size must be between 0 and 1, and cross-validation needs at least 2 folds.'
            if config.problem_type == 'clustering':
                config.target_column = None
            if cls._configs.get(key) == config:
                return {"saved": True, "config": _config_to_dict(config)}, None
            cls._pipelines.pop(key, None)
            cls._results.pop(key, None)
            cls._configs[key] = config
            return {"saved": True, "config": _config_to_dict(config)}, None
        except Exception as e:
            return None, f"Failed to save configuration: {str(e)}"

    @classmethod
    def get_config(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get saved ML workflow configuration."""
        key = cls._cache_key(user_id, dataset_id)
        config = cls._configs.get(key)
        if config:
            return _config_to_dict(config), None
        return None, None

    # ── Data Preparation ──────────────────────────────────────────

    @classmethod
    def prepare_data(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Prepare data for ML: split, preprocess, generate features report."""
        key = cls._cache_key(user_id, dataset_id)
        if cls.has_active_job(user_id, dataset_id):
            return None, 'Wait for training to finish before preparing data again.'
        config = cls._configs.get(key)
        if not config:
            return None, "No configuration found. Please configure the ML workflow first."

        df, err = cls.load_dataset(user_id, dataset_id)
        if err:
            return None, err

        try:
            result = MLWorkflowResult(config=config)
            warnings = []
            df = df.replace([np.inf, -np.inf], np.nan)

            # Determine task type
            if config.problem_type == 'clustering':
                result.task_type = 'clustering'
            elif config.problem_type == 'classification' or config.problem_type == 'regression':
                result.task_type = config.problem_type
            else:
                return None, f"Invalid problem type: {config.problem_type}"

            # Feature validation
            feature_cols = [c for c in config.feature_columns if c in df.columns]
            if config.target_column and config.target_column in df.columns:
                feature_cols = [c for c in feature_cols if c != config.target_column]

            if not feature_cols:
                return None, "No valid features selected for training."

            result.features_used = feature_cols
            result.categorical_features = [c for c in feature_cols if df[c].dtype == 'object' or str(df[c].dtype) == 'category']
            result.numerical_features = [c for c in feature_cols if c not in result.categorical_features]
            if config.encoding == 'onehot' and any(df[c].nunique() > 50 for c in result.categorical_features):
                warnings.append('High-cardinality categories are grouped into at most 50 encoded values per column to keep training manageable.')

            if config.problem_type != 'clustering':
                if not config.target_column or config.target_column not in df.columns:
                    return None, "Target column is required for supervised learning."

                X = df[feature_cols].copy()
                y = df[config.target_column].copy()

                # Handle missing target values
                valid_mask = y.notna()
                X = X[valid_mask]
                y = y[valid_mask]

                if len(y) == 0:
                    return None, "No valid (non-null) target values available."

                # Encode target if categorical
                original_classes = None
                if result.task_type == 'classification':
                    from sklearn.utils.multiclass import type_of_target
                    if type_of_target(y) == 'continuous':
                        return None, 'This target contains continuous numbers. Choose Regression, or select a categorical target such as payment or color.'
                    le = LabelEncoder()
                    y = pd.Series(le.fit_transform(y.astype(str)), index=y.index, name=config.target_column)
                    original_classes = list(le.classes_)
                else:
                    y = pd.to_numeric(y, errors='coerce')
                    if y.isna().any():
                        return None, 'Regression requires a numeric target. Choose Classification for category labels.'

                # Detect subtype
                n_classes = y.nunique()
                if result.task_type == 'classification':
                    result.problem_subtype = 'binary' if n_classes == 2 else 'multiclass'

                    # Class distribution
                    dist = y.value_counts()
                    if n_classes < 2:
                        return None, 'Classification requires at least two target classes.'
                    if dist.min() < 3:
                        return None, 'Each target class needs at least 3 examples for a held-out test and cross-validation. Choose another target or collect more examples for rare classes.'
                    result.class_distribution = {
                        "classes": {str(int(k)): int(v) for k, v in dist.items()},
                        "n_classes": int(n_classes),
                        "original_classes": original_classes,
                    }

                    # Imbalance check
                    min_class_pct = dist.min() / dist.sum() * 100
                    if min_class_pct < 10:
                        warnings.append(f"Class imbalance: smallest class is {min_class_pct:.1f}% of data.")

                    # Stratified split
                    use_stratify = True
                    if n_classes < 2:
                        use_stratify = False
                        warnings.append("Cannot use stratified split with a single class.")
                else:
                    use_stratify = False

                # Train/Test split (BEFORE preprocessing — prevents leakage)
                if use_stratify and (int(np.ceil(len(y) * config.test_size)) < n_classes or
                                     len(y) - int(np.ceil(len(y) * config.test_size)) < n_classes):
                    return None, 'The train and test sets must each have room for every class. Adjust the test size or choose a target with fewer classes.'
                stratify = y if use_stratify else None
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y,
                    test_size=config.test_size,
                    random_state=config.random_state,
                    stratify=stratify,
                )

                result.train_rows = len(X_train)
                result.test_rows = len(X_test)

                if result.train_rows < 5 or result.test_rows < 2:
                    return None, f"Insufficient data after split: {result.train_rows} train, {result.test_rows} test. Use a smaller test size or more data."

                # Build preprocessing pipeline
                cv_strategy = config.cv_strategy
                if cv_strategy == 'auto':
                    cv_strategy = 'stratified' if result.task_type == 'classification' else 'kfold'

                if result.task_type == 'classification' and y_train.value_counts().min() < 2:
                    return None, 'The split leaves too few training examples per class. Reduce the test size or add examples.'
                preprocessor = cls._build_preprocessor(X_train, config.scaling, config.encoding, config.imputation)

                # Fit on TRAINING data only, then transform both
                X_train_processed = preprocessor.fit_transform(X_train)
                X_test_processed = preprocessor.transform(X_test)

                # Get feature names
                try:
                    feature_names_out = list(preprocessor.get_feature_names_out())
                except Exception:
                    feature_names_out = [f"feature_{i}" for i in range(X_train_processed.shape[1])]

                result.preprocessing_info = {
                    "numerical_features": result.numerical_features,
                    "categorical_features": result.categorical_features,
                    "n_features_after_encoding": X_train_processed.shape[1],
                    "scaling": config.scaling,
                    "encoding": config.encoding,
                    "imputation": config.imputation,
                }

                # Store pipeline state
                cls._pipelines[key] = {
                    "preprocessor": preprocessor,
                    "X_train": X_train_processed,
                    "X_test": X_test_processed,
                    "y_train": y_train,
                    "y_test": y_test,
                    "X_train_raw": X_train,
                    "X_test_raw": X_test,
                    "feature_names_out": feature_names_out,
                    "task_type": result.task_type,
                    "df": df,
                    "feature_cols": feature_cols,
                    "label_encoder_classes": original_classes,
                }

            else:
                # Clustering: no target, no split needed
                X = df[feature_cols].copy()
                result.train_rows = len(X)
                result.test_rows = 0

                preprocessor = cls._build_preprocessor(X, config.scaling, config.encoding, config.imputation)
                X_processed = preprocessor.fit_transform(X)

                try:
                    feature_names_out = list(preprocessor.get_feature_names_out())
                except Exception:
                    feature_names_out = [f"feature_{i}" for i in range(X_processed.shape[1])]

                result.preprocessing_info = {
                    "numerical_features": result.numerical_features,
                    "categorical_features": result.categorical_features,
                    "n_features_after_encoding": X_processed.shape[1],
                    "scaling": config.scaling,
                    "encoding": config.encoding,
                    "imputation": config.imputation,
                }

                cls._pipelines[key] = {
                    "preprocessor": preprocessor,
                    "X_train": X_processed,
                    "X_test": None,
                    "y_train": None,
                    "y_test": None,
                    "X_train_raw": X,
                    "X_test_raw": None,
                    "feature_names_out": feature_names_out,
                    "task_type": "clustering",
                    "df": df,
                    "feature_cols": feature_cols,
                    "label_encoder_classes": None,
                }

            result.warnings = warnings
            cls._results[key] = result

            return _result_to_dict(result), None

        except Exception as e:
            traceback.print_exc()
            return None, f"Data preparation failed: {str(e)}"

    @classmethod
    def _build_preprocessor(cls, X, scaling: str = "standard", encoding: str = "onehot",
                            imputation: str = "median") -> ColumnTransformer:
        """Build sklearn ColumnTransformer for preprocessing."""
        numeric_features = X.select_dtypes(include=[np.number]).columns.tolist()
        categorical_features = [c for c in X.columns if c not in numeric_features]

        # Numeric transformer
        scaler_map = {
            'standard': StandardScaler(),
            'minmax': MinMaxScaler(),
            'robust': RobustScaler(),
        }
        imputer_map = {
            'median': SimpleImputer(strategy='median'),
            'mean': SimpleImputer(strategy='mean'),
            'most_frequent': SimpleImputer(strategy='most_frequent'),
            'constant': SimpleImputer(strategy='constant', fill_value=0),
        }

        numeric_transformer = SklearnPipeline(steps=[
            ('imputer', imputer_map.get(imputation, SimpleImputer(strategy='median'))),
            ('scaler', 'passthrough' if scaling == 'none' else scaler_map.get(scaling, StandardScaler())),
        ])

        # Categorical transformer
        if encoding == 'ordinal':
            cat_transformer = SklearnPipeline(steps=[
                ('imputer', SimpleImputer(strategy='most_frequent', fill_value='missing')),
                ('encoder', OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)),
            ])
        else:
            cat_transformer = SklearnPipeline(steps=[
                ('imputer', SimpleImputer(strategy='most_frequent', fill_value='missing')),
                ('encoder', OneHotEncoder(handle_unknown='infrequent_if_exist', max_categories=50, sparse_output=False)),
            ])

        transformers = []
        if numeric_features:
            transformers.append(('num', numeric_transformer, numeric_features))
        if categorical_features:
            transformers.append(('cat', cat_transformer, categorical_features))

        if not transformers:
            transformers.append(('num', numeric_transformer, X.columns.tolist()))

        return ColumnTransformer(transformers=transformers, remainder='drop')

    # ── Model Training ─────────────────────────────────────────────

    @classmethod
    def start_training_job(cls, user_id: int, dataset_id: int) -> Dict[str, str]:
        """Start model training in a background thread and return a job_id."""
        job_id = str(uuid.uuid4())
        with cls._job_guard:
            for existing_id, job in cls._jobs.items():
                if job['user_id'] == user_id and job['dataset_id'] == dataset_id and job['status'] in ('running', 'cancelling'):
                    return {'job_id': existing_id, 'status': job['status']}
            # Keep completed jobs for an hour, without unbounded result retention.
            for old_id in list(cls._jobs):
                old = cls._jobs[old_id]
                if old['status'] not in ('running', 'cancelling') and time.time() - old['created'] > 3600:
                    del cls._jobs[old_id]
            cls._jobs[job_id] = {'status': 'running', 'user_id': user_id,
                                'dataset_id': dataset_id, 'created': time.time(),
                                'completed': 0, 'total': 0, 'model': None,
                                'cancel': threading.Event()}
        job = cls._jobs[job_id]

        def progress(completed, total, model):
            with cls._job_guard:
                if job['cancel'].is_set():
                    raise TrainingCancelled('Training cancelled.')
                job.update(completed=completed, total=total, model=model)
        
        def run_job():
            try:
                progress(0, 0, None)
                result, error = cls.train_models(user_id, dataset_id, progress=progress)
                with cls._job_guard:
                    if job['cancel'].is_set():
                        job.update(status='cancelled')
                    elif error:
                        job.update(status='error', error=error)
                    else:
                        job.update(status='done', result=result)
            except Exception as e:
                if not isinstance(e, TrainingCancelled):
                    traceback.print_exc()
                with cls._job_guard:
                    job.update(status='cancelled' if job['cancel'].is_set() else 'error')
                    if job['status'] == 'error':
                        job['error'] = str(e)

        cls._executor.submit(run_job)
        return {"job_id": job_id, "status": "running"}

    @classmethod
    def get_job_status(cls, job_id: str, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Retrieve the status of a background job."""
        with cls._job_guard:
            job = cls._jobs.get(job_id)
            if not job or job['user_id'] != user_id or job['dataset_id'] != dataset_id:
                return None, 'Job not found'
            return {k: v for k, v in job.items() if k not in ('cancel', 'user_id', 'dataset_id', 'created')}, None

    @classmethod
    def cancel_job(cls, job_id, user_id, dataset_id):
        with cls._job_guard:
            status, error = cls.get_job_status(job_id, user_id, dataset_id)
            if error:
                return None, error
            job = cls._jobs[job_id]
            if job['status'] == 'running':
                job['cancel'].set()
                job['status'] = 'cancelling'
            return cls.get_job_status(job_id, user_id, dataset_id)

    @classmethod
    def train_models(cls, user_id: int, dataset_id: int, progress=None) -> Tuple[Optional[Dict], Optional[str]]:
        """Train ML models based on saved configuration."""
        key = cls._cache_key(user_id, dataset_id)

        # Check training lock (prevent duplicate submissions)
        if cls._training_locks.get(key):
            return None, "Training is already in progress. Please wait."

        pipeline_data = cls._pipelines.get(key)
        config = cls._configs.get(key)

        if not pipeline_data or not config:
            return None, "No prepared data found. Please prepare data first."

        cls._training_locks[key] = True
        try:
            X_train = pipeline_data["X_train"]
            y_train = pipeline_data["y_train"]
            X_test = pipeline_data["X_test"]
            y_test = pipeline_data["y_test"]
            task_type = pipeline_data["task_type"]

            start_time = time.time()
            warnings = list(cls._results.get(key, MLWorkflowResult(config=config)).warnings or [])

            if task_type == 'clustering':
                return cls._train_clustering(user_id, dataset_id, key, pipeline_data, config, warnings, progress)

            # Determine CV strategy
            cv_strategy = config.cv_strategy
            if cv_strategy == 'auto':
                cv_strategy = 'stratified' if task_type == 'classification' else 'kfold'
            if cv_strategy == 'stratified' and task_type != 'classification':
                cv_strategy = 'kfold'

            max_folds = int(y_train.value_counts().min()) if task_type == 'classification' else len(y_train) // 2
            folds = min(config.cv_folds, max_folds)
            if folds < 2:
                return None, 'Not enough training examples for cross-validation.'
            if folds != config.cv_folds:
                warnings.append(f'Cross-validation reduced to {folds} folds to fit the available training examples.')
            cv_config = CrossValidationConfig(
                strategy=cv_strategy,
                n_splits=folds,
                shuffle=True,
                random_state=config.random_state,
                scoring=config.primary_metric,
            )

            # Get models
            if config.auto_mode or not config.selected_algorithms:
                models = get_model_zoo(task_type, fast_mode=True, random_state=config.random_state)
            else:
                all_models = get_model_zoo(task_type, fast_mode=False, random_state=config.random_state)
                models = {name: all_models[name] for name in config.selected_algorithms if name in all_models}

            # Train and compare
            if not models:
                return None, 'Select at least one available model.'
            comparator = ModelComparisonService()
            results = comparator.compare(
                X_train, y_train, X_test, y_test,
                task_type=task_type,
                cv_config=cv_config,
                fast_mode=not config.auto_mode,
                random_state=config.random_state,
                models=models,
                preprocessor=pipeline_data['preprocessor'],
                X_train_raw=pipeline_data['X_train_raw'],
                progress=progress,
            )

            # Build leaderboard
            failed = {name: mr.error for name, mr in results.items() if not mr.is_valid}
            if len(failed) == len(results):
                return None, 'No models could be trained. ' + '; '.join(f'{name}: {error}' for name, error in failed.items())
            warnings.extend(f'{name} could not be evaluated: {error}' for name, error in failed.items())
            lb_service = LeaderboardService()
            leaderboard = lb_service.build(results, task_type, primary_metric=config.primary_metric)

            training_time = time.time() - start_time

            # Serialize results
            model_results = {}
            for name, mr in results.items():
                entry = {
                    "name": name,
                    "valid": mr.is_valid,
                    "fit_time": mr.fit_time_seconds,
                }
                if mr.is_valid:
                    entry["cv_mean"] = mr.cv_result.mean_score
                    entry["cv_std"] = mr.cv_result.std_score
                    entry["test_metrics"] = mr.test_metrics
                    entry["params"] = {k: str(v) for k, v in mr.params.items() if not k.endswith('_')}
                else:
                    entry["error"] = mr.error
                model_results[name] = entry

            leaderboard_data = []
            for entry in leaderboard:
                leaderboard_data.append({
                    "rank": entry.rank,
                    "model_name": entry.model_name,
                    "primary_metric": entry.primary_metric_name,
                    "primary_score": round(entry.primary_metric_value, 4),
                    "cv_mean": round(entry.cv_mean, 4),
                    "cv_std": round(entry.cv_std, 4),
                    "composite_score": round(entry.composite_score, 4),
                    "metrics": {k: round(v, 4) for k, v in entry.metrics.items()},
                    "fit_time": round(entry.fit_time_seconds, 2),
                })

            best_name = leaderboard[0].model_name if leaderboard else None

            # Update pipeline cache
            pipeline_data["results"] = results
            pipeline_data["leaderboard"] = leaderboard
            pipeline_data["model_results"] = model_results
            cls._pipelines[key] = pipeline_data

            # Update workflow result
            result = cls._results.get(key, MLWorkflowResult(config=config))
            result.model_results = model_results
            result.leaderboard = leaderboard_data
            result.best_model_name = best_name
            result.training_time = round(training_time, 2)
            result.warnings = warnings
            cls._results[key] = result

            return {
                "model_results": model_results,
                "leaderboard": leaderboard_data,
                "best_model": best_name,
                "training_time": round(training_time, 2),
                "task_type": task_type,
                "warnings": warnings,
                "cv_config": {
                    "strategy": cv_strategy,
                    "folds": folds,
                    "scoring": config.primary_metric,
                },
            }, None

        except Exception as e:
            traceback.print_exc()
            return None, f"Model training failed: {str(e)}"
        finally:
            cls._training_locks[key] = False

    @classmethod
    def _train_clustering(cls, user_id: int, dataset_id: int, key: str,
                         pipeline_data: Dict, config: MLWorkflowConfig,
                         warnings: List[str], progress=None) -> Tuple[Optional[Dict], Optional[str]]:
        """Train clustering models."""
        X = pipeline_data["X_train"]
        feature_names = pipeline_data.get("feature_names_out", [])
        start_time = time.time()

        clust_config = getattr(config, 'experiment_config', None) or {}
        if isinstance(clust_config, dict):
            clust_config = ClusteringConfig(**{k: v for k, v in clust_config.items() if k in ClusteringConfig.__dataclass_fields__})

        results = {}

        from app.services.clustering_service import compare_clusters
        results, leaderboard, best_model = compare_clusters(X, config, progress=progress)
        training_time = time.time() - start_time
        pipeline_data["leaderboard"] = leaderboard
        pipeline_data["clustering_results"] = results
        pipeline_data["best_clustering"] = best_model
        cls._pipelines[key] = pipeline_data

        result = cls._results.get(key, MLWorkflowResult(config=config))
        result.model_results = results
        result.leaderboard = leaderboard
        result.best_model_name = best_model
        result.training_time = round(training_time, 2)
        result.task_type = 'clustering'
        result.warnings = warnings
        cls._results[key] = result

        return {
            "model_results": results,
            "leaderboard": leaderboard,
            "best_model": best_model,
            "training_time": round(training_time, 2),
            "task_type": "clustering",
            "warnings": warnings,
        }, None

    # ── Hyperparameter Optimization ───────────────────────────────

    @classmethod
    def optimize_model(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Run hyperparameter optimization on a specific model."""
        key = cls._cache_key(user_id, dataset_id)
        pipeline_data = cls._pipelines.get(key)
        config = cls._configs.get(key)

        if not pipeline_data or not config:
            return None, "No trained models found. Train models first."

        if config.optimization_level == 'off':
            return None, "Optimization is disabled. Enable it in configuration."

        model_name = config.optimization_model
        if not model_name:
            model_name = cls._results[key].best_model_name if key in cls._results else None
        if not model_name:
            return None, "No model selected for optimization."

        X_train = pipeline_data["X_train"]
        y_train = pipeline_data["y_train"]
        task_type = pipeline_data["task_type"]

        if task_type == 'clustering':
            return None, "Hyperparameter optimization is not supported for clustering in this version."

        cv_strategy = config.cv_strategy
        if cv_strategy == 'auto':
            cv_strategy = 'stratified' if task_type == 'classification' else 'kfold'
        if cv_strategy == 'stratified' and task_type != 'classification':
            cv_strategy = 'kfold'

        n_trials = config.optimization_iterations
        if config.optimization_level == 'fast':
            n_trials = max(10, n_trials // 2)

        hp_config = HyperparameterConfig(
            method='random',  # Use RandomizedSearchCV for reliability
            n_trials=n_trials,
            cv=CrossValidationConfig(
                strategy=cv_strategy,
                n_splits=min(config.cv_folds, 3, int(y_train.value_counts().min()) if task_type == 'classification' else len(y_train) // 2),
                random_state=config.random_state,
                scoring=config.primary_metric,
            ),
        )

        try:
            tuner = HyperparameterTuningService()
            base_name = model_name.replace(' (Tuned)', '')
            tuned = tuner.tune(
                X_train, y_train, task_type, base_name, cv_config=hp_config.cv,
                random_state=config.random_state,
            )
            tuning_result = TuningResult(
                model_name=base_name, method='grid', best_params=tuned['best_params'],
                best_score=tuned['best_score'], n_trials=tuned['n_trials'],
                scoring=hp_config.cv.scoring or tuner.cv_service.default_scoring(task_type),
            )

            # Refit tuned model and evaluate on test set
            tuned_model = build_model(task_type, base_name, tuning_result.best_params, random_state=config.random_state)
            tuned_model.fit(X_train, y_train)
            y_pred = tuned_model.predict(pipeline_data["X_test"])

            # Calculate test metrics
            y_test = pipeline_data["y_test"]
            test_metrics = {}
            if task_type == 'classification':
                test_metrics['accuracy'] = float(accuracy_score(y_test, y_pred))
                test_metrics['precision'] = float(precision_score(y_test, y_pred, average='weighted', zero_division=0))
                test_metrics['recall'] = float(recall_score(y_test, y_pred, average='weighted', zero_division=0))
                test_metrics['f1'] = float(f1_score(y_test, y_pred, average='weighted', zero_division=0))
                try:
                    if hasattr(tuned_model, 'predict_proba') and len(np.unique(y_test)) == 2:
                        proba = tuned_model.predict_proba(pipeline_data["X_test"])[:, 1]
                        test_metrics['roc_auc'] = float(roc_auc_score(y_test, proba))
                except Exception as _e:
                    import logging
                    logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)
            else:
                test_metrics['r2'] = float(r2_score(y_test, y_pred))
                test_metrics['rmse'] = float(np.sqrt(mean_squared_error(y_test, y_pred)))
                test_metrics['mae'] = float(mean_absolute_error(y_test, y_pred))

            # Update pipeline cache
            if "tuning_results" not in pipeline_data:
                pipeline_data["tuning_results"] = []
            pipeline_data["tuning_results"].append({
                "model_name": model_name,
                "best_params": {k: v for k, v in tuning_result.best_params.items()},
                "best_score": round(float(tuning_result.best_score), 4),
                "n_trials": tuning_result.n_trials,
                "method": tuning_result.method,
                "test_metrics": {k: round(v, 4) for k, v in test_metrics.items()},
            })
            cls._pipelines[key] = pipeline_data

            return {
                "model_name": model_name,
                "best_params": {k: _serialize_val(v) for k, v in tuning_result.best_params.items()},
                "best_cv_score": round(float(tuning_result.best_score), 4),
                "n_trials": tuning_result.n_trials,
                "method": tuning_result.method,
                "test_metrics": {k: round(v, 4) for k, v in test_metrics.items()},
            }, None

        except Exception as e:
            traceback.print_exc()
            return None, f"Optimization failed: {str(e)}"

    # ── Results & Evaluation ──────────────────────────────────────

    @classmethod
    def get_results(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get training results."""
        key = cls._cache_key(user_id, dataset_id)
        result = cls._results.get(key)
        if not result:
            return None, "No results found. Train models first."

        pipeline_data = cls._pipelines.get(key)
        resp = _result_to_dict(result)

        # Add confusion matrix for classification
        if result.task_type == 'classification' and pipeline_data:
            try:
                y_test = pipeline_data["y_test"]
                best_name = result.best_model_name
                if best_name and best_name in pipeline_data.get("results", {}):
                    mr = pipeline_data["results"][best_name]
                    if mr.is_valid:
                        y_pred = pipeline_data["results"][best_name].fit_and_predict(
                            pipeline_data["X_train"], pipeline_data["y_train"],
                            pipeline_data["X_test"]
                        ) if hasattr(mr, 'fit_and_predict') else None

                        # Simpler approach: re-predict
                        best_entry = pipeline_data.get("model_results", {}).get(best_name, {})
                        if best_entry.get("valid"):
                            # Use cached predictions - get from test metrics calculation
                            pass
            except Exception as _e:
                import logging
                logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

        return resp, None

    @classmethod
    def get_confusion_matrix(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Generate confusion matrix for best classification model."""
        key = cls._cache_key(user_id, dataset_id)
        pipeline_data = cls._pipelines.get(key)
        result = cls._results.get(key)

        if not pipeline_data or not result:
            return None, "No results found."

        if result.task_type != 'classification':
            return None, "Confusion matrix is only available for classification tasks."

        try:
            X_test = pipeline_data["X_test"]
            y_test = pipeline_data["y_test"]
            best_name = result.best_model_name

            if not best_name:
                return None, "No best model found."

            # Re-fit and predict the best model
            base_name = best_name.replace(' (Tuned)', '')
            results = pipeline_data.get("results", {})
            if best_name in results and results[best_name].is_valid:
                mr = results[best_name]
                model = pipeline_data["results"][best_name].estimator
                model.fit(pipeline_data["X_train"], pipeline_data["y_train"])
                y_pred = model.predict(X_test)

                cm = confusion_matrix(y_test, y_pred)
                return {
                    "matrix": cm.tolist(),
                    "classes": sorted([int(c) for c in np.unique(y_test)]),
                    "model_name": best_name,
                }, None

            return None, f"Best model '{best_name}' is not available."
        except Exception as e:
            return None, f"Failed to generate confusion matrix: {str(e)}"

    @classmethod
    def get_predictions(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get actual vs predicted values for regression."""
        key = cls._cache_key(user_id, dataset_id)
        pipeline_data = cls._pipelines.get(key)
        result = cls._results.get(key)

        if not pipeline_data or not result:
            return None, "No results found."

        if result.task_type != 'regression':
            return None, "Predictions visualization is for regression tasks."

        try:
            X_test = pipeline_data["X_test"]
            y_test = pipeline_data["y_test"]
            best_name = result.best_model_name

            if not best_name:
                return None, "No best model found."

            results = pipeline_data.get("results", {})
            if best_name in results and results[best_name].is_valid:
                model = pipeline_data["results"][best_name].estimator
                model.fit(pipeline_data["X_train"], pipeline_data["y_train"])
                y_pred = model.predict(X_test)

                # Limit to 500 points for browser
                n = min(500, len(y_test))
                actual = y_test.values[:n].tolist()
                predicted = y_pred[:n].tolist()

                return {
                    "actual": actual,
                    "predicted": predicted,
                    "n_points": n,
                    "model_name": best_name,
                }, None

            return None, "Best model not available."
        except Exception as e:
            return None, f"Failed to get predictions: {str(e)}"

    @classmethod
    def get_feature_importance(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get feature importance for tree-based models."""
        key = cls._cache_key(user_id, dataset_id)
        pipeline_data = cls._pipelines.get(key)
        result = cls._results.get(key)

        if not pipeline_data or not result:
            return None, "No results found."

        best_name = result.best_model_name
        if not best_name:
            return None, "No best model found."

        # Check if model supports feature importance
        tree_models = {'Random Forest', 'Decision Tree', 'Gradient Boosting', 'XGBoost', 'LightGBM'}
        base_name = best_name.replace(' (Tuned)', '')
        if base_name not in tree_models and best_name not in tree_models:
            return {
                "available": False,
                "message": f"Feature importance is not available for {best_name}. It is supported for: {', '.join(sorted(tree_models))}.",
            }, None

        try:
            feature_names = pipeline_data.get("feature_names_out", [])
            if not feature_names:
                return None, "Feature names not available."

            X_train = pipeline_data["X_train"]
            y_train = pipeline_data["y_train"]
            model = pipeline_data["results"][best_name].estimator
            model.fit(X_train, y_train)

            if hasattr(model, 'feature_importances_'):
                importances = model.feature_importances_
                # Pair and sort
                pairs = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
                return {
                    "available": True,
                    "model_name": best_name,
                    "features": [{"name": n, "importance": round(float(imp), 4)} for n, imp in pairs],
                }, None
            else:
                return {"available": False, "message": f"{best_name} does not provide feature importances."}, None
        except Exception as e:
            return None, f"Failed to get feature importance: {str(e)}"

    # ── Model Saving ───────────────────────────────────────────────

    @classmethod
    def save_model(cls, user_id: int, dataset_id: int, model_name: Optional[str] = None,
                  custom_name: Optional[str] = None, description: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """Save a trained model to database and disk."""
        key = cls._cache_key(user_id, dataset_id)
        pipeline_data = cls._pipelines.get(key)
        config = cls._configs.get(key)
        result = cls._results.get(key)

        if not pipeline_data or not config or not result:
            return None, "No trained model to save. Train models first."

        if result.task_type == 'clustering':
            return None, "Saving clustering models is not yet supported."

        # Determine which model to save
        if not model_name:
            model_name = result.best_model_name
        if not model_name:
            return None, "No model specified to save."

        results = pipeline_data.get("results", {})
        if model_name not in results or not results[model_name].is_valid:
            return None, f"Model '{model_name}' is not available or failed during training."

        try:
            os.makedirs(cls.MODEL_STORAGE_DIR, exist_ok=True)

            # Check for existing versions
            db = get_session()
            existing = db.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.dataset_id == dataset_id,
                ModelDB.algorithm == model_name,
                ModelDB.is_active == True,
            ).order_by(ModelDB.version.desc()).first()

            version = (existing.version + 1) if existing else 1

            # Deactivate previous versions of same model (single UPDATE, not N+1)
            db.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.dataset_id == dataset_id,
                ModelDB.algorithm == model_name,
                ModelDB.is_active == True,
            ).update({"is_active": False})

            # Refit model on full training data
            base_name = model_name.replace(' (Tuned)', '')
            mr = results[model_name]
            safe_params = {k: v for k, v in mr.params.items() if k != 'random_state'}
            try:
                model = build_model(result.task_type, base_name, safe_params, random_state=config.random_state)
            except Exception:
                model = build_model(result.task_type, base_name, {}, random_state=config.random_state)
            model.fit(pipeline_data["X_train"], pipeline_data["y_train"])

            # Serialize
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            safe_algo = model_name.lower().replace(' ', '_').replace('(', '').replace(')', '')
            model_filename = f"{safe_algo}_v{version}_{timestamp}.joblib"
            model_filepath = os.path.join(cls.MODEL_STORAGE_DIR, model_filename)

            bundle = {
                'model': model,
                'preprocessor': pipeline_data["preprocessor"],
                'model_name': model_name,
                'task_type': result.task_type,
                'feature_columns': pipeline_data["feature_cols"],
                'target_column': config.target_column,
                'feature_names_out': pipeline_data.get("feature_names_out", []),
                'label_encoder_classes': pipeline_data.get("label_encoder_classes"),
                'metrics': mr.test_metrics,
                'params': dict(mr.params),
                'random_state': config.random_state,
            }
            import joblib
            joblib.dump(bundle, model_filepath)

            # Get metrics
            display_name = custom_name or f"{model_name} v{version}"
            primary_metric = config.primary_metric or ('accuracy' if result.task_type == 'classification' else 'r2')
            primary_score = mr.test_metrics.get(primary_metric, mr.test_metrics.get('accuracy', mr.test_metrics.get('r2', 0)))

            # Compute CV score
            cv_mean = mr.cv_result.mean_score if mr.cv_result else None
            cv_std = mr.cv_result.std_score if mr.cv_result else None

            # Determine CV strategy string
            cv_strategy = config.cv_strategy
            if cv_strategy == 'auto':
                cv_strategy = 'stratified' if result.task_type == 'classification' else 'kfold'

            # Save to database
            model_record = ModelDB(
                user_id=user_id,
                dataset_id=dataset_id,
                model_name=display_name,
                algorithm=model_name,
                problem_type=result.task_type,
                target_column=config.target_column,
                features=json.dumps(pipeline_data["feature_cols"]),
                metrics=json.dumps({k: round(v, 6) for k, v in mr.test_metrics.items()}),
                hyperparameters=json.dumps({k: _serialize_val(v) for k, v in mr.params.items()}),
                pipeline_config=json.dumps({
                    "scaling": config.scaling,
                    "encoding": config.encoding,
                    "imputation": config.imputation,
                    "test_size": config.test_size,
                    "random_state": config.random_state,
                    "n_features_after_encoding": pipeline_data.get("X_train").shape[1] if pipeline_data.get("X_train") is not None else 0,
                }),
                version=version,
                model_path=model_filepath,
                model_format='joblib',
                experiment_config=json.dumps(_config_to_dict(config)),
                primary_metric=primary_metric,
                primary_score=round(float(primary_score), 6),
                cv_strategy=cv_strategy,
                cv_score=round(float(cv_mean), 6) if cv_mean is not None else None,
                cv_std=round(float(cv_std), 6) if cv_std is not None else None,
                random_state=config.random_state,
                test_size=config.test_size,
                train_rows=result.train_rows,
                test_rows=result.test_rows,
                description=description,
            )
            model_record.is_active = True
            db.add(model_record)
            db.commit()
            db.refresh(model_record)

            return {
                "saved": True,
                "model_id": model_record.id,
                "model_name": display_name,
                "algorithm": model_name,
                "version": version,
                "path": model_filepath,
            }, None

        except Exception as e:
            db.rollback()
            traceback.print_exc()
            return None, f"Failed to save model: {str(e)}"
        finally:
            db.close()

    # ── Model Management ───────────────────────────────────────────

    @classmethod
    def list_models(cls, user_id: int) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List all saved models for a user."""
        db = get_session()
        try:
            models = db.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.is_active == True,
            ).order_by(ModelDB.created_at.desc()).all()

            # Batch-load all dataset names in a single query (eliminates N+1)
            dataset_ids = {m.dataset_id for m in models if m.dataset_id}
            dataset_names = {}
            if dataset_ids:
                for ds in db.query(DatasetDB.id, DatasetDB.name).filter(DatasetDB.id.in_(dataset_ids)).all():
                    dataset_names[ds.id] = ds.name

            result = []
            for m in models:
                dataset_name = dataset_names.get(m.dataset_id)

                entry = {
                    "id": m.id,
                    "model_name": m.model_name,
                    "algorithm": m.algorithm,
                    "problem_type": m.problem_type,
                    "dataset_name": dataset_name,
                    "dataset_id": m.dataset_id,
                    "primary_metric": m.primary_metric,
                    "primary_score": round(m.primary_score, 4) if m.primary_score else None,
                    "version": m.version,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "description": m.description,
                }
                result.append(entry)

            return result, None
        except Exception as e:
            return None, f"Failed to list models: {str(e)}"
        finally:
            db.close()

    @classmethod
    def get_model_detail(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Get detailed model information."""
        db = get_session()
        try:
            model = db.query(ModelDB).filter(
                ModelDB.id == model_id,
                ModelDB.user_id == user_id,
            ).first()

            if not model:
                return None, "Model not found."

            domain = model.to_domain()
            result = {
                "id": domain.id,
                "model_name": domain.model_name,
                "algorithm": domain.algorithm,
                "problem_type": domain.problem_type,
                "target_column": domain.target_column,
                "features": domain.features,
                "metrics": domain.metrics,
                "hyperparameters": domain.hyperparameters,
                "pipeline_config": domain.pipeline_config,
                "version": domain.version,
                "primary_metric": domain.primary_metric,
                "primary_score": round(domain.primary_score, 4) if domain.primary_score else None,
                "cv_strategy": domain.cv_strategy,
                "cv_score": round(domain.cv_score, 4) if domain.cv_score else None,
                "cv_std": round(domain.cv_std, 4) if domain.cv_std else None,
                "random_state": domain.random_state,
                "test_size": domain.test_size,
                "train_rows": domain.train_rows,
                "test_rows": domain.test_rows,
                "description": domain.description,
                "created_at": domain.created_at.isoformat() if domain.created_at else None,
                "updated_at": domain.updated_at.isoformat() if domain.updated_at else None,
            }

            # Dataset info
            if domain.dataset_id:
                dataset = db.query(DatasetDB).filter(DatasetDB.id == domain.dataset_id).first()
                if dataset:
                    result["dataset_name"] = dataset.name

            return result, None
        except Exception as e:
            return None, f"Failed to get model detail: {str(e)}"
        finally:
            db.close()

    @classmethod
    def download_model(cls, user_id: int, model_id: int) -> Tuple[Optional[str], Optional[str]]:
        """Return the file path for model download."""
        db = get_session()
        try:
            model = db.query(ModelDB).filter(
                ModelDB.id == model_id,
                ModelDB.user_id == user_id,
            ).first()

            if not model:
                return None, "Model not found."

            if not model.model_path or not os.path.exists(model.model_path):
                return None, "Model file not found on disk."

            return model.model_path, None
        except Exception as e:
            return None, f"Failed to get model path: {str(e)}"
        finally:
            db.close()

    @classmethod
    def delete_model(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Delete a saved model."""
        db = get_session()
        try:
            model = db.query(ModelDB).filter(
                ModelDB.id == model_id,
                ModelDB.user_id == user_id,
            ).first()

            if not model:
                return None, "Model not found."

            # Delete file
            if model.model_path and os.path.exists(model.model_path):
                try:
                    os.remove(model.model_path)
                except Exception as _e:
                    import logging
                    logging.getLogger(__name__).warning(f'Ignored exception: {_e}', exc_info=True)

            db.delete(model)
            db.commit()

            return {"deleted": True, "model_id": model_id, "model_name": model.model_name}, None
        except Exception as e:
            return None, f"Failed to delete model: {str(e)}"
        finally:
            db.close()

    # ── Cache Management ───────────────────────────────────────────

    @classmethod
    def clear_cache(cls, user_id: int, dataset_id: int):
        """Clear cached pipeline and results."""
        key = cls._cache_key(user_id, dataset_id)
        cls._pipelines.pop(key, None)
        cls._configs.pop(key, None)
        cls._results.pop(key, None)
        cls._training_locks.pop(key, None)

    @classmethod
    def get_available_algorithms(cls, task_type: str) -> Dict:
        """Get available algorithms for a task type with rich metadata."""
        # Algorithm metadata for display
        algo_meta = {
            'Extra Trees': {'description': 'Randomized tree ensemble.', 'speed': 'Medium'},
            'Lasso': {'description': 'Linear regression with L1 regularization.', 'speed': 'Fast'},
            'Elastic Net': {'description': 'Linear regression with combined L1 and L2 regularization.', 'speed': 'Fast'},
            'K-Means': {'description': 'Groups rows around cluster centers.', 'speed': 'Fast'},
            'Mini-Batch K-Means': {'description': 'K-Means using small batches for speed.', 'speed': 'Fast'},
            'Birch': {'description': 'Builds compact subclusters before grouping them.', 'speed': 'Fast'},
            'Agglomerative': {'description': 'Merges similar groups into a hierarchy.', 'speed': 'Medium'},
            'DBSCAN': {'description': 'Finds dense groups and marks isolated rows as noise.', 'speed': 'Medium'},
            'Random Forest': {
                'display_name': 'Random Forest',
                'description': 'Ensemble of decision trees, robust to overfitting.',
                'speed': 'Medium',
                'default': True,
            },
            'Decision Tree': {
                'display_name': 'Decision Tree',
                'description': 'Interpretable tree-based model.',
                'speed': 'Fast',
                'default': True,
            },
            'Logistic Regression': {
                'display_name': 'Logistic Regression',
                'description': 'Fast linear classifier, great baseline.',
                'speed': 'Fast',
                'default': True,
            },
            'Linear Regression': {
                'display_name': 'Linear Regression',
                'description': 'Fast linear model, great baseline for regression.',
                'speed': 'Fast',
                'default': True,
            },
            'Ridge Regression': {
                'display_name': 'Ridge Regression',
                'description': 'Regularised linear regression (L2 penalty).',
                'speed': 'Fast',
                'default': False,
            },
            'Gradient Boosting': {
                'display_name': 'Gradient Boosting',
                'description': 'Sequential boosting, high accuracy.',
                'speed': 'Medium',
                'default': True,
            },
            'SVM': {
                'display_name': 'Support Vector Machine',
                'description': 'Effective in high-dimensional spaces.',
                'speed': 'Slow',
                'default': False,
            },
            'K-Nearest Neighbors': {
                'display_name': 'K-Nearest Neighbors',
                'description': 'Instance-based, no training phase.',
                'speed': 'Fast',
                'default': False,
            },
            'Naive Bayes': {
                'display_name': 'Naive Bayes',
                'description': 'Probabilistic, very fast for text/classification.',
                'speed': 'Fast',
                'default': False,
            },
            'XGBoost': {
                'display_name': 'XGBoost',
                'description': 'Optimised gradient boosting, very accurate.',
                'speed': 'Medium',
                'default': True,
            },
            'LightGBM': {
                'display_name': 'LightGBM',
                'description': 'Fast gradient boosting, memory efficient.',
                'speed': 'Fast',
                'default': True,
            },
        }

        try:
            models = get_model_zoo(task_type, fast_mode=False)
        except Exception:
            models = {}

        algorithms = []
        for name in models:
            meta = algo_meta.get(name, {})
            algorithms.append({
                'name': name,
                'display_name': meta.get('display_name', name),
                'description': meta.get('description', ''),
                'speed': meta.get('speed', 'Medium'),
                'default': meta.get('default', False),
            })

        return {
            "algorithms": algorithms,
            "task_type": task_type,
            "recommendations": [],
        }

    @classmethod
    def get_recommended_algorithms(cls, user_id: int, dataset_id: int, target_column: Optional[str],
                                   problem_type: Optional[str]) -> Tuple[Optional[Dict], Optional[str]]:
        """Recommend algorithms based on dataset characteristics."""
        df, err = cls.load_dataset(user_id, dataset_id)
        if err:
            return None, err

        n_rows, n_cols = df.shape
        n_features = n_cols - 1 if target_column else n_cols

        rec_names = []
        if problem_type == 'classification':
            rec_names = ['Random Forest', 'Gradient Boosting', 'Logistic Regression']
            if n_rows < 1000:
                rec_names.insert(0, 'Decision Tree')
            if XGBOOST_AVAILABLE:
                rec_names.append('XGBoost')
            if LIGHTGBM_AVAILABLE:
                rec_names.append('LightGBM')
        elif problem_type == 'regression':
            rec_names = ['Random Forest', 'Gradient Boosting', 'Linear Regression', 'Ridge Regression']
            if n_rows < 1000:
                rec_names.insert(0, 'Decision Tree')
            if XGBOOST_AVAILABLE:
                rec_names.append('XGBoost')
            if LIGHTGBM_AVAILABLE:
                rec_names.append('LightGBM')

        reasons = [
            f"Dataset: {n_rows} rows × {n_features} features.",
            "Tree-based ensembles typically perform best on tabular data.",
        ]
        if n_rows < 500:
            reasons.append("Small dataset — simpler models reduce overfitting risk.")

        # Build full algorithm list
        base_result = cls.get_available_algorithms(problem_type or 'classification')
        algorithms = base_result['algorithms']

        # Mark recommendations with reason
        recommendations = []
        for algo in algorithms:
            if algo['name'] in rec_names:
                rec = dict(algo)
                rec['reason'] = f"Recommended for {problem_type} on this dataset size."
                recommendations.append(rec)

        return {
            "algorithms": algorithms,
            "recommendations": recommendations,
            "reasons": reasons,
            "all_available": [a['name'] for a in algorithms],
        }, None

    @classmethod
    def get_roc_curve(cls, user_id: int, dataset_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Compute ROC curve data for binary classification."""
        from sklearn.metrics import roc_curve as sk_roc_curve, auc

        key = cls._cache_key(user_id, dataset_id)
        pipeline_data = cls._pipelines.get(key)
        result = cls._results.get(key)

        if not pipeline_data or not result:
            return None, "No results found. Train models first."

        if result.task_type != 'classification':
            return None, "ROC curve is only available for classification tasks."

        best_name = result.best_model_name
        if not best_name:
            return None, "No best model found."

        X_train = pipeline_data['X_train']
        y_train = pipeline_data['y_train']
        X_test = pipeline_data['X_test']
        y_test = pipeline_data['y_test']

        n_classes = int(y_train.nunique()) if hasattr(y_train, 'nunique') else len(np.unique(y_train))
        if n_classes != 2:
            return {
                'available': False,
                'message': f'ROC curve is only available for binary classification. This problem has {n_classes} classes.',
            }, None

        try:
            base_name = best_name.replace(' (Tuned)', '')
            model = pipeline_data["results"][best_name].estimator
            model.fit(X_train, y_train)

            if not hasattr(model, 'predict_proba'):
                return {'available': False, 'message': f'{best_name} does not support probability estimates for ROC curve.'}, None

            y_score = model.predict_proba(X_test)[:, 1]
            fpr, tpr, _ = sk_roc_curve(y_test, y_score)
            roc_auc = float(auc(fpr, tpr))

            # Downsample to max 200 points for browser efficiency
            n_pts = len(fpr)
            if n_pts > 200:
                step = n_pts // 200
                fpr = fpr[::step].tolist()
                tpr = tpr[::step].tolist()
            else:
                fpr = fpr.tolist()
                tpr = tpr.tolist()

            return {
                'available': True,
                'fpr': fpr,
                'tpr': tpr,
                'auc': round(roc_auc, 4),
                'model_name': best_name,
            }, None
        except Exception as e:
            return None, f"Failed to compute ROC curve: {str(e)}"


# ── Helper Functions ──────────────────────────────────────────────

def _config_to_dict(config: MLWorkflowConfig) -> Dict:
    """Convert MLWorkflowConfig to dict."""
    return {
        "dataset_id": config.dataset_id,
        "target_column": config.target_column,
        "feature_columns": config.feature_columns,
        "problem_type": config.problem_type,
        "test_size": config.test_size,
        "random_state": config.random_state,
        "cv_folds": config.cv_folds,
        "cv_strategy": config.cv_strategy,
        "primary_metric": config.primary_metric,
        "scaling": config.scaling,
        "encoding": config.encoding,
        "imputation": config.imputation,
        "class_weights": config.class_weights,
        "selected_algorithms": config.selected_algorithms,
        "auto_mode": config.auto_mode,
        "optimization_level": config.optimization_level,
        "optimization_iterations": config.optimization_iterations,
        "optimization_model": config.optimization_model,
        "experiment_config": config.experiment_config,
    }


def _result_to_dict(result: MLWorkflowResult) -> Dict:
    """Convert MLWorkflowResult to dict."""
    return {
        "task_type": result.task_type,
        "problem_subtype": result.problem_subtype,
        "features_used": result.features_used,
        "categorical_features": result.categorical_features,
        "numerical_features": result.numerical_features,
        "train_rows": result.train_rows,
        "test_rows": result.test_rows,
        "class_distribution": result.class_distribution,
        "warnings": result.warnings,
        "preprocessing_info": result.preprocessing_info,
        "model_results": result.model_results,
        "leaderboard": result.leaderboard,
        "tuning_result": result.tuning_result,
        "best_model_name": result.best_model_name,
        "training_time": result.training_time,
    }


def _serialize_val(v):
    """Serialize a value for JSON storage."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, pd.Timestamp):
        return v.isoformat()
    if isinstance(v, np.datetime64):
        return pd.Timestamp(v).isoformat()
    if isinstance(v, (list, tuple)):
        return [_serialize_val(item) for item in v]
    if isinstance(v, dict):
        return {k: _serialize_val(val) for k, val in v.items()}
    return v



