"""PostgreSQL-backed operation reservation prototype. Not connected to Sheets.

DDL must be applied by a separate migration role on a disposable test DB.
A reserved operation is NOT permission to write to Google Sheets.
"""
import uuid
from datetime import datetime, timezone

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sheet_operations (
    operation_id UUID PRIMARY KEY,
    project_id TEXT NOT NULL,
    approval_id UUID NOT NULL,
    state TEXT NOT NULL CHECK (state IN
        ('approved','applying','applied','reconciliation_required','rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, approval_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_applying_operation_per_project
ON sheet_operations(project_id) WHERE state='applying';
"""


class CoordinationConflict(Exception):
    pass


class PostgresOperationCoordinator:
    def __init__(self, connection):
        self.connection = connection

    def reserve(self, *, project_id, approval_id):
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("Project ID required")
        approval_id = uuid.UUID(str(approval_id))
        operation_id = uuid.uuid4()
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """INSERT INTO sheet_operations
                       (operation_id,project_id,approval_id,state)
                       VALUES (%s,%s,%s,'approved')
                       ON CONFLICT (project_id,approval_id) DO NOTHING
                       RETURNING operation_id""",
                    (operation_id, project_id, approval_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise CoordinationConflict("Operation already reserved")
        return str(row[0])

    def begin(self, *, operation_id):
        """DB unique partial index prevents concurrent APPLYING for one project."""
        operation_id = uuid.UUID(str(operation_id))
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """UPDATE sheet_operations
                       SET state='applying',updated_at=%s
                       WHERE operation_id=%s AND state='approved'
                       RETURNING operation_id""",
                    (datetime.now(timezone.utc), operation_id),
                )
                if cur.fetchone() is None:
                    raise CoordinationConflict("Operation not approved or already begun")
        return "applying"

    def record_result(self, *, operation_id, confirmed_success):
        """Never automatically retry ambiguous external Sheets outcomes."""
        operation_id = uuid.UUID(str(operation_id))
        state = "applied" if confirmed_success else "reconciliation_required"
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """UPDATE sheet_operations SET state=%s,updated_at=%s
                       WHERE operation_id=%s AND state='applying'
                       RETURNING operation_id""",
                    (state, datetime.now(timezone.utc), operation_id),
                )
                if cur.fetchone() is None:
                    raise CoordinationConflict("Operation not applying")
        return state
