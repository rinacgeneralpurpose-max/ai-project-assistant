"""HTTP boundary tests for read-only operational status."""
import os
import unittest
from unittest.mock import patch

from app import app


class OperationApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {
            "PROJECT_API_KEY": "test-secret",
            "READONLY_DATABASE_URL": "postgresql://read-only-example.invalid/db",
        })
        self.env.start()
        self.headers = {"X-API-Key": "test-secret"}

    def tearDown(self):
        self.env.stop()

    def test_unauthorized_operations_rejected(self):
        self.assertEqual(self.client.get("/api/operations").status_code, 401)

    def test_unauthorized_detail_rejected(self):
        self.assertEqual(self.client.get("/api/operations/abc").status_code, 401)

    def test_missing_database_config_fails_closed(self):
        with patch.dict(os.environ, {"READONLY_DATABASE_URL": ""}):
            response = self.client.get("/api/operations", headers=self.headers)
        self.assertEqual(response.status_code, 503)

    @patch("app.list_operations")
    def test_listing_auth_and_no_store(self, mock_list):
        mock_list.return_value = {"operations": [], "count": 0, "writes_enabled": False}
        response = self.client.get("/api/operations?limit=5", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertFalse(response.json["writes_enabled"])
        self.assertEqual(mock_list.call_args.kwargs["limit"], "5")

    @patch("app.list_operations")
    def test_invalid_limit(self, mock_list):
        mock_list.side_effect = ValueError("Invalid limit")
        response = self.client.get("/api/operations?limit=999", headers=self.headers)
        self.assertEqual(response.status_code, 400)

    @patch("app.operation_detail")
    def test_detail_not_found(self, mock_detail):
        mock_detail.return_value = None
        response = self.client.get("/api/operations/00000000-0000-0000-0000-000000000001",
                                   headers=self.headers)
        self.assertEqual(response.status_code, 404)

    @patch("app.operation_detail")
    def test_detail_no_write_capability(self, mock_detail):
        mock_detail.return_value = {
            "operation_id": "id", "state": "reconciliation_required",
            "writes_enabled": False}
        response = self.client.get("/api/operations/00000000-0000-0000-0000-000000000001",
                                   headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["writes_enabled"])

    @patch("app.operation_detail")
    def test_database_failure_is_generic(self, mock_detail):
        mock_detail.side_effect = RuntimeError("secret database password")
        response = self.client.get("/api/operations/00000000-0000-0000-0000-000000000001",
                                   headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
