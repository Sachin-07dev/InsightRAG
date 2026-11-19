# Implementation walkthrough

## Inputs and contracts

[OrchestrationRequest](../../../apps/api/src/insightrag/orchestration/contracts.py) validates UUID source selections, query length, chart prerequisites, currency form, and optional year/region filters. It does not assert that IDs are authorized. [RouteDecision](../../../apps/api/src/insightrag/orchestration/contracts.py) limits the route to four values. [OrchestrationResponse](../../../apps/api/src/insightrag/orchestration/contracts.py) retains the original Phase 5 and Phase 6 response objects rather than converting a decimal to a float or flattening citations.

## Graph construction and execution

[classify](../../../apps/api/src/insightrag/orchestration/graph.py) uses the existing Phase 5 query normalization for a conservative document/analytics hint. A document-only question with no IDs uses Phase 5's authorized workspace-wide document scope. Combined requests must name separate subquestions. This rule is deliberate: changing “net revenue” into “revenue” during automatic decomposition would produce a plausible but incorrect financial answer. [build_graph](../../../apps/api/src/insightrag/orchestration/graph.py) wires conditional edges and compiles the graph; [execute](../../../apps/api/src/insightrag/orchestration/graph.py) invokes it asynchronously under a wall-clock timeout and recursion limit. It does not retry a RAG call that may write a conversation turn.

`analytics` runs first in a hybrid path. [analyze](../../../apps/api/src/insightrag/analytics/service.py) checks the dataset belongs to the request workspace in the same transaction as its resource grant, then validates the finite business plan and executes fixed parameterized SQL under RLS. `document` calls the existing [RAG endpoint function](../../../apps/api/src/insightrag/retrieval/routes.py), which assembles the configured provider adapters and invokes Phase 5's permission-aware retrieval and citation checks. A 503/504 document-provider error is a partial hybrid result; a 401/403/404/409 or analytics error propagates. This protects against treating a revoked resource as merely unavailable.

`verify` checks the returned service statuses and the presence of required outputs. It does **not** redo citation-to-claim entailment; that remains a Phase 5 limitation. `synthesize` copies exact analytics values and reports the metric, unit and half-open date range. It appends a separately labeled document section only when Phase 5 answered. [build_chart](../../../apps/api/src/insightrag/orchestration/graph.py) copies decimal strings into a typed bar/line spec; it cannot invent missing data. A month-shaped dimension selects `line`, otherwise `bar`. Chart spec validation does not prove that a particular visual encoding is ideal for every metric.

## Runtime errors and example

Input: dataset plus “Revenue by region in 2025”, `year=2025`. Output: Phase 6's unchanged `AnalyticsResponse` plus a sentence such as `Verified revenue (INR), 2025-01-01 to 2026-01-01 (end exclusive): Delhi: 100.1000.` With `chart=true`, `ChartSeries.values` holds the same `"100.1000"` string. A missing dataset for “show revenue chart” produces a Pydantic 422 or clarification, depending on whether the caller explicitly set `chart`. A forbidden dataset raises `resource_not_found` from the governed service. A 20-second graph timeout maps to `orchestration_timeout` 504. All numbers here are synthetic fixture examples.

## Operational behavior

The API is still ordinary REST over HTTPS. It does not use WebSockets or SSE because this endpoint returns one bounded response; large chart/dashboard streaming is deferred. Async graph invocation lets I/O waits release the event loop; CPU-heavy parsing and embedding jobs remain in their existing workers. Sequential hybrid execution adds service latencies. No per-tenant in-memory cache exists, so a graph-level cache cannot bypass permission revocation. Logs include route, status, nodes, duration and token counts, excluding raw content. The OTel API creates a span, but an SDK/exporter must be configured by deployment to collect it.
