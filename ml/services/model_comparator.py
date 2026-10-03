"""
Service: Model Comparison (Part 7)
"""
import time
import traceback
from typing import Dict, Optional, Any

import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score,
    r2_score, mean_squared_error, mean_absolute_error, mean_absolute_percentage_error,
)

from ml.domain.ml_config import CrossValidationConfig
from ml.domain.ml_result import ModelResult
from ml.services.cross_validator import CrossValidationService
from ml.services.model_registry import get_model_zoo


class TrainingCancelled(RuntimeError):
    """Raised at a safe model boundary when cancellation was requested."""


class ModelComparisonService:
    """Trains, cross-validates, and evaluates a zoo of candidate models"""

    def __init__(self):
        self.cv_service = CrossValidationService()

    def compare(
        self,
        X_train, y_train, X_test, y_test,
        task_type: str,
        cv_config: Optional[CrossValidationConfig] = None,
        fast_mode: bool = True,
        random_state: int = 42,
        models: Optional[Dict[str, Any]] = None,
        preprocessor=None,
        X_train_raw=None,
        progress=None,
    ) -> Dict[str, ModelResult]:
        cv_config = cv_config or CrossValidationConfig(strategy='stratified' if task_type == 'classification' else 'kfold')
        candidate_models = models or get_model_zoo(task_type, fast_mode=fast_mode, random_state=random_state)

        results: Dict[str, ModelResult] = {}

        from sklearn.model_selection import GridSearchCV
        
        for name, model in candidate_models.items():
            if progress:
                progress(len(results), len(candidate_models), name)
            try:
                splitter = self.cv_service.build_splitter(cv_config)
                scoring = cv_config.scoring or self.cv_service.default_scoring(task_type)
                scoring = {'f1': 'f1_weighted', 'precision': 'precision_weighted',
                           'recall': 'recall_weighted', 'rmse': 'neg_root_mean_squared_error',
                           'mae': 'neg_mean_absolute_error', 'mse': 'neg_mean_squared_error',
                           'mape': 'neg_mean_absolute_percentage_error'}.get(scoring, scoring)
                if scoring == 'roc_auc' and len(np.unique(y_train)) > 2:
                    scoring = 'roc_auc_ovr_weighted'
                from sklearn.pipeline import Pipeline
                from sklearn.base import clone
                estimator = Pipeline([('preprocess', clone(preprocessor)), ('model', model)]) if preprocessor is not None else model
                
                search = GridSearchCV(
                    estimator=estimator,
                    param_grid={},
                    cv=splitter,
                    scoring=scoring,
                    refit=True,
                    n_jobs=1,
                    error_score='raise',
                )
                
                fit_start = time.time()
                search.fit(X_train_raw if preprocessor is not None else X_train, y_train)
                fit_time = time.time() - fit_start

                best_model = search.best_estimator_['model'] if preprocessor is not None else search.best_estimator_
                
                predict_start = time.time()
                y_pred = best_model.predict(X_test)
                predict_time = time.time() - predict_start

                fold_keys = [k for k in search.cv_results_.keys() if k.startswith('split') and k.endswith('_test_score')]
                fold_scores = [float(search.cv_results_[k][0]) for k in fold_keys]
                if not np.isfinite(fold_scores).all():
                    raise ValueError('Cross-validation could not calculate a finite score. Check the metric and class counts.')
                
                from ml.domain.ml_result import CVResult
                cv_result = CVResult(
                    model_name=name,
                    strategy=cv_config.strategy,
                    scoring=scoring,
                    fold_scores=fold_scores,
                    mean_score=float(np.mean(fold_scores)),
                    std_score=float(np.std(fold_scores)),
                )
                
                test_metrics = self._compute_test_metrics(task_type, best_model, X_test, y_test, y_pred)

                results[name] = ModelResult(
                    name=name,
                    task_type=task_type,
                    cv_result=cv_result,
                    test_metrics=test_metrics,
                    fit_time_seconds=round(fit_time, 4),
                    predict_time_seconds=round(predict_time, 4),
                    params=best_model.get_params() if hasattr(best_model, 'get_params') else {},
                    estimator=best_model,
                )
            except Exception as e:
                results[name] = ModelResult(
                    name=name,
                    task_type=task_type,
                    error=f"{e} | {traceback.format_exc(limit=1)}",
                )

        if progress:
            progress(len(results), len(candidate_models), None)
        return results

    def _compute_test_metrics(self, task_type: str, model, X_test, y_test, y_pred) -> Dict[str, float]:
        metrics: Dict[str, float] = {}
        if task_type == 'classification':
            metrics['accuracy'] = float(accuracy_score(y_test, y_pred))
            metrics['precision'] = float(precision_score(y_test, y_pred, average='weighted', zero_division=0))
            metrics['recall'] = float(recall_score(y_test, y_pred, average='weighted', zero_division=0))
            metrics['f1'] = float(f1_score(y_test, y_pred, average='weighted', zero_division=0))
            try:
                if hasattr(model, "predict_proba"):
                    y_prob = model.predict_proba(X_test)
                    if len(np.unique(y_test)) == 2:
                        metrics['roc_auc'] = float(roc_auc_score(y_test, y_prob[:, 1]))
                    else:
                        metrics['roc_auc'] = float(roc_auc_score(y_test, y_prob, multi_class='ovr'))
            except Exception:
                pass
        else:
            metrics['r2'] = float(r2_score(y_test, y_pred))
            metrics['rmse'] = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            metrics['mae'] = float(mean_absolute_error(y_test, y_pred))
            metrics['mape'] = float(mean_absolute_percentage_error(y_test, y_pred))
        return {k: round(v, 4) for k, v in metrics.items()}
