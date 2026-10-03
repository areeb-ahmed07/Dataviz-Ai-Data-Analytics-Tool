"""Vercel serverless entry point for the Flask application."""

import os


# Vercel functions have a writable /tmp directory, but it is ephemeral.
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/dataviz_pro.db")
os.environ.setdefault("UPLOAD_FOLDER", "/tmp/dataviz-uploads")
os.environ.setdefault("REPORTS_FOLDER", "/tmp/dataviz-reports")


def _create_app():
    from app import create_app

    return create_app("production")


app = _create_app()
