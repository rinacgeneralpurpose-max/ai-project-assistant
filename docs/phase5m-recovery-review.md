# Phase 5M — verified recovery review (fail closed)

The initial Phase 5M scope is **recovery evidence capture and reviewer decision logging**, not automatic gate release. An ambiguous Google Sheets API request can arrive late even after a database record indicates reconciliation is required. A sheet snapshot cannot prove that no request is in flight.

The `RecoveryReviewStore` records a single reviewed `hold` or `escalate` decision for a locked reconciliation operation, under a PostgreSQL transaction. It intentionally never releases `project_write_gates`, marks an operation applied, or calls Google Sheets.

## Prerequisites before a future release mechanism
- A verified authenticated reviewer identity and independent requestor identity, with enforced role separation.
- Authoritative sheet observation, timestamps, request identifiers, and an operator-confirmed absence of in-flight writes.
- A worker protocol with fencing/serialization sufficient to rule out late requests; PostgreSQL alone cannot fence the Sheets API.
- Audited recovery decision and gate release in one DB transaction, with authorization and idempotency.
- Real PostgreSQL tests including rollback and concurrent recovery attempts.
- Append-only audit retention and backups.

This is an isolated module: no migration applied, no Flask integration, and no production writes enabled. Actor strings passed to this module are **not authenticated** by the module itself.
