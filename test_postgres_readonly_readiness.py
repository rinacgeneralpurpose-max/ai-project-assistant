"""Offline tests for PostgreSQL readiness, with no live credentials."""
import json
import unittest
from postgres_readonly_readiness import assess, REQUIRED_COLUMNS


class Cursor:
    def __init__(self, *, writable=False, missing=False):
        self.writable, self.missing = writable, missing
        self.query = ""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, query, params=None):
        self.query = query
        if params is not None:
            assert isinstance(params, tuple)
    def fetchone(self):
        if "transaction_read_only" in self.query:
            return ("on",)
        return (True, False, False, False, False)
    def fetchall(self):
        if "information_schema.columns" in self.query:
            return [(t, c) for t, cols in REQUIRED_COLUMNS.items()
                    for c in cols if not (self.missing and c == "state")]
        if "information_schema.tables" in self.query:
            return [(t, True, self.writable) for t in REQUIRED_COLUMNS]
        raise AssertionError("Unexpected query")


class Connection:
    def __init__(self, cursor):
        self.c = cursor
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def cursor(self):
        return self.c


class ReadinessTests(unittest.TestCase):
    def connect(self, **kwargs):
        return lambda dsn, connect_timeout: Connection(Cursor(**kwargs))

    def test_not_configured(self):
        self.assertEqual(assess(None)["status"], "not_configured")

    def test_all_checks_pass(self):
        report = assess("fake-dsn", connect=self.connect())
        self.assertEqual(report["status"], "pass")
        self.assertFalse(report["writes_enabled"])
        self.assertTrue(all(report["checks"].values()))
        self.assertNotIn("fake-dsn", json.dumps(report))

    def test_write_grants_fail(self):
        report = assess("fake-dsn", connect=self.connect(writable=True))
        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["checks"]["no_mutation_grants"])

    def test_missing_column_fails(self):
        report = assess("fake-dsn", connect=self.connect(missing=True))
        self.assertEqual(report["status"], "fail")
        self.assertFalse(report["checks"]["required_schema"])

    def test_connection_failure_redacted(self):
        def failing(*args, **kwargs):
            raise RuntimeError("secret-password")
        report = assess("secret-password", connect=failing)
        self.assertEqual(report["status"], "fail")
        self.assertNotIn("secret-password", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
