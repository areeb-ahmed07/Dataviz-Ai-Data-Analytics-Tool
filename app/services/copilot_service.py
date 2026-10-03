"""
Service: AI Copilot — Conversational Analytics Assistant (Phase 9)

Provides intelligent conversational analysis of datasets using the existing
rule-based AI engine (TrendDetector, AnomalyDetector,
RootCauseAnalyzer, RecommendationEngine) with
optional LLM enhancement. Routes user questions to the appropriate
analysis service and returns natural language responses.
"""

import os
import traceback
import threading
import time
import json
from uuid import uuid4
from typing import Dict, Any, Tuple, Optional, List

import numpy as np
import pandas as pd

from auth.database import DatasetDB, ModelDB, get_session
from app.services.dataset_service import DatasetService
from ai_engine import AIEngine
from ai_engine.services.recommendation_engine import RecommendationEngine
from ai_engine.domain.entities import (
    AnomalySummary, BusinessRecommendation, ExecutiveReportData, RootCauseItem, TrendResult,
)
from ai_engine.domain.enums import AnomalyMethod, ImpactLevel, TrendDirection


class _JobStore:
    _jobs: Dict[str, Dict] = {}
    _lock = threading.Lock()

    @classmethod
    def create(cls, job_id: str):
        with cls._lock:
            cls._jobs[job_id] = {"status": "running", "result": None, "error": None, "_created": time.time()}

    @classmethod
    def finish(cls, job_id: str, result: Any):
        with cls._lock:
            entry = cls._jobs.get(job_id)
            if entry:
                entry["status"] = "done"
                entry["result"] = result
    @classmethod
    def fail(cls, job_id: str, error: str):
        with cls._lock:
            entry = cls._jobs.get(job_id)
            if entry:
                entry["status"] = "error"
                entry["error"] = error
    @classmethod
    def get(cls, job_id: str) -> Optional[Dict]:
        with cls._lock:
            return cls._jobs.get(job_id)
    @classmethod
    def cleanup_old(cls, max_age_seconds: int = 900):
        now = time.time()
        with cls._lock:
            expired = [k for k, v in cls._jobs.items() if now - v.get("_created", now) > max_age_seconds]
            for k in expired:
                del cls._jobs[k]

