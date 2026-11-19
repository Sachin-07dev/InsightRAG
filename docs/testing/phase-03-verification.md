# Phase 3 verification record

Date: 2026-11-17. Environment: Windows host, locked Python 3.12 workspace, Docker Desktop Linux engine, real PostgreSQL 17/pgvector and authenticated Redis. Synthetic independent organizations and generated RSA test keys only. This is local regression evidence, not production assurance or compliance certification.

## Scope and isolation of test infrastructure

The existing Phase 2 check services/volumes were preserved. Phase 3 uses the separate Compose project `insightrag-phase3`, isolated data volumes and loopback host ports 25432/26379 because the default host PostgreSQL port was unavailable. An ignored generated Compose configuration in the work directory changes only the test ports; ignored secret URL files point to these services without printing credentials. Secrets remain out of source control.

## Executed checks

| Final check | Observed result |
| --- | --- |
| Default complete pytest suite | **205 passed**, 51 integration tests deselected; 108.11 seconds |
| Complete real-service integration suite after final migration replay | **51 passed**, 205 unit tests deselected; 206.74 seconds |
| Ruff | All checks passed |
| Ruff formatting | 114 files already formatted |
| mypy | Success, 28 source files |
| OpenAPI export | Development schema regenerated, including bearer contracts and shared 413 response |
| Documentation/bootstrap Node suite | **14 passed** |
| Documentation consistency | No errors; local links, original 14 deliverables/21 requirements/11 proposed ADRs and Mermaid declaration checks passed |
| Local secret bootstrap | Ten files ready, existing credentials preserved; no values printed |
| Compose configuration | Validated successfully with the security signing secret and SSO environment mappings |
| Migration replay | Successful downgrade to 0001 then upgrade to final head on asserted isolated port 25432 |
| Real Uvicorn HTTP smoke | Passed with exit 0 in the ordinary sandbox, including live/ready/meta/OpenAPI/echo/auth boundary, process shutdown and temporary-directory cleanup |

The 51 integration cases comprise 24 RLS, 19 signed-token API/worker scenarios, three operator-provisioning cases, four foundation DB/Redis/readiness/migration checks and one real Redis control test. Synthetic organizations, actual RSA signature verification and restricted runtime DB/Redis are used. Tests cover cross-company metadata/evidence/rows/jobs/mutations, row-filtered exact aggregation, vector/keyword isolation, ABAC, revision invalidation, grant bootstrap/publication fences, retention/holds, replay/idempotency and accurate pending-storage behavior. Worker coroutine effects are exercised against real services; a new security task broker-to-Celery-process delivery test was not performed in this phase.

The 205 unit cases include authentication, control adapters, all protected authentication gates, 21 pre-parse body-cap cases and independent review regressions. Earlier focused runs are subsets, not additional totals. ClamAV protocol uses a bounded local test server; no live antivirus signature service or real enterprise IdP was configured.

Warnings: upstream Starlette/httpx TestClient deprecation; integration also reports Alembic's existing path-separator deprecation. These did not fail the runs. Dependency locks were updated and installed successfully; no fresh local network vulnerability scan or hosted CI run is claimed.

## Exact repeatable commands

From the repository root after installing locked dependencies:

```powershell
uv sync --locked --all-packages
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run --package insightrag-api pytest
uv run --package insightrag-api python scripts/smoke-api.py
uv run --package insightrag-api python scripts/export-openapi.py
node scripts/validate-phase1.mjs
node --test scripts/*.test.mjs
```

For default Compose ports after running bootstrap and starting PostgreSQL/Redis:

```powershell
$env:INSIGHTRAG_DATABASE_URL_FILE='.secrets/host_database_url'
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE='.secrets/host_migration_database_url'
$env:INSIGHTRAG_REDIS_URL_FILE='.secrets/host_redis_url'
uv run --package insightrag-api alembic -c apps/api/alembic.ini upgrade head
$env:INSIGHTRAG_TEST_DATABASE_URL_FILE='.secrets/host_database_url'
$env:INSIGHTRAG_TEST_MIGRATION_DATABASE_URL_FILE='.secrets/host_migration_database_url'
$env:INSIGHTRAG_TEST_REDIS_URL_FILE='.secrets/host_redis_url'
uv run --package insightrag-api pytest -m integration
```

