"""
DataViz Pro - Reports Routes (Phase 10)

Full report generation using real analysis data.
Routes serve both HTML pages and JSON API endpoints.
"""
import os
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for, send_file, abort, current_app

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService
from app.services.report_service import ReportService

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route('/files/<filename>')
@login_required
def report_file(filename):
    path = ReportService.resolve_report(get_current_user().id, filename)
    if not path:
        abort(404)
    response = send_file(path, as_attachment=request.args.get('download') == '1', download_name=filename)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@reports_bp.route('/files/<filename>/delete', methods=['POST'])
@login_required
def delete_report(filename):
    user = get_current_user()
    path = ReportService.resolve_report(user.id, filename)
    if not path:
        abort(404)
    destination = 'dashboard.dashboard' if request.form.get('return_to') == 'dashboard' else 'reports.index'
    try:
        os.remove(path)
    except OSError:
        current_app.logger.exception('Could not delete report')
        flash('The report could not be deleted. Please try again.', 'error')
    else:
        from app.core.cache import dashboard_cache
        dashboard_cache.invalidate_user(user.id)
        flash('Report deleted.', 'success')
    return redirect(url_for(destination))


@reports_bp.route("/")
@login_required
def index():
    user = get_current_user()
    datasets = DatasetService.get_user_datasets(user.id)
    previous_reports = ReportService.list_reports(user.id)
    return render_template("reports/index.html", datasets=datasets, reports=previous_reports, active_page="reports")


@reports_bp.route("/<int:dataset_id>/workspace")
@login_required
def workspace(dataset_id):
    user = get_current_user()
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or access denied.", "danger")
        return redirect(url_for("reports.index"))
    return render_template("reports/builder.html", dataset=dataset, active_page="reports")


@reports_bp.route("/api/<int:dataset_id>/preview")
@login_required
def api_preview(dataset_id):
    user = get_current_user()
    preview, error = ReportService.get_report_preview(dataset_id, user.id)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(preview)


@reports_bp.route("/api/<int:dataset_id>/generate", methods=["POST"])
@login_required
def api_generate(dataset_id):
    user = get_current_user()
    data = request.get_json(silent=True) or {}
    ALLOWED_FORMATS = {"pdf", "html", "pptx", "excel", "word", "executive", "markdown"}
    format_type = data.get("format", "pdf").lower()
    if format_type not in ALLOWED_FORMATS:
        return jsonify({"error": f"Invalid format '{format_type}'. Allowed: {', '.join(sorted(ALLOWED_FORMATS))}"}), 400

    file_path, error = ReportService.generate_report(dataset_id, user.id, format_type)
    if error:
        return jsonify({"error": error}), 400

    filename = os.path.basename(file_path)
    return jsonify({
        "success": True,
        "filename": filename,
        "format": format_type,
        "download_url": url_for('reports.download_report', dataset_id=dataset_id, format=format_type),
    })


@reports_bp.route("/<int:dataset_id>/download")
@login_required
def download_report(dataset_id):
    user = get_current_user()
    data = request.args
    format_type = data.get("format", "pdf").lower()

    requested = request.args.get("filename", "")
    file_path = None
    error = None
    if requested:
        safe_requested = os.path.basename(requested)
        candidate = os.path.abspath(os.path.join("app", "static", "reports", str(user.id), safe_requested))
        report_root = os.path.abspath(os.path.join("app", "static", "reports", str(user.id)))
        if os.path.dirname(candidate) == report_root and os.path.isfile(candidate):
            file_path = candidate
        else:
            error = "Requested report file was not found. Please generate it again."
    if not file_path and not error:
        file_path, error = ReportService.generate_report(dataset_id, user.id, format_type)
    if error:
        flash(f"Error generating report: {error}", "danger")
        return redirect(request.referrer or url_for('reports.index'))

    return send_file(os.path.abspath(file_path), as_attachment=True, download_name=os.path.basename(file_path))


@reports_bp.route("/api/<int:dataset_id>/history")
@login_required
def api_history(dataset_id):
    user = get_current_user()
    reports = ReportService.list_reports(user.id)
    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if dataset and dataset.name:
        safe_name = dataset.name.replace(" ", "_").replace("/", "_")
        reports = [r for r in reports if safe_name in r.get("filename", "")]
    return jsonify(reports)
