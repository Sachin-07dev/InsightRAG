# Code and SQL walkthrough

The [sales validator](../../../apps/api/src/insightrag/analytics/ingestion.py) defines the transaction grain: one `transaction_id` per row/version, a local `transaction_date`, region/product dimensions, signed `Decimal` revenue/cost, integer units/returns and uppercase currency. `validate_sales(ParsedDataset)` returns a typed tuple or `None` for a non-sales schema; a file that looks like sales but violates the contract raises. The [existing parser](../../../apps/api/src/insightrag/ingestion/parsers.py) bounds rows and cells, while the [worker](../../../apps/api/src/insightrag/ingestion/service.py) inserts both original JSON and typed projection before publication. A worker failure rolls back staging; a newer version swaps visibility only when publication commits.

The [migration](../../../apps/api/migrations/versions/0007_analytics.py) adds `orgs.reporting_timezone`, `analytics_sales_rows`, a scope/date index, RLS policies and a complete-region boolean. `numeric(20,4)` prevents binary-float aggregation drift. `UNIQUE(org_id,resource_id,version_id,transaction_id)` is a second duplicate defense. PostgreSQL's table owner/migration role must remain separate from the restricted runtime role.

The [request contracts](../../../apps/api/src/insightrag/analytics/contracts.py) validate lengths, UUIDs, years and currency syntax. The [planner](../../../apps/api/src/insightrag/analytics/planning.py) recognizes one approved metric and a limited period. If today in the organization's timezone is 19 February 2026, “previous three complete months” becomes `[2025-11-01,2026-02-01)`. `year=2025,comparison_year=2024` means calendar 2025 over calendar 2024; one or two explicit years in the question can be resolved, but conflicting structured filters are rejected. A recognizable regional phrase requires a matching explicit region filter. An unsupported or multi-metric question returns a clarification error.

The [service](../../../apps/api/src/insightrag/analytics/service.py) first calls `require_resource(...,'query')`, then selects the active version and authorized currencies. `_query()` only interpolates sealed server-side metric/dimension expressions; values use bound `:org`, `:resource`, `:version`, `:currency`, `:start`, `:end`, `:region`. The representative approved query is:

```sql
SELECT region, SUM(revenue) AS value, COUNT(*) AS source_rows,
       MIN(row_number) AS source_row_min, MAX(row_number) AS source_row_max
FROM analytics_sales_rows
WHERE org_id=:org AND resource_id=:resource AND version_id=:version
  AND currency=:currency AND transaction_date>=:start AND transaction_date<:end
  AND (CAST(:region AS text) IS NULL OR region=:region)
GROUP BY region ORDER BY region LIMIT 500;
```

PostgreSQL RLS filters entitled regions even if a caller omits `:region`. Profit uses `SUM(revenue)-SUM(cost)`. Margin uses `(SUM(revenue)-SUM(cost))*100/SUM(revenue)` with null for zero revenue; averaging row margins would give a different, usually wrong total. Year growth is `(current-baseline)*100/baseline` only for a positive baseline; absent, zero and negative baselines return null pending approved business meaning. `source_rows=0` and `-100` represent a dimension that had a positive baseline but no current rows. A `highest` comparison sorts verified growth with a stable dimension tie-break. National contribution requires both the explicit region and database proof that every active region is entitled; its denominator uses the same metric, currency and period with the region filter removed.

The service sets a 3-second PostgreSQL statement timeout and 8 MiB `work_mem`, caps returned groups at 500, then rechecks resource permission, policy revision and version before audit/return. The [route](../../../apps/api/src/insightrag/analytics/routes.py) exposes non-streaming REST; a bounded calculation needs one request and one response. [DuckDB](../../../apps/api/src/insightrag/analytics/local.py) is an isolated offline comparison example, not a production route.

Failure examples: malformed sales data fails the ingestion job before publication; ambiguous multi-metric language returns 422; unauthorized resource returns 404; missing governed rows returns 422 or 404 on catalog discovery; multiple currencies request explicit currency; policy/version change returns 409; timeout aborts the transaction. PostgreSQL and external provider operational errors still need production incident mapping and alerting.

After independent review, `plan_question` rejects explicit gross/net/refund qualifiers and MoM growth rather than mapping them to unsupported calculations. `validate_sales` accepts XLSX midnight datetime cells as business dates but rejects non-midnight cells. The response includes `metric_definition_version=sales-assumption-v1`, immutable uploaded `source_sha256`, and per-group minimum/maximum source row numbers. These are bounds, not a complete contributor list; historic replay still requires the retained source and a persisted immutable metric registry. A restricted-role SQL oracle and XLSX worker integration now test these paths.
