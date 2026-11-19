# Phase 3 security operations

Run from the repository root. Start with the [foundation setup](phase-02-local.md) for uv, Node, Docker and pool settings. The commands below are local development instructions, not an assertion that a production identity or cloud integration exists.

## Install and start services

```powershell
node scripts/bootstrap-local.mjs
uv sync --locked --all-packages
docker compose config --quiet
docker compose up -d --wait postgres redis
$env:INSIGHTRAG_DATABASE_URL_FILE='.secrets/host_database_url'
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE='.secrets/host_migration_database_url'
$env:INSIGHTRAG_REDIS_URL_FILE='.secrets/host_redis_url'
$env:INSIGHTRAG_SIGNED_JOB_KEY_FILE='.secrets/signed_job_key'
uv run --package insightrag-api alembic -c apps/api/alembic.ini upgrade head
```

Bootstrap now preserves/creates ten local credential files, including a separate unpredictable job-signing secret. It never rotates an existing password. The API/worker container gets runtime database, Redis and signing-key files; migration credentials remain in the migration process. Do not mount the whole secret directory into the API. Local Redis and DB endpoints bind loopback; these are not production TLS connections.

For the entire local skeleton: `docker compose up --build --wait`. Protected routes remain unavailable until enterprise identity is configured and provisioned. Readiness covers infrastructure/schema, not IdP onboarding; use protected-route checks to verify identity separately.

## Configure an actual authorization server

Register a confidential BFF or public PKCE client and an API audience in your enterprise identity provider. The frontend login/BFF callback is not implemented here. Obtain access tokens through your organization's approved flow; do not place client secrets in browser code, commit tokens, or use an ID token as this API's credential.

Set all three together using the real provider values:

```powershell
$env:INSIGHTRAG_OIDC_ISSUER='https://your-approved-issuer.example/tenant'
$env:INSIGHTRAG_OIDC_AUDIENCE='your-registered-api-audience'
$env:INSIGHTRAG_OIDC_JWKS_URL='https://your-approved-issuer.example/tenant/jwks'
```

These example domains are placeholders to replace, not working integrations. The [supported profile](../security/oidc-integration.md) requires RS256, `typ=at+jwt`, bounded lifetime and specified claims. Configure the provider appropriately or implement a reviewed issuer-specific adapter. Do not relax issuer/audience/algorithm checks to make an incompatible token pass. Compose passes these three variables to API/worker; native Uvicorn reads them from the environment. JWKS network failure is a controlled 503 when no usable cache exists.

## Privileged identity provisioning

Run only in an approved operator environment with separate migration credentials. Use the exact `iss` and `sub` from the real identity provider. Region and retention are business decisions; values below describe a synthetic local organization, not a production policy.

```powershell
uv run --package insightrag-api python -m insightrag.security.provision --issuer 'https://your-approved-issuer.example/tenant' --subject 'real-provider-subject' --organization 'Synthetic Company A' --region 'approved-local-region' --role admin --workspace 'Default' --retention-days 30
```

Output contains generated user/organization/workspace UUIDs, never credentials. To add a provisioned user to an existing organization, include `--organization-id <returned UUID>` and the desired approved role. Optional `--group <name>` creates membership in an organization-local group. `--clearance 0..3` applies only to a newly created identity; adding a membership does not silently raise existing clearance. Organization membership and group provisioning are operator integrations, not self-service APIs. The operator role can bypass database policies and requires tightly scoped IAM, deployment separation, change review and independent audit.

Unset `INSIGHTRAG_MIGRATION_DATABASE_URL_FILE` before launching the API or worker; they must not inherit operator credentials. Use a separate terminal/process for provisioning in production.

## Run and inspect protected requests

```powershell
uv run --package insightrag-api uvicorn insightrag.main:app --reload --no-access-log
```

In an authorized client, supply a real access token in the Authorization header and the provisioned organization UUID in X-Organization-ID. GET `/api/v1/me` should return the current DB role/revision. A different organization's UUID must fail. See [API boundaries](../api/phase-03-security.md) for supported routes. Do not paste real tokens into issues or this repository. Native development allows local HTTP; production rejects protected HTTP requests and requires correctly configured trusted TLS termination/proxy handling.

## Scanner and quarantine

Set `INSIGHTRAG_CLAMAV_HOST` and optionally `INSIGHTRAG_CLAMAV_PORT` only to an operator-controlled scanner. No scanner is started or claimed by the default Compose file. Missing scanner returns 503 for validation. The raw upload body is limited to a configurable maximum no greater than 50 MiB, using X-Filename and Content-Type. A successful scan returns file hash/size and stored:false/published:false. No document bytes are persisted by this endpoint. Runtime cannot promote a quarantined resource to active; safe publication belongs to the next ingestion phase.

Other request bodies have a fixed 16 KiB ASGI cap before JSON parsing, including missing/misleading Content-Length and non-JSON content. Edge ingress still must cap headers/connections, enforce read timeouts and bound concurrent uploads; a byte budget does not stop slow-client exhaustion by itself.

## Cleanup jobs

A DELETE request tombstones access and atomically creates a durable cleanup job. Start the worker with runtime-only credentials and a signing key:

```powershell
uv run --package insightrag-api celery -A insightrag.worker:celery_app worker --loglevel=INFO --pool=solo
```

The solo pool supports local Windows development; production uses a suitable Linux worker pool. Trusted operator dispatch reads an existing job through RLS and sends a short-lived signed token:

```powershell
uv run --package insightrag-api python -m insightrag.security.jobs --organization-id '<UUID>' --actor-id '<UUID>' --job-id '<UUID>'
```

The UUID values are mandatory arguments to replace. The CLI prints a task ID without printing the token. The queued identity is not a replacement for current authorization. A policy revision change denies old work. A failed consumed nonce needs a new dispatch token after investigation; never replay or extend a captured token. Completion is idempotent; held/legal-retention jobs require approved controlled re-enqueue after hold/deadline resolution. There is no automatic outbox dispatcher/scheduler yet, so un-dispatched jobs remain durably queued and visible to their requester.

State meanings: completed means guarded database content cleanup succeeded; held means legal hold or future retention; denied means current policy does not authorize work; pending_storage means an object key exists but no storage adapter can assert deletion. Tombstones/audit remain; backups/object versions need separate provider retention controls. Never equate a 202 delete response with complete secure erasure.

## Production controls and incident response

Before deployment: TLS for ingress/DB/Redis/scanner paths; restricted trusted proxies; managed secrets/rotation; cloud KMS implementation; encrypted volumes/snapshots; tenant/workload IAM; network egress rules; managed PostgreSQL helper-role bootstrap; live antivirus/signature updates; parser sandboxing; edge IP and concurrency quotas; regional routing and replica/backup placement; independent immutable audit export; tested backup restore and deletion expiry. See [control detail](../security/controls-and-cloud.md) and [threat model](../security/phase-03-threat-model.md).

On suspected leakage, revoke current DB membership/grants, incremented revisions invalidate old work, disable affected integrations, preserve operator/audit evidence and investigate scoped request IDs without exposing payloads. Rotate compromised service/signing keys through a coordinated plan and drain old jobs; automatic online key rotation is not implemented. Monitor 401/403/404/409/429/503 rates, policy lock waits, queue age, JWKS/Redis/scanner failures, purge results and pool saturation. Tenant-facing logs/traces require an authorized export boundary; the existing sanitized global logs are operator-only.
