"""
Domain models for ML Studio (Phase 7)
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime


@dataclass
class ModelDomain:
    """Domain model for a saved ML model."""
    id: int
    user_id: int
    dataset_id: Optional[int] = None
    model_name: str = ""
    algorithm: str = ""
    problem_type: str = ""  # classification, regression, clustering
    target_column: Optional[str] = None
    features: Optional[List[str]] = None
    metrics: Optional[Dict[str, float]] = None
    hyperparameters: Optional[Dict[str, Any]] = None
    pipeline_config: Optional[Dict[str, Any]] = None
    version: int = 1
    model_path: Optional[str] = None
    model_format: Optional[str] = None
    experiment_config: Optional[Dict[str, Any]] = None
    primary_metric: Optional[str] = None
    primary_score: Optional[float] = None
    cv_strategy: Optional[str] = None
    cv_score: Optional[float] = None
    cv_std: Optional[float] = None
    random_state: Optional[int] = None
    test_size: Optional[float] = None
    train_rows: Optional[int] = None
    test_rows: Optional[int] = None
    is_active: bool = True
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class MLWorkflowConfig:
    """Configuration for the ML workflow."""
    dataset_id: int
    target_column: Optional[str] = None
    feature_columns: Optional[List[str]] = None
    problem_type: Optional[str] = None  # classification, regression, clustering
    test_size: float = 0.2
    random_state: int = 42
    cv_folds: int = 5
    cv_strategy: str = "auto"  # auto, stratified, kfold
    primary_metric: Optional[str] = None
    scaling: str = "standard"  # standard, minmax, robust
    encoding: str = "onehot"  # onehot, ordinal
    imputation: str = "median"  # median, mean, most_frequent, constant
    class_weights: Optional[str] = None  # balanced, None
    selected_algorithms: Optional[List[str]] = None
    auto_mode: bool = True
    optimization_level: str = "off"  # off, fast, thorough
    optimization_iterations: int = 20
    optimization_model: Optional[str] = None
    experiment_config: Optional[Dict[str, Any]] = None


@dataclass
class MLWorkflowResult:
    """Result of an ML workflow execution."""
    config: 'MLWorkflowConfig'
    task_type: Optional[str] = None
    problem_subtype: Optional[str] = None  # binary, multiclass
    features_used: List[str] = field(default_factory=list)
    categorical_features: List[str] = field(default_factory=list)
    numerical_features: List[str] = field(default_factory=list)
    train_rows: int = 0
    test_rows: int = 0
    class_distribution: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    preprocessing_info: Optional[Dict[str, Any]] = None
    model_results: Optional[Dict[str, Any]] = None
    leaderboard: Optional[List[Dict[str, Any]]] = None
    tuning_result: Optional[Dict[str, Any]] = None
    best_model_name: Optional[str] = None
    training_time: float = 0.0


@dataclass
class ClusteringConfig:
    """Configuration specific to clustering tasks."""
    algorithm: str = "kmeans"  # kmeans, agglomerative, dbscan
    n_clusters: int = 3
    dbscan_eps: float = 0.5
    dbscan_min_samples: int = 5
    linkage: str = "ward"  # for agglomerative: ward, complete, average
