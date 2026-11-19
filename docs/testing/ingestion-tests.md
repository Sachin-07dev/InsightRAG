# Phase 4 verification and measurable quality gates

## Actual execution

This run used Python 3.12, the locked `uv` environment, a synthetic isolated PostgreSQL/pgvector instance and Redis. Migrations `0003_ingestion`, `0004_ingestion_deletion`, and `0005_reindex` were applied to head. The Phase 4 synthetic unit tests passed **9/9** after packaging the pinned offline tokenizer table. The entire non-integration backend suite passed **214/214**; the real-service suite at revision 0005 passed **55/55**, including API upload with fake storage/scanner and post-commit dispatch, worker processing with fake storage/embedding, and real PostgreSQL publication/isolation, reindex, and deletion tests. `ruff check .`, `ruff format --check .`, `mypy apps/api/src`, offline wheel build/tokenizer inclusion, and the real Uvicorn HTTP smoke also passed. No real S3/KMS, malware daemon, hosted embedding endpoint or Tesseract OCR quality corpus was exercised. These checks demonstrate contracts and DB isolation, not deployed production behavior.

```powershell
$env:UV_CACHE_DIR='D:\projects\RAG\work\uv-cache'
uv sync --locked --all-packages
uv run --locked --no-sync ruff check .
uv run --locked --no-sync ruff format --check .
uv run --locked --no-sync mypy apps/api/src
uv run --locked --no-sync pytest -q apps/api/tests -m 'not integration'
docker --context desktop-linux compose --project-directory . -f work/phase3-compose.json -p insightrag-phase3 up -d --wait postgres redis
$env:INSIGHTRAG_MIGRATION_DATABASE_URL_FILE='.secrets/phase3_migration_database_url'
uv run --locked --no-sync alembic -c apps/api/alembic.ini upgrade head
$env:INSIGHTRAG_TEST_DATABASE_URL_FILE='.secrets/phase3_database_url'
$env:INSIGHTRAG_TEST_MIGRATION_DATABASE_URL_FILE='.secrets/phase3_migration_database_url'
$env:INSIGHTRAG_TEST_REDIS_URL_FILE='.secrets/phase3_redis_url'
uv run --locked --no-sync pytest -q -m integration apps/api/tests
```

The `work/phase3-compose.json` and `.secrets/*` files are ignored local fixtures from the Phase 3 isolated test setup, not portable repository assets. Use [the Phase 3 runbook](../operations/phase-03-security.md) to create your own secrets and test services; do not copy credentials from another machine. Never run the migration replay or destructive cleanup tests on a shared production DB.

## Quality and failure matrix

| Gate | Present automated check | Additional measurable acceptance before production |
| --- | --- | --- |
| PDF extraction and provenance | Synthetic one-page PDF text and page/block locator | Labeled corpus: text recall, reading order, page-citation accuracy and table-cell accuracy per document class. |
| OCR fallback | Empty scanned page fails when OCR is off | Tesseract-enabled fixture; character/word error rate and page coverage on representative scanned languages. |
| DOCX heading/table | Synthetic heading and table retained with locators | Multicolumn, merged-cell and complex style fixtures; no invented page references. |
| Chunk completeness | Token ceiling, heading and source locator check | Reconstruct every source token with overlap accounting; labeled retrieval recall/citation precision against size and overlap grid. |
| Embedding dimensionality | Reject wrong dimension and zero vector | Provider mock for NaN, malformed/duplicate index, 429 retry, batch count, cost and rate-limit behavior. |
| Indexing/publication | PostgreSQL inserts staged 1536D vector then publishes | Check count/hash of all chunks, HNSW query recall@k versus exact scan, atomic rollback after injected crash. |
| Isolation and ACL | A/B runtime-role RLS publication test plus Phase 3 ACL tests | Revoke grant during parse, pooled-connection reuse, row entitlement on versioned dataset, MFA and purpose-specific worker tests. |
| Retry/idempotency | Duplicate SHA returns existing version; stale older job rejected | Concurrent duplicate uploads, crash/restart at every stage, outbox loss, fresh-token redispatch, attempt cap. |
| Update/deletion | Active-version swap tested; new deletion guard exists | Live fake-S3 deletion test, hold/retention, backup policy, stale worker after tombstone, erasure receipt. |
| Malicious/unsupported | Existing upload-validator suite and one unsupported extension test | Parser sandbox escape/zip bomb/fuzz tests, malware daemon unavailable/infected cases, file-size edge. |
| Structured numerical accuracy | CSV strings summed with `Decimal` in a synthetic test; XLSX row parsed | Phase 6 typed schema, money/units/timezone validation, exact SQL aggregates and entitlement-filtered totals. |
| Concurrency/performance | No benchmark claimed | 10/100/1000 concurrent upload tests with p50/p95 latency, RSS peak, queue age, DB/HNSW CPU/RAM and provider spend. |

These gates distinguish executed checks from work still required. A 2 GB PDF is rejected by design at the 50 MiB boundary; its interview/system-design solution is in [the question bank](../interview/phase-04-ingestion.md).
