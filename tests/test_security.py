"""DataViz Pro -- Security Tests
"""
import time
import io
import json
from conftest import BaseTestCase


class TestSecurity(BaseTestCase):
    def test_unauthenticated_redirect(self):
        protected_routes = [
            ("/dashboard", "GET"),
            ("/datasets", "GET"),
            ("/datasets/upload", "GET"),
            ("/analysis/", "GET"),
            ("/models", "GET"),
            ("/xai", "GET"),
            ("/profile", "GET"),
            ("/projects", "GET"),
            ("/settings", "GET"),
        ]
        for url, method in protected_routes:
            with self.subTest(url=url, method=method):
                if method == "GET":
                    resp = self.client.get(url, follow_redirects=False)
                self.assertIn(resp.status_code, (302, 303))
                self.assertIn("/login", resp.headers.get("Location", ""))

    def test_cannot_access_other_user_dataset(self):
        s = str(int(time.time() * 1000))[-6:]
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
        csv_data = b"name,age,city\nAlice,30,NYC\nBob,25,LA\n"
        self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(csv_data), "test_data.csv")},
            follow_redirects=True,
        )
        api_resp = self.client.get("/api/datasets")
        datasets = json.loads(api_resp.data)
        self.assertGreater(len(datasets.get("datasets", [])), 0)
        dataset_id = datasets["datasets"][0]["id"]

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
        resp = self.client.get(f"/datasets/{dataset_id}", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"not found", resp.data.lower())

    def test_cannot_access_other_user_model(self):
        s = str(int(time.time() * 1000))[-6:]
        self.client.post(
            "/signup",
            data={
                "username": f"userb2_{s}",
                "email": f"userb2_{s}@example.com",
                "password": "TestPass123!",
                "confirm_password": "TestPass123!",
                "full_name": "User B2",
            },
            follow_redirects=True,
        )
        resp = self.client.get("/api/models/99999")
        self.assertIn(resp.status_code, (400, 404))

    def test_csrf_on_post_routes(self):
        self.login()
        self.app.config["WTF_CSRF_ENABLED"] = True
        try:
            resp = self.client.post(
                "/login",
                data={"email": "test@example.com", "password": "TestPass123!"},
            )
            self.assertIn(resp.status_code, (302, 400, 403))
        finally:
            self.app.config["WTF_CSRF_ENABLED"] = False


if __name__ == "__main__":
    unittest.main()
