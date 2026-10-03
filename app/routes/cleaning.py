"""
DataViz Pro — Cleaning Routes

Blueprint: cleaning_bp
URL prefix: (none — routes are under /datasets/<id>/clean)

HTML Routes (2):
  /datasets/<id>/clean              → Cleaning Studio main page
  /datasets/<id>/clean/versions     → Dataset versions page

API Routes (9):
  /api/datasets/<id>/clean/detect       → Detect quality problems
  /api/datasets/<id>/clean/preview      → Preview a single operation
  /api/datasets/<id>/clean/apply         → Apply a single operation
  /api/datasets/<id>/clean/undo          → Undo last operation
  /api/datasets/<id>/clean/reset         → Reset to original
  /api/datasets/<id>/clean/history       → Get operation history
  /api/datasets/<id>/clean/preview-data  → Get current preview data
  /api/datasets/<id>/clean/save          → Save cleaned dataset
  /api/datasets/<id>/clean/columns       → Get column info
  /api/datasets/<id>/clean/versions      → Get dataset versions
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService, FORMAT_LABELS
from app.services.cleaning_service import CleaningService

cleaning_bp = Blueprint("cleaning", __name__)


# ── Helper ──────────────────────────────────────────────────────

def _require_dataset(dataset_id: int):
    """Verify dataset exists and user owns it. Returns (user, dataset, error_response)."""
    user = get_current_user()
    if not user:
        return None, None, (jsonify({"error": "Unauthorized"}), 401)

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return None, None, (jsonify({"error": "Dataset not found"}), 404)

    return user, dataset, None


def _require_dataset_html(dataset_id: int):
    """Same as above but returns redirect for HTML routes."""
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return None, None, redirect(url_for("auth.login"))

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or you do not have access.", "error")
        return None, None, redirect(url_for("datasets.index"))

    return user, dataset, None


# ── HTML Routes ──────────────────────────────────────────────────

@cleaning_bp.route("/cleaning")
@login_required
def index():
    """Dataset selector page for the Cleaning Studio."""
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return render_template(
        "cleaning/index.html",
        user=user,
        datasets=datasets,
        active_page="cleaning"
    )



@cleaning_bp.route("/datasets/<int:dataset_id>/clean")
@login_required
def studio(dataset_id):
    """Cleaning Studio main page."""
    result = _require_dataset_html(dataset_id)
    user, dataset, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    # Check if this is a child dataset
    if dataset.parent_dataset_id:
        flash("This is a cleaned dataset. To clean further, work with the original or this version directly.", "info")

    return render_template(
        "cleaning/studio.html",
        user=user,
        dataset=dataset,
        format_labels=FORMAT_LABELS,
        active_page="cleaning",
    )


@cleaning_bp.route("/datasets/<int:dataset_id>/clean/versions")
@login_required
def versions(dataset_id):
    """Dataset versions page."""
    result = _require_dataset_html(dataset_id)
    user, dataset, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    return render_template(
        "cleaning/versions.html",
        user=user,
        dataset=dataset,
        format_labels=FORMAT_LABELS,
        active_page="cleaning",
    )


# ── API Routes ───────────────────────────────────────────────────


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/detect")
@login_required
def api_detect(dataset_id):
    """API: Detect data quality problems."""
    user = get_current_user()
    result, error = CleaningService.detect_problems(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/preview", methods=["POST"])
@login_required
def api_preview(dataset_id):
    """API: Preview a single cleaning operation."""
    user = get_current_user()

    # Verify ownership
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    data = request.get_json(silent=True) or {}
    if not data.get("type"):
        return jsonify({"error": "Operation type is required."}), 400

    result, error = CleaningService.preview_operation(user.id, dataset_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/apply", methods=["POST"])
@login_required
def api_apply(dataset_id):
    """API: Apply a cleaning operation."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    data = request.get_json(silent=True) or {}
    if not data.get("type"):
        return jsonify({"error": "Operation type is required."}), 400

    result, error = CleaningService.apply_operation(user.id, dataset_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/undo", methods=["POST"])
@login_required
def api_undo(dataset_id):
    """API: Undo last operation."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = CleaningService.undo_last(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/reset", methods=["POST"])
@login_required
def api_reset(dataset_id):
    """API: Reset all changes."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = CleaningService.reset(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/history")
@login_required
def api_history(dataset_id):
    """API: Get cleaning operation history."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = CleaningService.get_history(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/preview-data")
@login_required
def api_preview_data(dataset_id):
    """API: Get current working state preview data."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = CleaningService.get_preview_data(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/save", methods=["POST"])
@login_required
def api_save(dataset_id):
    """API: Save cleaned dataset as new version."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    data = request.get_json(silent=True) or {}
    name = data.get("name")

    result, error = CleaningService.save_cleaned_dataset(user.id, dataset_id, name)
    if error:
        return jsonify({"error": error}), 400

    # Clear pipeline cache for the new dataset
    if result and result.get("id"):
        CleaningService.clear_pipeline(user.id, dataset_id)

    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/columns")
@login_required
def api_columns(dataset_id):
    """API: Get column info for current working state."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = CleaningService.get_column_info(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@cleaning_bp.route("/api/datasets/<int:dataset_id>/clean/versions")
@login_required
def api_versions(dataset_id):
    """API: Get dataset versions (parent + children)."""
    user = get_current_user()

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = CleaningService.get_dataset_versions(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)
