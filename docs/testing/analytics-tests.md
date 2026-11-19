# Phase 6 validation and reproducibility

From repository root, use the locked environment:

```powershell
.venv/Scripts/pytest.exe apps/api/tests/test_analytics.py -q
.venv/Scripts/pytest.exe -q
.venv/Scripts/ruff.exe check apps/api/src apps/api/tests apps/api/migrations/versions/0007_analytics.py apps/api/migrations/versions/0008_analytics_scope.py
.venv/Scripts/ruff.exe format --check apps/api/src apps/api/tests
.venv/Scripts/mypy.exe apps/api/src
npm run check:docs
```

The [unit file](../../apps/api/tests/test_analytics.py) covers CSV parsing, exact decimal/refund arithmetic, DuckDB parity on a small synthetic sample, duplicate and invalid money rejection, non-sales classification, year boundary, national-share clarification, YoY plan, fixed SQL and ambiguous metrics. The [real-service regression](../../apps/api/tests/test_rls_integration.py) seeds Company A Delhi/Mumbai and Company B Delhi; Alice has only Company A Delhi entitlement. It expects exactly Delhi 100.1000, denies national share due incomplete region entitlement, rejects Company B and excludes tombstoned data. This test requires migrated PostgreSQL and the restricted runtime role; it is not a substitute for a production security assessment. The [general integration suite](../../apps/api/tests/test_integration.py) checks schema version and role restrictions.

Review-remediation additions: seven initially failing cases now verify gross/net/refund-qualifier and MoM fail-closed behavior. The XLSX parser test caught a real midnight-datetime rejection, which was corrected; the worker integration test now publishes an XLSX typed sales version and rejects replay. The RLS integration test compares the API-service revenue and margin with separate SQL under the restricted runtime identity, checks a small-fixture `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` executes, and verifies source hash/row bounds/metric version. The analytics HTTP test rejects Company B and a forged organization header. These do not validate FX, approved financial definitions, or production load.

Actual local results on 2026-11-19: non-integration suite **233 passed, 58 deselected**; Phase 6 unit file **13 passed**; Ruff check/format, mypy (**54 source files**), locked dependency resolution and documentation consistency (**11 checks**) passed. After the isolated Phase 3 PostgreSQL/Redis containers were started, `alembic upgrade head` applied `0007_analytics` successfully using the migration role. The real-service suite then completed **58 passed, 233 deselected**. It found an asyncpg prepared-statement error for the optional null region filter; the filter is now explicitly cast to `text`, and both the focused regression and full real-service suite passed. This verifies the synthetic RLS/version/contribution/deletion scenario against PostgreSQL, but does not establish production security, load capacity or provider-backed explanation.

After review remediation on the same date, the non-integration suite completed **244 passed, 61 deselected** and the real-service suite completed **61 passed, 244 deselected**. The focused Phase 6 unit file completed **24 passed**; the three direct Phase 6 PostgreSQL tests and analytics HTTP isolation test passed. A subsequent focused XLSX worker/source-hash test also passed after its final assertion was added. Ruff check/format, mypy (54 source files) and documentation consistency (11 checks) passed. These are synthetic correctness/security regressions, not a production benchmark. The first review document remains an audit snapshot; its remediation addendum records current status.

The additional 10,000-row synthetic regression initially **failed**: the old per-row grant policy took 19,888.908 ms for currency discovery and 23,088.798 ms for a grouped aggregate under restricted-role `EXPLAIN (ANALYZE, BUFFERS)`, so the API's 3-second statement timeout canceled currency discovery. [Migration 0008](../../apps/api/migrations/versions/0008_analytics_scope.py) now requires a transaction-local authorized resource scope, evaluates the current grant once per query, and still checks row entitlements and active version in PostgreSQL. The same test then **passed**, with cold-run SQL times of 103.498 ms and 88.416 ms, and a 544.230 ms service call; a subsequent warm run measured 19.237 ms, 18.487 ms and 205.409 ms, with 229.502 ms for the contribution request. These are local, single-user synthetic measurements, not p95, throughput or production capacity. The full integration suite after migration completed **62 passed, 244 deselected**; the focused missing/wrong-resource-scope regression passed after its final assertion was added.

The final additive-measure guard returns null growth for a negative prior total; its focused unit file completed **25 passed**. The final non-integration suite completed **245 passed, 62 deselected**. Ruff check/format, mypy (54 source files), and documentation consistency (11 checks) passed after this change. The full real-service suite completed **62 passed, 244 deselected** before the growth guard; focused Phase 6 isolation tests passed after their final assertions. Migration `0008_analytics_scope` was downgraded to `0007_analytics` and upgraded back to head in the isolated test DB; the post-upgrade schema-role and Phase 6 RLS tests both passed. This verifies the reversible policy migration on synthetic state, not a production rollback procedure.

After the final intent guards, the complete non-integration suite passed **255 tests** with 62 deselected, and the real-service integration suite passed **62 tests** with 255 deselected. Ruff check/format, mypy (54 source files), and all 11 documentation consistency tests passed. An initial integration command incorrectly mixed runtime URL-file variables with fixtures' explicit URLs, producing settings-validation errors; rerunning with only dedicated test URL-file variables passed. That command is corrected below. This was a test invocation error, not evidence of an application authorization failure.

For a fresh isolated test run, apply migrations with the migration role in a separate shell, then configure the dedicated synthetic test service URL files and run:

```powershell
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE='.secrets/phase3_migration_database_url'
.venv/Scripts/alembic.exe -c apps/api/alembic.ini upgrade head
```

In the test shell, do not set `INSIGHTRAG_DATABASE_URL_FILE` or `INSIGHTRAG_MIGRATION_DATABASE_URL_FILE`: several integration fixtures pass explicit URLs, and the settings validator rejects both forms together.

```powershell
$env:INSIGHTRAG_TEST_DATABASE_URL_FILE='.secrets/phase3_database_url'
$env:INSIGHTRAG_TEST_MIGRATION_DATABASE_URL_FILE='.secrets/phase3_migration_database_url'
$env:INSIGHTRAG_TEST_REDIS_URL_FILE='.secrets/phase3_redis_url'
.venv/Scripts/pytest.exe -q apps/api/tests -m integration
```

Never run this fixture against a production database: it creates and removes synthetic tenants. The `phase3_*` secret files are local, ignored workstation state; use equivalent dedicated files elsewhere and never print their contents. Missing service configuration skips locally and fails in CI. The executed RLS test checks exact entitled-row revenue, a denied incomplete national denominator, an authorized all-region contribution, cross-tenant denial, entitlement revocation, pooled scope reset and tombstone exclusion. Independent restricted-role SQL aggregation and a 10,000-row synthetic EXPLAIN are now executed. A restricted-role test confirms PostgreSQL cancels a deliberately slow statement at its transaction-local timeout; a unit test verifies safe 504/503 mapping. Only migration 0008's downgrade/re-upgrade was exercised. Representative concurrent-load/p95 testing, an actual 3-second API timeout, multi-currency selection, source retention and connectors remain future verification.
