# Phase 4 interview question bank

Every answer describes the current code and its limits. “Project example” links to actual files. Questions are grouped by technology/decision; each has a concise interview answer, deeper mechanism, two increasingly difficult answered follow-ups, and a common error to avoid. Review [the architecture](../modules/ingestion/architecture.md) and [test evidence](../testing/ingestion-tests.md) before claiming operational experience.

## A. Async, Celery, Redis and recovery

### 1. Why use Celery rather than FastAPI BackgroundTasks for ingestion?
**Short Answer:** OCR, embedding and indexing outlive an HTTP request; Celery gives separate workers, queueing and retries while PostgreSQL stores acceptance.
**Deep Explanation:** `BackgroundTasks` runs in the API process after a response and has no durable independent worker lifecycle. Celery sends a JSON task through Redis and may redeliver after a crash. The job row is durable; broker delivery is at least once, not exactly once. Late acknowledgement and DB fencing make repeat execution safe.
**Project Example:** [worker registration](../../apps/api/src/insightrag/worker.py) and [durable job service](../../apps/api/src/insightrag/ingestion/service.py).
**Follow-up Questions:** (1) What if Redis loses the message? **Answer:** The DB job stays queued; trusted operator redispatch issues a fresh signed task. (2) What would remove manual recovery? **Answer:** Transactional outbox plus lease-based reconciler, with measured queue-age alerts.
**Common Mistakes:** Treating a queued task as proof of completed indexing or assuming Celery guarantees exactly-once execution.

### 2. What is the difference between concurrency and parallelism in this worker?
**Short Answer:** Async I/O overlaps waiting tasks; parallel processes execute CPU work simultaneously.
**Deep Explanation:** An `await` yields the event loop during network/DB calls, but CPU-bound OCR still consumes a core. `asyncio.to_thread` prevents a blocking parser call from freezing the loop; real CPU parallelism requires separate worker processes or native code releasing the GIL. Worker concurrency and memory need explicit limits.
**Project Example:** [parse call](../../apps/api/src/insightrag/ingestion/service.py) and [Celery worker](../../apps/api/src/insightrag/worker.py).
**Follow-up Questions:** (1) Is `async def` automatically faster? **Answer:** No; only yielding I/O improves concurrency. (2) How would you isolate OCR? **Answer:** Separate no-network process/queue with CPU/RAM/time quotas.
**Common Mistakes:** Calling CPU-bound code inside an async route and expecting nonblocking behavior.

### 3. How are duplicate embeddings avoided after a retry?
**Short Answer:** Stable version/job IDs, primary keys and transactional staging prevent duplicate visible rows; a matching latest SHA avoids duplicate versions.
**Deep Explanation:** Retry may call the provider again, so provider cost can repeat. But SQL staging and active-version publication occur in one transaction. If it aborts, rows roll back; if it commits, the job is completed. A second upload with identical latest hash returns the existing version. This is idempotent **effect**, not exactly-once computation.
**Project Example:** [reservation/publication functions](../../apps/api/migrations/versions/0003_ingestion.py) and [PostgreSQL test](../../apps/api/tests/test_rls_integration.py).
**Follow-up Questions:** (1) Can a retry still incur embedding cost? **Answer:** Yes, before DB commit. (2) How might compatible embeddings be reused? **Answer:** Key a private cache by tenant, source hash, parser/chunk/tokenizer/model profile and ACL policy; verify provenance and deletion propagation.
**Common Mistakes:** Using only a Redis lock or only a SHA without version/model context.

### 4. What happens if a worker crashes during indexing?
**Short Answer:** PostgreSQL rolls back the staging/publication transaction; the previous active version stays visible.
**Deep Explanation:** Chunk/row inserts and `publish_ingestion` share a transaction. A crash before commit discards all staged rows. A fresh signed dispatch can retry if the actor and policy revision remain current. The object and durable job remain. A crash after commit may cause task redelivery, but completed state blocks new work.
**Project Example:** [transactional staging](../../apps/api/src/insightrag/ingestion/service.py) and [active-version SQL](../../apps/api/migrations/versions/0003_ingestion.py).
**Follow-up Questions:** (1) What if the broker acknowledgement is lost after commit? **Answer:** Redelivery sees completed job; no new publication. (2) What if the version became outdated? **Answer:** `latest_version` fence returns stale.
**Common Mistakes:** Inserting visible chunks one at a time without an active-version gate.

