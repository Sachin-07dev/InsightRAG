# API and tool boundaries

Status: Proposed contracts, not implemented routes/OpenAPI. Backend domain modules communicate through typed interfaces. No endpoint executes raw user/model SQL or Python.

Historical Phase 1 scope above refers to business APIs. Phase 2 now implements operational `/health/live`, `/health/ready`, `/api/v1/meta`, development-only `/api/v1/diagnostics/echo`, `/docs` and `/api/v1/openapi.json`. The development contract is [exported](openapi.json); see [Phase 2](../phase-02.md). Future business routes below remain proposals and will use the implemented `/api/v1` prefix.

## External boundaries

| Surface | Proposed route examples | Responsibility |
| --- | --- | --- |
| Identity | `GET /v1/me`, `GET /v1/organizations` | Current verified identity and memberships; web session login/callback/logout handled separately |
| Workspaces | `GET/POST /v1/workspaces` | Organization-scoped listing/creation |
| Upload | `POST /v1/upload-sessions`, `POST /v1/upload-sessions/{id}/complete` | Authorized quarantine upload and verified immutable completion |
| Catalog | `GET /v1/resources/{id}`, `GET /v1/resources/{id}/versions`, `DELETE /v1/resources/{id}` | Resource/version lifecycle; deletion returns purge job |
| Query | `POST /v1/query-runs`, `GET /v1/query-runs/{id}`, `GET /v1/query-runs/{id}/events`, `POST /v1/query-runs/{id}/cancel` | Bounded question execution, safe progress, result/cancellation |
| Analytics | `GET /v1/metrics`, `GET /v1/datasets/{id}/schema`, `POST /v1/analyses` | Authorized catalog and typed analytical plans |
| Evidence | `GET /v1/evidence/{id}`, `GET /v1/resources/{id}/versions/{version}/content` | Current-authorized source resolution and mediated content |
| Presentation | `POST /v1/dashboards`, `POST /v1/dashboards/{id}/refresh`, `POST /v1/exports` | Constrained panels and asynchronous reports |
| Administration | `POST /v1/grants`, `GET /v1/audit-events`, `GET /v1/jobs/{id}` | Restricted policy/operations inspection |
| Connectors | `POST /v1/connections`, `POST /v1/connections/{id}/validate` | Credential references and approved catalog/network configuration |

Organization selection is verified against membership; client-provided IDs are not trusted authority. Use cursor pagination, bounded list sizes, versioned DTOs and deprecation windows. Health/readiness endpoints reveal no tenant secrets and are operationally scoped.

## Query request and response

Illustrative request (source examples are synthetic):

```json
{
  "workspace_id": "authorized-workspace-reference",
  "question": "Compare Delhi and Mumbai net sales growth",
  "conversation_id": null,
  "as_of": "2026-11-16T00:00:00Z"
}
```

IDs above are illustrative strings, not validated UUID examples or hardcoded production values. If period, metric or growth definition is missing, return a clarification outcome. The organization reporting timezone determines business boundaries, not the browser's current timezone.

Response contract: run_id, status, factual_claims with evidence IDs, interpretations, recommendations, unknowns, analytical_result references, chart_specs, source freshness, limitations and correlation_id. Monetary result values use decimal strings plus unit/currency, avoiding binary JSON-number rounding. Citations contain permitted resource/version/locator references, never invented page numbers.

Progress events: accepted, clarifying, retrieving, analyzing, validating, completed, failed, cancelled. Resume uses an event cursor; reconnect does not restart paid calls. MVP streams progress but buffers sensitive generated content until final access checks.

## Internal tool contracts

- Retrieval input: trusted context, query, permitted scope, budget, retrieval profile. Output: authorized version/locator/text records and ranking metadata.
- Analytics input: trusted context and validated metric plan. Output: typed result schema/rows or object, decimal units, source/metric versions, execution/freshness record.
- Model gateway input: approved provider profile, minimized evidence, strict response schema, budget/deadline. Output: validated candidate structure and usage metadata, never authority.
- Chart builder input: validated result reference and allowed presentation intent. Output: constrained spec bound to existing columns.
- Job execution input: durable job ID and attempt lease. Output: recorded effect receipt or classified failure; no arbitrary functions supplied by a queue message.

## Errors, retries and compatibility

Structured errors carry code, safe message, correlation_id and retryable flag. Examples: clarification_required, insufficient_evidence, invalid_file, unsupported_metric, budget_exceeded, dependency_unavailable, resource_not_found. Use 401 for invalid authentication, consistent 404 for unknown/denied resources, 409 for stale mutation/idempotency conflict, 413 for upload size, 422 for invalid plan, 429 with retry guidance for admission limits, and 503 for transient infrastructure failures. Avoid revealing another tenant's resource existence through differing detail or list counts.

Mutations accept organization-scoped Idempotency-Key plus payload hash; replay returns the original operation, conflicting payload returns 409. Use ETag/If-Match or explicit revision for mutable metadata. Async submissions return 202 and status reference. Add fields compatibly; breaking semantics require version/deprecation policy. Error bodies never contain credentials, raw SQL engine traces or unauthorized schema names.
