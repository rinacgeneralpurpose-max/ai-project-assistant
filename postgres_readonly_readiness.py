"""Private, non-mutating PostgreSQL readiness checks.

Checks SELECT-only role grants, transaction read-only enforcement and the
schema used by operations_readonly.py. No DDL, DML, or credentials printed.
"""
import json
import os
import sys

REQUIRED_COLUMNS = {
    "sheet_operations": {"operation_id", "project_id", "state",
                         "created_at", "updated_at"},
    "project_write_gates": {"project_id", "operation_id", "recovery_required"},
    "operation_audit_events": {"operation_id", "event_id", "event_type",
                               "occurred_at"},
    "recovery_reviews": {"operation_id", "decision", "created_at"},
}


def assess(dsn, connect=None):
    if not dsn:
        return {"status": "not_configured", "writes_enabled": False}
    if connect is None:
        import psycopg
        connect = psycopg.connect
    checks = {}
    try:
        with connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute("SHOW transaction_read_only")
                checks["transaction_read_only"] = cur.fetchone()[0] == "on"
                cur.execute("""SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
                                      rolreplication
                               FROM pg_roles WHERE rolname=current_user""")
                role = cur.fetchone()
                checks["least_privilege_role"] = bool(
                    role and role[0] and not any(role[1:]))
                cur.execute("""SELECT table_name, column_name
                               FROM information_schema.columns
                               WHERE table_schema=current_schema()
                                 AND table_name=ANY(%s)""",
                            (list(REQUIRED_COLUMNS),))
                actual = {}
                for table, column in cur.fetchall():
                    actual.setdefault(table, set()).add(column)
                checks["required_schema"] = all(
                    required.issubset(actual.get(table, set()))
                    for table, required in REQUIRED_COLUMNS.items())
                cur.execute("""SELECT table_name,
                                      has_table_privilege(current_user,
                                          format('%I.%I', current_schema(),table_name),
                                          'SELECT'),
                                      has_table_privilege(current_user,
                                          format('%I.%I', current_schema(),table_name),
                                          'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                               FROM information_schema.tables
                               WHERE table_schema=current_schema()
                                 AND table_name=ANY(%s)""",
                            (list(REQUIRED_COLUMNS),))
                privileges = {name: (select, mutation)
                              for name, select, mutation in cur.fetchall()}
                checks["select_grants"] = all(
                    privileges.get(table, (False, True))[0]
                    for table in REQUIRED_COLUMNS)
                checks["no_mutation_grants"] = all(
                    not privileges.get(table, (False, True))[1]
                    for table in REQUIRED_COLUMNS)
    except Exception:
        return {"status": "fail", "checks": checks, "writes_enabled": False}
    return {"status": "pass" if all(checks.values()) else "fail",
            "checks": checks, "writes_enabled": False}


if __name__ == "__main__":
    report = assess(os.environ.get("READONLY_DATABASE_URL"))
    print(json.dumps(report, sort_keys=True))
    sys.exit(0 if report["status"] == "pass" else 1)
