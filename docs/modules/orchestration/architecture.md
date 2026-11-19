# Phase 7 architecture and transitions

The graph uses a `TypedDict` [GraphState](../../../apps/api/src/insightrag/orchestration/graph.py), Pydantic [RouteDecision](../../../apps/api/src/insightrag/orchestration/contracts.py), and no reducer. Every node returns a partial state update. The branches are finite: `START → classify → (clarify | document | analytics → optional document) → verify → synthesize → optional chart → END`. `recursion_limit=8` catches an accidental future cycle. There is no LLM router. A natural-language question with both a dataset and documents requires explicit, separately validated subquestions; otherwise `clarify` terminates.

```mermaid
sequenceDiagram
  participant U as User
  participant A as FastAPI/OIDC
  participant G as LangGraph
  participant S as Phase 6 SQL
  participant D as Phase 5 RAG
  U->>A: POST /api/v1/orchestration/query
  A->>A: Verify token and current membership
  A->>G: Scoped IDs and server-derived context
  G->>G: classify (Pydantic decision)
  alt analytics or hybrid
    G->>S: AnalyticsRequest + expected workspace
    S->>S: Current grant, RLS, fixed SQL, version recheck
    S-->>G: Decimal strings and provenance
  end
  alt document or hybrid
    G->>D: QueryRequest + explicit document IDs
    D->>D: Scope, retrieval ACL, generation, citation recheck
    D-->>G: Answer and citations, or abstention
  end
  G->>G: verify status and synthesize separate sections
  G->>G: optional chart from SQL rows only
  G-->>A: Pydantic response
  A-->>U: Structured result
```

The graph never interprets a valid JWT or caller-supplied organization header as a document or dataset grant. [Context dependency](../../../apps/api/src/insightrag/security/dependencies.py) resolves current membership; each service independently enforces resource and row permissions. The analytics workspace check occurs in the **same transaction** as resource authorization in [analyze](../../../apps/api/src/insightrag/analytics/service.py). The sequential hybrid order lets verified SQL survive a document-provider outage, while an authorization denial still aborts. Parallel branches would need safe state reducers, consistent policy snapshots, and extra database/provider pressure; there is no measured reason to add them now.

No checkpoint is configured. A reusable checkpoint thread could retain private RAG snippets after revocation, so durable resume needs a tenant-scoped encrypted store, retention/deletion propagation, identity-bound thread IDs and permission revalidation before release. The Phase 5 conversation ID is passed through to Phase 5 and remains owned by that service. Graph state is ephemeral and requests are independent.
