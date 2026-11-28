"""Isolated authenticated recovery review workflow. NO gate release or Sheets calls.

The operation requester link MUST be populated by a future authenticated
request creation path and protected from alteration via DB privileges.
"""
import uuid

from recovery_authentication import verify_recovery_reviewer
from recovery_review_store import RecoveryReviewStore, RecoveryReviewDenied


REQUESTER_LINK_DDL = """
CREATE TABLE IF NOT EXISTS operation_requesters (
    operation_id UUID PRIMARY KEY REFERENCES sheet_operations(operation_id),
    requestor_subject TEXT NOT NULL CHECK (length(btrim(requestor_subject)) > 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class AuthenticatedRecoveryWorkflow:
    def __init__(self, connection, *, audience, allowed_reviewer_subjects, verifier=None):
        self.connection = connection
        self.audience = audience
        self.allowed = allowed_reviewer_subjects
        self.verifier = verifier

    def submit(self, *, token, project_id, operation_id, evidence, decision):
        reviewer = verify_recovery_reviewer(
            token=token, audience=self.audience,
            allowed_subjects=self.allowed, verifier=self.verifier
        )
        operation_id = uuid.UUID(str(operation_id))
        if not isinstance(project_id, str) or not project_id.strip():
            raise RecoveryReviewDenied("Project ID required")
        # Read stored requester from the DB; NEVER accept it from request body.
        # The review insert shares the same transaction as the lookup.
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """SELECT r.requestor_subject
                       FROM operation_requesters r JOIN sheet_operations o
                         ON o.operation_id=r.operation_id
                       WHERE r.operation_id=%s AND o.project_id=%s
                       FOR SHARE OF r""",
                    (operation_id, project_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise RecoveryReviewDenied("Trusted operation requester is missing")
            result = RecoveryReviewStore(self.connection).record(
                operation_id=operation_id,
                project_id=project_id,
                reviewer_id=reviewer.subject,
                requestor_id=row[0],
                evidence=evidence,
                decision=decision,
            )
        return result
