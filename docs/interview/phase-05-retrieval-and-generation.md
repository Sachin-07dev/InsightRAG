# Phase 5 AI/ML and system-design interview bank

Each answer names the actual Phase 5 implementation. These are interview explanations, not claims of production benchmark results. Follow-ups include answers; exercises can be implemented against the synthetic tests.

## Retrieval mathematics and ranking

### 1. Why can cosine similarity be high for an irrelevant chunk?
**Short answer:** geometric proximity reflects a model's training objective, not task-specific answerability. **Deep/math:** cosine is `q·d/(||q||||d||)`; a generic finance passage may align with a precise invoice query while omitting the invoice. **Project/alternatives:** `repository.py` returns candidates, then lexical search/citation checks add evidence; a trained reranker is another option at extra latency. **Follow-ups:** How detect? Label relevance and inspect false positives. How fix? Improve chunks, hybrid search, rerank and abstention. **Mistake:** equating similarity with truth. **Exercise:** add an irrelevant high-cosine candidate to a ranking fixture.

### 2. How do cosine similarity and L2 distance differ?
**Short answer:** cosine measures angle; L2 measures geometric separation including magnitude. **Deep/math:** for `q=(1,0),d=(0.8,0.6)`, cosine=.8 and L2≈.632; cosine distance=.2. **Project/alternatives:** `repository.py` uses pgvector `<=>` cosine; `<->` would be L2 and needs compatible index ops. **Follow-ups:** Unit vectors? `L2²=2−2cos`. Which is better? Evaluate model training/normalization. **Mistake:** treating lower L2 as higher cosine numerically. **Exercise:** rank three vectors under both.

### 3. When does vector normalization change ranking?
**Short answer:** it can change dot-product and L2 rankings when norms differ; cosine is scale-invariant for nonzero vectors. **Deep/math:** `q=(1,0)`, `a=(2,0)`, `b=(0.9,0.1)` gives dot(a)>dot(b) though normalized cosine(a)=1 and cosine(b)<1; L2 can prefer b. **Project/alternatives:** Phase 4 validates nonzero 1,536-vectors; `ranking.py` computes cosine for MMR. **Follow-ups:** Why normalize? Comparable magnitudes. Caveat? Do not normalize if model encodes useful norm. **Mistake:** assuming all metrics equivalent without unit norms. **Exercise:** write a normalization property test.

### 4. Why use lexical search when dense retrieval exists?
**Short answer:** rare exact identifiers are often better matched by terms than semantics. **Deep/math:** inverted indexes map token→posting list; IDF gives rare terms greater weight in BM25, though this project uses `ts_rank_cd`. **Project/alternatives:** GIN FTS in migration `0006_retrieval.py`; a BM25 service adds sync/ACL burden. **Follow-ups:** What about `INV-42` tokenization? Inspect `to_tsvector`. Typos? Consider trigram search after measurement. **Mistake:** calling PostgreSQL rank BM25. **Exercise:** compare exact-ID recall on labelled cases.

### 5. How does RRF work mathematically?
**Short answer:** add reciprocal rank contributions across channels. **Deep/math:** `RRF(d)=Σ1/(60+r_c(d))`; dense #1+sparse #3 gives `1/61+1/63≈.03227`. **Project/alternatives:** `ranking.py` deduplicates by source/version/position; score fusion needs calibration. **Follow-ups:** Missing channel? Contribution zero. Why k=60? Damps top-rank dominance; tune with held-out labels. **Mistake:** adding raw distance and FTS rank. **Exercise:** calculate a three-item fusion by hand.

### 6. Why not add raw BM25 and cosine scores?
**Short answer:** scales and directions differ and this implementation does not compute BM25. **Deep/math:** cosine distance .2 is better than .8, while lexical rank 0.8 is better than .2; summing can invert intent. **Project/alternatives:** `ranking.py` uses RRF; normalized weighted scores are possible after distribution calibration. **Follow-ups:** Normalize how? Held-out per-channel calibration. Risk? Drift after model/corpus updates. **Mistake:** assuming 0.8 means the same thing across systems. **Exercise:** construct a counterexample where raw addition misranks.

