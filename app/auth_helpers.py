"""
DataViz Pro — Flask Authentication Helpers (Phase 13: Cached)

Provides login_required decorator and current_user helper for Flask routes.
Uses Flask sessions (server-side) instead of JWT for browser-based auth.
User objects are cached per-request to avoid redundant DB queries
when multiple routes/helpers call get_current_user() in the same request.
"""

from functools import wraps
from flask import session, redirect, url_for, flash, request, g
from auth.database import UserDB, get_session
from auth.domain.user import UserDomain

# Per-request user cache: avoid DB query when called multiple times per request
_request_cache = {}


def login_required(view_func):
    """
    Decorator that redirects unauthenticated users to /login.
    Stores the intended URL so the user can be redirected back after login.
    """
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session or not session.get("authenticated"):
            session["next_url"] = request.path
            flash("Please sign in to access this page.", "warning")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)
    return wrapped


def get_current_user() -> UserDomain | None:
    """
    Retrieve the authenticated user. Results are cached within the
    current request to avoid redundant DB queries (multiple routes/helpers
    call this per request).

    Returns None if not authenticated or user not found/inactive.
    """
    user_id = session.get("user_id")
    if not user_id:
        return None

    # Per-request cache: g is scoped to a single request
    uid = int(user_id)
    if not hasattr(request, '_cached_user'):
        request._cached_user = {}
    if uid in request._cached_user:
        return request._cached_user[uid]

    db = get_session()
    try:
        user_db = db.query(UserDB).filter(UserDB.id == uid).first()
        if user_db and user_db.is_active:
            domain = user_db.to_domain()
            request._cached_user[uid] = domain
            return domain
    except Exception:
        pass
    finally:
        db.close()
    return None


def set_session_user(user_domain: UserDomain) -> None:
    """
    Store minimal user identity in the Flask session.
    Never stores passwords, tokens, or sensitive data.
    """
    session["user_id"] = user_domain.id
    session["username"] = user_domain.username
    session["full_name"] = user_domain.full_name
    session["email"] = user_domain.email
    session["role"] = user_domain.role.value if hasattr(user_domain.role, "value") else str(user_domain.role)
    session["authenticated"] = True
    session.permanent = True


def clear_session() -> None:
    """Remove all authentication-related session data."""
    for key in ("user_id", "username", "full_name", "email", "role", "authenticated", "next_url"):
        session.pop(key, None)
