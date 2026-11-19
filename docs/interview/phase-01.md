# Phase 1 interview practice

These model answers defend proposals, not an already deployed system. Each domain has five questions, including system design and debugging. Tie answers to the actual [ADRs](../architecture/decisions/README.md), not technology popularity. Implementation phases will add file/function-specific questions.

## 1. System design and architecture

1. **System design: how would you support 10,000 organizations?** Establish corpus size, query/ingestion traffic, tenant skew, entitlements and residency first. Use regional cells, admission controls and dedicated heavy-tenant placement. The capacity table is a hypothesis; no single database or instance-size claim follows from organization count.
2. **Why a modular backend instead of microservices?** It preserves domain boundaries with simpler deployment and transactions. Separate CPU-heavy/unsafe workers for containment. Extract services when ownership, measured scaling or failure boundaries justify distributed-system costs.
3. **Debugging: API latency rises during file ingestion. What do you inspect?** Event-loop blocking, CPU/memory sharing, DB pool saturation, index writes, embedding quotas and queue fairness. Move heavy work away from requests and limit shared-resource contention rather than adding retries blindly.
4. **Why separate document retrieval and analytics?** Search selects relevant passages approximately; it cannot establish complete exact totals. An approved deterministic metric plan computes values, while retrieved reports provide explanations. A common evidence contract joins the two.
5. **How do you defend an architectural choice?** State requirements, alternatives, accepted costs, failure modes, validation evidence and reopening trigger. An ADR marked Proposed is a review request, not proof that the choice is correct or approved.

## 2. Identity and authorization

1. **System design: how do document permissions work?** Require current organization/workspace membership, permitted role capability and explicit resource grant, plus restrictions and lifecycle checks. Enforce before evidence leaves storage and on every derived-artifact access.
2. **What does OIDC solve?** It establishes authenticated identity claims via a trusted issuer and validated protocol. The application still owns resource authorization, membership freshness and tenant selection. Email is not a durable identity key; use issuer/subject.
3. **Debugging: a user sees another organization's cached answer. Where do you look?** Organization/principal/scope in cache keys, authorization revision, conversation ownership and tenant-switch behavior. Then inspect database transaction context and pooled-connection cleanup.
4. **Why does admin not automatically mean content reader?** Administrative duties can be performed without access to private reports. Separate capabilities reduce unnecessary disclosure. Emergency content access requires an explicit, time-limited audited workflow.
5. **Why is permission revocation more than deleting a grant?** Cached decisions, ongoing runs, saved answers, charts, exports and download capabilities may outlive the grant. Revision invalidation, final checks, dependency authorization and mediated downloads address different paths.

## 3. PostgreSQL, schema and persistence

1. **System design: shared database or database per tenant?** Shared tables with RLS and composite tenant keys reduce operational cost. Dedicated databases/cells give stronger resource/operational separation but multiply migrations and pooling. Contractual requirements and measured skew guide placement.
2. **Why does an ORM not establish isolation?** SQLAlchemy helps organize persistence and transactions; it cannot prevent a developer omitting a policy or using a privileged role. Database constraints/RLS and negative tests remain necessary.
3. **Debugging: RLS seems enabled but all rows are visible. What do you inspect?** Runtime role ownership, superuser/BYPASSRLS, FORCE RLS, permissive policy composition, SECURITY DEFINER/view behavior and missing context. Validate using the exact production runtime role, not a migration owner.
4. **Why composite foreign keys when IDs are UUIDs?** UUID uniqueness prevents ordinary collision, not a logical cross-tenant reference. Including organization/resource identity enforces ownership relationships and prevents activating another document's version.
5. **How do you migrate safely?** Expand schema compatibly, deploy readers/writers, backfill resumably, validate constraints/policies, then contract after the compatibility window. Runtime roles cannot migrate; rollback must account for schema and vector-profile compatibility.

## 4. Ingestion, storage and job reliability

1. **System design: how do you ingest safely?** Quarantine verified immutable input, persist a version/job/outbox, scan and parse in isolated workers, stage validated generations, then publish atomically with lifecycle and lease checks. Failures remain visible and prior publication survives updates.
2. **Why does a unique upload key not fully ensure immutable input?** A reusable presigned capability can replace bytes at that same key. Bind completion to a verified object version or copy into an immutable processing object before workers use it.
3. **Debugging: a document returns after deletion. What failed?** A stale worker likely published without checking tombstone/fencing state, or a restore omitted later deletion records. Fence jobs, invalidate dependencies and reconcile the latest ledger before serving.
4. **Do Celery acknowledgements provide exactly-once execution?** No. Crashes around effects/acknowledgements and retries can duplicate work. Durable intent, stable keys/payload hashes, unique receipts, leases, fencing and reconciliation protect the business effect.
5. **How do you choose parsers and chunks?** Evaluate PDF/DOCX/tables/OCR/language fixtures and preserve real locators. Parser correctness, retrieval quality, latency, licensing and isolation determine the choice; chunk size/overlap is a measured profile, not a universal constant.

## 5. Retrieval and embeddings

