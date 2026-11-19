# Ingestion architecture and execution flows

Every diagram here describes the Phase 4 code path. The storage/embedding/scanner endpoints require operator configuration; diagrams do not claim that those services were exercised.

## Upload, progress and worker

```mermaid
sequenceDiagram
  participant U as Authorized client
  participant A as FastAPI
  participant DB as PostgreSQL/RLS
  participant AV as Malware scanner
  participant S as S3/KMS
  participant Q as Redis/Celery
  participant W as Worker
  U->>A: POST raw file + JWT + org header
  A->>DB: Resolve identity, membership, upload grant
  A->>AV: Scan bounded validated bytes
  AV-->>A: Clean or reject
  A->>S: Put UUID-keyed SSE-KMS object
  A->>DB: reserve_ingestion(hash, key, version)
  DB-->>A: created or duplicate
  A-->>U: 202 job/version IDs
  A->>Q: Dispatch signed envelope after commit
  Q->>W: At-least-once task
  W->>DB: Fresh membership and policy check
  W->>S: Get bounded bytes and verify SHA-256
  W->>DB: Stage rows + fenced publish transaction
  U->>A: GET ingestion-jobs/{id}
  A->>DB: Owner-only job status + upload capability
  DB-->>U: State/stage/attempt/error code
```

Polling is enough for seconds-to-minutes ingestion; no persistent WebSocket server, reconnect tokens or fan-out tier is justified. The client may poll with exponential backoff and stop at a terminal state. A lost queue message leaves a durable `queued` row for operator redispatch. For deletion, the existing delete API tombstones the resource immediately; the signed deletion worker sees `pending_storage`, enumerates version keys under current policy, deletes objects, then removes chunks/rows/versions and finishes the security job. Retention/legal hold can keep the job held.

## Parsing and indexing branches

```mermaid
flowchart TD
  B[Verified object bytes] --> T{Detected suffix and kind}
  T -->|PDF| P[PyMuPDF text blocks with page/block locator]
  P --> E{Page has extractable text?}
  E -->|yes| SD[Document segments]
  E -->|no; OCR enabled| O[PyMuPDF Tesseract OCR]
  E -->|no; OCR off| F[Terminal parse failure]
  O --> SD
  T -->|DOCX| D[Paragraphs/headings/tables in body order]
  D --> SD
  T -->|TXT| X[UTF-8 lines]
  X --> SD
  T -->|CSV/XLSX| R[Header, rows and source row locator]
  SD --> C[cl100k_base 512-token windows, 48 overlap]
  C --> M[Fixed 1536-dim provider batches]
  M --> V[(pgvector staged chunks + HNSW)]
  R --> N[(JSONB dataset rows with region RLS)]
  V --> PUB[Atomic publication]
  N --> PUB
```

The `ingestion_chunks` HNSW index accelerates future similarity search but no Phase 5 retrieval endpoint uses it yet. Token windows never combine unrelated page/section segments. The lexical `locator` is copied from the parser; it is not invented after retrieval. For DOCX there is no stable rendered page number, so the locator is body/table position. CSV/XLSX rows are not embedded. Empty pages without OCR and empty datasets fail.

## Version, failure, deletion

```mermaid
stateDiagram-v2
  [*] --> queued: reserve SHA/key
  queued --> running: signed worker + fresh ACL
  running --> completed: stage and publish in one commit
  running --> failed: parse/dependency failure
  failed --> running: new signed dispatch + fresh ACL
  queued --> cancelled: newer version/delete
  running --> cancelled: newer version/delete
  completed --> [*]: active_version points here
```

`latest_version` fences old jobs; `active_version` points only at successfully published data. Publication checks the job owner, current policy revision, current upload grant, non-deleted resource, latest version, and staged content. A concurrent policy change is serialized through the organization revision lock. On failure inside the staging transaction, inserts roll back. The object and failed version remain for investigation or later cleanup; an abandoned object after a pre-reservation failure requires reconciliation. Deletion blocks access immediately through resource state/RLS while physical erasure is asynchronous and backups follow the retention policy.
