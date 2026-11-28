"""Reviewed PostgreSQL operational schema bootstrap, opt-in and fail-closed.

Never called by Flask. Requires explicit CLI confirmation and a migration-only
database connection. No Google Sheets writes, sample data or role creation.
"""
import argparse
import os
import sys

from postgres_operation_coordinator import SCHEMA_SQL
from postgres_project_gate import GATE_DDL
from audited_atomic_coordinator import AUDIT_DDL
from recovery_review_store import RECOVERY_DDL

DDL = (SCHEMA_SQL, GATE_DDL, AUDIT_DDL, RECOVERY_DDL)
TABLES = ("sheet_operations", "project_write_gates",
          "operation_audit_events", "recovery_reviews")


def bootstrap(dsn, *, confirm=False, connect=None):
    if not confirm:
        raise ValueError("Explicit --apply-reviewed-schema confirmation required")
    if not dsn:
        raise ValueError("MIGRATION_DATABASE_URL required")
    if connect is None:
        import psycopg
        connect = psycopg.connect
    with connect(dsn, connect_timeout=5) as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(824617032)")
                cur.execute("SELECT current_schema()")
                schema = cur.fetchone()[0]
                if schema != "public":
                    raise RuntimeError("Expected public schema")
                cur.execute("""SELECT count(*) FROM information_schema.tables
                               WHERE table_schema='public' AND table_name=ANY(%s)""",
                            (list(TABLES),))
                existing = cur.fetchone()[0]
                if existing:
                    raise RuntimeError("Operational tables already exist; refusing partial bootstrap")
                for statement in DDL:
                    cur.execute(statement)
                cur.execute("""SELECT count(*) FROM information_schema.tables
                               WHERE table_schema='public' AND table_name=ANY(%s)""",
                            (list(TABLES),))
                if cur.fetchone()[0] != len(TABLES):
                    raise RuntimeError("Incomplete operational schema")
    return {"status": "schema_created", "tables": len(TABLES),
            "writes_enabled": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-reviewed-schema", action="store_true",
                        help="Explicitly create the four operational tables")
    args = parser.parse_args(argv)
    try:
        result = bootstrap(os.environ.get("MIGRATION_DATABASE_URL"),
                           confirm=args.apply_reviewed_schema)
    except Exception:
        print("Schema bootstrap refused or failed; no credentials disclosed.",
              file=sys.stderr)
        return 1
    print("Operational schema created: %d tables; application writes disabled."
          % result["tables"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
