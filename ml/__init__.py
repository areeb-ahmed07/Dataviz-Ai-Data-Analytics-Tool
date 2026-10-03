"""
Part 7: Machine Learning Package Top-Level Exports

Includes the new Clean-Architecture ML Workbench (auto feature engineering,
model comparison, cross validation, hyperparameter optimization, leaderboard,
and model export) alongside the pre-existing AutoMLPipeline / ExplainableAI
modules, kept for backward compatibility with main_analyzer.py.
"""
from ml.domain import (
    FeatureEngineeringConfig,
    CrossValidationConfig,
    HyperparameterConfig,
    ModelExportConfig,
    FeatureEngineeringReport,
    CVResult,
    ModelResult,
    LeaderboardEntry,
    TuningResult,
    ExportManifest,
)
from ml.services import (
    FeatureEngineeringService,
    CrossValidationService,
    ModelComparisonService,
    HyperparameterTuningService,
    LeaderboardService,
    ModelExporterService,
    MLPipeline,
)

# UI layer depends on streamlit; keep it optional so domain/services can be
# used headlessly (e.g. from main_analyzer.py or a script) without streamlit installed.
try:
    from ml.ui import render_ml_workbench_ui
except Exception:
    render_ml_workbench_ui = None

# Legacy modules (Part 2 / Part 9) — retained for backward compatibility
from ml.automl_pipeline import AutoMLPipeline
from ml.explainable_ai import ExplainableAI

__all__ = [
    # Config
    'FeatureEngineeringConfig',
    'CrossValidationConfig',
    'HyperparameterConfig',
    'ModelExportConfig',
    # Results
    'FeatureEngineeringReport',
    'CVResult',
    'ModelResult',
    'LeaderboardEntry',
    'TuningResult',
    'ExportManifest',
    # Services
    'FeatureEngineeringService',
    'CrossValidationService',
    'ModelComparisonService',
    'HyperparameterTuningService',
    'LeaderboardService',
    'ModelExporterService',
    'MLPipeline',
    # UI
    'render_ml_workbench_ui',
    # Legacy
    'AutoMLPipeline',
    'ExplainableAI',
]
