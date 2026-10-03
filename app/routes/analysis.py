"""
DataViz Pro — Analysis Routes

Blueprint: analysis_bp
URL prefix: /analysis

HTML Routes (9):
  /                         → Dataset selector page
  /<int:dataset_id>         → Redirect to overview
  /<int:dataset_id>/overview
  /<int:dataset_id>/quality
  /<int:dataset_id>/statistics
  /<int:dataset_id>/correlations
  /<int:dataset_id>/distributions
  /<int:dataset_id>/outliers
  /<int:dataset_id>/categorical
  /<int:dataset_id>/insights

API Routes (8):
  /api/datasets             → User's datasets for selector
  /api/<int:dataset_id>/overview
  /api/<int:dataset_id>/quality
  /api/<int:dataset_id>/statistics
  /api/<int:dataset_id>/correlations
  /api/<int:dataset_id>/distribution?column=X
  /api/<int:dataset_id>/outliers
  /api/<int:dataset_id>/categorical?column=X
  /api/<int:dataset_id>/insights
  /api/<int:dataset_id>/columns
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService
from app.services.analysis_service import AnalysisService

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")


# ── HTML Routes ──────────────────────────────────────────────────


@analysis_bp.route("/")
@login_required
def index():
    """Dataset selector page for the Analysis Workspace."""
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return render_template("analysis/index.html", datasets=datasets, active_page="analysis")


@analysis_bp.route("/<int:dataset_id>")
@login_required
def redirect_to_overview(dataset_id):
    """Redirect /analysis/<id> to /analysis/<id>/overview."""
    return redirect(url_for("analysis.overview", dataset_id=dataset_id))


@analysis_bp.route("/<int:dataset_id>/overview")
@login_required
def overview(dataset_id):
    """Overview page: KPI cards, schema table, quality summary, insights preview."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/overview.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="overview",
    )


@analysis_bp.route("/<int:dataset_id>/quality")
@login_required
def quality(dataset_id):
    """Quality analysis page."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/quality.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="quality",
    )


@analysis_bp.route("/<int:dataset_id>/statistics")
@login_required
def statistics(dataset_id):
    """Descriptive statistics page."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/statistics.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="statistics",
    )


@analysis_bp.route("/<int:dataset_id>/correlations")
@login_required
def correlations(dataset_id):
    """Correlation analysis page."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/correlations.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="correlations",
    )


@analysis_bp.route("/<int:dataset_id>/distributions")
@login_required
def distributions(dataset_id):
    """Distribution analysis page with column selector."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/distributions.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="distributions",
    )


@analysis_bp.route("/<int:dataset_id>/outliers")
@login_required
def outliers(dataset_id):
    """Outlier detection page."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/outliers.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="outliers",
    )


@analysis_bp.route("/<int:dataset_id>/categorical")
@login_required
def categorical(dataset_id):
    """Categorical analysis page with column selector."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/categorical.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="categorical",
    )


@analysis_bp.route("/<int:dataset_id>/timeseries")
@login_required
def timeseries(dataset_id):
    """Time Series analysis page."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/timeseries.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="timeseries",
    )


@analysis_bp.route("/<int:dataset_id>/insights")
@login_required
def insights(dataset_id):
    """AI-powered insights page."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("analysis.index"))

    return render_template(
        "analysis/insights.html",
        dataset=dataset,
        active_page="analysis",
        active_analysis="insights",
    )


# ── API Routes ────────────────────────────────────────────────────


@analysis_bp.route("/api/datasets")
@login_required
def api_datasets():
    """Return user's datasets as JSON for the selector."""
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return jsonify([
        {
            "id": ds.id,
            "name": ds.name,
            "file_format": ds.file_format,
            "row_count": ds.row_count,
            "column_count": ds.column_count,
            "created_at": ds.created_at.isoformat() if ds.created_at else None,
        }
        for ds in datasets
    ])


@analysis_bp.route("/api/<int:dataset_id>/overview")
@login_required
def api_overview(dataset_id):
    """API: Overview data."""
    user = get_current_user()
    result, error = AnalysisService.get_overview(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/quality")
@login_required
def api_quality(dataset_id):
    """API: Quality analysis data."""
    user = get_current_user()
    result, error = AnalysisService.get_quality(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/statistics")
@login_required
def api_statistics(dataset_id):
    """API: Descriptive statistics."""
    user = get_current_user()
    result, error = AnalysisService.get_statistics(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/correlations")
@login_required
def api_correlations(dataset_id):
    """API: Correlation matrix and strong correlations."""
    user = get_current_user()
    result, error = AnalysisService.get_correlations(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/distribution")
@login_required
def api_distribution(dataset_id):
    """API: Distribution data for a specific column."""
    column = request.args.get("column", "")
    if not column:
        return jsonify({"error": "Column parameter is required."}), 400

    user = get_current_user()
    result, error = AnalysisService.get_distribution(dataset_id, user.id, column)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/outliers")
@login_required
def api_outliers(dataset_id):
    """API: Outlier detection results."""
    user = get_current_user()
    result, error = AnalysisService.get_outliers(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/categorical")
@login_required
def api_categorical(dataset_id):
    """API: Categorical frequency analysis."""
    column = request.args.get("column", "")
    user = get_current_user()
    result, error = AnalysisService.get_categorical_analysis(dataset_id, user.id, column or None)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/timeseries")
@login_required
def api_timeseries(dataset_id):
    """API: Time series analysis."""
    date_col = request.args.get("date_col", "")
    value_col = request.args.get("value_col", "")
    user = get_current_user()
    result, error = AnalysisService.get_timeseries_analysis(dataset_id, user.id, date_col or None, value_col or None)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/insights")
@login_required
def api_insights(dataset_id):
    """API: AI-generated insights."""
    user = get_current_user()
    result, error = AnalysisService.get_insights(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)


@analysis_bp.route("/api/<int:dataset_id>/columns")
@login_required
def api_columns(dataset_id):
    """API: Dataset column list with types."""
    user = get_current_user()
    result, error = AnalysisService.get_dataset_columns(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(result)
