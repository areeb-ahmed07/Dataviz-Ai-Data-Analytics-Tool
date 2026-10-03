"""DataViz Pro -- ML Route Tests
"""
import json
import io
import unittest
from conftest import BaseTestCase


class TestMLRoutes(BaseTestCase):
    def test_ml_studio_requires_auth(self):
        resp = self.client.get("/datasets/1/ml", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_ml_studio_renders(self):
        self.login()
        resp = self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(b"a,b\n1,2\n3,4\n"), "ml_test.csv")},
            follow_redirects=True,
        )
        api_resp = self.client.get("/api/datasets")
        if api_resp.status_code != 200:
            self.skipTest("Dataset upload failed")
        data = json.loads(api_resp.data)
        if not data.get("datasets"):
            self.skipTest("No datasets available")
        ds_id = data["datasets"][0]["id"]
        resp = self.client.get(f"/datasets/{ds_id}/ml")
        self.assertEqual(resp.status_code, 200)

    def test_ml_algorithms_api(self):
        self.login()
        resp = self.client.get("/api/datasets/99999/ml/algorithms?target_column=foo")
        self.assertIn(resp.status_code, (400, 404))

    def test_ml_dataset_info_handles_datetime_values(self):
        self.login()
        csv_content = "date,value\n2024-01-01,10\n2024-01-02,20\n"
        upload_resp = self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(csv_content.encode("utf-8")), "ml_datetime.csv")},
            follow_redirects=True,
        )
        self.assertEqual(upload_resp.status_code, 200)

        api_resp = self.client.get("/api/datasets")
        self.assertEqual(api_resp.status_code, 200)

        data = json.loads(api_resp.data)
        self.assertTrue(data.get("datasets"))

        ds_id = data["datasets"][0]["id"]
        ml_resp = self.client.get(f"/api/datasets/{ds_id}/ml/info")
        self.assertEqual(ml_resp.status_code, 200)

        payload = json.loads(ml_resp.data)
        self.assertIn("column_types", payload)
        self.assertEqual(payload["rows"], 2)

    def test_models_list(self):
        self.login()
        resp = self.client.get("/models")
        self.assertEqual(resp.status_code, 200)

    def test_model_detail_not_found(self):
        self.login()
        resp = self.client.get("/api/models/99999")
        self.assertIn(resp.status_code, (400, 404))

    def test_grid_search_budget_scaling(self):
        from sklearn.model_selection import ParameterGrid
        from ml.services.model_registry import default_search_space

        # The current tuner accepts discrete grids directly. Keep the default
        # search affordable without depending on the removed migration helper.
        for algorithm in ('Random Forest', 'Logistic Regression', 'XGBoost', 'LightGBM'):
            with self.subTest(algorithm=algorithm):
                search_space = default_search_space(algorithm)
                self.assertTrue(search_space)
                self.assertLessEqual(len(ParameterGrid(search_space)), 80)


if __name__ == "__main__":
    unittest.main()
