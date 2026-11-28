"""Standalone transactional operation audit prototype.

No production migration, Sheets write, Flask endpoint, or gate release.
Caller must use a restricted DB role and a separately migrated schema.
"""
import json
import uuid
from datetime import datetime, timezone


AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS operation_audit_events (
    event_id UUID PRIMARY KEY,
    operation_id UUID NOT NULL REFERENCES sheet_operations(operation_id),
    event_type TEXT NOT NULL CHECK (event_type IN
        ('operation_started','reconciliation_required')),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS operation_audit_events_by_operation
ON operation_audit_events(operation_id, occurred_at);
"""


class AuditedTransitionDenied(Exception):
    pass


class AuditedAtomicCoordinator:
    def __init__(self, connection):
        self.connection = connection

    def _event(self, cursor, *, operation_id, event_type, actor_id):
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("Verified actor ID required")
        cursor.execute(
            """INSERT INTO operation_audit_events
               (event_id,operation_id,event_type,detail_json)
               VALUES (%s,%s,%s,%s::jsonb)""",
            (uuid.uuid4(), operation_id, event_type,
             json.dumps({"actor_id": actor_id}, separators=(",", ":"))),
        )

    def start(self, *, project_id, operation_id, actor_id):
        operation_id = uuid.UUID(str(operation_id))
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("Project ID required")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("Verified actor ID required")
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """INSERT INTO project_write_gates(project_id,operation_id)
                       SELECT project_id,operation_id FROM sheet_operations
                       WHERE project_id=%s AND operation_id=%s AND state='approved'
                       ON CONFLICT DO NOTHING RETURNING operation_id""",
                    (project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AuditedTransitionDenied("Gate busy or operation not approved")
                cur.execute(
                    """UPDATE sheet_operations SET state='applying',updated_at=%s
                       WHERE project_id=%s AND operation_id=%s AND state='approved'
                       RETURNING operation_id""",
                    (datetime.now(timezone.utc), project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AuditedTransitionDenied("Operation state changed")
                self._event(cur, operation_id=operation_id,
                            event_type="operation_started", actor_id=actor_id)
        return "applying"

    def ambiguous(self, *, project_id, operation_id, actor_id):
        operation_id = uuid.UUID(str(operation_id))
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise ValueError("Verified actor ID required")
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """UPDATE sheet_operations
                       SET state='reconciliation_required',updated_at=%s
                       WHERE project_id=%s AND operation_id=%s AND state='applying'
                       RETURNING operation_id""",
                    (datetime.now(timezone.utc), project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AuditedTransitionDenied("Operation not applying")
                cur.execute(
                    """UPDATE project_write_gates SET recovery_required=TRUE
                       WHERE project_id=%s AND operation_id=%s
                       RETURNING operation_id""",
                    (project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AuditedTransitionDenied("Gate missing; rollback required")
                self._event(cur, operation_id=operation_id,
                            event_type="reconciliation_required", actor_id=actor_id)
        return "reconciliation_required"
