# Retrieval architecture and sequence

The implemented sequence uses FastAPI/HTTP over TLS for the external API and HTTPS for embedding, reranking and generation. PostgreSQL wire protocol runs inside the private service network. Transport is TCP for the deployed HTTP/1.1 or HTTP/2 and PostgreSQL paths; HTTP/3 would use QUIC/UDP at an edge that supports it. These layers solve different problems. The bounded response uses REST; SSE would help token-by-token delivery but needs disconnect, retry and authorization rules, and WebSockets would add bidirectional connection state without a current product need.

```mermaid
sequenceDiagram
  participant U as User
  participant A as FastAPI
  participant P as PostgreSQL/RLS
  participant E as Embedding provider
  participant R as Reranker (optional)
  participant L as LLM
  U->>A: POST question, workspace, optional resources
  A->>P: Resolve OIDC user, membership and workspace
  A->>E: Embed normalized query
  A->>P: Dense + FTS SQL with active version and ACL predicates
  P-->>A: Authorized candidate text only
  A->>A: RRF; optional MMR; token-bound context
  opt configured reranker
    A->>R: Authorized query/chunks only
    R-->>A: Scores or bounded fallback
  end
  A->>L: Evidence as untrusted data; JSON response contract
  L-->>A: Draft answer, source labels, usage
  A->>P: Recheck each chunk, version, access and policy revision
  A->>P: Store owner-scoped conversation turn and audit
  A-->>U: Answer/citations or abstention/error
```

The candidate SQL in `repository.py` is the security-critical component. It joins chunks to the active version, constrains organization/workspace/model and checks `can_resource(...,'read')`; Phase 4 chunk RLS adds an independent boundary. Even a perfect postfilter would be too late if unauthorized text reached a reranker, model or diagnostic trace. The final check prevents a deleted or superseded version from appearing after a slow inference. There is no answer cache. The conversation policy in migration `0006_retrieval.py` requires the current owner and workspace membership. Prior turns are not a durable authorization grant.

At 100, 1,000 or 10,000 concurrent users, no capacity number is assumed. Load tests must measure DB connections, HNSW recall with metadata filters, reranker queue time, provider 429s and token cost. Scale stateless API replicas, cap concurrent provider calls, right-size connection pools, and separate model-serving workers only if measurements warrant. A slow LLM call does not hold a DB connection in the implemented service. Query embedding and provider calls are async I/O; local CPU/GPU reranking would need dedicated execution capacity. Partial retrieval errors fail the query; silently returning only one channel could mask relevance loss. The optional reranker alone has a bounded fallback to fused ranking.
