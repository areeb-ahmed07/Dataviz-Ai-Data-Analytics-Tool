"""
Service: Explainable AI (XAI) — Phase 8

Full implementation of SHAP, LIME, Feature Importance,
Permutation Importance, Prediction Explanation, Partial Dependence,
Cluster Profiles, Importance Comparison, and Model Limitations.

All methods follow a (result, error) tuple return pattern.
Results are JSON-serialisable dicts ready for Flask jsonify.
"""

import os
import traceback
import uuid
import time
import json
import threading
import warnings
from typing import Dict, Any, Tuple, Optional, List

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

import shap
from lime.lime_tabular import LimeTabularExplainer
from sklearn.inspection import permutation_importance

from auth.database import ModelDB, DatasetDB, get_session


# ── In-memory job store for async-style polling ─────────────────────

class _JobStore:
    _jobs: Dict[str, Dict] = {}
    _lock = threading.Lock()

    @classmethod
    def create(cls, job_id: str):
        with cls._lock:
            cls._jobs[job_id] = {"status": "running", "result": None, "error": None}

    @classmethod
    def finish(cls, job_id: str, result: Any):
        with cls._lock:
            entry = cls._jobs.get(job_id)
            if entry:
                entry["status"] = "done"
                entry["result"] = result

    @classmethod
    def fail(cls, job_id: str, error: str):
        with cls._lock:
            entry = cls._jobs.get(job_id)
            if entry:
                entry["status"] = "error"
                entry["error"] = error

    @classmethod
    def get(cls, job_id: str) -> Optional[Dict]:
        with cls._lock:
            return cls._jobs.get(job_id)

    @classmethod
    def cleanup_old(cls, max_age_seconds: int = 600):
        now = time.time()
        with cls._lock:
            expired = [k for k, v in cls._jobs.items() if now - v.get("_created", now) > max_age_seconds]
            for k in expired:
                del cls._jobs[k]


