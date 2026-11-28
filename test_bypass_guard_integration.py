"""Opt-in PostgreSQL tests for DB-level bypass prevention. Disposable DB only."""
import os
import unittest
from uuid import uuid4

from audited_atomic_coordinator import AUDIT_DDL, AuditedAtomicCoordinator
from postgres_bypass_guard import BYPASS_GUARD_DDL
from postgres_operation_coordinator import PostgresOperationCoordinator, SCHEMA_SQL
from postgres_project_gate import GATE_DDL

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL database required")
class BypassGuardDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "bypass_test_" + uuid4().hex
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
                    cur.execute(BYPASS_GUARD_DDL)
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
        self.op = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())

    def state(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT state FROM sheet_operations WHERE operation_id=%s", (self.op,))
            return cur.fetchone()[0]

    def test_legacy_begin_denied_without_gate(self):
        with self.assertRaises(Exception):
            PostgresOperationCoordinator(self.conn).begin(operation_id=self.op)
        self.assertEqual(self.state(), "approved")

    def test_legacy_begin_denied_with_gate_but_no_audit(self):
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO project_write_gates(project_id,operation_id) VALUES (%s,%s)",
                    (self.project, self.op))
        with self.assertRaises(Exception):
            PostgresOperationCoordinator(self.conn).begin(operation_id=self.op)
        self.assertEqual(self.state(), "approved")

    def test_audited_start_allowed(self):
        self.assertEqual(
            AuditedAtomicCoordinator(self.conn).start(
                project_id=self.project, operation_id=self.op, actor_id="worker"),
            "applying")
        self.assertEqual(self.state(), "applying")

    def test_legacy_ambiguous_denied_without_recovery_gate(self):
        AuditedAtomicCoordinator(self.conn).start(
            project_id=self.project, operation_id=self.op, actor_id="worker")
        with self.assertRaises(Exception):
            PostgresOperationCoordinator(self.conn).record_result(
                operation_id=self.op, confirmed_success=False)
        self.assertEqual(self.state(), "applying")

    def test_legacy_applied_denied(self):
        AuditedAtomicCoordinator(self.conn).start(
            project_id=self.project, operation_id=self.op, actor_id="worker")
        with self.assertRaises(Exception):
            PostgresOperationCoordinator(self.conn).record_result(
                operation_id=self.op, confirmed_success=True)
        self.assertEqual(self.state(), "applying")

    def test_audited_ambiguity_allowed(self):
        coordinator = AuditedAtomicCoordinator(self.conn)
        coordinator.start(project_id=self.project, operation_id=self.op, actor_id="worker")
        self.assertEqual(coordinator.ambiguous(
            project_id=self.project, operation_id=self.op, actor_id="worker"),
            "reconciliation_required")
        self.assertEqual(self.state(), "reconciliation_required")

    def test_missing_audit_prevents_fake_recovery_transition(self):
        AuditedAtomicCoordinator(self.conn).start(
            project_id=self.project, operation_id=self.op, actor_id="worker")
        with self.assertRaises(Exception):
            with self.conn.transaction():
                with self.conn.cursor() as cur:
                    cur.execute(
                        """UPDATE project_write_gates SET recovery_required=TRUE
                           WHERE project_id=%s""", (self.project,))
                    cur.execute(
                        """UPDATE sheet_operations SET state='reconciliation_required'
                           WHERE operation_id=%s""", (self.op,))
        self.assertEqual(self.state(), "applying")
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT recovery_required FROM project_write_gates WHERE project_id=%s",
                (self.project,))
            self.assertIs(cur.fetchone()[0], False)


if __name__ == "__main__":
    unittest.main()
