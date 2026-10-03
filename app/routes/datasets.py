"""
DataViz Pro — Datasets Blueprint

Routes for dataset upload, listing, detail view,
preview, download, and deletion. All routes require
authentication and enforce user ownership.
"""

import os

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, send_file, jsonify, current_app
)
import pandas as pd

from app.auth_helpers import login_required, get_current_user
from app.services.dataset_service import DatasetService, FORMAT_LABELS
from connectors.domain.enums import DataSourceType
from connectors.domain.entities import ConnectionConfig, QueryConfig
from app.security import (
    AuditService, check_rate_limit, rate_limit_exceeded_response,
    validate_sql_query, validate_table_name, validate_api_url,
    sanitize_user_input, _get_client_ip,
)

datasets_bp = Blueprint("datasets", __name__)


# ── Helper ──────────────────────────────────────────────────────

def _require_dataset_owner(dataset_id: int):
    """
    Verify the current user owns the dataset.
    Returns (user, dataset) or redirects with flash.
    """
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return None, None, redirect(url_for("auth.login"))

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        flash("Dataset not found or you do not have access.", "error")
        return None, None, redirect(url_for("datasets.index"))

    return user, dataset, None


# ── Dataset List ─────────────────────────────────────────────────

@datasets_bp.route("/datasets")
@login_required
def index():
    """List all datasets belonging to the current user."""
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    search = request.args.get("q", "").strip()
    format_filter = request.args.get("format", "").strip()
    
    datasets = DatasetService.get_user_datasets(user.id, search=search)
    
    if format_filter:
        datasets = [d for d in datasets if d.file_format == format_filter]

    return render_template(
        "datasets/index.html",
        user=user,
        datasets=datasets,
        search=search,
        format_filter=format_filter,
        format_labels=FORMAT_LABELS,
    )


# ── Upload Page ───────────────────────────────────────────────────

@datasets_bp.route("/datasets/upload")
@login_required
def upload_page():
    """Display the dataset upload form."""
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    return render_template(
        "datasets/upload.html",
        user=user,
        max_size_mb=int(current_app.config.get("MAX_CONTENT_LENGTH", 52428800) / (1024 * 1024)),
    )


# ── Upload Handler ────────────────────────────────────────────────

@datasets_bp.route("/datasets/upload", methods=["POST"])
@login_required
def upload():
    """Handle dataset file upload, validation, profiling, and storage."""
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    # ── Rate limit check (Phase 14) ───────────────────────
    allowed, remaining, _ = check_rate_limit("upload")
    if not allowed:
        return rate_limit_exceeded_response("upload", remaining, 3600)

    if "file" not in request.files:
        flash("No file selected. Please choose a file to upload.", "error")
        return redirect(url_for("datasets.upload_page"))

    file = request.files["file"]
    if file.filename == "" or file.filename is None:
        flash("No file selected. Please choose a file to upload.", "error")
        return redirect(url_for("datasets.upload_page"))

    # Read file size from Content-Length or seek
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    # Validate file (Phase 14: includes MIME + magic-byte checks)
    is_valid, error_msg = DatasetService.validate_file(
        file.filename, file_size,
        current_app.config.get("MAX_CONTENT_LENGTH", 52428800),
        file_storage=file,
    )
    if not is_valid:
        AuditService.log(
            action="dataset_upload",
            user_id=user.id, username=user.username,
            resource_type="dataset",
            details={"filename": file.filename, "size": file_size, "reason": error_msg},
            success=False,
        )
        flash(error_msg, "error")
        return redirect(url_for("datasets.upload_page"))

    # Detect format
    file_format = DatasetService.detect_format(file.filename)
    if not file_format:
        flash("Could not detect file format.", "error")
        return redirect(url_for("datasets.upload_page"))

    # Save file securely
    try:
        storage_path, _ = DatasetService.save_file(
            file, user.id, current_app.config["UPLOAD_FOLDER"]
        )
    except Exception as exc:
        flash("Failed to save file. Please try again.", "error")
        return redirect(url_for("datasets.upload_page"))

    # Load DataFrame using existing connectors
    df, error = DatasetService.load_dataframe(storage_path, file_format)
    if df is None:
        # Clean up saved file
        DatasetService.delete_storage(storage_path)
        flash(error or "Failed to read the uploaded file.", "error")
        return redirect(url_for("datasets.upload_page"))

    if df.empty:
        DatasetService.delete_storage(storage_path)
        flash("The uploaded file contains no data rows.", "error")
        return redirect(url_for("datasets.upload_page"))

    # Profile dataset
    profile = DatasetService.profile_dataframe(df)
    del df  # Free memory after profiling

    # Generate dataset name from filename
    dataset_name = file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename

    # Persist to database
    try:
        dataset = DatasetService.create_dataset(
            user_id=user.id,
            name=sanitize_user_input(dataset_name, max_length=255),
            original_filename=file.filename,
            file_format=file_format,
            file_size=file_size,
            storage_path=storage_path,
            profile=profile,
        )
        AuditService.log(
            action="dataset_upload",
            user_id=user.id, username=user.username,
            resource_type="dataset", resource_id=dataset.id,
            details={"filename": file.filename, "format": file_format, "rows": profile.get("row_count"), "size": file_size},
        )
        flash(
            f"Dataset '{dataset.name}' uploaded successfully! "
            f"{profile.get('row_count', 0):,} rows x {profile.get('column_count', 0)} columns.",
            "success"
        )
        return redirect(url_for("datasets.detail", dataset_id=dataset.id))
    except Exception as exc:
        DatasetService.delete_storage(storage_path)
        flash("Failed to save dataset. Please try again.", "error")
        return redirect(url_for("datasets.upload_page"))