def _serialize_numpy(obj):
    """Recursively convert numpy types to JSON-safe Python types."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _serialize_numpy(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize_numpy(item) for item in obj]
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


class XAIService:
    """Fully-functional Explainable AI service."""

    # ── Model / Data Loading ───────────────────────────────────────

    @classmethod
    def _load_model_bundle(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        """Load the joblib bundle from disk and validate ownership."""
        db = get_session()
        try:
            model_db = db.query(ModelDB).filter(
                ModelDB.id == model_id,
                ModelDB.user_id == user_id,
            ).first()
            if not model_db:
                return None, "Model not found."
            if not model_db.model_path or not os.path.exists(model_db.model_path):
                return None, "Model file not found on disk."

            import joblib
            bundle = joblib.load(model_db.model_path)
            bundle["_model_db"] = model_db
            return bundle, None
        except Exception as e:
            return None, f"Failed to load model: {str(e)}"
        finally:
            db.close()

    @classmethod
    def _load_dataset(cls, dataset_id: int) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        """Load the original dataset from disk."""
        db = get_session()
        try:
            ds = db.query(DatasetDB).filter(DatasetDB.id == dataset_id).first()
            if not ds or not ds.storage_path or not os.path.exists(ds.storage_path):
                return None, "Dataset not found."
            df = pd.read_csv(ds.storage_path)
            return df, None
        except Exception as e:
            return None, f"Failed to load dataset: {str(e)}"
        finally:
            db.close()

    @classmethod
    def _prepare_data(cls, bundle: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Reconstruct X_train from the original dataset using the saved preprocessor.
        Returns a dict with: model, preprocessor, X_train, y_train, feature_names,
        feature_names_out, task_type, target_column, label_encoder_classes, model_db.
        """
        model_db = bundle.get("_model_db")
        if not model_db:
            return None, "No model database record."

        dataset_id = model_db.dataset_id
        if not dataset_id:
            return None, "Model is not associated with a dataset."

        df, err = cls._load_dataset(dataset_id)
        if err:
            return None, err

        task_type = bundle.get("task_type", model_db.problem_type)
        target_column = bundle.get("target_column", model_db.target_column)
        feature_columns = bundle.get("feature_columns", [])

        if not target_column:
            return None, "No target column recorded for this model."
        if target_column not in df.columns:
            return None, f"Target column '{target_column}' not found in dataset."

        # Determine feature columns if not saved
        if not feature_columns:
            feature_columns = [c for c in df.columns if c != target_column]

        # Filter to known columns only
        available_features = [c for c in feature_columns if c in df.columns]
        if not available_features:
            return None, "No feature columns found in dataset."

        # Split features / target
        X = df[available_features].copy()
        y = df[target_column].copy()

        # Drop rows with missing target
        mask = y.notna()
        X = X.loc[mask].reset_index(drop=True)
        y = y.loc[mask].reset_index(drop=True)

        # Apply the saved preprocessor
        preprocessor = bundle.get("preprocessor")
        if preprocessor is not None:
            try:
                X_transformed = preprocessor.transform(X)
                if hasattr(X_transformed, "toarray"):
                    X_transformed = X_transformed.toarray()
            except Exception:
                # Fallback: try fitting on this data (should not happen normally)
                X_transformed = preprocessor.fit_transform(X)
                if hasattr(X_transformed, "toarray"):
                    X_transformed = X_transformed.toarray()
        else:
            X_transformed = X.values

        # Get feature names after encoding
        feature_names_out = bundle.get("feature_names_out", list(available_features))
        if len(feature_names_out) != X_transformed.shape[1]:
            feature_names_out = [f"Feature_{i}" for i in range(X_transformed.shape[1])]

        model = bundle["model"]
        label_encoder_classes = bundle.get("label_encoder_classes")

        return {
            "model": model,
            "preprocessor": preprocessor,
            "X_train": X_transformed,
            "y_train": y.values,
            "X_train_raw": X,
            "feature_columns": available_features,
            "feature_names": feature_names_out,
            "task_type": task_type,
            "target_column": target_column,
            "label_encoder_classes": label_encoder_classes,
            "model_db": model_db,
            "n_samples": len(y),
            "n_features": X_transformed.shape[1],
        }, None

    # ── Job System ──────────────────────────────────────────────────

    @classmethod
    def start_xai_job(cls, func, user_id: int, model_id: int, **kwargs) -> Dict[str, str]:
        """Launch a background XAI computation. Returns {job_id, status}."""
        job_id = str(uuid.uuid4())[:12]
        _JobStore.create(job_id)

        def _worker():
            try:
                result, error = func(user_id, model_id, **kwargs)
                if error:
                    _JobStore.fail(job_id, error)
                else:
                    _JobStore.finish(job_id, _serialize_numpy(result))
            except Exception as e:
                _JobStore.fail(job_id, str(e))

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return {"job_id": job_id, "status": "running"}

    @classmethod
    def get_job_status(cls, job_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        entry = _JobStore.get(job_id)
        if not entry:
            return None, "Job not found."
        _JobStore.cleanup_old()
        if entry["status"] == "done":
            return {"status": "done", "result": entry["result"]}, None
        elif entry["status"] == "error":
            return {"status": "error", "error": entry["error"]}, None
        else:
            return {"status": "running"}, None

    # ── List Explainable Models ─────────────────────────────────────

    @classmethod
    def list_explainable_models(cls, user_id: int) -> Tuple[List, Optional[str]]:
        db = get_session()
        try:
            models = db.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.is_active == True,
            ).order_by(ModelDB.created_at.desc()).all()

            result = []
            for m in models:
                dataset_name = None
                if m.dataset_id:
                    ds = db.query(DatasetDB).filter(DatasetDB.id == m.dataset_id).first()
                    dataset_name = ds.name if ds else None

                metrics = {}
                if m.metrics:
                    try:
                        metrics = json.loads(m.metrics)
                    except Exception:
                        pass

                supported_methods = ["native", "permutation", "shap", "lime"]
                if m.problem_type == "clustering":
                    supported_methods = ["native", "permutation"]

                result.append({
                    "id": m.id,
                    "model_name": m.model_name,
                    "algorithm": m.algorithm,
                    "problem_type": m.problem_type,
                    "dataset_name": dataset_name,
                    "dataset_id": m.dataset_id,
                    "score": round(m.primary_score, 4) if m.primary_score else None,
                    "metrics": metrics,
                    "supported_methods": supported_methods,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "description": m.description,
                })

            return result, None
        except Exception as e:
            return [], f"Failed to list models: {str(e)}"
        finally:
            db.close()

    # ── Model Summary ───────────────────────────────────────────────

    @classmethod
    def get_model_summary(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        db = get_session()
        try:
            model_db = db.query(ModelDB).filter(
                ModelDB.id == model_id,
                ModelDB.user_id == user_id,
            ).first()
            if not model_db:
                return None, "Model not found."

            metrics = {}
            if model_db.metrics:
                try:
                    metrics = json.loads(model_db.metrics)
                except Exception:
                    pass

            features = []
            if model_db.features:
                try:
                    features = json.loads(model_db.features)
                except Exception:
                    pass

            # Load bundle to get actual feature count
            n_features = len(features)
            n_samples = 0
            if model_db.train_rows:
                n_samples = model_db.train_rows + (model_db.test_rows or 0)

            supported_methods = ["native", "permutation", "shap", "lime"]
            if model_db.problem_type == "clustering":
                supported_methods = ["native", "permutation"]

            dataset_name = None
            if model_db.dataset_id:
                ds = db.query(DatasetDB).filter(DatasetDB.id == model_db.dataset_id).first()
                dataset_name = ds.name if ds else None

            return {
                "id": model_db.id,
                "model_name": model_db.model_name,
                "name": model_db.model_name,
                "algorithm": model_db.algorithm,
                "problem_type": model_db.problem_type,
                "target_column": model_db.target_column,
                "features": features,
                "n_features": n_features,
                "n_samples": n_samples,
                "total_rows": n_samples,
                "metrics": metrics,
                "score": round(model_db.primary_score, 4) if model_db.primary_score else None,
                "best_score": round(model_db.primary_score, 4) if model_db.primary_score else None,
                "supported_methods": supported_methods,
                "methods": supported_methods,
                "dataset_name": dataset_name,
                "primary_metric": model_db.primary_metric,
                "cv_score": round(model_db.cv_score, 4) if model_db.cv_score else None,
                "cv_std": round(model_db.cv_std, 4) if model_db.cv_std else None,
                "train_rows": model_db.train_rows,
                "test_rows": model_db.test_rows,
                "version": model_db.version,
                "description": model_db.description,
                "created_at": model_db.created_at.isoformat() if model_db.created_at else None,
            }, None
        except Exception as e:
            return None, f"Failed to get model summary: {str(e)}"
        finally:
            db.close()

    # ── Overview (top features + performance for workspace) ──────────

    @classmethod
    def get_overview(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]
        model_db = data["model_db"]

        # Get native feature importance
        top_features = []
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            indices = np.argsort(imp)[::-1][:5]
            for idx in indices:
                fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
                top_features.append({"name": fname, "importance": float(imp[idx]), "value": float(imp[idx])})
        elif hasattr(model, "coef_"):
            coef = np.abs(model.coef_).flatten()
            if coef.ndim == 0:
                coef = coef.reshape(1)
            indices = np.argsort(coef)[::-1][:5]
            for idx in indices:
                fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
                top_features.append({"name": fname, "importance": float(coef[idx]), "value": float(coef[idx])})

        # Metrics
        metrics = {}
        if model_db.metrics:
            try:
                metrics = json.loads(model_db.metrics)
            except Exception:
                pass

        # Warnings
        warnings_list = []
        if X_train.shape[0] > 10000:
            warnings_list.append("Large dataset detected. SHAP/LIME computations may be slow on the full dataset.")
        if task_type == "clustering":
            warnings_list.append("Clustering models have limited explanation support. SHAP and LIME are not available for unsupervised models.")

        return {
            "top_features": top_features,
            "performance": metrics,
            "metrics": metrics,
            "n_samples": data["n_samples"],
            "n_features": data["n_features"],
            "warnings": warnings_list,
            "task_type": task_type,
            "algorithm": model_db.algorithm,
        }, None

    # ── Native Feature Importance ───────────────────────────────────

    @classmethod
    def get_feature_importance(cls, user_id: int, model_id: int, top_n: int = 20) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        feature_names = data["feature_names"]

        features = []
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            indices = np.argsort(imp)[::-1][:top_n]
            for idx in indices:
                fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
                features.append({"name": fname, "importance": float(imp[idx]), "value": float(imp[idx])})
        elif hasattr(model, "coef_"):
            coef = np.abs(model.coef_).flatten()
            if coef.ndim == 0:
                coef = coef.reshape(1)
            indices = np.argsort(coef)[::-1][:top_n]
            for idx in indices:
                fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
                features.append({"name": fname, "importance": float(coef[idx]), "value": float(coef[idx])})
        else:
            return {"features": [], "available": False, "message": "Native feature importance is not available for this model type."}, None

        return {"features": features, "available": True}, None

    # ── Permutation Importance ──────────────────────────────────────

    @classmethod
    def get_permutation_importance(cls, user_id: int, model_id: int, top_n: int = 20,
                                     sample_size: Optional[int] = None, n_repeats: int = 5) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        y_train = data["y_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        if task_type == "clustering":
            return None, "Permutation importance is not available for clustering models."

        X_sample = X_train[:sample_size] if sample_size and sample_size < len(X_train) else X_train
        y_sample = y_train[:sample_size] if sample_size and sample_size < len(y_train) else y_train

        scoring = "accuracy" if task_type == "classification" else "r2"

        try:
            perm_result = permutation_importance(
                model, X_sample, y_sample,
                n_repeats=n_repeats,
                scoring=scoring,
                random_state=42,
                n_jobs=1,
            )
        except Exception as e:
            return None, f"Permutation importance computation failed: {str(e)}"

        indices = np.argsort(perm_result.importances_mean)[::-1][:top_n]
        features = []
        for idx in indices:
            fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
            features.append({
                "name": fname,
                "importance": float(perm_result.importances_mean[idx]),
                "value": float(perm_result.importances_mean[idx]),
                "std": float(perm_result.importances_std[idx]),
            })

        return {"features": features, "available": True}, None

    # ── SHAP Global ─────────────────────────────────────────────────

    @classmethod
    def get_shap_global(cls, user_id: int, model_id: int, top_n: int = 20,
                          sample_size: Optional[int] = None) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        if task_type == "clustering":
            return None, "SHAP is not available for clustering models."

        X_sample = X_train[:sample_size] if sample_size and sample_size < len(X_train) else X_train

        try:
            explainer = cls._create_shap_explainer(model, X_sample)
            shap_values = explainer.shap_values(X_sample)
        except Exception as e:
            return None, f"SHAP computation failed: {str(e)}"

        # Handle multi-class: take mean absolute across classes
        if isinstance(shap_values, list):
            sv_array = np.abs(np.concatenate(shap_values, axis=1))
        elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
            sv_array = np.abs(shap_values).mean(axis=2)
        else:
            sv_array = np.abs(shap_values)

        mean_abs = np.mean(sv_array, axis=0)
        indices = np.argsort(mean_abs)[::-1][:top_n]

        features = []
        for idx in indices:
            fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
            features.append({"name": fname, "importance": float(mean_abs[idx]), "value": float(mean_abs[idx])})

        return {"features": features, "available": True}, None

    # ── SHAP Summary (Beeswarm Data) ────────────────────────────────

    @classmethod
    def get_shap_summary_data(cls, user_id: int, model_id: int, max_features: int = 20,
                                sample_size: Optional[int] = None) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        if task_type == "clustering":
            return None, "SHAP is not available for clustering models."

        X_sample = X_train[:sample_size] if sample_size and sample_size < len(X_train) else X_train

        try:
            explainer = cls._create_shap_explainer(model, X_sample)
            shap_values = explainer.shap_values(X_sample)
        except Exception as e:
            return None, f"SHAP computation failed: {str(e)}"

        # Normalise to 2D array
        if isinstance(shap_values, list):
            sv_2d = np.concatenate(shap_values, axis=1)
        elif shap_values.ndim == 3:
            sv_2d = shap_values.reshape(shap_values.shape[0], -1)
        else:
            sv_2d = shap_values

        # Mean absolute SHAP to select top features
        mean_abs = np.mean(np.abs(sv_2d), axis=0)
        top_indices = np.argsort(mean_abs)[::-1][:max_features]

        # For each top feature, collect (shap_value, feature_value) pairs
        features_list = []
        values_list = []
        feature_values_list = []

        for idx in top_indices:
            fname = feature_names[idx] if idx < len(feature_names) else f"Feature_{idx}"
            features_list.append(fname)
            values_list.append(sv_2d[:, idx].tolist())
            # Normalise feature values to [-1, 1] for color coding
            col = X_sample[:, idx]
            col_min, col_max = col.min(), col.max()
            if col_max - col_min > 1e-10:
                normalised = 2 * (col - col_min) / (col_max - col_min) - 1
            else:
                normalised = np.zeros_like(col)
            feature_values_list.append(normalised.tolist())

        return {
            "features": features_list,
            "values": values_list,
            "feature_values": feature_values_list,
            "available": True,
        }, None

    # ── SHAP Dependence Plot Data ───────────────────────────────────

    @classmethod
    def get_shap_dependence(cls, user_id: int, model_id: int, feature_index: int = 0,
                              sample_size: Optional[int] = None) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        if task_type == "clustering":
            return None, "SHAP is not available for clustering models."

        if feature_index < 0 or feature_index >= X_train.shape[1]:
            return None, f"Feature index {feature_index} is out of range (0-{X_train.shape[1]-1})."

        X_sample = X_train[:sample_size] if sample_size and sample_size < len(X_train) else X_train

        try:
            explainer = cls._create_shap_explainer(model, X_sample)
            shap_values = explainer.shap_values(X_sample)
        except Exception as e:
            return None, f"SHAP computation failed: {str(e)}"

        # Normalise to 2D
        if isinstance(shap_values, list):
            sv_2d = np.concatenate(shap_values, axis=1)
        elif shap_values.ndim == 3:
            sv_2d = shap_values.reshape(shap_values.shape[0], -1)
        else:
            sv_2d = shap_values

        feature_name = feature_names[feature_index] if feature_index < len(feature_names) else f"Feature_{feature_index}"
        feature_vals = X_sample[:, feature_index]
        shap_vals = sv_2d[:, feature_index]

        # Downsample if too many points for browser
        n_pts = len(feature_vals)
        if n_pts > 2000:
            step = n_pts // 2000
            feature_vals = feature_vals[::step]
            shap_vals = shap_vals[::step]

        return {
            "feature_name": feature_name,
            "feature_index": feature_index,
            "feature_values": feature_vals.tolist(),
            "shap_values": shap_vals.tolist(),
            "available": True,
        }, None

    # ── SHAP Local ──────────────────────────────────────────────────

    @classmethod
    def get_shap_local(cls, user_id: int, model_id: int, row_index: int = 0) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        if task_type == "clustering":
            return None, "SHAP is not available for clustering models."

        if row_index < 0 or row_index >= len(X_train):
            return None, f"Row index {row_index} is out of range (0-{len(X_train)-1})."

        instance = X_train[row_index:row_index + 1]

        try:
            explainer = cls._create_shap_explainer(model, X_train)
            shap_values = explainer.shap_values(instance)
        except Exception as e:
            return None, f"SHAP computation failed: {str(e)}"

        # Get base value
        if hasattr(explainer, "expected_value"):
            base_value = explainer.expected_value
            if isinstance(base_value, (list, np.ndarray)):
                base_value = float(np.mean(base_value))
            else:
                base_value = float(base_value)
        else:
            base_value = float(np.mean(model.predict(X_train)))

        # Normalise shap_values for single instance
        if isinstance(shap_values, list):
            sv = np.concatenate(shap_values, axis=1)[0]
        elif shap_values.ndim == 3:
            sv = shap_values[0].flatten()
        else:
            sv = shap_values[0]

        features = []
        values = []
        for i in range(len(sv)):
            fname = feature_names[i] if i < len(feature_names) else f"Feature_{i}"
            features.append(fname)
            values.append(float(sv[i]))

        prediction = float(model.predict(instance)[0])
        if hasattr(model, "predict_proba") and task_type == "classification":
            try:
                proba = model.predict_proba(instance)[0]
                probabilities = {str(i): float(p) for i, p in enumerate(proba)}
                label_classes = data.get("label_encoder_classes")
                if label_classes is not None:
                    proba_dict = {}
                    for i, p in enumerate(proba):
                        cls_name = str(label_classes[i]) if i < len(label_classes) else str(i)
                        proba_dict[cls_name] = float(p)
                    probabilities = proba_dict
            except Exception:
                probabilities = {}
        else:
            probabilities = {}

        return {
            "features": features,
            "values": values,
            "base_value": base_value,
            "prediction": prediction,
            "probabilities": probabilities,
            "row_index": row_index,
            "available": True,
        }, None

    # ── LIME Local ──────────────────────────────────────────────────

    @classmethod
    def get_lime_local(cls, user_id: int, model_id: int, row_index: int = 0,
                          num_features: int = 10) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]
        label_classes = data.get("label_encoder_classes")

        if task_type == "clustering":
            return None, "LIME is not available for clustering models."

        if row_index < 0 or row_index >= len(X_train):
            return None, f"Row index {row_index} is out of range (0-{len(X_train)-1})."

        instance = X_train[row_index]
        mode = "classification" if task_type == "classification" else "regression"

        class_names = None
        if mode == "classification" and label_classes is not None:
            class_names = [str(c) for c in label_classes]

        try:
            predict_fn = model.predict_proba if hasattr(model, "predict_proba") and mode == "classification" else model.predict

            explainer = LimeTabularExplainer(
                X_train,
                feature_names=feature_names,
                class_names=class_names,
                mode=mode,
                random_state=42,
                discretize_continuous=True,
            )

            exp = explainer.explain_instance(instance, predict_fn, num_features=num_features)
        except Exception as e:
            return None, f"LIME computation failed: {str(e)}"

        # Extract LIME explanation data
        local_exp_list = exp.as_list()
        features = []
        values = []
        conditions = []
        for weight, condition in local_exp_list:
            features.append(str(condition))
            values.append(float(weight))
            conditions.append(str(condition))

        # Also get in tuple format for JS compatibility
        local_exp_tuples = [[float(w), str(c)] for w, c in local_exp_list]

        prediction = float(model.predict(instance.reshape(1, -1))[0])
        if hasattr(model, "predict_proba") and task_type == "classification":
            try:
                proba = model.predict_proba(instance.reshape(1, -1))[0]
                probabilities = {str(i): float(p) for i, p in enumerate(proba)}
                if label_classes is not None:
                    proba_dict = {}
                    for i, p in enumerate(proba):
                        cls_name = str(label_classes[i]) if i < len(label_classes) else str(i)
                        proba_dict[cls_name] = float(p)
                    probabilities = proba_dict
            except Exception:
                probabilities = {}
        else:
            probabilities = {}

        return {
            "features": features,
            "values": values,
            "local_exp": local_exp_tuples,
            "conditions": conditions,
            "prediction": prediction,
            "probabilities": probabilities,
            "row_index": row_index,
            "intercept": float(exp.intercept[0]) if hasattr(exp, "intercept") and exp.intercept is not None else 0.0,
            "score": float(exp.score) if hasattr(exp, "score") else None,
            "local_pred": float(exp.local_pred[0]) if hasattr(exp, "local_pred") and exp.local_pred is not None else None,
            "available": True,
        }, None

    # ── Prediction Explanation ──────────────────────────────────────

    @classmethod
    def get_prediction_explanation(cls, user_id: int, model_id: int, row_index: int = 0) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        y_train = data["y_train"]
        X_train_raw = data["X_train_raw"]
        feature_names = data["feature_names"]
        feature_columns = data["feature_columns"]
        task_type = data["task_type"]
        label_classes = data.get("label_encoder_classes")
        model_db = data["model_db"]

        if row_index < 0 or row_index >= len(X_train):
            return None, f"Row index {row_index} is out of range (0-{len(X_train)-1})."

        instance = X_train[row_index:row_index + 1]
        raw_row = X_train_raw.iloc[row_index]

        # Prediction
        prediction = float(model.predict(instance)[0])
        actual = float(y_train[row_index]) if row_index < len(y_train) else None

        # Probabilities
        probabilities = {}
        predicted_class = None
        if hasattr(model, "predict_proba") and task_type == "classification":
            try:
                proba = model.predict_proba(instance)[0]
                pred_idx = int(np.argmax(proba))
                if label_classes is not None and pred_idx < len(label_classes):
                    predicted_class = str(label_classes[pred_idx])
                else:
                    predicted_class = str(pred_idx)
                for i, p in enumerate(proba):
                    cls_name = str(label_classes[i]) if label_classes is not None and i < len(label_classes) else str(i)
                    probabilities[cls_name] = float(p)
            except Exception:
                probabilities = {}

        # SHAP local values for contributing factors
        contributors = []
        if task_type != "clustering":
            try:
                explainer = cls._create_shap_explainer(model, X_train)
                sv = explainer.shap_values(instance)

                if isinstance(sv, list):
                    sv_flat = np.concatenate(sv, axis=1)[0]
                elif sv.ndim == 3:
                    sv_flat = sv[0].flatten()
                else:
                    sv_flat = sv[0]

                for i in range(len(sv_flat)):
                    fname = feature_names[i] if i < len(feature_names) else f"Feature_{i}"
                    contributors.append({
                        "feature": fname,
                        "shap_value": float(sv_flat[i]),
                        "contribution": float(sv_flat[i]),
                    })

                contributors.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
            except Exception:
                contributors = []

        # Feature values for the observation
        feature_values = []
        for i, col in enumerate(feature_columns):
            if i < len(raw_row):
                val = raw_row.iloc[i]
                feature_values.append({
                    "feature": col,
                    "value": _serialize_numpy(val),
                })

        # Business-friendly explanation
        business_explanation = cls._generate_business_explanation(
            prediction, predicted_class, contributors, task_type, probabilities
        )

        # Model performance context
        metrics = {}
        if model_db.metrics:
            try:
                metrics = json.loads(model_db.metrics)
            except Exception:
                pass

        # Caveats
        caveats = []
        if task_type == "clustering":
            caveats.append("Explanations for clustering models are limited to feature statistics per cluster.")
        if X_train.shape[0] < 100:
            caveats.append("Small training dataset. Explanations may be unreliable.")
        if len(contributors) == 0:
            caveats.append("Could not compute SHAP values for contributing factors.")

        return {
            "prediction": prediction,
            "predicted_class": predicted_class,
            "actual": actual,
            "probabilities": probabilities,
            "contributors": contributors,
            "feature_values": feature_values,
            "business_explanation": business_explanation,
            "metrics": metrics,
            "caveats": caveats,
            "row_index": row_index,
            "task_type": task_type,
            "available": True,
        }, None

    # ── Importance Comparison ───────────────────────────────────────

    @classmethod
    def get_importance_comparison(cls, user_id: int, model_id: int, top_n: int = 15) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        y_train = data["y_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        # 1. Native importance
        native_imp = {}
        if hasattr(model, "feature_importances_"):
            for i, v in enumerate(model.feature_importances_):
                fname = feature_names[i] if i < len(feature_names) else f"Feature_{i}"
                native_imp[fname] = float(v)
        elif hasattr(model, "coef_"):
            coef = np.abs(model.coef_).flatten()
            if coef.ndim == 0:
                coef = coef.reshape(1)
            for i, v in enumerate(coef):
                fname = feature_names[i] if i < len(feature_names) else f"Feature_{i}"
                native_imp[fname] = float(v)

        # 2. SHAP importance
        shap_imp = {}
        if task_type != "clustering":
            try:
                X_sample = X_train[:min(500, len(X_train))]
                explainer = cls._create_shap_explainer(model, X_sample)
                sv = explainer.shap_values(X_sample)
                if isinstance(sv, list):
                    sv_abs = np.abs(np.concatenate(sv, axis=1))
                elif sv.ndim == 3:
                    sv_abs = np.abs(sv).mean(axis=2)
                else:
                    sv_abs = np.abs(sv)
                mean_abs = np.mean(sv_abs, axis=0)
                for i, v in enumerate(mean_abs):
                    fname = feature_names[i] if i < len(feature_names) else f"Feature_{i}"
                    shap_imp[fname] = float(v)
            except Exception:
                pass

        # 3. Permutation importance
        perm_imp = {}
        if task_type != "clustering":
            try:
                X_sample = X_train[:min(500, len(X_train))]
                y_sample = y_train[:min(500, len(y_train))]
                scoring = "accuracy" if task_type == "classification" else "r2"
                perm_result = permutation_importance(
                    model, X_sample, y_sample,
                    n_repeats=3, scoring=scoring, random_state=42, n_jobs=1,
                )
                for i, v in enumerate(perm_result.importances_mean):
                    fname = feature_names[i] if i < len(feature_names) else f"Feature_{i}"
                    perm_imp[fname] = float(v)
            except Exception:
                pass

        # Gather all features that appear in any method
        all_features = list(set(list(native_imp.keys()) + list(shap_imp.keys()) + list(perm_imp.keys())))

        # Build comparison rows
        rows = []
        for fname in all_features:
            row = {
                "feature": fname,
                "native": native_imp.get(fname),
                "native_rank": None,
                "shap": shap_imp.get(fname),
                "shap_rank": None,
                "permutation": perm_imp.get(fname),
                "permutation_rank": None,
            }
            rows.append(row)

        # Compute ranks within each method
        for method in ["native", "shap", "permutation"]:
            valid = [(i, r[method]) for i, r in enumerate(rows) if r[method] is not None]
            valid.sort(key=lambda x: x[1], reverse=True)
            for rank, (idx, _) in enumerate(valid, 1):
                rows[idx][method + "_rank"] = rank

        # Sort by average rank
        for row in rows:
            ranks = [row[m + "_rank"] for m in ["native", "shap", "permutation"] if row[m + "_rank"] is not None]
            row["avg_rank"] = sum(ranks) / len(ranks) if ranks else 999

        rows.sort(key=lambda x: x["avg_rank"])
        rows = rows[:top_n]

        return {
            "rows": rows,
            "features": rows,
            "methods_available": {
                "native": len(native_imp) > 0,
                "shap": len(shap_imp) > 0,
                "permutation": len(perm_imp) > 0,
            },
        }, None

    # ── Cluster Profiles ────────────────────────────────────────────

    @classmethod
    def get_cluster_profiles(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        X_train = data["X_train"]
        feature_names = data["feature_names"]
        task_type = data["task_type"]

        if task_type != "clustering":
            return {"clusters": [], "available": False, "message": "Cluster profiles are only available for clustering models."}, None

        # Predict cluster labels
        labels = model.fit_predict(X_train)
        unique_labels = sorted(set(labels) if -1 not in set(labels) else set(labels) - {-1})

        clusters = []
        for label in unique_labels:
            mask = labels == label
            cluster_data = X_train[mask]
            stats = {
                "cluster_id": int(label),
                "size": int(mask.sum()),
                "percentage": round(float(mask.sum()) / len(labels) * 100, 1),
                "features": [],
            }
            for i, fname in enumerate(feature_names):
                col = cluster_data[:, i]
                stats["features"].append({
                    "name": fname,
                    "mean": float(np.mean(col)),
                    "std": float(np.std(col)),
                    "min": float(np.min(col)),
                    "max": float(np.max(col)),
                })
            clusters.append(stats)

        return {"clusters": clusters, "available": True, "n_clusters": len(clusters)}, None

    # ── Model Limitations ───────────────────────────────────────────

    @classmethod
    def get_model_limitations(cls, user_id: int, model_id: int) -> Tuple[Optional[Dict], Optional[str]]:
        bundle, err = cls._load_model_bundle(user_id, model_id)
        if err:
            return None, err

        data, err = cls._prepare_data(bundle)
        if err:
            return None, err

        model = data["model"]
        task_type = data["task_type"]
        n_samples = data["n_samples"]
        n_features = data["n_features"]
        model_db = data["model_db"]

        limitations = []
        warnings = []

        # Dataset size warnings
        if n_samples < 50:
            limitations.append("Very small dataset ({} rows). Model predictions may be unreliable and heavily overfitted.".format(n_samples))
            warnings.append("small_dataset")
        elif n_samples < 200:
            limitations.append("Small dataset ({} rows). Consider collecting more data for better generalization.".format(n_samples))
            warnings.append("small_dataset")

        # Feature count
        if n_features > 100:
            limitations.append("High dimensionality ({} features) relative to sample size. Risk of curse of dimensionality.".format(n_features))

        # Algorithm-specific limitations
        algo = model_db.algorithm
        if "Logistic" in algo or "Linear" in algo:
            limitations.append("Linear models assume linear relationships between features and target. Non-linear patterns will not be captured.")
        if "KNN" in algo or "K-Nearest" in algo:
            limitations.append("KNN models are sensitive to feature scaling and the choice of k. Performance degrades in high-dimensional spaces.")
        if "Random Forest" in algo:
            limitations.append("Random Forest can overfit on noisy datasets with many features. Individual tree interpretations may not reflect ensemble behavior.")

        # General XAI caveats
        limitations.append("SHAP values explain the model's behavior, not the true data-generating process. Correlation does not imply causation.")
        limitations.append("LIME explanations are local approximations and may vary between runs due to random sampling.")
        limitations.append("Feature importance measures relative importance within this model, not absolute importance in the real world.")

        if task_type == "clustering":
            limitations.append("Clustering models lack a ground truth. Evaluation metrics (silhouette, etc.) provide relative quality only.")
            limitations.append("SHAP and LIME explanations are not available for unsupervised clustering models.")

        # Supported methods
        supported = {"native": True, "permutation": True, "shap": task_type != "clustering", "lime": task_type != "clustering"}
        if not (hasattr(model, "feature_importances_") or hasattr(model, "coef_")):
            supported["native"] = False

        return {
            "limitations": limitations,
            "warnings": warnings,
            "supported_methods": supported,
            "model_type": algo,
            "task_type": task_type,
            "n_samples": n_samples,
            "n_features": n_features,
        }, None

    # ── Helper: Create SHAP Explainer ────────────────────────────────

    @classmethod
    def _create_shap_explainer(cls, model, X_sample):
        """Create the appropriate SHAP explainer for the model type."""
        from sklearn.ensemble import (RandomForestClassifier, RandomForestRegressor,
                                       GradientBoostingClassifier, GradientBoostingRegressor)
        from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
        from sklearn.linear_model import LogisticRegression, LinearRegression, Ridge
        from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor

        tree_based = (RandomForestClassifier, RandomForestRegressor,
                      GradientBoostingClassifier, GradientBoostingRegressor,
                      DecisionTreeClassifier, DecisionTreeRegressor)

        if isinstance(model, tree_based):
            return shap.TreeExplainer(model)
        elif isinstance(model, (LogisticRegression, LinearRegression, Ridge)):
            return shap.LinearExplainer(model, X_sample)
        elif isinstance(model, (KNeighborsClassifier, KNeighborsRegressor)):
            return shap.KernelExplainer(model.predict, X_sample, nsamples=200)
        else:
            # Fallback to KernelExplainer for any model
            try:
                return shap.KernelExplainer(model.predict, shap.sample(X_sample, min(100, len(X_sample))), nsamples=200)
            except Exception:
                return shap.KernelExplainer(model.predict, X_sample, nsamples=100)

    # ── Helper: Business Explanation Generator ───────────────────────

    @classmethod
    def _generate_business_explanation(cls, prediction, predicted_class, contributors,
                                         task_type, probabilities):
        """Generate a plain-language explanation of the prediction."""
        if not contributors:
            return "No contributing factors could be computed for this prediction."

        top_positive = [c for c in contributors if c["shap_value"] > 0][:3]
        top_negative = [c for c in contributors if c["shap_value"] < 0][:3]

        parts = []

        if task_type == "classification":
            class_label = predicted_class or str(round(prediction))
            parts.append("The model predicts this observation belongs to class <strong>{}</strong>.".format(class_label))
            if probabilities:
                top_prob = max(probabilities.items(), key=lambda x: x[1])
                parts.append("The model is {conf:.1%} confident in this prediction.".format(conf=top_prob[1]))
        else:
            parts.append("The model predicts a value of <strong>{val:.4f}</strong> for this observation.".format(val=prediction))

        if top_positive:
            pos_names = ", ".join([c["feature"] for c in top_positive])
            parts.append("The main factors <span style=\"color:#10B981;\">increasing</span> this prediction are: {}.".format(pos_names))

        if top_negative:
            neg_names = ", ".join([c["feature"] for c in top_negative])
            parts.append("The main factors <span style=\"color:#EF4444;\">decreasing</span> this prediction are: {}.".format(neg_names))

        return " ".join(parts)
