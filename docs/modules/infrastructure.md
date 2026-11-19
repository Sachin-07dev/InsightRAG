# Infrastructure, persistence and operations

## WHAT

Provides versioned environments, managed state, worker isolation, telemetry, deployment/recovery and cost control.

## WHY

Docker supports reproducible local/runtime packaging; Terraform can express reviewed infrastructure. Managed containers reduce initial operating burden. PostgreSQL combines transactional/catalog/retrieval needs; Redis is replaceable dispatch/cache state. Kubernetes and extra databases need measurable justification.

## HOW

CI validates code/contracts/security, builds signed/scanned artifacts where supported, applies controlled migrations, deploys compatible services and verifies readiness. Runtime secrets come from approved secret services. OTel correlates API/model/worker/DB stages with safe identifiers; Prometheus/Grafana or approved backends expose SLOs. Langfuse is optional after content/residency review, not enabled by default.

## IMPLEMENTATION

No infrastructure exists yet. Proposed boundaries: environment configuration, migration runner role, runtime roles, job pools, telemetry collector, retention and backup tasks. Documentation tooling currently uses only Node built-ins and no installed packages. It cannot demonstrate application reliability. See [verification](../testing/verification.md).

## PRODUCTION

Avoid holding transactions during network calls; use bounded pools, admission controls, fair queues and idempotent jobs. Monitor queue age, saturation, database I/O, index maintenance, provider quotas and restore/deletion lag. Do not put every tenant ID into high-cardinality metrics; controlled usage accounting is separate. Test recovery and rollback, not only backup success.

## IMPROVEMENT

Regional cells and dedicated placements follow tenant skew and isolation needs. Warehouses/search clusters/Kubernetes can improve specific constraints but each adds patching, backup, access and on-call work. Revisit through ADRs with measured evidence and migration plans.