def _serialize_numpy(obj):
    "Recursively convert numpy types for JSON serialization."
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [_serialize_numpy(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _serialize_numpy(v) for k, v in obj.items()}
    return obj


class CopilotService:
    """Conversational AI analytics assistant powered by rule-based AI engine."""
    _MAX_DF_ROWS = 5000
    _MAX_CHAT_HISTORY = 50
    _CHAT_HISTORY: Dict[int, List[Dict]] = {}
    @classmethod
    def start_analysis_job(cls, func, *args, **kwargs):
        """Launch a background analysis job."""
        job_id = f"cop_{uuid4().hex}"
        _JobStore.create(job_id)
        def worker():
            try:
                result, error = func(*args, **kwargs)
                if error:
                    _JobStore.fail(job_id, error)
                else:
                    _JobStore.finish(job_id, _serialize_numpy(result))
            except Exception as e:
                _JobStore.fail(job_id, str(e))
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return {"job_id": job_id, "status": "running"}
    @classmethod
    def get_job_status(cls, job_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        entry = _JobStore.get(job_id)
        if not entry:
            return None, "Job not found."
        _JobStore.cleanup_old()
        if entry["status"] == "done":
            return {"status": "done", "result": entry["result"]}, None
        elif entry["status"] == "error":
            return {"status": "error", "error": entry["error"]}, None
        return {"status": "running"}, None
    # ── Conversation Management ───────────────────────────────────────
    @classmethod
    def get_or_create_chat(cls, dataset_id: int) -> List[Dict]:
        """Get or create a chat session for a dataset."""
        if dataset_id not in cls._CHAT_HISTORY:
            cls._CHAT_HISTORY[dataset_id] = []
        return cls._CHAT_HISTORY[dataset_id]
    @classmethod
    def add_message(cls, dataset_id: int, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add a user message to the chat history."""
        history = cls.get_or_create_chat(dataset_id)
        history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
            "metadata": metadata or {},
        })
    @classmethod
    def get_chat_history(cls, dataset_id: int) -> List[Dict]:
        return cls._CHAT_HISTORY.get(dataset_id, [])
    # ── Intent Detection & Response Generation ────────────────────────────────
    @classmethod
    def detect_intent_and_respond(cls, dataset_id: int, user_message: str, chat_history: List[Dict]) -> Dict[str, Any]:
        """Analyze a user question, detect the intent, run analysis, return NLP response."""
        question = user_message.strip()
        if not question:
            return cls._quick_response("Please ask a question about your dataset to get started.")
        question_lower = question.lower()

        # ── Dataset Stats Query ───────────────────────────────────────────
        stats_queries = [
            (['what', 'how many', 'count', 'size', 'rows', 'columns'],
                lambda q: cls._quick_stats(dataset_id, q)),
        ]
        for patterns, handler in stats_queries:
            if any(p in question_lower for p in patterns):
                return cls._quick_stats(dataset_id, question)
        # ── Column-Specific Queries ────────────────────────────────────
        col_queries = [
            (['describe', 'tell me about', 'what is', 'explain'],
                lambda q: cls._quick_column_info(dataset_id, q)),
            (['which', 'columns', 'features', 'variables'],
                lambda q: cls._quick_columns(dataset_id, q)),
            (['correlation', 'correlate', 'correlated'],
                lambda q: cls._quick_correlations(dataset_id, q)),
            (['missing', 'null', 'missing values', 'missing data'],
                lambda q: cls._quick_missing(dataset_id, q)),
            (['outlier', 'outliers', 'anomalies', 'anomaly'],
                lambda q: cls._quick_anomalies(dataset_id, q)),
            (['trend', 'trends', 'direction', 'growth', 'decline', 'increase'],
                lambda q: cls._quick_trends(dataset_id, q)),
            (['root cause', 'causes', 'why', 'reason'],
                lambda q: cls._quick_root_causes(dataset_id, q)),
            (['recommend', 'suggest', 'recommendation', 'improve', 'action'],
                lambda q: cls._quick_recommendations(dataset_id, q)),
            (['predict', 'prediction', 'model predict'],
                lambda q: cls._quick_model_prediction(dataset_id, q)),
            (['summary', 'summarize', 'executive', 'overview'],
                lambda q: cls._quick_overview(dataset_id, q)),
            (['kpi', 'metric', 'performance', 'score', 'accuracy'],
                lambda q: cls._quick_model_metrics(dataset_id, q)),
            (['quality', 'data quality', 'data quality score'],
                lambda q: cls._quick_quality(dataset_id, q)),
            (['unique', 'distinct', 'duplicates'],
                lambda q: cls._quick_duplicates(dataset_id, q)),
        ]
        for patterns, handler in col_queries:
            if any(p in question_lower for p in patterns):
                return handler(question)
        # ── Conversational Follow-ups ────────────────────────────────────────
        follow_ups = [
            (['follow', 'more', 'detail', 'elaborate', 'expand', 'dig deeper'],
                lambda q: cls._follow_up_analysis(dataset_id, q, chat_history)),
            (['how', 'why', 'can you explain', 'what does'],
                lambda q: cls._explain_insight(dataset_id, q, chat_history)),
            (['compare', 'vs', 'difference'],
                lambda q: cls._quick_comparison(dataset_id, q, chat_history)),
        ]
        for patterns, handler in follow_ups:
            if any(p in question_lower for p in patterns):
                return handler(question)
        # ── Fallback ──────────────────────────────────────────────
        # Check for model-related questions
        model_q = [
            (['model', 'models', 'trained', 'saved model', 'ml model'],
                lambda q: cls._quick_model_info(dataset_id, q)),
        ]
        for patterns, handler in model_q:
            if any(p in question_lower for p in patterns):
                return handler(question)
        # Generic catch-all
        return cls._quick_overview(dataset_id, question)
    @staticmethod
    def _quick_response(answer: str) -> Dict[str, Any]:
        return {"answer": answer}

    @classmethod
    def _quick_stats(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        profile = DatasetService.profile_dataframe(df)
        answer = f"Dataset **{profile.get('row_count', '?')}** has **{profile.get('column_count', '?')}** columns and **{profile.get('total_missing', 0)}** missing values ({profile.get('missing_pct', '0')}% data quality score."
        return {"answer": answer, "intent": "dataset_stats"}
    @classmethod
    def _quick_columns(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        cols = [c for c in df.columns if df[c].dtype in ['number', 'int64', 'float64', 'int32', 'float32', 'Int64', 'Float64']]
        if not cols:
            return {"answer": "No numeric columns found in the dataset.", "intent": "column_info"}
        # Show basic stats for first few columns
        parts = [f"**{c}**: mean={float(df[c].mean()):.2f}, std={float(df[c].std()):.2f}, min={float(df[c].min()):.2f}, max={float(df[c].max()):.2f}" for c in cols[:6]]
        return {"answer": "Numeric columns overview:\n" + '\n'.join(parts), "intent": "column_info"}
    @classmethod
    def _quick_correlations(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return {"answer": "No numeric columns found to compute correlations.", "intent": "correlation_info"}
        corr = numeric.corr()
        pairs = [
            {"column1": str(col1), "column2": str(col2), "correlation": float(corr.iloc[i, j])}
            for i, col1 in enumerate(corr.columns)
            for j, col2 in enumerate(corr.columns)
            if i < j and pd.notna(corr.iloc[i, j])
        ]
        top_pairs = sorted(pairs, key=lambda pair: abs(pair["correlation"]), reverse=True)[:8]
        if not top_pairs:
            return {"answer": "No significant correlations found between numeric columns.", "intent": "correlation_info"}
        parts = [f"**{pair['column1']} / {pair['column2']}**: r={pair['correlation']:.3f}" for pair in top_pairs]
        return {"answer": "Correlation analysis (top pairs):\n" + '\n'.join(parts), "intent": "correlation_info", "data": top_pairs}
    @classmethod
    def _quick_missing(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        missing = df.isna().sum()
        total_missing = int(missing.sum())
        if total_missing == 0:
            return {"answer": "No missing values detected. The dataset appears clean.", "intent": "missing_info"}
        cols_with_missing = missing[missing > 0].index.tolist()
        cols_str = ', '.join(map(str, cols_with_missing[:8]))
        total_cells = int(df.size)
        null_pct = round(total_missing / total_cells * 100, 2) if total_cells else 0
        return {"answer": f"Found missing values in **{len(cols_with_missing)}** columns ({null_pct}% of all cells).\nColumns with missing data: {cols_str}.\nMissing cells may affect analysis accuracy.", "intent": "missing_info", "data": {"columns_missing": cols_with_missing, "total_missing": total_missing, "total_cells": total_cells}}
    @classmethod
    def _quick_trends(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return {"answer": "No numeric columns found to analyze trends.", "intent": "trend_info"}
        trends = []
        for col in numeric.columns[:10]:
            series = df[col].dropna()
            if len(series) < 5:
                continue
            slope, intercept = np.polyfit(range(len(series)), series.values, 1)
            fitted = slope * np.arange(len(series)) + intercept
            total_variance = float(((series - series.mean()) ** 2).sum())
            r2 = 1 - float(((series.values - fitted) ** 2).sum()) / total_variance if total_variance else 0
            if r2 < 0.1:
                continue
            direction = "upward" if slope > 0.001 else ("downward" if slope < -0.001 else "stable")
            pct = ((series.iloc[-1] - series.iloc[0]) / series.iloc[0]) * 100 if series.iloc[0] != 0 else 0
            trends.append({"column": col, "direction": direction, "slope": round(slope, 4), "r2": round(r2, 4), "pct_change": round(pct, 2), "mean": round(series.mean(), 4)})
        if not trends:
            return {"answer": "No significant trends detected in the numeric columns analyzed.", "intent": "trend_info"}
        top = sorted(trends, key=lambda t: abs(t["slope"]), reverse=True)[:5]
        parts = []
        for t in top:
            direction_str = "↗ " if t["direction"] == "upward" else "↘ "
            parts.append(f"**{t['column']}**: {t['direction']} (slope: {t['slope']:.4}, R²={t['r2']:.3f}, {t['pct_change']:+.1f}%)")
        return {"answer": "Trend analysis (top 5):\n" + '\n'.join(parts), "intent": "trend_info", "data": top}
    @classmethod
    def _quick_root_causes(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        # Run a quick analysis on numeric columns
        numeric = df.select_dtypes(include="number")
        if numeric.empty:
            return {"answer": "No numeric columns found for root cause analysis. Root cause analysis requires at least one numeric feature.", "intent": "root_cause_info"}
        # Simple threshold-based analysis
        root_causes = []
        for col in numeric.columns[:6]:
            series = df[col].dropna()
            if len(series) < 10:
                continue
            q25, q75 = series.quantile([0.25, 0.75])
            upper = series.mean() + 2.5 * series.std()
            lower = series.mean() - 2.5 * series.std()
            anomaly_mask = (series > upper) | (series < lower)
            if anomaly_mask.sum() == 0:
                continue
            anomaly_count = int(anomaly_mask.sum())
            if anomaly_count == 0:
                continue
            anomaly_pct = anomaly_count / len(series) * 100
            root_causes.append({
                "feature": col,
                "condition": f"{q25:.1f} < value < {q75:.1f}",
                "affected_rows": anomaly_count,
                "affected_pct": round(anomaly_count / len(series) * 100, 2),
                "description": f"{anomaly_count} rows ({anomaly_pct:.1f}%) of '{col}' fall outside normal range [{lower:.2f}, {upper:.2f}]."
            })
        if not root_causes:
            return {"answer": "No significant root causes detected. All numeric features appear within normal ranges.", "intent": "root_cause_info"}
        top_rc = sorted(root_causes, key=lambda r: r["affected_pct"], reverse=True)[:3]
        parts = []
        for rc in top_rc:
            parts.append(f"**{rc['feature']}**: {rc['condition']} — affects {rc['affected_pct']:.1f}% of rows.\n                Score: {rc['affected_pct'] / 10:.1f}. Description: {rc['description']}")
        return {"answer": f"Root cause analysis (top {len(top_rc)} drivers):\n" + '\n'.join(parts), "intent": "root_cause_info", "data": top_rc}
    @classmethod
    def _quick_recommendations(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        profile = DatasetService.profile_dataframe(df)
        recs = RecommendationEngine()
        recs_list = recs.generate_recommendations(
            summary_data={"dataset_name": "", "dataset_shape": df.shape, "missing_percentage": 100 * profile.get("total_missing", 0) / max(profile.get("total_cells", 0), 1), "duplicate_rows": profile.get("duplicate_count", 0)},
            trends=[], anomalies=None, root_causes=[],
        )
        top = recs_list[:3]
        parts = []
        for rec in top:
            parts.append(f"{rec.title}: {rec.description} (Priority: {rec.impact.value})")
        if not parts:
            return {"answer": "No specific recommendations at this time.", "intent": "recommendation_info"}
        return {"answer": "Recommendations (top 3):\n" + '\n'.join(parts), "intent": "recommendation_info", "data": top}
    @classmethod
    def _quick_model_info(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        db = get_session()
        try:
            models = db.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.is_active == True,
            ).order_by(ModelDB.created_at.desc()).all()
            items = []
            for m in models:
                ds_name = None
                if m.dataset_id:
                    ds = db.query(DatasetDB).filter(DatasetDB.id == m.dataset_id).first()
                    if ds:
                        ds_name = ds.name
                items.append({"id": m.id, "name": m.model_name, "algorithm": m.algorithm, "problem_type": m.problem_type, "dataset_name": ds_name})
            db.close()
        except Exception:
                return {"answer": "No trained models found for this dataset.", "intent": "model_info"}
        if not items:
            return {"answer": "No trained models found for this dataset.", "intent": "model_info"}
        return {"answer": "Available models: " + ', '.join(m['name'] + ' (' + m['algorithm'] + ')' for m in items) + '\n', "intent": "model_info"}
    @classmethod
    def _quick_model_prediction(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        db = get_session()
        try:
            models = db.query(ModelDB).filter(
                ModelDB.user_id == user_id,
                ModelDB.is_active == True,
            ).order_by(ModelDB.created_at.desc()).all()
            db.close()
        except Exception:
                return {"answer": "No trained models found for this dataset.", "intent": "model_info"}
        for m in models:
            if m.dataset_id != dataset_id:
                continue
            if m.problem_type == 'clustering':
                return {"answer": f"The model '{m.model_name}' is a clustering model. Predictions are cluster assignments, not numeric values. Try asking about cluster profiles in the XAI module.", "intent": "model_info"}
            task = m.problem_type
            metrics = {}
            try:
                metrics = json.loads(m.metrics) if m.metrics else {}
            except Exception:
                pass
            primary = m.primary_score
            return {
                "answer": f"Model '{m.model_name}' is a **{task}** model with primary score **{primary}**.\n"
                          f"Metrics: {metrics}\nTo explain specific predictions, use the Prediction Explorer in the XAI module.",
                "intent": "model_info",
                "model_id": m.id,
                "model_name": m.model_name,
            }
    @classmethod
    def _quick_quality(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        profile = DatasetService.profile_dataframe(df)
        qi = profile.get("quality_info", {})
        score = qi.get("quality_score", 0)
        if qi.get("anomalies_detected", 0) > 0:
            return {"answer": f"Data quality score: **{score}**/100. Issues detected: {qi.get('consistency_issues', 0)}, {qi.get('anomalies_detected', 0)} anomalies. Dataset may need cleaning before analysis.", "intent": "quality_info"}
        if score >= 80:
            return {"answer": f"Data quality is good (score: {score}/100). Minimal issues detected.", "intent": "quality_info"}
        elif score >= 50:
            return {"answer": f"Data quality is moderate (score: {score}/100). Consider addressing: {qi.get('missing_pct', 0)}% missing values.", "intent": "quality_info"}
        else:
            return {"answer": f"Data quality is low (score: {score}/100). Significant issues detected: {qi.get('consistency_issues', 0)} consistency issues, {qi.get('anomalies_detected', 0)} anomalies, {qi.get('missing_pct', 0)}% missing values.", "intent": "quality_info"}
    @classmethod
    def _quick_duplicates(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        dups = df.duplicated().sum()
        if dups == 0:
            return {"answer": "No duplicate rows found. The dataset appears unique.", "intent": "duplicate_info"}
        return {"answer": f"Found **{dups}** exact duplicate rows ({dups / len(df) * 100:.1f}%). Consider removing duplicates before analysis to prevent metric inflation.", "intent": "duplicate_info"}
    @classmethod
    def _quick_overview(cls, dataset_id: int, question: str) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        profile = DatasetService.profile_dataframe(df)
        total_cells = profile.get("total_cells", 0)
        missing = profile.get("total_missing", 0)
        missing_pct = missing / total_cells * 100 if total_cells else 0
        dups = profile.get("duplicate_count", 0)
        quality = profile.get("quality_info", {})
        score = quality.get("quality_score", 0)
        summary = (
            f"Dataset **{profile.get('row_count', '?')}** (rows × {profile.get('column_count', '?')} cols). "
            f"Data quality score: {score}/100. " +
            f"Missing values: {missing}/{total_cells} ({missing_pct:.1f}%). " +
            f"Duplicate rows: {dups}."
        )
        return {"answer": summary, "intent": "overview"}
    @classmethod
    def _follow_up_analysis(cls, dataset_id: int, question: str, chat_history: List[Dict]) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        context = ""
        # Check if this is about the same trend
        if chat_history:
            last = chat_history[-1] if chat_history else None
            if last and 'trend' in str(last.get('content', '')) and 'direction' in str(last.get('content', '')):
                last_trend = last.get('data', {})
                return cls._format_trend_response(last_trend)
        # Check for anomaly follow-up
        last_anomaly = None
        for msg in reversed(chat_history):
            if 'anomal' in str(msg.get('content', '')) or 'outlier' in str(msg.get('content', '')):
                last_anomaly = msg.get('data', {})
                break
        if last_anomaly:
            items = last_anomaly.get('items', [])
            if items:
                top = items[0]
                return {"answer": f"Earlier, I detected **{top.get('column', 'unknown')}** as an anomaly (score: {top.get('score', '?')}) in {top.get('affected_pct', '?')}% of rows. {top.get('description', 'No details available.')}", "intent": "followup_anomaly"}
        # Check for root cause follow-up
        for msg in reversed(chat_history):
            if 'root cause' in str(msg.get('content', '')) or 'why' in str(msg.get('content', '')):
                last_rc = msg.get('data', {})
                if last_rc:
                    return {"answer": f"Regarding the root cause you asked about — the key factor was **{last_rc.get('feature', 'unknown')}** affecting {last_rc.get('affected_pct', '?')}% of rows. {last_rc.get('description', 'No details available.')}", "intent": "followup_root_cause"}
        # Check for model prediction follow-up
        for msg in reversed(chat_history):
            if 'predict' in str(msg.get('content', '')) or 'prediction' in str(msg.get('content', '')):
                last_pred = msg.get('data', {})
                if last_pred:
                    return {"answer": f"Regarding the model prediction you mentioned — the predicted value was **{last_pred.get('prediction', '?')}** using model '{last_pred.get('model_name', '?')}'. {last_pred.get('description', 'No details available.')}", "intent": "followup_prediction"}
        # Generic follow-up with current data
        return cls._quick_overview(dataset_id, question)
    @classmethod
    def _format_trend_response(cls, trend: TrendResult) -> str:
        return f"{trend.direction.value} trend in **{trend.column}**: slope = {trend.slope:.4}, R? = {trend.r2_score:.3f}, {trend.pct_change:+.1f}% total change."
    @classmethod
    def _format_anomaly_response(cls, items: list, total_rows: int, pct: float) -> str:
        top_items = items[:5] if items else items
        parts = []
        for a in top_items:
            parts.append(
                f"Row {a.row_index}: **{a.score:.2f}** anomaly score in '{a.column}' (method: {a.method.value}). {a.reason}"
            )
        return f"Detected **{len(items)}** anomalous observations ({pct:.1f}% of data). Top anomalies:\n" + '\n'.join(parts)
    @classmethod
    def _format_root_cause_response(cls, items: list, df_shape: tuple) -> str:
        top_items = items[:5] if items else items
        parts = []
        for rc in top_items:
            parts.append(
                f"**{rc['feature']}**: {rc['condition']} — affects {rc['affected_pct']:.1f}% of rows. Score: {rc['affected_pct'] / 10:.1f}. {rc['description']}"
            )
        return f"Root cause analysis (top {len(items)} drivers):\n" + '\n'.join(parts)
    @classmethod
    def _format_recommendation_response(cls, recs: list) -> str:
        parts = []
        for i, rec in enumerate(recs, 1):
            parts.append(f"{i+1}. **{rec.title}** [{rec.impact.value}]: {rec.category}] — {rec.description}")
        return '\n'.join(parts)
    def _load_df(cls, dataset_id: int) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
        db = get_session()
        try:
            dataset_db = db.query(DatasetDB).filter(
                DatasetDB.id == dataset_id,
                DatasetDB.user_id == user_id,
            ).first()
            if not dataset_db:
                return None, "Dataset not found."
            df = DatasetService.load_dataframe(dataset_db.storage_path, dataset_db.file_format)
            return df, None
        except Exception as e:
            return None, f"Error: {str(e)[:200]}"
        finally:
            db.close()
    @classmethod
    def _quick_comparison(cls, dataset_id: int, question: str, chat_history: List[Dict]) -> Dict[str, Any]:
        df, err = cls._load_df(dataset_id)
        if err:
            return {"answer": f"Could not load dataset: {err}"}
        # Check if comparing specific models
        model_ids_in_q = set()
        for msg in reversed(chat_history):
            m = msg.get('data', {}).get('model_id')
            if m:
                model_ids_in_q.add(int(m))
        if not model_ids_in_q:
            return cls._quick_model_info(dataset_id, question)
        # Otherwise give a general overview comparison
        return cls._quick_overview(dataset_id, question)
