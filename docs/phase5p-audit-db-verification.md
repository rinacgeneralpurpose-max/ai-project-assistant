# Phase 5P — Audited coordinator real PostgreSQL verification

Adds six opt-in tests of the Phase 5L audited atomic coordinator against a disposable PostgreSQL 16 database, using an isolated schema. The GitHub Actions PostgreSQL integration job now runs this fifth module alongside the previous four.

Coverage:
- Atomic start persists the gate, operation state, and audit event.
- Ambiguous outcome persists the recovery lock and both audit events.
- Forced audit insert failure rolls back gate acquisition and state transition.
- Forced ambiguity-audit failure rolls back the recovery flag and operation state.
- A second operation cannot bypass the held gate or insert an audit event.
- A missing gate prevents ambiguous transition and audit insertion.

These are **database transaction tests**, not tests of real Google Sheets or identity provider calls. No migration, Flask endpoint, production database connection, gate release, or write permission is added.

**CI must complete successfully before merge.** Existing legacy coordinator methods still bypass the new gate/audit path and must be retired or protected before production write enablement. No worker fencing or late-request prevention exists for the external Google Sheets API.
