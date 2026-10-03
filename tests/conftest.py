"""
DataViz Pro — Test Configuration and Base Test Case

Provides a BaseTestCase with Flask test client, CSRF disabled,
temporary upload directories, and convenient auth helpers.
"""

import os
import sys
import unittest
import tempfile
import shutil
import atexit
import uuid

# Ensure project root AND tests dir are on path
_this_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _this_dir)
sys.path.insert(0, os.path.dirname(_this_dir))

# Always isolate tests, even when the developer's .env selects a live database.
_test_runtime = tempfile.mkdtemp(prefix="dataviz-tests-")
_test_db = os.path.join(_test_runtime, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"
os.environ["SECRET_KEY"] = "isolated-test-session-key"

from app import create_app


def _cleanup_test_runtime():
    from auth.database import engine
    engine.dispose()
    shutil.rmtree(_test_runtime, ignore_errors=True)


atexit.register(_cleanup_test_runtime)


class BaseTestCase(unittest.TestCase):
    """Base test case with Flask test client and test database."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app("testing")
        cls.app.config["TESTING"] = True
        cls.app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF for tests
        cls.client = cls.app.test_client()

        # Create temporary directories for testing
        cls.temp_dir = tempfile.mkdtemp()
        cls.app.config["UPLOAD_FOLDER"] = os.path.join(cls.temp_dir, "uploads")
        cls.app.config["REPORTS_FOLDER"] = os.path.join(cls.temp_dir, "reports")
        os.makedirs(cls.app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(cls.app.config["REPORTS_FOLDER"], exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        # Each case gets a fresh limiter while still exercising real limits.
        from app.security import rate_limiter
        with rate_limiter._lock:
            rate_limiter._store.clear()
        self.ctx = self.app.app_context()
        self.ctx.push()
        # Clear session cookie before each test to prevent leakage
        self.client.get("/logout")

    def tearDown(self):
        self.ctx.pop()

    # ── Unique test identifiers ──────────────────────────────────

    @staticmethod
    def _unique_suffix():
        """Return a short unique suffix to avoid DB collisions."""
        return uuid.uuid4().hex[:12]

    # ── Auth helpers ────────────────────────────────────────────

    def register(
        self,
        username=None,
        email=None,
        password="TestPass123!",
        full_name="Test User",
    ):
        """Register a test user and return the response.

        Uses a unique suffix to avoid DB unique-constraint violations.
        """
        s = self._unique_suffix()
        username = username or f"testuser_{s}"
        email = email or f"test_{s}@example.com"
        return self.client.post(
            "/signup",
            data={
                "username": username,
                "email": email,
                "password": password,
                "confirm_password": password,
                "full_name": full_name,
            },
            follow_redirects=True,
        )

    def login(self, email=None, password="TestPass123!"):
        """Login and return the response.

        Registers a fresh user first, then logs in with those credentials.
        """
        s = self._unique_suffix()
        email = email or f"test_{s}@example.com"
        username = f"testuser_{s}"
        # Register
        self.client.post(
            "/signup",
            data={
                "username": username,
                "email": email,
                "password": password,
                "confirm_password": password,
                "full_name": "Test User",
            },
            follow_redirects=True,
        )
        # Logout
        self.client.get("/logout", follow_redirects=True)
        # Login
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def login_with(self, email, password):
        """Login with specific credentials (no auto-register)."""
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def logout(self):
        """Logout and return the response."""
        return self.client.get("/logout", follow_redirects=True)
