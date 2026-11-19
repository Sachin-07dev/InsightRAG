# Retrieval engine

## WHAT

Selects authorized passages using lexical and semantic search, fusion, reranking and bounded context assembly.

## WHY

FTS finds exact identifiers; embeddings help paraphrases. Neither alone covers every enterprise question. PostgreSQL initially keeps permission/catalog/retrieval state close; dedicated engines add replicated-policy and deletion responsibilities.

## HOW

Resolve active authorized versions -> FTS and vector queries -> reciprocal rank fusion -> authorized rerank -> diversify/deduplicate -> build evidence references. Enforce SQL authorization even when approximate indexes internally scan candidates from broader index structures. Never fetch unauthorized text into the application for later filtering. Missing hits trigger abstention, not unfiltered retry.

## IMPLEMENTATION

Proposed input: trusted context, query, scope, deadline and profile; output: evidence records with source version, real locator, content and ranking metadata. Start experiments with 50 candidates per path, up to 40 reranked and 8 passages, then tune. Keep embedding dimension/model spaces distinct. Example: policy code matches lexical search; a paraphrased entitlement question may match vectors. Both cite the same pinned version if it is authoritative.

## PRODUCTION

Measure recall@k, ranking quality, no-evidence rate, rerank latency and ACL-selectivity breakdowns. Approximate filtering can return too few hits. Compare exact authorized scans, tuned iterative scans and partition/cell placement. Index builds, vacuum, write amplification and model rate limits affect latency/cost.

## IMPROVEMENT

Improve parser layout, query rewriting, multilingual profiles and rerankers against labeled data. Avoid uncontrolled query expansion or removing permissions. Adopt specialized infrastructure only when measured limits justify it. See [concepts](../concepts/retrieval-vs-analytics.md).
