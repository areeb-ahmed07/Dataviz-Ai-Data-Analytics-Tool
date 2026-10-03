"""
Domain models for Machine Learning Configurations (Part 7)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class FeatureEngineeringConfig:
    """Configuration for Automated Feature Engineering"""
    enable_datetime_extraction: bool = True
    enable_log_transform: bool = True
    skew_threshold: float = 1.0                 # |skew| above this triggers log1p transform
    enable_interactions: bool = True
    max_interaction_features: int = 8           # top-k numeric features considered for pairwise interactions
    enable_polynomial: bool = False
    polynomial_degree: int = 2
    enable_binning: bool = False
    binning_columns: Optional[List[str]] = None
    n_bins: int = 5
    drop_low_variance: bool = True
    variance_threshold: float = 0.0
    drop_correlated: bool = True
    correlation_threshold: float = 0.95
    max_generated_features: int = 60            # hard cap on total engineered features kept


@dataclass
class CrossValidationConfig:
    """Configuration for Cross Validation"""
    strategy: str = 'kfold'                     # 'kfold', 'stratified', 'timeseries'
    n_splits: int = 5
    shuffle: bool = True
    random_state: int = 42
    scoring: Optional[str] = None                # auto-selected from task type if None


@dataclass
class HyperparameterConfig:
    """Configuration for Hyperparameter Optimization"""
    method: str = 'optuna'                       # 'optuna', 'random', 'grid'
    n_trials: int = 25
    timeout_seconds: Optional[int] = 180
    cv: CrossValidationConfig = field(default_factory=lambda: CrossValidationConfig(n_splits=3))
    search_space: Optional[Dict[str, Any]] = None  # override the default search space


@dataclass
class ModelExportConfig:
    """Configuration for Model Export"""
    export_format: str = 'joblib'                # 'joblib' or 'pickle'
    include_preprocessor: bool = True
    output_dir: str = 'ml_exports'
