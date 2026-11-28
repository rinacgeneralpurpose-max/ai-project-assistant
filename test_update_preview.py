"""Unit tests use stubs; no Google credentials or network required."""
import unittest
from unittest.mock import patch
from update_preview import preview_update

PROJECT = {"Project ID": "1", "Client": "Example", "Project Name": "Sample",
           "Next Action": "Old", "Current Stage": "CIVIL WORK"}

class PreviewTests(unittest.TestCase):
    def test_preview(self):
        with patch("update_preview.get_projects", return_value={"projects": [PROJECT], "total": 1}):
            result, code = preview_update({"project_id": "1", "transcript": "Call tomorrow",
                                           "changes": {"Next Action": "Call tomorrow"}})
        self.assertEqual(code, 200)
        self.assertEqual(result["status"], "review_required")
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(result["proposed_changes"]["Next Action"]["current"], "Old")

    def test_unknown_project(self):
        with patch("update_preview.get_projects", return_value={"projects": [], "total": 0}):
            _, code = preview_update({"project_id": "9", "transcript": "Test", "changes": {"Next Action": "Test"}})
        self.assertEqual(code, 409)

    def test_reject_disallowed_fields(self):
        _, code = preview_update({"project_id": "1", "transcript": "Test", "changes": {"Owner": "Someone"}})
        self.assertEqual(code, 400)

    def test_reject_missing_transcript(self):
        _, code = preview_update({"project_id": "1", "changes": {"Next Action": "Test"}})
        self.assertEqual(code, 400)

if __name__ == "__main__":
    unittest.main()