# ── Database Import Handler ───────────────────────────────────────

@datasets_bp.route("/datasets/connect_db", methods=["POST"])
@login_required
def connect_db():
    """Handle database connection and data import.

    Security (Phase 14): SQL whitelist, table name validation, rate limiting.
    """
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    # ── Rate limit check ───────────────────────────────
    allowed, remaining, _ = check_rate_limit("db_connect")
    if not allowed:
        return rate_limit_exceeded_response("db_connect", remaining, 3600)

    source_type_str = request.form.get("source_type", "")
    dataset_name = sanitize_user_input(request.form.get("dataset_name", ""), max_length=255)
    
    # Parse source type
    try:
        source_type = DataSourceType(source_type_str.lower())
    except ValueError:
        flash(f"Invalid database type: {source_type_str}", "error")
        return redirect(url_for("datasets.upload_page") + "#database")

    # Build ConnectionConfig
    conn_config = ConnectionConfig(
        source_type=source_type,
        connection_string=request.form.get("connection_string", "").strip() or None,
        host=request.form.get("host", "").strip() or None,
        port=int(request.form.get("port")) if request.form.get("port", "").strip() else None,
        username=request.form.get("username", "").strip() or None,
        password=request.form.get("password", "").strip() or None,
        database=request.form.get("database", "").strip() or None,
        file_path=request.form.get("file_path", "").strip() or None,
    )

    # Build QueryConfig
    try:
        limit = int(request.form.get("limit", "100000"))
    except ValueError:
        limit = 100000
        
    table_name = request.form.get("table_name", "").strip() or None
    sql_query = request.form.get("sql_query", "").strip() or None

    # ── SQL Injection Prevention (Phase 14) ──────────
    if sql_query:
        is_valid_sql, sql_error = validate_sql_query(sql_query)
        if not is_valid_sql:
            AuditService.log(
                action="db_connect",
                user_id=user.id, username=user.username,
                details={"reason": sql_error, "sql_preview": sql_query[:200]},
                success=False,
            )
            flash(f"SQL validation failed: {sql_error}", "error")
            return redirect(url_for("datasets.upload_page") + "#database")

    if table_name:
        is_valid_table, table_error = validate_table_name(table_name)
        if not is_valid_table:
            AuditService.log(
                action="db_connect",
                user_id=user.id, username=user.username,
                details={"reason": table_error, "table_name": table_name},
                success=False,
            )
            flash(f"Invalid table name: {table_error}", "error")
            return redirect(url_for("datasets.upload_page") + "#database")

    query_config = QueryConfig(
        table_name=table_name,
        sql_query=sql_query,
        limit=limit
    )
    
    if not query_config.table_name and not query_config.sql_query:
        flash("You must specify a table name or provide a custom SQL query.", "error")
        return redirect(url_for("datasets.upload_page") + "#database")

    dataset, error = DatasetService.ingest_from_database(
        user_id=user.id,
        config=conn_config,
        query=query_config,
        dataset_name=dataset_name,
        base_upload_dir=current_app.config["UPLOAD_FOLDER"]
    )
    
    if error or not dataset:
        AuditService.log(
            action="db_connect",
            user_id=user.id, username=user.username,
            details={"reason": error, "source_type": source_type_str},
            success=False,
        )
        flash(error or "Database import failed.", "error")
        return redirect(url_for("datasets.upload_page") + "#database")

    AuditService.log(
        action="db_connect",
        user_id=user.id, username=user.username,
        resource_type="dataset", resource_id=dataset.id,
        details={"source_type": source_type_str, "rows": dataset.row_count},
    )
    flash(
        f"Dataset '{dataset.name}' imported from database successfully! "
        f"{dataset.row_count:,} rows x {dataset.column_count} columns.",
        "success"
    )
    return redirect(url_for("datasets.detail", dataset_id=dataset.id))


