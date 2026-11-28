# Milestone 8 — Reviewed operational schema bootstrap

Render PostgreSQL `ai-project-assistant-db` exists in Singapore and currently has zero public tables. This PR adds a **manual, opt-in** bootstrap of four existing schema definitions: `sheet_operations`, `project_write_gates`, `operation_audit_events`, and `recovery_reviews`. No production schema was modified by creating this PR.

## Before executing

1. Review the four imported DDL constants and their dependencies. This is the minimum read-only Operations API schema; it does not install optional bypass-guard triggers or approval-store tables.
2. Obtain explicit authorization for the one-time production schema change and a recovery/backup plan. Render Free PostgreSQL is temporary and has an expiration date.
3. Run the command only from a trusted operator environment with a separately stored `MIGRATION_DATABASE_URL` pointing to the intended database. **Never** use `READONLY_DATABASE_URL` for DDL, put the URL in a PR or paste it into chat.
4. Execute `py bootstrap_operational_schema.py --apply-reviewed-schema` once. The bootstrap refuses if any of its four tables already exist; it runs in a transaction and checks the target schema. On failure, inspect private PostgreSQL logs, not secrets.
5. Separately provision a least-privilege SELECT-only login with USAGE on schema `public` and SELECT on exactly these four tables. Do not use the database owner as the API read-only login. Have a database administrator review role membership, ownership, default privileges and connectivity.
6. On a trusted machine set `READONLY_DATABASE_URL` to the dedicated login, run `py postgres_readonly_readiness.py`, and require `status=pass`. Only then set that URL in the Render web service environment and rerun `py live_readonly_acceptance.py`; require Operations `pass`.

## Safety boundaries

The bootstrap performs schema DDL only after the explicit flag; it does not run on Flask startup, in CI or during deploy. It does not provision database users, seed records, perform Google Sheets writes or enable approval transitions. The schema may be empty; `/api/operations` should return an empty list once correctly configured. The legacy `postgres_bypass_guard.py` DDL is not installed by this bootstrap and needs separate review before any operational state mutation is considered.
