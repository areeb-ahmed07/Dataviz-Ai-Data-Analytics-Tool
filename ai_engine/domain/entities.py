"""
Domain entities for the AI Engine module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .enums import AnomalyMethod, ImpactLevel, TrendDirection


@dataclass
class AnomalyItem:
    """A single detected anomaly observation."""
    row_index: int
    column: str
    value: Any
    score: float                         # Normalized anomaly score [0.0 - 1.0]
    method: AnomalyMethod
    expected_range: Tuple[float, float] = (0.0, 0.0)
    reason: str = ""


@dataclass
class AnomalySummary:
    """Summary result of an anomaly detection analysis."""
    total_rows: int
    anomalous_rows_count: int
    anomaly_percentage: float
    detected_anomalies: List[AnomalyItem] = field(default_factory=list)
    method_used: AnomalyMethod = AnomalyMethod.ENSEMBLE


@dataclass
class TrendResult:
    """Summary of trend analysis for a numeric column or metric."""
    column: str
    direction: TrendDirection
    slope: float                         # Slope / rate of change per step
    r2_score: float                      # Linear fit confidence
    pct_change: float                    # Total % change across series
    mean_val: float
    std_val: float
    change_points: List[int] = field(default_factory=list) # Row indices where mean/var shifted
    summary_text: str = ""


@dataclass
class RootCauseItem:
    """A driver or segment rule contributing to a target outcome."""
    feature: str
    condition: str                       # e.g., "age > 45 AND category == 'Tech'"
    impact_score: float                  # Relative importance / lift [0.0 - 1.0]
    affected_rows: int
    affected_percentage: float
    description: str


@dataclass
class BusinessRecommendation:
    """Actionable recommendation for decision makers."""
    title: str
    impact: ImpactLevel
    category: str                        # e.g., "Data Quality", "Growth", "Risk", "Operations"
    description: str
    action_items: List[str] = field(default_factory=list)
    data_evidence: str = ""


@dataclass
class ExecutiveReportData:
    """Complete structured dataset used to populate PDF, PPTX, HTML, Excel, Word, and Executive reports."""
    title: str = "Executive Data Analytics & Insights Report"
    generated_at: datetime = field(default_factory=datetime.now)
    dataset_name: str = "Dataset"
    dataset_shape: Tuple[int, int] = (0, 0)
    quality_score: float = 100.0
    missing_percentage: float = 0.0
    kpis: List[Dict[str, Any]] = field(default_factory=list)
    trends: List[TrendResult] = field(default_factory=list)
    anomalies: Optional[AnomalySummary] = None
    root_causes: List[RootCauseItem] = field(default_factory=list)
    recommendations: List[BusinessRecommendation] = field(default_factory=list)
    summary_paragraph: str = ""
    # Extended fields populated by ReportService from real analysis
    statistics: Dict[str, Any] = field(default_factory=dict)
    quality_detail: Dict[str, Any] = field(default_factory=dict)
    correlations: Dict[str, Any] = field(default_factory=dict)
    distributions: Dict[str, Any] = field(default_factory=dict)
    outliers: Dict[str, Any] = field(default_factory=dict)
    categorical: Dict[str, Any] = field(default_factory=dict)
    insights: Dict[str, Any] = field(default_factory=dict)
    overview: Dict[str, Any] = field(default_factory=dict)
    ml_models: List[Dict[str, Any]] = field(default_factory=list)
