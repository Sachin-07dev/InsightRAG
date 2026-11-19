# Phase 6 analytics operations and failure diagnosis

Apply [migration 0007](../../apps/api/migrations/versions/0007_analytics.py) and [migration 0008](../../apps/api/migrations/versions/0008_analytics_scope.py) with the migration role before starting API/worker. Readiness expects `phase6` and `0008_analytics_scope`. Existing files still follow Phase 4 scanned-upload, signed-job and atomic-publication processes. Query requests use the restricted runtime role and the Phase 3 OIDC/rate-limit controls. Do not put migration credentials in API settings. The Phase 6 service sets a transaction-local resource scope after current grant validation; missing scope produces no typed sales rows.

| Symptom | Likely cause | Check and recovery |
| --- | --- | --- |
| Upload fails before publication | Missing/extra sales column, duplicate transaction ID, bad decimal/date, scanner/object failure | Inspect job stage/error code and validate synthetic reproduction; retain old active version, correct source and upload new version |
| Schema 404 | No query grant, no active version, no entitled governed rows | Check membership/grant/entitlements with an authorized admin; do not expose hidden schema |
| Query 422 clarification | Multiple metrics, missing period, mixed currency, unsupported national scope | Request explicit metric/year/currency/region or revise approved glossary; do not guess |
| Query 409 | Grant revision or active version changed during calculation | Retry with fresh authorization; investigate rapid policy/reindex churn |
| `analytics_timeout` 504 / DB saturation | PostgreSQL statement timeout, large scan, lock, poor selectivity or concurrency | Inspect `pg_stat_activity`, EXPLAIN on synthetic data, p95 latency, temp spills and pool waits; add admission/isolation before raising limits. The error body omits SQL and connection details. |
| `analytics_unavailable` 503 | Database driver failure or unavailable connection | Check database health and pool pressure; retry with backoff after recovery; avoid logging private query text. |
| Wrong total | Misunderstood signed convention, source date, currency, duplicate grain, partial row entitlement | Recompute approved SQL as the same runtime identity and version, check source transaction IDs and period bounds |
| Deleted data visible | RLS/active-version regression | Stop service and investigate; run [real RLS tests](../testing/analytics-tests.md), never rely on API filtering alone |

Monitor query request latency, timeouts, 422/409/404 counts, grouped row count, source-row count, ingestion failures, policy revisions, database CPU/buffers/temp files, and grant-denial audit events. Do not log raw private rows or query text by default. The current implementation logs audit action/resource but has no full tracing/cost dashboard or per-tenant analytic scan quota. A separate governed worker/warehouse is a future scaling path after measurement and review.
