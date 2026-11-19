# Threat model and control requirements

Status: Proposed. Assets: private sources, tenant identity/policies, credentials, analytical results, model context, derived artifacts, audit evidence and service capacity. Threat actors include malicious users/documents, compromised accounts, unsafe dependencies, misconfigured operators and compromised service components.

Trust boundaries: browser/session, API/database, broker/worker, parser/host, analytics/host, application/provider, connector/network, object download/client and restore/live service.

| Threat | Attack example | Required mitigation | Future verification |
| --- | --- | --- | --- |
| Cross-tenant access | Substitute another resource ID | RLS, composite references, grants, uniform not-found policy | API/DB negative tests |
| Indirect prompt injection | Uploaded PDF requests secret export | Treat text as evidence; restricted tools/egress; no model policy control | Adversarial documents |
| Unsafe SQL | File read, extension load, huge join | Typed plan compiler; allowlists; OS sandbox; memory/time/I/O limits | Execution containment tests |
| Parser compromise | Crafted PDF/archive or decompression bomb | Quarantine, malware scan, isolated non-root parser, no network, limits | Malformed/oversized fixtures |
| Upload mutation | Reuse signed URL after acceptance | Bind immutable object version or copy before processing | Upload race test |
| Job tampering/replay | Forged tenant or old publication message | Trusted job lookup, payload hash, idempotency and fencing | Duplicate/stale-worker tests |
| Connector SSRF | Private metadata endpoint as database host | Approved destinations, DNS/redirect/IP controls, private egress policy | Network-denial tests |
| Secret disclosure | Model gets connection credentials | Secret references, service identities, minimal executor capabilities | Secret canary/trace inspection |
| Stale authorization | Reopen answer after grant removal | Revisioned caches and final dependency checks | Revoke mid-run and reopen |
| Output injection | Markdown script, chart callback, CSV formula | Safe renderer, CSP, constrained specs, CSV neutralization | Browser/export payloads |
| Resource exhaustion | Oversized files or query fan-out | Tenant quotas, fair queues, deadlines, admission and result limits | Noisy-neighbor tests |
| Restore resurrection | Old backup restores erased material | Durable deletion ledger, reconciliation before traffic | Restore/deletion drill |
| Telemetry leakage | Raw prompts in traces | Redaction, access control, regional storage, bounded retention | Log/trace content review |
| Aggregate inference | Tiny-group metric reveals a person | Approved aggregation/disclosure policy | Small-cohort query tests |
| Supply-chain compromise | Vulnerable parser/tool adapter | Lock dependencies, scan images, patch, least privilege | CI/security review |

Defense in depth is required because prompt formatting cannot eliminate prompt injection. See [OWASP](https://genai.owasp.org/llmrisk/llm01-prompt-injection/). No unrestricted model-generated Python is permitted, including dataframe repair code or chart scripts.

Read-only SQL does not imply safe SQL. DuckDB can access files/network and load extensions; use process/OS isolation with narrowly mounted authorized input, no application secrets, no outbound network, restricted extensions and hard limits. See [DuckDB security](https://duckdb.org/security).

Residual risks: models can produce unsupported claims; authorized users can export accessible information; a compromised trusted API can misuse application privileges; shared infrastructure has timing/resource side channels. Dedicated tenant infrastructure may be required by risk assessment. No control is described as eliminating all risk.
