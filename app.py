import os
import hmac
from flask import Flask, jsonify, request
from sheets_readonly import verify_schema
from projects_readonly import get_projects
from dashboard_readonly import dashboard, activity_history

app = Flask(__name__)

@app.get("/health")
def health():
    return jsonify(status="ok", service="ai-project-assistant", writes_enabled=False)

@app.get("/")
def index():
    return jsonify(service="ai-project-assistant", mode="read-only-verification", writes_enabled=False)

@app.get("/verify-sheets")
def verify_sheets():
    try:
        return jsonify(verify_schema())
    except Exception:
        app.logger.exception("Google Sheets verification failed")
        return jsonify(status="error", reason="Verification failed. Check Render logs."), 500

@app.get("/api/projects")
def projects():
    secret = os.environ.get("PROJECT_API_KEY", "")
    supplied = request.headers.get("X-API-Key", "")
    if not secret:
        return jsonify(status="unavailable", reason="PROJECT_API_KEY not configured"), 503
    if not supplied or not hmac.compare_digest(secret, supplied):
        return jsonify(status="unauthorized"), 401
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return jsonify(status="invalid_request", reason="limit and offset must be integers"), 400
    if not (1 <= limit <= 100) or offset < 0:
        return jsonify(status="invalid_request", reason="limit must be 1-100 and offset >= 0"), 400
    try:
        result = get_projects(limit=limit, offset=offset)
        response = jsonify(result)
        response.headers["Cache-Control"] = "no-store"
        return response
    except Exception:
        app.logger.exception("Project data read failed")
        return jsonify(status="error", reason="Unable to read projects. Check Render logs."), 500


def _authorized():
    secret = os.environ.get("PROJECT_API_KEY", "")
    supplied = request.headers.get("X-API-Key", "")
    return bool(secret and supplied and hmac.compare_digest(secret, supplied))

def _api_response(payload):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/api/dashboard")
def dashboard_api():
    if not os.environ.get("PROJECT_API_KEY"):
        return _api_response({"status": "unavailable"}), 503
    if not _authorized():
        return _api_response({"status": "unauthorized"}), 401
    try:
        return _api_response(dashboard())
    except Exception:
        app.logger.exception("Dashboard read failed")
        return _api_response({"status": "error", "reason": "Dashboard unavailable. Check Render logs."}), 500

@app.get("/api/activities")
def activities_api():
    if not os.environ.get("PROJECT_API_KEY"):
        return _api_response({"status": "unavailable"}), 503
    if not _authorized():
        return _api_response({"status": "unauthorized"}), 401
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return _api_response({"status": "invalid_request", "reason": "limit and offset must be integers"}), 400
    if not (1 <= limit <= 100) or offset < 0:
        return _api_response({"status": "invalid_request", "reason": "limit must be 1-100 and offset >= 0"}), 400
    try:
        return _api_response(activity_history(
            project_id=request.args.get("project_id"), limit=limit, offset=offset))
    except Exception:
        app.logger.exception("Activity History read failed")
        return _api_response({"status": "error", "reason": "Activity History unavailable. Check Render logs."}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
