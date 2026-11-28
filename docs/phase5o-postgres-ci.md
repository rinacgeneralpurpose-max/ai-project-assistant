# Phase 5O — PostgreSQL tests in GitHub Actions

The dedicated `PostgreSQL Integration Tests` workflow starts a **disposable PostgreSQL 16 service container** inside GitHub Actions and runs the four opt-in test modules with `RUN_POSTGRES_INTEGRATION_TESTS=1`.

The test credentials are non-production values defined only for the disposable CI container. Do **not** replace `TEST_DATABASE_URL` with Render's `DATABASE_URL`. The workflow does not deploy, create any production resources, enable Sheets write scopes, or invoke Google Sheets.

## What this changes

Previously, default CI skipped the opt-in PostgreSQL integration suites, so a green Python test job could not prove the PostgreSQL tests had run. The new job explicitly runs the real database tests on pull requests, main pushes, and manual dispatch.

## Required verification

- Inspect the workflow run and ensure all four test modules actually execute and pass. **Creating this workflow does not mean the tests passed.**
- Investigate failures in the database test harness or coordinator implementation; do not mark tests green by disabling or skipping them.
- Keep recovery gates locked until a separate verified and audited release/fencing design is implemented.
- OIDC verification against a live provider and production database connectivity are outside this CI scope.

Production Google Sheets writes remain disabled.
