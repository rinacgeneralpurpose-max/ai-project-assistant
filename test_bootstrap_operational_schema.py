"""Fail-closed tests for the opt-in schema bootstrap."""
import unittest
from bootstrap_operational_schema import bootstrap, DDL, TABLES


class Cursor:
    def __init__(self, existing=0, schema="public", fail=False):
        self.existing = existing
        self.schema = schema
        self.fail = fail
        self.query = ""
        self.ddl_count = 0
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, params=None):
        self.query = sql
        if sql in DDL:
            if self.fail:
                raise RuntimeError("secret-db-error")
            self.ddl_count += 1
    def fetchone(self):
        if "current_schema()" in self.query:
            return (self.schema,)
        if "information_schema.tables" in self.query:
            return (self.existing if not self.ddl_count else len(TABLES),)
        raise AssertionError("Unexpected fetchone")


class Connection:
    def __init__(self, cursor):
        self.c = cursor
        self.committed = False
        self.rolled_back = False
    def __enter__(self):
        return self
    def __exit__(self, typ, *_):
        self.committed = typ is None
        self.rolled_back = typ is not None
        return False
    def transaction(self):
        return self
    def cursor(self):
        return self.c


class BootstrapTests(unittest.TestCase):
    def test_explicit_confirmation_required(self):
        with self.assertRaises(ValueError):
            bootstrap("fake-dsn")
    def test_dsn_required(self):
        with self.assertRaises(ValueError):
            bootstrap("", confirm=True)
    def test_creates_expected_schema_once(self):
        conn = Connection(Cursor())
        result = bootstrap("fake-dsn", confirm=True,
                           connect=lambda *a, **k: conn)
        self.assertEqual(result["tables"], 4)
        self.assertFalse(result["writes_enabled"])
        self.assertEqual(conn.c.ddl_count, 4)
        self.assertTrue(conn.committed)
    def test_existing_schema_refused(self):
        conn = Connection(Cursor(existing=1))
        with self.assertRaises(RuntimeError):
            bootstrap("fake-dsn", confirm=True, connect=lambda *a, **k: conn)
        self.assertEqual(conn.c.ddl_count, 0)
        self.assertTrue(conn.rolled_back)
    def test_wrong_schema_refused(self):
        conn = Connection(Cursor(schema="other"))
        with self.assertRaises(RuntimeError):
            bootstrap("fake-dsn", confirm=True, connect=lambda *a, **k: conn)
        self.assertEqual(conn.c.ddl_count, 0)
    def test_ddl_failure_rolls_back(self):
        conn = Connection(Cursor(fail=True))
        with self.assertRaises(RuntimeError):
            bootstrap("fake-dsn", confirm=True, connect=lambda *a, **k: conn)
        self.assertTrue(conn.rolled_back)


if __name__ == "__main__":
    unittest.main()