### 5. How do you apply backpressure to millions of documents?
**Short Answer:** Measure queue age and resource usage, then bound per-tenant concurrency, split expensive stages and control provider rate.
**Deep Explanation:** Throughput is limited by parse CPU/RAM, OCR, embedding quotas, DB writes and HNSW maintenance. A single unbounded worker pool lets one tenant monopolize capacity. Separate queues and budgets by stage, use admission quotas, batch inserts, and a reconciler/outbox. Scale workers only after DB/provider bottlenecks are measured.
**Project Example:** [current bounded worker](../../apps/api/src/insightrag/worker.py) and [limits](../modules/ingestion/README.md); per-tenant queue fairness is deferred.
**Follow-up Questions:** (1) Which metric signals capacity first? **Answer:** Queue wait p95 by stage/tenant relative to SLO. (2) How prevent hotspot tenants? **Answer:** Weighted fair queues and tenant concurrency/token budgets.
**Common Mistakes:** Adding workers while the embedding provider or PostgreSQL is already saturated.

## B. Parsing and OCR

### 6. How does a digital PDF differ from a scanned PDF?
**Short Answer:** A digital page has extractable text operations; a scanned page may be only pixels and needs OCR.
**Deep Explanation:** PyMuPDF reads PDF text blocks, preserving page/block provenance. If none exist, OCR attempts image-to-text recognition when enabled. OCR can misread characters, tables and order; an empty page is failed rather than silently indexed.
**Project Example:** [PDF parser and OCR branch](../../apps/api/src/insightrag/ingestion/parsers.py).
**Follow-up Questions:** (1) How do you measure OCR quality? **Answer:** Character/word error rate and field/table accuracy against labeled pages. (2) When use managed OCR? **Answer:** If measured fidelity exceeds local OCR and residency/cost/security controls permit it.
**Common Mistakes:** Assuming every PDF yields reliable text or treating OCR output as exact numbers.

### 7. Why select PyMuPDF over Docling or pdfplumber initially?
**Short Answer:** It supplies page/block text and an OCR hook with a small initial integration surface.
**Deep Explanation:** Docling may better reconstruct complex layout and tables, but brings models/compute/dependencies. pdfplumber offers low-level layout tools. Selection should be revisited with labeled extraction metrics, not assumed superiority. PyMuPDF output does not solve semantic table/heading reconstruction by itself.
**Project Example:** [parser adapter](../../apps/api/src/insightrag/ingestion/parsers.py) and [comparison](../modules/ingestion/technology-comparisons.md).
**Follow-up Questions:** (1) What metric would justify Docling? **Answer:** Material improvement in table/reading-order/citation accuracy at acceptable latency/cost. (2) How deploy two parsers? **Answer:** Version parser profiles and route by document class, then compare outputs.
**Common Mistakes:** Claiming a parser is universally best or treating a PDF text block as a true table.

### 8. How would you ingest a 2 GB PDF without exhausting API memory?
**Short Answer:** Do not send it through the current 50 MiB API path; use controlled multipart object upload and streaming, sandboxed page processing.
**Deep Explanation:** A 2 GB body plus decoded pages/OCR can exceed RAM by multiples. A short-lived tenant/resource-scoped upload grant writes directly to private quarantine storage. A finalize request checks size/hash/type and scans before a job is accepted. Workers process page ranges with resource quotas and durable checkpoints; publication remains atomic. This is a future design, not implemented here.
**Project Example:** [50 MiB validator](../../apps/api/src/insightrag/security/uploads.py) and [phase limits](../phase-04.md).
**Follow-up Questions:** (1) Can one global SHA be computed without loading all bytes? **Answer:** Yes, incremental hashing while streaming. (2) How retain atomic visibility across page workers? **Answer:** Stage immutable page outputs, verify expected count/hash, then swap active version once.
**Common Mistakes:** Raising the body limit to 2 GB or storing all OCR pages in one Python list.

