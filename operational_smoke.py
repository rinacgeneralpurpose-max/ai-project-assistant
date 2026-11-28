"""Safe, unauthenticated production acceptance smoke test.

Only GET requests: /health, /api/projects, /api/dashboard,
/api/activities, /api/operations. Never transmits credentials, writes
data or probes private operation IDs. Run against a known trusted HTTPS host.
"""
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROUTES = ("/api/projects", "/api/dashboard", "/api/activities", "/api/operations")


def _get(url, *, opener=urlopen):
    req = Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener(req, timeout=20) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        finally:
            exc.close()


def run_smoke(*, base_url, opener=urlopen):
    parsed = urlsplit(base_url)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("Expected trusted HTTPS service origin without credentials")
    origin = base_url.rstrip("/")
    results = {}
    try:
        status, payload = _get(origin + "/health", opener=opener)
        if (status != 200 or not isinstance(payload, dict)
                or payload.get("status") != "ok"
                or payload.get("service") != "ai-project-assistant"
                or payload.get("writes_enabled") is not False):
            raise RuntimeError("Health or write-safety contract failed")
        results["/health"] = "pass"
        for route in ROUTES:
            status, payload = _get(origin + route, opener=opener)
            # No key: 401 means auth enforced; 503 means API key not configured.
            if status not in (401, 503):
                raise RuntimeError("Unauthenticated access contract failed for " + route)
            if not isinstance(payload, dict) or payload.get("status") not in (
                "unauthorized", "unavailable"
            ):
                raise RuntimeError("Unexpected auth response for " + route)
            results[route] = "protected"
    except (HTTPError, URLError, OSError, ValueError, TypeError) as exc:
        raise RuntimeError("Read-only smoke test unavailable") from exc
    return {"status": "pass", "checks": results, "writes_enabled": False}


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        print(json.dumps(run_smoke(base_url=url), sort_keys=True))
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"status": "fail", "reason": str(exc)}))
        sys.exit(1)
