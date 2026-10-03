"""
DataViz Pro — Configuration Module

All sensitive values are read from environment variables (.env).
Never hard-code secrets or credentials in this file.
"""

import os
from dotenv import load_dotenv

# Explicit process settings (tests and deployment) take precedence over local defaults.
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"), override=False)


class Config:
    """Base configuration (shared across all environments)."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    if not SECRET_KEY:
        import warnings
        warnings.warn(
            "SECRET_KEY not set. Generating insecure random key. "
            "Set the SECRET_KEY environment variable for production.",
            RuntimeWarning,
            stacklevel=2,
        )
        import secrets
        SECRET_KEY = secrets.token_hex(32)

    # Flask
    DEBUG = os.environ.get("DEBUG", "False").lower() in ("true", "1", "yes")

    # Uploads
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", os.path.join(basedir, "uploads"))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 50 * 1024 * 1024))  # 50 MB

    # Reports output directory
    REPORTS_FOLDER = os.environ.get("REPORTS_FOLDER", os.path.join(basedir, "reports"))

    # Session
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = int(os.environ.get("SESSION_LIFETIME", 86400))  # 24h

    # Application metadata
    APP_NAME = "DataViz Pro"
    APP_VERSION = "2.0.0"

    # OAuth credentials (optional — configure in .env if needed)
    # GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    # GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    # GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
    # GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

    # AI (OpenAI)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

    # App base URL (updated for Flask default port)
    APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5000")


class DevelopmentConfig(Config):
    """Development-specific overrides."""
    DEBUG = True


class ProductionConfig(Config):
    """Production-specific overrides."""
    DEBUG = False


class TestingConfig(Config):
    """Testing-specific overrides."""
    TESTING = True
    DEBUG = True


# Config map for factory selection
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
