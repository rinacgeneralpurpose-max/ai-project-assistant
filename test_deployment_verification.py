"""Offline deployment verifier tests. No network calls."""
import io
import json
import unittest

from deployment_verification import (
    DeploymentVerificationError, compare_deployed_revision, check_public_health,
)


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *args):
        return json.dumps(self.payload).encode()


class DeploymentVerificationTests(unittest.TestCase):
    def test_live_matching_revision(self):
        sha = "a" * 40
        result = compare_deployed_revision(
            expected_sha=sha, deployed_sha=sha, deploy_status="live")
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["writes_enabled"])

    def test_live_stale_revision(self):
        result = compare_deployed_revision(
            expected_sha="a" * 40, deployed_sha="b" * 40,
            deploy_status="live")
        self.assertEqual(result["status"], "not_current")
        self.assertFalse(result["revision_matches"])

    def test_matching_but_failed_deployment(self):
        result = compare_deployed_revision(
            expected_sha="a" * 40, deployed_sha="a" * 40,
            deploy_status="failed")
        self.assertEqual(result["status"], "not_current")

    def test_partial_sha_rejected(self):
        with self.assertRaises(DeploymentVerificationError):
            compare_deployed_revision(
                expected_sha="abc123", deployed_sha="a" * 40,
                deploy_status="live")

    def test_read_only_health_success(self):
        def opener(req, timeout):
            self.assertEqual(req.get_method(), "GET")
            self.assertTrue(req.full_url.endswith("/health"))
            self.assertEqual(timeout, 10)
            return FakeResponse({
                "status": "ok", "service": "ai-project-assistant",
                "writes_enabled": False,
            })
        self.assertEqual(
            check_public_health(url="https://example.com", opener=opener)["status"],
            "healthy_read_only")

    def test_health_rejects_write_enabled(self):
        def opener(req, timeout):
            return FakeResponse({
                "status": "ok", "service": "ai-project-assistant",
                "writes_enabled": True,
            })
        with self.assertRaises(DeploymentVerificationError):
            check_public_health(url="https://example.com", opener=opener)

    def test_health_rejects_wrong_service(self):
        def opener(req, timeout):
            return FakeResponse({
                "status": "ok", "service": "other", "writes_enabled": False,
            })
        with self.assertRaises(DeploymentVerificationError):
            check_public_health(url="https://example.com", opener=opener)

    def test_http_only_url_rejected(self):
        with self.assertRaises(DeploymentVerificationError):
            check_public_health(url="http://example.com")

    def test_url_credentials_rejected(self):
        with self.assertRaises(DeploymentVerificationError):
            check_public_health(url="https://user:password@example.com")


if __name__ == "__main__":
    unittest.main()
