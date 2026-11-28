"""Fail-closed PostgreSQL project gate prototype; no Sheets API calls.

A project gate remains held after ambiguous results and worker crashes.
Only a separate verified recovery workflow may release it. This module
deliberately provides no release method.
"""
import uuid

GATE_DDL = """
CREATE TABLE IF NOT EXISTS project_write_gates (
    project_id TEXT PRIMARY KEY,
    operation_id UUID NOT NULL UNIQUE,
    acquired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recovery_required BOOLEAN NOT NULL DEFAULT FALSE
);
"""


class ProjectGateBusy(Exception):
    pass


class PostgresProjectGate:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self, *, project_id, operation_id):
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("Project ID required")
        operation_id = uuid.UUID(str(operation_id))
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """INSERT INTO project_write_gates(project_id,operation_id)
                       VALUES (%s,%s)
                       ON CONFLICT DO NOTHING
                       RETURNING operation_id""",
                    (project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise ProjectGateBusy("Project is locked pending completion or recovery")
        return "held"

    def mark_recovery_required(self, *, project_id, operation_id):
        """A failed/unknown Sheets outcome cannot release the project gate."""
        operation_id = uuid.UUID(str(operation_id))
        with self.connection.transaction():
            with self.connection.cursor() as cur:
                cur.execute(
                    """UPDATE project_write_gates SET recovery_required=TRUE
                       WHERE project_id=%s AND operation_id=%s
                       RETURNING operation_id""",
                    (project_id, operation_id),
                )
                if cur.fetchone() is None:
                    raise ProjectGateBusy("Gate not owned by operation")
        return "recovery_required"

    def status(self, *, project_id):
        with self.connection.cursor() as cur:
            cur.execute(
                """SELECT operation_id,recovery_required
                   FROM project_write_gates WHERE project_id=%s""",
                (project_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"state": "unlocked", "writes_enabled": False}
        return {
            "state": "recovery_required" if row[1] else "held",
            "operation_id": str(row[0]),
            "writes_enabled": False,
        }
