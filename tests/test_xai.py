"""DataViz Pro -- XAI Route Tests
"""
from conftest import BaseTestCase


class TestXAIRoutes(BaseTestCase):
    def test_xai_requires_auth(self):
        resp = self.client.get("/xai", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_xai_model_selection_renders(self):
        self.login()
        resp = self.client.get("/xai")
        self.assertEqual(resp.status_code, 200)

    def test_xai_workspace_not_found(self):
        self.login()
        resp = self.client.get("/models/99999/explain", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"not found", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
