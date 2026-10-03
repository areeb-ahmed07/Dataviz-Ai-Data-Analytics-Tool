"""
DataViz Pro — Explainable AI (XAI) Routes (Phase 8)

Blueprint: xai_bp

HTML Routes:
  /xai                            → XAI model selection page
  /models/<id>/explain             → XAI workspace for a model
  /models/<id>/explain/global      → Global explanations page
  /models/<id>/explain/local       → Local explanations page
  /models/<id>/explain/prediction  → Prediction explanation page

API Routes (matching JS expectations):
  /api/xai/models                              → List explainable models
  /api/xai/models/<id>/summary                  → Model summary
  /api/xai/models/<id>/overview                 → Overview (top features, performance)
  /api/xai/models/<id>/global/feature-importance → Native feature importance
  /api/xai/models/<id>/global/permutation-importance → Permutation importance
  /api/xai/models/<id>/global/shap/global        → SHAP global importance (async)
  /api/xai/models/<id>/global/shap/summary       → SHAP summary beeswarm (async)
  /api/xai/models/<id>/global/shap/dependence    → SHAP dependence plot (async)
  /api/xai/models/<id>/global/comparison         → Importance comparison
  /api/xai/models/<id>/local/shap                → SHAP local explanation (async)
  /api/xai/models/<id>/local/lime                → LIME local explanation (async)
  /api/xai/models/<id>/predict                   → Prediction explanation (async)
  /api/models/<id>/xai/status/<job_id>           → Job status polling
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash

from app.auth_helpers import login_required, get_current_user
from app.services.xai_service import XAIService

xai_bp = Blueprint("xai", __name__)


# ── Helper ──────────────────────────────────────────────────────

def _require_model(model_id: int):
    """Verify model exists and user owns it. Returns (user, model_metadata, error_response)."""
    user = get_current_user()
    if not user:
        return None, None, (jsonify({"error": "Unauthorized"}), 401)
    model, err = XAIService.get_model_summary(user.id, model_id)
    if err or not model:
        return None, None, (jsonify({"error": "Model not found"}), 404)
    return user, model, None


def _require_model_html(model_id: int):
    """Same as above but returns redirect for HTML routes."""
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return None, None, redirect(url_for("auth.login"))
    model, err = XAIService.get_model_summary(user.id, model_id)
    if err or not model:
        flash("Model not found or you do not have access.", "error")
        return None, None, redirect(url_for("xai.model_selection"))
    return user, model, None


# ── HTML Routes ────────────────────────────────────────────────────


@xai_bp.route("/xai")
@login_required
def model_selection():
    """XAI model selection page."""
    user = get_current_user()
    return render_template(
        "xai/index.html",
        user=user,
        active_page="xai",
    )


@xai_bp.route("/models/<int:model_id>/explain")
@login_required
def explain(model_id):
    """XAI workspace main page for a model."""
    result = _require_model_html(model_id)
    user, model, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    return render_template(
        "xai/workspace.html",
        user=user,
        model=model,
        model_id=model_id,
        model_name=model.get("model_name", "Model"),
        active_page="xai",
    )


@xai_bp.route("/models/<int:model_id>/explain/global")
@login_required
def explain_global(model_id):
    """Global explanations page."""
    result = _require_model_html(model_id)
    user, model, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    return render_template(
        "xai/global.html",
        user=user,
        model=model,
        model_id=model_id,
        model_name=model.get("model_name", "Model"),
        active_page="xai",
    )


@xai_bp.route("/models/<int:model_id>/explain/local")
@login_required
def explain_local(model_id):
    """Local explanations page."""
    result = _require_model_html(model_id)
    user, model, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    return render_template(
        "xai/local.html",
        user=user,
        model=model,
        model_id=model_id,
        model_name=model.get("model_name", "Model"),
        active_page="xai",
    )


@xai_bp.route("/models/<int:model_id>/explain/prediction")
@login_required
def explain_prediction(model_id):
    """Prediction explanation page."""
    result = _require_model_html(model_id)
    user, model, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    return render_template(
        "xai/prediction.html",
        user=user,
        model=model,
        model_id=model_id,
        model_name=model.get("model_name", "Model"),
        active_page="xai",
    )


# ── API Routes ───────────────────────────────────────────────────


@xai_bp.route("/api/xai/models")
@login_required
def api_list_models():
    """List all explainable models."""
    user = get_current_user()
    result, error = XAIService.list_explainable_models(user.id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"models": result})


@xai_bp.route("/api/xai/models/<int:model_id>/summary")
@login_required
def api_summary(model_id):
    """Get model summary for XAI workspace."""
    user = get_current_user()
    result, error = XAIService.get_model_summary(user.id, model_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/overview")
@login_required
def api_overview(model_id):
    """Get overview data for workspace (top features, performance, warnings)."""
    user = get_current_user()
    result, error = XAIService.get_overview(user.id, model_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


# ── Global Explanation APIs ──────────────────────────────────────


@xai_bp.route("/api/xai/models/<int:model_id>/global/feature-importance")
@login_required
def api_global_feature_importance(model_id):
    """Get native feature importance."""
    user = get_current_user()
    top_n = request.args.get("top_n", 20, type=int)
    result, error = XAIService.get_feature_importance(user.id, model_id, top_n=top_n)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/global/permutation-importance")
@login_required
def api_global_permutation_importance(model_id):
    """Get permutation importance."""
    user = get_current_user()
    top_n = request.args.get("top_n", 20, type=int)
    sample_size = request.args.get("sample_size", type=int)
    n_repeats = request.args.get("n_repeats", 5, type=int)
    result, error = XAIService.get_permutation_importance(
        user.id, model_id, top_n=top_n, sample_size=sample_size, n_repeats=n_repeats
    )
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/global/shap/global")
@login_required
def api_global_shap_global(model_id):
    """Get SHAP global feature importance (async)."""
    user = get_current_user()
    top_n = request.args.get("top_n", 20, type=int)
    sample_size = request.args.get("sample_size", type=int)
    result = XAIService.start_xai_job(
        XAIService.get_shap_global, user.id, model_id,
        top_n=top_n, sample_size=sample_size
    )
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/global/shap/summary")
@login_required
def api_global_shap_summary(model_id):
    """Get SHAP summary data for beeswarm visualisation (async)."""
    user = get_current_user()
    max_features = request.args.get("max_features", 20, type=int)
    sample_size = request.args.get("sample_size", type=int)
    result = XAIService.start_xai_job(
        XAIService.get_shap_summary_data, user.id, model_id,
        max_features=max_features, sample_size=sample_size
    )
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/global/shap/dependence")
@login_required
def api_global_shap_dependence(model_id):
    """Get SHAP dependence plot data (async)."""
    user = get_current_user()
    feature_index = request.args.get("feature_index", 0, type=int)
    sample_size = request.args.get("sample_size", type=int)
    result = XAIService.start_xai_job(
        XAIService.get_shap_dependence, user.id, model_id,
        feature_index=feature_index, sample_size=sample_size
    )
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/global/comparison")
@login_required
def api_global_comparison(model_id):
    """Get feature importance comparison across methods."""
    user = get_current_user()
    top_n = request.args.get("top_n", 15, type=int)
    result, error = XAIService.get_importance_comparison(user.id, model_id, top_n=top_n)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


# ── Local Explanation APIs ──────────────────────────────────────


@xai_bp.route("/api/xai/models/<int:model_id>/local/shap")
@login_required
def api_local_shap(model_id):
    """Get SHAP local explanation for a single observation (async)."""
    user = get_current_user()
    row_index = request.args.get("row_index", 0, type=int)
    result = XAIService.start_xai_job(
        XAIService.get_shap_local, user.id, model_id, row_index=row_index
    )
    return jsonify(result)


@xai_bp.route("/api/xai/models/<int:model_id>/local/lime")
@login_required
def api_local_lime(model_id):
    """Get LIME local explanation for a single observation (async)."""
    user = get_current_user()
    row_index = request.args.get("row_index", 0, type=int)
    num_features = request.args.get("num_features", 10, type=int)
    result = XAIService.start_xai_job(
        XAIService.get_lime_local, user.id, model_id, row_index=row_index, num_features=num_features
    )
    return jsonify(result)


# ── Prediction Explanation API ───────────────────────────────────


@xai_bp.route("/api/xai/models/<int:model_id>/predict")
@login_required
def api_prediction(model_id):
    """Get prediction explanation for a single observation (async)."""
    user = get_current_user()
    row_index = request.args.get("row_index", 0, type=int)
    result = XAIService.start_xai_job(
        XAIService.get_prediction_explanation, user.id, model_id, row_index=row_index
    )
    return jsonify(result)


# ── Job Status (used by polling) ─────────────────────────────────


@xai_bp.route("/api/models/<int:model_id>/xai/status/<job_id>")
@login_required
def api_xai_status(model_id, job_id):
    """Get status of a background XAI job."""
    user = get_current_user()
    model, err = XAIService.get_model_summary(user.id, model_id)
    if err or not model:
        return jsonify({"error": "Model not found"}), 404

    status_data, error = XAIService.get_job_status(job_id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(status_data)


# ── Additional API endpoints for backward compatibility ──────────


@xai_bp.route("/api/models/<int:model_id>/xai/feature-importance")
@login_required
def api_legacy_feature_importance(model_id):
    """Backward-compat: native feature importance."""
    user = get_current_user()
    top_n = request.args.get("top_n", 20, type=int)
    result, error = XAIService.get_feature_importance(user.id, model_id, top_n=top_n)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/models/<int:model_id>/xai/permutation")
@login_required
def api_legacy_permutation(model_id):
    """Backward-compat: permutation importance."""
    user = get_current_user()
    top_n = request.args.get("top_n", 20, type=int)
    sample_size = request.args.get("sample_size", type=int)
    result, error = XAIService.get_permutation_importance(user.id, model_id, top_n=top_n, sample_size=sample_size)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/models/<int:model_id>/xai/comparison")
@login_required
def api_legacy_comparison(model_id):
    """Backward-compat: importance comparison."""
    user = get_current_user()
    top_n = request.args.get("top_n", 15, type=int)
    result, error = XAIService.get_importance_comparison(user.id, model_id, top_n=top_n)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/models/<int:model_id>/xai/cluster-profile")
@login_required
def api_legacy_cluster_profile(model_id):
    """Backward-compat: cluster profiles."""
    user = get_current_user()
    result, error = XAIService.get_cluster_profiles(user.id, model_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@xai_bp.route("/api/models/<int:model_id>/xai/limitations")
@login_required
def api_legacy_limitations(model_id):
    """Backward-compat: model limitations."""
    user = get_current_user()
    result, error = XAIService.get_model_limitations(user.id, model_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)
