# Ingestion and job module

## WHAT

Converts untrusted source bytes into validated, versioned text evidence or canonical datasets through durable asynchronous jobs.

## WHY

OCR, parsing and embedding can be slow or unsafe. Separate workers isolate resources and preserve API responsiveness. Synchronous parsing and in-place index updates are rejected because failures expose partial state and block requests.

## HOW

Authorized quarantine -> immutable verified input -> PostgreSQL job/outbox -> Celery dispatch -> scan/parse/OCR -> normalize/chunk or profile/canonicalize -> stage -> validate -> conditional publish. Jobs use stable operation keys, payload hashes, leases and increasing fencing generations. Transient failures back off with jitter; invalid input becomes terminal rather than retrying forever.

## IMPLEMENTATION

The implemented path is described in [the Phase 4 module guide](ingestion/README.md). Earlier interface names here were architectural proposals; the actual worker entry is `process_job` and publication is `insightrag_security.publish_ingestion`. A blank document fails before publication.

## PRODUCTION

Bound expanded bytes/pages, parser CPU/memory/time, temp disk and provider throughput. Parsers run without secrets/network, with minimal privileges. Separate OCR and embedding queues and enforce per-tenant fairness. Monitor queue age, stage durations, retries, empty text, locator completeness and publication failures. Broker delivery is not the durable acceptance record.

## IMPROVEMENT

Incremental reuse avoids unchanged work within compatible tenant/profile scope. Tune chunk size/overlap using retrieval evidence, not arbitrary defaults. Choose a durable workflow engine if recovery bookkeeping dominates. Never optimize by allowing stale workers to publish or deleting provenance.
