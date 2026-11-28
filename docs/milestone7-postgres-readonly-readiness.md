# Milestone 7 — PostgreSQL read-only readiness

The Milestone 6 private live API test passed for Projects, Dashboard and Activities; Operations reported `not_configured`. This milestone adds an **offline-testable private PostgreSQL readiness assessment**, not a database provisioning or migration action.

## Run privately

Provision a dedicated PostgreSQL login with SELECT-only access to the operational tables and their schema. Configure `READONLY_DATABASE_URL` privately on a trusted operator workstation; do not paste credentials into chat, PRs, Actions or terminal transcripts.

```powershell
py postgres_readonly_readiness.py
```

Output contains only booleans for transaction read-only mode, role capabilities, required columns, SELECT privileges and absence of mutation privileges on the four operational tables. A missing DSN returns `not_configured`. The command never executes DDL or DML.

## Schema and permissions expected

- `sheet_operations`: operation_id, project_id, state, created_at, updated_at
- `project_write_gates`: project_id, operation_id, recovery_required
- `operation_audit_events`: operation_id, event_id, event_type, occurred_at
- `recovery_reviews`: operation_id, decision, created_at

The role must not be a superuser, have CREATEDB/CREATEROLE/REPLICATION, or have INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER privileges on these tables. The assessment tests effective privileges on the named tables, **not** every database object, ownership, membership inheritance or the server-wide security configuration. A production security review remains necessary. A transaction set read-only is not proof that the login cannot write in a different transaction.

Run `python -m unittest -v test_postgres_readonly_readiness` without a database. Once a dedicated read-only role passes private review, configure `READONLY_DATABASE_URL` in Render and re-run `live_readonly_acceptance.py` from a private environment. Operations should change from `not_configured` to `pass`. If schema is absent, perform a separate reviewed migration using a distinct migration role; never use the API's read-only role for migrations.

No production credentials, role grants, schema migrations, Google Sheets writes or operational state transitions are introduced by this PR.
