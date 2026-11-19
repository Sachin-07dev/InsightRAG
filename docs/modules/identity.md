# Identity and policy module

Phase 1 design context below is retained. The actual Phase 3 implementation, file walkthrough and operational limits are documented in the [security module guide](security-foundation.md) and [security concepts](../concepts/phase-03-security.md). Browser PKCE/BFF login and per-organization issuer onboarding remain future integration work; only the backend access-token boundary is implemented.

## WHAT

OIDC proves the signed-in identity; memberships, role capabilities and resource grants decide what it can do. Tenant context is verified application state, not a request header to trust.

## WHY

An existing identity provider avoids implementing passwords and enterprise authentication. RBAC expresses operations; resource grants express data access. Global admin-as-reader is rejected because administration need not include private content.

## HOW

Web login -> verified issuer/audience/signature/expiry and protocol protections -> internal identity keyed by issuer/subject -> current organization membership -> workspace/role/grant resolution -> scoped transaction/repository calls. Authorization revisions invalidate prior decisions. Use authorization-code flow with appropriate PKCE/state/nonce protections; exact library configuration is verified in Phase 3.

## IMPLEMENTATION

The original proposed interfaces were `resolve_context(session, organization)` and `authorize(context, capability, resource)`. Phase 3 implements this boundary with get_principal/get_access_context, immutable AccessContext, tenant_session and require_resource plus database policy helpers; see the [implementation guide](../concepts/phase-03-security.md) for exact source links. Example: an analyst can query a granted sales dataset but cannot inspect a private HR report in the same workspace. Wrong membership or missing context denies access.

## PRODUCTION

Risks include stale group membership, pool context leakage, excessive policy joins and support access. Monitor denied/allowed operation outcomes and policy latency without recording content. Use local transaction context, indexed grants and short-lived/revisioned decision caching. Do not hold transactions during model calls. Shared DB privileges remain within the trusted API boundary.

## IMPROVEMENT

SCIM/SAML integration, policy engine adoption and dedicated tenant placement follow demonstrated customer requirements. Adding row/column permissions changes analytics and aggregate disclosure design; deny affected datasets until implemented. See [interview section](../interview/phase-01.md).
