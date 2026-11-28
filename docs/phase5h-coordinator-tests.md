# Phase 5H: operation coordinator database integration tests

This is an opt-in test suite for a **dedicated disposable PostgreSQL database**. It does not use Render production credentials, migrate production tables, or invoke Google Sheets.

Run with `psycopg[binary]>=3,<4`, `TEST_DATABASE_URL` and `RUN_POSTGRES_INTEGRATION_TESTS=1`:

```
python -m unittest -v test_operation_coordinator_integration.py
```

Tests create a random schema and attempt to remove it afterward. They verify duplicate reservations, partial unique index enforcement, concurrent project operations, state persistence across connections, and prevention of replay after ambiguous results.

**Known limitations:** The test suite intentionally documents that a second operation can begin once the first enters `reconciliation_required`. This is not sufficient to guarantee correct ordering if the first Google Sheets call is still in flight. Production needs a project-level fencing/lease protocol and reconciliation gate before allowing any subsequent operation. No Sheets writes are enabled. CI normally skips these tests without an explicit test database; a green CI badge is not proof they ran.
