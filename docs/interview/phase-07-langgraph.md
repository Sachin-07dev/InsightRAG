# Phase 7 interview bank: LangGraph orchestration

Each answer refers to the implemented [graph](../../apps/api/src/insightrag/orchestration/graph.py), [API adapter](../../apps/api/src/insightrag/orchestration/routes.py), and [contracts](../../apps/api/src/insightrag/orchestration/contracts.py). The examples are synthetic; they do not demonstrate production model quality.

## Graph and state (five questions)

### 1. What is a LangGraph `StateGraph`?

**Short answer:** It is a graph builder whose nodes read shared state and return partial state updates; compilation yields an executable workflow.

**Deep explanation:** Edges define control flow, and conditional edges choose the next node from a finite map. Our `GraphState` is a `TypedDict`; Pydantic validates API data and route labels at runtime. `START` enters `classify`, and terminal paths reach `END`. Compilation validates graph structure, not authorization. **Project:** [build_graph](../../apps/api/src/insightrag/orchestration/graph.py) wires seven nodes. **Alternatives:** Plain async functions reduce dependency overhead; LangChain chains fit linear prompt calls. **Follow-ups:** Q: What does a node return? A: Changed state keys. Q: Does compile execute the graph? A: No, `ainvoke` does. **Common mistake:** Calling the builder directly or treating typed state as runtime wire validation.

### 2. When does a reducer matter?

**Short answer:** A reducer combines concurrent writes to the same state key in parallel branches.

**Deep explanation:** Without a reducer, simultaneous updates can conflict. Our hybrid path runs analytics then document sequentially, so each node writes its own result and a node list; no parallel merge occurs. **Project:** `GraphState` has no `Annotated` reducer. **Alternatives:** Parallel fan-out with reducers could lower p95 but increases database/provider pressure. **Follow-ups:** Q: Can a reducer solve authorization races? A: No. Q: What must a parallel result merger preserve? A: Provenance, versions, and failure status. **Common mistake:** Adding a list concatenation reducer before understanding duplicate or stale state.

### 3. Why is routing deterministic?

**Short answer:** Caller-selected source classes and explicit hybrid subquestions give predictable, auditable tool selection without model drift.

**Deep explanation:** The classifier uses a conservative query hint; it does not rewrite resource IDs or financial terms. Both sources without separate subquestions terminate in clarification. **Project:** [classify](../../apps/api/src/insightrag/orchestration/graph.py). **Alternatives:** A structured LLM router may improve recall on ambiguous language but adds latency, cost and prompt-injection exposure; evaluate it on labeled cases first. **Follow-ups:** Q: Can an LLM route authorize a dataset? A: Never. Q: What if a question says “net revenue”? A: Phase 6 rejects unsupported definitions. **Common mistake:** Treating a plausible route as a permission grant.

### 4. What bounds graph execution?

**Short answer:** Finite edges, an eight-step recursion ceiling and a configured wall-clock timeout.

**Deep explanation:** The graph has no loop. `asyncio.wait_for` cancels a slow request; `recursion_limit` guards future accidental cycles but does not limit SQL CPU. Phase 6 sets its own statement timeout. **Project:** [execute](../../apps/api/src/insightrag/orchestration/graph.py), [Settings](../../apps/api/src/insightrag/core/config.py). **Alternatives:** Node-specific timeouts are useful once per-stage measurements exist. **Follow-ups:** Q: Does cancellation roll back provider cost? A: No. Q: Does recursion limit replace rate limiting? A: No. **Common mistake:** Claiming recursion limit is a full resource quota.

### 5. Why no checkpointer?

**Short answer:** Graph state may contain private evidence, and a secure tenant-bound durable-resume policy is not yet designed.

**Deep explanation:** A checkpointer stores state between steps and can replay it with a thread ID. A reused or unscoped thread could expose revoked evidence. Phase 5 already owns conversation persistence with permission rechecks. **Project:** [build_graph](../../apps/api/src/insightrag/orchestration/graph.py) calls `compile()` without one. **Alternatives:** Encrypted PostgreSQL checkpoints with TTL, tenant/owner binding, deletion propagation and revalidation. **Follow-ups:** Q: Is `InMemorySaver` durable across pods? A: No. Q: What must happen on resume after revocation? A: Revalidate before use or release. **Common mistake:** Adding shared checkpoint memory as a shortcut for chat history.

