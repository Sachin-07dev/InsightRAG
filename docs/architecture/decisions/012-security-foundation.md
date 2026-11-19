# ADR 012: verified identity, database policies and bounded job delegation

Status: Proposed

Implemented for Phase 3 evaluation, pending owner review.

## Context

The Phase 2 runtime role can serve foundation metadata but has no trusted tenant identity. Phase 3 requires enforceable isolation across API, document evidence, dataset rows and background work. A caller-selected organization or token role claim cannot establish resource permission.

## Decision

Verify an explicitly configured HTTPS issuer/audience/JWKS RS256 access-token profile. Map issuer/subject to a provisioned active database identity. Resolve current organization/workspace membership, resource ACL, classification, fresh MFA, trusted purpose and explicit dataset row entitlements. Use forced PostgreSQL RLS and composite tenant foreign keys with transaction-local context under the non-owner runtime role.

Use a NOLOGIN policy-reader role with SELECT-only catalog access for fixed-search-path SECURITY DEFINER policy helpers, avoiding recursive RLS. Revoke default public function execution and deny runtime role switching. Provisioning and narrowly scoped purge functions require separately controlled privileged migration/operator credentials. The runtime has no unrestricted resource publication, retention edits or audit UPDATE/DELETE permission.

Increment organization policy revisions on security changes. Policy mutations acquire and validate the organization revision lock before writing; reads check the final revision before releasing the response. A job carries a short-lived signed tenant/actor/job/resource/revision envelope and replay nonce, but must reload membership, validate durable job state and reauthorize actual effects. Database cleanup is transactional/idempotent; holds, retention and absent blob integration produce explicit non-completion states.

## Alternatives

Application-only filtering is simpler but vulnerable to missing predicates. A database per organization offers stronger deployment separation and costs more to migrate/operate; use where contracts or measured isolation needs justify it. A shared superuser runtime is rejected. A general external policy engine is deferred until policy distribution complexity is demonstrated. Long-lived bearer tokens in jobs and caller-supplied permission payloads are rejected because revocation must take effect.

## Consequences

RLS adds policy/query-plan and privileged-helper review work. Organization-wide revisions intentionally invalidate unrelated queued work and may cause lock contention. Shared service credentials are trusted: arbitrary SQL could forge application context and is never exposed. Database administrators can bypass these controls and require separate IAM, auditing and operational separation. Cloud TLS/KMS/SIEM/residency/backup controls remain deployment requirements, not properties proved by local tests. No certification is claimed.

Evidence: [Phase 3 verification](../../testing/phase-03-verification.md). PostgreSQL documents owner/superuser/BYPASSRLS behavior and default-deny policies in its [RLS reference](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

## Validation

Run real PostgreSQL/runtime-role cross-tenant, lock, revision, retention and cleanup regressions, plus signed-token API/worker tests as described in the verification record. Local tests do not establish cloud controls.

## Revisit

Revisit when onboarding multiple enterprise issuers, deploying managed PostgreSQL, introducing a real blob/analytics/LLM adapter, or measuring unacceptable organization lock contention or job invalidation.
