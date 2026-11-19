# Authorization and isolation contract

Historical Phase 1 design record. The implemented Phase 3 subset now includes verified backend identity, current memberships/resource grants, explicit dataset row entitlements, forced RLS and guarded cleanup. See the [Phase 3 guide](../phase-03.md), [actual API](../api/phase-03-security.md) and [verification](../testing/phase-03-verification.md). Remaining chart/retrieval/publication/cloud controls below are design requirements. Business approval of production defaults is pending.

## Policy

An organization is a tenant. A workspace organizes resources inside it. Access requires active organization membership AND permitted workspace membership AND a role capability AND a resource grant AND applicable restrictions AND an available resource/version. Default is deny. A workspace-wide resource grant is explicit, never inferred from proximity in storage.

Roles: organization owner/admin manages membership and policy; workspace manager manages workspace grants; steward uploads/versions/retires permitted data; analyst queries and creates private outputs; viewer reads permitted outputs; auditor inspects approved audit metadata. Administrative capability does not grant automatic content access. Break-glass access needs a separate approval, reason, expiry and audit event.

Original resource capability examples: read_content, query, upload_version, delete, manage_grants, export. Phase 3 implements read/query/upload/delete/manage and explicit user-region row entitlements. Column-level masking and aggregate disclosure/small-group rules remain unimplemented; datasets requiring those controls must remain unavailable until enforcement exists.

## Enforced boundaries

| Boundary | Required enforcement |
| --- | --- |
| HTTP/session | Verify identity; resolve memberships server-side; reject forged tenant context |
| PostgreSQL | Tenant RLS plus resource authorization for every content path; composite keys |
| Retrieval | Restrict SQL candidates before content/rerank/model use; final permission recheck |
| Analytics | Authorized dataset/projection, approved fields and joins, sandboxed limited execution |
| Storage | Mediated access or short-lived scoped capability after authorization; no public bucket |
| Jobs | Load trusted durable job state; do not trust broker-supplied grants or serialized credentials |
| Cache | Include organization, principal/scope, authorization revision, source/metric versions |
| Answers/charts/exports | Reauthorize dependencies on reopen/refresh/download |
| Restore | Replay tombstones and current access policy before serving restored data |

## PostgreSQL role discipline

Runtime roles are not owners, superusers or BYPASSRLS roles. Enable and force RLS on relevant tenant tables; policies need both visibility (`USING`) and write (`WITH CHECK`) behavior. Missing context yields no access. Set principal/organization context transaction-locally from verified application state and test pool reuse and rollback. Separate migrations, backups and operations from request roles. Restrict SECURITY DEFINER code, search paths, views, functions and grants; analytics cannot reach the control-plane database with arbitrary SQL.

PostgreSQL owners normally bypass RLS unless forced; superusers/BYPASSRLS always bypass. Whole-table operations are outside ordinary row policies. See [PostgreSQL documentation](https://www.postgresql.org/docs/current/ddl-rowsecurity.html). A trusted API role that sets context remains part of the trust boundary: RLS does not contain a fully compromised API.

## Revocation and derived artifacts

Increment authorization revision on membership/group/grant changes. Recheck at tool start and final response release. Buffer answer content until final checks; progress events must contain no sensitive excerpts. Shared conversation/output access cannot exceed the intersection of applicable source permissions. MVP conversations are private; any future sharing requires explicit policy design.

Previously issued object download URLs may remain usable until expiry. For strict immediate revocation, use authenticated mediated downloads with lifecycle checks; do not claim a reusable presigned URL provides immediate revocation. Expire caches and sessions appropriately. Previously downloaded files cannot be recalled.

## Acceptance

Negative tests must cover every path in the table, wrong IDs, revoked users, stale cached decisions, tenant switching, pool reuse, denied historical citations, stale workers, connector scope, logs, and restore. A finite suite is evidence of tested cases, not a proof against every attack.
