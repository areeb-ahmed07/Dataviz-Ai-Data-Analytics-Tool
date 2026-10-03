"""
DataViz Pro — Analysis Route Tests
"""

import json
from conftest import BaseTestCase


class TestAnalysisRoutes(BaseTestCase):
    def test_analysis_requires_auth(self):
        resp = self.client.get("/analysis/", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_analysis_selector_renders(self):
        self.login()
        resp = self.client.get("/analysis/")
        self.assertEqual(resp.status_code, 200)

    def test_analysis_overview_api_returns_json(self):
        self.login()
        resp = self.client.get("/analysis/api/datasets")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIsInstance(data, list)

    def test_analysis_with_nonexistent_dataset(self):
        self.login()
        resp = self.client.get("/analysis/99999/overview", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"not found", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
