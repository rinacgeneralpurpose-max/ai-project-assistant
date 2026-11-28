"""Fail-closed recovery review records; intentionally NO gate release.

A human reconciliation decision alone cannot prove that a previously sent
Google Sheets request has stopped. Therefore this module cannot unlock a
project or mark an operation applied.
"""
import json
import uuid
from datetime import datetime, timezone


RECOVERY_DDL = """
CREATE TABLE IF NOT EXISTS recovery_reviews (
    review_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL UNIQUE REFERENCES sheet_operations(operation_id),
    project_id TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    evidence_json JSONB NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('hold','escalate')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class RecoveryReviewDenied(Exception):
    pass


class RecoveryReviewStore:
    def __init__(self, connection):
        self.connection = connection

    def record(self, *, operation_id, project_id, reviewer_id, requestor_id,
               evidence, decision):
        operation_id = uuid.UUID(str(operation_id))
        if not all(isinstance(x, str) and x.strip()
                   for x in (project_id, reviewer_id, requestor_id)):
            raise RecoveryReviewDenied("Verified reviewer, requester and project required")
        if reviewer_id == requestor_id:
            raise RecoveryReviewDenied("Self review denied")
        if decision not in ("hold", "escalate"):
            raise RecoveryReviewDenied("Unsafe recovery decision")
        if not isinstance(evidence, dict) or not evidence.get("sheet_observation"):
            raise RecoveryReviewDenied("Documented sheet observation required")
        review_id = uuid.uuid4()
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """SELECT o.state,g.recovery_required
                       FROM sheet_operations o JOIN project_write_gates g
                       ON g.operation_id=o.operation_id AND g.project_id=o.project_id
                       WHERE o.operation_id=%s AND o.project_id=%s
                       FOR UPDATE OF o,g""",
                    (operation_id, project_id),
                )
                row = cur.fetchone()
                if row != ("reconciliation_required", True):
                    raise RecoveryReviewDenied("Operation not locked for reconciliation")
                cur.execute(
                    """INSERT INTO recovery_reviews
                       (review_id,operation_id,project_id,reviewer_id,evidence_json,decision)
                       VALUES (%s,%s,%s,%s,%s::jsonb,%s)""",
                    (review_id, operation_id, project_id, reviewer_id,
                     json.dumps(evidence, sort_keys=True, allow_nan=False), decision),
                )
        return {"review_id": str(review_id), "decision": decision,
                "gate_released": False, "writes_enabled": False}