### 9. How are tables and headings preserved?
**Short Answer:** DOCX paragraphs, heading styles and tables retain body order and locators; PDF currently preserves blocks, not guaranteed semantic tables.
**Deep Explanation:** DOCX XML exposes paragraph/table elements and heading styles. PDF is drawing instructions, so table reconstruction is heuristic. Chunking carries the parser's locator and heading into every piece. A citation should point to the true source position, not an inferred page number for DOCX.
**Project Example:** [DOCX/PDF parsers](../../apps/api/src/insightrag/ingestion/parsers.py) and [chunk metadata](../../apps/api/src/insightrag/ingestion/chunking.py).
**Follow-up Questions:** (1) What about merged cells? **Answer:** Add a labeled fixture and explicit cell-grid normalization. (2) How validate heading detection? **Answer:** Precision/recall against annotated section boundaries.
**Common Mistakes:** Fabricating rendered DOCX page numbers or promising perfect PDF table extraction.

### 10. How do you defend a parser against malicious files?
**Short Answer:** Layer bounded validation, malware scanning, parser resource isolation and fail-closed errors.
**Deep Explanation:** Extension/MIME alone is spoofable. The validator inspects signatures, ZIP manifest/path/expansion, PDF active markers and text encoding, then requires clean scanning. Parser bugs can still exist, so production needs a patched, no-network low-privilege process with CPU/RAM/temp disk limits. Extracted text remains untrusted instructions.
**Project Example:** [upload checks](../../apps/api/src/insightrag/security/uploads.py) and [security review](../security/ingestion-security.md).
**Follow-up Questions:** (1) What if the scanner is down? **Answer:** Reject or keep quarantined; never publish. (2) How test ZIP bombs? **Answer:** Synthetic expansion/member/path fixtures plus process memory/timeout tests.
**Common Mistakes:** Assuming a clean antivirus verdict proves parser safety.

## C. Tokens, embeddings and vector indexes

### 11. How do you choose chunk size and overlap?
**Short Answer:** Respect the embedding model token limit and tune recall/citation quality versus cost on labeled questions.
**Deep Explanation:** `max_tokens=512`, `overlap=48` gives stride 464 within each source segment. Smaller chunks can improve pinpoint citations but lose context; larger chunks cost more and may dilute relevance. Overlap reduces boundary misses but duplicates storage/provider tokens. Structure and provenance matter as much as size.
**Project Example:** [token-aware chunker](../../apps/api/src/insightrag/ingestion/chunking.py).
**Follow-up Questions:** (1) Why not split by characters? **Answer:** Characters do not bound model tokens. (2) How compare policies? **Answer:** Offline grid over recall@k, answer faithfulness, locator correctness, latency and spend.
**Common Mistakes:** Declaring one chunk size optimal for every corpus/model.

### 12. What happens when the embedding model changes?
**Short Answer:** Treat it as a new vector profile and reembed/reindex; never mix incompatible spaces.
**Deep Explanation:** Two models can both output 1536 dimensions yet place concepts differently. Scores are meaningful only within a consistent model/profile. Record model ID per version, build a side-by-side index, compare labeled retrieval and switch after validation. A tokenizer change can also require re-chunking.
**Project Example:** [model ID in publication](../../apps/api/migrations/versions/0003_ingestion.py) and [provider config](../../apps/api/src/insightrag/ingestion/embeddings.py).
**Follow-up Questions:** (1) Can old and new vectors share one HNSW index? **Answer:** Physically possible if same dimensions, semantically unsafe for ranking. (2) How roll back? **Answer:** Keep old version/profile until new retrieval passes quality and access tests.
**Common Mistakes:** Assuming dimensional equality proves model compatibility.

### 13. Explain cosine, dot product and Euclidean distance.
**Short Answer:** Cosine compares angle, dot mixes angle and magnitude, Euclidean compares geometric separation.
**Deep Explanation:** `cos(a,b)=a·b/(||a||||b||)`; `L2(a,b)=sqrt(sum((a_i-b_i)^2))`. For unit vectors, dot=cos and squared L2=`2−2cos`. The selected pgvector index uses cosine distance. Zero/nonfinite vectors are rejected because cosine is undefined or meaningless.
**Project Example:** [vector validation](../../apps/api/src/insightrag/ingestion/embeddings.py) and [cosine HNSW migration](../../apps/api/migrations/versions/0003_ingestion.py).
**Follow-up Questions:** (1) Why normalize? **Answer:** It removes magnitude from dot ranking. (2) What is pgvector `<=>`? **Answer:** Cosine distance; lower ranks closer.
**Common Mistakes:** Treating similarity as factual truth or comparing scores across models.

