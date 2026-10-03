"""DataViz Pro -- API Consistency Tests
"""
import json
from conftest import BaseTestCase


class TestAPIConsistency(BaseTestCase):
    def test_health_check_json(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "ok")
        self.assertIn("version", data)
        self.assertIn("application", data)

    def test_api_unauthenticated_returns_redirect_or_401(self):
        api_endpoints = [
            ("/api/datasets", "GET"),
            ("/analysis/api/datasets", "GET"),
            ("/api/datasets/1", "GET"),
            ("/api/models", "GET"),
            ("/api/xai/models", "GET"),
        ]
        for url, method in api_endpoints:
            with self.subTest(url=url, method=method):
                if method == "GET":
                    resp = self.client.get(url, follow_redirects=False)
                self.assertIn(resp.status_code, (302, 303, 401))

    def test_api_dataset_list_json_format(self):
        self.login()
        resp = self.client.get("/api/datasets")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content_type, "application/json")
        data = json.loads(resp.data)
        self.assertIn("datasets", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["datasets"], list)
        self.assertIsInstance(data["count"], int)

    def test_api_not_found_json(self):
        self.login()
        resp = self.client.get("/api/datasets/99999")
        self.assertIn(resp.status_code, (400, 404))
        data = json.loads(resp.data)
        self.assertIn("error", data)


if __name__ == "__main__":
    unittest.main()
