import unittest
from unittest.mock import MagicMock

from postgres_diagnostics import check_database


class DatabaseDiagnosticTests(unittest.TestCase):
    def test_missing_dsn(self):
        self.assertEqual(check_database(dsn="")["status"], "not_configured")

    def fake_connect(self, row):
        connect = MagicMock()
        conn = connect.return_value.__enter__.return_value
        conn.cursor.return_value.__enter__.return_value.fetchone.return_value = row
        return connect, conn.cursor.return_value.__enter__.return_value

    def test_ready_read_only(self):
        connect, cur = self.fake_connect(("approvals", "approval_audit"))
        result = check_database(connect=connect, dsn="postgres://example")
        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(cur.execute.call_args_list[0].args[0], "SET TRANSACTION READ ONLY")

    def test_schema_missing(self):
        connect, _ = self.fake_connect((None, None))
        self.assertEqual(check_database(connect=connect, dsn="postgres://example")["status"], "schema_missing")

    def test_connection_failure_redacted(self):
        connect = MagicMock(side_effect=RuntimeError("password=secret"))
        result = check_database(connect=connect, dsn="postgres://example")
        self.assertEqual(result, {"status": "connection_failed", "writes_enabled": False})
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
