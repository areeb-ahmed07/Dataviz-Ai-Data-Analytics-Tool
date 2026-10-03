"""
Domain enumerations for the AI Engine module.
"""

from enum import Enum


class ImpactLevel(Enum):
    """Priority level for business recommendations."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TrendDirection(Enum):
    """Direction of a detected trend."""
    UPWARD = "upward"
    DOWNWARD = "downward"
    STABLE = "stable"
    VOLATILE = "volatile"


class AnomalyMethod(Enum):
    """Algorithm used for anomaly detection."""
    ISOLATION_FOREST = "isolation_forest"
    Z_SCORE = "z_score"
    IQR = "iqr"
    ENSEMBLE = "ensemble"


class ReportFormat(Enum):
    """Export format for generated reports."""
    MARKDOWN = "markdown"
    HTML = "html"
    PPTX = "pptx"
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"
    EXECUTIVE = "executive"
