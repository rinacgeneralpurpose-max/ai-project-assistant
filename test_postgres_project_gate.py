import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from postgres_project_gate import GATE_DDL, PostgresProjectGate, ProjectGateBusy


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class ProjectGateTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = Transaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.gate = PostgresProjectGate(self.conn)

    def test_primary_key_project_lock(self):
        self.assertIn("project_id TEXT PRIMARY KEY", GATE_DDL)

    def test_acquire(self):
        self.cur.fetchone.return_value = (uuid4(),)
        self.assertEqual(self.gate.acquire(project_id="P1", operation_id=uuid4()), "held")

    def test_duplicate_project_denied(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(ProjectGateBusy):
            self.gate.acquire(project_id="P1", operation_id=uuid4())

    def test_invalid_project_denied(self):
        with self.assertRaises(ValueError):
            self.gate.acquire(project_id=" ", operation_id=uuid4())

    def test_recovery_does_not_release(self):
        self.cur.fetchone.return_value = (uuid4(),)
        self.assertEqual(self.gate.mark_recovery_required(
            project_id="P1", operation_id=uuid4()), "recovery_required")
        self.assertIn("SET recovery_required=TRUE", self.cur.execute.call_args.args[0])
        self.assertNotIn("DELETE", self.cur.execute.call_args.args[0])

    def test_recovery_wrong_owner_denied(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(ProjectGateBusy):
            self.gate.mark_recovery_required(project_id="P1", operation_id=uuid4())

    def test_locked_status(self):
        operation = uuid4()
        self.cur.fetchone.return_value = (operation, True)
        result = self.gate.status(project_id="P1")
        self.assertEqual(result["state"], "recovery_required")
        self.assertFalse(result["writes_enabled"])

    def test_unlocked_status(self):
        self.cur.fetchone.return_value = None
        self.assertEqual(self.gate.status(project_id="P1")["state"], "unlocked")

    def test_no_unsafe_release_api(self):
        self.assertFalse(hasattr(self.gate, "release"))


if __name__ == "__main__":
    unittest.main()
