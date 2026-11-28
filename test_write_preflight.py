import unittest

from write_preflight import PreflightError, ProposedChange, preflight

FIELDS = frozenset({"Next Action", "Current Stage"})
ROWS = [{"Project ID": "1", "Next Action": "Call client", "Current Stage": "OPEN"}]


class WritePreflightTests(unittest.TestCase):
    def run_plan(self, **overrides):
        values = dict(project_id="1", field="Next Action", expected="Call client", proposed="Send proposal")
        values.update(overrides)
        return preflight(ProposedChange(**values), rows=ROWS, allowed_fields=FIELDS)

    def test_valid_dry_run_does_not_mutate(self):
        original = [row.copy() for row in ROWS]
        result = self.run_plan()
        self.assertEqual(result["status"], "dry_run_only")
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(ROWS, original)

    def test_stale_value_rejected(self):
        with self.assertRaises(PreflightError):
            self.run_plan(expected="Old")

    def test_unknown_field_rejected(self):
        with self.assertRaises(PreflightError):
            self.run_plan(field="Order Value")

    def test_project_id_not_writable(self):
        with self.assertRaises(PreflightError):
            self.run_plan(field="Project ID")

    def test_formula_prefixes_rejected(self):
        for prefix in ("=", "+", "-", "@"):
            with self.subTest(prefix=prefix), self.assertRaises(PreflightError):
                self.run_plan(proposed="  " + prefix + "SUM(A1:A2)")

    def test_duplicate_id_rejected(self):
        with self.assertRaises(PreflightError):
            preflight(ProposedChange("1", "Next Action", "Call client", "Send proposal"),
                      rows=ROWS + ROWS, allowed_fields=FIELDS)

    def test_missing_id_rejected(self):
        with self.assertRaises(PreflightError):
            self.run_plan(project_id="999")

    def test_noop_rejected(self):
        with self.assertRaises(PreflightError):
            self.run_plan(proposed="Call client")


if __name__ == "__main__":
    unittest.main()
