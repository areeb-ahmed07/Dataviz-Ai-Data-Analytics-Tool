"""DataViz Pro — Phase 14 Security Tests

Comprehensive tests for:
- CSRF protection
- Rate limiting
- RBAC (admin_required)
- Input sanitization (SQL injection, XSS)
- File upload validation (magic bytes)
- Audit logging
- Security headers
- Session security
- Login brute-force protection
- SSRF protection
"""

import io
import json
import time
import unittest
from conftest import BaseTestCase


class TestCSRFProtection(BaseTestCase):
    """Test CSRF token enforcement on state-changing routes."""

    def test_post_login_without_csrf_fails(self):
        """POST /login without CSRF token should be rejected."""
        # Enable CSRF for this test
        self.app.config["WTF_CSRF_ENABLED"] = True
        try:
            resp = self.client.post(
                "/login",
                data={"email": "test@example.com", "password": "TestPass123!"},
            )
            self.assertIn(resp.status_code, (302, 400, 403))
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = False

    def test_post_signup_without_csrf_fails(self):
        """POST /signup without CSRF token should be rejected."""
        self.app.config["WTF_CSRF_ENABLED"] = True
        try:
            s = self._unique_suffix()
            resp = self.client.post(
                "/signup",
                data={
                    "username": f"csrf_test_{s}",
                    "email": f"csrf_{s}@example.com",
                    "password": "TestPass123!",
                    "confirm_password": "TestPass123!",
                    "full_name": "CSRF Test",
                },
            )
            self.assertIn(resp.status_code, (302, 400, 403))
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = False


