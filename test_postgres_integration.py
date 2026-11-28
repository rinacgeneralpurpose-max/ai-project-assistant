"""Opt-in real PostgreSQL tests. Never point TEST_DATABASE_URL at production.

Requires RUN_POSTGRES_INTEGRATION_TESTS=1 and TEST_DATABASE_URL.
Creates isolated temporary tables on a dedicated disposable test database.
"""
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from approval_store_postgres import ApprovalRejected, PostgresApprovalStore

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
URL = os.environ.get("TEST_DATABASE_URL")
if ENABLED and URL:
    import psycopg


@unittest.skipUnless(ENABLED and URL, "Set RUN_POSTGRES_INTEGRATION_TESTS=1 and TEST_DATABASE_URL for disposable DB")
class PostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_approval_" + uuid4().hex
        cls.admin = psycopg.connect(URL, autocommit=True)
        with cls.admin.cursor() as cur:
            cur.execute("CREATE SCHEMA " + cls.schema)
            cur.execute("SET search_path TO " + cls.schema)
        cls.connection = psycopg.connect(URL, options="-c search_path=" + cls.schema)
        PostgresApprovalStore(cls.connection).initialize()

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()
        try:
            with cls.admin.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS " + cls.schema + " CASCADE")
        finally:
            cls.admin.close()

    def setUp(self):
        self.store = PostgresApprovalStore(self.connection)
        self.payload = {"field": "Next Action", "value": "Contact client"}
        self.actor = "integration-reviewer"
        self.project = "project-123"
        self.approval = self.store.create(
            actor_id=self.actor, project_id=self.project, payload=self.payload,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            idempotency_key=uuid4().hex,
        )

    def test_consumption_once_and_audit(self):
        self.store.consume(approval_id=self.approval, actor_id=self.actor,
                           project_id=self.project, payload=self.payload)
        with self.assertRaises(ApprovalRejected):
            self.store.consume(approval_id=self.approval, actor_id=self.actor,
                               project_id=self.project, payload=self.payload)
        with self.connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM approval_audit WHERE approval_id=%s", (self.approval,))
            self.assertEqual(cur.fetchone()[0], 1)

    def test_tampered_payload_rejected(self):
        with self.assertRaises(ApprovalRejected):
            self.store.consume(approval_id=self.approval, actor_id=self.actor,
                               project_id=self.project, payload={"field": "Other"})
        with self.connection.cursor() as cur:
            cur.execute("SELECT consumed_at FROM approvals WHERE approval_id=%s", (self.approval,))
            self.assertIsNone(cur.fetchone()[0])

    def test_rollback_when_audit_fails(self):
        with self.connection.cursor() as cur:
            cur.execute("SAVEPOINT unused") if False else None
            cur.execute("""CREATE OR REPLACE FUNCTION reject_audit() RETURNS trigger
                           LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit unavailable'; END; $$""")
            cur.execute("""CREATE TRIGGER reject_audit_insert BEFORE INSERT ON approval_audit
                           FOR EACH ROW EXECUTE FUNCTION reject_audit()""")
        self.connection.commit()
        try:
            with self.assertRaises(Exception):
                self.store.consume(approval_id=self.approval, actor_id=self.actor,
                                   project_id=self.project, payload=self.payload)
            with self.connection.cursor() as cur:
                cur.execute("SELECT consumed_at FROM approvals WHERE approval_id=%s", (self.approval,))
                self.assertIsNone(cur.fetchone()[0])
        finally:
            with self.connection.cursor() as cur:
                cur.execute("DROP TRIGGER reject_audit_insert ON approval_audit")
                cur.execute("DROP FUNCTION reject_audit()")
            self.connection.commit()

    def test_concurrent_consume_only_one_succeeds(self):
        outcomes = []
        barrier = threading.Barrier(2)
        def worker():
            try:
                with psycopg.connect(URL, options="-c search_path=" + self.schema) as conn:
                    barrier.wait(timeout=10)
                    PostgresApprovalStore(conn).consume(
                        approval_id=self.approval, actor_id=self.actor,
                        project_id=self.project, payload=self.payload)
                outcomes.append("consumed")
            except ApprovalRejected:
                outcomes.append("rejected")
            except Exception as exc:
                outcomes.append(type(exc).__name__)
        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=20)
        self.assertEqual(sorted(outcomes), ["consumed", "rejected"])

    def test_persists_across_connections(self):
        with psycopg.connect(URL, options="-c search_path=" + self.schema) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT idempotency_key FROM approvals WHERE approval_id=%s", (self.approval,))
                self.assertIsNotNone(cur.fetchone())


if __name__ == "__main__":
    unittest.main()
