# InsightRAG Enterprise

An enterprise knowledge and business intelligence platform design. Documents are retrieved with citations; structured data is analyzed by deterministic, restricted tools. Uploading content does not train or fine-tune the language model.

**Current phase:** Phase 6, governed structured sales analytics. Exact decimal aggregates run against authorized, versioned PostgreSQL rows through a bounded semantic plan; an offline DuckDB adapter compares validated samples. Browser SSO, connectors, charts and cloud deployment remain later work. No compliance certification or production deployment is claimed.

Start with the [Phase 6 guide](docs/phase-06.md), [analytics learning resource](docs/modules/analytics/README.md), and [verification](docs/testing/analytics-tests.md). The [Phase 5 retrieval guide](docs/phase-05.md), [Phase 4 ingestion guide](docs/phase-04.md), [Phase 3 security guide](docs/phase-03.md), [Phase 2 foundation](docs/phase-02.md), and [Phase 1 design](docs/phase-01.md) remain available.

## Repository layout

```text
RAG/
|-- apps/
|   |-- api/           # FastAPI, worker, migrations and backend tests
|   `-- web/           # Next.js application and frontend tests
|-- docs/              # Design, concepts, security, operations and learning
|-- infra/             # Container build and PostgreSQL/Redis setup
|-- scripts/           # Local bootstrap and verification commands
|-- .github/           # CI workflow
|-- .vscode/           # Shared Explorer settings
|-- compose.yaml       # Full local service stack
|-- pyproject.toml     # Python workspace and check configuration
|-- uv.lock            # Exact Python dependency versions
|-- package.json       # npm workspace and root commands
`-- package-lock.json  # Exact JavaScript dependency versions
```

Generated files and local dependencies are hidden in VS Code by [workspace settings](.vscode/settings.json); they remain on disk where required. See the [folder guide](docs/operations/repository-layout.md) for the backend/web structure, what can be regenerated, and what must be preserved. Root workspace configuration and required documentation stay in their existing locations.

## Run the local foundation

Requires Docker with modern Compose and Node.js 24. Docker Desktop and its Linux engine are now installed on this machine; see [actual verification](docs/testing/phase-02-verification.md) for project runtime results. The [Windows installation guide](docs/operations/docker-windows.md) remains available for setup and the Windows support boundary. Docker is optional for frontend development and backend unit tests. From this directory:

```powershell
node scripts/bootstrap-local.mjs
docker compose config --quiet
docker compose up --build --wait
```

Intended local addresses: web [localhost:3000](http://localhost:3000), API docs [localhost:8000/docs](http://localhost:8000/docs), readiness [localhost:8000/health/ready](http://localhost:8000/health/ready). These links do not imply the services are currently running. Consult verification before treating container behavior as established.

Native development and exact migration/worker commands are in the local runbook. Python is locked by `uv.lock`; JavaScript by `package-lock.json`. `apps/api` is the installable Python package, `apps/web` the npm workspace, `infra/` the local process/role boundary and `.github/workflows/ci.yml` the CI definition.

Protected APIs require a real enterprise authorization-server configuration and operator-provisioned issuer/subject membership. Missing identity, quota or scanner controls fail closed. See the [Phase 3 security runbook](docs/operations/phase-03-security.md); the frontend remains the foundation skeleton and does not yet implement browser login.

## Documentation map

| Area | Purpose |
| --- | --- |
| [Project instructions](docs/project-instructions.md) | Persistent product, engineering, teaching, and phase expectations |
| [Phase 6 implementation](docs/phase-06.md) | Governed sales projection, bounded SQL analytics and review boundaries |
| [Phase 6 learning guide](docs/modules/analytics/README.md) | Metrics, calendars, calculations, authorization and operations |
| [Phase 6 verification](docs/testing/analytics-tests.md) | Executed and pending correctness/security checks |
| [Phase 5 implementation](docs/phase-05.md) | Scoped hybrid retrieval, grounded generation and review boundaries |
| [Phase 5 learning guide](docs/modules/retrieval/README.md) | Ranking, context, citations, conversations and operations |
| [Phase 5 evaluation](docs/testing/retrieval-evaluation.md) | Executed checks versus unverified provider/load experiments |
| [Phase 4 implementation](docs/phase-04.md) | Bounded versioned ingestion, architecture and review |
| [Phase 4 learning guide](docs/modules/ingestion/README.md) | Parsing, jobs, tokens, vectors, security and operations |
| [Phase 4 verification](docs/testing/ingestion-tests.md) | Actual parser, unit, PostgreSQL isolation and deletion checks |
| [Phase 3 security](docs/phase-03.md) | Identity, RLS and protected resource foundation |
| [C4 diagrams](docs/architecture/c4.md) | Context, container, and component boundaries |
| [Data flows](docs/architecture/data-flows.md) | Ingestion, Q&A, analytics, charts, updates, deletion |
| [Data model](docs/architecture/data-model.md) | Entities, tenant keys, constraints, indexes, lifecycle |
| [Capacity and objectives](docs/architecture/capacity-and-slos.md) | Explicit assumptions, calculations, SLOs, recovery targets |
| [Technology choices](docs/architecture/technology-selection.md) | Alternatives, tradeoffs, change triggers |
| [ADRs](docs/architecture/decisions/README.md) | Proposed architectural decisions |
| [Security](docs/security/authorization.md) | Permissions and isolation contracts |
| [Threat model](docs/security/threat-model.md) | Attack surfaces and required controls |
| [Governance](docs/security/residency-retention-deletion.md) | Residency, retention, erasure, compliance discovery |
| [API boundaries](docs/api/boundaries.md) | Proposed external and internal contracts |
| [Module guide](docs/modules/README.md) | What, why, how, implementation, production, improvements |
| [Acceptance plan](docs/testing/acceptance-plan.md) | Future functional, quality, integration, security gates |
| [Verification](docs/testing/verification.md) | Actual documentation checks and their limits |
| [Backlog](docs/backlog.md) | Dependency-ordered, bounded implementation steps |
| [Interview practice](docs/interview/phase-01.md) | Architecture defense and debugging exercises |
| [Learning journal](docs/learning-journal.md) | Concepts, assumptions, and review questions |
| [Sources](docs/architecture/sources.md) | Primary documentation behind sensitive technical choices |

## Validate the foundation

With uv 0.13.7, Python 3.12 and Node.js 24:

```powershell
uv sync --locked --all-packages
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run --package insightrag-api pytest
uv run --package insightrag-api python scripts/smoke-api.py
npm ci
npm run lint:web
npm run format:check:web
npm run typecheck:web
npm run test:web
npm run build:web
```

Real-service tests, audits, CI/CD boundaries and failure handling: [CI guide](docs/operations/phase-02-ci.md). Generated development OpenAPI is [checked in](docs/api/openapi.json); regenerate with `uv run --package insightrag-api python scripts/export-openapi.py`. Production disables interactive schema/diagnostic routes.

## Validate the historical design package

Requires Node.js 22 or newer. No npm installation or API credentials are required.

```powershell
node scripts/validate-phase1.mjs
node --test scripts/validate-phase1.test.mjs
```

These checks validate documentation consistency. They do not test application security, retrieval quality, performance, or disaster recovery. See [verification](docs/testing/verification.md) for the actual run record.
