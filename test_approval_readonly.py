import unittest
from unittest.mock import patch
from approval_readonly import create_review, validate_approval

BASE = {"project_id": "1", "transcript": "Follow up", "changes": {"Next Action": "Call client"}}
PREVIEW = {"status": "review_required", "project_id": "1", "transcript": "Follow up",
           "proposed_changes": {"Next Action": {"current": "Old action", "proposed": "Call client"}}}

class ApprovalTests(unittest.TestCase):
    @patch.dict("os.environ", {"APPROVAL_SIGNING_KEY": "a" * 64})
    @patch("approval_readonly.preview_update", return_value=(PREVIEW, 200))
    def test_review_and_validation(self, mock_preview):
        review, code = create_review(BASE)
        self.assertEqual(code, 200)
        result, code = validate_approval({"approve": True, "review_token": review["review_token"]})
        self.assertEqual(code, 200)
        self.assertEqual(result["status"], "approval_validated")
        self.assertFalse(result["writes_enabled"])

    @patch.dict("os.environ", {"APPROVAL_SIGNING_KEY": "a" * 64})
    @patch("approval_readonly.preview_update", return_value=(PREVIEW, 200))
    def test_tampered_token(self, mock_preview):
        review, _ = create_review(BASE)
        token = review["review_token"]
        result, code = validate_approval({"approve": True, "review_token": token[:-1] + ("0" if token[-1] != "0" else "1")})
        self.assertEqual(code, 401)

    @patch.dict("os.environ", {"APPROVAL_SIGNING_KEY": "a" * 64})
    @patch("approval_readonly.preview_update")
    def test_conflict(self, mock_preview):
        mock_preview.return_value = (PREVIEW, 200)
        review, _ = create_review(BASE)
        changed = {**PREVIEW, "proposed_changes": {"Next Action": {"current": "Changed elsewhere", "proposed": "Call client"}}}
        mock_preview.return_value = (changed, 200)
        result, code = validate_approval({"approve": True, "review_token": review["review_token"]})
        self.assertEqual(code, 409)
        self.assertEqual(result["status"], "conflict")

if __name__ == "__main__":
    unittest.main()
