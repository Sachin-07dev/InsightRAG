# Phase 2 continuous integration and dependency control

The workflow is implemented in `.github/workflows/ci.yml`. It has not been executed on GitHub in this session; no remote repository or hosted run is claimed. Local verification and its limits are recorded in the [Phase 2 results](../testing/phase-02-verification.md).

## What CI does

| Job | Checks and purpose |
| --- | --- |
| Documentation | Phase 1 consistency and all Node documentation/bootstrap tests |
| Backend | Locked uv environment; Ruff lint/format; strict mypy; isolated unit tests; real PostgreSQL/Redis integration; Python advisory audit |
| Frontend | `npm ci`; ESLint; formatting; TypeScript; public-origin tests; Next.js production build; npm high/critical advisory gate |
| Containers | Build both images; boot complete Compose stack; check liveness/readiness/meta/OpenAPI/web and worker control plus actual diagnostic task/result |

All jobs have bounded timeouts, read-only repository permissions and concurrency cancellation. They use immutable SHA references for checkout, setup-node and setup-uv. Those refs were resolved from official release tags on 2026-11-16. uv is fixed to 0.13.7 and Node major 24. Dependency updates should be reviewed and rerun through the same checks; a lockfile does not establish that packages are vulnerability-free.

## Backend sequence and exact commands

```powershell
uv python install
uv sync --locked --all-packages --group dev
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run --package insightrag-api pytest
```

Default pytest excludes tests marked integration; those tests are not counted as a real database pass. The backend CI job starts actual Compose PostgreSQL and Redis, runs migrations with a scoped owner URL, then executes integration explicitly with runtime-role and dependency URLs. On PowerShell locally:

```powershell
node scripts/bootstrap-local.mjs
docker compose up -d --wait postgres redis
$env:INSIGHTRAG_DATABASE_URL_FILE = '.secrets/host_database_url'
$env:INSIGHTRAG_REDIS_URL_FILE = '.secrets/host_redis_url'
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE = '.secrets/host_migration_database_url'
uv run --package insightrag-api alembic -c apps/api/alembic.ini upgrade head
Remove-Item Env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE
$env:INSIGHTRAG_TEST_DATABASE_URL_FILE = '.secrets/host_database_url'
$env:INSIGHTRAG_TEST_REDIS_URL_FILE = '.secrets/host_redis_url'
$env:INSIGHTRAG_TEST_MIGRATION_DATABASE_URL_FILE = '.secrets/host_migration_database_url'
uv run --package insightrag-api pytest -m integration
```

CI environment variables are scoped to steps; migration credentials do not become normal API environment. Integration tests are allowed elevated credentials only for their explicitly isolated migration checks. No tenant data is involved. Production rollout must not run destructive migration tests against its live database.

The Python audit exports all workspace runtime dependencies from `uv.lock`, omits unpublished workspace project entries, and asks pip-audit to evaluate the pinned dependency set:

```powershell
New-Item -ItemType Directory -Force work | Out-Null
uv export --locked --all-packages --no-dev --no-emit-workspace --format requirements-txt --output-file work/requirements-audit.txt
uv run pip-audit --strict --requirement work/requirements-audit.txt --no-deps --disable-pip
```

The advisory service needs network access. A failed network request is not a clean audit. The runtime audit excludes developer tools; maintain and review those separately. No advisory exceptions are silently ignored. CI should fail when a known dependency vulnerability is detected; assess and fix/update rather than run blanket forced upgrades.

## Frontend and container commands

```powershell
npm ci
npm run lint:web
npm run format:check:web
npm run typecheck:web
npm run test:web
npm run build:web
npm audit --audit-level=high
```

`npm ci` fails inconsistent package/lock files and installs the locked tree. Build verifies the actual production bundle and generated types. Three public-origin tests verify the configuration boundary; browser/user-flow tests are added with behavior in later phases. Low/moderate advisory findings remain reviewable even when the high/critical gate passes.

Container checks run only after other jobs pass. Bootstrap creates fresh random throwaway credentials. Compose waits for actual dependency health and successful one-shot migration. HTTP checks exercise public foundation endpoints; `inspect ping` checks worker control, and submitting `insightrag.diagnostics.ping` plus retrieving its typed result proves broker/worker/backend dispatch. The diagnostic is not the future durable business-job API. Services stop in an `always()` cleanup step; failure logs are limited to application/migration/web services and should remain redacted.

## Locking, images and remaining CD work

`uv.lock` and `package-lock.json` pin dependency resolution; CI refuses drift rather than silently rewriting locks. PostgreSQL/pgvector and Redis Compose images include registry-verified content digests. Registry metadata verification confirms tag/digest existence, not that an image builds or runs correctly on this machine. Python/uv/frontend base image tags remain explicit version-family tags and should be digest-pinned through the release-image update process before production. Include container-image scanning/provenance in that process.

This workflow is CI, not automatic production deployment. CD must later add approved infrastructure, environment secrets, release artifacts, image scanning/signing policy, backward-compatible migrations, deployment readiness, rollback gates and recovery evidence. No workflow publishes a site, pushes an image, creates a cloud environment or deploys on approval merely by existing.

References: [uv GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/), [pip-audit](https://github.com/pypa/pip-audit), [npm ci](https://docs.npmjs.com/cli/v11/commands/npm-ci), [npm audit](https://docs.npmjs.com/cli/v11/commands/npm-audit).
