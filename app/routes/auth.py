"""
Auth Blueprint — Authentication routes for DataViz Pro.

Provides login, signup, logout, profile, and dashboard routes.
Reuses the existing auth.services.AuthService for all business logic.
Security: rate limiting, audit logging, session rotation, brute-force protection.
"""

import re
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, session, current_app, jsonify,
)
from auth.services.auth_service import AuthService
from auth.services.project_service import ProjectService
from auth.security import sanitize_input
from app.auth_helpers import (
    login_required, get_current_user, set_session_user, clear_session,
)
from app.security import (
    AuditService, check_rate_limit, rate_limit_exceeded_response,
    login_tracker, _get_client_ip, sanitize_user_input,
)

auth_bp = Blueprint("auth", __name__)


# ── LOGIN ────────────────────────────────────────────────────────

@auth_bp.route('/admin/login')
def legacy_admin_login():
    return redirect(url_for('auth.login'))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Render login page or process login form submission.

    Security measures:
    - Rate limiting (5 attempts per 5 minutes per IP+identifier)
    - DB-backed login attempt tracking (10 failures → 15-minute lockout)
    - Audit logging for all attempts
    - Session rotation after successful login
    """
    # Already logged in → redirect to dashboard
    if session.get("authenticated"):
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        identifier = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Email and password are required.", "error")
            return render_template("auth/login.html")

        # ── Rate limit check (in-memory) ───────────────────
        rl_key = f"login:{_get_client_ip()}:{identifier.lower()}"
        allowed, remaining, reset_secs = check_rate_limit("login", key=rl_key)
        if not allowed:
            flash("Too many login attempts. Please wait a few minutes before trying again.", "error")
            AuditService.log(
                action="login_rate_limited",
                username=identifier,
                details={"identifier": identifier, "ip": _get_client_ip()},
                success=False,
            )
            return render_template("auth/login.html")

        # ── DB-backed lockout check ────────────────────────
        locked, lock_remaining = login_tracker.is_locked_out(identifier.lower(), _get_client_ip())
        if locked:
            flash(
                f"Account temporarily locked due to too many failed attempts. "
                f"Please try again in {lock_remaining // 60 + 1} minutes.",
                "error"
            )
            AuditService.log(
                action="login_locked_out",
                username=identifier,
                details={"identifier": identifier, "lock_remaining": lock_remaining},
                success=False,
            )
            return render_template("auth/login.html")

        auth_service = AuthService()
        success, message, token, user_domain = auth_service.login_user(identifier, password)

        if success and user_domain:
            # ── Session rotation: clear old session data and regenerate ──
            clear_session()
            set_session_user(user_domain)

            # Record successful login
            AuditService.log(
                action="login_success",
                user_id=user_domain.id,
                username=user_domain.username,
                ip_address=_get_client_ip(),
            )
            login_tracker.record_attempt(identifier.lower(), success=True, ip_address=_get_client_ip())

            flash("Welcome back!", "success")
            return redirect(url_for('admin.list_users') if user_domain.role.value == 'admin' else url_for("dashboard.dashboard"))
        else:
            # Record failed login
            AuditService.log(
                action="login_failed",
                username=identifier,
                details={"identifier": identifier},
                success=False,
                ip_address=_get_client_ip(),
            )
            login_tracker.record_attempt(identifier.lower(), success=False, ip_address=_get_client_ip())

            flash(message or "Invalid email or password.", "error")
            return render_template("auth/login.html")

    return render_template("auth/login.html")


# ── SIGNUP ───────────────────────────────────────────────────────

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Render signup page or process registration form submission.

    Security: rate limiting (3 signups per hour per IP), audit logging.
    """
    # Already logged in → redirect to dashboard
    if session.get("authenticated"):
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        # ── Rate limit check ───────────────────────────────
        allowed, remaining, reset_secs = check_rate_limit("signup")
        if not allowed:
            return rate_limit_exceeded_response("signup", remaining, reset_secs)

        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # ── Server-side validation ───────────────────────────────
        errors = _validate_signup(full_name, username, email, password, confirm_password)
        if errors:
            for err in errors:
                flash(err, "error")
            return render_template(
                "auth/signup.html",
                full_name=full_name,
                username=username,
                email=email,
            )

        # ── Register via existing AuthService ─────────────────────
        auth_service = AuthService()
        success, message, user_domain = auth_service.register_user(
            full_name=full_name,
            username=username,
            email=email,
            password=password,
        )

        if success and user_domain:
            AuditService.log(
                action="signup",
                user_id=user_domain.id,
                username=user_domain.username,
                details={"email": email},
            )
            set_session_user(user_domain)
            flash("Account created successfully! Welcome to DataViz Pro.", "success")
            return redirect(url_for("dashboard.dashboard"))
        else:
            AuditService.log(
                action="signup_failed",
                details={"identifier": username, "email": email, "reason": message},
                success=False,
            )
            flash(message or "Registration failed. Please try again.", "error")
            return render_template(
                "auth/signup.html",
                full_name=full_name,
                username=username,
                email=email,
            )

    return render_template("auth/signup.html")


def _validate_signup(full_name, username, email, password, confirm_password):
    """Server-side validation for signup form. Returns list of error messages."""
    errors = []

    if not full_name:
        errors.append("Full name is required.")
    elif len(full_name) < 2:
        errors.append("Full name must be at least 2 characters.")

    if not username:
        errors.append("Username is required.")
    elif len(username) < 3:
        errors.append("Username must be at least 3 characters.")
    elif not re.match(r"^[a-zA-Z0-9_]+$", username):
        errors.append("Username can only contain letters, numbers, and underscores.")

    if not email:
        errors.append("Email is required.")
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Please enter a valid email address.")

    if not password:
        errors.append("Password is required.")
    elif len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif password != confirm_password:
        errors.append("Passwords do not match.")

    return errors


# ── LOGOUT ───────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    """Clear session and redirect to home.

    Security: Accepts POST to prevent CSRF via link/image-tag.
    GET is still supported for backward compatibility with navigation.
    Audit logs the logout event.
    """
    user_id = session.get("user_id")
    username = session.get("username")
    if user_id:
        AuditService.log(
            action="logout",
            user_id=user_id,
            username=username,
        )
    clear_session()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.index"))


# ── PROFILE (protected) ────────────────────────────────────────

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Protected user profile page (Redirects to unified settings)."""
    return redirect(url_for("dashboard.settings", tab="account"))
