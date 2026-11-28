"""Real disposable-PostgreSQL tests of protected record mutation triggers."""
import os
import unittest
from uuid import uuid4

from postgres_operation_coordinator import SCHEMA_SQL, PostgresOperationCoordinator
from audited_atomic_coordinator import AUDIT_DDL, AuditedAtomicCoordinator
from postgres_project_gate import GATE_DDL
from recovery_review_store import RECOVERY_DDL
from authenticated_recovery_workflow import REQUESTER_LINK_DDL
from postgres_integrity_guards import INTEGRITY_DDL

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL required")
class IntegrityGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "integrity_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.conn = None
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(
                DSN, autocommit=True, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    for ddl in (SCHEMA_SQL, GATE_DDL, AUDIT_DDL,
                                RECOVERY_DDL, REQUESTER_LINK_DDL, INTEGRITY_DDL):
                        cur.execute(ddl)
        except Exception:
            if cls.conn:
                cls.conn.close()
            with cls.admin.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS " + cls.schema + " CASCADE")
            cls.admin.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()
        try:
            with cls.admin.cursor() as cur:
                cur.execute("DROP SCHEMA IF EXISTS " + cls.schema + " CASCADE")
        finally:
            cls.admin.close()

    def setUp(self):
        self.project = "P-" + uuid4().hex
        self.op = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        AuditedAtomicCoordinator(self.conn).start(
            project_id=self.project, operation_id=self.op, actor_id="worker")
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO operation_requesters(operation_id,requestor_subject) VALUES (%s,%s)",
                    (self.op, "original-requester"))

    def test_audit_event_cannot_be_updated(self):
        with self.assertRaises(Exception):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute(
                        """UPDATE operation_audit_events SET event_type='reconciliation_required'
                           WHERE operation_id=%s""", (self.op,))

    def test_audit_event_cannot_be_deleted(self):
        with self.assertRaises(Exception):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute("DELETE FROM operation_audit_events WHERE operation_id=%s",
                                (self.op,))

    def test_requester_identity_cannot_be_reassigned(self):
        with self.assertRaises(Exception):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute(
                        """UPDATE operation_requesters SET requestor_subject='attacker'
                           WHERE operation_id=%s""", (self.op,))

    def test_requester_identity_cannot_be_deleted(self):
        with self.assertRaises(Exception):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute("DELETE FROM operation_requesters WHERE operation_id=%s",
                                (self.op,))

    def test_recovery_review_cannot_be_mutated(self):
        AuditedAtomicCoordinator(self.conn).ambiguous(
            project_id=self.project, operation_id=self.op, actor_id="worker")
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO recovery_reviews
                       (review_id,operation_id,project_id,reviewer_id,evidence_json,decision)
                       VALUES (%s,%s,%s,%s,%s::jsonb,%s)""",
                    (uuid4(), self.op, self.project, "reviewer", "{}", "hold"))
        with self.assertRaises(Exception):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM recovery_reviews WHERE operation_id=%s", (self.op,))


if __name__ == "__main__":
    unittest.main()
