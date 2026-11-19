# Phase 3 interview preparation

These model answers refer to the [actual implementation](../concepts/phase-03-security.md), not a claim of deployed cloud controls. Each topic includes a design and debugging question, plus how to defend the choice.

## Identity and enterprise SSO

1. **What is OAuth versus OIDC?** OAuth delegates access; OIDC adds identity claims and authentication flows. Our API validates an access token for its audience, then resolves local membership separately.
2. **Why not trust JWT roles?** A signed claim may be valid but stale or intended for a different application. We use verified issuer/subject as identity and current DB membership/ACL as application authority.
3. **Design enterprise onboarding.** Register issuer/audience/JWKS and client flow, provision exact issuer/subject, approved organization/workspace membership, test least privilege and revocation, then add controlled lifecycle automation. Never trust an email domain alone to create admin access.
4. **Debug: tokens suddenly fail after key rotation.** Check configured issuer/audience, kid, bounded JWKS cache age/refresh failure, key profile and token timestamps using safe metadata. Do not log tokens or accept unsigned data to restore availability.
5. **Defend RS256 and strict typ.** Asymmetric verification separates signing secrets from the API. A narrow access-token profile reduces confusion with ID tokens or unsupported issuer formats. Add explicit vetted adapters when actual enterprise issuers require another profile.

## RBAC, ABAC and PostgreSQL RLS

1. **How do roles, ACLs and attributes interact?** A role permits a capability, an explicit user/group ACL grants access to a resource, and classification/MFA/purpose narrow it. Dataset rows additionally need explicit region entitlement.
2. **Why RLS as well as application checks?** It constrains trusted SQL even if a developer forgets an organization predicate. It also applies to joins/aggregations. It does not sandbox arbitrary SQL under our shared trusted service credential.
3. **Design isolation for vector and SQL access.** Carry verified transaction-local context, apply content ACL/tenant predicates in the database before return/aggregation, include tenant in foreign keys, and reauthorize derived artifacts. Separate retrieval from exact analytics.
4. **Debug: SELECT works but SELECT FOR SHARE returns no rows.** Locking reads can involve UPDATE policy restrictions. Our real integration test found this for analysts. Use the narrow active-member policy-revision lock helper; do not expand every reader's general UPDATE privilege.
5. **Defend shared DB versus database per tenant.** Shared PostgreSQL reduces operational/migration overhead and supports transactional policy checks. Dedicated databases are justified by contractual isolation, residency or measured noisy-neighbor constraints, with higher operational cost.

## API transactions, pooling and revocation

1. **Why transaction-local settings?** They disappear on commit/rollback, preventing tenant context leakage when pooled connections are reused. Session-level context risks cross-request contamination.
2. **What does a function-scoped dependency change?** Its teardown runs before response release, so a failed final authorization revision check rolls back and replaces a stale data response rather than discovering revocation after bytes were sent.
3. **Design concurrent revocation.** Lock/check policy revision before writes, increment revision on permission changes, and lock/check at final read completion. This orders the request with revocation; data delivered before a later revocation cannot be recalled.
4. **Debug: own grant changes always produce 409.** A mutation legitimately increments policy revision. Record its resulting revision only while holding the preflight org lock; blindly accepting the latest revision could absorb another concurrent mutation.
5. **Defend organization-wide revisions.** They are easy to audit and invalidate all dependent work safely. They cause unrelated retries and contention; use finer resource revisions only when measurements justify added invalidation complexity.

## Jobs, retention and deletion

1. **Why isn't a signed queue message enough?** It proves delegated payload integrity and expiry, not current membership, resource permission, retention or job state. The worker reloads these before effects.
2. **What is idempotent deletion?** Repeating completed cleanup returns durable state without redoing unsafe effects. Tombstone/job creation is atomic and the DB purge function locks state; Redis replay prevention is an extra fence, not the sole correctness mechanism.
3. **Design secure deletion across services.** Block access immediately, record durable intent/source versions, respect legal holds/retention, remove indices/content/cache/object versions using idempotent adapters, reconcile partial failures, track provider receipts and backup expiry separately.
4. **Debug: a retry is denied after a grant change.** The current org revision no longer matches the queued delegation. Reauthorize deliberately and create fresh dispatch; do not extend stale tokens or restore deleted grants automatically.
5. **Defend pending_storage.** Without a storage adapter there is no evidence a blob was erased. Returning pending is accurate and operationally actionable. Reporting completed would fabricate an external effect.

## Uploads and untrusted content

1. **Why isn't extension validation sufficient?** Names and Content-Type are attacker-controlled; validate signatures/structure, bounds and content, then scan and sandbox parsing. Every layer has limits.
2. **What makes a ZIP bomb dangerous?** Small compressed input expands into large memory/disk or many entries. Bound file size, member count, aggregate uncompressed bytes, expansion ratio and traversal/symlink/macro features before extraction.
3. **Design ingestion publication.** Receive bounded quarantine content, validate/scan, sandbox parsing, preserve provenance/version, index idempotently, then atomically publish only the still-current authorized version. Deletion/update fencing prevents stale jobs resurrecting content.
4. **Debug: all uploads return 503.** Verify scanner configuration/connectivity/signature service. Fail closed is intentional; do not treat scanner downtime as clean content. Our validation route does not store bytes even after success.
5. **Defend no automatic activation.** File validation is not a finished parser/indexer transaction. Quarantine avoids publishing incomplete or unscanned data. Phase 4 must add a separate controlled publication path.

## Encryption, quotas, auditing and operations

1. **Why envelope encryption?** Random data keys encrypt content; a managed provider wraps them. Tenant/resource/key-ID associated data detects envelope swapping. TLS, encrypted disks and key IAM remain distinct controls.
2. **Why atomic Redis quotas?** Concurrent workers must share counters and a clock. Lua and Redis TIME provide atomic window accounting; missing Redis denies protected work rather than bypassing quotas.
3. **Design tenant observability.** Emit safe structured events without tokens/content, scope tenant audit in DB, export to independently controlled immutable storage, and authorize tenant-facing views. Protect operator/global logs separately and avoid high-cardinality tenant labels in shared metrics.
4. **Debug: Company A receives a cached answer after revocation.** Inspect whether the key includes user/org/revision/resource/version and whether the adapter reauthorizes before return. A namespace helper alone cannot secure a cache adapter that skips current policy.
5. **Defend the compliance wording.** Implementing controls and passing local adversarial tests provide evidence of specific behavior. Certification/legal compliance requires deployment scope, policies, operational evidence, audits and legal review; we do not claim it from source code.

## Three conceptual review questions

1. Why does a valid signed access token plus X-Organization-ID still not prove resource access?
2. What prevents a pooled database connection or a retried job from reusing stale tenant authority?
3. Why can deletion block access immediately while complete erasure remains held or pending?
