"""PostgreSQL approval and audit storage (not wired to API or Sheets).

Requires psycopg 3 and an externally provisioned durable PostgreSQL database.
Use a dedicated restricted database role. The service must not enable writes
until human identity, review, sheet serialization and recovery are complete.
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone

DDL = """
CREATE TABLE IF NOT EXISTS approvals (
    approval_id UUID PRIMARY KEY,
    actor_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS approval_audit (
    event_id UUID PRIMARY KEY,
    approval_id UUID NOT NULL REFERENCES approvals(approval_id),
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    metadata_json JSONB NOT NULL
);
"""


class ApprovalRejected(Exception):
    pass


def payload_digest(payload):
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PostgresApprovalStore:
    """Caller owns psycopg connection; methods commit their own transactions."""

    def __init__(self, connection):
        self.conn = connection

    def initialize(self):
        # Schema migration should be performed by a separate privileged role.
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(DDL)

    def create(self, *, actor_id, project_id, payload, expires_at, idempotency_key):
        if not all(isinstance(v, str) and v.strip() for v in (actor_id, project_id, idempotency_key)):
            raise ValueError("Actor, project and idempotency key required")
        if not isinstance(expires_at, datetime) or expires_at.tzinfo is None:
            raise ValueError("Timezone-aware expiry required")
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("Expiry must be in future")
        approval_id = uuid.uuid4()
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO approvals
                       (approval_id, actor_id, project_id, payload_hash, idempotency_key, expires_at)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (approval_id, actor_id, project_id, payload_digest(payload), idempotency_key, expires_at),
                )
        return str(approval_id)

    def consume(self, *, approval_id, actor_id, project_id, payload):
        """Single transaction ensures a successful consume always has an audit event."""
        now = datetime.now(timezone.utc)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """UPDATE approvals SET consumed_at = %s
                       WHERE approval_id = %s AND actor_id = %s AND project_id = %s
                         AND payload_hash = %s AND consumed_at IS NULL AND expires_at > %s
                       RETURNING approval_id""",
                    (now, approval_id, actor_id, project_id, payload_digest(payload), now),
                )
                if cur.fetchone() is None:
                    raise ApprovalRejected("Expired, mismatched or already consumed")
                cur.execute(
                    """INSERT INTO approval_audit
                       (event_id, approval_id, event_type, occurred_at, metadata_json)
                       VALUES (%s, %s, %s, %s, %s::jsonb)""",
                    (uuid.uuid4(), approval_id, "approval_consumed", now,
                     json.dumps({"actor_id": actor_id, "project_id": project_id})),
                )
        return {"status": "consumed", "writes_enabled": False}
