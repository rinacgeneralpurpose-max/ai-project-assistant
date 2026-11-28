# Phase 5L — transactional operation audit prototype

This phase introduces an operation audit event table and an isolated coordinator that inserts an audit event **inside the same PostgreSQL transaction** as a gate acquisition and state transition. On an audit insertion error, the database transaction must roll back the gate and state updates.

Events currently supported: `operation_started` and `reconciliation_required`. No success/release/recovery-decision event exists yet.

## Remaining safeguards
- Apply reviewed schema migrations on a disposable DB first and run real PostgreSQL rollback tests; unit tests use mocks only.
- Use an authenticated server-side actor ID, never caller-supplied identities. This module validates only that an ID is nonblank.
- Enforce append-only audit storage using restricted DB privileges and external immutable retention. This schema alone is not tamper-proof.
- Connect the audited coordinator to the actual runtime only after removing unsafe alternate coordinator paths.
- Define verified recovery and a safe gate release path, and address late/in-flight Google Sheets requests.
- PostgreSQL transactions cannot atomically commit a Google Sheets API call.

No production database was modified and no Google Sheets writes are enabled.
