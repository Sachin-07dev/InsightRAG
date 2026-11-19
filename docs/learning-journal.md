# Learning journal

## 2026-11-16: Phase 1 design package

The owner moved this chat into `D:\projects\RAG` and asked to repeat Phase 1 as repository work. Inspection found an empty directory, no Git repository and no applicable ancestor/project instructions. Design documents now preserve the project direction without building application code. Saving them does not approve architecture decisions.

Verification: documentation consistency passed and all 10 validation-tool tests passed. Fourteen deliverables, 21 PRD requirements, eleven proposed ADRs and twenty-six tasks are mapped. Application quality/security/load/recovery tests and visual Mermaid rendering have not run. See the [actual verification record](testing/verification.md).

## Concepts to be able to explain

- RAG retrieves indexed evidence; it does not train an LLM on uploaded files.
- Retrieval quality, factual support and numerical correctness are separate properties.
- Tenant isolation extends to caches, worker messages, checkpoints, exports, telemetry and restore.
- RBAC determines permitted operations; resource grants determine permitted content.
- Metric semantics are versioned business contracts, not just SQL expressions.
- Read-only analytical intent does not establish safe execution.
- Stable versions, atomic publication, idempotency and fencing solve different failure cases.
- Checkpoints and broker acknowledgements do not imply exactly-once external effects.
- Raw vector size is not total database/storage size; organization count is not workload.
- SLO/RPO/RTO proposals need measured validation and a declared workload envelope.

## Phase 2 authorization and learning

The owner explicitly authorized repository/backend/infrastructure implementation after reviewing the Phase 1 direction. The foundation now has FastAPI contracts/lifespan, bounded async pools, separate migration/runtime credentials, safe server/application logging, JSON Celery diagnostics, local Compose, Next.js and CI. See [Phase 2](phase-02.md), [backend internals](concepts/phase-02-backend.md), [interview exercises](interview/phase-02.md) and [actual verification](testing/phase-02-verification.md).

Key distinctions: process liveness versus dependency readiness; event-loop concurrency versus CPU parallelism; engine versus request session; immutable dependency resolution versus vulnerability assurance; eager task tests versus broker round trips; CI definition versus an executed hosted run. A sanitized HTTP error does not automatically sanitize the server's re-raised exception logs.

Phase 2 understanding check: Why can live pass while ready fails? Why must concurrent requests not share AsyncSession? Why must migrations use a different process/role?

## Phase 2 pre-review housekeeping

The owner asked for a clearer folder structure before the next phase. Inspection found useful source boundaries rather than redundant applications. Cleanup removed eleven tool/bytecode cache directories and four generated scratch files, while [workspace settings](../.vscode/settings.json) hide retained dependencies, generated builds, environments, secrets and scratch state from Explorer. The [folder guide](operations/repository-layout.md) explains each boundary and the [Windows Docker guide](operations/docker-windows.md) covers installation and the detected Windows support issue.

What/why: generated local state can obscure a small monorepo; removing source boundaries or required learning documents would not solve that problem. How/implementation: retain package manifests and locks, preserve Next.js routing conventions, validate exact cleanup paths, remove only reviewed disposable outputs, and use shared Explorer exclusions. Production: hiding a folder is not access control; deleting ignored files can destroy credentials or database state. Improvement: create new feature/shared-package folders only when implemented responsibilities justify them.

Verification: documentation consistency, all 13 Node documentation/bootstrap tests, frontend formatting/lint/TypeScript and all three frontend helper tests passed. No backend behavior changed. Docker installation, container builds, live service integration and hosted CI remain unverified; no Phase 3 work started. See the [actual record](testing/phase-02-verification.md) for scope and limits and the [folder guide](operations/repository-layout.md) for five interview questions with model answers.

Housekeeping understanding check: Which directories are source versus generated local state? Why must this machine retain `work/python/`? Which remaining checks require a working Docker engine?

## Still-open production policy decisions

Launch region/data restrictions, first workflow, row/column entitlement needs, metric ownership, retention/hold authority, provider approval and workload targets remain pending. See [review gate](architecture/review.md). Do not replace these with implicit production defaults.

## Understanding check

1. Why must a sales comparison use deterministic analytics even if reports mention the numbers?
2. Why must a saved chart be reauthorized when reopened?
3. Which combination of tombstones, lifecycle checks and fencing stops a stale worker publishing deleted content?

Record the owner's answers and corrections after review; no answers or approvals have been fabricated.

## Phase 3 implementation and learning

