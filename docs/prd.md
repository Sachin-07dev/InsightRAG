# Product requirements document

Status: Proposed. Product: InsightRAG Enterprise. Owner: project owner, not yet assigned business stakeholder names.

## Problem and intended outcomes

Organizations need trustworthy answers across private narrative and tabular information without exposing another team's or tenant's information. A conventional PDF chatbot cannot establish exact business calculations, metric semantics, dashboard lineage, or enterprise access control.

The platform retrieves document evidence, executes deterministic analytics, and presents facts, interpretations, hypotheses, and recommendations distinctly. A fluent answer is insufficient: authorized provenance and reproducibility are part of the product.

## Personas

| Persona | Need | Success |
| --- | --- | --- |
| Analyst | Trends, regional comparisons, category analysis | Reproducible calculations and visible filters |
| Knowledge worker | Policy lookup, report summary | Real citations and explicit missing evidence |
| Executive | Dashboards, recommendations | Evidence strength and freshness are understandable |
| Data steward | Upload, validate, map, version, delete | Processing state and lineage are inspectable |
| Administrator | Membership, grants, quotas, policies | Predictable control without automatic content access |
| Security reviewer | Access and retention evidence | Isolation, erasure, and audit trails can be demonstrated |
| Operator | Reliability, latency, cost, recovery | Failures are diagnosable and bounded |

## Functional requirements

| ID | Requirement | Observable acceptance |
| --- | --- | --- |
| FR-01 | Organizations, workspaces, users and groups | Switching organization never carries prior access or cached answers |
| FR-02 | PDF/DOCX/TXT/CSV/XLSX upload | Actual file content is validated and every attempt has a processing state |
| FR-03 | Authorized document Q&A | Claims cite permitted, pinned versions and real locators |
| FR-04 | Exact structured analytics | Values come from approved metric plans and deterministic execution |
| FR-05 | Combined evidence | Answer distinguishes document statements, computations, and hypotheses |
| FR-06 | Interactive visualizations | Every plotted value maps to a typed result column |
| FR-07 | Dashboards and downloadable reports | Refresh/reopen/export reauthorizes all dependencies |
| FR-08 | Versioning and incremental ingestion | Unchanged versions avoid repeated effects; failed update preserves prior publication |
| FR-09 | Deletion | New access stops at tombstone; live purge and backup expiry are tracked separately |
| FR-10 | Authorized connectors | Approved objects, network paths, credentials, and freshness contracts constrain access |
| FR-11 | Administration and audit | Authorized reviewers can inspect grants, jobs, usage, and actor events |
| FR-12 | Clarification and abstention | Ambiguous metrics and insufficient evidence produce explicit uncertainty |

Primary use cases: Delhi sales over the prior three complete calendar months; Delhi/Mumbai growth; underperforming categories; financial-report summaries; regional decline explanation; monthly trends; 2024/2025 performance; feedback recommendations; executive metrics; facts-versus-hypotheses inspection. Tests cover missing comparison periods, mixed currencies, conflicting reports, denied sources, and unavailable data.

## Nonfunctional requirements

| ID | Requirement | Gate |
| --- | --- | --- |
| NFR-01 | Tenant and resource isolation | Negative access tests across API, DB, workers, cache, exports, restore |
| NFR-02 | Numerical and evidence correctness | Golden decimal calculations and held-out claim support review |
| NFR-03 | Availability and latency | Targets measured against declared workload, including provider failures |
| NFR-04 | Recoverability | Restore drills validate RPO/RTO and deletion reconciliation |
| NFR-05 | Operability | Correlated redacted telemetry; actionable queue and budget alerts |
| NFR-06 | Maintainability | Typed contracts, migrations, backward compatibility and ADRs |
| NFR-07 | Governance | Approved residency, retention, provider handling and audit policy |
| NFR-08 | Accessibility | Keyboard navigation, contrast, readable errors, chart data tables |
| NFR-09 | Scalability and cost | Tenant quotas, worker scaling, query budgets, measured placement |

Detailed [targets](architecture/capacity-and-slos.md) are proposals. No benchmark has run.

## Milestones

| Milestone | Scope | Exit criteria |
| --- | --- | --- |
| MVP | Synthetic sales/report workflow; secure multi-tenancy; uploaded documents and datasets; cited Q&A; deterministic analytics; combined questions; charts; private saved dashboards; CSV/PDF reports | Critical user journeys, isolation, metric, provenance, update, deletion tests pass |
| Production baseline | Approved enterprise OIDC; read-only PostgreSQL connector; HA managed services; recovery; audit; quotas; evaluation and operational runbooks | Security/load/recovery gates pass; customer policies approved |
| Enterprise scale | Regional cells, dedicated tenant option, provisioning integrations, more connectors; warehouse/search specialization when justified | Placement/load evidence and contract requirements justify each addition |

MVP excludes anonymous sharing, unrestricted SQL/Python, autonomous business actions, cross-tenant learning, multi-region active-active writes, and unapproved row/column entitlement datasets. Initial data access is dataset-level; restrictive row/column requirements must be implemented before admitting such data.

## Proposed product limits and success measures

Initial per-file envelope: 50 MB/500 pages for documents, 100 MB/1 million rows for CSV/XLSX after archive expansion limits. Oversized work is rejected explicitly. OCR languages and scanned-layout support need fixture validation. These limits are assumptions to review, not discovered capabilities.

Launch evaluation: synthetic two-tenant journeys, exact golden calculations, real citation resolution, zero tolerated unauthorized disclosure, proposed recall@20 >=0.90 and supported-claim precision >=0.95 on a defined held-out set. Track clarification, task completion, usefulness, latency and per-task cost; product adoption targets need a real customer pilot.

Approval is required for customer workflow, metric owner, launch region, entitlements, retention, and workload. See [review](architecture/review.md).
