"""Atomic PostgreSQL gate + operation state transition prototype.

No Sheets calls, Flask route, migration execution, or gate release.
Requires pre-created sheet_operations and project_write_gates tables.
"""
import uuid
from datetime import datetime, timezone


class AtomicStartDenied(Exception):
    pass


class AtomicProjectCoordinator:
    def __init__(self, connection):
        self.connection = connection

    def start(self, *, project_id, operation_id):
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("Project ID required")
        operation_id = uuid.UUID(str(operation_id))
        # A single DB transaction ensures the gate cannot exist without an
        # APPLYING operation, or vice versa, after commit.
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """INSERT INTO project_write_gates(project_id, operation_id)
                       SELECT project_id, operation_id FROM sheet_operations
                       WHERE project_id=%s AND operation_id=%s AND state='approved'
                       ON CONFLICT DO NOTHING RETURNING operation_id""",
                    (project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AtomicStartDenied("Project busy or operation not approved")
                cur.execute(
                    """UPDATE sheet_operations SET state='applying',updated_at=%s
                       WHERE project_id=%s AND operation_id=%s AND state='approved'
                       RETURNING operation_id""",
                    (datetime.now(timezone.utc), project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AtomicStartDenied("Operation state changed")
        return "applying"

    def ambiguous(self, *, project_id, operation_id):
        operation_id = uuid.UUID(str(operation_id))
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
                    raise AtomicStartDenied("Operation not applying")
                cur.execute(
                    """UPDATE project_write_gates SET recovery_required=TRUE
                       WHERE project_id=%s AND operation_id=%s
                       RETURNING operation_id""",
                    (project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise AtomicStartDenied("Missing gate; transaction rolled back")
        return "reconciliation_required"
