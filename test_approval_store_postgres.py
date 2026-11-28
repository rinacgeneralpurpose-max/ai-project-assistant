import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from approval_store_postgres import ApprovalRejected, PostgresApprovalStore, payload_digest


class FakeTransaction:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class PostgresApprovalTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = FakeTransaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.store = PostgresApprovalStore(self.conn)

    def test_canonical_hash(self):
        self.assertEqual(payload_digest({"a": 1, "b": 2}), payload_digest({"b": 2, "a": 1}))

    def test_create_requires_actor(self):
        with self.assertRaises(ValueError):
            self.store.create(actor_id="", project_id="1", payload={}, idempotency_key="x",
                              expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))

    def test_create_requires_aware_expiry(self):
        with self.assertRaises(ValueError):
            self.store.create(actor_id="a", project_id="1", payload={}, idempotency_key="x",
                              expires_at=datetime.utcnow())

    def test_consume_success_writes_audit(self):
        self.cur.fetchone.return_value = ("approval-id",)
        result = self.store.consume(approval_id="00000000-0000-0000-0000-000000000001",
                                    actor_id="reviewer", project_id="1", payload={"x": "y"})
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(self.cur.execute.call_count, 2)
        self.assertIn("INSERT INTO approval_audit", self.cur.execute.call_args_list[1].args[0])

    def test_consume_rejected_without_audit(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(ApprovalRejected):
            self.store.consume(approval_id="00000000-0000-0000-0000-000000000001",
                               actor_id="reviewer", project_id="1", payload={})
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_expiry_checked_in_sql(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(ApprovalRejected):
            self.store.consume(approval_id="00000000-0000-0000-0000-000000000001",
                               actor_id="reviewer", project_id="1", payload={})
        self.assertIn("expires_at > %s", self.cur.execute.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