### 14. How does HNSW work internally, and why pgvector rather than FAISS?
**Short Answer:** HNSW traverses a layered neighbor graph for approximate search; pgvector keeps vectors, metadata and RLS in PostgreSQL.
**Deep Explanation:** Sparse upper layers guide a greedy descent; denser lower layers refine candidates. Construction and larger search breadth improve recall but use RAM/CPU and latency. Exact scan is the recall baseline. FAISS is excellent for local ANN experiments, but this platform needs transactional version publication and tenant policy in the database. A dedicated vector service is justified only by measured limits.
**Project Example:** [HNSW index](../../apps/api/migrations/versions/0003_ingestion.py) and [ADR](../architecture/decisions/013-versioned-ingestion.md).
**Follow-up Questions:** (1) What if restrictive filters return too few candidates? **Answer:** Measure recall under filters; tune search breadth or use exact filtered scan. (2) How would you benchmark? **Answer:** Same authorized corpus/query set, recall@k versus p95 latency/RAM/build time.
**Common Mistakes:** Assuming an ANN index enforces tenant ACL or always finds the true nearest vector.

### 15. Why batch embeddings, and how do you validate a provider response?
**Short Answer:** Batches amortize request overhead; validate count, order, dimension, finite values and nonzero norm before indexing.
**Deep Explanation:** The adapter sends up to 32 texts per HTTPS call, retries transient 429/5xx responses and sorts returned items by provider index. A malformed batch must fail as a whole so chunk-to-vector position remains correct. Production also needs token quotas, per-tenant budgets and provider residency review.
**Project Example:** [embedding adapter](../../apps/api/src/insightrag/ingestion/embeddings.py) and [worker use](../../apps/api/src/insightrag/ingestion/service.py).
**Follow-up Questions:** (1) Can retries charge twice? **Answer:** Yes; DB idempotency does not make provider calls exactly once. (2) How handle 429? **Answer:** Respect retry-after, global rate budget, backoff/jitter and queue pressure.
**Common Mistakes:** Trusting vector length alone or ignoring provider ordering.

## D. Tenancy, versioning and deletion

### 16. Why doesn't a valid JWT and organization header prove document access?
**Short Answer:** JWT authenticates a principal; current DB membership, workspace role, resource grant and attributes authorize each action.
**Deep Explanation:** Headers are caller-supplied. A token may outlive revocation or have broad identity claims. The API resolves issuer/subject and checks current active membership, clearance, MFA, purpose and resource grant. RLS repeats the boundary for SQL reads/writes. A worker must check again because permission can change after upload.
**Project Example:** [identity dependency](../../apps/api/src/insightrag/security/dependencies.py), [resource check](../../apps/api/src/insightrag/security/database.py).
**Follow-up Questions:** (1) Where is document-level access encoded? **Answer:** Resource grants plus workspace/attribute checks. (2) Why recheck after retrieval? **Answer:** A concurrent policy change can invalidate the result before response.
**Common Mistakes:** Treating an org ID as an access token.

### 17. How do pooled database connections avoid stale permissions?
**Short Answer:** Set tenant/user/MFA/purpose with transaction-local PostgreSQL settings; clear them automatically at transaction end.
**Deep Explanation:** Session-level settings could leak the previous caller's identity when a pooled connection is reused. `set_config(...,true)` scopes values to the current transaction. Security functions/RLS read those values and current DB policy. The API also locks/checks policy revision at completion for protected responses.
**Project Example:** [tenant session](../../apps/api/src/insightrag/security/database.py) and [RLS policies](../../apps/api/migrations/versions/0003_ingestion.py).
**Follow-up Questions:** (1) What if context is missing? **Answer:** RLS fails closed, returning no rows/denial. (2) What if a raw owner connection bypasses RLS? **Answer:** It must never serve request data; test the restricted runtime role separately.
**Common Mistakes:** Using a global Python tenant variable or trusting connection pooling to reset arbitrary session state.

