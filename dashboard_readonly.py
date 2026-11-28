"""Read-only Activity History and project dashboard aggregates."""
import os
from collections import Counter
from datetime import date, datetime
from google.auth import default
from google.auth.transport.requests import AuthorizedSession
from projects_readonly import get_projects
from sheets_readonly import REQUIRED, SCOPE

def _read_tab(name):
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID missing")
    credentials, _ = default(scopes=SCOPE)
    response = AuthorizedSession(credentials).get(
        f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/'{name}'!A:Z",
        timeout=20,
    )
    response.raise_for_status()
    rows = response.json().get("values", [])
    headers = REQUIRED[name]
    if not rows or rows[0][:len(headers)] != headers:
        raise ValueError(f"{name} headers do not match expected schema")
    return [
        dict(zip(headers, (row + [""] * len(headers))[:len(headers)]))
        for row in rows[1:] if any(str(value).strip() for value in row)
    ]

def activity_history(project_id=None, limit=50, offset=0):
    records = _read_tab("Activity History")
    if project_id is not None:
        records = [r for r in records if str(r["Project ID"]).strip() == project_id]
    records.reverse()
    return {"status": "ok", "total": len(records), "limit": limit,
            "offset": offset, "activities": records[offset:offset + limit]}

def _parse_date(value):
    value = str(value).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None

def dashboard():
    # Fetch every page rather than silently truncating at the API's default 50.
    records = []
    offset = 0
    while True:
        page = get_projects(limit=100, offset=offset)
        records.extend(page["projects"])
        offset += len(page["projects"])
        if offset >= page["total"] or not page["projects"]:
            break
    today = date.today()
    stages = Counter((p["Current Stage"].strip() or "Unspecified") for p in records)
    statuses = Counter((p["Opportunity Status"].strip() or "Unspecified") for p in records)
    overdue = []
    due_today = []
    upcoming = []
    for p in records:
        due = _parse_date(p["Next Due Date"])
        if due is None or not p["Next Action"].strip():
            continue
        item = {"project_id": p["Project ID"], "client": p["Client"],
                "project_name": p["Project Name"], "next_action": p["Next Action"],
                "next_due_date": p["Next Due Date"], "owner": p["Owner"]}
        if due < today:
            overdue.append(item)
        elif due == today:
            due_today.append(item)
        else:
            upcoming.append(item)
    return {"status": "ok", "total_projects": len(records),
            "by_stage": dict(stages), "by_opportunity_status": dict(statuses),
            "overdue_count": len(overdue), "due_today_count": len(due_today),
            "upcoming_count": len(upcoming), "overdue": overdue,
            "due_today": due_today, "upcoming": upcoming,
            "note": "Due-date lists include projects with a parseable date and nonempty Next Action; no completion inference is made."}
