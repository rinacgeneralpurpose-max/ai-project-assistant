"""Authenticated read-only API contract tests using synthetic records.

Never contacts Google Sheets or PostgreSQL. Covers authorization,
pagination, response masking and cross-endpoint data shape.
"""
import os
import unittest
from unittest.mock import patch
from app import app


class AuthenticatedReadOnlyAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.environment = patch.dict(os.environ, {
            "PROJECT_API_KEY": "acceptance-test-key",
            "READONLY_DATABASE_URL": "postgresql://example.invalid/read_only",
        })
        self.environment.start()
        self.headers = {"X-API-Key": "acceptance-test-key"}

    def tearDown(self):
        self.environment.stop()

    def test_unauthorized_data_routes(self):
        for path in ("/api/projects", "/api/dashboard", "/api/activities",
                     "/api/operations"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
                self.assertEqual(
                    self.client.get(path, headers={"X-API-Key": "wrong"}).status_code,
                    401)

    def test_missing_api_key_fails_closed(self):
        with patch.dict(os.environ, {"PROJECT_API_KEY": ""}):
            for path in ("/api/projects", "/api/dashboard", "/api/activities",
                         "/api/operations"):
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path, headers=self.headers).status_code,
                                     503)

    @patch("app.get_projects")
    def test_projects_authenticated_data_and_pagination(self, read):
        read.return_value = {
            "status": "ok", "total": 1, "limit": 1, "offset": 0,
            "projects": [{"Project ID": "P-001", "Client": "Synthetic Client"}],
        }
        response = self.client.get("/api/projects?limit=1&offset=0",
                                   headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["projects"][0]["Project ID"], "P-001")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        read.assert_called_once_with(limit=1, offset=0)

    @patch("app.dashboard")
    def test_dashboard_authenticated_aggregates(self, read):
        read.return_value = {
            "status": "ok", "total_projects": 1, "overdue_count": 0,
            "by_stage": {"Enquiry": 1},
        }
        response = self.client.get("/api/dashboard", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["by_stage"]["Enquiry"], 1)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    @patch("app.activity_history")
    def test_activities_project_filter_and_pagination(self, read):
        read.return_value = {
            "status": "ok", "total": 1, "limit": 5, "offset": 0,
            "activities": [{"Project ID": "P-001"}],
        }
        response = self.client.get(
            "/api/activities?project_id=P-001&limit=5&offset=0",
            headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["activities"][0]["Project ID"], "P-001")
        read.assert_called_once_with(project_id="P-001", limit=5, offset=0)

    @patch("app.list_operations")
    def test_operations_authenticated_and_no_writes(self, read):
        read.return_value = {
            "operations": [{"operation_id": "synthetic", "state": "approved"}],
            "count": 1, "writes_enabled": False,
        }
        response = self.client.get("/api/operations?project_id=P-001&limit=5",
                                   headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["writes_enabled"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(read.call_args.kwargs["project_id"], "P-001")

    @patch("app.list_operations")
    def test_operations_db_failure_does_not_expose_secret(self, read):
        read.side_effect = RuntimeError("private-db-password")
        response = self.client.get("/api/operations", headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private-db-password", response.get_data(as_text=True))

    @patch("app.get_projects")
    def test_project_read_failure_does_not_expose_secret(self, read):
        read.side_effect = RuntimeError("google-service-credential")
        response = self.client.get("/api/projects", headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("google-service-credential", response.get_data(as_text=True))

    def test_invalid_pagination_rejected(self):
        for route in ("/api/projects", "/api/activities"):
            for query in ("limit=0", "limit=101", "offset=-1", "limit=abc"):
                with self.subTest(route=route, query=query):
                    self.assertEqual(self.client.get(
                        route + "?" + query, headers=self.headers).status_code, 400)

    def test_write_methods_not_exposed_on_data_routes(self):
        for path in ("/api/projects", "/api/dashboard", "/api/activities",
                     "/api/operations"):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(
                    path, headers=self.headers, json={"state": "completed"}).status_code,
                    405)


if __name__ == "__main__":
    unittest.main()
