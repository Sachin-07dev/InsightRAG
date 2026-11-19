# ADR 013 — Bounded versioned ingestion and atomic publication

**Status: proposed for owner review.** Phase 4 implementation exists, but this ADR is not owner-approved.

## Context and decision

Documents must remain private, versioned and unavailable until parsing/embedding completes. Structured numerical rows must retain exact values instead of being represented solely by vectors. The chosen first implementation uses a 50 MiB REST upload, existing fail-closed scanner, S3-compatible SSE-KMS object adapter, PostgreSQL durable job/version catalog, Celery/Redis processing, PyMuPDF/python-docx/openpyxl parsers, pinned token windows, configurable 1536D embeddings, PostgreSQL/pgvector staging and a conditional active-version swap. Polling returns progress. Source and current ACL checks precede every operation. The exact interfaces are in [the walkthrough](../../modules/ingestion/implementation-walkthrough.md).

## Consequences and alternatives

One database can atomically stage evidence and publish a version while RLS filters active rows; it also concentrates write/index load. HNSW is installed for future retrieval and requires memory/build time; no retrieval-quality claim is made yet. Celery is better than in-process background work for durable retries, but Redis transport alone is not the acceptance record; PostgreSQL remains the job ledger. Polling is simpler than WebSockets for coarse job progress. PyMuPDF is lighter to integrate than a full layout pipeline but does not recover all tables/headings accurately. The source-size ceiling and in-process expansion are intentional initial limits, not a 2 GB solution. A dedicated vector engine, Docling, managed OCR, SSE, RabbitMQ, typed warehouse, streaming multipart and workflow engine can be introduced when measured quality/load warrants them.

## Invariants and review triggers

Only current authorized users can queue or read data. Stale policy revision, deleted resource, or older version cannot publish. Retries cannot create duplicate visible chunks. Every published document chunk has a real locator and full 1536D vector. CSV/XLSX rows stay in a separate RLS-protected table. The erasure job must not report completion while versioned blobs remain. Review this ADR after labeled extraction/retrieval evaluation, p95 queue age and latency measurements, a cloud security design, and a deletion/recovery exercise with real object storage.
