# Architecture overview

Status: Proposed. Architecture style: modular backend with independently scalable worker processes and regional data placement.

## Boundaries

The API owns identity enforcement, catalog operations, bounded query orchestration, evidence contracts, and response validation. Ingestion, heavy analytics, and exports run outside API processes. PostgreSQL stores relational state, full-text indexes, and vector representations initially. Object storage holds immutable sources, canonical dataset snapshots, and generated artifacts. Redis is a broker/disposable cache, never the only record of accepted work.

## Components and purpose

| Component | Responsibility | Tradeoff |
| --- | --- | --- |
| Next.js/React web | Workspace/upload/chat/dashboard/admin UI and secure session boundary | Server hop improves token handling; session/CSRF controls remain necessary |
| Identity/policy | Trusted user context, memberships, role capability, resource grants | Shared policy needs enforcement at every downstream boundary |
| Catalog | Resources, versions, lifecycle and active publication | Coordinates stores that cannot share a transaction |
| Ingestion | Scan, parse, OCR, normalize, chunk, embed, publish | Async readiness and partial failure must be visible |
| Retrieval | Authorized lexical/vector candidates, fusion and rerank | Quality/latency tuning needs realistic filter selectivity |
| Analytics | Resolve metrics, validate plans, execute limited deterministic computations | Constrained expressiveness preserves meaning and safety |
| Orchestration | Route, clarify, collect evidence, compose, validate | Graph state adds explicit control and recovery complexity |
| Evidence | Pin sources/results, associate claims and dependencies | Storage and lineage costs enable reproducibility and revocation |
| Visualization/export | Validate chart specs, render accessible UI, generate safe files | Limited vocabulary is easier to secure than executable chart code |
| Jobs/outbox | Durable intent, dispatch, retry, leases, fencing, reconciliation | More bookkeeping avoids silent task loss and duplicate effects |
| Model gateway | Provider profiles, budgets, timeouts, capability checks | Protocol similarity does not establish behavioral equivalence |
| Observability | Correlate latency/errors/usage without raw content by default | Telemetry itself is a governed data store |

See [C4](c4.md) for process boundaries and [modules](../modules/README.md) for teaching details.

## Data and trust invariants

1. No content leaves storage for reranking/model use before authorization.
2. No answer, export, or source download releases newly unauthorized evidence.
3. Retrieval relevance does not establish numerical or causal truth.
4. Every computed value pins metric and dataset versions, filters, units, and time semantics.
5. Document/model content cannot define credentials, policy, arbitrary SQL, Python, object paths, or outbound destinations.
6. New versions publish atomically. Tombstones and fencing prevent resurrection.
7. Accepted asynchronous intent lives in PostgreSQL; broker messages can be rebuilt.
8. Sources, embeddings, conversation state, outputs, backups and telemetry obey residency and retention.

## Deployment evolution

Begin with one region and managed containers, PostgreSQL, object storage, and Redis. Keep API replicas stateless; store job/run state durably. Scale worker pools separately for OCR, embedding, analytics, and export. Separate queues and per-tenant admission prevent one workload consuming all resources.

A regional cell is a complete data-serving boundary assigned a tenant set. The organization directory maps tenants to home cells. Cross-cell authorization and data queries are not supported by default. Dedicated database/cell placement remains available for large or regulated tenants; it is not promised for the MVP.

Adopt Kubernetes, dedicated vector engines, or warehouses only after [capacity measurements](capacity-and-slos.md) and [ADRs](decisions/README.md) justify them. No exact cloud, region, instance size, provider/model version, or certification is selected here.
