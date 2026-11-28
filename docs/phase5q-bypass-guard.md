# Phase 5Q — database-level legacy coordinator bypass guard

This branch provides an **opt-in migration prototype** with PostgreSQL deferred constraint triggers on `sheet_operations`. It is **not applied to production**.

For state changes into `applying`, a matching non-recovery project gate and an `operation_started` audit event must exist at transaction commit. For `reconciliation_required`, a matching recovery gate and audit event must exist. All new transitions to `applied` are denied pending a separately designed, audited success/release protocol and external Google Sheets request fencing.

The deferred triggers permit the Phase 5L audited coordinator to create gate, state change and audit event within one transaction. Legacy `PostgresOperationCoordinator.begin()` and `record_result()` cannot commit unaudited transitions once the migration is applied. The Python legacy methods still exist for compatibility with earlier isolated prototypes; this is a database enforcement layer, not removal of those methods.

Seven new real-PostgreSQL tests check legacy begin rejection, missing audit rejection, permitted audited start and ambiguity, blocked success, and recovery rollback. The disposable PostgreSQL CI workflow executes this test module.

**Migration prerequisites:** review trigger syntax on the target PostgreSQL version, inventory existing states and missing audit rows, plan backfill without fabricating history, ensure restricted migration/DB roles, review concurrency and lock behavior, and run a rehearsal on a disposable snapshot. Do not install the guard without these checks. Database owners or privileged roles can alter/drop triggers; this is not protection against a compromised migration role.

**Still not production ready:** Google Sheets HTTP requests cannot be fenced by PostgreSQL triggers, authenticated worker identity is not connected, real audit append-only privileges are not enforced, no safe success release exists, and no production writes are enabled.
