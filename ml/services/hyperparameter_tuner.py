from sklearn.model_selection import GridSearchCV
from ml.domain.ml_config import CrossValidationConfig
from ml.services.cross_validator import CrossValidationService
from ml.services.model_registry import build_model, default_search_space

class HyperparameterTuningService:
    def __init__(self):
        self.cv_service = CrossValidationService()
        
    def tune(self, X_train, y_train, task_type: str, algorithm: str, param_grid: dict = None, cv_config: CrossValidationConfig = None, random_state: int = 42):
        base_model = build_model(task_type, algorithm, {}, random_state)
        if not base_model:
            raise ValueError(f"Algorithm {algorithm} not supported.")
            
        param_grid = param_grid or default_search_space(algorithm)
        cv_config = cv_config or CrossValidationConfig(strategy='stratified' if task_type == 'classification' else 'kfold')
        
        splitter = self.cv_service.build_splitter(cv_config)
        scoring = cv_config.scoring or self.cv_service.default_scoring(task_type)
        
        search = GridSearchCV(
            estimator=base_model,
            param_grid=param_grid,
            cv=splitter,
            scoring=scoring,
            n_jobs=1,
            refit=True
        )
        
        search.fit(X_train, y_train)
        return {
            'best_params': search.best_params_,
            'best_score': float(search.best_score_),
            'best_model': search.best_estimator_,
            'n_trials': len(search.cv_results_['params']),
        }
