"""Read-only operational visibility from PostgreSQL.

No schema changes, approval transitions, Google Sheets calls or writes.
Uses a dedicated read-only DB transaction and bounded query limits.
"""
import uuid


def _limit(value, default=50):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer") from None
    if not 1 <= number <= 100:
        raise ValueError("limit must be between 1 and 100")
    return number


def _project(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError("Invalid project_id")
    return value


def _connection(dsn, connect=None):
    if connect is None:
        import psycopg
        connect = psycopg.connect
    return connect(dsn, connect_timeout=5)


def list_operations(*, dsn, project_id=None, limit=50, connect=None):
    project_id = _project(project_id)
    limit = _limit(limit)
    if not isinstance(dsn, str) or not dsn:
        raise RuntimeError("Read-only database not configured")
    with _connection(dsn, connect) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """SELECT o.operation_id::text,o.project_id,o.state,
                          o.created_at,o.updated_at,
                          g.recovery_required,
                          EXISTS(SELECT 1 FROM recovery_reviews r
                                 WHERE r.operation_id=o.operation_id) AS reviewed
                   FROM sheet_operations o
                   LEFT JOIN project_write_gates g
                     ON g.operation_id=o.operation_id AND g.project_id=o.project_id
                   WHERE (%s::text IS NULL OR o.project_id=%s)
                   ORDER BY o.created_at DESC,o.operation_id DESC LIMIT %s""",
                (project_id, project_id, limit),
            )
            records = cur.fetchall()
    return {
        "operations": [
            {
                "operation_id": row[0], "project_id": row[1],
                "state": row[2], "created_at": row[3].isoformat(),
                "updated_at": row[4].isoformat(),
                "recovery_required": row[5] is True,
                "recovery_reviewed": row[6] is True,
            } for row in records
        ],
        "count": len(records), "writes_enabled": False,
    }


def operation_detail(*, dsn, operation_id, connect=None):
    try:
        operation_id = uuid.UUID(str(operation_id))
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Invalid operation_id") from None
    if not isinstance(dsn, str) or not dsn:
        raise RuntimeError("Read-only database not configured")
    with _connection(dsn, connect) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """SELECT o.operation_id::text,o.project_id,o.state,
                          g.recovery_required
                   FROM sheet_operations o LEFT JOIN project_write_gates g
                   ON g.project_id=o.project_id AND g.operation_id=o.operation_id
                   WHERE o.operation_id=%s""",
                (operation_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            cur.execute(
                """SELECT event_type,occurred_at
                   FROM operation_audit_events WHERE operation_id=%s
                   ORDER BY occurred_at DESC,event_id DESC LIMIT 100""",
                (operation_id,),
            )
            events = cur.fetchall()
            cur.execute(
                """SELECT decision,created_at
                   FROM recovery_reviews WHERE operation_id=%s LIMIT 1""",
                (operation_id,),
            )
            review = cur.fetchone()
    return {
        "operation_id": row[0], "project_id": row[1],
        "state": row[2], "recovery_required": row[3] is True,
        "audit_events": [
            {"event_type": event[0], "occurred_at": event[1].isoformat()}
            for event in events
        ],
        "recovery_review": None if review is None else {
            "decision": review[0], "created_at": review[1].isoformat()
        },
        "writes_enabled": False,
    }