### 7. What if retrieval K is too small or large?
**Short answer:** small K misses relevant evidence; large K adds noise, latency and tokens. **Deep/math:** P@K and R@K move differently as K grows; recall usually rises while precision can fall. **Project/alternatives:** settings bound dense/sparse/fusion/context pools separately; reranking can rescue larger candidate pools at cost. **Follow-ups:** Which K tune first? Candidate coverage. How measure? Paired held-out P/R/NDCG and latency. **Mistake:** choosing K by intuition. **Exercise:** plot metrics for K=1,3,5 on fixture.

### 8. How choose a similarity threshold?
**Short answer:** calibrate model-specific distance distributions against relevant/irrelevant labels and abstention costs. **Deep/math:** cosine distance `1−cos`; lower is better. A threshold trades false positives against false negatives. **Project/alternatives:** cutoff is disabled by default in `config.py`; rerank or confidence model are alternatives. **Follow-ups:** Model changes? Recalibrate. Sparse hits? May still pass fusion. **Mistake:** reusing a threshold from another embedding model. **Exercise:** choose an operating point from labelled scores.

### 9. How does MMR reduce duplicates?
**Short answer:** it rewards query relevance and penalizes similarity to already selected chunks. **Deep/math:** `λsim(q,d)−(1−λ)max sim(d,s)`; at λ=.5, a near-duplicate with .9 relevance/.99 redundancy scores −.045. **Project/alternatives:** optional `maximal_marginal_relevance` in `ranking.py`; parent retrieval or clustering may preserve nuance better. **Follow-ups:** λ=1? No diversity penalty. Main risk? Omitting a crucial similar chunk. **Mistake:** claiming MMR increases factual correctness by itself. **Exercise:** test two duplicates plus one distinct chunk.

### 10. Why rerank after dense/hybrid retrieval?
**Short answer:** a joint query-document model can judge fine-grained relevance on a small pool. **Deep/math:** a cross-encoder attends across both token sequences; cost scales with pairs and sequence length. **Project/alternatives:** `rerank.py` is an optional HTTPS score adapter; local CPU/GPU cross-encoder is deferred. **Follow-ups:** What input may leave? Authorized candidates only. What if timeout? Fused-order fallback. **Mistake:** sending unfiltered candidates to reranker. **Exercise:** mock timeout and assert fallback.

### 11. Why not score every document with a cross-encoder?
**Short answer:** per-pair inference is too expensive for a large corpus. **Deep/math:** N documents require N forward passes versus ANN/FTS candidate lookup then C≪N rerank passes. **Project/alternatives:** bounded `retrieval_rerank_k` after fusion; a small corpus might permit full scan. **Follow-ups:** Batch/GPU? Improves throughput, not free compute. How choose C? Evaluate candidate coverage versus p95. **Mistake:** assuming cross-encoder scores are precomputable for arbitrary queries. **Exercise:** estimate passes for N=1M,C=20.

### 12. How prevent irrelevant chunks filling context?
**Short answer:** bounded candidate pools, optional reranking/MMR, token limits, deduplication and abstention. **Deep/math:** evidence token budget is context window minus instructions/history/output reserve; more K can lower signal-to-noise. **Project/alternatives:** `context.py` caps 2,400 evidence tokens and six chunks by default; extractive compression/parent retrieval need evaluation. **Follow-ups:** Lost-in-middle? Order stronger evidence near salient positions. How debug? Log IDs/ranks, not text. **Mistake:** stuffing all retrieved chunks. **Exercise:** test a small budget excludes the tail.

### 13. How handle conflicting documents?
**Short answer:** keep both current authorized sources, state disagreement and cite each; do not average unsupported claims. **Deep/math:** ranking does not resolve truth; provenance/version/date authority are separate signals. **Project/alternatives:** active-version filtering prevents old/new same-resource conflict; cross-resource conflict is not automatically resolved. **Follow-ups:** Which source wins? Business authority policy, not model confidence. Test? Label conflicts and expected uncertainty. **Mistake:** reporting a single confident answer. **Exercise:** create two contradictory synthetic chunks.

### 14. How ensure answers are grounded?
**Short answer:** restrict evidence, require source labels, validate labels/excerpts and evaluate claim support. **Deep/math:** grounding is entailment between each claim and evidence, not high retrieval similarity. **Project/alternatives:** `provider.py` JSON prompt and `service.py` revalidation; an entailment checker/human review can improve claim-level assurance. **Follow-ups:** Can valid citation be wrong? Yes. How detect? Annotated claim-citation pairs. **Mistake:** equating label existence with faithfulness. **Exercise:** return a cited but unsupported claim and classify it.