The owner explicitly authorized enterprise security and tenant isolation. See the [phase guide](phase-03.md), [security module](modules/security-foundation.md), [teaching](concepts/phase-03-security.md), [runbook](operations/phase-03-security.md), [interview practice](interview/phase-03.md) and [actual verification](testing/phase-03-verification.md).

Key lessons: authentication proves identity, current authorization grants data access; a caller-selected organization is not a credential; roles, explicit resource ACLs and attributes intersect; RLS supplements trusted application checks without sandboxing arbitrary service-role SQL; transaction-local settings prevent pool contamination; a queue signature does not replace fresh permission checks. Immediate tombstoning and completed erasure are separate outcomes. Managed-key interfaces, protocol adapters and local regressions are not deployed cloud controls or certification.

The real PostgreSQL tests found that a locking SELECT also encounters UPDATE policy restrictions: an analyst could read org metadata but a direct FOR SHARE returned no row, producing a false stale-policy response. A narrow member-only lock helper preserves permission ordering without expanding general UPDATE privileges. Mutation routes now authorize before locking, then reauthorize under the lock to preserve uniform cross-company 404 responses. Review also aligned upload limits, separated quarantine metadata from active content, fenced grant bootstrap by SQL transaction identity and capped control-plane bodies before JSON parsing.

Still open: actual enterprise IdP/client configuration, multi-issuer lifecycle, approved regions and retention, cloud KMS/storage/TLS/IAM, independent audit export, live antivirus and parser sandboxing, controlled dispatch scheduling and backup/object-version erasure. Phase 4 remains gated on owner review. No answers or architecture approvals are fabricated.

Phase 3 understanding check: Why does a valid JWT plus organization header not establish document access? How do pooled sessions and retried jobs avoid retaining stale authority? Why can an access-blocking delete remain held or pending before full erasure?

## 2026-11-17: Phase 4 versioned ingestion

Phase 4 separated **source transport**, **durable acceptance**, **background computation**, and **published evidence**. A clean upload stores immutable bytes; a PostgreSQL job records acceptance; Celery requests execution at least once; `active_version` exposes only fully staged results. `latest_version` and organization policy revision are independent fences: one protects source ordering, the other current authority. A JWT and signed job envelope do not replace current resource grants and RLS. Token windows use a pinned offline BPE table and preserve real locators. Embeddings are similarity features, not facts; CSV/XLSX rows stay separate for future deterministic analytics. The 50 MiB cap, unverified cloud services, parser expansion, and missing outbox are explicit production gaps.

Review: Why can a worker compute every vector yet fail to publish? Why is OOXML validation insufficient without a parser sandbox? Which measurement would justify moving beyond PostgreSQL/pgvector or polling? See the [Phase 4 interview guide](interview/phase-04-ingestion.md) and [verification](testing/ingestion-tests.md).

## Phase 5 implementation and learning

The owner explicitly authorized permission-aware document RAG. The [phase guide](phase-05.md), [retrieval module](modules/retrieval/README.md), [algorithms](concepts/hybrid-retrieval-and-rrf.md), [security](security/retrieval-security.md), [API](api/rag.md), [failure matrix](operations/phase-05-failures.md), [evaluation](testing/retrieval-evaluation.md), and [interview bank](interview/phase-05-retrieval-and-generation.md) connect the code to its operating assumptions.

Key lessons: a valid token does not grant document read access; retrieval predicates and RLS must apply before candidate text leaves PostgreSQL; cosine distance and `ts_rank_cd` have different directions/scales; RRF combines ranks rather than pretending scores are calibrated; PostgreSQL `ts_rank_cd` is not BM25; a citation label/excerpt proves provenance, not logical support; every conversation turn needs current ACL/version checks; document RAG must hand exact numerical aggregates to a typed analytics engine. The synthetic four-case rank fixture is a deterministic teaching example, not a measured provider or production-quality benchmark.

Open decisions: approved model endpoints/residency, language analyzers, thresholds calibrated on a larger held-out corpus, semantic claim-level verification, conversation retention/purge, full stage tracing, local cross-encoder versus API reranking, streaming, and production load targets. ADR 014 remains proposed. No Phase 6 analytics or owner approval is implied.

Phase 5 understanding check: Why does SQL-side ACL filtering precede fusion? Why can a real citation still fail to support a claim? What changes when an embedding model is replaced?

## 2026-11-19: Phase 6 governed analytics

