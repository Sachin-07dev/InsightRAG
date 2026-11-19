# Technology selection matrix

Status: Proposed. Select exact supported versions and licenses during Phase 2; this is not a dependency lock. No paid service, provider account or cloud deployment has been configured.

| Area | Choice and fit | Viable alternatives | Tradeoff and evidence for change |
| --- | --- | --- | --- |
| Backend | Python/FastAPI/Pydantic: typed HTTP contracts next to parsing and ML ecosystem | Django, NestJS | Django fits admin-heavy products; CPU work must leave API event loop |
| Web | Next.js/React/TypeScript/Tailwind: typed enterprise UI/session boundary | React SPA, Angular | Extra server responsibility; SPA works if BFF/SSR provides no value |
| Persistence | PostgreSQL/SQLAlchemy/Alembic: transactions, relations, migrations and tenant policies | Other SQL platforms | ORM is not authorization; inspect SQL/RLS plans and migration behavior |
| Retrieval | PostgreSQL FTS/pgvector: lexical and semantic evidence in one governed core | OpenSearch, Qdrant, managed vector services | Selective ANN filters affect recall; split on measured quality/latency/operations needs |
| Analytics | Isolated DuckDB: snapshot-based analytical scans away from transactional load | PostgreSQL analytical schemas, ClickHouse, managed warehouse | Process isolation and dataset limits required; warehouses fit larger concurrent shared analytics |
| Data preparation | SQL first; bounded Pandas for non-SQL transforms; canonical Parquet snapshots | Polars/Arrow-native pipeline | Pandas can exhaust memory; do not load arbitrary datasets unbounded or run generated code |
| Orchestration | LangGraph, with selective LangChain adapters behind owned interfaces | Explicit Python state machine, Temporal | Explicit state/recovery is useful; more framework surface and upgrades to govern |
| Models | Application-owned OpenAI-compatible provider interface | Direct provider SDK, enterprise gateway | Compatibility needs conformance tests for schemas, tools, token usage, timeout and residency |
| Embeddings | Approved configurable embedding profile | Hosted/local providers | Choose dimensions/language/quality via evaluation; changing model creates a new index generation |
| Storage | Regional S3-compatible service, unique immutable source versions | Azure Blob, local filesystem for development | Portability requires semantic tests for versions, checksums, policy and retention |
| Jobs | Celery/Redis with durable PostgreSQL job registry and outbox | RabbitMQ, managed queues, Temporal | Assume duplicates/loss; broker is replaceable; retry correctness belongs to business effects |
| Charts | Apache ECharts with constrained typed specs | Plotly, Vega-Lite | Excellent business interactivity; Plotly is attractive for scientific plots |
| Reports | Constrained CSV/PDF templates over validated results | DOCX/XLSX export later | Browser/server renderers and formulas need hardening; avoid executable report content |
| Identity | Enterprise OIDC, existing approved IdP | Self-hosted IdP, SAML gateway | Avoid implementing passwords; SAML/SCIM follow customer requirements |
| Telemetry | OpenTelemetry instrumentation, approved metrics/logs/traces backend | Cloud-native telemetry | Self-host Prometheus/Grafana/Langfuse only if justified; content capture off by default |
| Tests | Pytest, Playwright and labeled RAG/metric fixtures | Other language/browser tools | Suites must measure behavior, not mirror code; model evaluation separate from deterministic tests |
| Runtime | Docker locally and managed containers initially | Kubernetes | Adopt Kubernetes only for scheduling/policy/scale/operator needs backed by evidence |
| IaC and CI | Terraform and GitHub Actions provisionally | Native cloud IaC, Azure DevOps | Match repository/cloud governance; no CI service is currently connected |

## How choices communicate

Pydantic-like contracts define HTTP/tool data; SQLAlchemy manages controlled persistence; domain services call repositories and provider/analytics interfaces. Celery messages carry trusted-job identifiers, not arbitrary execution instructions. Object storage is referenced by versioned metadata; vector/text retrieval joins to the authorization catalog. DuckDB execution receives authorized snapshots, not database-superuser access. React receives typed evidence/results and renders constrained charts.

## Why not deploy the entire preferred stack now?

Every extra stateful system adds backup, monitoring, patching, access policy and failure handling. PostgreSQL consolidation reduces initial consistency problems. Kubernetes, specialized search and warehouses remain evolution options; a design is defensible when the change trigger is explicit, not when it has the most technologies.

## Sensitive technical details

Use the primary [source register](sources.md). PostgreSQL role ownership, filtered pgvector recall, DuckDB capabilities and Celery retry semantics need explicit validation in the selected versions. Provider capability and retention settings cannot be inferred from protocol compatibility.
