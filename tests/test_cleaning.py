"""
DataViz Pro — Cleaning Route Tests
"""
import json
from conftest import BaseTestCase


class TestCleaningRoutes(BaseTestCase):
    def test_cleaning_studio_requires_auth(self):
        resp = self.client.get("/datasets/1/clean", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_cleaning_detect_api(self):
        self.login()
        resp = self.client.get("/api/datasets/99999/clean/detect")
        self.assertIn(resp.status_code, (400, 404))
        data = json.loads(resp.data)
        self.assertIn("error", data)

    def test_cleaning_nonexistent_dataset(self):
        self.login()
        resp = self.client.get("/datasets/99999/clean", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"not found", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
