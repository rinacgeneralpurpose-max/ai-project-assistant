"""Offline tests for credential-safe live read acceptance."""
import io
import json
import unittest
from urllib.error import HTTPError
from live_readonly_acceptance import verify_live


class Response:
    def __init__(self, payload, status=200, cache="no-store"):
        self.status = status
        self.headers = {"Cache-Control": cache}
        self.data = io.BytesIO(json.dumps(payload).encode())
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, size=-1):
        return self.data.read(size)


class LiveAcceptanceTests(unittest.TestCase):
    def opener(self, req, timeout):
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.get_header("X-api-key"), "private-test-key")
        self.assertEqual(timeout, 30)
        if "/api/projects" in req.full_url:
            return Response({"status": "ok", "total": 1,
                             "projects": [{"Project ID": "synthetic"}]})
        if "/api/dashboard" in req.full_url:
            return Response({"status": "ok", "total_projects": 1,
                             "by_stage": {"Enquiry": 1}})
        if "/api/activities" in req.full_url:
            return Response({"status": "ok", "total": 0, "activities": []})
        return Response({"writes_enabled": False, "operations": []})

    def test_healthy_read_only_contract(self):
        result = verify_live(key="private-test-key", opener=self.opener)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["writes_enabled"])
        self.assertNotIn("synthetic", json.dumps(result))
        self.assertNotIn("private-test-key", json.dumps(result))

    def test_missing_secret_rejected(self):
        with self.assertRaises(ValueError):
            verify_live(key="", opener=self.opener)

    def test_non_https_origin_rejected(self):
        with self.assertRaises(ValueError):
            verify_live(origin="http://example.com", key="secret", opener=self.opener)

    def test_error_fails_closed_without_leaking_response(self):
        def failing(req, timeout):
            raise HTTPError(req.full_url, 500, "private-credential",
                            {"Cache-Control": "no-store"},
                            io.BytesIO(b'{"status":"error","reason":"secret"}'))
        result = verify_live(key="private-test-key", opener=failing)
        self.assertEqual(result["status"], "fail")
        self.assertNotIn("secret", json.dumps(result))

    def test_wrong_dashboard_shape_fails(self):
        def bad_dashboard(req, timeout):
            if "/api/dashboard" in req.full_url:
                return Response({"status": "ok", "total_projects": "invalid",
                                 "by_stage": {}})
            return self.opener(req, timeout)
        self.assertEqual(
            verify_live(key="private-test-key", opener=bad_dashboard)["status"],
            "fail")

    def test_missing_cache_control_fails(self):
        def no_cache(req, timeout):
            if "/api/projects" in req.full_url:
                return Response({"status": "ok", "total": 0, "projects": []},
                                cache="")
            return self.opener(req, timeout)
        self.assertEqual(
            verify_live(key="private-test-key", opener=no_cache)["status"],
            "fail")


if __name__ == "__main__":
    unittest.main()
