"""Offline tests of production read-only smoke-test contract."""
import io
import json
import unittest
from urllib.error import HTTPError
from operational_smoke import run_smoke, ROUTES


class Response:
    def __init__(self, status, payload):
        self.status = status
        self.body = io.BytesIO(json.dumps(payload).encode())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        return self.body.read(size)


class OperationalSmokeTests(unittest.TestCase):
    def make_opener(self, *, health=None, route_status=401):
        calls = []
        def opener(req, timeout):
            calls.append((req.full_url, req.get_method()))
            self.assertEqual(timeout, 20)
            if req.full_url.endswith("/health"):
                return Response(200, health or {
                    "status": "ok", "service": "ai-project-assistant",
                    "writes_enabled": False})
            payload = {"status": "unauthorized" if route_status == 401 else "unavailable"}
            raise HTTPError(req.full_url, route_status, "expected", {},
                            io.BytesIO(json.dumps(payload).encode()))
        return opener, calls

    def test_safe_success(self):
        opener, calls = self.make_opener()
        result = run_smoke(base_url="https://example.com", opener=opener)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(len(calls), 1 + len(ROUTES))
        self.assertTrue(all(method == "GET" for _, method in calls))
        self.assertFalse(result["writes_enabled"])

    def test_missing_api_key_configuration_allowed(self):
        opener, _ = self.make_opener(route_status=503)
        self.assertEqual(
            run_smoke(base_url="https://example.com", opener=opener)["status"], "pass")

    def test_write_enabled_rejected(self):
        opener, _ = self.make_opener(health={
            "status": "ok", "service": "ai-project-assistant", "writes_enabled": True})
        with self.assertRaises(RuntimeError):
            run_smoke(base_url="https://example.com", opener=opener)

    def test_unauthenticated_access_is_rejected(self):
        opener, _ = self.make_opener(route_status=200)
        with self.assertRaises(RuntimeError):
            run_smoke(base_url="https://example.com", opener=opener)

    def test_invalid_host_rejected(self):
        for origin in ("http://example.com", "https://u:p@example.com",
                       "https://example.com/path", "https://example.com?token=abc"):
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError):
                    run_smoke(base_url=origin)


if __name__ == "__main__":
    unittest.main()
