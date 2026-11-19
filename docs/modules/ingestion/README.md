# Ingestion engineering guide

This guide describes the implemented **Phase 4** slice. It is a learning reference, not a claim of deployed production assurance. Begin with the [flow diagrams](architecture.md), continue through the [file-by-file walkthrough](implementation-walkthrough.md), then compare the [technology choices](technology-comparisons.md). Read the [security invariants](../../security/ingestion-security.md), [test evidence](../../testing/ingestion-tests.md), and [interview bank](../../interview/phase-04-ingestion.md). The [phase guide](../../phase-04.md) records acceptance and deferred work.

## What the system actually does

`POST /api/v1/resources/{id}/versions` accepts raw bytes with `X-Filename` and `X-Organization-ID`, authenticated via the Phase 3 OIDC and membership flow. The resource must grant `upload` and have a compatible kind. File validation checks extension, media type, PDF signature or OOXML archive structure, archive expansion, text encoding and a clean scanner verdict. The maximum source is 50 MiB. A UUID-generated key is stored with S3 SSE-KMS; a version and job are reserved in PostgreSQL. A signed Celery message requests processing after the transaction. The worker rereads current authorization and the stored hash, then parses, chunks/embeds documents or stores structured dataset rows. A single DB transaction stages rows and conditionally swaps the active version. The `GET /api/v1/ingestion-jobs/{id}` endpoint is polling-based progress. Published evidence and rows have separate guarded endpoints.

## Why these boundaries matter

Vector search retrieves relevant wording, but an approximate neighbor cannot prove an exact sum. CSV/XLSX rows go to `ingestion_dataset_rows`, not the vector index. They preserve original cell values and row locators for later typed analytical contracts. The present parser does **not** infer approved units, currencies or dates; Phase 6 must validate schemas before numerical answers. The source data is indexed and queried under authorization, never used to train the model.

`resources.active_version` is a visibility switch. A failed or stale worker can leave a queued/failed version but cannot replace the current one. RLS permits reads only for the active version and current resource ACL. Each SQL transaction sets tenant/user/MFA/purpose context locally so pooled connections do not retain a previous caller's identity.

## Local run and verification

Use [the test runbook](../../testing/ingestion-tests.md). To run services, configure the Phase 3 OIDC, scanner, Redis, signed-job key and database; additionally set `INSIGHTRAG_OBJECT_BUCKET`, `INSIGHTRAG_OBJECT_REGION`, `INSIGHTRAG_OBJECT_KMS_KEY_ID`, and an HTTPS `INSIGHTRAG_OBJECT_ENDPOINT` only for a compatible private service. Configure `INSIGHTRAG_EMBEDDING_ENDPOINT`, `INSIGHTRAG_EMBEDDING_API_KEY_FILE`, and `INSIGHTRAG_EMBEDDING_MODEL` for 1536-dimensional embeddings. IAM credentials come from the environment/instance role, not repository files. Apply `alembic upgrade head` before API/worker startup. No S3, KMS, OCR service, ClamAV daemon, or embedding provider was provisioned as part of this repository-only phase; protected upload fails closed when required controls are absent.

Example after provisioning an authorized resource and bearer token (replace placeholders with real authorized values; never commit a token):

```powershell
curl.exe -X POST "https://your-api/api/v1/resources/RESOURCE_UUID/versions" -H "Authorization: Bearer TOKEN" -H "X-Organization-ID: ORG_UUID" -H "X-Filename: report.txt" -H "Content-Type: text/plain" --data-binary "@report.txt"
curl.exe -H "Authorization: Bearer TOKEN" -H "X-Organization-ID: ORG_UUID" "https://your-api/api/v1/ingestion-jobs/JOB_UUID"
```

The response is `queued`, then polling exposes `parsing`, `embedding`, `indexing`, `published`, or `failed`. A queued/failed/abandoned job can be redispatched by a trusted operator with `python -m insightrag.ingestion.dispatch --organization-id ... --actor-id ... --job-id ...`; current policy is rechecked. Broker delivery alone is not proof of completion.

## Production and improvement

Capacity pressure appears first at 50 MiB buffering, OOXML expansion, OCR CPU, provider rate limits, per-row SQL inserts, HNSW build cost, and DB connection count. Monitor queue age, running age, retry count, parser failures, bytes/pages/rows, chunk count, empty extraction, embedding cost and latency, publication failures, RLS denials, and deletion pending time. Separate queues, quota-aware batching, streaming multipart object upload, sandboxed parsing, batch inserts/COPY, an outbox dispatcher and regional buckets are future improvements justified by measured load. See [limitations and measurable tests](../../testing/ingestion-tests.md).