### 15. How verify citations support claims?
**Short answer:** validate provenance first, then assess semantic entailment separately. **Deep/math:** exact substring proves excerpt identity, not `evidence⇒claim`. **Project/alternatives:** `verify_citations` and `revalidate_evidence` verify ID/version/access/text; human or independent entailment judge is deferred. **Follow-ups:** Stale version? Final recheck rejects. Multi-claim answer? Map each claim to cited spans. **Mistake:** counting any citation as correct. **Exercise:** annotate three claim-span pairs.

### 16. When should RAG abstain?
**Short answer:** when authorized evidence is absent or insufficient, citations are invalid, or exact analytics is required. **Deep/math:** abstention threshold balances false answers against false refusals; evaluate both rates. **Project/alternatives:** no evidence/no cited output abstains; forged label returns 502; numerical aggregate returns `analytics_required`. **Follow-ups:** High similarity sufficient? No. How calibrate? Held-out answerability labels. **Mistake:** always producing a fluent answer. **Exercise:** test an unanswerable query.

### 17. How evaluate retrieval independently from generation?
**Short answer:** compare ranked source IDs to labelled relevant chunks without calling an LLM. **Deep/math:** P@K, R@K, MRR, MAP, NDCG and candidate coverage measure rankings. **Project/alternatives:** `evaluation.py` and toy `scripts/evaluate-retrieval.py`; generation is assessed separately by correctness/faithfulness. **Follow-ups:** ANN recall? Compare HNSW to exact authorized vector scan. Why permission-aware labels? Unauthorized relevant chunks must never count as available. **Mistake:** using answer fluency as retrieval quality. **Exercise:** compute MRR from a fixture.

### 18. Precision@K versus Recall@K?
**Short answer:** precision is relevant fraction of returned K; recall is relevant fraction of all relevant items. **Deep/math:** one relevant among three returned, two total relevant gives P@3=1/3 and R@3=1/2. **Project/alternatives:** `evaluate_ranking` computes both; NDCG adds graded order sensitivity. **Follow-ups:** No relevant items? Define convention and measure abstention separately. Which matters for first stage? Recall/candidate coverage. **Mistake:** swapping denominators. **Exercise:** label a five-item ranking and calculate both.

### 19. What is MRR and when useful?
**Short answer:** mean reciprocal rank rewards placing the first relevant hit early. **Deep/math:** first relevant at rank 4 gives RR=.25; mean across queries gives MRR. It ignores later relevant results, so multi-document tasks also need recall/NDCG. **Project/alternatives:** `evaluation.py` computes per-query RR; MAP considers all relevant ranks. **Follow-ups:** Unanswerable query? RR=0 by convention. Why use MRR? Single-answer navigation. **Mistake:** calling it recall. **Exercise:** compute MRR of ranks 1,2,∞.

### 20. How evaluate hallucination and faithfulness?
**Short answer:** label answer claims against authorized evidence and count unsupported claims, with human review for difficult cases. **Deep/math:** a hallucination rate can be unsupported factual claims/total factual claims; define the denominator and abstention treatment. **Project/alternatives:** current citation validation is provenance-only; LLM-as-judge and entailment models are possible but can share biases. **Follow-ups:** Correct answer with wrong source? Citation failure. Model judge disagreement? Adjudicate sampled cases. **Mistake:** relying only on exact answer strings. **Exercise:** score three synthetic claims.

### 21. How prevent cross-tenant leakage?
**Short answer:** derive identity server-side, filter candidates in SQL, enforce RLS, revalidate before inference/output and isolate history. **Deep/math:** the invariant is `candidate.org=user.org ∧ current_acl(candidate,user)`. **Project/alternatives:** `repository.py`, Phase 3 RLS and migration conversation policies; separate databases improve isolation at cost. **Follow-ups:** Reranker cache? Must be tenant/version/policy scoped. DB pool? `set_config(...,true)` is transaction-local. **Mistake:** filtering after model input. **Exercise:** run the real-service Company A/B test.

