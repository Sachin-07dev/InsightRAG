# Phase 2 local execution and infrastructure

Phase 2 provides the engineering foundation, not a RAG engine or a production deployment. It creates no tenant data APIs or authentication implementation. Docker was unavailable during initial implementation; the owner has since installed it and follow-up checks confirmed a working Linux engine. See [CI](phase-02-ci.md) for automated runtime checks and [verification](../testing/phase-02-verification.md) for measured project results and remaining gaps.

## Prerequisites and first start

Use Node.js 24, uv 0.13.7, and Docker Engine/Desktop with Linux containers and modern Compose v2. Docker is required for the full local stack. uv installs the Python 3.12 interpreter for native backend work. Do not put private customer data into this foundation.

Windows users: follow the [Docker Desktop and WSL setup guide](docker-windows.md), including this machine's Windows 10 support caveat, before starting the stack.

From the repository root:

```powershell
node scripts/bootstrap-local.mjs
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
```

Bootstrap is idempotent: it generates random local credentials once and refuses inconsistent existing files. It creates nine files under ignored `.secrets/`; it does not create `.env` or `.env.local` and never prints credential values. Compose points settings at the secret files. No default password is stored in source.

Expected interfaces:

| Address | Purpose |
| --- | --- |
| http://localhost:3000 | Next.js foundation page |
| http://localhost:8000/health/live | Process liveness, independent of service availability |
| http://localhost:8000/health/ready | Database/schema and Redis dependency readiness |
| http://localhost:8000/api/v1/meta | Public platform version metadata, no tenant content |
| http://localhost:8000/docs | Development Swagger UI |
| http://localhost:8000/api/v1/openapi.json | Versioned OpenAPI schema in development |

On Windows, use `Invoke-RestMethod http://localhost:8000/health/ready` to inspect readiness. Expected success is HTTP 200 with ready dependency status; unavailable/unmigrated dependencies produce 503, not a misleading healthy result. Production configuration disables public interactive documentation/schema endpoints.

```powershell
docker compose ps
docker compose logs --tail 100 api worker migrate
docker compose exec -T worker celery -A insightrag.worker:celery_app inspect ping --timeout=5
docker compose exec -T api python -c "from insightrag.worker import celery_app; result = celery_app.send_task('insightrag.diagnostics.ping'); assert result.get(timeout=20) == {'status': 'ok'}"
docker compose down
```

`down` stops containers and keeps named data volumes. Never regenerate credentials while preserving an initialized database: PostgreSQL initialization scripts run only on a new empty volume. Rotation requires an explicit database/Redis credential update and synchronized secret-file change. Bootstrap is not a rotation command. Do not use destructive volume-reset commands against data you intend to retain.

## Services and important files

| File/service | What and why |
| --- | --- |
| `compose.yaml` | Local dependency graph, health checks, loopback ports, named volumes, per-service secrets |
| `infra/docker/backend.Dockerfile` | Locked production dependencies built with uv; final non-root API/worker/migration image |
| `apps/web/Dockerfile` | Next.js standalone frontend image, maintained with the frontend skeleton |
| `infra/postgres/init-runtime.sh` | Creates a non-owner, non-superuser, non-BYPASSRLS runtime role; revokes public schema CREATE; enables vector extension |
| `infra/redis/start.sh` | Reads password from secret file into restricted ephemeral configuration, then launches the official Redis entrypoint |
| `scripts/bootstrap-local.mjs` | Cryptographically random credentials, separate owner/runtime users, host/container URLs, no overwrite |
| `scripts/bootstrap-local.test.mjs` | Verifies credential creation, preservation, inconsistent-file rejection and malformed input |
| `.dockerignore` | Excludes secrets, env files, virtualenvs, caches, generated builds and scratch work from image contexts |
| `.gitignore` | Keeps credentials, environments, dependency/build/test caches out of version control |
| `.gitattributes` | Preserves LF for shell scripts so Linux container entrypoints remain executable after Windows checkout |

