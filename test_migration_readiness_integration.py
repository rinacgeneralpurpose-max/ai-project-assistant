"""Opt-in real PostgreSQL migration-readiness verification.

Only run with a disposable TEST_DATABASE_URL.
"""
import os
import unittest
from uuid import uuid4

from migration_readiness import inspect_migration_readiness
from audited_atomic_coordinator import AUDIT_DDL, AuditedAtomicCoordinator
from authenticated_recovery_workflow import REQUESTER_LINK_DDL
from postgres_operation_coordinator import SCHEMA_SQL, PostgresOperationCoordinator
from postgres_project_gate import GATE_DDL
from recovery_review_store import RECOVERY_DDL

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL required")
class MigrationReadinessDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "readiness_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        cls.conn = None
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(
                DSN, autocommit=True, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    for ddl in (SCHEMA_SQL, GATE_DDL, AUDIT_DDL, RECOVERY_DDL,
                                REQUESTER_LINK_DDL):
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
        # Each test starts with a clean disposable schema; avoid order dependence.
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute(
                    """TRUNCATE recovery_reviews, operation_requesters,
                       operation_audit_events, project_write_gates,
                       sheet_operations CASCADE""")

    def test_empty_schema_is_ready_for_review_only(self):
        report = inspect_migration_readiness(self.conn)
        self.assertTrue(report.ready_for_review)
        self.assertFalse(report.as_dict()["writes_enabled"])
        self.assertTrue(all(value == 0 for value in report.findings.values()))

    def test_unmapped_operation_fails_closed(self):
        op = PostgresOperationCoordinator(self.conn).reserve(
            project_id="P-" + uuid4().hex, approval_id=uuid4())
        report = inspect_migration_readiness(self.conn)
        self.assertFalse(report.ready_for_review)
        self.assertGreater(report.findings["unmapped_operation_requesters"], 0)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO operation_requesters(operation_id,requestor_subject) VALUES (%s,%s)",
                            (op, "requester"))
        self.assertEqual(
            inspect_migration_readiness(self.conn).findings["unmapped_operation_requesters"], 0)

    def test_legacy_applying_without_audit_is_detected(self):
        project = "P-" + uuid4().hex
        op = PostgresOperationCoordinator(self.conn).reserve(
            project_id=project, approval_id=uuid4())
        PostgresOperationCoordinator(self.conn).begin(operation_id=op)
        report = inspect_migration_readiness(self.conn)
        self.assertFalse(report.ready_for_review)
        self.assertGreater(report.findings["applying_without_gate"], 0)
        self.assertGreater(report.findings["applying_without_start_audit"], 0)

    def test_audited_start_has_gate_and_audit(self):
        project = "P-" + uuid4().hex
        op = PostgresOperationCoordinator(self.conn).reserve(
            project_id=project, approval_id=uuid4())
        AuditedAtomicCoordinator(self.conn).start(
            project_id=project, operation_id=op, actor_id="worker")
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute("INSERT INTO operation_requesters(operation_id,requestor_subject) VALUES (%s,%s)",
                            (op, "requester"))
        report = inspect_migration_readiness(self.conn)
        self.assertEqual(report.findings["applying_without_gate"], 0)
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM sheet_operations o
                   LEFT JOIN project_write_gates g ON g.project_id=o.project_id
                     AND g.operation_id=o.operation_id
                   WHERE o.operation_id=%s AND g.operation_id IS NULL""",
                (op,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_missing_tables_fail_closed(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT current_schema()")
            self.assertEqual(cur.fetchone()[0], self.schema)
        # Empty schema on separate connection, no production objects.
        empty_schema = "missing_test_" + uuid4().hex
        with self.admin.cursor() as cur:
            cur.execute("CREATE SCHEMA " + empty_schema)
        try:
            with psycopg.connect(
                DSN, autocommit=True,
                options="-c search_path=" + empty_schema) as conn:
                report = inspect_migration_readiness(conn)
                self.assertFalse(report.ready_for_review)
                self.assertTrue(report.missing_tables)
        finally:
            with self.admin.cursor() as cur:
                cur.execute("DROP SCHEMA " + empty_schema + " CASCADE")


if __name__ == "__main__":
    unittest.main()
