# Milestone 2 — Application workflow integration: read-only operations

This milestone integrates the existing PostgreSQL operation/audit/recovery models into the running Flask application's **read-only visibility layer**, without enabling state changes or Google Sheets writes.

## Endpoints

- `GET /api/operations?project_id=...&limit=50`: bounded listing of operation state, project ID, recovery lock flag and whether a recovery review exists.
- `GET /api/operations/<uuid>`: operation state, bounded audit event types/timestamps and recovery review decision/timestamp. Actor IDs, raw evidence, credentials and connection details are not returned.

Both routes require the existing `X-API-Key: PROJECT_API_KEY` and return `Cache-Control: no-store`. The existing shared API key is **not** human reviewer identity; these endpoints expose no reviewer actions. Failure responses do not expose DB errors.

## Deployment configuration

Configure `READONLY_DATABASE_URL` only after the database has the reviewed schema and a dedicated **SELECT-only PostgreSQL role**. This variable is separate from `DATABASE_URL`; never reuse migration/owner credentials. If absent, both new endpoints return 503. The query explicitly executes `SET TRANSACTION READ ONLY` as a defense-in-depth measure.

The optional runtime PostgreSQL driver `psycopg[binary]>=3,<4` is added to requirements. No migration or connection to the production database is performed in this PR.

## Tests

- HTTP boundary tests for authentication, missing DB configuration, error masking and no-store.
- Disposable PostgreSQL tests for operation listing, audit visibility, recovery state and no mutation.
- GitHub Actions PostgreSQL workflow includes the new integration test module.

## Scope limitations

No authenticated human review route, approval consumption, safe gate release, success transition, worker fencing, Google Sheets mutation or production write authorization is added. Database trigger migration from Phase 5Q and security integrity migrations remain **opt-in and unexecuted**. Any existing Render deployment must be checked separately.

The next milestone is integrated testing, deployment readiness, and controlled **read-only** Render verification. Production write activation requires separate explicit authorization and safeguards.