The actual isolated host run substitutes the generated phase3-prefixed secret URL files for the three host-prefixed URL files. Do not print their contents. Unit tests intentionally exclude the integration marker by default; a skipped or deselected test does not count as passed. CI selects integration explicitly with real services and required secret configuration.

Exact replay on this existing workstation, using its retained ignored port-override configuration and secret URL files:

```powershell
docker --context desktop-linux compose --project-directory . -f work/phase3-compose.json -p insightrag-phase3 up -d --wait postgres redis
$env:INSIGHTRAG_DATABASE_URL_FILE='.secrets/phase3_database_url'
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE='.secrets/phase3_migration_database_url'
$env:INSIGHTRAG_REDIS_URL_FILE='.secrets/phase3_redis_url'
uv run --package insightrag-api alembic -c apps/api/alembic.ini upgrade head
$env:INSIGHTRAG_TEST_DATABASE_URL_FILE='.secrets/phase3_database_url'
$env:INSIGHTRAG_TEST_MIGRATION_DATABASE_URL_FILE='.secrets/phase3_migration_database_url'
$env:INSIGHTRAG_TEST_REDIS_URL_FILE='.secrets/phase3_redis_url'
uv run --package insightrag-api pytest -m integration
docker --context desktop-linux compose --project-directory . -f work/phase3-compose.json -p insightrag-phase3 stop postgres redis
```

The ignored configuration is local test state, not a source artifact expected in a fresh clone. New installations use the default-port setup above or supply their own reviewed port override and matching host secret URLs. At handoff the isolated Phase 3 services are stopped and their volumes retained; the existing Phase 2 project/volumes were not stopped or removed.

## Defects found and corrected

- Upload configuration allowed 100 MiB while the validator supports 50 MiB. Clamped configuration to the supported maximum; regression rejects unsupported values rather than allowing runtime 500.
- Resource sharing lookup incorrectly depended on directory visibility. Added a bounded same-org active-member eligibility helper without opening the membership directory.
- Mutation revision tracking could adopt an unrelated concurrent change. Added a preflight organization lock/baseline check before security mutations.
- Quarantine metadata was inaccessible through an active-content read guard. Added metadata-specific authorization while retaining active-only content access.
- Real PostgreSQL showed a direct SELECT FOR SHARE was filtered by the org UPDATE policy for readers, causing false 409 responses. Replaced it with a narrow active-member-only revision-lock helper and tested analyst/viewer/steward behavior.
- Bounded numeric Content-Length parsing avoids unbounded integer conversion on malformed headers.
- Added a 16 KiB pre-parse body cap independent of Content-Type and declared length, retaining exact authorized upload streaming.
- Mutations now authorize before taking the writer lock, then reauthorize under the lock. This preserves safe 404 denial for an analyst requesting another company's resource while retaining race protection.
- Windows venv launcher shutdown left its real Uvicorn child alive during scratch cleanup. The smoke harness now launches the actual locked Windows CPython process while preserving venv discovery, owns the correct PID and emits PASS only after process/directory cleanup. Final smoke succeeds without process-tree enumeration or taskkill.

## Limits of the evidence

No real enterprise IdP tenant/client, browser login, cloud KMS, cloud storage, live antivirus deployment, managed cloud PostgreSQL bootstrap, production TLS, cross-region routing, immutable audit collector, backup-erasure certification or hosted CI run was performed. The frontend is unchanged by this phase. No production RAG quality, ANN recall, analytics throughput, load/availability, penetration-test or compliance claim follows from these tests.

The initial API integration attempt found real authorization-lock defects; those failures are preserved here as part of the verification history rather than described as passing. The host also showed transient service timeouts under concurrent load. A real Redis readiness ping in the integration fixture warms its connection without bypassing quota execution. The final sequential complete integration run passed with production timeout defaults unchanged. Initial HTTP smoke checks passed but process cleanup failed; after the ownership correction, the final complete smoke passed with exit 0 inside the ordinary sandbox.
