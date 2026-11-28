"""Phase 4: deterministic, read-only update preview. No model inference or writes."""
from projects_readonly import get_projects

ALLOWED = {"Current Stage", "Opportunity Status", "Latest Update", "Next Action", "Next Due Date"}
MAX_TEXT = 4000

def preview_update(data):
    if not isinstance(data, dict):
        return {"status": "invalid_request", "reason": "JSON object required"}, 400
    transcript = data.get("transcript", "")
    project_id = data.get("project_id", "")
    changes = data.get("changes", {})
    if not isinstance(transcript, str) or len(transcript) > MAX_TEXT or not transcript.strip():
        return {"status": "invalid_request", "reason": "Nonempty transcript up to 4000 characters required"}, 400
    if not isinstance(project_id, str) or not project_id.strip() or len(project_id) > 100:
        return {"status": "invalid_request", "reason": "Explicit project_id required"}, 400
    if not isinstance(changes, dict) or not changes or set(changes) - ALLOWED:
        return {"status": "invalid_request", "reason": "Nonempty changes with allowed fields required"}, 400
    if any(not isinstance(v, str) or len(v) > 1000 for v in changes.values()):
        return {"status": "invalid_request", "reason": "Change values must be strings up to 1000 characters"}, 400
    matches = []
    offset = 0
    while True:
        page = get_projects(limit=100, offset=offset)
        matches.extend(p for p in page["projects"] if str(p.get("Project ID", "")).strip() == project_id.strip())
        offset += len(page["projects"])
        if offset >= page["total"] or not page["projects"]:
            break
    if len(matches) != 1:
        return {"status": "conflict", "reason": "Project ID not found or not unique; no changes applied"}, 409
    project = matches[0]
    return {"status": "review_required", "project_id": project_id.strip(),
            "client": project.get("Client", ""), "project_name": project.get("Project Name", ""),
            "proposed_changes": {k: {"current": project.get(k, ""), "proposed": v} for k, v in changes.items()},
            "transcript": transcript, "writes_enabled": False,
            "note": "Preview only. No approval, persistence, or Google Sheets mutation is implemented."}, 200
