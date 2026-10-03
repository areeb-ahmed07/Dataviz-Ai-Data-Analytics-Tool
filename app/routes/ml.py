"""
DataViz Pro — ML Studio Routes

Blueprint: ml_bp
URL prefix: (none — routes are under /datasets/<id>/ml and /models)

HTML Routes:
  /datasets/<id>/ml              → ML Studio main page
  /models                        → Saved models list

API Routes:
  /api/datasets/<id>/ml/info          → Get dataset info for ML
  /api/datasets/<id>/ml/target         → Analyze target column
  /api/datasets/<id>/ml/features       → Validate feature selection
  /api/datasets/<id>/ml/configure      → Save workflow configuration
  /api/datasets/<id>/ml/prepare        → Prepare data (split + preprocess)
  /api/datasets/<id>/ml/train          → Train models
  /api/datasets/<id>/ml/optimize       → Hyperparameter optimization
  /api/datasets/<id>/ml/results        → Get training results
  /api/datasets/<id>/ml/confusion-matrix → Get confusion matrix
  /api/datasets/<id>/ml/predictions    → Get actual vs predicted
  /api/datasets/<id>/ml/feature-importance → Get feature importance
  /api/datasets/<id>/ml/algorithms     → Get available/recommended algorithms
  /api/datasets/<id>/ml/save           → Save model
  /api/datasets/<id>/ml/clear          → Clear ML cache
  /api/models                          → List saved models
  /api/models/<id>                     → Get model detail
  /api/models/<id>/download            → Download model file
  /api/models/<id>/delete              → Delete model
"""

from flask import Blueprint, render_template, jsonify, request, redirect, url_for, flash, send_file

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService
from app.services.ml_service import MLService

ml_bp = Blueprint("ml", __name__)


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


def _require_model(model_id: int):
    """Verify model exists and user owns it. Returns (user, model_domain, error_response)."""
    user = get_current_user()
    if not user:
        return None, None, (jsonify({"error": "Unauthorized"}), 401)
    model, err = MLService.get_model_detail(user.id, model_id)
    if err or not model:
        return None, None, (jsonify({"error": "Model not found"}), 404)
    return user, model, None


# ── HTML Routes ──────────────────────────────────────────────────

@ml_bp.route("/ml")
@login_required
def index():
    """Dataset selector page for ML Studio."""
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    return render_template(
        "ml/selector.html",
        user=user,
        datasets=datasets,
        active_page="ml"
    )



@ml_bp.route("/datasets/<int:dataset_id>/ml")
@login_required
def studio(dataset_id):
    """ML Studio main page."""
    result = _require_dataset_html(dataset_id)
    user, dataset, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    return render_template(
        "ml/index.html",
        user=user,
        dataset=dataset,
        active_page="ml",
    )


@ml_bp.route("/models")
@login_required
def models_list():
    """Saved models list page."""
    user = get_current_user()
    return render_template(
        "ml/models.html",
        user=user,
        active_page="ml",
    )


# ── API Routes ───────────────────────────────────────────────────

@ml_bp.route('/models/<int:model_id>/predict', methods=['GET', 'POST'])
@login_required
def predict_upload(model_id):
    user, model, error_response = _require_model(model_id)
    if error_response:
        return error_response
    error = None
    if request.method == 'POST':
        from app.services.prediction_service import predict_csv
        try:
            output = predict_csv(user.id, model_id, request.files.get('file'))
            return send_file(output, mimetype='text/csv', as_attachment=True,
                             download_name=f'predictions-{model_id}.csv')
        except ValueError as exc:
            error = str(exc)
        except Exception:
            from flask import current_app
            current_app.logger.exception('Saved-model prediction failed')
            error = 'This model could not generate predictions. Try saving it again from ML Studio.'
    return render_template('ml/predict.html', user=user, model=model, error=error,
                           active_page='ml'), 400 if error else 200


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/info")
@login_required
def api_info(dataset_id):
    """Get dataset info for ML studio."""
    user = get_current_user()
    result, error = MLService.get_dataset_info(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/target")
@login_required
def api_target(dataset_id):
    """Analyze target column."""
    user = get_current_user()
    target = request.args.get("column")
    if not target:
        return jsonify({"error": "Target column is required."}), 400
    result, error = MLService.analyze_target(user.id, dataset_id, target)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/features")
@login_required
def api_features(dataset_id):
    """Validate feature selection."""
    user = get_current_user()
    data = request.args
    target = data.get("target_column")
    features = data.getlist("features")
    problem_type = data.get("problem_type", "classification")
    result, error = MLService.validate_features(user.id, dataset_id, target, features, problem_type)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/configure", methods=["POST"])
@login_required
def api_configure(dataset_id):
    """Save workflow configuration."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    data = request.get_json(silent=True) or {}
    result, error = MLService.save_config(user.id, dataset_id, data)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/prepare", methods=["POST"])
@login_required
def api_prepare(dataset_id):
    """Prepare data for ML."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.prepare_data(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/train", methods=["POST"])
