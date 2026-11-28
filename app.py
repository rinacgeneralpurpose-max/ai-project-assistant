import os
import hmac
from flask import Flask, jsonify, request
from sheets_readonly import verify_schema
from projects_readonly import get_projects
from dashboard_readonly import dashboard, activity_history
from update_preview import preview_update
from approval_readonly import create_review, validate_approval
from operations_readonly import list_operations, operation_detail

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

@app.post("/api/updates/preview")
def update_preview_api():
    if not os.environ.get("PROJECT_API_KEY"):
        return _api_response({"status": "unavailable"}), 503
    if not _authorized():
        return _api_response({"status": "unauthorized"}), 401
    if not request.is_json or request.content_length is not None and request.content_length > 12000:
        return _api_response({"status": "invalid_request", "reason": "JSON body required (max 12 KB)"}), 400
    try:
        payload, status_code = preview_update(request.get_json(silent=True))
        return _api_response(payload), status_code
    except Exception:
        app.logger.exception("Update preview failed")
        return _api_response({"status": "error", "reason": "Preview unavailable. Check Render logs."}), 500


def _approval_request(handler):
    if not os.environ.get("PROJECT_API_KEY"):
        return _api_response({"status": "unavailable"}), 503
    if not _authorized():
        return _api_response({"status": "unauthorized"}), 401
    if not request.is_json or request.content_length is None or request.content_length > 12000:
        return _api_response({"status": "invalid_request", "reason": "JSON body with Content-Length required (max 12 KB)"}), 400
    try:
        payload, code = handler(request.get_json(silent=True))
        return _api_response(payload), code
    except Exception:
        app.logger.exception("Approval validation failed")
        return _api_response({"status": "error", "reason": "Approval validation unavailable. Check Render logs."}), 500

@app.post("/api/updates/review")
def review_api():
    return _approval_request(create_review)

@app.post("/api/updates/validate-approval")
def validate_approval_api():
    return _approval_request(validate_approval)


def _read_only_db_configured():
    return bool(os.environ.get("READONLY_DATABASE_URL", ""))


@app.get("/api/operations")
def operations_api():
    if not os.environ.get("PROJECT_API_KEY"):
        return _api_response({"status": "unavailable"}), 503
    if not _authorized():
        return _api_response({"status": "unauthorized"}), 401
    if not _read_only_db_configured():
        return _api_response({"status": "unavailable", "reason": "Read-only database not configured"}), 503
    try:
        limit = request.args.get("limit", "50")
        project_id = request.args.get("project_id")
        result = list_operations(
            dsn=os.environ["READONLY_DATABASE_URL"],
            project_id=project_id, limit=limit)
        return _api_response(result)
    except ValueError:
        return _api_response({"status": "invalid_request"}), 400
    except Exception:
        app.logger.exception("Read-only operation listing failed")
        return _api_response({"status": "error", "reason": "Operation status unavailable"}), 500


@app.get("/api/operations/<operation_id>")
def operation_detail_api(operation_id):
    if not os.environ.get("PROJECT_API_KEY"):
        return _api_response({"status": "unavailable"}), 503
    if not _authorized():
        return _api_response({"status": "unauthorized"}), 401
    if not _read_only_db_configured():
        return _api_response({"status": "unavailable", "reason": "Read-only database not configured"}), 503
    try:
        result = operation_detail(
            dsn=os.environ["READONLY_DATABASE_URL"],
            operation_id=operation_id)
        if result is None:
            return _api_response({"status": "not_found"}), 404
        return _api_response(result)
    except ValueError:
        return _api_response({"status": "invalid_request"}), 400
    except Exception:
        app.logger.exception("Read-only operation detail failed")
        return _api_response({"status": "error", "reason": "Operation detail unavailable"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