### 22. Why is a valid JWT insufficient for document access?
**Short answer:** authentication proves a principal, not current workspace/resource grants. **Deep/math:** authorization evaluates issuer/subject→user, active membership, workspace role, classification, MFA, purpose and ACL at request time. **Project/alternatives:** `security/dependencies.py` and `require_resource`; token-embedded ACLs become stale. **Follow-ups:** What about an org header? It is a selector, not proof. Permission revocation? DB recheck. **Mistake:** trusting client-supplied tenant IDs. **Exercise:** use one valid user against a denied document.

### 23. How prevent deleted documents in retrieval?
**Short answer:** constrain to active published version and current resource state in SQL/RLS, then recheck after inference. **Deep/math:** vector index entries may persist physically while `r.state='deleted'` makes them invisible. **Project/alternatives:** `repository.py` and Phase 4 tombstones; synchronous physical purge would slow deletion and still need backups. **Follow-ups:** Worker reinsert? Phase 4 version fencing blocks stale publish. Stale citation? Deny resolution. **Mistake:** relying on asynchronous index deletion alone. **Exercise:** mark a synthetic resource deleted, query again.

### 24. What if permissions change during a conversation?
**Short answer:** every turn reauthorizes; previous evidence is not a grant. **Deep/math:** historical citation references are versioned IDs but access is time-dependent. **Project/alternatives:** `service.py` reads only prior questions and reretrieves; static client history risks stale leaks. **Follow-ups:** Change during model call? Final policy/evidence check returns 409. After final commit? A narrow delivery race remains. **Mistake:** replaying stored answer context. **Exercise:** revoke a grant between turns.

### 25. How defend against prompt injection in documents?
**Short answer:** treat documents as data, never tool instructions; enforce ACLs outside the model and validate outputs. **Deep/math:** instruction hierarchy is a trust boundary, not a string delimiter guarantee. **Project/alternatives:** `provider.py` untrusted-evidence instruction, no SQL/Python tools, bounded JSON and source checks; isolation alone cannot prove semantic safety. **Follow-ups:** “Ignore previous instructions” in evidence? Quote/ignore, do not execute. Tool-using agent? Strict allowlisted tools and policy gates. **Mistake:** believing a prompt alone is sufficient. **Exercise:** insert malicious text into a synthetic chunk.

### 26. Relevant chunks but wrong answers: debug how?
**Short answer:** inspect context selection, prompt, model output and claim support separately from retrieval. **Deep/math:** high recall does not imply faithfulness. **Project/alternatives:** use authorized diagnostic IDs from `service.py` stages, compare extractive answer baseline, test token budget/order and conflict handling. **Follow-ups:** Context truncated? Check tokenizer counts. Provider nondeterminism? Pin model/version and repeat. **Mistake:** tuning HNSW when relevant text already reached the model. **Exercise:** force a wrong mock answer with correct citation ID.

### 27. Correct answer but wrong citations: debug how?
**Short answer:** trace label-to-chunk mapping and claim-to-excerpt support. **Deep/math:** correctness and attribution are independent axes. **Project/alternatives:** `context.py` labels source/version/position; `service.py` verifies membership/excerpt but semantic mismatch needs claim labels. **Follow-ups:** Version changed? Revalidation 409. Duplicate text? Dedup key includes source version. **Mistake:** accepting any citation because wording is correct. **Exercise:** swap two valid labels in a mock response.

### 28. Reduce latency without large accuracy loss?
**Short answer:** profile stages and optimize the actual p95 bottleneck under a fixed quality floor. **Deep/math:** p95 is the latency at which 95% of requests complete; tail latency can be dominated by provider queues. **Project/alternatives:** async remote I/O, bounded K/context and no DB connection during inference; batching, tuned indexes or a smaller model require measured comparisons. **Follow-ups:** Cache? Requires policy/version invalidation. Reranker? Disable only if NDCG impact acceptable. **Mistake:** optimizing mean latency alone. **Exercise:** build a stage-timing budget.

### 29. REST, SSE or WebSockets for answers?
**Short answer:** REST fits the current bounded non-streamed response; SSE fits one-way token streaming; WebSockets fit bidirectional interaction. **Deep/protocol:** HTTP/1.1/2 run over TCP+TLS; HTTP/3 over QUIC/UDP. SSE is an HTTP response stream, whereas WebSocket upgrades to a persistent full-duplex channel. **Project/alternatives:** `routes.py` uses REST; streaming needs disconnect/final-citation/retry design. **Follow-ups:** Reconnect? Idempotent query/turn IDs. Backpressure? Limit buffered tokens and close slow clients. **Mistake:** equating WebSocket with lower latency by default. **Exercise:** design an SSE event schema.

