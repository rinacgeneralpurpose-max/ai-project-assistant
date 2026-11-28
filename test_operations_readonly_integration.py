"""Disposable PostgreSQL integration tests for read-only application queries."""
import os
import unittest
from uuid import uuid4

from audited_atomic_coordinator import AUDIT_DDL, AuditedAtomicCoordinator
from postgres_operation_coordinator import SCHEMA_SQL, PostgresOperationCoordinator
from postgres_project_gate import GATE_DDL
from recovery_review_store import RECOVERY_DDL
from operations_readonly import list_operations, operation_detail

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL required")
class OperationVisibilityDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "visibility_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.conn = None
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(
                DSN, autocommit=True, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    for ddl in (SCHEMA_SQL, GATE_DDL, AUDIT_DDL, RECOVERY_DDL):
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

    @classmethod
    def connect(cls, dsn, connect_timeout=5):
        return psycopg.connect(
            dsn, connect_timeout=connect_timeout,
            options="-c search_path=" + cls.schema)

    def setUp(self):
        self.project = "P-" + uuid4().hex
        self.op = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())

    def test_list_returns_reserved_operation(self):
        result = list_operations(
            dsn=DSN, project_id=self.project, connect=self.connect)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["operations"][0]["state"], "approved")
        self.assertFalse(result["writes_enabled"])

    def test_detail_includes_audit_without_actor_identity(self):
        AuditedAtomicCoordinator(self.conn).start(
            project_id=self.project, operation_id=self.op, actor_id="internal-actor")
        result = operation_detail(
            dsn=DSN, operation_id=self.op, connect=self.connect)
        self.assertEqual(result["state"], "applying")
        self.assertEqual(result["audit_events"][0]["event_type"], "operation_started")
        self.assertNotIn("internal-actor", str(result))
        self.assertFalse(result["writes_enabled"])

    def test_recovery_status_is_visible(self):
        coordinator = AuditedAtomicCoordinator(self.conn)
        coordinator.start(project_id=self.project, operation_id=self.op, actor_id="worker")
        coordinator.ambiguous(project_id=self.project, operation_id=self.op, actor_id="worker")
        result = list_operations(
            dsn=DSN, project_id=self.project, connect=self.connect)
        self.assertTrue(result["operations"][0]["recovery_required"])

    def test_bad_uuid_rejected_before_connection(self):
        with self.assertRaises(ValueError):
            operation_detail(dsn=DSN, operation_id="bad", connect=self.connect)

    def test_read_only_query_does_not_change_state(self):
        before = operation_detail(
            dsn=DSN, operation_id=self.op, connect=self.connect)
        list_operations(dsn=DSN, project_id=self.project, connect=self.connect)
        after = operation_detail(
            dsn=DSN, operation_id=self.op, connect=self.connect)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
