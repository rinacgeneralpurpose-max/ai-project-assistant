# Milestone 5 — Authenticated read-only functional acceptance

## Scope

The existing production smoke workflow verifies public health and that unauthenticated calls are rejected. This milestone adds a separate **synthetic authenticated functional test suite** covering the existing Flask API. It does not connect to live Google Sheets, PostgreSQL or Render and does not assert that production data has been validated.

## Automated contract checks

- Correct and incorrect API keys on project, dashboard, activity and operation endpoints.
- Fail-closed behavior if the API key is missing.
- Project records and pagination; dashboard aggregates; activity project filtering.
- Operation listing and explicit `writes_enabled=false`.
- `Cache-Control: no-store` on successful data responses.
- Generic error responses without database or Google credential details.
- Invalid pagination rejection and rejection of POST on read-only data routes.

Run `python -m unittest -v test_authenticated_readonly_acceptance`. The GitHub Actions workflow runs on PR, main and manual dispatch.

## Live acceptance — separate operator verification

1. Confirm GitHub main commit matches Render's live deployment SHA.
2. Confirm Production Read-Only Acceptance Smoke passes.
3. In a trusted private operator environment, make authenticated GET requests to `/api/projects?limit=1`, `/api/dashboard`, and `/api/activities?limit=1`. Use `X-API-Key` from a secret manager; never paste keys in public workflow logs, PR comments, or chat.
4. Validate expected JSON structure, 200 responses and `Cache-Control: no-store`; compare representative values with the source Google Sheet.
5. If `READONLY_DATABASE_URL` is intentionally not configured, `/api/operations` should return 503; do not treat this as a failure of Sheets endpoints. Before enabling it, verify the PostgreSQL role is SELECT-only and schema is reviewed.
6. If a private authenticated request fails, inspect sanitized Render logs and environment variable presence, not secret values. Do not add an unauthenticated debug endpoint.

## Acceptance boundaries

Passing the new workflow demonstrates **mocked API contract correctness**, not live data integration. Production Sheets write scopes, database mutation endpoints, review approvals, gate release and reconciliation transitions remain disabled. Live end-to-end acceptance must be documented separately.
