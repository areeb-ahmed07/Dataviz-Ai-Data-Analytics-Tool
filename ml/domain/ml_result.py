"""
Domain models for Machine Learning Results (Part 7)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class FeatureEngineeringReport:
    """Summary of an Auto Feature Engineering run"""
    original_feature_count: int
    final_feature_count: int
    added_features: List[str] = field(default_factory=list)
    dropped_features: List[str] = field(default_factory=list)
    transformations_applied: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class CVResult:
    """Result of a Cross Validation run for a single model"""
    model_name: str
    strategy: str
    scoring: str
    fold_scores: List[float]
    mean_score: float
    std_score: float


@dataclass
class ModelResult:
    """Full evaluation result for a single model (CV + holdout test metrics)"""
    name: str
    task_type: str                               # 'classification' or 'regression'
    cv_result: Optional[CVResult] = None
    test_metrics: Dict[str, float] = field(default_factory=dict)
    fit_time_seconds: float = 0.0
    predict_time_seconds: float = 0.0
    params: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    estimator: Any = field(default=None, repr=False)

    @property
    def is_valid(self) -> bool:
        return self.error is None and self.cv_result is not None


@dataclass
class LeaderboardEntry:
    """A single ranked row on the Model Leaderboard"""
    rank: int
    model_name: str
    primary_metric_name: str
    primary_metric_value: float
    cv_mean: float
    cv_std: float
    composite_score: float
    metrics: Dict[str, float] = field(default_factory=dict)
    fit_time_seconds: float = 0.0


@dataclass
class TuningResult:
    """Result of a Hyperparameter Optimization run"""
    model_name: str
    method: str
    best_params: Dict[str, Any]
    best_score: float
    n_trials: int
    scoring: str
    trials_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ExportManifest:
    """Metadata describing an exported model artifact"""
    model_path: str
    format: str
    model_name: str
    task_type: str
    feature_columns: List[str]
    target_column: str
    metrics: Dict[str, float]
    timestamp: str
    training_code_path: Optional[str] = None
