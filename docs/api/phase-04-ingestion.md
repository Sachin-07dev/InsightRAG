# Phase 4 ingestion API contract

The generated development contract is [OpenAPI](openapi.json). All protected routes require a verified bearer JWT and `X-Organization-ID`; authorization is server-side and current. Errors use the shared JSON error contract and request ID. API paths are versioned under `/api/v1`.

| Method/path | Request | Success | Authorization |
| --- | --- | --- | --- |
| `POST /resources/{resource_id}/versions` | Raw PDF/DOCX/TXT/CSV/XLSX bytes, `X-Filename`, matching `Content-Type`; optional `X-Reindex: true`; max 50 MiB | 202 `queued` with `job_id`, `version_id`, `sha256`, or `duplicate` version | Current workspace/resource `upload`, file kind match, clean scanner, object/queue config |
| `GET /ingestion-jobs/{job_id}` | No body | State, stage, attempts, error code and timestamps | Requesting actor plus current `upload` permission |
| `GET /ingested-documents/{resource_id}/evidence` | No body | Up to 100 active-version chunks with real locator/heading/token count | Current `read`, knowledge purpose, RLS |
| `GET /ingested-datasets/{resource_id}/rows` | No body | Up to 100 active-version structured rows | Current `query`, analytics purpose, region RLS |

`queued` means accepted into the durable PostgreSQL job catalog; it is not proof that a broker accepted the message or that indexing completed. Poll until `completed`/`failed`; an authorized operator can redispatch a stuck job. The evidence endpoint is a review/debug boundary, not full hybrid RAG retrieval. The row endpoint is not an analytics engine and does not compute totals. Results are capped and must not be treated as complete for aggregation.

Re-uploading unchanged bytes normally returns the latest version as a duplicate. `X-Reindex: true` explicitly creates a new version from those same freshly validated and scanned bytes, enabling a parser/embedding-profile rebuild. It still requires current upload permission and another private object write.

Important failures: 401 invalid/missing identity; 404 inaccessible organization/resource/job; 413 body exceeds cap; 422 unsupported/mismatched/malicious file; 503 missing scanner/storage/identity/quota dependency; 409 changed authorization at response boundary. Do not expose raw object keys or provider credentials in responses.
