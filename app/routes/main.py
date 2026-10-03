"""
Main Blueprint — Core routes for DataViz Pro.

Provides the primary pages and health-check endpoints.
Later phases will add additional blueprints for auth, dashboard, etc.
"""

from flask import Blueprint, render_template, jsonify, current_app

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """Render the home / landing page."""
    return render_template("home.html")


@main_bp.route("/health")
def health_check():
    """
    Health-check endpoint for deployment monitoring.

    Returns:
        JSON with application status and metadata.
    """
    return jsonify(
        status="ok",
        application=current_app.config["APP_NAME"],
        version=current_app.config["APP_VERSION"],
    )
