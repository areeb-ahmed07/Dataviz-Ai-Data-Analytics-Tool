"""
DataViz Pro — AI Copilot Routes
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService
from ai_engine import AIEngine

copilot_bp = Blueprint("copilot", __name__, url_prefix="/copilot")

@copilot_bp.route("/")
@login_required
def index():
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return render_template("copilot/index.html", datasets=datasets, active_page="ai-copilot")

@copilot_bp.route("/<int:dataset_id>/workspace")
@login_required
def workspace(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("copilot.index"))
        
    return render_template("copilot/workspace.html", dataset=dataset, active_page="ai-copilot")

@copilot_bp.route("/api/<int:dataset_id>/insights", methods=["GET"])
@login_required
def api_insights(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404
        
    df, error = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format)
    if error or df is None:
        return jsonify({"error": error or "Failed to load dataset"}), 400
        
    try:
        engine = AIEngine(df, dataset_name=dataset.name)
        # Analyze once, preserving row order and using the same results throughout.
        report = engine.run_full_ai_analysis()
        trends = report.trends
        anomalies = report.anomalies
        root_causes = report.root_causes
        recommendations = report.recommendations
        
        # Serialize to dicts
        result = {
            "trends": [
                {
                    "column": t.column, 
                    "direction": t.direction.value if hasattr(t.direction, 'value') else str(t.direction), 
                    "pct_change": t.pct_change,
                    "description": t.summary_text
                } for t in trends
            ],
            "anomalies": {
                "count": anomalies.anomalous_rows_count,
                "percentage": anomalies.anomaly_percentage,
                "items": [
                    {
                        "index": a.row_index,
                        "score": a.score, 
                        "description": a.reason,
                        "method": a.method.value if hasattr(a.method, 'value') else str(a.method)
                    } for a in sorted(anomalies.detected_anomalies, key=lambda item: item.score, reverse=True)[:5]
                ]
            },
            "root_causes": [
                {
                    "feature": r.feature,
                    "description": r.description,
                    "impact_score": r.impact_score,
                    "condition": r.condition,
                    "affected_rows": r.affected_rows
                } for r in root_causes
            ],
            "recommendations": [
                {
                    "title": rec.title, 
                    "description": rec.description, 
                    "expected_impact": rec.impact.value,
                    "action_items": rec.action_items
                } for rec in recommendations
            ]
        }
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
