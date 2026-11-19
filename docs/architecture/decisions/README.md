# Architecture Decision Records

All decisions are **Proposed**. Creation is not approval. Each record captures context, choice, alternatives, consequences, validation and reopening trigger.

| ADR | Decision |
| --- | --- |
| [001](001-modular-backend.md) | Modular backend and separate workers |
| [002](002-tenant-isolation.md) | Shared tenant tables and resource authorization |
| [003](003-retrieval-and-analytics.md) | Separate retrieval from numerical analytics |
| [004](004-postgres-hybrid-search.md) | PostgreSQL hybrid retrieval first |
| [005](005-typed-analytics.md) | Typed plans and isolated execution |
| [006](006-immutable-publication.md) | Immutable versions and atomic publication |
| [007](007-job-reliability.md) | Idempotent effects, outbox and fencing |
| [008](008-untrusted-model-content.md) | Untrusted documents/model outputs |
| [009](009-regional-data.md) | Regional tenant data boundary |
| [010](010-derived-artifact-lineage.md) | Derived artifacts inherit evidence dependencies |
| [011](011-infrastructure-evolution.md) | Defer infrastructure specialization |
| [012](012-security-foundation.md) | Phase 3 verified identity, current policy, bounded cleanup delegation |
| [013](013-versioned-ingestion.md) | Phase 4 bounded versioned ingestion and atomic publication |
| [014](014-hybrid-grounded-retrieval.md) | Proposed Phase 5 scoped hybrid retrieval and grounded citation boundary |
| [015](015-governed-sales-analytics.md) | Proposed Phase 6 governed sales projection and bounded SQL analytics |
