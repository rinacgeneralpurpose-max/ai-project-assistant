"""Read-only PostgreSQL deployment diagnostics.

No Flask endpoint, migration, approval consumption or Google Sheets write.
Call explicitly from an operator environment with DATABASE_URL configured.
"""
import os


def check_database(*, connect=None, dsn=None):
    """Check DB reachability and existing approval tables without modifying state."""
    if dsn is None:
        dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        return {"status": "not_configured", "writes_enabled": False}
    if connect is None:
        import psycopg
        connect = psycopg.connect
    try:
        with connect(dsn, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION READ ONLY")
                cur.execute(
                    """SELECT to_regclass('public.approvals')::text,
                              to_regclass('public.approval_audit')::text"""
                )
                row = cur.fetchone()
        return {"status": "ready" if row == ("approvals", "approval_audit") else "schema_missing",
                "tables_present": bool(row == ("approvals", "approval_audit")),
                "writes_enabled": False}
    except Exception:
        # Avoid leaking DSNs, server names or database exception details.
        return {"status": "connection_failed", "writes_enabled": False}
