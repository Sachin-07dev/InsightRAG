# Implementation backlog

Status: Phase 2 foundation (B02-B04) is implemented, pending remaining runtime verification and owner review; later implementation phases remain planned. See the [current phase guide](phase-02.md) and [verification record](testing/phase-02-verification.md) for actual results and open checks. [Machine-readable backlog](backlog.json) is the source of task dependencies and acceptance criteria. Sizes S/M/L indicate relative complexity, not time commitments; estimate with the implementing team. Critical security/correctness dependencies cannot be skipped to accelerate a demo.

| Phase | Tasks | Scope and review gate |
| --- | --- | --- |
| 1 | B01 | Review design and resolve/defer important decisions explicitly |
| 2 | B02-B04 | Implemented repository, services/configuration, migration and role foundation; runtime verification and owner review pending |
| 3 | B05-B06 | Identity, memberships, RLS, resource grants, audit |
| 4 | B07-B10 | Safe immutable uploads, durable jobs, parsing, publication/deletion |
| 5 | B11 | Evaluated hybrid retrieval and real citations |
| 6 | B12-B15 | Canonical datasets, metric compiler, isolation, production connector |
| 7 | B16 | Bounded query graph and evidence contracts |
| 8 | B17-B18 | Charts, private dashboards and safe reports |
| 9 | B19 | Enterprise user/admin workflows and accessibility |
| 10 | B20-B21 | Consolidated quality, security and load release gates |
| 11 | B22-B24 | HA deployment, recovery, quotas/cost and scale review |
| 12 | B25-B26 | Documentation mastery and production readiness review |

Every JSON task specifies dependencies and an observable acceptance criterion. Open the JSON for exact IDs, scope and size. Core dependency chain: review -> foundation -> identity/policy -> ingestion -> retrieval and analytics -> orchestration -> visualization -> enterprise workflows -> evaluation -> deployment/recovery -> release review.

B03 covers PostgreSQL and Redis in the active Phase 2 scope. Object storage belongs to B07's quarantined upload work in Phase 4, when uploads need it; no storage service is required for the current foundation.

B15 is production-baseline scope and is not a dependency of the MVP orchestration route. Its placement in Phase 6 establishes connector architecture; it may remain explicitly deferred at that review if the owner chooses uploaded-data MVP first. Later baseline gates require it. Tests, tracing, redaction and teaching documentation accompany each feature; Phase 10 does not defer early verification.

No application work is authorized by a task merely appearing here. Stop after each major phase for review; record measured results and changes to assumptions. Before using private data, resolve region, provider handling, entitlements and retention. See [approval checklist](architecture/review.md).
