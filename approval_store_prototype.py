"""Offline SQLite prototype for one-time approvals and append-only audit events.

NOT connected to Flask endpoints or Google Sheets. Local SQLite files on an
ephemeral Render filesystem are NOT acceptable as production persistence.
Use durable transactional Postgres before deploying any write capability.
"""
import hashlib
import json
import sqlite3
import time
import uuid


class ApprovalStoreError(Exception):
    pass


class ApprovalStore:
    def __init__(self, connection):
        self.db = connection
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id TEXT PRIMARY KEY,
            actor_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            consumed_at INTEGER,
            idempotency_key TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            approval_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            recorded_at INTEGER NOT NULL,
            detail_json TEXT NOT NULL,
            FOREIGN KEY (approval_id) REFERENCES approvals(approval_id)
        );
        """)

    @staticmethod
    def payload_hash(payload):
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def create(self, *, actor_id, project_id, payload, expires_at, idempotency_key):
        if not all(isinstance(x, str) and x.strip() for x in (actor_id, project_id, idempotency_key)):
            raise ApprovalStoreError("Actor, project and idempotency key are required")
        if not isinstance(expires_at, int) or expires_at <= int(time.time()):
            raise ApprovalStoreError("Expiry must be in the future")
        approval_id = str(uuid.uuid4())
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, NULL, ?)",
                    (approval_id, actor_id, project_id, self.payload_hash(payload), expires_at, idempotency_key),
                )
        except sqlite3.IntegrityError as exc:
            raise ApprovalStoreError("Duplicate idempotency key") from exc
        return approval_id

    def consume(self, *, approval_id, actor_id, project_id, payload, now=None):
        now = int(time.time()) if now is None else now
        with self.db:
            cursor = self.db.execute(
                """UPDATE approvals SET consumed_at = ?
                   WHERE approval_id = ? AND actor_id = ? AND project_id = ?
                     AND payload_hash = ? AND consumed_at IS NULL AND expires_at > ?""",
                (now, approval_id, actor_id, project_id, self.payload_hash(payload), now),
            )
            if cursor.rowcount != 1:
                raise ApprovalStoreError("Approval invalid, expired, mismatched or already consumed")
            self.db.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), approval_id, "approval_consumed", now,
                 json.dumps({"actor_id": actor_id, "project_id": project_id}, sort_keys=True)),
            )
        return {"status": "consumed", "writes_enabled": False}

    def audit(self, approval_id):
        return self.db.execute(
            "SELECT event_type, recorded_at, detail_json FROM audit_events WHERE approval_id = ? ORDER BY recorded_at",
            (approval_id,),
        ).fetchall()
