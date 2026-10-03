"""
DataViz Pro — Visualization Routes (Phase 13: Cached)
"""
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
import json

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService

visualization_bp = Blueprint("visualization", __name__, url_prefix="/visualization")

@visualization_bp.route("/")
@login_required
def index():
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return render_template("visualization/index.html", datasets=datasets, active_page="visualization")

@visualization_bp.route("/<int:dataset_id>/workspace")
@login_required
def workspace(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("visualization.index"))

    load_chart_id = request.args.get("load_chart")
    loaded_config = None
    if load_chart_id:
        from auth.database import get_session, SavedChartDB
        db = get_session()
        try:
            chart = db.query(SavedChartDB).filter(
                SavedChartDB.id == load_chart_id,
                SavedChartDB.user_id == user.id
            ).first()
            if chart:
                loaded_config = chart.config
        finally:
            db.close()

    return render_template("visualization/workspace.html", dataset=dataset, loaded_config=loaded_config, active_page="visualization")

@visualization_bp.route("/api/<int:dataset_id>/data")
@login_required
def api_data(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    chart_type = request.args.get("chart_type", "")
    x_col = request.args.get("x")
    y_col = request.args.get("y")
    z_col = request.args.get("z")
    agg_func = request.args.get("agg", "none")

    # ── Use DataFrame cache key ──────────────────────────
    from app.core.cache import _make_key
    df_cache_key = _make_key(user.id, dataset_id, "df")
    df, error = DatasetService.load_dataframe(dataset.storage_path, dataset.file_format, _cache_key=df_cache_key)
    if error or df is None:
        return jsonify({"error": error or "Failed to load dataset"}), 400

    from app.services.chart_service import prepare_chart_data
    try:
        return jsonify(prepare_chart_data(df, chart_type, x_col, y_col, z_col, agg_func))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
# ── Save & Export Charts ──────────────────────────────────────────

@visualization_bp.route("/<int:dataset_id>/save", methods=["POST"])
@login_required
def save_chart(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    name = data.get("name", "").strip()[:200]
    # Remove any HTML/script tags from chart name
    import re
    name = re.sub(r"<[^>]*>", "", name).strip()
    if not name:
        return jsonify({"error": "Chart name is required"}), 400

    chart_type = data.get("chart_type")
    config = data.get("config")
    if not isinstance(config, dict):
        return jsonify({"error": "Chart configuration is required"}), 400
    from auth.database import get_session, SavedChartDB
    db = get_session()
    try:
        new_chart = SavedChartDB(
            user_id=user.id,
            dataset_id=dataset_id,
            name=name,
            chart_type=chart_type,
            config=json.dumps(config)
        )
        db.add(new_chart)
        db.commit()
        return jsonify({"message": "Chart saved successfully", "id": new_chart.id})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

@visualization_bp.route("/saved")
@login_required
def saved_charts():
    """Saved charts page."""
    user = get_current_user()
    from auth.database import get_session, SavedChartDB
    db = get_session()
    try:
        charts = (db.query(SavedChartDB)
            .filter(SavedChartDB.user_id == user.id)
            .order_by(SavedChartDB.created_at.desc())
            .all())
        datasets = DatasetService.get_user_datasets(user.id)
        ds_map = {ds.id: ds.name for ds in datasets}
        return render_template("visualization/saved.html", charts=charts, ds_map=ds_map, active_page="visualization")
    finally:
        db.close()

@visualization_bp.route("/saved/<int:chart_id>", methods=["DELETE"])
@login_required
def delete_chart(chart_id):
    user = get_current_user()
    from auth.database import get_session, SavedChartDB
    db = get_session()
    try:
        chart = db.query(SavedChartDB).filter(
            SavedChartDB.id == chart_id,
            SavedChartDB.user_id == user.id
        ).first()
        if not chart:
            return jsonify({"error": "Chart not found"}), 404
        db.delete(chart)
        db.commit()
        return jsonify({"message": "Chart deleted successfully"})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()

