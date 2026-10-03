"""
Service: Report Generation (Phase 10)

Orchestrates gathering real analysis data from AnalysisService, MLService,
and XAIService, then delegates to AI Engine generators.

All methods return (result, error) tuples consistent with other services.
No fake data, no placeholders, no TODOs.
"""

import os
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.services.dataset_service import DatasetService
from app.services.analysis_service import AnalysisService, _load_dataset, MAX_ANALYSIS_ROWS


class ReportService:
    """
    Service layer for Report generation.
    Gathers real analysis results from existing services and
    builds ExecutiveReportData for the generators.
    """

    # ── Full Analysis Data Gatherer ──────────────────────────────

    @staticmethod
    def report_directory(user_id):
        from flask import current_app, has_app_context
        static_root = current_app.static_folder if has_app_context() else os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static')
        return os.path.join(static_root, 'reports', str(user_id))

    @staticmethod
    def resolve_report(user_id, filename):
        """Resolve an existing file strictly inside the current user's report folder."""
        if not filename or any(char in filename for char in ('/', '\\', ':', '\x00')):
            return None
        root = os.path.realpath(ReportService.report_directory(user_id))
        candidate = os.path.realpath(os.path.join(root, filename))
        if os.path.dirname(candidate) != root or not os.path.isfile(candidate):
            return None
        if os.path.splitext(filename)[1].lower() not in {'.pdf', '.html', '.xlsx', '.pptx', '.docx', '.md'}:
            return None
        return candidate

    @staticmethod
    def gather_analysis_data(dataset_id: int, user_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Gather ALL available analysis data for a dataset.
        Returns a comprehensive dictionary with overview, quality,
        statistics, correlations, distributions, and ML model data.
        """
        # 1. Load the DataFrame
        df, error = _load_dataset(dataset_id, user_id, max_rows=MAX_ANALYSIS_ROWS)
        if df is None:
            return None, error

        dataset = DatasetService.get_dataset(dataset_id, user_id)
        if not dataset:
            return None, "Dataset not found."

        result: Dict[str, Any] = {
            "dataset_name": dataset.name,
            "dataset_id": dataset.id,
            "row_count": len(df),
            "col_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {col: str(df[col].dtype) for col in df.columns},
            "memory_mb": round(df.memory_usage(deep=True).sum() / 1024 ** 2, 2),
        }

        # 2. Overview (KPIs, schema, quality summary, insights)
        overview, ov_err = AnalysisService.get_overview(dataset_id, user_id)
        if overview:
            result["overview"] = overview
        if ov_err:
            result["overview_error"] = ov_err

        # 3. Quality analysis
        quality, q_err = AnalysisService.get_quality(dataset_id, user_id)
        if quality:
            result["quality"] = quality
        if q_err:
            result["quality_error"] = q_err

        # 4. Descriptive statistics
        stats, s_err = AnalysisService.get_statistics(dataset_id, user_id)
        if stats:
            # Normalize AnalysisService's API names to the report generator schema.
            stats["numeric_stats"] = stats.get("numeric_stats", stats.get("numeric", []))
            stats["categorical_stats"] = stats.get("categorical_stats", stats.get("categorical", []))
            stats["datetime_stats"] = stats.get("datetime_stats", stats.get("datetime", []))
            for item in stats["categorical_stats"]:
                if "top_values" not in item:
                    item["top_values"] = [{"value": item.get("top_value"), "frequency": item.get("top_pct", 0)}]
            result["statistics"] = stats
        if s_err:
            result["statistics_error"] = s_err

        # 5. Correlations
        correlations, c_err = AnalysisService.get_correlations(dataset_id, user_id)
        if correlations:
            if "top_pairs" not in correlations:
                correlations["top_pairs"] = [
                    {"col_a": p.get("var1"), "col_b": p.get("var2"), "correlation": p.get("pearson")}
                    for p in correlations.get("strong_correlations", [])
                ]
            result["correlations"] = correlations
        if c_err:
            result["correlations_error"] = c_err

        # 6. Distributions (the analysis API is column-scoped; reports include all numeric columns)
        distributions = {}
        numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()
        distribution_errors = []
        for column in numeric_columns[:20]:
            dist, d_err = AnalysisService.get_distribution(dataset_id, user_id, column)
            if dist:
                distributions[column] = dist
            if d_err:
                distribution_errors.append(f"{column}: {d_err}")
        if distributions:
            result["distributions"] = distributions
        if distribution_errors:
            result["distributions_error"] = "; ".join(distribution_errors)

        # 7. Outlier analysis
        outliers, o_err = AnalysisService.get_outliers(dataset_id, user_id)
        if outliers:
            if "iqr_outliers" not in outliers:
                outliers["iqr_outliers"] = [
                    {"column": x.get("column"), "count": x.get("outlier_count", 0), "percentage": x.get("outlier_pct", 0),
                     "lower_bound": x.get("lower_fence", 0), "upper_bound": x.get("upper_fence", 0)}
                    for x in outliers.get("outlier_details", [])
                ]
            result["outliers"] = outliers
        if o_err:
            result["outliers_error"] = o_err

        # 8. Categorical analysis
        categorical, cat_err = AnalysisService.get_categorical_analysis(dataset_id, user_id)
        if categorical:
            result["categorical"] = categorical
        if cat_err:
            result["categorical_error"] = cat_err

        # 9. ML models for this dataset
        ml_models = ReportService._get_models_for_dataset(dataset_id, user_id)
        result["ml_models"] = ml_models

        # 10. Insights from NLG
        insights_data, i_err = AnalysisService.get_insights(dataset_id, user_id)
        if insights_data:
            result["insights"] = insights_data
        if i_err:
            result["insights_error"] = i_err

        return result, None

    @staticmethod
    def _get_models_for_dataset(dataset_id: int, user_id: int) -> List[Dict[str, Any]]:
        """Get all trained ML models for a dataset."""
        try:
            from auth.database import ModelDB, get_session
            session = get_session()
            models = session.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.dataset_id == dataset_id
            ).order_by(ModelDB.created_at.desc()).all()

            result = []
            for m in models:
                model_dict = {
                    "id": m.id,
                    "model_name": m.model_name,
                    "algorithm": m.algorithm,
                    "problem_type": m.problem_type,
                    "metrics": m.metrics or {},
                    "hyperparameters": m.hyperparameters or {},
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                result.append(model_dict)
            session.close()
            return result
        except Exception:
            return []

    # ── Report Data Builders ─────────────────────────────────────

    @staticmethod
    def build_executive_report_data(analysis_data: Dict[str, Any], user_id: Optional[int] = None) -> Tuple[Optional[object], Optional[str]]:
        """
        Build ExecutiveReportData from gathered analysis data.
        Populates trends, anomalies, root causes, recommendations, KPIs.
        """
        try:
            from ai_engine import AIEngine
            from ai_engine.domain.entities import ExecutiveReportData, AnomalySummary, AnomalyItem
            from ai_engine.domain.enums import AnomalyMethod

            # Load the actual dataframe for AI analysis
            dataset_id = analysis_data["dataset_id"]
            user_id = user_id or analysis_data.get("user_id")
            if not user_id:
                return None, "User context is required to build a report."
            df, _ = _load_dataset(dataset_id, user_id, max_rows=5000)
            if df is None:
                # Fallback: build from analysis_data alone
                return ReportService._build_report_from_cache(analysis_data)

            # Run AI analysis on real data
            engine = AIEngine(df, dataset_name=analysis_data["dataset_name"])
            report_data = engine.run_full_ai_analysis()

            # Enrich with real analysis results
            report_data = ReportService._enrich_report_data(report_data, analysis_data)

            return report_data, None
        except Exception as e:
            # Fallback path
            return ReportService._build_report_from_cache(analysis_data)

    @staticmethod
    def _enrich_report_data(report_data, analysis_data: Dict[str, Any]) -> object:
        """Enrich ExecutiveReportData with real statistics, quality, ML data."""
        from ai_engine.domain.entities import ExecutiveReportData

        # Enrich KPIs from real analysis
        kpis = []
        overview = analysis_data.get("overview", {})
        if overview and "kpis" in overview:
            ov_kpis = overview["kpis"]
            kpis.append({
                "title": "Total Records",
                "agg": "COUNT",
                "value": f"{ov_kpis.get('rows', 0):,}",
                "status": "OK",
            })
            kpis.append({
                "title": "Features",
                "agg": "COUNT",
                "value": str(ov_kpis.get("columns", 0)),
                "status": "OK",
            })
            kpis.append({
                "title": "Missing Values",
                "agg": "SUM",
                "value": f"{ov_kpis.get('missing_values', 0):,}",
                "status": "WARNING" if ov_kpis.get("missing_pct", 0) > 5 else "OK",
            })
            kpis.append({
                "title": "Duplicate Rows",
                "agg": "COUNT",
                "value": f"{ov_kpis.get('duplicate_rows', 0):,}",
                "status": "WARNING" if ov_kpis.get("duplicate_rows", 0) > 0 else "OK",
            })
            kpis.append({
                "title": "Numeric Columns",
                "agg": "COUNT",
                "value": str(ov_kpis.get("numeric_count", 0)),
                "status": "OK",
            })
            kpis.append({
                "title": "Categorical Columns",
                "agg": "COUNT",
                "value": str(ov_kpis.get("categorical_count", 0)),
                "status": "OK",
            })

            report_data.kpis = kpis
            report_data.quality_score = analysis_data.get("quality", {}).get("quality_score", report_data.quality_score)
            report_data.missing_percentage = analysis_data.get("quality", {}).get("missing_pct", report_data.missing_percentage)

        # Attach ML model performance
        ml_models = analysis_data.get("ml_models", [])
        if ml_models:
            report_data.ml_models = ml_models  # type: ignore

        # Attach statistics
        report_data.statistics = analysis_data.get("statistics", {})  # type: ignore
        report_data.quality_detail = analysis_data.get("quality", {})  # type: ignore
        report_data.correlations = analysis_data.get("correlations", {})  # type: ignore
        report_data.distributions = analysis_data.get("distributions", {})  # type: ignore
        report_data.outliers = analysis_data.get("outliers", {})  # type: ignore
        report_data.categorical = analysis_data.get("categorical", {})  # type: ignore
        report_data.insights = analysis_data.get("insights", {})  # type: ignore
        report_data.overview = analysis_data.get("overview", {})  # type: ignore

        return report_data

    @staticmethod
    def _build_report_from_cache(analysis_data: Dict[str, Any]) -> Tuple[Optional[object], Optional[str]]:
        """Build ExecutiveReportData purely from cached analysis results (no AIEngine)."""
        try:
            from ai_engine.domain.entities import (
                ExecutiveReportData, AnomalySummary, AnomalyItem,
                TrendResult, RootCauseItem, BusinessRecommendation,
            )
            from ai_engine.domain.enums import AnomalyMethod, ImpactLevel, TrendDirection

            overview = analysis_data.get("overview", {})
            quality = analysis_data.get("quality", {})
            stats = analysis_data.get("statistics", {})
            kpis_data = overview.get("kpis", {})

            quality_score = quality.get("quality_score", 100.0)
            missing_pct = quality.get("missing_pct", 0.0)

            # Build KPIs
            kpis = [
                {"title": "Total Records", "agg": "COUNT", "value": f"{kpis_data.get('rows', 0):,}", "status": "OK"},
                {"title": "Features", "agg": "COUNT", "value": str(kpis_data.get("columns", 0)), "status": "OK"},
                {"title": "Missing Values", "agg": "SUM", "value": f"{kpis_data.get('missing_values', 0):,}", "status": "WARNING" if missing_pct > 5 else "OK"},
                {"title": "Duplicate Rows", "agg": "COUNT", "value": f"{kpis_data.get('duplicate_rows', 0):,}", "status": "WARNING" if kpis_data.get("duplicate_rows", 0) > 0 else "OK"},
            ]

            # Build summary paragraph
            numeric_stats = stats.get("numeric_stats", [])
            summary_parts = [
                f"Comprehensive analysis of '{analysis_data['dataset_name']}' dataset with {analysis_data['row_count']:,} rows and {analysis_data['col_count']} features.",
                f"Data quality score: {quality_score:.1f}/100 with {missing_pct:.1f}% missing values.",
            ]
            if quality.get("duplicate_rows", 0) > 0:
                summary_parts.append(f"Found {quality['duplicate_rows']} duplicate rows requiring attention.")
            if numeric_stats:
                summary_parts.append(f"Analyzed {len(numeric_stats)} numeric columns for distribution, skewness, and outliers.")

            ml_models = analysis_data.get("ml_models", [])
            if ml_models:
                summary_parts.append(f"{len(ml_models)} trained ML model(s) available for evaluation.")

            report_data = ExecutiveReportData(
                title=f"Analytics Report - {analysis_data['dataset_name']}",
                dataset_name=analysis_data["dataset_name"],
                dataset_shape=(analysis_data["row_count"], analysis_data["col_count"]),
                quality_score=quality_score,
                missing_percentage=missing_pct,
                kpis=kpis,
                summary_paragraph=" ".join(summary_parts),
            )

            # Attach all analysis data
            report_data.statistics = stats  # type: ignore
            report_data.quality_detail = quality  # type: ignore
            report_data.correlations = analysis_data.get("correlations", {})  # type: ignore
            report_data.distributions = analysis_data.get("distributions", {})  # type: ignore
            report_data.outliers = analysis_data.get("outliers", {})  # type: ignore
            report_data.categorical = analysis_data.get("categorical", {})  # type: ignore
            report_data.insights = analysis_data.get("insights", {})  # type: ignore
            report_data.overview = overview  # type: ignore
            report_data.ml_models = ml_models  # type: ignore

            return report_data, None
        except Exception as e:
            return None, f"Failed to build report data: {str(e)}"

    # ── Report Generation Orchestration ──────────────────────────

    @staticmethod
    def generate_report(dataset_id: int, user_id: int, format_type: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Generate a report in the specified format.
        Returns (file_path, error).
        """
        # 1. Gather all analysis data
        analysis_data, error = ReportService.gather_analysis_data(dataset_id, user_id)
        if error or analysis_data is None:
            return None, error or "Failed to gather analysis data."

        # 2. Build ExecutiveReportData
        analysis_data["user_id"] = user_id
        report_data, error = ReportService.build_executive_report_data(analysis_data, user_id)
        if error or report_data is None:
            return None, error or "Failed to build report data."

        # 3. Generate the report in requested format
        output_dir = ReportService.report_directory(user_id)
        os.makedirs(output_dir, exist_ok=True)

        safe_name = analysis_data["dataset_name"].replace(" ", "_").replace("/", "_")

        try:
            if format_type == "pdf":
                filename = f"{safe_name}_Report.pdf"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                result = AIEngine.generate_pdf_report(report_data, output_path)
                if not result:
                    return None, "PDF generation failed. Is fpdf2 installed?"
                return output_path, None

            elif format_type in ("word", "docx"):
                filename = f"{safe_name}_Report.docx"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                result = AIEngine.generate_word_report(report_data, output_path)
                if not result:
                    return None, "Word generation failed. Is python-docx installed?"
                return output_path, None

            elif format_type in ("excel", "xlsx"):
                filename = f"{safe_name}_Report.xlsx"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                result = AIEngine.generate_excel_summary(report_data, output_path)
                if not result:
                    return None, "Excel generation failed."
                return output_path, None

            elif format_type == "pptx":
                filename = f"{safe_name}_Report.pptx"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                result = AIEngine.generate_pptx_summary(report_data, output_path)
                if not result:
                    return None, "PowerPoint generation failed. Is python-pptx installed?"
                return output_path, None

            elif format_type == "html":
                filename = f"{safe_name}_Report.html"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                content = AIEngine.generate_executive_html(report_data)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return output_path, None

            elif format_type == "markdown":
                filename = f"{safe_name}_Report.md"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                content = AIEngine.generate_executive_markdown(report_data)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return output_path, None

            elif format_type == "executive":
                filename = f"{safe_name}_Executive_Report.pdf"
                output_path = os.path.join(output_dir, filename)
                from ai_engine import AIEngine
                result = AIEngine.generate_pdf_report(report_data, output_path)
                if not result:
                    return None, "Executive PDF generation failed."
                return output_path, None

            else:
                return None, f"Unsupported format: {format_type}"

        except Exception as e:
            traceback.print_exc()
            return None, f"Report generation error: {str(e)}"

    # ── Preview Data (for the builder UI) ────────────────────────

    @staticmethod
    def get_report_preview(dataset_id: int, user_id: int) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get a lightweight preview of what the report will contain.
        Used by the builder UI to show available sections and data.
        """
        analysis_data, error = ReportService.gather_analysis_data(dataset_id, user_id)
        if error or analysis_data is None:
            return None, error

        overview = analysis_data.get("overview", {})
        quality = analysis_data.get("quality", {})
        stats = analysis_data.get("statistics", {})
        ml_models = analysis_data.get("ml_models", [])

        preview = {
            "dataset_name": analysis_data["dataset_name"],
            "row_count": analysis_data["row_count"],
            "col_count": analysis_data["col_count"],
            "quality_score": quality.get("quality_score", 100.0),
            "missing_pct": quality.get("missing_pct", 0.0),
            "duplicate_rows": quality.get("duplicate_rows", 0),
            "numeric_columns": len(stats.get("numeric_stats", [])),
            "categorical_columns": len(stats.get("categorical_stats", [])),
            "datetime_columns": len(stats.get("datetime_stats", [])),
            "has_correlations": bool(analysis_data.get("correlations")),
            "has_distributions": bool(analysis_data.get("distributions")),
            "has_outliers": bool(analysis_data.get("outliers")),
            "ml_model_count": len(ml_models),
            "ml_models": [{"id": m["id"], "name": m["model_name"], "algorithm": m["algorithm"], "problem_type": m["problem_type"]} for m in ml_models],
            "available_formats": ["pdf", "html", "pptx", "excel", "word", "executive", "markdown"],
            "sections": [],
        }

        # Build available sections list
        sections = []
        sections.append({"id": "overview", "title": "Executive Summary", "available": bool(overview), "description": "Key performance indicators, dataset schema, and top insights"})
        sections.append({"id": "quality", "title": "Data Quality Assessment", "available": bool(quality), "description": "Missing values, duplicates, consistency and type issues"})
        sections.append({"id": "statistics", "title": "Descriptive Statistics", "available": bool(stats), "description": "Mean, median, standard deviation, skewness, kurtosis for all columns"})
        sections.append({"id": "correlations", "title": "Correlation Analysis", "available": preview["has_correlations"], "description": "Feature correlation matrix and top correlated pairs"})
        sections.append({"id": "distributions", "title": "Distribution Analysis", "available": preview["has_distributions"], "description": "Histogram data and distribution shapes for numeric features"})
        sections.append({"id": "outliers", "title": "Outlier Detection", "available": preview["has_outliers"], "description": "IQR and Z-score based outlier detection results"})
        sections.append({"id": "ml_models", "title": "ML Model Performance", "available": len(ml_models) > 0, "description": f"{len(ml_models)} trained model(s) with evaluation metrics"})
        sections.append({"id": "recommendations", "title": "AI Recommendations", "available": True, "description": "AI-generated strategic business recommendations"})
        preview["sections"] = sections
        # Keep preview responses safe for missing or partial analysis modules.
        for key in ("quality_score", "missing_pct"):
            try:
                preview[key] = float(preview[key] or 0)
            except (TypeError, ValueError):
                preview[key] = 0.0

        return preview, None

    # ── List Previously Generated Reports ────────────────────────

    @staticmethod
    def list_reports(user_id: int) -> List[Dict[str, Any]]:
        """List all previously generated reports for a user."""
        reports_dir = ReportService.report_directory(user_id)
        if not os.path.isdir(reports_dir):
            return []

        reports = []
        for filename in sorted(os.listdir(reports_dir), reverse=True):
            filepath = os.path.join(reports_dir, filename)
            if not os.path.isfile(filepath):
                continue
            stat = os.stat(filepath)
            ext = os.path.splitext(filename)[1].lstrip(".").upper()
            reports.append({
                "filename": filename,
                "format": ext,
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)),
            })
        return reports
