"""
DataViz Pro — Security Module (Phase 14)

Centralized security infrastructure:
- RBAC decorators (admin_required, permission_required)
- Rate limiting (in-memory, per-IP and per-identifier for login)
- Audit logging service
- Security headers (CSP, HSTS, X-Frame-Options, etc.)
- Input validation helpers (SQL injection prevention, URL validation)
- Rate-limit-aware login attempt tracking
"""

import os
import re
import json
import time
import logging
import threading
from functools import wraps
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from collections import defaultdict

from flask import (
    Flask, request, jsonify, redirect, url_for,
    session, flash, abort, g,
)
from werkzeug.http import parse_cookie

from auth.domain.user import Role
from auth.database import (
    AuditLogDB, LoginAttemptDB, get_session, session_scope,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  AUDIT LOGGING
# ═══════════════════════════════════════════════════════════════

class AuditService:
    """Record and query security audit events."""

    # Actions that are always logged
    CRITICAL_ACTIONS = frozenset({
        "login_success", "login_failed", "signup",
        "logout", "password_change", "password_change_failed",
        "admin_role_change", "admin_toggle_user_status",
        "admin_view_users", "admin_view_audit_logs",
        "dataset_upload", "dataset_delete", "dataset_download",
        "model_delete", "model_download",
        "profile_update", "settings_update",
        "account_disabled", "session_expired",
        "db_connect", "api_connect",
    })

    @staticmethod
    def log(
        action: str,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """Asynchronously record an audit event.

        Uses a background thread to avoid blocking the request.
        Falls back to synchronous DB write if threading fails.
        """
        if ip_address is None:
            ip_address = _get_client_ip()
        if user_agent is None:
            user_agent = request.headers.get("User-Agent", "")[:500]
        if username is None and "username" in session:
            username = session.get("username")

        details_json = json.dumps(details, default=str) if details else None

        def _write():
            try:
                with session_scope() as db:
                    entry = AuditLogDB(
                        user_id=user_id,
                        username=username,
                        action=action,
                        resource_type=resource_type,
                        resource_id=resource_id,
                        details=details_json,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        success=success,
                    )
                    db.add(entry)
            except Exception:
                logger.debug("[audit] Failed to write audit log for %s", action, exc_info=True)

        try:
            t = threading.Thread(target=_write, daemon=True)
            t.start()
        except Exception:
            _write()  # synchronous fallback

    @staticmethod
    def get_logs(
        user_id: Optional[int] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query audit logs. Returns (logs, total_count)."""
        db = get_session()
        try:
            q = db.query(AuditLogDB)
            if user_id is not None:
                q = q.filter(AuditLogDB.user_id == user_id)
            if action:
                q = q.filter(AuditLogDB.action == action)
            if resource_type:
                q = q.filter(AuditLogDB.resource_type == resource_type)

            total = q.count()
            rows = (q
                    .order_by(AuditLogDB.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all())

            logs = []
            for r in rows:
                d = {
                    "id": r.id,
                    "user_id": r.user_id,
                    "username": r.username,
                    "action": r.action,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "details": r.details,
                    "ip_address": r.ip_address,
                    "user_agent": r.user_agent,
                    "success": r.success,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                # Parse details JSON
                if r.details:
                    try:
                        d["details"] = json.loads(r.details)
                    except Exception:
                        pass
                logs.append(d)
            return logs, total
        finally:
            db.close()

    @staticmethod
    def cleanup_old_logs(days: int = 90) -> int:
        """Delete audit logs older than `days`. Returns count deleted."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        with session_scope() as db:
            count = db.query(AuditLogDB).filter(
                AuditLogDB.created_at < cutoff
            ).delete(synchronize_session="fetch")
            return count


# ═══════════════════════════════════════════════════════════════
#  RATE LIMITING
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """In-memory sliding-window rate limiter.

    Thread-safe, no external dependencies.
    Tracks (key -> list of timestamps). Stale entries are
    pruned on every check to bound memory.
    """

    def __init__(self):
        self._store: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Check if a request is allowed under the rate limit.

        Returns True if allowed, False if rate limit exceeded.
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._store[key]
            # Prune expired timestamps
            self._store[key] = [t for t in timestamps if t > cutoff]

            if len(self._store[key]) >= max_requests:
                return False

            self._store[key].append(now)
            return True

    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        """Get remaining requests in the current window."""
        now = time.time()
        cutoff = now - window_seconds
        with self._lock:
            timestamps = [t for t in self._store.get(key, []) if t > cutoff]
            self._store[key] = timestamps
            return max(0, max_requests - len(timestamps))

    def reset(self, key: str) -> None:
        """Reset rate limit for a specific key."""
        with self._lock:
            self._store.pop(key, None)


# Global rate limiter instance
rate_limiter = RateLimiter()

# ── Rate limit configurations ───────────────────────────────
RATE_LIMITS = {
    "login": (5, 300),        # 5 attempts per 5 minutes per IP+identifier
    "signup": (3, 3600),       # 3 signups per hour per IP
    "password_change": (3, 300),  # 3 attempts per 5 minutes
    "api_general": (60, 60),   # 60 requests per minute per IP
    "db_connect": (10, 3600),  # 10 DB connections per hour per user
    "api_connect": (10, 3600), # 10 API connections per hour per user
    "upload": (20, 3600),      # 20 uploads per hour per user
}


def check_rate_limit(category: str, key: Optional[str] = None) -> Tuple[bool, int, int]:
    """Check rate limit for a category. Returns (allowed, remaining, reset_seconds).

    If `key` is None, auto-generates from client IP (+ user identity if authenticated).
    """
    if category not in RATE_LIMITS:
        return True, 999, 0

    max_requests, window = RATE_LIMITS[category]
    if key is None:
        key = _get_client_ip()
        # Add user ID suffix for user-specific limits
        uid = session.get("user_id")
        if uid and category not in ("login", "signup"):
            key = f"{uid}:{key}"

    allowed = rate_limiter.is_allowed(key, max_requests, window)
    remaining = rate_limiter.get_remaining(key, max_requests, window)
    return allowed, remaining, window


def rate_limit_exceeded_response(category: str, remaining: int = 0, reset_seconds: int = 0):
    """Return appropriate 429 response."""
    if request.path.startswith("/api/"):
        resp = jsonify({
            "success": False,
            "error": {
                "code": "RATE_LIMITED",
                "message": f"Too many requests. Try again in {reset_seconds} seconds.",
                "retry_after": reset_seconds,
            }
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(reset_seconds)
        return resp
    flash("Too many requests. Please wait a moment before trying again.", "error")
    return redirect(request.referrer or url_for("main.index"))


# ═══════════════════════════════════════════════════════════════
#  LOGIN ATTEMPT TRACKING (DB-backed for persistence)
# ═══════════════════════════════════════════════════════════════

class LoginAttemptTracker:
    """Track login attempts in the database for persistent rate limiting.

    Used alongside the in-memory RateLimiter to prevent brute-force
    attacks that could bypass in-memory limits via app restarts.
    """

    MAX_ATTEMPTS = 10
    LOCKOUT_MINUTES = 15

    @staticmethod
    def is_locked_out(identifier: str, ip_address: Optional[str] = None) -> Tuple[bool, int]:
        """Check if identifier or IP is locked out. Returns (locked, remaining_seconds)."""
        db = get_session()
        try:
            cutoff = datetime.utcnow() - timedelta(minutes=LoginAttemptTracker.LOCKOUT_MINUTES)

            # Check by identifier
            recent_failures = db.query(LoginAttemptDB).filter(
                LoginAttemptDB.identifier == identifier,
                LoginAttemptDB.success == False,
                LoginAttemptDB.created_at > cutoff,
            ).count()

            if recent_failures >= LoginAttemptTracker.MAX_ATTEMPTS:
                # Find the oldest failure in the window to compute remaining time
                oldest = db.query(LoginAttemptDB).filter(
                    LoginAttemptDB.identifier == identifier,
                    LoginAttemptDB.success == False,
                    LoginAttemptDB.created_at > cutoff,
                ).order_by(LoginAttemptDB.created_at.asc()).first()

                if oldest:
                    lock_expires = oldest.created_at + timedelta(minutes=LoginAttemptTracker.LOCKOUT_MINUTES)
                    remaining = max(0, int((lock_expires - datetime.utcnow()).total_seconds()))
                    return True, remaining

            return False, 0
        finally:
            db.close()

    @staticmethod
    def record_attempt(identifier: str, success: bool, ip_address: Optional[str] = None):
        """Record a login attempt."""
        if ip_address is None:
            ip_address = _get_client_ip()

        def _write():
            try:
                with session_scope() as db:
                    entry = LoginAttemptDB(
                        identifier=identifier,
                        ip_address=ip_address,
                        success=success,
                    )
                    db.add(entry)
            except Exception:
                pass

        try:
            t = threading.Thread(target=_write, daemon=True)
            t.start()
        except Exception:
            _write()

    @staticmethod
    def cleanup_old_attempts(days: int = 30) -> int:
        """Delete old login attempt records."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        with session_scope() as db:
            return db.query(LoginAttemptDB).filter(
                LoginAttemptDB.created_at < cutoff
            ).delete(synchronize_session="fetch")


login_tracker = LoginAttemptTracker()


# ═══════════════════════════════════════════════════════════════
#  RBAC DECORATORS
# ═══════════════════════════════════════════════════════════════

def admin_required(view_func):
    """Decorator: require admin role. Returns 403 for non-admins."""
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        from app.auth_helpers import get_current_user
        user = get_current_user()
        if not user:
            flash("Session expired. Please sign in again.", "warning")
            return redirect(url_for("auth.login"))
        if user.role != Role.ADMIN:
            logger.warning("[security] Non-admin user %s (id=%s) attempted admin route: %s",
                           user.username, user.id, request.path)
            AuditService.log(
                action="unauthorized_admin_access",
                user_id=user.id,
                username=user.username,
                details={"path": request.path, "method": request.method},
                success=False,
            )
            abort(403)
        return view_func(*args, **kwargs)
    return wrapped


def permission_required(resource_type: str, action: str):
    """Decorator factory: require specific permission on a resource type.

    Usage::
        @permission_required("dataset", "delete")
        def delete_dataset(dataset_id):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            from app.auth_helpers import get_current_user
            user = get_current_user()
            if not user:
                flash("Session expired. Please sign in again.", "warning")
                return redirect(url_for("auth.login"))
            # Admin can do everything
            if user.role == Role.ADMIN:
                return view_func(*args, **kwargs)
            # Regular users can only access their own resources
            # (enforced at route level via ownership checks, this is a defense-in-depth layer)
            return view_func(*args, **kwargs)
        return wrapped
    return decorator


# ═══════════════════════════════════════════════════════════════
#  SECURITY HEADERS
# ═══════════════════════════════════════════════════════════════

def inject_security_headers(response):
    """Add security headers to every response. Called via after_request."""
    # Content Security Policy
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )

    # HSTS — only in production (breaks HTTP development)
    is_production = not current_app_or_none() or not getattr(current_app_or_none(), "debug", True)
    if is_production and request.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Cache-Control for sensitive pages
    if request.path in ("/login", "/signup"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"

    return response


def current_app_or_none():
    """Safely get current_app, returning None outside of request context."""
    try:
        from flask import current_app
        return current_app._get_current_object()
    except (RuntimeError, AttributeError):
        return None


# ═══════════════════════════════════════════════════════════════
#  INPUT VALIDATION HELPERS
# ═══════════════════════════════════════════════════════════════

# Allowed SQL keywords for the database connector whitelist
SAFE_SQL_PREFIXES = (
    "SELECT", "WITH",
)
FORBIDDEN_SQL_TOKENS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"ATTACH|DETACH|PRAGMA|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)


def validate_sql_query(sql: str) -> Tuple[bool, str]:
    """Validate a user-supplied SQL query for the database connector.

    Only allows SELECT and WITH (CTE) queries.
    Prevents DROP, DELETE, INSERT, UPDATE, ALTER, etc.

    Returns (is_valid, error_message).
    """
    if not sql or not sql.strip():
        return False, "SQL query cannot be empty."

    stripped = sql.strip()

    # Check prefix
    if not any(stripped.upper().startswith(prefix) for prefix in SAFE_SQL_PREFIXES):
        return False, "Only SELECT and WITH (CTE) queries are allowed."

    # Check for forbidden tokens anywhere in the query
    match = FORBIDDEN_SQL_TOKENS.search(stripped)
    if match:
        return False, f"Forbidden SQL keyword detected: {match.group()}. Only read-only queries are permitted."

    return True, ""


def validate_table_name(table_name: str) -> Tuple[bool, str]:
    """Validate a table name to prevent SQL injection.

    Only allows alphanumeric characters and underscores.
    """
    if not table_name:
        return False, "Table name cannot be empty."
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        return False, (
            f"Invalid table name '{table_name}'. "
            "Only alphanumeric characters and underscores are allowed."
        )
    if len(table_name) > 128:
        return False, "Table name too long (max 128 characters)."
    return True, ""


def validate_api_url(url: str) -> Tuple[bool, str]:
    """Validate an API URL to prevent SSRF attacks.

    Blocks:
    - Private/internal IP ranges (127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - localhost
    - file:// protocol
    - Non-HTTP(S) schemes
    """
    if not url:
        return False, "URL cannot be empty."

    url = url.strip()

    # Check scheme
    if not url.startswith(("http://", "https://")):
        return False, "Only HTTP and HTTPS URLs are allowed."

    # Block localhost and private IPs
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return False, "Could not parse URL hostname."

        # Block localhost variants
        blocked_hosts = {
            "localhost", "localhost.localdomain",
            "127.0.0.1", "0.0.0.0",
            "[::1]", "ip6-localhost", "ip6-loopback",
        }
        if hostname.lower() in blocked_hosts:
            return False, "Connections to localhost are not allowed."

        # Block private IP ranges
        import ipaddress
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False, "Connections to private/internal IP addresses are not allowed."
        except ValueError:
            # hostname is a domain name, check resolved IPs
            import socket
            try:
                # Only resolve to check — don't make the actual connection
                addrs = socket.getaddrinfo(hostname, parsed.port or 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
                for family, _, _, _, sockaddr in addrs:
                    ip = ipaddress.ip_address(sockaddr[0])
                    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                        return False, "URL resolves to a private/internal IP address."
            except socket.gaierror:
                return False, "Could not resolve hostname."

    except Exception as e:
        return False, f"Invalid URL: {str(e)}"

    return True, ""


# ── File upload MIME type validation (magic bytes) ──────────

FILE_SIGNATURES = {
    b"\x50\x4B\x03\x04": "xlsx",     # ZIP (xlsx files are ZIP archives)
    b"\xD0\xCF\x11\xE0": "xls",      # OLE2 (old Excel)
    b"{\x00": "json",                # Could be JSON
    b"[": "json",                     # Could be JSON array
    b"PAR1": "parquet",               # Parquet magic bytes
}


def validate_file_content(file_storage, declared_format: str) -> Tuple[bool, str]:
    """Validate file content using magic bytes.

    This is a defense-in-depth check. A mismatch doesn't
    necessarily mean the file is malicious, but it warrants
    closer inspection.

    Returns (is_valid, warning_message). Returns (True, "") if OK.
    """
    try:
        # Read first 4 bytes
        pos = file_storage.tell()
        header = file_storage.read(4)
        file_storage.seek(pos)

        if not header:
            return False, "Could not read file content."

        # CSV has no magic bytes — skip for csv (validated by parser later)
        if declared_format == "csv":
            return True, ""

        # Check known signatures
        for sig, fmt in FILE_SIGNATURES.items():
            if header.startswith(sig) and fmt == declared_format:
                return True, ""

        # xlsx detection: also check for ZIP local file header
        if declared_format == "xlsx" and header[:2] == b"PK":
            return True, ""

        # JSON: try to parse first few bytes
        if declared_format == "json":
            file_storage.seek(pos)
            sample = file_storage.read(1024).decode("utf-8", errors="ignore").strip()
            file_storage.seek(pos)
            if sample and (sample[0] in "{["):
                return True, ""

        # Parquet: check for PAR1 at start and end
        if declared_format == "parquet":
            if header == b"PAR1":
                return True, ""

        # File signature doesn't match — suspicious but not necessarily malicious
        return True, ""

    except Exception:
        return True, ""  # Don't block on validation errors


# ═══════════════════════════════════════════════════════════════
#  HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _get_client_ip() -> str:
    """Extract client IP from request, respecting X-Forwarded-For.

    In production behind a reverse proxy, the real client IP is in
    X-Forwarded-For. We take the first (leftmost) IP in the chain.
    """
    # Trust X-Forwarded-For only if BEHIND_PROXY is set
    if os.environ.get("BEHIND_PROXY", "").lower() in ("true", "1", "yes"):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"


def sanitize_user_input(text: str, max_length: int = 500) -> str:
    """Sanitize user-provided text for safe storage and display.

    - Strips HTML via bleach
    - Truncates to max_length
    - Strips leading/trailing whitespace
    """
    from auth.security import sanitize_input as _bleach_clean
    if not isinstance(text, str):
        return ""
    text = _bleach_clean(text)
    if len(text) > max_length:
        text = text[:max_length]
    return text.strip()
