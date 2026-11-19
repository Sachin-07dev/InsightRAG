# ADR 014 — scoped PostgreSQL hybrid retrieval and verified source labels

**Status: proposed; owner review pending.**

## Context

Phase 4 publishes one active document version with pgvector rows under Phase 3 RLS. Document questions need semantic and exact-term recall without adding another indexed service. Structured numerical calculations are a different trust and accuracy problem.

## Decision

Use a cosine pgvector candidate query and an English PostgreSQL full-text candidate query, each constrained by organization, workspace, active published version, compatible embedding model and `can_resource(...,'read')`; the runtime DB role also applies RLS. Merge by RRF with deterministic ties. Optional MMR and HTTPS API reranking operate only on authorized candidates. Use a configured OpenAI-compatible JSON chat adapter, reserve a bounded context, validate citation IDs, and re-read evidence and policy after model inference. Persist conversation turns with owner/workspace RLS, using prior questions only to resolve short follow-ups. Exact aggregate questions are handed off as `analytics_required`.

## Alternatives and consequences

Dense-only search misses rare identifiers. PostgreSQL FTS alone misses paraphrases. A dedicated BM25 engine could improve lexical ranking, but adds synchronization, tenant-policy replication and operational cost; measure a labelled corpus first. Raw score blending is rejected because `ts_rank_cd` and cosine distance have unrelated directions and distributions. A local cross-encoder is deferred until measured relevance gain justifies GPU/CPU serving; the API adapter is an integration point, not a claim that any provider is deployed. No global answer cache is used because ACL and version changes would invalidate it. Provider errors fail closed; reranker errors fall back to fused ranking. Citation ID/excerpt checks establish provenance, not semantic entailment.

## Revisit when

Labelled retrieval tests show lexical ranking or multilingual stemming inadequate; pgvector prefilter/ANN recall fails agreed SLOs; reranking improves NDCG enough to offset p95 latency/cost; or production traffic warrants streaming, model serving, or a dedicated search index.
