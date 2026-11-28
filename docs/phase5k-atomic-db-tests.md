# Phase 5K — real PostgreSQL tests for atomic coordination

This phase adds five opt-in integration tests for the Phase 5J atomic project coordinator.

Run only against a **dedicated disposable PostgreSQL database** with schema creation privileges:

```
python -m pip install "psycopg[binary]>=3,<4"
export RUN_POSTGRES_INTEGRATION_TESTS=1
export TEST_DATABASE_URL="postgresql://...disposable-test-db..."
python -m unittest -v test_atomic_coordinator_integration.py
```

The tests create and drop a randomly named schema. Interrupted tests may leave a schema requiring manual cleanup.

Covered: atomic start, gate exclusivity, persistent ambiguity lock, rollback on missing gate, concurrent start.

**Not covered:** live Render connection, schema migration, worker crash with external Sheets request in flight, authenticated reviewer identity, audit event insertion, verified release/fencing, or Google Sheets API mutations. Default CI skips these tests, so a green check does not establish that PostgreSQL tests ran. Production Sheets writes remain disabled.