## Security and tool boundaries (five questions)

### 6. Why is a valid JWT insufficient for a document or dataset query?

**Short answer:** It proves an identity claim, not current workspace membership, resource grant, row entitlement or publication state.

**Deep explanation:** The API resolves current membership, then Phase 5 and Phase 6 check current grants within their own transactions. Analytics also checks the selected workspace and PostgreSQL RLS. **Project:** [Context dependency](../../apps/api/src/insightrag/security/dependencies.py), [analyze](../../apps/api/src/insightrag/analytics/service.py). **Alternatives:** A coarse token role is faster but cannot track revocation safely. **Follow-ups:** Q: Can an organization header switch tenants? A: Membership must match. Q: What if a resource moves? A: Transactional workspace comparison fails closed. **Common mistake:** Authorizing from JWT role or caller-controlled ID alone.

### 7. How does the graph prevent prompt injection from invoking SQL?

**Short answer:** Retrieved text never controls graph edges or SQL; Phase 6 compiles a bounded plan to fixed SQL.

**Deep explanation:** The classifier reads only the request question and selected source IDs. Phase 5 treats document text as untrusted evidence. An LLM-produced phrase cannot name arbitrary tables or functions. **Project:** [classify](../../apps/api/src/insightrag/orchestration/graph.py), [Phase 6 planner](../../apps/api/src/insightrag/analytics/planning.py). **Alternatives:** Raw text-to-SQL is more flexible but requires stronger AST and database boundaries. **Follow-ups:** Q: Can prompts alone enforce this? A: No. Q: What enforces rows? A: PostgreSQL RLS. **Common mistake:** Assuming a system prompt is a security control.

### 8. How do hybrid answers preserve numerical accuracy?

**Short answer:** The graph copies decimal strings from the authorized SQL result and labels document narrative separately.

**Deep explanation:** Phase 6 computes metrics; Phase 5 generates cited narrative. The graph does not ask an LLM to recompute values or infer that narrative caused a numeric change. Chart points are the same strings. **Project:** [synthesize and build_chart](../../apps/api/src/insightrag/orchestration/graph.py). **Alternatives:** A final LLM synthesis could improve prose but risks altering figures; it needs strict claim verification. **Follow-ups:** Q: Can a vector score supply revenue? A: No. Q: What if SQL and a report conflict? A: Preserve both provenance paths and flag the conflict. **Common mistake:** Presenting co-occurrence as causal proof.

### 9. When is a partial hybrid result safe?

**Short answer:** Only when analytics has already returned a verified result and the document provider reports unavailability; authorization failures must propagate.

**Deep explanation:** The graph catches only document-side 503/504 on a hybrid path. It returns no fabricated document answer. A 404 or authorization revision conflict cannot be downgraded to partial. **Project:** `document` node and [provider-outage test](../../apps/api/tests/test_orchestration.py). **Alternatives:** Fail the entire request for simpler semantics, at the cost of losing a valid SQL result. **Follow-ups:** Q: Should an analytics timeout return a document-only total? A: No exact metric is then verified. Q: Should revoked access look like provider outage? A: No. **Common mistake:** Catching every exception and returning stale cached values.

### 10. How do you prevent chart data leakage?

**Short answer:** Build the chart only from the already authorized analytics response; never fetch additional rows or dimensions in the chart node.

**Deep explanation:** The chart spec contains the exact dataset version ID, metric version and row values. Phase 6 applied resource and row policies before those values existed. A chart is a derived artifact and must inherit the same access boundary if persisted later. **Project:** [build_chart](../../apps/api/src/insightrag/orchestration/graph.py). **Alternatives:** A later dashboard store needs resource-bound ACLs and revocation invalidation. **Follow-ups:** Q: Can chart labels expose sensitive regions? A: Yes, so labels also come only from authorized rows. Q: Is an in-memory chart cache safe? A: Only if scoped and revalidated. **Common mistake:** Treating visualizations as public because they are aggregated.

