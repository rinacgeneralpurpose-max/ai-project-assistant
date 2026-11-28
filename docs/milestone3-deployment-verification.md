# Milestone 3 — Deployment readiness and controlled verification

## Observed deployment drift

At the start of this milestone, the Render service `srv-dc57k149v7es739gf5i0` reported its most recent live deployment as commit `08d514c504101148dcad14a5960596fd62b34e01` (merged PR #4). GitHub main had already merged PR #24. Therefore a live service alone **does not prove the latest code was deployed**. Render service reports `autoDeploy=yes`, but the observed deployment history was stale.

## Acceptance gates

1. GitHub Python and disposable PostgreSQL CI pass for the exact candidate SHA.
2. Render build and deploy finish with status `live` **and the Render deployment commit SHA equals the reviewed main SHA**. No short-SHA comparison.
3. Public `GET /health` returns 200, `service=ai-project-assistant`, `status=ok` and `writes_enabled=false`.
4. Existing read-only endpoints are checked with authorized credentials, without exposing keys in logs. New operation endpoints should return 503 if `READONLY_DATABASE_URL` is absent; this is expected and not a deployment failure.
5. A dedicated SELECT-only PostgreSQL role and reviewed schema are prerequisites before setting `READONLY_DATABASE_URL`. Do not use a migration/owner role.
6. Review deployment logs for errors without publishing credentials or sensitive data. No production Sheets writes or schema migrations.

## Implemented automated checks

`deployment_verification.py` checks revision equality and read-only health semantics. `test_deployment_verification.py` tests those conditions offline. The checks do not trigger a deploy or claim to verify Render without actual metadata. No secrets, database URLs or Google Sheets API permissions are added.

## Next operational action

After CI passes, explicitly deploy the reviewed main commit through the existing Render service, then compare the Render deployed commit to main and verify health. If the deployment does not track main, investigate the Render GitHub integration rather than treating an older live deployment as success.
