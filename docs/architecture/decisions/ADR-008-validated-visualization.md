# ADR 008 — Verified data to restricted ECharts views

Status: proposed for owner review. Phase 8 implements this bounded choice.

Context: Phase 6 returns authorized decimal aggregates, but not multi-series or coordinates. Phase 7 can route chart requests. Decision: expose a narrow Pydantic visualization contract and request-local multi-query dashboard; use ECharts SVG for line/bar plus exact HTML tables and KPI cards. Reuse trusted Phase 7/6 calls for every view. Reject unsupported stacked/scatter/geo rather than fabricate source data. Do not persist dashboards until ACL and revocation requirements are specified.

Consequences: low infrastructure cost and clear trust boundary; sequential query latency and no shared database snapshot. Alternative Plotly offers a mature React wrapper and wide scientific chart vocabulary, but does not solve data authorization. Raw ECharts options would increase flexibility while weakening the validation boundary. Revisit after actual accessibility, bundle-size and large-series measurements, and after the semantic layer exposes approved multi-measure/geographic data.
