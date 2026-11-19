# Phase 6 analytics engineering guide

This guide describes the *implemented* bounded sales analytics slice. Begin with the [architecture](architecture.md), [file and query walkthrough](implementation-walkthrough.md), and [technology comparisons](technology-comparisons.md). The [concept guides](../../concepts/semantic-layer.md), [security model](../../security/analytics-security.md), [test evidence](../../testing/analytics-tests.md), [interview bank](../../interview/phase-06-analytics.md), and [phase guide](../../phase-06.md) expand the reasoning.

## What exists

The Phase 4 `POST /api/v1/resources/{id}/versions` upload still scans and versions CSV/XLSX. An exact sales file has headers `transaction_id,transaction_date,region,product,revenue,cost,units,returns,currency`. [Validation](../../../apps/api/src/insightrag/analytics/ingestion.py) rejects missing/extra columns, duplicate transaction IDs, invalid dates/counts, nonfinite or overprecision money and invalid currencies. The [worker](../../../apps/api/src/insightrag/ingestion/service.py) stages JSON rows and typed sales rows, then publishes an active version atomically. Unrelated spreadsheets remain generic rows and are not marketed as sales data.

`GET /api/v1/analytics/datasets/{resource_id}/schema` exposes only an authorized governed catalog. `POST /api/v1/analytics/query` accepts `resource_id`, a bounded natural-language `question`, optional `region`/`currency`, and `year`/`comparison_year`. OIDC, organization membership and resource query grant are required. Supported questions name one metric and either explicit years or the previous three complete calendar months. Optional `by region`, `by product`, and `monthly` group results for later charts. An explicit region and complete row entitlement are needed for national revenue contribution. Unsupported wording requests clarification; no raw SQL endpoint exists.

For example, a synthetic dataset with Delhi revenue `100.10` and a `-10.05` refund yields `90.05` INR under the current *assumed* signed-revenue convention; a business owner has not approved gross/net semantics. The production response is computed by PostgreSQL from authorized rows; this number is an example, not a measured customer result. A chart consumer receives `rows`, `unit`, `[period_start,period_end_exclusive)`, `filters`, source `resource_id`/`version_id`/`version_number`/`source_sha256`, `metric_definition_version`, metric description, row counts and bounded row-number locators. Min/max row numbers are not a complete contributor list. It should label an authorized-scope total accurately.

The planner now rejects explicit gross/net or before/after-refund wording, month-over-month growth, growth/comparison without two years, unsupported rankings, averages, forecasts and explanatory questions instead of returning a misleading sum. XLSX date cells parsed as midnight datetimes are accepted as business dates; non-midnight values are rejected. See the [remediation audit](PHASE_06_REVIEW_REPORT.md) for verified changes and open business decisions.

## Run and verify

Use Python 3.12 and the locked workspace dependencies. From repository root:

```powershell
uv sync --locked
.venv/Scripts/alembic.exe -c apps/api/alembic.ini upgrade head
.venv/Scripts/pytest.exe apps/api/tests/test_analytics.py -q
.venv/Scripts/ruff.exe check apps/api/src apps/api/tests
.venv/Scripts/mypy.exe apps/api/src
```

The migration command requires configured migration DB credentials and the existing PostgreSQL/pgvector security roles. Follow [the integration runbook](../../testing/analytics-tests.md) before assuming migration or RLS correctness. The API needs the same OIDC, database, Redis and rate-limit setup as Phases 3–5. It does not need an LLM to calculate a metric.

Example API body after a governed dataset has been published:

```json
{"resource_id":"DATASET_UUID","question":"What was our Delhi sales revenue during the previous three complete months?","region":"Delhi","currency":"INR"}
```

Send it to `POST /api/v1/analytics/query` with the real bearer token and `X-Organization-ID`. The API obtains the business date from the organization's timezone; it does not trust a browser clock. `year: 2025, comparison_year: 2024` requests additive-measure year-over-year comparison.

## Limits and operations

This is a governed single-fact-table engine. It has no approved joins, currency conversion, optional source connectors, live LLM explanation, full text-to-SQL, production DuckDB snapshot worker, async large-query service, or frontend chart UI. The local DuckDB adapter compares already-authorized validated rows in memory; its caller is responsible for authorization. The API never accepts it as a route. Large files still inherit the Phase 4 50 MiB and 100,000-row parser bounds, plus per-row inserts. The [scoped RLS migration](../../../apps/api/migrations/versions/0008_analytics_scope.py) corrected a measured 10,000-row timeout without dropping database permission checks; see [the actual test record](../../testing/analytics-tests.md). Monitor upload failures, query timeout/latency, scanned/grouped row counts, denied access, ambiguous queries, zero baselines and version conflicts. For scale, benchmark indexes/partitioning/materialized aggregates with realistic entitlements before adding a warehouse.
