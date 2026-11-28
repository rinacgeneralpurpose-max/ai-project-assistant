import unittest

from write_coordination_policy import (
    OperationState, PolicyDenied, ReviewerIdentity, authorize_reviewer,
    classify_sheet_result, deduplication_key, transition,
)


class CoordinationPolicyTests(unittest.TestCase):
    def test_authenticated_reviewer(self):
        reviewer = ReviewerIdentity("reviewer-2", frozenset({"project_update_reviewer"}), True)
        self.assertTrue(authorize_reviewer(reviewer, requestor_subject="requester-1"))

    def test_self_approval_denied(self):
        reviewer = ReviewerIdentity("same", frozenset({"project_update_reviewer"}), True)
        with self.assertRaises(PolicyDenied):
            authorize_reviewer(reviewer, requestor_subject="same")

    def test_unauthenticated_denied(self):
        reviewer = ReviewerIdentity("reviewer", frozenset({"project_update_reviewer"}), False)
        with self.assertRaises(PolicyDenied):
            authorize_reviewer(reviewer, requestor_subject="requester")

    def test_role_denied(self):
        reviewer = ReviewerIdentity("reviewer", frozenset({"viewer"}), True)
        with self.assertRaises(PolicyDenied):
            authorize_reviewer(reviewer, requestor_subject="requester")

    def test_unknown_identity_denied(self):
        with self.assertRaises(PolicyDenied):
            authorize_reviewer(None, requestor_subject="requester")

    def test_valid_transition(self):
        self.assertEqual(transition("approved", "applying"), OperationState.APPLYING)

    def test_illegal_retry_transition(self):
        with self.assertRaises(PolicyDenied):
            transition("reconciliation_required", "applying")

    def test_no_replay_after_applied(self):
        with self.assertRaises(PolicyDenied):
            transition("applied", "applying")

    def test_ambiguous_sheet_result_requires_reconciliation(self):
        self.assertEqual(classify_sheet_result(request_sent=True, confirmed_success=False),
                         OperationState.RECONCILIATION_REQUIRED)

    def test_unsent_request_can_return_to_approved(self):
        self.assertEqual(classify_sheet_result(request_sent=False, confirmed_success=False),
                         OperationState.APPROVED)

    def test_deduplication_key(self):
        self.assertEqual(deduplication_key(project_id="P1", approval_id="A1"), ("P1", "A1"))


if __name__ == "__main__":
    unittest.main()
