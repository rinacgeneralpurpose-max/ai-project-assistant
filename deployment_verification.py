"""Read-only deployment verification helpers.

A healthy HTTP response is not proof that the deployed commit is current.
Commit equality must be checked against Render's deployment metadata.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class DeploymentVerificationError(Exception):
    pass


def compare_deployed_revision(*, expected_sha, deployed_sha, deploy_status):
    if not all(isinstance(x, str) and x.strip()
               for x in (expected_sha, deployed_sha, deploy_status)):
        raise DeploymentVerificationError("Commit and deployment status required")
    expected = expected_sha.strip().lower()
    actual = deployed_sha.strip().lower()
    if len(expected) != 40 or len(actual) != 40 or any(
        char not in "0123456789abcdef" for char in expected + actual
    ):
        raise DeploymentVerificationError("Full 40-character commit SHAs required")
    return {
        "status": "verified" if deploy_status == "live" and expected == actual
                  else "not_current",
        "revision_matches": expected == actual,
        "deployment_live": deploy_status == "live",
        "writes_enabled": False,
    }


def check_public_health(*, url, opener=urlopen):
    """GET only. Never send API keys or call mutation endpoints."""
    if not isinstance(url, str) or not url.startswith("https://"):
        raise DeploymentVerificationError("HTTPS service URL required")
    if "?" in url or "#" in url or "@" in url:
        raise DeploymentVerificationError("URL must not contain query, fragment or userinfo")
    endpoint = url.rstrip("/") + "/health"
    request = Request(endpoint, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener(request, timeout=10) as response:
            if response.status != 200:
                raise DeploymentVerificationError("Health endpoint not healthy")
            payload = json.load(response)
    except (HTTPError, URLError, OSError, ValueError, TypeError) as exc:
        raise DeploymentVerificationError("Health endpoint unavailable") from exc
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        raise DeploymentVerificationError("Unexpected health response")
    if payload.get("service") != "ai-project-assistant":
        raise DeploymentVerificationError("Wrong service")
    if payload.get("writes_enabled") is not False:
        raise DeploymentVerificationError("Write safety flag is not false")
    return {"status": "healthy_read_only", "writes_enabled": False}