### 18. How do retried jobs avoid outdated authorization and versions?
**Short Answer:** Signed claims identify a job, but current membership, grant, policy revision and `latest_version` are checked before publish.
**Deep Explanation:** HMAC prevents forged identity, not revocation. The worker reloads the job owner and organization revision; SQL publication compares stored revision and the latest version under locks. If permission changed or a newer version was reserved, old work cannot become active even after expensive embedding.
**Project Example:** [worker reauthorization](../../apps/api/src/insightrag/ingestion/service.py) and [publication function](../../apps/api/migrations/versions/0003_ingestion.py).
**Follow-up Questions:** (1) What if a grant changes mid-embedding? **Answer:** Final revision/grant check denies publication. (2) Why also compare version? **Answer:** Policy can be unchanged while a newer source supersedes the job.
**Common Mistakes:** Trusting the original signed envelope as permanent permission.

### 19. How can deletion deny access immediately while physical erasure is pending?
**Short Answer:** Tombstone the resource first; RLS denies reads, then a guarded worker deletes storage and DB descendants.
**Deep Explanation:** Physical S3 deletion, replication and backups are asynchronous. The Phase 4 deletion guard returns `pending_storage` while version keys exist. The worker checks hold/retention/current policy, deletes keys, then finalizes SQL cleanup. A failed S3 call must leave the job pending. Backup expiry is a separate operational policy.
**Project Example:** [deletion guard](../../apps/api/migrations/versions/0004_ingestion_deletion.py) and [worker cleanup](../../apps/api/src/insightrag/security/jobs.py).
**Follow-up Questions:** (1) Can a stale worker restore deleted chunks? **Answer:** Publication checks resource state and latest version, so no. (2) How prove erasure? **Answer:** Record storage deletion receipts and audit backup/replica retention; this phase does not verify those cloud controls.
**Common Mistakes:** Reporting “deleted everywhere” after only changing a DB flag.

### 20. What happens when two uploads race for one document?
**Short Answer:** Reservation locks the resource, assigns increasing version numbers and sets `latest_version`; only the latest can publish.
**Deep Explanation:** Without a lock, both requests could derive the same version or publish out of order. The SQL function serializes reservation on the resource row. A hash matching the latest queued/processing/published version returns a duplicate result. Older workers may complete computation but publication returns stale.
**Project Example:** [reservation SQL](../../apps/api/migrations/versions/0003_ingestion.py) and [integration test](../../apps/api/tests/test_rls_integration.py).
**Follow-up Questions:** (1) Does this prevent duplicate object writes? **Answer:** The API can still create an orphan/duplicate object before reservation; reconciliation is needed. (2) How test concurrency? **Answer:** Parallel uploads against a real DB and assert one latest version and no duplicate visible chunks.
**Common Mistakes:** Using only client-supplied version numbers or publishing in completion order.

## E. Networking, storage and structured analytics

### 21. How would you report progress to thousands of clients, and when use WebSockets?
**Short Answer:** Start with authenticated polling for coarse states; measure load, then consider SSE for one-way updates or WebSockets for bidirectional sessions.
**Deep Explanation:** Polling is stateless and proxy-friendly but creates repeated requests. SSE streams server-to-client HTTP events and supports reconnection. WebSockets start with an HTTP handshake and maintain a full-duplex connection, adding connection/auth refresh/fan-out complexity. This ingestion job changes stages infrequently, so current polling is proportionate.
**Project Example:** [status endpoint](../../apps/api/src/insightrag/ingestion/routes.py) and [networking guide](../concepts/networking-and-protocols.md).
**Follow-up Questions:** (1) How reauthorize a long-lived SSE connection? **Answer:** Check on connect and periodically/at each event, terminate on revocation. (2) What if a client reconnects? **Answer:** Resume from durable job state or an event cursor; never trust client-supplied stage.
**Common Mistakes:** Choosing WebSockets because a progress bar exists.

### 22. Explain TCP, UDP, HTTP/2, HTTP/3 and TLS in this upload path.
**Short Answer:** HTTP is application-layer; HTTP/1.1/2 usually use TCP and TLS, while HTTP/3 uses QUIC over UDP with built-in encryption/reliability.
**Deep Explanation:** TCP provides ordered reliable byte streams. UDP is datagram transport without TCP's stream guarantee; QUIC implements reliable multiplexed streams and congestion control over UDP. TLS authenticates/encrypts transport. WebSockets commonly run over TLS/TCP after HTTP upgrade; the current REST upload uses HTTPS. Neither TCP nor UDP is universally better.
**Project Example:** [REST route](../../apps/api/src/insightrag/ingestion/routes.py) and [S3 HTTPS adapter](../../apps/api/src/insightrag/ingestion/storage.py).
**Follow-up Questions:** (1) Does HTTP/3 make upload parsing safer? **Answer:** No; parser/security validation is an application concern. (2) Why TLS on S3? **Answer:** Confidentiality/integrity of private bytes in transit plus endpoint authentication.
**Common Mistakes:** Calling WebSocket a transport protocol or equating UDP with unreliable application behavior in all cases.

