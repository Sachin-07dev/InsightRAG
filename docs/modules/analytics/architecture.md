# Actual Phase 6 architecture

```mermaid
sequenceDiagram
  participant Client
  participant API as FastAPI analytics route
  participant DB as PostgreSQL runtime/RLS
  participant Worker as Signed ingestion worker
  Client->>Worker: Existing scanned CSV/XLSX upload job
  Worker->>Worker: Parse and validate exact sales contract
  Worker->>DB: Stage JSON and typed sales rows
  Worker->>DB: Publish active version atomically
  Client->>API: Bearer token, org header, resource ID, question
  API->>DB: Resolve identity, current membership and query grant
  API->>DB: Set transaction-local authorized resource scope
  API->>DB: Read authorized schema/currency/active version
  API->>API: Resolve metric, period and fixed SQL template
  API->>DB: Execute bound SQL under row RLS and timeout
  API->>DB: Lock/check policy revision and active version; audit
  API-->>Client: Decimal values, unit, filters, source hash/version/row bounds
```

The runtime role has `SELECT` and staging `INSERT` on the typed table, but no `UPDATE`/`DELETE`. The [scoped RLS policy](../../../apps/api/migrations/versions/0008_analytics_scope.py) denies reads without a transaction-local resource ID, checks that the resource ID matches each row and that the user still has `query` permission, then intersects region entitlements and the active version. The grant check is evaluated once per scoped query instead of per fact row; the 10,000-row synthetic regression exposed the old per-row cost. The projection's foreign key cascades physical erasure when the Phase 4 deletion routine deletes source versions. A tombstoned resource loses `can_resource(...,'query')` immediately, before physical erasure. A policy revision check serializes permission changes with the response transaction; version recheck rejects reindex races. Database pool sessions use transaction-local context via the existing `tenant_session` helper.

The [local DuckDB adapter](../../../apps/api/src/insightrag/analytics/local.py) is deliberately outside this request sequence. It accepts a caller-supplied `tuple[SalesRow,...]`, creates an in-memory table with external access disabled, runs one fixed aggregate, and closes the connection. It does not load source files or connect to PostgreSQL. There is no evidence yet that it improves production latency or capacity.
