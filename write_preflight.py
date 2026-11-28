"""Offline-only preflight for proposed Google Sheets writes.

This module does not import Google APIs or perform network, storage, or sheet writes.
An authenticated approval and transactional write coordinator must be implemented
separately before any production mutation is possible.
"""
import re
from dataclasses import dataclass
from typing import Mapping

PROJECT_ID_FIELD = "Project ID"
FORBIDDEN_PREFIXES = ("=", "+", "-", "@")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class PreflightError(ValueError):
    pass


@dataclass(frozen=True)
class ProposedChange:
    project_id: str
    field: str
    expected: str
    proposed: str


def validate_change(change: ProposedChange, *, allowed_fields: frozenset[str]) -> None:
    if not isinstance(change.project_id, str) or not SAFE_ID.fullmatch(change.project_id):
        raise PreflightError("Invalid project ID")
    if change.field not in allowed_fields or change.field == PROJECT_ID_FIELD:
        raise PreflightError("Field not writable")
    if not isinstance(change.expected, str) or not isinstance(change.proposed, str):
        raise PreflightError("Values must be strings")
    if not change.proposed.strip() or len(change.proposed) > 5000:
        raise PreflightError("Proposed value must be nonempty and at most 5000 characters")
    if change.proposed.lstrip().startswith(FORBIDDEN_PREFIXES):
        raise PreflightError("Potential spreadsheet formula rejected")
    if any(ord(c) < 32 and c not in "\t\n" for c in change.proposed):
        raise PreflightError("Control characters rejected")


def preflight(
    change: ProposedChange,
    *,
    rows: list[Mapping[str, str]],
    allowed_fields: frozenset[str],
) -> dict:
    """Return a dry-run plan; never modify rows or a spreadsheet."""
    validate_change(change, allowed_fields=allowed_fields)
    matches = [(i, row) for i, row in enumerate(rows) if row.get(PROJECT_ID_FIELD) == change.project_id]
    if len(matches) != 1:
        raise PreflightError("Project ID must match exactly one row")
    index, row = matches[0]
    if change.field not in row:
        raise PreflightError("Field absent from current schema")
    if row[change.field] != change.expected:
        raise PreflightError("Stale expected value; refresh preview")
    if change.proposed == change.expected:
        raise PreflightError("No change requested")
    return {
        "status": "dry_run_only",
        "project_id": change.project_id,
        "row_index_zero_based": index,
        "field": change.field,
        "expected": change.expected,
        "proposed": change.proposed,
        "writes_enabled": False,
    }
