# Milestone 6 — Private live read-only data acceptance

GitHub PR #27 CI checks (Python, PostgreSQL and authenticated contract) passed, and Render's latest live SHA matches GitHub main (`7b5314a878352c427fc6d2b709553805a33ca666`). These checks do not establish that the production Google Sheet is readable.

## Private operator execution

From a trusted machine with the repository checked out, inject `PROJECT_API_KEY` using a private secret manager or secure local environment, then run:

```bash
python live_readonly_acceptance.py
```

The script sends authenticated GET requests to the deployed HTTPS service, checks Projects, Dashboard and Activities response shape and `no-store` caching, and optionally checks Operations. It outputs only pass/fail status per endpoint, never records, keys or response bodies. Operations returning 503 with `status=unavailable` is recorded as `not_configured` and is acceptable until the SELECT-only PostgreSQL role is deployed. Other failures fail the run.

**Do not store `PROJECT_API_KEY` in GitHub Actions secrets for an unreviewed workflow, PR text, repository files, terminal transcripts or chat.** This script deliberately has no production GitHub Actions workflow.

## Acceptance criteria and limitations

- All three Google Sheets-backed endpoints must return authenticated 200 responses with expected data structures and `Cache-Control: no-store`.
- Compare at least one Project ID, total project count and representative Activity History entry against the source Sheet privately. The script validates response structure, not the truth of the underlying data.
- A zero-project response may be structurally valid but should be investigated if real projects exist.
- PostgreSQL operation visibility remains optional until schema and least-privilege credentials are reviewed.
- No write permissions, approval state transitions, production schema changes or recovery actions are introduced.