@login_required
def api_train(dataset_id):
    """Train ML models."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result = MLService.start_training_job(user.id, dataset_id)
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/train/status/<job_id>")
@login_required
def api_train_status(dataset_id, job_id):
    """Get status of background training job."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    status_data, error = MLService.get_job_status(job_id, user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 404
    return jsonify(status_data)


@ml_bp.route('/api/datasets/<int:dataset_id>/ml/train/cancel/<job_id>', methods=['POST'])
@login_required
def api_cancel_train(dataset_id, job_id):
    user, dataset, response = _require_dataset(dataset_id)
    if response:
        return response
    result, error = MLService.cancel_job(job_id, user.id, dataset_id)
    return (jsonify(error=error), 404) if error else jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/optimize", methods=["POST"])
@login_required
def api_optimize(dataset_id):
    """Run hyperparameter optimization."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.optimize_model(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/results")
@login_required
def api_results(dataset_id):
    """Get training results."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.get_results(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/confusion-matrix")
@login_required
def api_confusion_matrix(dataset_id):
    """Get confusion matrix."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.get_confusion_matrix(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/predictions")
@login_required
def api_predictions(dataset_id):
    """Get actual vs predicted values."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.get_predictions(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/roc-curve")
@login_required
def api_roc_curve(dataset_id):
    """Get ROC curve data for binary classification."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.get_roc_curve(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/feature-importance")
@login_required
def api_feature_importance(dataset_id):
    """Get feature importance."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    result, error = MLService.get_feature_importance(user.id, dataset_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/algorithms")
@login_required
def api_algorithms(dataset_id):
    """Get available/recommended algorithms."""
    user = get_current_user()
    task_type = request.args.get("task_type", "classification")
    target = request.args.get("target_column")

    if target:
        result, error = MLService.get_recommended_algorithms(user.id, dataset_id, target, task_type)
        if error:
            return jsonify({"error": error}), 400
        return jsonify(result)

    result = MLService.get_available_algorithms(task_type)
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/save", methods=["POST"])
@login_required
def api_save_model(dataset_id):
    """Save trained model."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    data = request.get_json(silent=True) or {}
    # JS sends 'name'; service expects 'custom_name'. Accept both.
    custom_name = data.get("custom_name") or data.get("name")
    result, error = MLService.save_model(
        user.id, dataset_id,
        model_name=data.get("model_name"),
        custom_name=custom_name,
        description=data.get("description"),
    )
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/datasets/<int:dataset_id>/ml/clear", methods=["POST"])
@login_required
def api_clear(dataset_id):
    """Clear ML cache for this dataset."""
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    if MLService.has_active_job(user.id, dataset_id):
        return jsonify(error='Cancel training and wait for it to stop before resetting.'), 409
    MLService.clear_cache(user.id, dataset_id)
    return jsonify({"cleared": True})


# ── Model Management API ────────────────────────────────────────


@ml_bp.route("/api/models")
@login_required
def api_models_list():
    """List all saved models."""
    user = get_current_user()
    result, error = MLService.list_models(user.id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/models/<int:model_id>")
@login_required
def api_model_detail(model_id):
    """Get model detail."""
    user = get_current_user()
    result, error = MLService.get_model_detail(user.id, model_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)


@ml_bp.route("/api/models/<int:model_id>/download")
@login_required
def api_model_download(model_id):
    """Download model file."""
    user = get_current_user()
    filepath, error = MLService.download_model(user.id, model_id)
    if error:
        return jsonify({"error": error}), 404

    import os
    filename = os.path.basename(filepath)
    return send_file(filepath, as_attachment=True, download_name=filename)


@ml_bp.route("/api/models/<int:model_id>/delete", methods=["POST"])
@login_required
def api_model_delete(model_id):
    """Delete a saved model."""
    user = get_current_user()
    result, error = MLService.delete_model(user.id, model_id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(result)
