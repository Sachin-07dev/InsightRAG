# Assumptions, risks and deferred decisions

Status: Open review register. Owners below are roles to assign, not invented people. No risk acceptance has been granted.

## Assumptions

| ID | Assumption | Owner / resolution gate |
| --- | --- | --- |
| A01 | First workflow is synthetic sales plus narrative business reports | Product owner / Phase 1 review |
| A02 | Shared tenant tables plus resource grants are an acceptable baseline | Security owner / Phase 1 review |
| A03 | Initial analytics needs dataset-level grants only | Product/security owner / before admitting data |
| A04 | Managed regional services are available | Platform owner / Phase 2 planning |
| A05 | No autonomous actions or arbitrary generated code | Product/security owner / standing scope |
| A06 | Capacity follows the explicit workload model, with skew tests | Platform owner / before sizing purchases |
| A07 | Source data is synthetic until governance is approved | Data owner / production admission gate |

## Major risks

| ID | Severity | Risk | Mitigation / evidence | Owner |
| --- | --- | --- | --- | --- |
| R01 | Critical | Tenant/resource leakage | RLS, grants, cache scoping, derived access; negative tests | Security |
| R02 | High | Wrong numbers or metric meaning | Versioned semantics, deterministic plans, golden decimals | Data |
| R03 | High | Unsupported model claims | Evidence mapping, abstention, held-out human evaluation | ML |
| R04 | Critical | Malicious tools/uploads | Restricted plans, OS sandbox, isolated parsing, no egress | Security/platform |
| R05 | High | Deletion resurrection | Tombstones, fencing, lineage invalidation, restore drill | Backend/platform |
| R06 | High | Noisy neighbor or runaway cost | Quotas, fair queues, deadlines, placement and budget alerts | Platform |
| R07 | High | Selective vector search misses relevant evidence | Exact baseline, filtered-recall evaluation, tuned scans/partitions | ML/data |
| R08 | High | Provider outage/retention mismatch | Approved profiles, bounded retries, regional policy and fallback review | ML/security |
| R09 | High | Connector exfiltration/inconsistency | Egress controls, read-only approved catalog, snapshot contract | Data/security |
| R10 | High | Jobs lost or effects duplicated | Durable jobs/outbox, stable keys, fencing, reconciliation | Backend |
| R11 | High | Sensitive observability data | Redaction, regional storage, access review and expiry | Security/platform |
| R12 | High | Recovery objectives infeasible for index size | Restore/rebuild drills and retained publication strategy | Platform |

## Deferred decisions and triggers

| Decision | Proposed deferral | Evidence to reopen |
| --- | --- | --- |
| Exact cloud, launch region, DR region | Must resolve before private data hosting | Residency, contracts and platform constraints |
| Row/column entitlement engine | Deny affected datasets until supported | First dataset needing finer entitlement |
| Vector engine split | Keep PostgreSQL initially | Filtered recall/latency or operational targets unmet after tuning |
| Warehouse | Keep bounded snapshots | Dataset size, concurrency or freshness exceeds agreed envelope |
| Kubernetes | Managed containers first | Scheduling, policy or platform standards justify cost |
| SAML/SCIM | Existing OIDC initially | Required customer federation/provisioning integration |
| Shared chat/public dashboard links | Private MVP artifacts | Explicit sharing policy and dependency access design |
| Causal recommendations | Label as hypotheses | Appropriate data, domain review and causal methodology |
| Exact model/parser/provider versions | Select in implementation | Quality, language, cost, licensing and security evaluation |

Remaining [approval items](review.md) are deliberately unresolved. Unanswered questions must not silently become production defaults.
