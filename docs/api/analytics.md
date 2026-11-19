# Analytics API v1

All endpoints require an OIDC bearer access token and `X-Organization-ID`; current organization membership, dataset query grant and row entitlement are checked server-side. HTTPS is required in production. The service never accepts SQL text.

`GET /api/v1/analytics/datasets/{resource_id}/schema` returns the approved sales columns, metric descriptions, reporting timezone and active version only when at least one governed row is visible. A missing/unauthorized resource returns 404.

`POST /api/v1/analytics/query` accepts:

```json
{"resource_id":"DATASET_UUID","question":"Revenue by region in 2025","year":2025,"currency":"INR"}
```

Optional fields: `region`, `currency`, `year`, `comparison_year`. The planner recognizes one or two explicit years in the question; structured year filters must agree. A named regional question requires a matching explicit `region` filter so it cannot silently become an all-region total. `comparison_year` requires `year`, supports additive metrics only, and makes `growth_percent` available. A national revenue contribution requires explicit `region` and complete active-row entitlement. Multi-metric requests, vague dates, no rows in period, unsupported schema or mixed currencies without a selected code fail with a structured 422. Unauthorized resources return 404. Revocation/version races return 409. Results use decimal strings rather than JSON floats:

Explicit `gross`/`net` and before/after-refund qualifiers, plus month-over-month growth requests, return `analytics_clarification_required` (422) until the business owner approves their definitions and calculation contract. The existing `revenue` metric is signed source revenue; the API does not relabel it as gross or net. A PostgreSQL statement timeout returns `analytics_timeout` (504); other database-driver failures return the generic `analytics_unavailable` (503), without SQL or connection details.

Growth/comparison questions without two explicit years and unsupported ranking, averaging, forecasting, explanation, or per-transaction wording also return clarification. A yearly `highest ... growth` question with two years is supported; a `highest revenue` request is not silently sorted by name or by growth.

```json
{"status":"answered","metric":"revenue","definition":"Signed revenue including refunds","metric_definition_version":"sales-assumption-v1","unit":"INR","reporting_timezone":"UTC","period_start":"2025-01-01","period_end_exclusive":"2026-01-01","filters":{"currency":"INR"},"resource_id":"DATASET_UUID","version_id":"VERSION_UUID","version_number":1,"source_sha256":"SOURCE_SHA256","rows":[{"dimension":"Delhi","value":"100.1000","comparison_value":null,"growth_percent":null,"source_rows":1,"source_row_min":2,"source_row_max":2}],"notes":["Only currently authorized rows are included.","Growth is null when the comparison baseline is absent, zero, or negative."]}
```

The UUID, hash and value above are illustrative placeholders/synthetic values, not a live API result. `metric_definition_version` identifies the current *assumed* sales contract; it is not business approval. `source_sha256` identifies the immutable uploaded file. Row min/max are bounds of contributing rows in that version, **not** an enumeration of every contributing row. A full audit must replay the same authorized version and metric definition. The schema response also exposes `metric_definition_version`. See [the implementation](../modules/analytics/implementation-walkthrough.md), [security](../security/analytics-security.md) and [tests](../testing/analytics-tests.md).
