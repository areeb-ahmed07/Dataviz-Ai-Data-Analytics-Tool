"""DataViz Pro — Shared Route Helpers

Common utility functions used across multiple route modules."""

from flask import flash, redirect, url_for
from app.auth_helpers import get_current_user, clear_session


def require_current_user():
    """Get current user or redirect to login if session expired.
    
    Returns:
        user domain object, or None (after redirecting).
    Usage:
        user = require_current_user()
        if user is None:
            return  # already redirected
    """
    user = get_current_user()
    if not user:
        clear_session()
        flash("Session expired. Please sign in again.", "warning")
        return None
    return user


def require_current_user_redirect():
    """Get current user or perform redirect to login.
    
    Returns:
        tuple: (user, redirect_response) where redirect_response is 
               a redirect Response if user is None, else None.
    """
    user = get_current_user()
    if not user:
        clear_session()
        flash("Session expired. Please sign in again.", "warning")
        return None, redirect(url_for("auth.login"))
    return user, None


def require_dataset(dataset_id, user_id):
    """Load dataset with ownership validation.
    
    Returns:
        (dataset, error_response) — dataset is DatasetDomain or None.
    """
    from app.services.dataset_service import DatasetService
    dataset = DatasetService.get_dataset(dataset_id, user_id)
    if not dataset:
        return None, ("Dataset not found or you don't have access.", 404)
    return dataset, None


def require_model(model_id, user_id):
    """Load model with ownership validation.
    
    Returns:
        (model, error_response) — model details dict or None.
    """
    from app.services.ml_service import MLService
    model = MLService.get_model_detail(model_id, user_id)
    if not model:
        return None, ("Model not found or you don't have access.", 404)
    return model, None


def safe_int(value, default=None):
    """Safely convert a string to int. Returns default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=None):
    """Safely convert a string to float. Returns default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def validate_pagination(page, per_page, max_per_page=100):
    """Validate and clamp pagination parameters."""
    page = max(1, safe_int(page, 1))
    per_page = max(1, min(safe_int(per_page, 20), max_per_page))
    return page, per_page
