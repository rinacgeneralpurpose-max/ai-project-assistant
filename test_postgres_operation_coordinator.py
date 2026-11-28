import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from postgres_operation_coordinator import (
    CoordinationConflict, PostgresOperationCoordinator, SCHEMA_SQL,
)


class FakeTransaction:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = FakeTransaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.coordinator = PostgresOperationCoordinator(self.conn)

    def test_unique_operation_schema(self):
        self.assertIn("UNIQUE (project_id, approval_id)", SCHEMA_SQL)

    def test_project_serialization_schema(self):
        self.assertIn("WHERE state='applying'", SCHEMA_SQL)

    def test_reserve_success(self):
        op = uuid4()
        self.cur.fetchone.return_value = (op,)
        self.assertEqual(self.coordinator.reserve(project_id="P1", approval_id=uuid4()), str(op))

    def test_duplicate_reservation_rejected(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(CoordinationConflict):
            self.coordinator.reserve(project_id="P1", approval_id=uuid4())

    def test_blank_project_rejected(self):
        with self.assertRaises(ValueError):
            self.coordinator.reserve(project_id=" ", approval_id=uuid4())

    def test_begin_only_approved(self):
        self.cur.fetchone.return_value = (uuid4(),)
        self.assertEqual(self.coordinator.begin(operation_id=uuid4()), "applying")
        self.assertIn("state='approved'", self.cur.execute.call_args.args[0])

    def test_begin_replay_denied(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(CoordinationConflict):
            self.coordinator.begin(operation_id=uuid4())

    def test_unconfirmed_result_requires_reconciliation(self):
        self.cur.fetchone.return_value = (uuid4(),)
        self.assertEqual(self.coordinator.record_result(operation_id=uuid4(),
                                                        confirmed_success=False),
                         "reconciliation_required")

    def test_confirmed_result_applied(self):
        self.cur.fetchone.return_value = (uuid4(),)
        self.assertEqual(self.coordinator.record_result(operation_id=uuid4(),
                                                        confirmed_success=True), "applied")


if __name__ == "__main__":
    unittest.main()
