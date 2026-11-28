# Phase 5F: authorization and write coordination policy

This change introduces **pure offline policy functions only**. No authentication provider, PostgreSQL coordination table, lock, Sheets mutation, or Flask write route is wired up.

- Reviewer identity must originate from a verified authentication system; caller-provided subject or roles are not trusted.
- A reviewer must be authenticated, hold `project_update_reviewer`, and differ from the requester.
- The operation state machine prevents replay from terminal states and automatic retry after an ambiguous Sheets outcome.
- A request sent to Google Sheets without confirmed success is `reconciliation_required`; an operator must compare authoritative Sheet state before marking applied or rejected.
- `(project_id, approval_id)` identifies an operation logically, but this Python tuple is **not** a database uniqueness constraint or distributed lock.

Before enabling writes, implement server-side session/identity verification, DB-backed unique operation records, per-project serialization, durable state transitions and audit, recovery runbook, and Google Sheets compare-before-write with concurrency safeguards. The Sheets API and PostgreSQL are not one atomic transaction. Keep all production Sheets writes disabled.
