import sqlite3
import time
import unittest

from approval_store_prototype import ApprovalStore, ApprovalStoreError


class ApprovalStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.store = ApprovalStore(self.db)
        self.payload = {"changes": {"Next Action": "Call client"}, "expected": {"Next Action": "Old"}}
        self.kw = {"actor_id": "reviewer-1", "project_id": "1", "payload": self.payload}
        self.approval_id = self.store.create(**self.kw, expires_at=int(time.time()) + 600, idempotency_key="request-1")

    def tearDown(self):
        self.db.close()

    def test_consume_once(self):
        result = self.store.consume(approval_id=self.approval_id, **self.kw)
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(len(self.store.audit(self.approval_id)), 1)
        with self.assertRaises(ApprovalStoreError):
            self.store.consume(approval_id=self.approval_id, **self.kw)

    def test_wrong_actor(self):
        with self.assertRaises(ApprovalStoreError):
            self.store.consume(approval_id=self.approval_id, actor_id="other", project_id="1", payload=self.payload)

    def test_wrong_project(self):
        with self.assertRaises(ApprovalStoreError):
            self.store.consume(approval_id=self.approval_id, actor_id="reviewer-1", project_id="2", payload=self.payload)

    def test_tampered_payload(self):
        with self.assertRaises(ApprovalStoreError):
            self.store.consume(approval_id=self.approval_id, actor_id="reviewer-1", project_id="1",
                               payload={"changes": {"Next Action": "Different"}})

    def test_expired(self):
        with self.assertRaises(ApprovalStoreError):
            self.store.consume(approval_id=self.approval_id, **self.kw, now=int(time.time()) + 601)

    def test_duplicate_idempotency_key(self):
        with self.assertRaises(ApprovalStoreError):
            self.store.create(**self.kw, expires_at=int(time.time()) + 600, idempotency_key="request-1")

    def test_audit_not_written_on_rejection(self):
        with self.assertRaises(ApprovalStoreError):
            self.store.consume(approval_id=self.approval_id, actor_id="other", project_id="1", payload=self.payload)
        self.assertEqual(self.store.audit(self.approval_id), [])

if __name__ == "__main__":
    unittest.main()
