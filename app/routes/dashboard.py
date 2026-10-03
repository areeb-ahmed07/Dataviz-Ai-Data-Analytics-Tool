import os
import datetime
import logging
from collections import defaultdict
from flask import Blueprint, render_template, request, abort, current_app

from app.auth_helpers import login_required
from app.utils.helpers import require_current_user_redirect
from auth.services.project_service import ProjectService
from app.services.dataset_service import DatasetService
from auth.services.auth_service import AuthService
from auth.database import get_session, session_scope, AnalysisDB, ModelDB, DatasetDB as DatasetDBModel
from auth.domain.user import Role
from app.security import AuditService, check_rate_limit, rate_limit_exceeded_response

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


# ── Dashboard ────────────────────────────────────────────────────

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    """Main dashboard page — cached for 30s, aggregates via SQL not Python.

    Target: < 2 seconds on cached hit, < 3s on cold load.
    """
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response

    # ── Check dashboard cache first ─────────────────────
    from app.core.cache import dashboard_cache
    cache_key = f"u:{user.id}:dashboard"
    cached = dashboard_cache.get(cache_key)
    if cached is not None:
        return render_template("dashboard/index.html", user=user, **cached)

    db = get_session()
    try:
        # 1. Projects (uses shared session)
        try:
            project_service = ProjectService(db=db)
            projects = project_service.get_user_projects(user.id)
        except Exception:
            logger.exception("Failed to load projects")
            projects = []

        # 2. Datasets (cached 15s in DatasetService)
        try:
            datasets = DatasetService.get_user_datasets(user.id)
            dataset_count = len(datasets)
            recent_datasets = sorted(datasets, key=lambda x: x.created_at, reverse=True)[:5]
        except Exception:
            logger.exception("Failed to load datasets")
            datasets = []
            dataset_count = 0
            recent_datasets = []

        # Dataset Stats (computed from already-loaded data — no extra query)
        total_rows = sum(ds.row_count or 0 for ds in datasets)
        total_cols = sum(ds.column_count or 0 for ds in datasets)
        total_size_mb = sum(ds.file_size or 0 for ds in datasets) / (1024 * 1024)

        # Chart Data (computed from already-loaded data)
        formats = defaultdict(int)
        for ds in datasets:
            formats[ds.file_format] += 1
        formats_chart_data = {
            "labels": list(formats.keys()),
            "data": list(formats.values())
        }

        # 3. Analyses — single query for count + recent (uses ix_analyses_user_created)
        try:
            total_analyses = db.query(AnalysisDB).filter(AnalysisDB.user_id == user.id).count()
            recent_analyses = (db.query(AnalysisDB)
                .filter(AnalysisDB.user_id == user.id)
                .order_by(AnalysisDB.created_at.desc())
                .limit(20)
                .all())
        except Exception:
            logger.exception("Failed to load analyses")
            total_analyses = 0
            recent_analyses = []

        # 4. ML Models count (single aggregate query)
        try:
            total_models = db.query(ModelDB).filter(ModelDB.user_id == user.id).count()
        except Exception:
            logger.exception("Failed to count models")
            total_models = 0

        # 5. Reports (from file system — lazy, skip if dir doesn't exist)
        from app.services.report_service import ReportService
        reports_dir = ReportService.report_directory(user.id)
        recent_reports = []
        total_reports = 0
        files = []
        if os.path.exists(reports_dir):
            try:
                for filename in os.listdir(reports_dir):
                    filepath = os.path.join(reports_dir, filename)
                    if os.path.isfile(filepath):
                        files.append({
                            "name": filename,
                            "created_at": datetime.datetime.fromtimestamp(os.path.getmtime(filepath)),
                            "path": f"reports/{user.id}/{filename}"
                        })
            except OSError:
                pass
            total_reports = len(files)
            recent_reports = sorted(files, key=lambda x: x["created_at"], reverse=True)[:5]

        # 6. System Stats (Admin only — cached 10s)
        system_stats = None
        if user.role.value == Role.ADMIN.value:
            try:
                from app.core.cache import system_stats_cache
                ss_key = "global:system_stats"
                system_stats = system_stats_cache.get(ss_key)
                if system_stats is None:
                    auth_service = AuthService(db=db)
                    system_stats = auth_service.get_system_stats()
                    system_stats_cache.set(ss_key, system_stats, ttl=10)
            except Exception:
                logger.exception("Failed to load system stats")

        # 7. Timeline (merge datasets, projects, analyses)
        timeline = []
        for ds in datasets:
            timeline.append({"type": "dataset", "title": f"Uploaded dataset: {ds.name}", "date": ds.created_at, "icon": "upload"})
        for p in projects:
            timeline.append({"type": "project", "title": f"Created project: {p.project_name}", "date": p.created_at, "icon": "folder"})
        for a in recent_analyses:
            timeline.append({"type": "analysis", "title": f"Ran {a.analysis_type} analysis", "date": a.created_at, "icon": "activity"})
        for r in files:
            timeline.append({"type": "report", "title": f"Generated report: {r['name']}", "date": r["created_at"], "icon": "file-text"})

        timeline.sort(key=lambda x: x["date"], reverse=True)
        recent_activity = timeline[:10]

        template_data = {
            "projects": projects,
            "datasets": datasets,
            "dataset_count": dataset_count,
            "recent_datasets": recent_datasets,
            "total_rows": total_rows,
            "total_cols": total_cols,
            "total_size_mb": total_size_mb,
            "formats_chart_data": formats_chart_data,
            "total_analyses": total_analyses,
            "total_models": total_models,
            "total_reports": total_reports,
            "recent_reports": recent_reports,
            "system_stats": system_stats,
            "recent_activity": recent_activity,
        }

        # Cache the template data (30s TTL)
        dashboard_cache.set(cache_key, template_data, ttl=30)

        return render_template("dashboard/index.html", user=user, **template_data)
    finally:
        db.close()


