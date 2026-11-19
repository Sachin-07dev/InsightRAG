# Visualization architecture

```mermaid
sequenceDiagram
  participant U as Authenticated user
  participant W as Next.js proxy
  participant V as Visualization API
  participant G as LangGraph
  participant A as Governed analytics
  participant P as PostgreSQL/RLS
  U->>W: POST dashboard with token, org, workspace, dataset, questions
  W->>V: Forward bounded request; no-store
  loop For each view, maximum 8
    V->>G: OrchestrationRequest
    G->>A: Authorized analytics tool
    A->>P: Current membership, resource ACL, workspace, RLS, bounded SQL
    P-->>A: Verified rows + source version
    A-->>G: Decimal result and provenance
    G-->>V: Answered analytics response
    V->>V: Validate shape, numeric data and version
  end
  V-->>W: Typed specs or whole-request error
  W-->>U: Exact HTML tables + ECharts views
```

The database enforces tenant/resource access before visualization. The endpoint does not query tables itself. Request-local dashboard composition avoids persistence and stale saved permissions. Version equality prevents mixing results from two active versions. It does not provide a full snapshot across separately committed SQL transactions; complete snapshot semantics would need an analytics batch API with a shared database snapshot and policy fence. The frontend proxy is a transport convenience, not an authorization boundary.

Chart export occurs in the currently authorized browser session. It is not a managed downloadable report, and previously downloaded files cannot be revoked. Because exporting may expose private metrics, production policy should govern client export and watermarking. The exact table remains available to keyboard/screen-reader users independently of the SVG visualization.
