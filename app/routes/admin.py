"""
Admin Blueprint — Admin-only routes for DataViz Pro.

Provides user management, audit log viewing, and system administration.
All routes require admin role (enforced by @admin_required decorator).
Phase 14: RBAC + Audit Logging.
"""

from datetime import datetime
import re

from flask import (
    Blueprint, render_template, request, jsonify, flash, redirect, url_for,
)

from app.auth_helpers import login_required, get_current_user
from app.security import admin_required, AuditService, sanitize_user_input
from auth.services.auth_service import AuthService
from auth.domain.user import Role
from auth.database import get_session, UserDB

admin_bp = Blueprint("admin", __name__)

_EMAIL_PATTERN = re.compile(r"[\w.!#$%&'*+/=?^`{|}~-]+@[\w.-]+")


def _private_admin_view(value):
    """Redact email identifiers in admin responses, including historical logs."""
    if isinstance(value, str):
        return _EMAIL_PATTERN.sub("[email hidden]", value)
    if isinstance(value, dict):
        return {_private_admin_view(key): _private_admin_view(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_private_admin_view(item) for item in value]
    return value


@admin_bp.route("/admin/users")
@login_required
@admin_required
def list_users():
    """List all users with management controls."""
    user = get_current_user()
    auth_service = AuthService()
    # Only send account-management fields to the template, never email addresses.
    users = [_private_admin_view({
        "id": account.id,
        "full_name": account.full_name,
        "username": account.username,
        "role": account.role.value,
        "is_active": account.is_active,
        "created_at": account.created_at,
    }) for account in auth_service.list_all_users()]

    AuditService.log(
        action="admin_view_users",
        user_id=user.id, username=user.username,
    )

    return render_template("admin/users.html", user=user, users=users)


@admin_bp.route("/admin/users/<int:target_user_id>/role", methods=["POST"])
@login_required
@admin_required
def change_role(target_user_id):
    """Change a user's role (user ↔ admin)."""
    user = get_current_user()
    if target_user_id == user.id:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("admin.list_users"))

    new_role_str = request.form.get("role", "user").strip().lower()
    try:
        new_role = Role(new_role_str)
    except ValueError:
        flash("Invalid role specified.", "error")
        return redirect(url_for("admin.list_users"))

    db = get_session()
    try:
        auth_service = AuthService(db=db)
        success, msg = auth_service.update_user_role(target_user_id, new_role)
        if success:
            AuditService.log(
                action="admin_role_change",
                user_id=user.id, username=user.username,
                resource_type="user", resource_id=target_user_id,
                details={"new_role": new_role.value},
            )
            flash(msg, "success")
        else:
            flash(msg, "error")
    finally:
        db.close()

    return redirect(url_for("admin.list_users"))


@admin_bp.route("/admin/users/<int:target_user_id>/toggle-status", methods=["POST"])
@login_required
@admin_required
def toggle_status(target_user_id):
    """Enable or disable a user account."""
    user = get_current_user()
    if target_user_id == user.id:
        flash("You cannot disable your own account.", "error")
        return redirect(url_for("admin.list_users"))

    db = get_session()
    try:
        auth_service = AuthService(db=db)
        success, msg = auth_service.toggle_user_status(target_user_id)
        if success:
            # Get updated status for audit log
            target = db.query(UserDB).filter(UserDB.id == target_user_id).first()
            AuditService.log(
                action="admin_toggle_user_status",
                user_id=user.id, username=user.username,
                resource_type="user", resource_id=target_user_id,
                details={"new_status": "active" if target and target.is_active else "disabled"},
            )
            flash(msg, "success")
        else:
            flash(msg, "error")
    finally:
        db.close()

    return redirect(url_for("admin.list_users"))


@admin_bp.route("/admin/audit-logs")
@login_required
@admin_required
def audit_logs():
    """View security audit logs."""
    user = get_current_user()

    action_filter = request.args.get("action", "").strip() or None
    resource_type = request.args.get("resource_type", "").strip() or None
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    per_page = 50
    offset = (page - 1) * per_page

    logs, total = AuditService.get_logs(
        action=action_filter,
        resource_type=resource_type,
        limit=per_page,
        offset=offset,
    )

    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    # The audit service returns JSON-ready timestamps, not datetime objects.
    logs = _private_admin_view(logs)
    for entry in logs:
        timestamp = entry.get("created_at")
        try:
            entry["display_timestamp"] = (
                datetime.fromisoformat(timestamp).strftime("%b %d, %Y %I:%M %p")
                if timestamp else "—"
            )
        except (TypeError, ValueError):
            entry["display_timestamp"] = "—"

    AuditService.log(
        action="admin_view_audit_logs",
        user_id=user.id, username=user.username,
        details={"filters": {"action": action_filter, "resource_type": resource_type}},
    )

    return render_template(
        "admin/audit_logs.html",
        user=user,
        logs=logs,
        total=total,
        page=page,
        total_pages=total_pages,
        action_filter=action_filter,
        resource_type=resource_type,
    )



@admin_bp.route("/admin/api/audit-logs")
@login_required
@admin_required
def api_audit_logs():
    """JSON API: Get audit logs for admin dashboard."""
    user = get_current_user()
    action = (request.args.get("action") or "").strip() or None
    resource_type = (request.args.get("resource_type") or "").strip() or None
    try:
        limit = min(int(request.args.get("limit", 100)), 500)
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        limit, offset = 100, 0

    logs, total = AuditService.get_logs(
        action=action,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )
    return jsonify({"logs": _private_admin_view(logs), "total": total})