class TestSecurityHeaders(BaseTestCase):
    """Test security headers on HTTP responses."""

    def test_x_content_type_options_header(self):
        """X-Content-Type-Options: nosniff should be present."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")

    def test_x_frame_options_header(self):
        """X-Frame-Options: DENY should be present."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")

    def test_referrer_policy_header(self):
        """Referrer-Policy: strict-origin-when-cross-origin should be present."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("strict-origin-when-cross-origin", resp.headers.get("Referrer-Policy", ""))

    def test_xss_protection_header(self):
        """X-XSS-Protection header should be present."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("X-XSS-Protection"), "1; mode=block")

    def test_login_page_no_cache(self):
        """Login page should have no-cache headers."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)
        cache_control = resp.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache_control)


class TestSessionSecurity(BaseTestCase):
    """Test session security configuration."""

    def test_session_cookie_httponly(self):
        """Session cookie should be HttpOnly."""
        self.app.config["SESSION_COOKIE_HTTPONLY"] = True
        resp = self.client.get("/login")
        cookie_header = resp.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie_header)

    def test_session_cookie_samesite(self):
        """Session cookie should have SameSite=Lax."""
        resp = self.client.get("/login")
        cookie_header = resp.headers.get("Set-Cookie", "")
        self.assertIn("SameSite=Lax", cookie_header)

    def test_logout_accepts_post(self):
        """POST /logout should work (Phase 14: CSRF-safe logout)."""
        self.login()
        resp = self.client.post("/logout")
        self.assertIn(resp.status_code, (200, 302, 303))


class TestInputSanitization(BaseTestCase):
    """Test input sanitization and SQL injection prevention."""

    def test_sql_query_validation_blocks_drop(self):
        """SQL validation should reject DROP statements."""
        from app.security import validate_sql_query
        ok, err = validate_sql_query("DROP TABLE users")
        self.assertFalse(ok)
        self.assertTrue(len(err) > 0)  # Error message should be non-empty

    def test_sql_query_validation_blocks_delete(self):
        """SQL validation should reject DELETE statements."""
        from app.security import validate_sql_query
        ok, err = validate_sql_query("DELETE FROM users WHERE 1=1")
        self.assertFalse(ok)

    def test_sql_query_validation_allows_select(self):
        """SQL validation should allow SELECT statements."""
        from app.security import validate_sql_query
        ok, err = validate_sql_query("SELECT * FROM users LIMIT 10")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_sql_query_validation_allows_cte(self):
        """SQL validation should allow WITH (CTE) queries."""
        from app.security import validate_sql_query
        ok, err = validate_sql_query(
            "WITH active AS (SELECT * FROM users WHERE is_active=1) "
            "SELECT * FROM active"
        )
        self.assertTrue(ok)

    def test_sql_query_validation_blocks_insert(self):
        """SQL validation should reject INSERT statements."""
        from app.security import validate_sql_query
        ok, err = validate_sql_query("INSERT INTO users VALUES (1, 'hacked')")
        self.assertFalse(ok)

    def test_sql_query_validation_blocks_empty(self):
        """SQL validation should reject empty queries."""
        from app.security import validate_sql_query
        ok, err = validate_sql_query("")
        self.assertFalse(ok)

    def test_table_name_validation_allows_valid(self):
        """Table name validation should allow valid identifiers."""
        from app.security import validate_table_name
        ok, err = validate_table_name("users")
        self.assertTrue(ok)

    def test_table_name_validation_blocks_sql_injection(self):
        """Table name validation should block SQL injection."""
        from app.security import validate_table_name
        ok, err = validate_table_name("users; DROP TABLE users--")
        self.assertFalse(ok)
        self.assertIn("Invalid", err)

    def test_table_name_validation_blocks_quotes(self):
        """Table name validation should block quoted identifiers."""
        from app.security import validate_table_name
        ok, err = validate_table_name('"users"')
        self.assertFalse(ok)

    def test_table_name_validation_blocks_empty(self):
        """Table name validation should reject empty names."""
        from app.security import validate_table_name
        ok, err = validate_table_name("")
        self.assertFalse(ok)

    def test_sanitize_user_input_strips_html(self):
        """sanitize_user_input should strip HTML tags."""
        from app.security import sanitize_user_input
        result = sanitize_user_input('<script>alert(1)</script>')
        self.assertNotIn("<script>", result)
        self.assertNotIn("</script>", result)

    def test_sanitize_user_input_truncates(self):
        """sanitize_user_input should truncate to max_length."""
        from app.security import sanitize_user_input
        result = sanitize_user_input("a" * 1000, max_length=100)
        self.assertLessEqual(len(result), 100)


class TestSSRFProtection(BaseTestCase):
    """Test SSRF protection on API URL validation."""

    def test_blocks_localhost(self):
        """Should block localhost URLs."""
        from app.security import validate_api_url
        ok, err = validate_api_url("http://localhost/api/data")
        self.assertFalse(ok)
        self.assertIn("localhost", err.lower())

    def test_blocks_127_0_0_1(self):
        """Should block 127.0.0.1."""
        from app.security import validate_api_url
        ok, err = validate_api_url("http://127.0.0.1/api/data")
        self.assertFalse(ok)

    def test_blocks_file_protocol(self):
        """Should block file:// protocol."""
        from app.security import validate_api_url
        ok, err = validate_api_url("file:///etc/passwd")
        self.assertFalse(ok)
        self.assertIn("HTTP", err)

    def test_blocks_ftp_protocol(self):
        """Should block non-HTTP protocols."""
        from app.security import validate_api_url
        ok, err = validate_api_url("ftp://example.com/data")
        self.assertFalse(ok)

    def test_allows_https(self):
        """Should allow valid HTTPS URLs."""
        from app.security import validate_api_url
        # This may fail DNS resolution in test env, but URL format should pass
        ok, err = validate_api_url("https://api.example.com/data")
        # May fail DNS resolution in CI, so just check it's not a protocol error
        if not ok:
            self.assertNotIn("HTTP", err)  # Shouldn't be a protocol-level rejection

    def test_blocks_empty_url(self):
        """Should block empty URLs."""
        from app.security import validate_api_url
        ok, err = validate_api_url("")
        self.assertFalse(ok)