1. **System design: how would you build hybrid retrieval?** Search authorized active versions with full-text and vector paths, combine ranks, rerank permitted content, diversify and bound context, then record source/version/locator evidence. Evaluate each stage against labeled queries.
2. **Why reciprocal rank fusion?** Lexical and vector scores need not be calibrated to the same scale. Combining rank contributions offers a simple baseline. Candidate counts and damping remain evaluation parameters, not guarantees.
3. **Debugging: a small tenant gets too few ANN hits. Why?** Selective filtering may remove scanned approximate candidates. Check actual authorized corpus, query plan, scan settings and exact-search baseline. Never fix it by widening access.
4. **What happens when embedding models change?** Model/dimension spaces are incompatible unless explicitly proven otherwise. Create a separate generation/collection, re-embed, evaluate, then switch publication. Do not silently mix old and new vectors.
5. **What makes citations trustworthy?** Real source/version/locator, current access and support for the attached claim. Locator validity alone is insufficient; retrieval relevance and factual support need separate review. DOCX pagination cannot be invented.

## 6. Analytics and metric semantics

1. **System design: how do you calculate exact sales securely?** Resolve approved metric/date/currency/grain rules, validate a typed plan against authorized snapshots, compile controlled SQL and execute in a constrained process. Return decimal values with full source and metric provenance.
2. **Why not execute arbitrary generated SQL with a read-only flag?** Reads can disclose data or exhaust resources; engines may expose filesystem/network/extensions. Typed plans, restricted credentials, capability controls and OS containment address different risks.
3. **Debugging: finance disagrees with a correct-looking total. What do you inspect?** Metric version, discounts/returns/tax, cancellations, date attribution, timezone, currency, duplicate joins and snapshot freshness. Arithmetic correctness does not imply semantic agreement.
4. **How do you define three complete months and growth?** Use the organization's reporting timezone and half-open month boundaries. Growth is (current-prior)/prior; missing prior data is not zero, and prior zero gives undefined growth. Label percent versus percentage-point changes.
5. **When would you replace DuckDB with a warehouse?** When dataset size, shared concurrency, freshness or operational requirements exceed the validated snapshot envelope. Keep semantic/access/provenance contracts; a new engine does not solve metric definitions or authorization automatically.

## 7. Orchestration and providers

1. **System design: how do you answer 'why did revenue decline'?** Compute the change deterministically, retrieve relevant authorized reports, assemble evidence and separate observed facts from possible explanations. Do not claim causal proof from correlation and narrative coincidence.
2. **Why LangGraph rather than one prompt?** Explicit state, branching, budgets and persistence make workflows inspectable. A plain state machine remains viable for simple flows. Keep domain policy outside framework-specific state so the choice stays reversible.
3. **Debugging: a resumed run duplicates an export. Why?** Checkpoint recovery can replay nodes after an external effect committed. Use a durable operation identity and receipt; reauthorize resumed work. Checkpointing alone does not make effects exactly once.
4. **What must a provider abstraction test?** Structured outputs, tool argument behavior, timeouts, usage accounting, rate limits, model capability and approved region/retention settings. Matching an OpenAI-style endpoint does not imply equivalent semantics or data handling.
5. **How do you contain prompt injection?** Treat document/model content as untrusted, restrict tool schemas and capabilities, enforce access/egress independently, and validate output. Prompt instructions help behavior but cannot replace these boundaries.

## 8. Web, charts and dashboards

1. **System design: how do you generate a trustworthy dashboard?** Store approved panel plans, refresh under current permissions, pin each result's source/metric versions and render constrained specs bound to real columns. Show freshness and partial failure per panel.
2. **Why TypeScript/React/Next.js?** Typed interfaces and component composition fit a complex enterprise UI; a server session boundary can reduce browser token exposure. They do not replace backend validation, CSRF defenses or access control; a SPA is a viable alternative.
3. **Debugging: chart totals differ from the answer. What do you inspect?** Result IDs, filters, aggregation, timezone, downsampling, source versions and stale cache. Both chart and narrative must consume the same typed calculation, not independently recompute through a model.
4. **Why ECharts and restricted specs?** It supports interactive business charts while an application-owned spec limits series/units/features. Reject arbitrary callbacks/HTML/URLs. Plotly is attractive for scientific plots; choice follows actual visualization needs.
5. **How do you secure exported reports?** Reauthorize dependencies at generation/download, use constrained renderers, neutralize CSV formulas, expire artifacts and preserve provenance. Downloaded files cannot be recalled; strict revocation needs mediated access before download.

## 9. Operations, observability and deployment

1. **System design: how would you recover the service?** Restore metadata and matching objects in an approved region, replay current deletions/access state, validate indexes/snapshots, fence old workers, reconcile jobs, test isolation and reopen gradually. Measure actual RPO/RTO.
2. **How do you use OpenTelemetry/Prometheus/Grafana/Langfuse?** Instrument correlated stage traces, bounded-cardinality metrics and redacted logs. Choose approved backends; keep content capture off by default. Tenant billing records belong in controlled accounting, not unbounded metric labels.
3. **Debugging: backups succeed but recovery misses RTO. Why?** Index rebuild, object reconciliation, missing credentials, ledger verification or undocumented operational steps may dominate. Only a restore drill tests the complete recovery path.
4. **Why defer Kubernetes?** Scheduling/policy features can help at scale but bring operating cost. Managed containers suffice initially if validated. Adopt Kubernetes when platform constraints or measured needs justify it, with ownership and migration plans.
5. **What should CI/IaC prove?** Reproducible checks/builds, reviewed infrastructure, secret handling, migration compatibility and deployment readiness. Terraform and GitHub Actions/Azure DevOps are tools, not evidence of reliability by themselves; acceptance includes security/load/recovery results.
