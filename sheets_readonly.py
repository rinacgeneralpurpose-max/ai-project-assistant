"""Read-only Google Sheets schema verification. No mutation methods are used."""
import os
from google.auth import default
from google.auth.transport.requests import AuthorizedSession

REQUIRED = {
    "Project Master": ["Project ID", "Client", "Project Name", "Location", "Application", "Product", "Current Stage", "Opportunity Status", "Owner", "Latest Update", "Next Action", "Next Due Date", "Order Value INR", "Last Updated"],
    "Activity History": ["Activity ID", "Timestamp", "Project ID", "Stage", "Update Type", "Voice Transcript", "Outcome / Summary", "Next Action", "Owner", "Due Date", "Recorded By"],
    "Voice Inbox": ["Update ID", "Received At", "Project ID (Candidate)", "Client / Project Mention", "Voice Transcript", "Detected Stage", "Extracted Update", "Missing Current-Stage Fields", "Proposed Changes JSON", "Review Status", "Review Notes", "Applied At", "Error / Conflict"],
}
SCOPE = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

def verify_schema():
    spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not spreadsheet_id:
        return {"status": "not_configured", "reason": "GOOGLE_SHEET_ID missing"}
    credentials, _ = default(scopes=SCOPE)
    session = AuthorizedSession(credentials)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    ranges = [f"'{name}'!1:1" for name in REQUIRED]
    response = session.get(url, params=[("ranges", r) for r in ranges], timeout=15)
    response.raise_for_status()
    actual = response.json().get("valueRanges", [])
    checks = {}
    for (name, expected), item in zip(REQUIRED.items(), actual):
        rows = item.get("values", [])
        found = rows[0] if rows else []
        checks[name] = {"valid": found[:len(expected)] == expected, "expected_columns": len(expected), "actual_columns": len(found)}
    return {"status": "verified" if len(checks) == len(REQUIRED) and all(v["valid"] for v in checks.values()) else "schema_mismatch", "tabs": checks}
