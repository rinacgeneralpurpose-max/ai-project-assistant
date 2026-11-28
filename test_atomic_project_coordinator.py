import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from atomic_project_coordinator import AtomicProjectCoordinator, AtomicStartDenied


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class AtomicCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = Transaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.coordinator = AtomicProjectCoordinator(self.conn)

    def test_start_uses_single_transaction(self):
        self.cur.fetchone.side_effect = [(uuid4(),), (uuid4(),)]
        self.assertEqual(self.coordinator.start(project_id="P1", operation_id=uuid4()), "applying")
        self.assertEqual(self.conn.transaction.call_count, 1)
        self.assertEqual(self.cur.execute.call_count, 2)

    def test_busy_gate_denied_before_state_update(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.start(project_id="P1", operation_id=uuid4())
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_state_race_denied(self):
        self.cur.fetchone.side_effect = [(uuid4(),), None]
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.start(project_id="P1", operation_id=uuid4())

    def test_project_required(self):
        with self.assertRaises(ValueError):
            self.coordinator.start(project_id=" ", operation_id=uuid4())

    def test_ambiguous_marks_both_in_one_transaction(self):
        self.cur.fetchone.side_effect = [(uuid4(),), (uuid4(),)]
        self.assertEqual(self.coordinator.ambiguous(
            project_id="P1", operation_id=uuid4()), "reconciliation_required")
        self.assertEqual(self.conn.transaction.call_count, 1)
        self.assertIn("recovery_required=TRUE", self.cur.execute.call_args.args[0])

    def test_ambiguous_missing_gate_denied(self):
        self.cur.fetchone.side_effect = [(uuid4(),), None]
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.ambiguous(project_id="P1", operation_id=uuid4())

    def test_ambiguous_wrong_state_denied(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(AtomicStartDenied):
            self.coordinator.ambiguous(project_id="P1", operation_id=uuid4())
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_no_release_api(self):
        self.assertFalse(hasattr(self.coordinator, "release"))


if __name__ == "__main__":
    unittest.main()
