# Phase 3 security: concepts and implementation

Read with the [phase guide](../phase-03.md), [OIDC profile](../security/oidc-integration.md), [control adapters](../security/controls-and-cloud.md) and [interview questions](../interview/phase-03.md).

## Identity: what, why and how

OAuth 2.0 delegates API access; OpenID Connect adds an identity layer. The API verifies an access token issued for this API, not a login page response or an arbitrary ID token. The issuer says who authenticated the subject; local persisted membership says which business data the subject may access. These are separate authorities. See the [OpenID specification](https://openid.net/specs/openid-connect-core-1_0.html).

[auth.py](../../apps/api/src/insightrag/security/auth.py) contains `OIDCVerifier`, a reusable asynchronous verifier, and immutable `Principal`. Configuration fixes issuer, audience and HTTPS public-key endpoint. The verifier accepts bounded RS256 access JWTs with `typ=at+jwt`, required issuer/subject/audience/expiry/issued-at/not-before claims, bounded lifetime and a known key ID. It rejects ambiguous encodings/claims, unsupported algorithms and malformed public keys. Token-supplied issuer discovery, jku and role/tenant claims do not become trust configuration. JWKS fetching has a timeout, bounded body/key count, no redirects and no environment proxy inheritance. Cached public keys reduce network latency; an unknown key can trigger only a throttled refresh. Expired cache plus unavailable issuer fails closed.

The `Principal` exposes verified issuer, subject and authentication/MFA facts, not application roles. Fresh MFA requires supported signed authentication-method claims and recent authentication time. A newly refreshed token's issued-at time is not proof that the user just completed MFA. This conservative profile may require an enterprise IdP adapter; supporting every token shape silently would weaken the contract.

Production: monitor verification latency, bounded JWKS refresh failures and rejection codes without logging tokens. Short access-token life limits stale identity risk; current database membership handles immediate application revocation. Availability of the authorization server affects cold/expired caches, so deploy reliable IdP endpoints. Multi-issuer support needs a controlled registry, issuer lifecycle and per-issuer policy; arbitrary discovery remains excluded.

## Authorization and the data model

RBAC answers which capabilities a role has. ABAC narrows those capabilities using attributes. An explicit ACL identifies which principal may perform a particular action on a resource. Here a role alone never gives unrestricted private content access.

[schema.py](../../apps/api/src/insightrag/security/schema.py) describes the tables; the [migration](../../apps/api/migrations/versions/0002_tenant_security.py) freezes the actual DDL, policies and helper bodies so later Python refactors do not change old migrations.

| Tables | Purpose and relationship |
| --- | --- |
| security_users | Global issuer/subject identity, active state and clearance; one subject can join multiple organizations |
| orgs, org_memberships | Region, retention, policy revision and current organization roles/status |
| workspaces, workspace_memberships | Bounded collaboration scope and capability role within an organization |
| groups, group_memberships | Organization-local groups for explicit ACL grants |
| resources, resource_grants | Document/dataset metadata, lifecycle, classification/MFA/purpose and user-or-group action grants |
| dataset_rows, row_entitlements | Structured row payloads and explicit user/resource/region entitlement; no wildcard fallback |
| document_chunks | Active authorized document content; synthetic three-dimensional vectors only for policy tests |
| audit_events | Tenant/actor/action/outcome/request correlation, append-only to runtime |
| security_jobs | Durable actor/resource/revision/action/state cleanup intent |

Composite keys and foreign keys include organization IDs, so a valid resource UUID cannot be attached to another organization's workspace, grant, row or job. The caller cannot supply its own organization on resource creation; the verified selected context provides it.

Roles: organization owner/admin manage organization-level metadata; steward can upload/manage where explicitly permitted; analyst queries; viewer reads; auditor reads audit. Workspace manager/steward/analyst/viewer narrows capabilities. Resource actions are read/query/upload/delete/manage. Content also requires active state, clearance >= classification, required fresh MFA, compatible trusted operation purpose and workspace membership. Dataset query requires query capability plus explicit region entitlement for each row. Group grants still require current group and organization membership.

Alternative: embed role claims in JWTs. This reduces database reads but delays revocation and duplicates policy truth. Alternative: use only ACLs. This makes every capability administrative and makes least-privilege defaults harder to explain. Here current roles and ACLs intersect; attributes only restrict access further.

## PostgreSQL policy internals

RLS attaches `USING` visibility and `WITH CHECK` write constraints to tables. SQL privileges still apply: a policy cannot grant a table privilege the role lacks. Forced RLS constrains ordinary owner behavior, while superusers/BYPASSRLS remain privileged as documented by [PostgreSQL](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

Policies consult fixed helpers in the `insightrag_security` schema. A NOLOGIN, SELECT-only policy reader avoids recursive policy evaluation when checking membership and ACL tables. Every SECURITY DEFINER helper has a fixed search path and fully qualified catalog objects; runtime cannot replace the function or assume its role. SQL parameters are bound values. Internal helper execution grants are explicit rather than relying on PUBLIC defaults.

[database.py](../../apps/api/src/insightrag/security/database.py) sets verified `app.user_id`, `app.organization_id`, MFA and trusted purpose with `set_config(..., true)`. The final `true` makes these settings transaction-local. `tenant_session` opens a transaction, sets context, yields a session and commits or rolls back. A pooled connection therefore cannot retain tenant state after transaction end. Session-level `SET` would be unsafe with pooling.

This is defense against trusted-code mistakes, not a sandbox for malicious SQL. The shared runtime credential can set these context values. Tenants and LLMs never receive that credential or unrestricted SQL execution. Expose future analytics through validated read-only plans and a restricted schema, not the policy service connection.

Production: inspect helper query plans, composite ACL indexes, pool pressure and lock waits. Row policies affect keyword/vector and aggregation queries before data is returned. Index recall/ANN performance requires separate measurements; the synthetic vector test proves isolation behavior only. Dedicated databases remain an option for contractual deployment isolation.

## Request lifecycle and concurrency

[dependencies.py](../../apps/api/src/insightrag/security/dependencies.py) composes FastAPI dependencies:

1. `get_principal` obtains a bearer token, checks production HTTPS and invokes the verifier. It returns `Principal` or a safe 401/503.
2. `get_access_context` maps issuer/subject to an active identity, validates the selected organization membership from PostgreSQL, reads the current policy revision and applies Redis user/organization quotas. `X-Organization-ID` selects an organization; it does not prove membership.
3. `get_security_session` opens one tenant transaction. Function-scoped dependency teardown completes before the HTTP response is released, enabling the final current-policy revision check to abort a stale result.
4. Policy-changing routes lock and compare the organization revision before writing. Triggers increment revisions for security-relevant mutations. The route records only its own resulting revision while holding the lock; it cannot absorb an unrelated concurrent policy change.
5. On normal completion, the transaction commits with its audit event. On a security error it rolls back; a separate safe denial audit is attempted without storing the inaccessible resource contents.

[context.py](../../apps/api/src/insightrag/security/context.py) uses a frozen `AccessContext`, so callers derive a new purpose/workspace context rather than mutate shared identity. The purpose is chosen by trusted route/tool code. Client-provided purpose, role, MFA or clearance never overrides it.

An example race: an analyst reads entitled rows while an administrator revokes the grant. If revocation commits before the final revision lock/check, the API returns 409 and releases no row response. If the request acquires the final lock first, it completes before the revocation can commit. This gives an explicit authorization ordering; it cannot retract data already delivered before a later revocation. Long streaming content needs a separate design and is not exposed.

Production: short transactions reduce permission-lock contention; never hold a DB transaction across an LLM call. Organization-wide revisions are conservative and may cause retries for unrelated changes. Move to resource/subtree revisions only when measured contention or queue invalidation warrants complexity.

## Protected API implementation

[body_limits.py](../../apps/api/src/insightrag/core/body_limits.py) is an ASGI boundary before FastAPI parsing. It caps non-upload bodies at 16 KiB independently of Content-Type and counts actual chunks rather than trusting Content-Length. The exact raw upload-validation route retains authorization before its separately bounded stream. Outer request-context middleware provides safe correlated 413 responses. This bounds memory per request; edge connection/header limits and read timeouts still protect against slow clients.

[routes.py](../../apps/api/src/insightrag/security/routes.py) contains bounded server-owned SQL. Pydantic rejects extra create/grant fields and constrains IDs/action values. Resources are created quarantined with creator self-grants in the same SQL transaction. The creator identity and creating transaction ID are DB defaults inaccessible to runtime INSERT columns. A later request cannot exploit the initial-grant exception. Metadata inspection can use permitted upload/manage capability while active content still requires read/query authorization.

Grant creation checks exactly one user/group target, current resource manage permission and a bounded same-organization target eligibility helper. General membership directory visibility does not need to be expanded to implement sharing. SQL identifiers come from static server allowlists; user strings remain bound parameters. Rows/evidence limits bound output and require current access before and after reading. The evidence route returns existing authorized chunks; it is not an implemented retriever or citation generator.

Example inputs: POST a dataset title to an authorized workspace -> 201 with a new quarantine resource UUID; GET another company's resource UUID -> 404; POST an unknown grant field -> 422; GET without bearer -> 401. Detailed [API boundaries](../api/phase-03-security.md) describe routes and error semantics.

## Jobs, retention and secure deletion

[jobs.py](../../apps/api/src/insightrag/security/jobs.py) separates signing/dispatch from execution. `dispatch_job(settings, organization, actor, job_id)` reads an existing actor-owned durable job under RLS, signs a short-lived envelope and sends only that token to the registered JSON task. This CLI is a trusted operator integration, not an HTTP endpoint accepting caller identity.

`run_security_job(token, settings)` verifies the envelope, reloads current active identity/membership and matching durable resource/action/revision, applies a Redis single-use nonce, then invokes the bounded database purge function. The function locks current policy and durable job rows and checks permissions again. A signature proves integrity of delegation; it never proves that yesterday's permission still exists. Completed work returns its durable state on redelivery only when the envelope is otherwise valid, unexpired and matches current policy. A failure after nonce consumption requires a fresh dispatch token; database idempotency prevents duplicate effects.

The delete API blocks access by tombstoning immediately and writes cleanup intent atomically. The default organization retention becomes the resource retention deadline at creation; runtime cannot shorten it. Legal holds and future deadlines produce held. Database-only expired content can be removed transactionally. A real object key without storage integration returns pending_storage; the worker must not mark a blob deleted. Audit/tombstone retention and backup lifecycle remain explicit operational policies. Held work needs controlled re-enqueue after policy approval, not an automatic reset of a terminal job.

[provision.py](../../apps/api/src/insightrag/security/provision.py) is deliberately separate: it requires operator/migration credentials, registers real issuer/subject mappings and creates memberships/workspaces/groups. There is no role-changing HTTP bootstrap endpoint. Existing identity clearance is not automatically raised while adding organization membership. Operator DB actions also require independent cloud/operator audit because a privileged administrator can alter local audit data.

## Controls, production and improvements

[controls.py](../../apps/api/src/insightrag/security/controls.py) provides atomic Redis quotas, UUID-only object namespaces, user/revision/resource/version cache keys and signed job identities. Redis TIME prevents inconsistent client clocks from defining rate windows. Revision-bearing keys prevent reuse after permission changes, but a cache adapter still must reauthorize before returning content and expire old entries. Edge anonymous/IP limits, storage budgets and cost quotas require deployment controls; request quotas alone do not solve every abuse path.

[uploads.py](../../apps/api/src/insightrag/security/uploads.py) validates extension, media/signature consistency, bounded stream length, UTF-8 constraints, suspicious PDF structures and safe OOXML archive bounds before scanning through a timeout-bound ClamAV INSTREAM adapter. Missing scanner fails closed. Format markers and antivirus are layers, not proof that a parser is safe; parser sandboxing, CDR, CPU/memory/time limits and quarantine publication follow in ingestion. The [OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) likewise recommends layered validation and limits.

[crypto.py](../../apps/api/src/insightrag/security/crypto.py) implements AES-GCM envelope encryption. A random data key encrypts bytes; an injected key provider wraps that key. Authenticated associated data binds organization/resource/key ID, so swapping an envelope to another tenant fails authentication. The local key provider is test/development only. Production needs an actual cloud KMS provider, tenant IAM, rotation/rewrap and availability monitoring. TLS, disk encryption and backup encryption are separate controls.

Significant alternatives and improvement triggers: stream quarantine files when memory/concurrency warrants it; managed queues/workload identity when deploying distributed cloud workers; external policy service after measured policy distribution pain; dedicated tenant infrastructure after contractual or noisy-neighbor evidence. Do not add these merely because they are common enterprise technologies. For each change, rerun the isolation, revocation and failure-path regressions before enabling new routes.
