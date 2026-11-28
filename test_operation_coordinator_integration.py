"""Opt-in tests for PostgreSQL operation coordination on a disposable DB.

Never use production credentials. Requires psycopg 3, TEST_DATABASE_URL and
RUN_POSTGRES_INTEGRATION_TESTS=1. No Google Sheets calls are made.
"""
import os
import threading
import unittest
from uuid import uuid4

from postgres_operation_coordinator import (
    CoordinationConflict, PostgresOperationCoordinator, SCHEMA_SQL,
)

ENABLED = os.environ.get("RUN_POSTGRES_INTEGRATION_TESTS") == "1"
DSN = os.environ.get("TEST_DATABASE_URL", "")
if ENABLED and DSN:
    import psycopg
    from psycopg.errors import UniqueViolation


@unittest.skipUnless(ENABLED and DSN, "Disposable PostgreSQL database required")
class OperationCoordinatorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "coord_test_" + uuid4().hex
        cls.admin = psycopg.connect(DSN, autocommit=True)
        try:
            with cls.admin.cursor() as cur:
                cur.execute("CREATE SCHEMA " + cls.schema)
            cls.conn = psycopg.connect(DSN, options="-c search_path=" + cls.schema)
            with cls.conn.transaction():
                with cls.conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
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
        self.coordinator = PostgresOperationCoordinator(self.conn)
        self.project = "P-" + uuid4().hex
        self.approval = uuid4()
        self.operation = self.coordinator.reserve(project_id=self.project, approval_id=self.approval)

    def test_duplicate_reservation_across_connections(self):
        with psycopg.connect(DSN, options="-c search_path=" + self.schema) as conn:
            with self.assertRaises(CoordinationConflict):
                PostgresOperationCoordinator(conn).reserve(
                    project_id=self.project, approval_id=self.approval)

    def test_single_project_applying_slot(self):
        second = self.coordinator.reserve(project_id=self.project, approval_id=uuid4())
        self.coordinator.begin(operation_id=self.operation)
        with self.assertRaises(UniqueViolation):
            self.coordinator.begin(operation_id=second)
        self.assertEqual(self.coordinator.record_result(
            operation_id=self.operation, confirmed_success=False),
            "reconciliation_required")
        # Reconciliation releases the applying slot but must not retry the first operation.
        self.assertEqual(self.coordinator.begin(operation_id=second), "applying")
        with self.assertRaises(CoordinationConflict):
            self.coordinator.begin(operation_id=self.operation)

    def test_state_persists_across_connections(self):
        self.coordinator.begin(operation_id=self.operation)
        with psycopg.connect(DSN, options="-c search_path=" + self.schema) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM sheet_operations WHERE operation_id=%s",
                            (self.operation,))
                self.assertEqual(cur.fetchone()[0], "applying")

    def test_ambiguous_result_blocks_replay(self):
        self.coordinator.begin(operation_id=self.operation)
        self.coordinator.record_result(operation_id=self.operation, confirmed_success=False)
        with self.assertRaises(CoordinationConflict):
            self.coordinator.record_result(operation_id=self.operation, confirmed_success=True)

    def test_concurrent_begin_only_one_wins(self):
        second = self.coordinator.reserve(project_id=self.project, approval_id=uuid4())
        barrier = threading.Barrier(2)
        outcomes = []
        def worker(op):
            try:
                with psycopg.connect(DSN, options="-c search_path=" + self.schema) as conn:
                    barrier.wait(timeout=10)
                    PostgresOperationCoordinator(conn).begin(operation_id=op)
                outcomes.append("applying")
            except Exception as exc:
                outcomes.append(type(exc).__name__)
        threads = [threading.Thread(target=worker, args=(op,)) for op in (self.operation, second)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(outcomes.count("applying"), 1)
        self.assertEqual(outcomes.count("UniqueViolation"), 1)


if __name__ == "__main__":
    unittest.main()
