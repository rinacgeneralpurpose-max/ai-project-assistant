import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from audited_atomic_coordinator import (
    AUDIT_DDL, AuditedAtomicCoordinator, AuditedTransitionDenied,
)


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class AuditedCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = Transaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.coordinator = AuditedAtomicCoordinator(self.conn)

    def test_start_has_audit_in_same_transaction(self):
        self.cur.fetchone.side_effect = [(uuid4(),), (uuid4(),)]
        self.assertEqual(self.coordinator.start(
            project_id="P1", operation_id=uuid4(), actor_id="reviewer"), "applying")
        self.assertEqual(self.conn.transaction.call_count, 1)
        self.assertEqual(self.cur.execute.call_count, 3)
        self.assertIn("INSERT INTO operation_audit_events", self.cur.execute.call_args.args[0])

    def test_start_busy_does_not_audit(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(AuditedTransitionDenied):
            self.coordinator.start(project_id="P1", operation_id=uuid4(), actor_id="reviewer")
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_ambiguous_audited(self):
        self.cur.fetchone.side_effect = [(uuid4(),), (uuid4(),)]
        self.assertEqual(self.coordinator.ambiguous(
            project_id="P1", operation_id=uuid4(), actor_id="reviewer"),
            "reconciliation_required")
        self.assertEqual(self.cur.execute.call_count, 3)

    def test_missing_gate_no_audit(self):
        self.cur.fetchone.side_effect = [(uuid4(),), None]
        with self.assertRaises(AuditedTransitionDenied):
            self.coordinator.ambiguous(project_id="P1", operation_id=uuid4(), actor_id="reviewer")
        self.assertEqual(self.cur.execute.call_count, 2)

    def test_blank_actor_denied(self):
        with self.assertRaises(ValueError):
            self.coordinator.start(project_id="P1", operation_id=uuid4(), actor_id=" ")

    def test_audit_schema_references_operation(self):
        self.assertIn("REFERENCES sheet_operations(operation_id)", AUDIT_DDL)

    def test_no_release_method(self):
        self.assertFalse(hasattr(self.coordinator, "release"))


if __name__ == "__main__":
    unittest.main()
