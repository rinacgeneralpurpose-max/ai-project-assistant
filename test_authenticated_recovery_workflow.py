"""Offline tests: all identity-provider responses are stubs, not real logins."""
import unittest
from unittest.mock import MagicMock
from uuid import uuid4

from recovery_authentication import (
    RecoveryAuthenticationDenied, verify_recovery_reviewer,
)
from authenticated_recovery_workflow import (
    AuthenticatedRecoveryWorkflow, REQUESTER_LINK_DDL,
)
from recovery_review_store import RecoveryReviewDenied


AUDIENCE = "example-google-client.apps.googleusercontent.com"
CLAIMS = {
    "iss": "https://accounts.google.com",
    "aud": AUDIENCE,
    "email_verified": True,
    "sub": "reviewer-123",
}


class AuthTests(unittest.TestCase):
    def verify(self, claims=None, **kwargs):
        return verify_recovery_reviewer(
            token="valid-test-token", audience=AUDIENCE,
            allowed_subjects={"reviewer-123"},
            verifier=lambda token, audience: CLAIMS if claims is None else claims,
            **kwargs,
        )

    def test_allowlisted_google_subject(self):
        self.assertEqual(self.verify().subject, "reviewer-123")

    def test_bad_issuer_denied(self):
        with self.assertRaises(RecoveryAuthenticationDenied):
            self.verify(claims={**CLAIMS, "iss": "https://attacker.invalid"})

    def test_wrong_audience_denied(self):
        with self.assertRaises(RecoveryAuthenticationDenied):
            self.verify(claims={**CLAIMS, "aud": "other-client"})

    def test_unverified_account_denied(self):
        with self.assertRaises(RecoveryAuthenticationDenied):
            self.verify(claims={**CLAIMS, "email_verified": False})

    def test_non_allowlisted_subject_denied(self):
        with self.assertRaises(RecoveryAuthenticationDenied):
            self.verify(claims={**CLAIMS, "sub": "untrusted-user"})

    def test_signature_failure_denied_without_leaking_detail(self):
        def reject(token, audience):
            raise ValueError("supersecret token")
        with self.assertRaisesRegex(RecoveryAuthenticationDenied, "Identity verification failed") as context:
            verify_recovery_reviewer(
                token="invalid", audience=AUDIENCE,
                allowed_subjects={"reviewer-123"}, verifier=reject)
        self.assertNotIn("supersecret", str(context.exception))

    def test_unconfigured_audience_denied(self):
        with self.assertRaises(RecoveryAuthenticationDenied):
            verify_recovery_reviewer(token="x", audience="", allowed_subjects={"reviewer-123"})

    def test_unconfigured_allowlist_denied(self):
        with self.assertRaises(RecoveryAuthenticationDenied):
            verify_recovery_reviewer(token="x", audience=AUDIENCE, allowed_subjects=[])


class Transaction:
    def __enter__(self): return self
    def __exit__(self, *args): return False


class RecoveryWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.conn.transaction.return_value = Transaction()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.workflow = AuthenticatedRecoveryWorkflow(
            self.conn, audience=AUDIENCE,
            allowed_reviewer_subjects={"reviewer-123"},
            verifier=lambda token, audience: CLAIMS)
        self.kwargs = dict(token="token", project_id="P1", operation_id=uuid4(),
                           evidence={"sheet_observation": "value unchanged"},
                           decision="hold")

    def test_authenticated_review_stays_locked(self):
        self.cur.fetchone.side_effect = [
            ("requester-456",), ("reconciliation_required", True)]
        result = self.workflow.submit(**self.kwargs)
        self.assertFalse(result["gate_released"])
        self.assertEqual(self.conn.transaction.call_count, 2)
        self.assertIn("INSERT INTO recovery_reviews", self.cur.execute.call_args.args[0])
        self.assertEqual(self.cur.execute.call_count, 3)

    def test_missing_trusted_requester_denied(self):
        self.cur.fetchone.return_value = None
        with self.assertRaises(RecoveryReviewDenied):
            self.workflow.submit(**self.kwargs)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_self_review_denied_using_stored_requester(self):
        self.cur.fetchone.return_value = ("reviewer-123",)
        with self.assertRaises(RecoveryReviewDenied):
            self.workflow.submit(**self.kwargs)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_unverified_token_does_not_query_database(self):
        self.workflow.verifier = lambda token, audience: {**CLAIMS, "sub": "unknown"}
        with self.assertRaises(RecoveryAuthenticationDenied):
            self.workflow.submit(**self.kwargs)
        self.cur.execute.assert_not_called()

    def test_invalid_decision_does_not_insert(self):
        self.cur.fetchone.return_value = ("requester-456",)
        self.kwargs["decision"] = "release"
        with self.assertRaises(RecoveryReviewDenied):
            self.workflow.submit(**self.kwargs)
        self.assertEqual(self.cur.execute.call_count, 1)

    def test_requester_link_has_unique_operation_id(self):
        self.assertIn("operation_id UUID PRIMARY KEY", REQUESTER_LINK_DDL)


if __name__ == "__main__":
    unittest.main()
