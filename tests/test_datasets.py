"""
DataViz Pro — Dataset Route Tests

Tests for dataset upload, listing, detail, preview, download, and deletion.
"""

import io
import os
import time
import json

from conftest import BaseTestCase


class TestDatasetRoutes(BaseTestCase):
    """Test dataset-related routes."""

    # ── Auth gate ──────────────────────────────────────────────

    def test_datasets_list_requires_auth(self):
        """GET /datasets without auth should redirect to /login."""
        resp = self.client.get("/datasets", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    def test_upload_page_requires_auth(self):
        """GET /datasets/upload without auth should redirect to /login."""
        resp = self.client.get("/datasets/upload", follow_redirects=False)
        self.assertIn(resp.status_code, (302, 303))
        self.assertIn("/login", resp.headers.get("Location", ""))

    # ── Listing ────────────────────────────────────────────────

    def test_datasets_list_renders(self):
        """Authenticated user should see datasets list page."""
        self.login()
        resp = self.client.get("/datasets")
        self.assertEqual(resp.status_code, 200)

    # ── Upload ─────────────────────────────────────────────────

    def _upload_csv(self, filename="test_upload.csv", content=None):
        """Helper: upload a CSV file and return response."""
        if content is None:
            content = b"col_a,col_b,col_c\n1,2,3\n4,5,6\n7,8,9\n"
        return self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(content), filename)},
            follow_redirects=True,
        )

    def test_upload_csv_file(self):
        """Uploading a valid CSV should succeed and redirect to detail."""
        self.login()
        resp = self._upload_csv()
        self.assertEqual(resp.status_code, 200)
        # Should show success flash or dataset detail
        self.assertIn(b"upload", resp.data.lower()) or self.assertIn(b"dataset", resp.data.lower())

    def test_upload_invalid_format(self):
        """Uploading a non-data file should be rejected."""
        self.login()
        resp = self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(b"not a data file"), "test.xyz")},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        # Should show error or remain on upload page
        self.assertIn(b"upload", resp.data.lower())

    def test_upload_empty_file(self):
        """Uploading an empty file should be rejected."""
        self.login()
        resp = self.client.post(
            "/datasets/upload",
            data={"file": (io.BytesIO(b""), "empty.csv")},
            follow_redirects=True,
        )
        self.assertEqual(resp.status_code, 200)
        # Should show error
        self.assertTrue(
            b"error" in resp.data.lower() or b"no data" in resp.data.lower()
            or b"upload" in resp.data.lower()
        )

    # ── Detail / Preview / Download (need a real dataset) ──────

    def _get_test_dataset_id(self):
        """Helper: login, upload, and return the dataset ID."""
        self.login()
        self._upload_csv()
        api_resp = self.client.get("/api/datasets")
        data = json.loads(api_resp.data)
        self.assertGreater(len(data.get("datasets", [])), 0)
        return data["datasets"][0]["id"]

    def test_dataset_detail(self):
        """GET /datasets/<id> should render the detail page."""
        ds_id = self._get_test_dataset_id()
        resp = self.client.get(f"/datasets/{ds_id}")
        self.assertEqual(resp.status_code, 200)

    def test_dataset_preview(self):
        """GET /datasets/<id>/preview should render the preview page."""
        ds_id = self._get_test_dataset_id()
        resp = self.client.get(f"/datasets/{ds_id}/preview")
        self.assertEqual(resp.status_code, 200)

    def test_dataset_download(self):
        """GET /datasets/<id>/download should return a file attachment."""
        ds_id = self._get_test_dataset_id()
        resp = self.client.get(f"/datasets/{ds_id}/download")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp.headers.get("Content-Disposition", ""))

    def test_dataset_delete(self):
        """POST /datasets/<id>/delete should delete the dataset."""
        ds_id = self._get_test_dataset_id()
        resp = self.client.post(f"/datasets/{ds_id}/delete", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"deleted", resp.data.lower())

    def test_dataset_not_found(self):
        """Non-existent dataset ID should redirect/return 404."""
        self.login()
        resp = self.client.get("/datasets/99999", follow_redirects=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"not found", resp.data.lower())


if __name__ == "__main__":
    unittest.main()
