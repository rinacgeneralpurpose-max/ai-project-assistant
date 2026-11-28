import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from recovery_review_store import RecoveryReviewDenied, RecoveryReviewStore, RECOVERY_DDL


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class RecoveryReviewTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = Transaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.store = RecoveryReviewStore(self.conn)
        self.kw = dict(operation_id=uuid4(), project_id="P1",
                       reviewer_id="reviewer", requestor_id="requester",
                       evidence={"sheet_observation": "value unchanged"}, decision="hold")

    def test_review_stays_locked(self):
        self.cur.fetchone.return_value = ("reconciliation_required", True)
        result = self.store.record(**self.kw)
        self.assertFalse(result["gate_released"])
        self.assertFalse(result["writes_enabled"])

    def test_self_review_denied(self):
        self.kw["requestor_id"] = "reviewer"
        with self.assertRaises(RecoveryReviewDenied):
            self.store.record(**self.kw)

    def test_release_decision_denied(self):
        self.kw["decision"] = "release"
        with self.assertRaises(RecoveryReviewDenied):
            self.store.record(**self.kw)

    def test_missing_evidence_denied(self):
        self.kw["evidence"] = {}
        with self.assertRaises(RecoveryReviewDenied):
            self.store.record(**self.kw)

    def test_unlocked_operation_denied(self):
        self.cur.fetchone.return_value = ("applied", False)
        with self.assertRaises(RecoveryReviewDenied):
            self.store.record(**self.kw)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_schema_prevents_duplicate_review(self):
        self.assertIn("operation_id UUID NOT NULL UNIQUE", RECOVERY_DDL)

    def test_no_release_method(self):
        self.assertFalse(hasattr(self.store, "release"))


if __name__ == "__main__":
    unittest.main()
