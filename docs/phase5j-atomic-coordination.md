# Phase 5J — atomic gate and operation transitions

This isolated prototype combines the Phase 5G operation state update and Phase 5I project gate acquisition in one PostgreSQL transaction. It also atomically records an ambiguous result in both tables while retaining the gate.

## What this addresses
- An operation cannot transition to `applying` through this coordinator unless it also acquires the project gate.
- If a second SQL statement fails, the surrounding PostgreSQL transaction rolls back the first.
- The project gate is retained on `reconciliation_required`; no release API is provided.

## Not production-ready
- Existing Phase 5G methods still exist and are not replaced or disabled. Any caller bypassing this new coordinator can evade the gate.
- No production database migration, live PostgreSQL concurrency test, authenticated operator recovery, or write endpoint is included.
- No external Sheets request is fenced by PostgreSQL. A late Sheets request remains possible even if the database reports a completed operation.
- The successful-operation path and audited gate release are not implemented.
- No immutable audit event is written for these transitions.
- Mock tests check SQL call flow, not PostgreSQL atomicity; real DB tests are required.

**Production Google Sheets writes remain disabled.**
