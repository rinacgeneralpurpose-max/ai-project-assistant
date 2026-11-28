"""Operator-run, credential-safe live read-only acceptance.

Use a private environment with PROJECT_API_KEY set. No data values,
API keys, database URLs or response bodies are printed.
"""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROUTES = (
    ("/api/projects?limit=1", "projects", ("status", "total", "projects")),
    ("/api/dashboard", "dashboard", ("status", "total_projects", "by_stage")),
    ("/api/activities?limit=1", "activities", ("status", "total", "activities")),
)
ORIGIN = "https://ai-project-assistant-0u1f.onrender.com"


def request_json(origin, path, key, *, opener=urlopen):
    req = Request(origin + path, method="GET",
                  headers={"X-API-Key": key, "Accept": "application/json"})
    try:
        with opener(req, timeout=30) as response:
            status = response.status
            cache = response.headers.get("Cache-Control", "")
            body = json.load(response)
    except HTTPError as exc:
        status = exc.code
        cache = exc.headers.get("Cache-Control", "")
        try:
            body = json.load(exc)
        finally:
            exc.close()
    return status, cache, body


def verify_live(*, origin=ORIGIN, key=None, opener=urlopen):
    parts = urlsplit(origin)
    if (parts.scheme != "https" or not parts.hostname or parts.username
            or parts.password or parts.query or parts.fragment
            or parts.path not in ("", "/")):
        raise ValueError("Trusted HTTPS origin required")
    if not key:
        raise ValueError("PROJECT_API_KEY must be supplied privately")
    result = {}
    for path, label, required in ROUTES:
        try:
            status, cache, body = request_json(origin.rstrip("/"), path, key,
                                               opener=opener)
            valid = (status == 200 and "no-store" in cache.lower()
                     and isinstance(body, dict)
                     and body.get("status") == "ok"
                     and all(field in body for field in required))
            if label in ("projects", "activities") and valid:
                valid = (isinstance(body[label], list)
                         and isinstance(body["total"], int)
                         and len(body[label]) <= 1)
            if label == "dashboard" and valid:
                valid = (isinstance(body["total_projects"], int)
                         and isinstance(body["by_stage"], dict))
            result[label] = "pass" if valid else "fail"
        except (HTTPError, URLError, OSError, ValueError, TypeError):
            result[label] = "fail"
    # Operations are optional until a dedicated SELECT-only PG role is configured.
    try:
        status, cache, body = request_json(origin.rstrip("/"),
                                          "/api/operations?limit=1", key,
                                          opener=opener)
        if status == 503 and isinstance(body, dict) and body.get("status") == "unavailable":
            result["operations"] = "not_configured"
        elif (status == 200 and "no-store" in cache.lower()
              and isinstance(body, dict) and body.get("writes_enabled") is False
              and isinstance(body.get("operations"), list)):
            result["operations"] = "pass"
        else:
            result["operations"] = "fail"
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        result["operations"] = "fail"
    return {"status": "pass" if all(result[k] == "pass" for k in
            ("projects", "dashboard", "activities")) and result["operations"] != "fail"
            else "fail", "checks": result, "writes_enabled": False}


if __name__ == "__main__":
    report = verify_live(key=os.environ.get("PROJECT_API_KEY"))
    print(json.dumps(report, sort_keys=True))
    sys.exit(0 if report["status"] == "pass" else 1)
