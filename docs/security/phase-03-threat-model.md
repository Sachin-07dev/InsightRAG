# Phase 3 threat model and control boundaries

Scope: verified HTTP entry points, PostgreSQL policy boundary, quotas/caches, upload validation, signed background work and encryption adapters. Assets are private evidence, structured rows, identities, ACLs, keys, tenant audit and derived-artifact source lineage. Trust boundaries separate browser/IdP, API, runtime database role, privileged operator, Redis/worker, scanner and future storage/model providers.

| Threat and concrete attempt | Implemented control | Residual risk / required work |
| --- | --- | --- |
| Forged JWT, wrong audience or algorithm confusion | Fixed RS256 profile, signature/claims/type validation, bounded public keys | Real IdP configuration/rotation runbook; no browser login configured |
| Token-controlled JWKS URL / SSRF | Configured HTTPS JWKS only, no token URL discovery, redirects or inherited proxies | Operator configuration remains trusted; deployment egress policy required |
| Company A selects Company B header or resource UUID | Current DB membership, forced RLS, composite tenant keys, uniform inaccessible-resource 404 | Service credential compromise / arbitrary SQL bypasses trusted-context assumption |
| Viewer escalates roles or self-grants old resource | No role mutation HTTP route, explicit capabilities/ACL, creating-XID initial grant guard, restricted column privileges | Separate operator credentials and cloud IAM review required |
| Admin role automatically reads all private documents | Explicit resource grant + workspace/attribute constraints | Operators with DB privileges can bypass policies; independent auditing required |
| Restricted region leaks through totals | Dataset row RLS before aggregation, explicit entitlements | Future metric plans and chart caches must preserve same boundary and source lineage |
| Revocation races a read or queued purge | Revision triggers, lock/check ordering, fresh worker membership/resource checks | Already delivered data cannot be recalled; coarse revisions cause retries |
| Cross-tenant vector/keyword matches | Content RLS before return, actual SQL isolation tests | ANN quality/performance and production embedding dimensions unmeasured |
| Queue payload tampering/replay | HMAC envelope, expiry, Redis nonce, matching durable job, current DB reauthorization | Signing secret available only to trusted producers; rotate/reconcile failed delivery |
| Cache or object-key collision | Organization/workspace/resource/version namespaces and policy-sensitive cache keys | No content cache or object-store adapter exposed; future adapters must authorize reads |
| Upload bomb, macro, active document or malware | Byte/archive/signature/path checks, scan gate, quarantine-only lifecycle | Live scanner/signature updates, sandbox/CDR and parser limits required |
| Prompt injection asks to ignore ACLs or execute SQL | No model instructions can set identity, no generated SQL/Python execution; evidence remains data | Test future orchestrator tools/model output separately; no LLM engine exists yet |
| Old versions survive delete | Immediate tombstone, durable cleanup, retention/hold checks, DB purge | Blob versions, multipart copies, backups, search caches and replicas require provider workflow |
| Encryption envelope swapped between tenants | AES-GCM AAD binds organization/resource/key ID | Managed KMS provider, IAM, at-rest volumes, TLS and key rotation not deployed |
| Logs or telemetry reveal content/tokens | Allowlisted JSON logs omit headers, bodies, vendor text and credentials; audit is RLS-scoped | Central collectors need access-controlled tenant partitions; no tenant-facing trace endpoint |
| Flooding / scan cost abuse | Atomic user+organization Redis request quotas, bounded uploads, safe timeouts | Edge IP/WAF controls, concurrent upload limits, storage/LLM spend budgets still required |
| Runtime erases evidence of misuse | Runtime audit INSERT/SELECT only; no UPDATE/DELETE | Privileged operators can modify DB; WORM/SIEM independent export required |

Run the [regression commands](../testing/phase-03-verification.md) after any policy, helper, role, connection-pool, ingestion, analytics or artifact change. Local tests demonstrate specific adversarial scenarios; they do not certify SOC 2, ISO 27001, GDPR, HIPAA or any other legal/compliance status. Region/retention requirements need owner and legal review for the actual deployment.