# ── API Import Handler ────────────────────────────────────────────

@datasets_bp.route("/datasets/connect_api", methods=["POST"])
@login_required
def connect_api():
    """Handle REST API connection and data import.

    Security (Phase 14): SSRF protection, rate limiting, audit logging.
    """
    import json
    
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    # ── Rate limit check ───────────────────────────────
    allowed, remaining, _ = check_rate_limit("api_connect")
    if not allowed:
        return rate_limit_exceeded_response("api_connect", remaining, 3600)

    dataset_name = sanitize_user_input(request.form.get("dataset_name", ""), max_length=255)
    api_url = request.form.get("api_url", "").strip()
    
    if not api_url:
        flash("API URL is required.", "error")
        return redirect(url_for("datasets.upload_page") + "#api")

    # ── SSRF Protection (Phase 14) ─────────────────────
    is_valid_url, url_error = validate_api_url(api_url)
    if not is_valid_url:
        AuditService.log(
            action="api_connect",
            user_id=user.id, username=user.username,
            details={"reason": url_error, "url": api_url[:200]},
            success=False,
        )
        flash(f"Invalid URL: {url_error}", "error")
        return redirect(url_for("datasets.upload_page") + "#api")
        
    headers_str = request.form.get("headers", "").strip()
    params_str = request.form.get("params", "").strip()
    json_path = request.form.get("json_path", "").strip() or None
    
    headers = {}
    if headers_str:
        try:
            headers = json.loads(headers_str)
        except json.JSONDecodeError:
            flash("Headers must be a valid JSON object.", "error")
            return redirect(url_for("datasets.upload_page") + "#api")
            
    params = {}
    if params_str:
        try:
            params = json.loads(params_str)
        except json.JSONDecodeError:
            flash("Params must be a valid JSON object.", "error")
            return redirect(url_for("datasets.upload_page") + "#api")

    conn_config = ConnectionConfig(
        source_type=DataSourceType.REST_API,
        api_url=api_url,
        headers=headers,
        params=params,
        json_path=json_path
    )

    dataset, error = DatasetService.ingest_from_api(
        user_id=user.id,
        config=conn_config,
        dataset_name=dataset_name,
        base_upload_dir=current_app.config["UPLOAD_FOLDER"]
    )
    
    if error or not dataset:
        flash(error or "API import failed.", "error")
        return redirect(url_for("datasets.upload_page") + "#api")
        
    flash(
        f"Dataset '{dataset.name}' imported from API successfully! "
        f"{dataset.row_count:,} rows x {dataset.column_count} columns.",
        "success"
    )
    return redirect(url_for("datasets.detail", dataset_id=dataset.id))


# ── Dataset Detail ───────────────────────────────────────────────

@datasets_bp.route("/datasets/<int:dataset_id>")
@login_required
def detail(dataset_id):
    """View dataset overview, metadata, and column profiles."""
    result = _require_dataset_owner(dataset_id)
    user, dataset, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    versions = DatasetService.get_dataset_versions(dataset_id, user.id)

    return render_template(
        "datasets/detail.html",
        user=user,
        dataset=dataset,
        versions=versions,
        format_labels=FORMAT_LABELS,
    )


# ── Dataset Edit ─────────────────────────────────────────────────

@datasets_bp.route("/datasets/<int:dataset_id>/edit", methods=["POST"])
@login_required
def edit(dataset_id):
    """Edit dataset metadata."""
    user, dataset, redirect_resp = _require_dataset_owner(dataset_id)
    if redirect_resp:
        return redirect_resp

    name = sanitize_user_input(request.form.get("name", ""), max_length=255)
    description = sanitize_user_input(request.form.get("description", ""), max_length=2000)
    
    success, msg = DatasetService.update_dataset(dataset_id, user.id, name, description)
    if success:
        flash(msg, "success")
    else:
        flash(msg, "error")

    return redirect(url_for("datasets.detail", dataset_id=dataset_id))


# ── Data Preview ─────────────────────────────────────────────────

