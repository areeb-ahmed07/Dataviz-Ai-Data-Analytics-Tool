"""
DataViz Pro — Application Factory

Creates and configures the Flask application instance.
Follows the Application Factory pattern for clean, testable initialization.
"""

import os
from flask import Flask, render_template, jsonify, request, flash, redirect, url_for
from flask_wtf.csrf import CSRFProtect
csrf = CSRFProtect()
from datetime import datetime

from config import config_map


def create_app(config_name: str = "default") -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config_name: Key from config_map ('development', 'production', 'testing').

    Returns:
        Configured Flask application instance.
    """
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder="templates",
        static_folder="static",
    )

    # ── Load configuration ──────────────────────────────────────────
    cfg = config_map.get(config_name, config_map["default"])
    app.config.from_object(cfg)

    # Override from .env if present (for SECRET_KEY etc.)
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", app.config["SECRET_KEY"]
    )

    # ── Logging configuration ────────────────────────────────────
    import logging
    log_level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    app.logger.setLevel(log_level)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )
    if not app.logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)

    # ── Session security configuration (Phase 14) ──────────────
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["PERMANENT_SESSION_LIFETIME"] = 86400  # 24 hours
    # Secure cookie in production (HTTPS only)
    if not app.config.get("DEBUG"):
        app.config["SESSION_COOKIE_SECURE"] = True
    # Custom cookie name to avoid fingerprinting
    app.config["SESSION_COOKIE_NAME"] = "dvpro_session"

    # ── Ensure required directories exist ────────────────────────
    for folder_key in ("UPLOAD_FOLDER", "REPORTS_FOLDER"):
        path = app.config.get(folder_key)
        if path:
            os.makedirs(path, exist_ok=True)

    # ── Initialize database tables ─────────────────────────────────
    _init_database()

    # ── Register blueprints ────────────────────────────────────────
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.datasets import datasets_bp
    from app.routes.analysis import analysis_bp
    from app.routes.cleaning import cleaning_bp
    from app.routes.ml import ml_bp
    from app.routes.xai import xai_bp
    from app.routes.visualization import visualization_bp
    from app.routes.timeseries import timeseries_bp
    from app.routes.reports import reports_bp
    from app.routes.copilot import copilot_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    from app.oauth import init_oauth
    init_oauth(app)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(datasets_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(cleaning_bp)
    app.register_blueprint(ml_bp)
    app.register_blueprint(xai_bp)
    app.register_blueprint(visualization_bp)
    app.register_blueprint(timeseries_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(copilot_bp)
    from app.routes.workspaces import workspaces_bp
    app.register_blueprint(workspaces_bp)

    # ── Security Headers (Phase 14) ──────────────────────────
    from app.security import inject_security_headers

    @app.after_request
    def _add_security_headers(response):
        return inject_security_headers(response)

    # ── CSRF Protection ─────────────────────────────────
    csrf.init_app(app)

    # CSRF error handler
    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        if request.path.startswith("/api/") or request.path == "/health":
            return jsonify({"success": False, "error": {"code": "CSRF_FAILED", "message": "CSRF validation failed."}}), 400
        flash("Security validation failed. Please try again.", "error")
        return redirect(request.referrer or url_for("main.index"))

    # ── Admin Routes (Phase 14) ──────────────────────────
    from app.routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    # ── Error handlers ────────────────────────────────────
    _register_error_handlers(app)

    # ── Template context processors ────────────────────────────────
    @app.context_processor
    def inject_globals():
        from app.auth_helpers import get_current_user
        theme_user = get_current_user()
        return {
            "current_hour": datetime.now().hour,
            "theme_preference": theme_user.theme if theme_user else "light",
        }

    # ── Template filters ──────────────────────────────────────────
    import os as _os
    app.jinja_env.filters['basename'] = lambda p: _os.path.basename(p) if p else ''

    return app


def _init_database() -> None:
    """Initialize auth database tables if they don't exist yet."""
    try:
        from auth.database import init_db
        init_db()
    except Exception as e:
        import sys
        print(f"[WARN] Database initialization skipped: {e}", file=sys.stderr)


def _register_error_handlers(app: Flask) -> None:
    """Register custom HTTP error pages."""

    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def payload_too_large(error):
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def too_many_requests(error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_error(error):
        return render_template("errors/500.html"), 500
