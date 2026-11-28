"""Opt-in real PostgreSQL transaction tests for the audited coordinator.

Disposable database only. No external Sheets requests or production writes.
"""
import os
import unittest
from uuid import uuid4

from audited_atomic_coordinator import (
    AUDIT_DDL, AuditedAtomicCoordinator, AuditedTransitionDenied,
)
from postgres_operation_coordinator import PostgresOperationCoordinator, SCHEMA_SQL
from postgres_project_gate import GATE_DDL

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL test DB required")
class AuditedCoordinatorDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "audit_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.conn = None
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(
                DSN, autocommit=True, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
                    cur.execute(GATE_DDL)
                    cur.execute(AUDIT_DDL)
        except Exception:
            if cls.conn is not None:
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
        self.operation = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        self.coordinator = AuditedAtomicCoordinator(self.conn)

    def rows(self):
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT event_type,detail_json->>'actor_id'
                   FROM operation_audit_events WHERE operation_id=%s
                   ORDER BY occurred_at""", (self.operation,))
            return cur.fetchall()

    def state(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT state FROM sheet_operations WHERE operation_id=%s",
                (self.operation,))
            return cur.fetchone()[0]

    def gate(self):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT recovery_required FROM project_write_gates WHERE project_id=%s",
                (self.project,))
            row = cur.fetchone()
            return None if row is None else row[0]

    def test_start_audit_and_gate_commit_together(self):
        self.coordinator.start(
            project_id=self.project, operation_id=self.operation, actor_id="worker-1")
        self.assertEqual(self.state(), "applying")
        self.assertIs(self.gate(), False)
        self.assertEqual(self.rows(), [("operation_started", "worker-1")])

    def test_ambiguous_audit_and_gate_persist(self):
        self.coordinator.start(
            project_id=self.project, operation_id=self.operation, actor_id="worker-1")
        self.coordinator.ambiguous(
            project_id=self.project, operation_id=self.operation, actor_id="worker-1")
        self.assertEqual(self.state(), "reconciliation_required")
        self.assertIs(self.gate(), True)
        self.assertEqual(
            [row[0] for row in self.rows()],
            ["operation_started", "reconciliation_required"])

    def test_start_audit_failure_rolls_back_state_and_gate(self):
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """CREATE FUNCTION reject_start_audit() RETURNS trigger
                       LANGUAGE plpgsql AS $$
                       BEGIN RAISE EXCEPTION 'audit rejected'; END; $$""")
                cur.execute(
                    """CREATE TRIGGER reject_start_audit_insert
                       BEFORE INSERT ON operation_audit_events
                       FOR EACH ROW EXECUTE FUNCTION reject_start_audit()""")
        try:
            with self.assertRaises(Exception):
                self.coordinator.start(
                    project_id=self.project, operation_id=self.operation,
                    actor_id="worker-1")
            self.assertEqual(self.state(), "approved")
            self.assertIsNone(self.gate())
            self.assertEqual(self.rows(), [])
        finally:
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute("DROP TRIGGER reject_start_audit_insert ON operation_audit_events")
                    cur.execute("DROP FUNCTION reject_start_audit()")

    def test_ambiguity_audit_failure_rolls_back_gate_and_state(self):
        self.coordinator.start(
            project_id=self.project, operation_id=self.operation, actor_id="worker-1")
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """CREATE FUNCTION reject_ambiguity_audit() RETURNS trigger
                       LANGUAGE plpgsql AS $$
                       BEGIN IF NEW.event_type='reconciliation_required'
                       THEN RAISE EXCEPTION 'audit rejected'; END IF;
                       RETURN NEW; END; $$""")
                cur.execute(
                    """CREATE TRIGGER reject_ambiguity_audit_insert
                       BEFORE INSERT ON operation_audit_events
                       FOR EACH ROW EXECUTE FUNCTION reject_ambiguity_audit()""")
        try:
            with self.assertRaises(Exception):
                self.coordinator.ambiguous(
                    project_id=self.project, operation_id=self.operation,
                    actor_id="worker-1")
            self.assertEqual(self.state(), "applying")
            self.assertIs(self.gate(), False)
            self.assertEqual(self.rows(), [("operation_started", "worker-1")])
        finally:
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute("DROP TRIGGER reject_ambiguity_audit_insert ON operation_audit_events")
                    cur.execute("DROP FUNCTION reject_ambiguity_audit()")

    def test_second_start_denied_and_no_extra_audit(self):
        self.coordinator.start(
            project_id=self.project, operation_id=self.operation, actor_id="worker-1")
        second = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        with self.assertRaises(AuditedTransitionDenied):
            self.coordinator.start(
                project_id=self.project, operation_id=second, actor_id="worker-2")
        self.assertEqual(self.rows(), [("operation_started", "worker-1")])
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM operation_audit_events WHERE operation_id=%s",
                (second,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_ambiguous_without_gate_rolls_back_state(self):
        self.coordinator.start(
            project_id=self.project, operation_id=self.operation, actor_id="worker-1")
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM project_write_gates WHERE project_id=%s",
                    (self.project,))
        with self.assertRaises(AuditedTransitionDenied):
            self.coordinator.ambiguous(
                project_id=self.project, operation_id=self.operation,
                actor_id="worker-1")
        self.assertEqual(self.state(), "applying")
        self.assertEqual(self.rows(), [("operation_started", "worker-1")])


if __name__ == "__main__":
    unittest.main()