Postgres uses a persistent named volume and a digest-pinned pgvector/PostgreSQL 17 image. Redis uses a digest-pinned Redis 8.2 image with AOF persistence. Persistence is not a guarantee against all job loss or duplicate execution; durable business jobs/outbox arrive in Phase 4. The current Celery task is operator-only diagnostics with short-lived results.

`migrate` waits for PostgreSQL health and exits after Alembic succeeds. `api` and `worker` wait for healthy PostgreSQL/Redis and successful migration. API/worker run as UID 10001 with read-only root filesystem, temporary `/tmp`, dropped capabilities and no-new-privileges. Only the migration service receives owner credentials. The frontend waits for API readiness. Restart policies do not replace readiness or runtime retry handling.

## Container networking and secrets

Inside Compose, `postgres:5432` and `redis:6379` resolve by service name on the project network. `localhost` inside the API container is the API container itself. Host-native processes instead use `127.0.0.1`; bootstrap therefore creates separate `host_*_url` files. Published ports bind only to host loopback: 3000, 8000, 5432 and 6379. Development HTTP is not a production TLS policy.

Compose secrets are local bind-mounted files, not a vault or encrypted secret distribution service. On Unix, the bootstrap enforces `.secrets` directory mode 0700 and files 0644 so non-root container processes can read explicitly mounted files; the private parent directory blocks ordinary host traversal. Compose file-backed secret uid/mode remapping cannot be assumed. Windows relies on host ACLs: restrict the project/secret folder appropriately. Production needs an approved secret manager and access/rotation policy. Git ignore and Docker ignore prevent accidental inclusion; neither encrypts files.

## Native backend development with container dependencies

```powershell
node scripts/bootstrap-local.mjs
docker compose up -d --wait postgres redis
uv python install
uv sync --locked --all-packages --group dev
$env:INSIGHTRAG_ENVIRONMENT = 'development'
$env:INSIGHTRAG_DATABASE_URL_FILE = '.secrets/host_database_url'
$env:INSIGHTRAG_REDIS_URL_FILE = '.secrets/host_redis_url'
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE = '.secrets/host_migration_database_url'
uv run --package insightrag-api alembic -c apps/api/alembic.ini upgrade head
Remove-Item Env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE
uv run --package insightrag-api uvicorn insightrag.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

Remove the migration owner setting before launching long-running API/worker processes. In another terminal set the same runtime database/Redis file settings and start the diagnostic worker. Windows native Celery requires the development-only solo pool; use the Compose Linux worker for the production-like process model:

```powershell
$env:INSIGHTRAG_DATABASE_URL_FILE = '.secrets/host_database_url'
$env:INSIGHTRAG_REDIS_URL_FILE = '.secrets/host_redis_url'
uv run --package insightrag-api celery -A insightrag.worker:celery_app worker --loglevel=INFO --pool=solo --concurrency=1
```

For native web development:

```powershell
npm ci
npm run dev:web
```

Do not run the Compose API/web and native processes on the same host ports simultaneously. Host environment settings override file defaults; configure a direct URL or its `_FILE` setting, never both. Never print resolved settings or secret URLs for troubleshooting.

## Failures and production limits

Missing secrets -> run bootstrap; wrong existing credentials -> follow deliberate rotation, not overwrite. Busy ports -> stop the conflicting development process or review mappings. Migration failure -> inspect migration logs and connectivity before starting API. Ready 503 -> inspect named dependency states and schema revision. Worker connection failure -> verify Redis file configuration and host/container address. Image pull/build errors -> check approved network access and image availability.

Docker execution, image builds, live migrations, live readiness and Celery round trips require a working Docker runtime; consult the verification record for the exact checks performed. This setup has no HA, managed backups, SSO/RBAC/RLS tenant tables, TLS ingress, private-data storage, RAG or production deployment.

References: [Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/), [startup readiness](https://docs.docker.com/compose/how-tos/startup-order/), [uv Docker](https://docs.astral.sh/uv/guides/integration/docker/), [pgvector image tags](https://github.com/pgvector/pgvector#docker).
