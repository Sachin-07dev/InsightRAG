# ADR 004: PostgreSQL hybrid retrieval initially

Status: Proposed

## Context

Transactional permissions and retrieval content must remain consistent while initial operational burden stays bounded.

## Decision

Use PostgreSQL full-text and pgvector search with authorized SQL, rank fusion and evaluated reranking. Exact search is the baseline for small authorized sets; approximate indexes require selective-filter evaluation.

## Alternatives

OpenSearch improves dedicated lexical/search operations. Dedicated vector services offer specialized indexing but add replicated metadata, authorization synchronization and deletion complexity.

## Consequences

Consolidation reduces distributed state. Index memory, write maintenance and post-scan ANN filtering can limit scale/recall. Partition/cell strategy is measured, not assumed.

## Validation

Benchmark exact/ANN recall and latency by tenant size, ACL selectivity and concurrent indexing.

## Revisit

Adopt dedicated retrieval infrastructure when tuned PostgreSQL cannot meet measured targets or operational requirements.
