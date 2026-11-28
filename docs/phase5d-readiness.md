# Phase 5D deployment readiness (no production writes)

The PostgreSQL implementation in Phase 5C is not connected to Flask or Google Sheets. This phase adds an optional, read-only diagnostic and unit tests only.

## Required before any production write integration
1. Provision a durable PostgreSQL instance, backup policy, and least-privilege application role. Keep the database URL in Render secrets, never GitHub.
2. Apply schema migrations with a separate migration role; do not grant the runtime role DDL permissions. Review the schema in `approval_store_postgres.py` before applying migrations.
3. Run database diagnostics using a trusted operator environment, not a public endpoint. The diagnostic reports only reachability and table presence.
4. Run actual PostgreSQL integration tests including concurrent consumption, rollback on audit insert failure, and restart persistence.
5. Implement authenticated reviewer identity and role authorization; the existing shared API key does not establish individual human identity.
6. Implement serialized Google Sheets updates and durable operation states with reconciliation for ambiguous partial failures. A PostgreSQL transaction does not atomically commit a Google Sheets API call.
7. Harden audit storage to append-only with restricted roles and external retention.
8. Keep `SHEETS_WRITES_ENABLED=false` and Google Sheets read-only scope until explicit security review and release authorization.

## Optional diagnostic command
Install `psycopg[binary]>=3,<4` in an isolated operator environment, set `DATABASE_URL` securely, and run:

```python
from postgres_diagnostics import check_database
print(check_database())
```

This does not initialize tables or modify database rows. It is not an application health endpoint.
