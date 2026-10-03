from sklearn.model_selection import KFold, StratifiedKFold
from ml.domain.ml_config import CrossValidationConfig

class CrossValidationService:
    def build_splitter(self, config: CrossValidationConfig):
        random_state = config.random_state if hasattr(config, 'random_state') else 42
        n_splits = config.n_splits if hasattr(config, 'n_splits') else 5
        shuffle = getattr(config, 'shuffle', True)
        
        if config.strategy == 'stratified':
            return StratifiedKFold(n_splits=n_splits, shuffle=shuffle, random_state=random_state)
        return KFold(n_splits=n_splits, shuffle=shuffle, random_state=random_state)

    def default_scoring(self, task_type: str) -> str:
        return 'accuracy' if task_type == 'classification' else 'neg_mean_squared_error'