Review-remediation lesson: seven new tests reproduced misleading gross/net and monthly-growth answers before the planner began rejecting those unsupported meanings. An XLSX integration test exposed that spreadsheet date cells become midnight ISO datetimes; accepting only midnight preserves the business-date contract. A restricted-role SQL oracle now checks revenue and margin, while response provenance adds a source hash, bounded row locators and an explicitly *assumed* metric-definition version. A two-row EXPLAIN establishes query-plan execution, not production performance. The [review addendum](modules/analytics/PHASE_06_REVIEW_REPORT.md) keeps full enterprise BI readiness as NO-GO until business definitions and remaining verification are approved.

A further 10,000-row synthetic query demonstrated why a correct RLS policy can still be unusably slow: the original grant function was evaluated per fact row, producing 19.9–23.1-second SQL scans and a timeout. The revised policy uses an authorized transaction-local resource scope so PostgreSQL evaluates the grant once per query while still enforcing row entitlements and active version. The same local case completed in hundreds of milliseconds. Missing/wrong scope regression tests and the full real-service suite passed; this does not establish concurrent production capacity.

The owner explicitly authorized structured analytics. See the [phase guide](phase-06.md), [module](modules/analytics/README.md), [formulas](concepts/analytical-calculations.md), [security](security/analytics-security.md), [API](api/analytics.md), [operations](operations/phase-06-analytics.md), [tests](testing/analytics-tests.md) and [interview practice](interview/phase-06-analytics.md).

Key lessons: a JSON spreadsheet row is not a governed metric; declare event grain and validate typed decimals before publication. A correct SQL `SUM` over RLS-visible rows can be wrong if labelled “national.” A semantic layer defines formula, unit, scope and calendar, not only synonyms. Fixed server-generated SQL with bound values narrows injection risk; PostgreSQL RLS and current policy checks remain necessary. Aggregate margin uses totals, and a zero YoY baseline has no defined growth percentage. DuckDB can compare an already-authorized snapshot, but its current in-memory adapter is not a production connector or sandbox.

The isolated PostgreSQL run applied migration `0007_analytics` and passed 58 integration tests. It exposed a prepared-statement edge case: PostgreSQL cannot infer an untyped optional `NULL` bind when checking `:region IS NULL`. An explicit `CAST(:region AS text)` preserves parameter binding and makes the query executable through asyncpg. The regression also exercises partial-region denial for national contribution, complete-region authorization, cross-tenant isolation and tombstone exclusion.

Open decisions: business approval of signed-revenue/refund/profit definitions, currency rates, source timestamp semantics and completeness watermarks; metric-definition versioning; governed joins and connector policy; production DuckDB snapshot worker; load targets, chart integration and LLM explanation. ADR 015 remains proposed. No approval or production benchmark is implied.

Phase 6 understanding check: Why can a regional analyst's denominator be mislabelled national? Why is aggregate margin a ratio of sums? How do version and policy checks protect a query racing deletion or revocation?

## Phase 7 implementation and learning

The owner authorized LangGraph orchestration. [Phase guide](phase-07.md), [module README](modules/orchestration/README.md), [fundamentals](concepts/langgraph-fundamentals.md), [security](security/orchestration-security.md), [tests](testing/orchestration-tests.md), and [interview bank](interview/phase-07-langgraph.md) reference the actual graph and adapters. A finite `StateGraph` makes routing and termination visible, while the trusted Phase 5/6 services still own authorization. Typed state helps developers; Pydantic validates external contracts. Sequential hybrid execution avoids reducer races and permits a narrowly labeled analytics-only partial response on document-provider outage. A graph recursion ceiling is not a SQL timeout, and an in-memory checkpointer is not a safe production memory store. Chart points must inherit SQL authorization and provenance. The five synthetic graph traces are execution evidence for routing, not provider quality or financial approval.

Still open: owner-approved Phase 6 metric/FX rules, automatic hybrid decomposition evaluation, safe durable checkpoint lifecycle, provider-cost admission, exported distributed spans and representative concurrent p95 load. No Phase 8 features or owner approvals are inferred.

# Phase 8 learning note

Visualization is a presentation of authorized calculations, not a calculation authority. A typed request can contain filters and chart intent without containing data values. A dashboard with multiple SQL queries can mix dataset versions unless it fences them; equality of versions is still weaker than a single database snapshot. Chart coordinates use JavaScript floating-point numbers, so an exact decimal table should remain visible for financial review. A map, scatter or stacked chart requires the correct data shape and approved metric semantics; a chart library cannot create those facts. Current Phase 8 limitations and verification commands are in [the visualization module](./modules/visualization/README.md).

