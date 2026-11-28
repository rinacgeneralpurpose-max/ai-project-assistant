"""Read-only migration readiness checks for the consolidated backend security milestone.

Requires an existing PostgreSQL connection. No schema changes, external calls,
or Google Sheets write capabilities. Returns aggregate counts only.
"""
from dataclasses import dataclass


REQUIRED_TABLES = (
    "sheet_operations", "project_write_gates", "operation_audit_events",
    "recovery_reviews", "operation_requesters",
)

# Every query is a fixed string; never interpolate project IDs or schema names.
CHECKS = {
    "applying_without_gate": """
        SELECT count(*) FROM sheet_operations o
        LEFT JOIN project_write_gates g ON g.project_id=o.project_id
            AND g.operation_id=o.operation_id AND NOT g.recovery_required
        WHERE o.state='applying' AND g.project_id IS NULL
    """,
    "reconciliation_without_recovery_gate": """
        SELECT count(*) FROM sheet_operations o
        LEFT JOIN project_write_gates g ON g.project_id=o.project_id
            AND g.operation_id=o.operation_id AND g.recovery_required
        WHERE o.state='reconciliation_required' AND g.project_id IS NULL
    """,
    "applying_without_start_audit": """
        SELECT count(*) FROM sheet_operations o
        WHERE o.state IN ('applying','reconciliation_required','applied')
          AND NOT EXISTS (
            SELECT 1 FROM operation_audit_events a
            WHERE a.operation_id=o.operation_id AND a.event_type='operation_started'
          )
    """,
    "reconciliation_without_audit": """
        SELECT count(*) FROM sheet_operations o
        WHERE o.state='reconciliation_required'
          AND NOT EXISTS (
            SELECT 1 FROM operation_audit_events a
            WHERE a.operation_id=o.operation_id
              AND a.event_type='reconciliation_required'
          )
    """,
    "unmapped_operation_requesters": """
        SELECT count(*) FROM sheet_operations o
        LEFT JOIN operation_requesters r ON r.operation_id=o.operation_id
        WHERE r.operation_id IS NULL
    """,
    "gate_without_matching_operation": """
        SELECT count(*) FROM project_write_gates g
        LEFT JOIN sheet_operations o ON o.operation_id=g.operation_id
          AND o.project_id=g.project_id
        WHERE o.operation_id IS NULL
    """,
    "duplicate_start_audit_events": """
        SELECT count(*) FROM (
            SELECT operation_id FROM operation_audit_events
            WHERE event_type='operation_started'
            GROUP BY operation_id HAVING count(*) > 1
        ) duplicate_operations
    """,
    "duplicate_reconciliation_audit_events": """
        SELECT count(*) FROM (
            SELECT operation_id FROM operation_audit_events
            WHERE event_type='reconciliation_required'
            GROUP BY operation_id HAVING count(*) > 1
        ) duplicate_operations
    """,
}


@dataclass(frozen=True)
class MigrationReadiness:
    ready_for_review: bool
    missing_tables: tuple
    findings: dict

    def as_dict(self):
        return {
            "ready_for_review": self.ready_for_review,
            "missing_tables": list(self.missing_tables),
            "findings": dict(self.findings),
            "writes_enabled": False,
        }


def inspect_migration_readiness(connection):
    """Use an already-open read-only DB connection, with a fixed search_path.

    A zero-count report permits *human review*, not deployment or write access.
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT table_name FROM information_schema.tables
               WHERE table_schema=current_schema()
                 AND table_name = ANY(%s)""",
            (list(REQUIRED_TABLES),),
        )
        present = {row[0] for row in cur.fetchall()}
        missing = tuple(sorted(set(REQUIRED_TABLES) - present))
        if missing:
            return MigrationReadiness(False, missing, {})
        findings = {}
        for name, query in CHECKS.items():
            cur.execute(query)
            count = cur.fetchone()[0]
            if not isinstance(count, int) or count < 0:
                raise ValueError("Invalid migration readiness count")
            findings[name] = count
    return MigrationReadiness(not any(findings.values()), (), findings)
