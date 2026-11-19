# Protected API boundaries

Every route below requires `Authorization: Bearer <real API access token>` and `X-Organization-ID: <selected organization UUID>`. The latter is a selector verified against current DB membership. Tenant roles and resource permissions come from the server, not client payloads. Public metadata/liveness/readiness expose no business data. Production disables development echo/docs/schema according to existing configuration.

| Method/path | Required authorization and behavior |
| --- | --- |
| GET /api/v1/me | Current identity/membership; returns only current scope and policy revision |
| GET /api/v1/workspaces | Current organization/workspace policies; max 100 |
| GET /api/v1/directory/{memberships,groups,roles} | Organization owner/admin; no private content implied by admin role |
| POST /api/v1/workspaces/{id}/resources | Current workspace upload capability, clearance/MFA; creates private quarantined resource and creator grants atomically |
| GET /api/v1/resources/{id} | Authorized resource metadata; strips object key, legal hold and internal transaction fields |
| GET /api/v1/documents/{id}/evidence | Active document read, knowledge purpose and RLS; max 20 existing chunks; no model retrieval engine |
| GET /api/v1/datasets/{id}/rows | Active dataset query, analytics purpose, row entitlements; max 100 rows; no generated SQL |
| POST /api/v1/resources/{id}/grants | Current manage permission; exactly one active same-org user or group target; allowed action enum |
| DELETE /api/v1/resources/{id}/grants/{grant} | Current manage permission; scoped grant removal |
| DELETE /api/v1/resources/{id} | Current delete permission; tombstone and durable job in one transaction; 202 means access blocked, cleanup pending |
| GET /api/v1/jobs/{id} | Actor-owned durable job state under RLS |
| GET /api/v1/audit-events | Organization owner/admin/auditor, bounded tenant-scoped events |
| POST /api/v1/resources/{id}/validate-upload | Current upload capability before/after validation; raw bounded body, X-Filename and Content-Type; scanner required; no persistence/publication |

Example create request body:

```json
{"kind":"document","title":"Synthetic quarterly report","classification":0,"require_mfa":false}
```

No organization, object key, retention override, actor role or active state can be supplied in this body. Additional fields are rejected. New UUIDs come from the server. For uploads, send the raw file bytes, not a multipart form; this is a validation boundary rather than a finished upload workflow.

Errors follow the existing safe error contract with request ID. 401 includes a bearer challenge; invalid/inaccessible resource is 404; stale policy is 409; control-plane body cap or declared upload size excess is 413; streamed file-validation size excess is 422 file_size_limit; quota is 429 with Retry-After; unavailable identity/quota/scanner is 503. Pydantic syntax/contract failures use 422 without echoing sensitive rejected values. Other database failures follow the centralized sanitized error path and return no business data.

The [generated development OpenAPI](openapi.json) is the exact route schema. Response payloads in this initial security module use bounded JSON mappings; evolving stable domain response models, pagination and artifact/citation contracts belongs with their respective feature phases. There are no arbitrary SQL, model execution, chart generation, object download, SSO callback, signup or operator provisioning HTTP endpoints.