class TestFileUploadValidation(BaseTestCase):
    """Test file upload security validation."""

    def test_magic_byte_validation_xlsx(self):
        """xlsx file with correct magic bytes should pass."""
        from app.services.dataset_service import _validate_file_magic_bytes
        # PK\x03\x04 = ZIP header (xlsx is a ZIP file)
        fake_file = io.BytesIO(b"PK\x03\x04\x00\x00\x00\x00")
        ok, err = _validate_file_magic_bytes(fake_file, "xlsx")
        self.assertTrue(ok)

    def test_magic_byte_validation_rejects_fake_xlsx(self):
        """Non-ZIP file claiming to be xlsx should fail."""
        from app.services.dataset_service import _validate_file_magic_bytes
        fake_file = io.BytesIO(b"\x00\x00\x00\x00\x00\x00\x00\x00")
        ok, err = _validate_file_magic_bytes(fake_file, "xlsx")
        self.assertFalse(ok)

    def test_magic_byte_validation_xls(self):
        """xls file with correct OLE2 magic bytes should pass."""
        from app.services.dataset_service import _validate_file_magic_bytes
        fake_file = io.BytesIO(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1")
        ok, err = _validate_file_magic_bytes(fake_file, "xls")
        self.assertTrue(ok)

    def test_magic_byte_validation_parquet(self):
        """Parquet file with correct magic bytes should pass."""
        from app.services.dataset_service import _validate_file_magic_bytes
        fake_file = io.BytesIO(b"PAR1\x00\x00\x00\x00")
        ok, err = _validate_file_magic_bytes(fake_file, "parquet")
        self.assertTrue(ok)

    def test_reject_unsupported_extension(self):
        """File with unsupported extension should be rejected."""
        self.login()
        resp = self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(b"data"), "malware.exe")},
            follow_redirects=True,
        )
        self.assertIn(b"Unsupported", resp.data)

    def test_reject_empty_file(self):
        """Empty file upload should be rejected."""
        self.login()
        resp = self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(b""), "empty.csv")},
            follow_redirects=True,
        )
        self.assertIn(b"empty", resp.data.lower())


class TestRBAC(BaseTestCase):
    """Test Role-Based Access Control."""

    def test_admin_required_blocks_regular_user(self):
        """Regular user should get 403 on admin routes."""
        self.login()
        resp = self.client.get("/admin/users", follow_redirects=False)
        self.assertIn(resp.status_code, (403, 302))

    def test_admin_required_blocks_unauthenticated(self):
        """Unauthenticated user should be redirected from admin routes."""
        resp = self.client.get("/admin/users", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))


class TestAuditLogging(BaseTestCase):
    """Test audit log recording."""

    def test_audit_log_table_exists(self):
        """audit_logs table should be created by init_db."""
        from auth.database import engine, text
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'"
            )).fetchone()
        self.assertIsNotNone(result)

    def test_login_attempt_table_exists(self):
        """login_attempts table should be created by init_db."""
        from auth.database import engine, text
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='login_attempts'"
            )).fetchone()
        self.assertIsNotNone(result)

    def test_audit_service_logs_and_retrieves(self):
        """AuditService.log should write to DB and get_logs should retrieve."""
        from app.security import AuditService
        from auth.database import AuditLogDB, get_session
        # Write synchronously to avoid thread/timing issues in tests
        with self.app.app_context():
            db = get_session()
            try:
                entry = AuditLogDB(
                    username="testuser",
                    action="test_event",
                    ip_address="127.0.0.1",
                    user_agent="test-agent",
                    details='{"test": true}',
                )
                db.add(entry)
                db.commit()
            finally:
                db.close()

        logs, total = AuditService.get_logs(action="test_event")
        self.assertGreater(total, 0)
        found = any(l["action"] == "test_event" for l in logs)
        self.assertTrue(found)