## Runtime and production debugging (five questions)

### 11. What does async LangGraph execution improve?

**Short answer:** It lets the server handle other requests while database or provider I/O waits, without promising faster CPU work.

**Deep explanation:** `ainvoke` awaits async nodes; FastAPI runs on ASGI. Pool saturation, provider rate limits and model latency still set throughput. **Project:** [execute](../../apps/api/src/insightrag/orchestration/graph.py) and the existing async Phase 5/6 services. **Alternatives:** Sync worker pools can isolate blocking code; GPU/model-serving queues handle heavy inference. **Follow-ups:** Q: Does `async` parallelize SQL? A: No. Q: Why not fan out hybrid branches now? A: No measured need and a harder consistency problem. **Common mistake:** Equating concurrency with parallel CPU execution.

### 12. How would you debug the wrong route?

**Short answer:** Reproduce the request against `classify`, inspect selected source IDs and normalized query kind, then add a labeled regression.

**Deep explanation:** Node sequence and route are logged without raw query text. A hybrid question lacking subquestions must clarify, even if a human can infer the split. **Project:** [five graph traces](../../apps/api/tests/test_orchestration.py). **Alternatives:** LLM-based classifier experiments can be evaluated offline. **Follow-ups:** Q: What if a chart phrase routes to documents? A: Require a dataset or clarify. Q: Can logs contain private text for debugging? A: Only under separately approved protected diagnostics. **Common mistake:** Fixing routing by weakening downstream authorization.

### 13. How would you debug correct SQL values paired with a wrong document explanation?

**Short answer:** Verify SQL provenance and metric period, then inspect Phase 5 citations and whether the narrative actually supports the claim.

**Deep explanation:** The graph keeps `analytics` and `document` separate; a report about shipment delays is not causal proof of the measured revenue change. Phase 5 citation ID validation does not guarantee entailment. **Project:** [response contract](../../apps/api/src/insightrag/orchestration/contracts.py) exposes both sources. **Alternatives:** Human review or claim-level entailment checks could reduce errors. **Follow-ups:** Q: Should the graph edit the SQL value to match prose? A: Never. Q: How is a stale source found? A: Compare version IDs and current authorization. **Common mistake:** Treating fluent prose as verified evidence.

### 14. What telemetry would you collect under load?

**Short answer:** Route counts, per-node and end-to-end p50/p95/p99 latency, provider errors, SQL timeouts, token use and partial-result rate, without raw private content.

**Deep explanation:** This phase emits a request span and completion log. An OTel SDK/exporter must be configured to export spans; node-level spans and cost estimation are future work. Correlate with existing request IDs and Phase 5/6 service timing. **Project:** [execute](../../apps/api/src/insightrag/orchestration/graph.py). **Alternatives:** Custom metrics alone lose cross-service causality; unredacted logs risk leakage. **Follow-ups:** Q: What does p95 reveal that the mean hides? A: Tail bottlenecks. Q: Where might backpressure appear? A: DB pool or provider limits. **Common mistake:** Reporting synthetic unit-test speed as production capacity.

### 15. How would you design a secure durable orchestration system at 10,000 concurrent users?

**Short answer:** Keep stateless API workers, enforce per-tenant admission and provider quotas, use tenant-bound encrypted checkpoints only if resume is required, and load-test real bottlenecks.

**Deep explanation:** First measure DB pool waits, RAG retrieval, generation, and analytics p95. Scale service replicas and provider capacity according to evidence. Preserve current authorization inside each tool and on resume. Bound time, token consumption and result size; separate heavy model serving if necessary. **Project:** Current graph is ephemeral, sequential and bounded, while Phase 6's 10,000-row single-user result is not concurrency evidence. **Alternatives:** Parallel graph fan-out or workflow queues may help long-running work but add state/retry complexity. **Follow-ups:** Q: Can a checkpoint replay old evidence after deletion? A: Yes unless retention/deletion and revalidation are designed. Q: What is the first load-test goal? A: Find p95 bottlenecks under representative tenant/query mix. **Common mistake:** Claiming LangGraph itself supplies horizontal scale or tenant isolation.