@dashboard_bp.route("/search")
@login_required
def search():
    """Search functionality."""
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response

    query = request.args.get("q", "").strip().lower()

    datasets = DatasetService.get_user_datasets(user.id, search=query if query else None)
    results = []
    if query:
        for ds in datasets:
            if query in ds.name.lower() or (ds.description and query in ds.description.lower()):
                results.append(ds)

    return render_template("dashboard/search.html", user=user, query=query, results=results)


# ── Projects ────────────────────────────────────────────────────

@dashboard_bp.route("/projects")
@login_required
def projects():
    """User projects listing page."""
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response

    try:
        project_service = ProjectService()
        projects = project_service.get_user_projects(user.id)
    except Exception:
        projects = []

    return render_template("projects/index.html", user=user, projects=projects)


@dashboard_bp.route("/help")
@login_required
def help_page():
    """Help center opened from the dashboard top bar."""
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response
    return render_template("dashboard/help.html", user=user, active_page="help")


@dashboard_bp.route("/notifications")
@login_required
def notifications():
    """Notification center opened from the dashboard top bar."""
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response
    return render_template("dashboard/notifications.html", user=user, active_page="notifications")


# ── Settings ─────────────────────────────────────────────────────

@dashboard_bp.route("/settings/theme", methods=["POST"])
@login_required
def update_theme():
    """Persist the toolbar theme switch without changing other preferences."""
    from flask import jsonify
    from auth.database import UserDB
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response
    theme = (request.get_json(silent=True) or {}).get("theme")
    if theme not in ("light", "dark", "system"):
        return jsonify(error="Choose a valid theme."), 400
    db = get_session()
    try:
        account = db.query(UserDB).filter(UserDB.id == user.id).first()
        if not account:
            return jsonify(error="Account not found."), 404
        account.theme = theme
        db.commit()
        return jsonify(theme=theme)
    except Exception:
        db.rollback()
        logger.exception("Could not save theme")
        return jsonify(error="Could not save the theme. Please try again."), 500
    finally:
        db.close()

@dashboard_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Settings page with profile, security, appearance, and notification forms."""
    user, redirect_response = require_current_user_redirect()
    if redirect_response:
        return redirect_response

    from flask import flash, session, redirect
    from auth.security import sanitize_input
    from auth.database import UserDB

    db = get_session()
    try:
        auth_service = AuthService(db=db)

        if request.method == "POST":
            action = request.form.get("action")

            if action == "update_account":
                full_name = request.form.get("full_name")
                email = request.form.get("email")
                success, msg = auth_service.update_profile(user.id, full_name, email)
                if success:
                    session["full_name"] = sanitize_input(full_name)
                    session["email"] = sanitize_input(email).lower()
                    flash(msg, "success")
                    return redirect("/settings?tab=account")
                else:
                    flash(msg, "error")

            elif action == "update_password":
                # ── Rate limit (Phase 14) ─────────────────────
                allowed, remaining, _ = check_rate_limit("password_change")
                if not allowed:
                    return rate_limit_exceeded_response("password_change", remaining, 300)

                current_pw = request.form.get("current_password")
                new_pw = request.form.get("new_password")
                confirm_pw = request.form.get("confirm_password")

                if new_pw != confirm_pw:
                    flash("New passwords do not match.", "error")
                else:
                    success, msg = auth_service.change_password(user.id, current_pw, new_pw)
                    if success:
                        AuditService.log(
                            action="password_change",
                            user_id=user.id, username=user.username,
                        )
                        flash(msg, "success")
                        return redirect("/settings?tab=security")
                    else:
                        AuditService.log(
                            action="password_change_failed",
                            user_id=user.id, username=user.username,
                            success=False,
                        )
                        flash(msg, "error")

            elif action == "update_preferences":
                theme = request.form.get("theme", "light")
                notifications = request.form.get("notifications_enabled") == "on"
                success, msg = auth_service.update_preferences(user.id, theme, notifications)
                if success:
                    flash(msg, "success")
                    return redirect("/settings?tab=appearance")
                else:
                    flash(msg, "error")

        active_tab = request.args.get("tab", "account")

        # Reload fresh user data
        fresh_user = db.query(UserDB).filter(UserDB.id == user.id).first()
        user_domain = fresh_user.to_domain() if fresh_user else user
        return render_template("settings/index.html", user=user_domain, active_tab=active_tab)
    finally:
        db.close()
