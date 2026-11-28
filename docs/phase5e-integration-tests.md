# Phase 5E: real PostgreSQL integration tests

These tests are **opt-in**, and must run only against a dedicated, disposable PostgreSQL test database. They do not configure or validate a live production database.

## Run

1. Provision a throwaway PostgreSQL database with permission to CREATE SCHEMA. Never use the production DATABASE_URL.
2. In a separate environment, install `psycopg[binary]>=3,<4`.
3. Set `TEST_DATABASE_URL` to that database and `RUN_POSTGRES_INTEGRATION_TESTS=1`.
4. Run `python -m unittest -v test_postgres_integration.py`.

Tests use a randomly named schema and delete it after the test class. If execution is interrupted, a test schema may remain and need manual cleanup.

Covered: single-use consumption and audit, payload tampering, transactional rollback on audit failure, concurrent consume race, persistence across connections.

Not covered: live Render database connectivity, backup/restore, crash recovery across Google Sheets writes, reviewer authentication, append-only audit privilege enforcement, or sheet update serialization. These must be completed before enabling writes. **Writes remain disabled.**
