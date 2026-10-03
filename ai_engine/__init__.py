"""
AI Engine Module — Unified Facade API for Advanced AI Features.

Features (Part 4)
─────────────────
✓ Root Cause Analysis
✓ Trend Detection
✓ Anomaly Detection
✓ AI Generated Business Recommendations
✓ AI Generated Executive Reports
✓ AI Generated PowerPoint Summary (.pptx)
✓ AI Generated PDF Reports (.pdf)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from ai_engine.domain.entities import (
    AnomalySummary,
    BusinessRecommendation,
    ExecutiveReportData,
    RootCauseItem,
    TrendResult,
)
from ai_engine.domain.enums import AnomalyMethod, ImpactLevel, ReportFormat, TrendDirection
from ai_engine.generators.executive_report_generator import ExecutiveReportGenerator
from ai_engine.generators.pdf_generator import PDFGenerator
from ai_engine.generators.pptx_generator import PPTXGenerator
from ai_engine.generators.excel_generator import ExcelGenerator
from ai_engine.generators.word_generator import WordGenerator
from ai_engine.services.anomaly_detector import AnomalyDetector
from ai_engine.services.recommendation_engine import RecommendationEngine
from ai_engine.services.root_cause_analyzer import RootCauseAnalyzer
from ai_engine.services.trend_detector import TrendDetector


class AIEngine:
    """
    Unified Facade orchestrator for all Part 4 AI Features.
    """

    def __init__(self, df: pd.DataFrame, dataset_name: str = "Dataset") -> None:
        self._df = df.copy()
        self._dataset_name = dataset_name
        self._root_cause_analyzer = RootCauseAnalyzer(df)
        self._trend_detector = TrendDetector(df)
        self._anomaly_detector = AnomalyDetector(df)
        self._recommendation_engine = RecommendationEngine()

    def run_full_ai_analysis(
        self,
        target_column: Optional[str] = None,
        summary_data: Optional[Dict[str, Any]] = None,
    ) -> ExecutiveReportData:
        """
        Execute complete AI analysis (Trends, Anomalies, Root Causes, Recommendations).
        """
        summary_dict = summary_data or {
            "dataset_name": self._dataset_name,
            "dataset_shape": self._df.shape,
            "missing_percentage": (self._df.isnull().sum().sum() / self._df.size * 100) if self._df.size > 0 else 0,
            "duplicate_rows": self._df.duplicated().sum(),
        }

        # 1. Trends
        trends = self._trend_detector.detect_trends()

        # 2. Anomalies
        anomalies = self._anomaly_detector.detect_anomalies()

        # 3. Root Causes
        root_causes = self._root_cause_analyzer.analyze(target_column=target_column)

        # 4. Recommendations
        recommendations = self._recommendation_engine.generate_recommendations(
            summary_data=summary_dict,
            trends=trends,
            anomalies=anomalies,
            root_causes=root_causes,
        )

        # 5. Formulate Executive Report Data
        summary_paragraph = (
            f"Automated AI Intelligence Scan for '{self._dataset_name}' ({self._df.shape[0]:,} rows × {self._df.shape[1]} cols). "
            f"Identified {len(trends)} primary directional trends, {anomalies.anomalous_rows_count:,} anomalies ({anomalies.anomaly_percentage:.1f}%), "
            f"and {len(recommendations)} strategic recommendations."
        )

        return ExecutiveReportData(
            title=f"AI Analytics Report — {self._dataset_name}",
            dataset_name=self._dataset_name,
            dataset_shape=self._df.shape,
            quality_score=max(0.0, 100.0 - summary_dict.get("missing_percentage", 0.0)),
            missing_percentage=summary_dict.get("missing_percentage", 0.0),
            trends=trends,
            anomalies=anomalies,
            root_causes=root_causes,
            recommendations=recommendations,
            summary_paragraph=summary_paragraph,
        )

    # ─── Individual Feature APIs ─────────────────────────────────────────────

    def analyze_root_causes(self, target_column: Optional[str] = None) -> List[RootCauseItem]:
        return self._root_cause_analyzer.analyze(target_column=target_column)

    def detect_trends(self) -> List[TrendResult]:
        return self._trend_detector.detect_trends()

    def detect_anomalies(self) -> AnomalySummary:
        return self._anomaly_detector.detect_anomalies()

    def generate_recommendations(self, summary_data: Dict[str, Any]) -> List[BusinessRecommendation]:
        trends = self.detect_trends()
        anomalies = self.detect_anomalies()
        root_causes = self.analyze_root_causes()
        return self._recommendation_engine.generate_recommendations(summary_data, trends, anomalies, root_causes)

    # ─── Export Generators ───────────────────────────────────────────────────

    @staticmethod
    def generate_executive_html(report_data: ExecutiveReportData) -> str:
        return ExecutiveReportGenerator(report_data).generate_html()

    @staticmethod
    def generate_executive_markdown(report_data: ExecutiveReportData) -> str:
        return ExecutiveReportGenerator(report_data).generate_markdown()

    @staticmethod
    def generate_pptx_summary(report_data: ExecutiveReportData, output_path: str) -> Optional[str]:
        return PPTXGenerator(report_data).generate(output_path)

    @staticmethod
    def generate_pdf_report(report_data: ExecutiveReportData, output_path: str) -> Optional[str]:
        return PDFGenerator(report_data).generate(output_path)

    @staticmethod
    def generate_excel_summary(report_data: ExecutiveReportData, output_path: str) -> Optional[str]:
        return ExcelGenerator(report_data).generate(output_path)

    @staticmethod
    def generate_word_report(report_data: ExecutiveReportData, output_path: str) -> Optional[str]:
        return WordGenerator(report_data).generate(output_path)


__all__ = [
    "AIEngine",
    "AnomalyMethod",
    "ImpactLevel",
    "ReportFormat",
    "TrendDirection",
    "AnomalySummary",
    "BusinessRecommendation",
    "ExecutiveReportData",
    "RootCauseItem",
    "TrendResult",
]