### 30. Scale to thousands of concurrent users?
**Short answer:** measure bottlenecks first, then scale stateless APIs, DB pools/indexes and provider capacity with quotas/backpressure. **Deep/math:** Little's law `L=λW` links concurrency, arrival rate and latency; 1,000 in-flight at 5 seconds implies roughly 200 req/s if stable. **Project/alternatives:** `service.py` releases DB connections during provider calls; dedicated model serving or vector service is conditional on load tests. **Follow-ups:** Provider 429s? Bounded queues and controlled retry. Tenant fairness? Per-tenant budgets. **Mistake:** claiming a capacity without tests. **Exercise:** draft a 100/1,000/10,000-user load plan.

### 31. How prevent cache leakage?
**Short answer:** avoid shared response caches without tenant/user/policy/version keys and reauthorization. **Deep/math:** a key derived only from query text collides across users with different ACLs. **Project/alternatives:** this phase has no answer cache; private per-request embedding reuse might be safer but still needs model/query privacy review. **Follow-ups:** Grant revocation? Invalidate or recheck on hit. Cross-region? Residency constraints. **Mistake:** using global query hash as an authorization boundary. **Exercise:** design a cache key and invalidation test.

### 32. Multiple embedding-model versions in one index?
**Short answer:** never compare incompatible vectors; filter by model ID and reindex for migration. **Deep/math:** coordinates and score distributions differ even at equal dimensions. **Project/alternatives:** `document_versions.model_id` is filtered in `repository.py`; a parallel index per model can support gradual migration but costs storage. **Follow-ups:** Dimension changes? New column/index or store. Threshold? Recalibrate. **Mistake:** assuming 1,536 dimensions imply compatibility. **Exercise:** query an old-model active version and verify exclusion.

### 33. Design a multi-stage retrieval pipeline.
**Short answer:** authorize scope, generate dense/lexical candidates, fuse, optionally rerank, assemble context, generate, verify. **Deep/math:** early stages optimize high recall per unit cost; later stages optimize precision with bounded C≪N. **Project/alternatives:** `repository.py`→`ranking.py`→`context.py`→`provider.py`→`service.py`; a search engine or parent-child index may replace a stage after measurement. **Follow-ups:** Where ACL? Before candidate text leaves DB and again before output. Where abstention? Before/after generation. **Mistake:** applying ACL only after reranking. **Exercise:** draw a sequence with failure branches.

### 34. How measure reranking improvement?
**Short answer:** use the same held-out queries and candidate pool, compare ranking quality, answer quality, p95 and cost with reranker on/off. **Deep/math:** paired per-query `ΔNDCG@K` with confidence intervals avoids hiding regressions in means. **Project/alternatives:** optional `rerank.py` adapter; no provider-backed lift has been measured. **Follow-ups:** Candidate miss? Reranker cannot recover absent relevant chunks. Privacy? Egress assessment. **Mistake:** changing K, model and reranker simultaneously. **Exercise:** add a fixed-score mock reranker to evaluation.

### 35. Defend the architecture in a senior interview.
**Short answer:** it separates exact analytics from evidence retrieval, enforces ACLs before model input, uses PostgreSQL RLS plus explicit SQL scope, fuses complementary rankings, cites immutable versions and rechecks after inference. **Deep/math:** RRF avoids score-scale mismatch; HNSW/FTS give bounded candidate search; context budgets bound inference cost. **Project/alternatives:** Phase 3/4 foundations and Phase 5 modules; a dedicated BM25/vector tier or local model serving awaits measured SLO gaps. **Follow-ups:** Biggest residual risk? Semantic citation faithfulness and provider/deployment assurance. First scaling experiment? Tenant-filtered exact-vs-HNSW recall and end-to-end p95 load. **Mistake:** claiming production readiness from a toy fixture. **Exercise:** present the sequence and a failure/recovery path in five minutes.

## Three owner review questions

1. If a chunk ranks first by cosine but contains no answer, which metric or evaluation label reveals that problem, and what stage could correct it?
2. Why is a PostgreSQL `ts_rank_cd` value unsafe to add directly to a pgvector cosine distance?
3. A user loses access while an LLM call is running. Which implemented checks protect the response, and what narrow race remains after the final transaction?
