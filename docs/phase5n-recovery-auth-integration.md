# Phase 5N — Recovery identity verification and disposable-DB tests

## Scope

This branch adds an **isolated** recovery workflow that validates a Google OIDC **ID token** (signature, expiry and client audience via google-auth), confirms a Google issuer and verified account, and authorizes by a **server-managed allowlist of Google subject IDs** (the stable `sub` claim). It does not trust the token's claimed roles.

The workflow reads the requester's subject from the new `operation_requesters` database table rather than accepting a requester ID in the recovery request. It uses the existing Phase 5M recovery review store to record only `hold` or `escalate` decisions. **It cannot release a gate or call Google Sheets.**

## Deployment prerequisites (not implemented)

1. Register and configure an appropriate Google OIDC client and securely provide its exact audience. Do not treat `PROJECT_API_KEY` as human identity.
2. Maintain a trusted, server-side allowlist of Google `sub` identifiers authorized for independent recovery review. Subject strings are not emails.
3. Populate `operation_requesters` **atomically from a verified requester identity** when a future operation is originally created. The current repository does not yet do this.
4. Migrate `operation_requesters` with a separate database migration role. Prevent the runtime role from modifying existing requester mappings or audit history.
5. Protect any future authenticated endpoint with appropriate rate limits, session/CSRF protections if browser-based, secure logging, and least-privilege database access. This branch adds **no endpoint**.
6. Establish an append-only audit policy and reconciliation/fencing protocol before implementing a gate-release mechanism. A Sheet snapshot does not prove a previously submitted request has stopped.
7. Continue to use read-only Google Sheets credentials. Production writes must stay disabled.

## Tests

Offline tests in `test_authenticated_recovery_workflow.py` use a stub identity-token verifier and mocked DB; they **do not prove live Google token verification**.

The additional integration tests in `test_recovery_workflow_integration.py` run only when all of the following are true:

- A disposable PostgreSQL database has been provisioned; never use the Render production database.
- `TEST_DATABASE_URL` points to that disposable database and allows schema creation.
- `RUN_POSTGRES_INTEGRATION_TESTS=1`.
- `psycopg[binary]>=3,<4` is installed in the test environment.

Then run `python -m unittest -v test_recovery_workflow_integration.py`.

These tests create a randomly named schema and attempt to drop it after execution. On interruption, clean up orphaned test schemas manually. They check recovery persistence, duplicate review rejection, database-derived self-review denial, rollback on review insertion failure, and concurrent review uniqueness.

**Default GitHub Actions CI skips integration tests. Green CI does not demonstrate successful real PostgreSQL or live OIDC verification.** No production database credentials are configured or used by this branch.

## Remaining security gap

Phase 5N still cannot establish that an earlier Google Sheets HTTP request has stopped. A recovery review records investigation and keeps the gate locked; it is **not** permission to retry or release the lock. PostgreSQL coordination and Google Sheets writes are not a single atomic transaction.
