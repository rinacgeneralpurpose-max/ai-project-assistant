# Milestone 1 — Consolidated backend security readiness

This is a **milestone PR**, not another production-write feature. It combines database migration preflight diagnostics, integrity safeguards and real-PostgreSQL test coverage.

## Deliverables

1. `migration_readiness.py`: read-only, aggregate-only checks for required tables, missing project gates, missing start/reconciliation audit events, missing trusted operation requester links, orphan gates and duplicate audit events. A zero-count result means **ready for human migration review**, not safe for production writes.
2. `postgres_integrity_guards.py`: separately reviewable, optional PostgreSQL migration DDL that prevents UPDATE/DELETE of audit events, requester mappings and recovery reviews. This is not tamper-proof against database owners; production runtime roles must be restricted.
3. Two opt-in real PostgreSQL test modules, now registered in the disposable PostgreSQL GitHub Actions CI job. They cover migration preflight findings, historical unsafe states, protected audit/requester records and protected recovery reviews.

## Required pre-deployment work

- Inspect existing production schema and data **read-only** with a least-privilege role. This PR does not connect to Render PostgreSQL.
- Confirm PostgreSQL version, schema ownership, role grants, migration order and trigger interactions. A privileged role can bypass/drop triggers.
- Rehearse migrations on a disposable snapshot; verify rollbacks and any historical records that lack trustworthy provenance. Do not fabricate missing audit history or requester identities.
- Keep legacy coordinator entry points inaccessible from any write-capable runtime.
- Verify actual OIDC identity and server-side reviewer allowlists before exposing recovery review endpoints.
- Define and test a Sheets request-fencing protocol before implementing successful write completion or project-gate release.
- Keep read-only Sheets scopes and `writes_enabled=false` until explicit security approval.

## Testing

GitHub Actions `PostgreSQL Integration Tests` runs the new modules with PostgreSQL 16 and `RUN_POSTGRES_INTEGRATION_TESTS=1`. These tests are not run against production and do not exercise Google Sheets or live OIDC. CI must be green and reviewed before merge.

## Next milestones

**Milestone 2:** application workflow integration (read-only operational visibility first, then authenticated approval/recovery surfaces; no write activation).

**Milestone 3:** integrated testing, Render deployment validation and controlled non-production verification. Production write activation is a separate explicit decision, not implied by merging code.
