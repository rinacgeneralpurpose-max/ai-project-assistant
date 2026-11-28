# Phase 5G — PostgreSQL operation coordination prototype

This module defines an isolated database-backed operation reservation and state transition layer. It is **not** connected to production, Flask, or Google Sheets.

## Guarantees provided by the schema
- `UNIQUE(project_id, approval_id)` prevents reserving the same approval twice.
- Partial unique index allows only one `applying` operation per project at a time.
- Conditional updates prevent replay from `applied` or `reconciliation_required`.

## Limitations requiring resolution
- The partial unique index causes a database uniqueness error if another operation is already applying; production code must handle this safely.
- If a worker crashes while `applying`, the row intentionally blocks new operations for that project until manual reconciliation. Do not reset it automatically.
- The database transaction does not make a Sheets API request atomic. Recovery must compare actual sheet state, expected value, and audit trail before any further attempt.
- This prototype does not verify approval signatures, reviewer identity, or a preflight result before reservation.
- The SQL schema has not been migrated to any database; it requires separate migration, real PostgreSQL concurrency tests, and audited privileges.
- No append-only event ledger or durable Sheets response receipt is yet implemented.

**Production Google Sheets writes remain disabled.**
