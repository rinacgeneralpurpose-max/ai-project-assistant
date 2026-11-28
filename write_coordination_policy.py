"""Offline write authorization and coordination policy.

This module never contacts Google Sheets or PostgreSQL. It does not grant
production write capability. Human identity must be established by a trusted
authenticator before constructing ReviewerIdentity.
"""
from dataclasses import dataclass
from enum import Enum


class PolicyDenied(ValueError):
    pass


@dataclass(frozen=True)
class ReviewerIdentity:
    subject: str
    roles: frozenset
    authenticated: bool


class OperationState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    APPLYING = "applying"
    APPLIED = "applied"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    REJECTED = "rejected"


TRANSITIONS = {
    OperationState.PENDING: frozenset({OperationState.APPROVED, OperationState.REJECTED}),
    OperationState.APPROVED: frozenset({OperationState.APPLYING, OperationState.REJECTED}),
    OperationState.APPLYING: frozenset({OperationState.APPLIED, OperationState.RECONCILIATION_REQUIRED}),
    OperationState.RECONCILIATION_REQUIRED: frozenset({OperationState.APPLIED, OperationState.REJECTED}),
    OperationState.APPLIED: frozenset(),
    OperationState.REJECTED: frozenset(),
}


def authorize_reviewer(identity, *, requestor_subject):
    if not isinstance(identity, ReviewerIdentity):
        raise PolicyDenied("Trusted reviewer identity required")
    if not identity.authenticated or not identity.subject.strip():
        raise PolicyDenied("Authenticated reviewer required")
    if "project_update_reviewer" not in identity.roles:
        raise PolicyDenied("Reviewer role required")
    if identity.subject == requestor_subject:
        raise PolicyDenied("Self approval prohibited")
    return True


def transition(current, proposed):
    try:
        current, proposed = OperationState(current), OperationState(proposed)
    except ValueError as exc:
        raise PolicyDenied("Invalid operation state") from exc
    if proposed not in TRANSITIONS[current]:
        raise PolicyDenied("Illegal operation transition")
    return proposed


def deduplication_key(*, project_id, approval_id):
    if not isinstance(project_id, str) or not project_id.strip():
        raise PolicyDenied("Project ID required")
    if not isinstance(approval_id, str) or not approval_id.strip():
        raise PolicyDenied("Approval ID required")
    return (project_id, approval_id)


def classify_sheet_result(*, request_sent, confirmed_success):
    """Ambiguous network outcomes must never be automatically retried."""
    if confirmed_success and not request_sent:
        raise PolicyDenied("Impossible result")
    if confirmed_success:
        return OperationState.APPLIED
    if request_sent:
        return OperationState.RECONCILIATION_REQUIRED
    return OperationState.APPROVED
