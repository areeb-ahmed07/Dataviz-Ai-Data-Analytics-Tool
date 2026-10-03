"""
DataViz Pro — Authentication Route Tests

Tests for signup, login, logout, profile, protected routes,
and session handling via the Flask test client.
"""

import time

from conftest import BaseTestCase


class TestAuthRoutes(BaseTestCase):
    """Test authentication-related routes."""

    # ── Page rendering ──────────────────────────────────────────

    def test_home_page_renders(self):
        """GET / should return 200 and contain the app name."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"DataViz", resp.data)

    def test_signup_page_renders(self):
        """GET /signup should return 200."""
        resp = self.client.get("/signup")
        self.assertEqual(resp.status_code, 200)

    def test_login_page_renders(self):
        """GET /login should return 200."""
        resp = self.client.get("/login")
        self.assertEqual(resp.status_code, 200)

    # ── Signup ──────────────────────────────────────────────────

    def test_signup_with_valid_data(self):
        """Valid registration should redirect to dashboard."""
        s = str(int(time.time() * 1000))[-6:]
        resp = self.client.post(
            "/signup",
            data={
                "username": f"validuser_{s}",
                "email": f"valid_{s}@example.com",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "Valid User",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"dashboard", resp.data.lower())

    def test_signup_with_invalid_email(self):
        """Invalid email should re-render signup with error flash."""
        s = str(int(time.time() * 1000))[-6:]
        resp = self.client.post(
            "/signup",
            data={
                "username": f"bademail_{s}",
                "email": "not-an-email",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "Bad Email",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"valid email", resp.data.lower())

    def test_signup_with_short_password(self):
        """Password shorter than 8 chars should be rejected."""
        s = str(int(time.time() * 1000))[-6:]
        resp = self.client.post(
            "/signup",
            data={
                "username": f"shortpw_{s}",
                "email": f"shortpw_{s}@example.com",
                "password": "short",
                "confirm_password": "short",
                "full_name": "Short Pw",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"at least 8", resp.data.lower())

    def test_signup_with_mismatched_passwords(self):
        """Mismatched password and confirm_password should be rejected."""
        s = str(int(time.time() * 1000))[-6:]
        resp = self.client.post(
            "/signup",
            data={
                "username": f"mismatch_{s}",
                "email": f"mismatch_{s}@example.com",
                "password": "TestPass123!",
                "confirm_password": "DifferentPass456!",
                "full_name": "Mismatch",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"do not match", resp.data.lower())

    def test_signup_with_duplicate_email(self):
        """Duplicate email should fail registration."""
        s = str(int(time.time() * 1000))[-6:]
        email = f"dup_{s}@example.com"

        resp1 = self.client.post(
            "/signup",
            data={
                "username": f"dup_first_{s}",
                "email": email,
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "First",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp1.status_code, 200)

        self.client.get("/logout", follow_redirects=True)

        resp2 = self.client.post(
            "/signup",
            data={
                "username": f"dup_second_{s}",
                "email": email,
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "Second",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp2.status_code, 200)
        self.assertIn(b"already registered", resp2.data.lower())

    # ── Login ───────────────────────────────────────────────────

    def test_login_with_valid_credentials(self):
        """Valid login should redirect to dashboard."""
        resp = self.login()
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"dashboard", resp.data.lower())

    def test_login_with_invalid_credentials(self):
        """Invalid password should show error on login page."""
        s = str(int(time.time() * 1000))[-6:]
        email = f"badcred_{s}@example.com"
        self.client.post(
            "/signup",
            data={
                "username": f"badcred_{s}",
                "email": email,
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "Bad Cred",
            },
            follow_redirects=True,
        )
        self.client.get("/logout", follow_redirects=True)

        resp = self.client.post(
            "/login",
            data={"email": email, "password": "WrongPassword!"},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"invalid", resp.data.lower())

    def test_login_with_empty_fields(self):
        """Empty email or password should show error."""
        resp = self.client.post(
            "/login",
            data={"email": "", "password": ""},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"required", resp.data.lower())

    # ── Logout ──────────────────────────────────────────────────

    def test_logout_redirects(self):
        """GET /logout should clear session and redirect to home."""
        self.login()
        resp = self.logout()
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/dashboard", follow_redirects=False)
        self.assertIn(resp2.status_code, (302, 303))
        self.assertIn("/login", resp2.headers.get("Location", ""))

    # ── Profile ─────────────────────────────────────────────────

    def test_profile_requires_auth(self):
        """GET /profile without auth should redirect to /login."""
        # setUp already cleared session via logout
        resp = self.client.get("/profile", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_profile_page_renders(self):
        """GET /profile when authenticated should return 302 redirect to settings."""
        self.login()
        resp = self.client.get("/profile")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/settings?tab=account", resp.headers["Location"])

    def test_profile_update(self):
        """POST /settings with update_account action should update and redirect."""
        self.login()
        s = str(int(time.time() * 1000))[-6:]
        resp = self.client.post(
            "/settings",
            data={
                "action": "update_account",
                "full_name": "Updated Name",
                "email": f"updated_{s}@example.com",
            },
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        # Check success flash or the profile page renders
        self.assertIn(b"account", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
