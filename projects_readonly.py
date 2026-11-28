"""Read-only, authenticated access to Project Master records."""
import os
from google.auth import default
from google.auth.transport.requests import AuthorizedSession

SCOPE = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
HEADERS = ["Project ID", "Client", "Project Name", "Location", "Application", "Product", "Current Stage", "Opportunity Status", "Owner", "Latest Update", "Next Action", "Next Due Date", "Order Value INR", "Last Updated"]

def get_projects(limit=50, offset=0):
    spreadsheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID missing")
    credentials, _ = default(scopes=SCOPE)
    session = AuthorizedSession(credentials)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/'Project Master'!A:N"
    response = session.get(url, timeout=20)
    response.raise_for_status()
    rows = response.json().get("values", [])
    if not rows or rows[0][:len(HEADERS)] != HEADERS:
        raise ValueError("Project Master headers do not match expected schema")
    records = []
    for row in rows[1:]:
        if not any(str(value).strip() for value in row):
            continue
        records.append(dict(zip(HEADERS, (row + [""] * len(HEADERS))[:len(HEADERS)])))
    return {"status": "ok", "total": len(records), "limit": limit, "offset": offset, "projects": records[offset:offset + limit]}
