"""
AI Business Recommendation Engine — synthesizes anomalies, trends, quality, and root causes into actionable recommendations.

Single Responsibility: generates prioritized strategic recommendations (High/Medium/Low Impact).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

from ai_engine.domain.entities import (
    AnomalySummary,
    BusinessRecommendation,
    ImpactLevel,
    RootCauseItem,
    TrendResult,
)


class RecommendationEngine:
    """
    Synthesizes multi-module analytics data into prioritized, strategic business recommendations.
    """

    def __init__(self) -> None:
        self._openai_api_key = os.environ.get("OPENAI_API_KEY")

    def generate_recommendations(
        self,
        summary_data: Dict[str, Any],
        trends: List[TrendResult],
        anomalies: Optional[AnomalySummary],
        root_causes: List[RootCauseItem],
    ) -> List[BusinessRecommendation]:
        """
        Generate business recommendations using rule-based heuristics with LLM fallback.
        """
        recs: List[BusinessRecommendation] = []

        # 1. Data Quality & Missingness Recommendation
        missing_pct = summary_data.get("missing_percentage", 0.0)
        duplicates = summary_data.get("duplicate_rows", 0)

        if missing_pct > 5.0:
            recs.append(BusinessRecommendation(
                title="Implement Automated Data Cleaning & Imputation Pipeline",
                impact=ImpactLevel.HIGH if missing_pct > 15.0 else ImpactLevel.MEDIUM,
                category="Data Quality",
                description=f"Dataset contains {missing_pct:.1f}% missing values which may bias analytics and machine learning models.",
                action_items=[
                    "Deploy median/mode imputation for numeric features.",
                    "Audit upstream data ingest sources for missing payload fields.",
                    "Filter out incomplete records prior to predictive modeling.",
                ],
                data_evidence=f"{missing_pct:.1f}% missing data rate detected across columns.",
            ))

        if duplicates > 0:
            recs.append(BusinessRecommendation(
                title="Deduplicate Record Ingestion Streams",
                impact=ImpactLevel.MEDIUM,
                category="Data Governance",
                description=f"Identified {duplicates:,} exact duplicate rows in the dataset.",
                action_items=[
                    "Implement primary key uniqueness constraints on database tables.",
                    "Remove redundant rows before aggregations to prevent metric inflation.",
                ],
                data_evidence=f"{duplicates:,} duplicate rows found.",
            ))

        # 2. Anomaly Recommendations
        if anomalies and anomalies.anomalous_rows_count > 0:
            pct = anomalies.anomaly_percentage
            impact = ImpactLevel.HIGH if pct > 3.0 else ImpactLevel.MEDIUM
            recs.append(BusinessRecommendation(
                title="Investigate High-Risk Outlier Events",
                impact=impact,
                category="Risk & Compliance",
                description=f"Detected {anomalies.anomalous_rows_count:,} anomalous observations ({pct:.1f}% of total data) using ensemble outlier scoring.",
                action_items=[
                    "Review top flagged anomaly rows in the Anomaly Inspector.",
                    "Verify whether anomalies represent fraud, system errors, or genuine business spikes.",
                    "Set up real-time threshold alerts for future outlier occurrences.",
                ],
                data_evidence=f"{anomalies.anomalous_rows_count:,} anomalous observations identified.",
            ))

        # 3. Negative / Downward Trend Recommendations
        downward_trends = [t for t in trends if t.direction.value == "downward"]
        if downward_trends:
            top_down = downward_trends[0]
            recs.append(BusinessRecommendation(
                title=f"Address Declining Trend in {top_down.column.replace('_', ' ').title()}",
                impact=ImpactLevel.HIGH,
                category="Performance Optimization",
                description=top_down.summary_text,
                action_items=[
                    f"Conduct deep-dive segment analysis on {top_down.column}.",
                    "Implement corrective operational strategies to reverse the negative slope.",
                    "Monitor weekly rolling averages to track recovery progress.",
                ],
                data_evidence=f"{top_down.pct_change:.1f}% total decline detected (slope: {top_down.slope:.2f}).",
            ))

        # 4. Upward / Growth Trend Recommendations
        upward_trends = [t for t in trends if t.direction.value == "upward"]
        if upward_trends:
            top_up = upward_trends[0]
            recs.append(BusinessRecommendation(
                title=f"Capitalize on Upward Momentum in {top_up.column.replace('_', ' ').title()}",
                impact=ImpactLevel.MEDIUM,
                category="Growth Strategy",
                description=top_up.summary_text,
                action_items=[
                    f"Allocate additional resources to support positive momentum in {top_up.column}.",
                    "Analyze drivers behind the increase to replicate success across other business units.",
                ],
                data_evidence=f"+{top_up.pct_change:.1f}% growth trajectory identified.",
            ))

        # 5. Root Cause Recommendations
        if root_causes:
            top_rc = root_causes[0]
            recs.append(BusinessRecommendation(
                title=f"Optimize Key Business Segment ({top_rc.condition})",
                impact=ImpactLevel.HIGH,
                category="Operational Strategy",
                description=top_rc.description,
                action_items=[
                    f"Target resources towards the sub-population defined by {top_rc.condition}.",
                    "Establish KPI tracking specific to this operational segment.",
                ],
                data_evidence=f"Segment accounts for {top_rc.affected_percentage:.1f}% of target variance.",
            ))

        # Optional LLM Enhancement if API key is present
        if self._openai_api_key:
            llm_recs = self._enhance_with_llm(summary_data, recs)
            if llm_recs:
                return llm_recs

        return recs

    def _enhance_with_llm(
        self, summary: Dict[str, Any], base_recs: List[BusinessRecommendation]
    ) -> Optional[List[BusinessRecommendation]]:
        """Optional LLM-enhanced recommendation generator via OpenAI API."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._openai_api_key)
            prompt = (
                "You are an executive management consultant. Based on this data analysis summary, "
                "provide 3 concise, highly actionable strategic business recommendations:\n"
                f"Data Summary: {summary}\n"
                f"Base Findings: {[r.title for r in base_recs]}\n\n"
                "Return a structured list of recommendations."
            )
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.7,
            )
            content = response.choices[0].message.content
            if content:
                # Append LLM recommendation
                base_recs.insert(0, BusinessRecommendation(
                    title="AI-Executive Strategic Outlook",
                    impact=ImpactLevel.HIGH,
                    category="Strategic Insight",
                    description=content[:300] + "...",
                    action_items=["Review strategic advisory items with executive team."],
                    data_evidence="Generated via OpenAI GPT analysis.",
                ))
            return base_recs
        except Exception:
            return base_recs