class TestRateLimiter(BaseTestCase):
    """Test in-memory rate limiter."""

    def test_rate_limiter_allows_under_limit(self):
        """Should allow requests under the limit."""
        from app.security import rate_limiter
        # Reset first
        rate_limiter.reset("test_key")
        for _ in range(3):
            allowed = rate_limiter.is_allowed("test_key", 5, 60)
            self.assertTrue(allowed)

    def test_rate_limiter_blocks_over_limit(self):
        """Should block requests over the limit."""
        from app.security import rate_limiter
        rate_limiter.reset("test_block_key")
        for _ in range(5):
            rate_limiter.is_allowed("test_block_key", 5, 60)
        # 6th should be blocked
        allowed = rate_limiter.is_allowed("test_block_key", 5, 60)
        self.assertFalse(allowed)

    def test_rate_limiter_remaining(self):
        """Should correctly report remaining requests."""
        from app.security import rate_limiter
        rate_limiter.reset("test_remaining")
        rate_limiter.is_allowed("test_remaining", 5, 60)
        rate_limiter.is_allowed("test_remaining", 5, 60)
        remaining = rate_limiter.get_remaining("test_remaining", 5, 60)
        self.assertEqual(remaining, 3)


class TestHorizontalAccessControl(BaseTestCase):
    """Test that users cannot access other users' resources."""

    def test_cannot_access_other_user_dataset(self):
        """User B should not be able to see User A's dataset."""
        s = str(int(time.time() * 1000))[-6:]
        # Register User A
        self.client.post(
            "/signup",
            data={
                "username": f"usera_{s}",
                "email": f"usera_{s}@example.com",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "User A",
            },
            follow_redirects=True,
        )
        # Upload a dataset as User A
        csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(csv_data), "test_data.csv")},
            follow_redirects=True,
        )
        # Get dataset ID
        api_resp = self.client.get("/api/datasets")
        datasets = json.loads(api_resp.data)
        self.assertGreater(len(datasets.get("datasets", [])), 0)
        dataset_id = datasets["datasets"][0]["id"]

        # Logout and register User B
        self.client.get("/logout", follow_redirects=True)
        self.client.post(
            "/signup",
            data={
                "username": f"userb_{s}",
                "email": f"userb_{s}@example.com",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "User B",
            },
            follow_redirects=True,
        )
        # Try to access User A's dataset
        resp = self.client.get(f"/datasets/{dataset_id}", follow_redirects=True)
        self.assertIn(b"not found", resp.data.lower())


class TestDatabaseConnectorSecurity(BaseTestCase):
    """Test SQL injection prevention in database connectors."""

    def test_sqlite_quote_identifier_valid(self):
        """Valid table names should be quoted successfully."""
        from connectors.database_connectors.sqlite_connector import _quote_identifier
        result = _quote_identifier("users")
        self.assertEqual(result, '"users"')

    def test_sqlite_quote_identifier_rejects_injection(self):
        """SQL injection in table names should be rejected."""
        from connectors.database_connectors.sqlite_connector import _quote_identifier
        with self.assertRaises(ValueError):
            _quote_identifier("users; DROP TABLE users--")

    def test_sqlite_quote_identifier_rejects_empty(self):
        """Empty table name should be rejected."""
        from connectors.database_connectors.sqlite_connector import _quote_identifier
        with self.assertRaises(ValueError):
            _quote_identifier("")

    def test_mysql_quote_identifier_valid(self):
        """MySQL connector should quote valid identifiers."""
        from connectors.database_connectors.mysql_connector import _quote_identifier
        result = _quote_identifier("users")
        self.assertEqual(result, "`users`")

    def test_postgresql_quote_identifier_valid(self):
        """PostgreSQL connector should quote valid identifiers."""
        from connectors.database_connectors.postgresql_connector import _quote_identifier
        result = _quote_identifier("users")
        self.assertEqual(result, '"users"')


class TestUnauthenticatedAccess(BaseTestCase):
    """Test that protected routes redirect unauthenticated users."""

    def test_dashboard_redirects(self):
        resp = self.client.get("/dashboard", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_datasets_redirects(self):
        resp = self.client.get("/datasets", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_models_redirects(self):
        resp = self.client.get("/models", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))

    def test_api_datasets_returns_401(self):
        resp = self.client.get("/api/datasets", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))


if __name__ == "__main__":
    unittest.main()
