# Acceptance and evaluation plan

Status: Future application tests, not executed. Documentation validation is [separate](verification.md). Every suite uses synthetic tenant data unless separately approved.

## Layers and essential fixtures

| Layer | Scenarios | Acceptance |
| --- | --- | --- |
| Unit | Decimal sums, null/zero denominators, leap/DST/calendar boundaries, allowed plans, chart schema | Exact approved results and classified invalid inputs |
| Integration | Upload/publication, source locators, snapshots/results, failed update, dependency purge | Consistent pinned evidence and visible partial failure |
| Identity/isolation | Wrong tenant/workspace/resource IDs, role ownership, pool reuse, revoked group/user | Every denied fixture remains denied across all access paths |
| SQL containment | File reads, network, extensions, unsafe functions, unauthorized schemas, huge joins | Rejected plans or terminated isolated execution with no disclosure |
| Input security | Corrupt/empty/encrypted files, archive bombs, MIME mismatch, malicious document instructions | Visible rejection or isolated failure; no unsafe execution |
| Job correctness | Duplicate dispatch, crash at commit/ack, lease expiry, broker loss, stale update/delete | One valid effect, no resurrection, reconciled accepted intent |
| Artifacts | Revoked citations, cache hits, charts, mixed-source reports, download expiry | Reauthorization and conservative invalidation |
| Browser/accessibility | Login, tenant switch, upload, clarify, cite, dashboard, admin, keyboard/table | Critical journeys usable without exposing unauthorized data |
| Load/resilience | Tenant skew, OCR bursts, indexing, provider throttle, dashboard fan-out, DB failover | Publish workload/percentiles/errors; match reviewed envelope |
| Recovery | Restore metadata/objects, deletion-ledger replay, index readiness, job fencing | Measured RPO/RTO plus isolation before reopening |

## Proposed numerical and RAG gates

Golden metrics compare exact decimals with explicit rounding; include discounts/returns/cancellations, duplicate joins, mixed currencies, missing periods and timezone boundaries. Expected values are independently authored, not computed by the code under test.

Initial retrieval recall@20 >=0.90 on a labeled authorized corpus. Supported factual claims >=95% on held-out answers using a documented human rubric; report sample size, query strata, reviewer disagreements and uncertainty. Citation resolution/authorization is required for every released reference. LLM-as-judge may assist triage but is not the sole ground truth. Include adversarial unanswerable/conflicting questions to measure abstention and clarification.

No tolerated unauthorized disclosure in the tested suite. That is a release criterion, not proof that every future attack is impossible. Prompt injection needs both model behavior evaluation and structural tool/data-access tests.

## Traceability and release

[Coverage manifest](phase1-manifest.json) maps every PRD requirement to backlog tasks and all fourteen design deliverables to files. Later phases link actual test names and CI evidence to those tasks. Phase 10 consolidates gates; each earlier feature adds its own tests and telemetry. No production label before review of functional, quality, security, load, recovery and governance evidence.
