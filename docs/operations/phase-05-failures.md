# Phase 5 failure and debugging matrix

Use request IDs and stage/count telemetry; do not record private query or chunk text in ordinary logs. For every row below, the columns give root cause, symptom/impact, detection/debugging, recovery/prevention and regression test. “Pending” means a proposed test, not executed evidence.

| Failure | Root cause | Symptom and impact | Detect/debug | Recover/prevent | Regression |
| --- | --- | --- | --- | --- | --- |
| No evidence | No authorized active match or model mismatch | Abstention, no citation | Candidate counts, scope/model IDs | Verify ingestion, grants and query labels; never invent answer | Unit abstention pending; integration empty after delete passed |
| Dense/sparse disagree | Paraphrase versus rare ID | Unstable top rank | Per-channel IDs and relevance labels | RRF, labelled rerank evaluation | RRF unit passed; relevance study pending |
| Rewrite drift | Pronoun context drops entity/date | Wrong document | Compare original and resolved query under authorized trace | Disable learned rewrite; current rule appends prior question | Follow-up integration passed; drift corpus pending |
| Wrong tenant predicate | Missing org/workspace/ACL constraint | Data leak | Company A/B runtime-role test and SQL review | Fail closed, RLS plus explicit predicates | Cross-tenant integration passed |
| Deleted document | Stale vector remains | Forbidden citation | Compare resource state/active version | SQL tombstone exclusion and final reread | Deleted exclusion integration passed |
| Superseded version | Inference spans publication | Stale citation | Version mismatch 409 | Retry on active version | Concurrent update test pending |
| Embedding model mismatch | Reindexed or misconfigured model | Empty candidates or invalid dimensions | Compare `model_id`, dimension | Reindex/restore matched profile | Dimension unit from Phase 4; mixed-model integration pending |
| HNSW degradation | Filtered ANN recall or index bloat | Relevant misses, slow scan | Exact-vs-ANN recall, EXPLAIN | Tune/reindex only on measured evidence | Load/recall benchmark pending |
| Reranker timeout | External dependency slow | Fused-order fallback | Warning and rerank latency | Bounded timeout/circuit strategy | Fault-injection pending |
| Context overflow | Tokenizer/model window mismatch | Provider rejection | Token count and 4xx without content | Lower budget/reserve output | Context unit passed; provider window pending |
| Hallucination | Model extrapolates beyond excerpt | Unsupported answer | Claim-level human/entailment labels | Abstain, prompt/model change, reviewer feedback | Citation ID unit passed; semantic test pending |
| Wrong citation | Model chooses valid but unrelated source | Misattribution | Claim-to-excerpt audit | Claim-level verifier or human review | Forged ID unit passed; entailment pending |
| Prompt injection | Retrieved text imitates instructions | Manipulated answer | Injection-labelled cases, output audit | No tools, untrusted data boundary, output validation | Full adversarial suite pending |
| History leakage | Conversation owner/workspace check missing | Cross-user context | Foreign-ID test | RLS and request-time owner check | Foreign conversation integration passed |
| Pool exhaustion | Too many SQL sessions | Timeouts and p99 rise | Pool wait/active count | Short transactions, queue/backpressure, sizing | Load test pending |
| Provider outage | Embedding or LLM unavailable | 503, no fabricated answer | Error class, timeout, provider status | Controlled retry/circuit and capacity contract | Mock outage test pending |
| Retry storm | Many clients retry 503/429 | Cascading overload | Request rate and retry headers | Jitter, idempotency and retry budgets | Chaos test pending |
| Streaming disconnect | Future SSE path interrupted | Partial answer/citations | Disconnect events | Final citation event/idempotent turn semantics | Not applicable; streaming deferred |
| High latency | DB, rerank or LLM bottleneck | Poor p95/p99 | Per-stage timings and traces | Optimize measured stage, cap K/tokens | Load benchmark pending |

The safe allowlisted completion event includes total, embedding, dense, sparse, fusion, rerank (when enabled), context, generation and final recheck durations plus counts and provider token usage. Full OpenTelemetry spans and p50/p95/p99 dashboards are deferred. Do not interpret absence of a failure log as evidence of safety. Migration/rollback and production retention must be coordinated with the existing database and data-erasure runbooks.