@datasets_bp.route("/datasets/<int:dataset_id>/preview")
@login_required
def preview(dataset_id):
    """View dataset data in a tabular preview with pagination."""
    result = _require_dataset_owner(dataset_id)
    user, dataset, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    try:
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
        
    try:
        per_page = int(request.args.get("per_page", 100))
        if per_page not in (50, 100, 500):
            per_page = 100
    except ValueError:
        per_page = 100

    df, _ = DatasetService.get_preview_data(dataset_id, user.id, page=page, per_page=per_page)
    if df is None:
        flash("Could not load preview data. The file may have been moved or deleted.", "error")
        return redirect(url_for("datasets.detail", dataset_id=dataset_id))

    # Convert DataFrame to list of dicts for template rendering
    columns = list(df.columns)
    rows = df.to_dict(orient="records")
    # Convert any non-serializable values to strings
    for row in rows:
        for key in row:
            val = row[key]
            if pd.isna(val):
                row[key] = ""
            elif hasattr(val, 'isoformat'):
                row[key] = val.isoformat()
            else:
                try:
                    str(val)
                except Exception:
                    row[key] = ""

    total_rows = dataset.row_count or len(rows)
    total_pages = (total_rows + per_page - 1) // per_page if total_rows > 0 else 1

    return render_template(
        "datasets/preview.html",
        user=user,
        dataset=dataset,
        columns=columns,
        rows=rows,
        total_rows=total_rows,
        preview_rows=len(rows),
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        format_labels=FORMAT_LABELS,
    )


# ── Dataset Download ─────────────────────────────────────────────

@datasets_bp.route("/datasets/<int:dataset_id>/download")
@login_required
def download(dataset_id):
    """Download the original uploaded file."""
    result = _require_dataset_owner(dataset_id)
    user, dataset, redirect_resp = result
    if redirect_resp:
        return redirect_resp

    if not dataset.storage_path or not os.path.exists(dataset.storage_path):
        flash("File not found. It may have been moved or deleted.", "error")
        return redirect(url_for("datasets.detail", dataset_id=dataset_id))

    AuditService.log(
        action="dataset_download",
        user_id=user.id, username=user.username,
        resource_type="dataset", resource_id=dataset_id,
        details={"filename": dataset.original_filename},
    )
    return send_file(
        dataset.storage_path,
        download_name=dataset.original_filename,
        as_attachment=True,
    )


# ── Dataset Delete ────────────────────────────────────────────────

@datasets_bp.route("/datasets/<int:dataset_id>/delete", methods=["POST"])
@login_required
def delete(dataset_id):
    """Delete a dataset and its stored file."""
    user = get_current_user()
    if not user:
        flash("Session expired. Please sign in again.", "warning")
        return redirect(url_for("auth.login"))

    success, message = DatasetService.delete_dataset(dataset_id, user.id)
    if success:
        AuditService.log(
            action="dataset_delete",
            user_id=user.id, username=user.username,
            resource_type="dataset", resource_id=dataset_id,
        )
        flash("Dataset deleted successfully.", "success")
    else:
        flash(message or "Failed to delete dataset.", "error")

    return redirect(url_for("datasets.index"))


# ── API Endpoints ────────────────────────────────────────────────

@datasets_bp.route("/api/datasets")
@login_required
def api_list():
    """JSON API: List user's datasets."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    search = request.args.get("q", "").strip()
    datasets = DatasetService.get_user_datasets(user.id, search=search)

    result = []
    for ds in datasets:
        result.append({
            "id": ds.id,
            "name": ds.name,
            "original_filename": ds.original_filename,
            "file_format": ds.file_format,
            "file_size": ds.file_size,
            "row_count": ds.row_count,
            "column_count": ds.column_count,
            "created_at": ds.created_at.isoformat() if ds.created_at else None,
            "updated_at": ds.updated_at.isoformat() if ds.updated_at else None,
        })

    return jsonify({"datasets": result, "count": len(result)})


@datasets_bp.route("/api/datasets/<int:dataset_id>")
@login_required
def api_detail(dataset_id):
    """JSON API: Get dataset details."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    dataset = DatasetService.get_dataset(dataset_id, user.id)
    if not dataset:
        return jsonify({"error": "Dataset not found"}), 404

    return jsonify({
        "id": dataset.id,
        "name": dataset.name,
        "original_filename": dataset.original_filename,
        "file_format": dataset.file_format,
        "file_size": dataset.file_size,
        "row_count": dataset.row_count,
        "column_count": dataset.column_count,
        "description": dataset.description,
        "encoding": dataset.encoding,
        "column_info": dataset.column_info,
        "quality_info": dataset.quality_info,
        "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
        "updated_at": dataset.updated_at.isoformat() if dataset.updated_at else None,
    })


@datasets_bp.route("/api/datasets/<int:dataset_id>", methods=["DELETE"])
@login_required
def api_delete(dataset_id):
    """JSON API: Delete a dataset."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401

    success, message = DatasetService.delete_dataset(dataset_id, user.id)
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"error": message}), 404


