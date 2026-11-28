"""Opt-in real PostgreSQL tests for Phase 5J atomic coordinator.

Only use a disposable database. Never supply production credentials.
"""
import os
import threading
import unittest
from uuid import uuid4

from atomic_project_coordinator import AtomicProjectCoordinator, AtomicStartDenied
from postgres_operation_coordinator import PostgresOperationCoordinator, SCHEMA_SQL
from postgres_project_gate import GATE_DDL

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg


@unittest.skipUnless(ENABLED and DSN, "Requires disposable PostgreSQL test database")
class AtomicCoordinatorDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "atomic_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(DSN, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
                    cur.execute(GATE_DDL)
        except Exception:
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
        self.coordinator = AtomicProjectCoordinator(self.conn)

    def test_start_creates_gate_and_applying_atomically(self):
        self.assertEqual(self.coordinator.start(
            project_id=self.project, operation_id=self.operation), "applying")
        with self.conn.cursor() as cur:
            cur.execute("SELECT state FROM sheet_operations WHERE operation_id=%s",
                        (self.operation,))
            self.assertEqual(cur.fetchone()[0], "applying")
            cur.execute("SELECT operation_id FROM project_write_gates WHERE project_id=%s",
                        (self.project,))
            self.assertEqual(str(cur.fetchone()[0]), self.operation)

    def test_gate_prevents_second_start(self):
        second = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        self.coordinator.start(project_id=self.project, operation_id=self.operation)
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.start(project_id=self.project, operation_id=second)
        with self.conn.cursor() as cur:
            cur.execute("SELECT state FROM sheet_operations WHERE operation_id=%s", (second,))
            self.assertEqual(cur.fetchone()[0], "approved")

    def test_ambiguity_retains_gate(self):
        self.coordinator.start(project_id=self.project, operation_id=self.operation)
        self.coordinator.ambiguous(project_id=self.project, operation_id=self.operation)
        with self.conn.cursor() as cur:
            cur.execute("SELECT recovery_required FROM project_write_gates WHERE project_id=%s",
                        (self.project,))
            self.assertTrue(cur.fetchone()[0])
        second = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.start(project_id=self.project, operation_id=second)

    def test_rollback_when_gate_missing(self):
        self.coordinator.start(project_id=self.project, operation_id=self.operation)
        with self.conn.transaction():
            with self.conn.cursor() as cur:
                cur.execute("DELETE FROM project_write_gates WHERE project_id=%s",
                            (self.project,))
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.ambiguous(project_id=self.project, operation_id=self.operation)
        with self.conn.cursor() as cur:
            cur.execute("SELECT state FROM sheet_operations WHERE operation_id=%s",
                        (self.operation,))
            self.assertEqual(cur.fetchone()[0], "applying")

    def test_concurrent_start_only_one_wins(self):
        second = PostgresOperationCoordinator(self.conn).reserve(
            project_id=self.project, approval_id=uuid4())
        barrier = threading.Barrier(2)
        outcomes = []
        def worker(op):
            try:
                with psycopg.connect(DSN, options="-c search_path=" + self.schema) as conn:
                    barrier.wait(timeout=10)
                    AtomicProjectCoordinator(conn).start(project_id=self.project, operation_id=op)
                outcomes.append("started")
            except AtomicStartDenied:
                outcomes.append("denied")
            except Exception as exc:
                outcomes.append(type(exc).__name__)
        threads = [threading.Thread(target=worker, args=(op,)) for op in (self.operation, second)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=20)
        self.assertEqual(sorted(outcomes), ["denied", "started"])


if __name__ == "__main__":
    unittest.main()
