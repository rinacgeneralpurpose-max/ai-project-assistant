# Operational acceptance: live read-only API

## Verified from GitHub and Render

- GitHub main merge commit for PR #25: `60545aa263269b6e9ede649918e525df16fb5dd3`.
- Render latest live deployment: same commit. Deploy ID `dep-dc5c93h7lnhs73bfepkg`.
- The PR #25 feature-branch commit `38eff0f17d396f6fbdfb9519a8946ba87d280175` has successful Python Automated Tests and PostgreSQL Integration Tests workflow runs.
- Render build logs show successful package installation and gunicorn startup.

## Not yet verified

- A direct external HTTP response from the live `/health` endpoint could not be obtained from the current execution environment. Render's live deployment metadata does not substitute for HTTP acceptance.
- Live authenticated API reads have not been tested; do not place `PROJECT_API_KEY` in public workflows.
- PostgreSQL production schema and `READONLY_DATABASE_URL` are not verified; new operations routes may intentionally return 503 when not configured.
- No live Google Sheets write tests are authorized.

## Manual GitHub Actions smoke test

After merging this PR, run **Actions → Production Read-Only Acceptance Smoke → Run workflow**. It sends only unauthenticated GET requests to `/health`, `/api/projects`, `/api/dashboard`, `/api/activities` and `/api/operations`. It expects `/health` to return a healthy read-only JSON response and each API route to reject unauthenticated requests with 401 or 503. It sends no secrets, mutating requests or database connections.

A successful smoke test establishes only public health and basic authentication enforcement, **not** full authorized API functionality or production readiness for writes.

## Remaining acceptance gates

1. Confirm GitHub Actions Python and disposable PostgreSQL tests pass on the exact merged revision.
2. Execute the manual smoke workflow and inspect the result.
3. Verify authenticated read-only project/dashboard/activity responses using a trusted private operator environment; do not log the key.
4. Confirm a dedicated SELECT-only PostgreSQL role, schema readiness and `READONLY_DATABASE_URL` before enabling read-only operation visibility.
5. Keep Google Sheets write scopes and mutation endpoints disabled until a separately approved, tested write-safety design exists.
