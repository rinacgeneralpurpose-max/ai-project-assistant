# Phase 5I — fail-closed project recovery gate prototype

This phase addresses a specific Phase 5H design gap: changing an operation to `reconciliation_required` previously freed the partial-index `applying` slot, permitting another operation to begin while an external Sheets request might still be in flight.

The new `project_write_gates` table provides a separate project-keyed gate. The gate is **not automatically released** on ambiguity, timeout, process restart, or `reconciliation_required`. The prototype intentionally does not expose a release method.

## Critical limitations
- The gate is NOT wired into the Phase 5G coordinator, Flask, PostgreSQL production, or Google Sheets. Existing coordinator behavior is unchanged.
- Gate acquisition and operation transition must ultimately occur in the **same database transaction**; otherwise a crash can leave inconsistent state.
- Before release, a separately authenticated operator must verify that the previous external request is no longer in flight, inspect authoritative Sheet values, and record a durable audit decision. Checking Sheet values alone cannot prove an in-flight request has stopped.
- Without a cooperating Sheets worker/fencing mechanism, a late external request can still land after recovery. The gate is a fail-closed design component, not a complete distributed fencing guarantee.
- Successful completion also needs a separately audited, atomic release procedure. No release mechanism is implemented here.
- Migrations and real PostgreSQL concurrency tests are pending. No production database is touched.

**Google Sheets production writes remain disabled.**