### 23. Why are CSV/XLSX rows separate from document vectors?
**Short Answer:** Vector neighbors can find relevant descriptions but cannot guarantee complete, exact sums, filters or date boundaries.
**Deep Explanation:** Embedding similarity is approximate and may omit rows. `100.10 + 200.20` should be computed as `Decimal('300.30')` or typed SQL numeric over all authorized rows. The current ingestion stores rows and region entitlements, but Phase 6 must validate column types, currency/unit, timezone, date semantics and allowed analytical queries before answering totals. Pandas/DuckDB can help staged profiling; a warehouse can handle measured scale.
**Project Example:** [CSV/XLSX parser](../../apps/api/src/insightrag/ingestion/parsers.py), [dataset table](../../apps/api/migrations/versions/0003_ingestion.py), and [synthetic numeric test](../../apps/api/tests/test_ingestion.py).
**Follow-up Questions:** (1) Why not float for money? **Answer:** Binary floats can introduce representation error; use decimal/numeric. (2) How compare Delhi and Mumbai growth? **Answer:** Approved net-sales metric, complete monthly boundaries, region entitlement, SQL grouping, then deterministic ratio calculation.
**Common Mistakes:** Summing retrieved text snippets or inventing units from a column name.

### 24. How do you protect a private S3 source object?
**Short Answer:** Generate a scoped opaque key, require private bucket/IAM and SSE-KMS, use HTTPS and never expose raw keys as public links.
**Deep Explanation:** The API constructs org/workspace/resource/version UUID paths and checks the grammar. Storage uses an operator-configured bucket, region and KMS key; IAM supplies credentials. Database RLS does not secure S3, so bucket policy, private endpoint, key access, retention and deletion must be deployed separately. SHA-256 checks corruption/substitution when a worker reads the object.
**Project Example:** [key grammar](../../apps/api/src/insightrag/security/controls.py), [storage adapter](../../apps/api/src/insightrag/ingestion/storage.py), [worker hash check](../../apps/api/src/insightrag/ingestion/service.py).
**Follow-up Questions:** (1) What if a DB transaction fails after S3 put? **Answer:** A possible orphan needs an object reconciliation job. (2) How support residency? **Answer:** Region-specific buckets, KMS and routing with audited cross-region replication settings.
**Common Mistakes:** Assuming an org-prefixed key alone is an access-control policy.

### 25. What evidence would justify moving analytics to DuckDB or a warehouse?
**Short Answer:** Measured row volume, query latency, concurrency and workload isolation exceeding PostgreSQL's acceptable envelope.
**Deep Explanation:** The current JSONB row path preserves ingestion provenance but does not define typed analytical metrics. DuckDB is useful for columnar scans on bounded files; a managed warehouse scales governed concurrent analytical queries. Either adds data movement, entitlement propagation, freshness and deletion complexity. First define exact metric semantics and test numerical correctness on the present row data.
**Project Example:** [dataset ingestion](../../apps/api/src/insightrag/ingestion/service.py) and [technology matrix](../modules/ingestion/technology-comparisons.md).
**Follow-up Questions:** (1) How preserve row ACL in DuckDB? **Answer:** Apply an authorized, scoped extract or typed policy filter before execution; verify counts and lineage. (2) How prevent stale warehouse rows after deletion? **Answer:** Versioned publication/tombstone propagation with lag SLO and reconciliation checks.
**Common Mistakes:** Introducing a warehouse before semantics and permissions are defined.

## Three review questions for the project owner

1. If an embedding provider succeeds but `latest_version` changes before publication, what remains visible and why?
2. Why can a valid JWT and a correct organization ID still fail a document upload?
3. For `Delhi 100.10` and `Mumbai 200.20`, why should a sales total come from a typed analytical path rather than the vector index?
