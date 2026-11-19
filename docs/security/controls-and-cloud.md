# Security adapters, upload quarantine and cloud control boundary

Status: application adapters implemented for Phase 3; managed cloud/KMS/scanner services are not fabricated. Live-service evidence is recorded by the phase verification report, not inferred from unit doubles. These controls complement identity, current database policy and RLS; they do not grant access by themselves.

## Scoped identifiers and worker protection

**WHAT:** `security/controls.py` contains cache/object namespace functions, Redis rate limiting and HMAC worker envelopes. **WHY:** cached results, object paths and background messages are alternative routes around an otherwise correct HTTP authorization check. Putting only `tenant_id` in an API query is insufficient.

`cache_key(organization_id, user_id, policy_revision, resource_id, version_id, purpose)` hashes the complete access/version identity. It includes no question, excerpt or arbitrary user-supplied key material. A new permission revision produces a different namespace. Invalidation still needs policy revision updates and bounded cache expiry; hashing does not make stored content public or erase an old value.

`object_key(org, workspace, resource, version)` uses UUID values and a fixed grammar; original filenames never become storage paths. `assert_object_scope(key, org, workspace)` validates that whole grammar, canonical UUID encoding, organization and workspace. A same-prefix traversal suffix or encoded path segment is rejected. The object store must also deny public access and enforce service IAM; namespace checks are not a replacement for authorization.

**HOW:** `RateLimiter.check` runs one Lua script with Redis TIME, a period/count hash, and expiry. Redis serializes that server-side operation; concurrent requests cannot perform separate non-atomic read/increment steps. The fixed window is scoped to organization, user and trusted purpose. It may admit a boundary burst across adjacent windows; a sliding/token bucket policy can replace it if measurements justify the complexity. Per-organization aggregate/concurrency/spend quotas are additional controls, not provided automatically by this user-scoped counter. Missing/failed/timed-out Redis fails closed as `ControlUnavailable`; an exhausted healthy quota raises `RateLimitExceeded(retry_after)` for a safe 429 response. Configure accepted limits server-side, never from model instructions.

`SignedJobEnvelope` authenticates UUID organization/user/job/resource claims, policy revision, issue/expiry times and random nonce using HMAC-SHA256 with a >=32-byte configured secret. Envelopes live at most five minutes; comparisons use `hmac.compare_digest`. `verify_once` adds Redis SET NX replay protection until expiry. Payloads contain no credentials, raw storage paths, callable names or embedded grants. Signature validity proves message authenticity, not current permission. Before every data tool, reload the durable job and current membership/resource policy, compare identities/revision/fencing state and reauthorize. A business retry needs a newly authorized envelope; durable operation identity and effect receipts still make business effects idempotent. Redis replay state is not the durable job registry. Redis loss/eviction can remove consumed markers, so configure a protected non-evicting control store and retain durable lease/fencing/effect checks independently.

**PRODUCTION:** configure a separate worker-signing secret, restrict broker/Redis access, rotate signing keys with a deliberate overlap policy and keep clocks synchronized. Short-lived envelopes plus DB reauthorization limit stale work; rotation/revocation and broker loss need operational drills. Only an approved internal scheduler should issue envelopes. Do not expose a generic signed-job minting endpoint.

## Upload validation and malware scanning

**WHAT:** `security/uploads.py` incrementally counts an async byte stream into a bounded buffer, detects allowed content and requires a clean scanner verdict. It returns immutable `ValidatedUpload(filename, suffix, media_type, sha256, size_bytes)` metadata. **WHY:** extension/MIME alone are attacker-controlled; upload validation, scanning, isolated parsing and publication are separate safeguards.

Allowed types are PDF, DOCX, TXT, CSV and XLSX. The default file cap is 50 MiB; each incoming chunk is checked before accumulation. Unsafe/path-like filenames, type mismatches, empty/binary text and visible active/encrypted PDF markers are rejected. PDF header checks are preliminary, not a complete PDF parser or guarantee against embedded malicious content.

DOCX/XLSX are inspected without extracting files. Checks bound members to 1,000, aggregate expanded bytes to 200 MiB and per-member compression ratio to 100:1. Paths, duplicates, symlinks, encrypted members, unsupported compression, macro-bearing/nested archives and mismatched OOXML manifests are rejected. Every member is read in bounded chunks to validate actual decompression/CRC, rather than trusting central-directory sizes alone. ZIP work runs in a thread to avoid blocking the event loop; a thread is not an OS sandbox or a hard CPU kill boundary. Phase 4 must parse in an isolated worker with hard memory/CPU/temp-disk/time limits.

TXT/CSV must be UTF-8-compatible text without binary controls. No spreadsheet formula is executed; formula-cell and export-injection handling still belongs to later data-import/export paths. Validation does not make HTML-like text safe to render as HTML. Use safe output rendering.

`MalwareScanner.scan(bytes)` returns `clean` or `infected`. No configured scanner means `UnavailableScanner`, which denies acceptance. An unavailable, timed-out, malformed or unknown verdict also denies acceptance; it never becomes clean. The outer validator bounds scanner time. `ClamAVScanner` implements actual clamd `zINSTREAM` framing: command, network-order chunk lengths, chunks, zero-length terminator, then a bounded NUL-terminated response. Only `stream: OK` is clean; FOUND is infected; other responses fail closed. A local test daemon verifies protocol behavior but is not a live signature-engine evaluation.

Clamd's TCP protocol has no built-in authentication/TLS. Its host/port must come from approved server configuration, be unreachable from public/user networks, and use private authenticated transport controls where required. Never let an upload request choose a scanner URL. Keep signatures fresh, set compatible StreamMaxLength/archive limits, alert on scanner age/outage, and keep rejected bytes in controlled quarantine only under retention policy. Signature scanning reduces risk; it does not prove all malware absent. See the [ClamAV scanning guide](https://docs.clamav.net/manual/Usage/Scanning.html) and [OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).

## Envelope encryption and managed keys

**WHAT:** `security/crypto.py` provides AES-256-GCM envelope encryption. `EnvelopeCipher.encrypt(org, resource, plaintext)` returns frozen version/key ID/nonce/ciphertext/wrapped-key fields; `decrypt` authenticates the same scope. **WHY:** storage encryption alone does not protect against every object-copy or broad service-access mistake, and raw long-lived keys should not be stored beside content.

Each encryption creates a random 256-bit data key and 96-bit nonce. AAD binds a domain/version marker, organization UUID, resource UUID and configured key ID. `ManagedKeyProvider.wrap_key/unwrap_key` is an explicit asynchronous integration protocol. A real provider must use approved KMS/HSM operations, scoped encryption context, IAM, region policy, rotation and audit. No AWS/Azure integration or production account is claimed by defining this protocol. A missing provider fails closed. Key IDs are selected by server configuration; envelope key IDs cannot redirect decryption to an arbitrary KMS key.

`LocalKeyProvider` requires explicit development/test mode and an externally supplied 32-byte key; it refuses production mode. It wraps data keys with another AES-GCM operation and the same context, supporting local tests without a fake managed service. Cross-tenant/resource use, ciphertext/nonce/wrapped-key changes, unexpected envelope structure or unknown key identity fail authentication. Decryption does not grant authorization: authorize the resource first, then use trusted identity as AAD.

Plaintext/ciphertext sizes, byte types and wrapped-key sizes are bounded. Key operations have a configurable timeout (ten seconds by default) and fail closed; the provider must also bound its network responses and retries. Python does not guarantee complete zeroization of key bytes; use process isolation and approved managed cryptographic boundaries where memory assurance requires it. AEAD nonce uniqueness is required; keys/nonces are generated per envelope, not derived from request text. See [Cryptography AEAD documentation](https://cryptography.io/en/latest/hazmat/primitives/aead/).

## Cloud and operational responsibilities

| Requirement | Application contribution | Deployment responsibility |
| --- | --- | --- |
| TLS | No plaintext remote transport should be approved implicitly | HTTPS edge/internal policy, certificate rotation, managed DB/Redis TLS and verified CA configuration |
| IAM | Trusted IDs and narrow provider interfaces | Separate runtime/migration/scanner/worker/KMS roles; least privilege; no public buckets or broker |
| Keys | AEAD scope, random data keys, fail-closed provider | KMS/HSM integration, allowed key mapping, audit/rotation, region, break-glass controls |
| Residency | Org/resource scope propagated through adapters | Approved model/scanner/KMS/storage/Redis/log/backup placement and egress |
| Retention | Hashes, version IDs and dependencies enable controlled lifecycle | Quarantine expiry, rejected-file policy, backup deletion reconciliation and legal holds |
| SSRF | Scanner endpoint never selected from user requests | Approved endpoint/DNS/IP/egress controls for scanner, IdP, KMS and connectors |
| Resource limits | Bounded input/archive/scanner/quota operations | Proxy body/connection limits, isolated parser resources, Redis capacity/availability and tenant admission |

Local Compose is development infrastructure. A local filesystem secret, adapter interface or mocked verdict is not production KMS, IAM, TLS, malware coverage or compliance evidence. Resolve region/retention/provider policy before private-data admission.

## Tests and exact commands

```powershell
uv run --package insightrag-api pytest apps/api/tests/test_security_controls.py -m "not integration"
uv run mypy apps/api/src/insightrag/security
uv run ruff check apps/api/src/insightrag/security apps/api/tests/test_security_controls.py
```

The integration-marked Redis quota test needs the ordinary `INSIGHTRAG_TEST_REDIS_URL_FILE` or explicit test URL. It sends ten simultaneous requests with a three-request quota and requires exactly three successes. Unit doubles test error/replay contracts separately and must not be reported as real Redis evidence. The test daemon checks ClamAV wire framing/unknown-verdict handling; no ClamAV signature database is installed by these tests.

Actual focused verification on 2026-11-16 with Cryptography 48.0.1: **22 tests passed, 1 integration test deselected**; mypy passed all three adapter files; Ruff lint/format passed the adapters and focused test file. One upstream Starlette/httpx deprecation warning was observed. Real Redis Lua evaluation and a live ClamAV signature-engine verdict are not established by that focused run; see the complete phase verification record for subsequently executed integration checks.

## Interview and improvement exercises

1. **System design: how do you authorize a worker?** Verify envelope authenticity/replay, load durable job state, compare trusted identities/revision/fence, reauthorize current DB permissions, then execute approved tools. A signed message is not a durable access grant.
2. **Debugging: two revoked users still get cached answers. What do you inspect?** Principal/org scope, policy revision propagation, source version keys, cached-content read authorization and expiry. Hashing alone does not invalidate old access.
3. **Why Redis Lua rather than separate GET/INCR/EXPIRE calls?** The atomic script prevents concurrent races and uses server time; the client must fail closed on outage rather than bypass quota.
4. **What is a fixed-window limitation?** Requests around a boundary can produce a burst close to twice the nominal window allowance. Choose sliding windows/token buckets when that matters and measure capacity/latency.
5. **How do you defend scoped object keys?** Fixed UUID grammar eliminates user-controlled path construction and detects tenant/workspace mismatch, while IAM and current policy independently enforce access.
6. **System design: what makes uploads safe to accept?** Bounded bytes, allowlisted detected type, archive constraints, clean fresh malware verdict, authorized quarantine, isolated parsing and atomic publication. No single extension or signature check suffices.
7. **Debugging: a ZIP header reports a small size but processing grows memory. What failed?** Trusting metadata without aggregate actual decompression bounds or extracting unrestricted members. Read bounded chunks and isolate parser resources.
8. **Why fail closed on scanner outage?** No clean verdict was obtained. Availability pressure cannot turn unknown risk into an authenticated clean result; keep the object quarantined or reject retryably.
9. **Does rejecting visible PDF JavaScript prove safety?** No. Compressed/obfuscated structures and parser defects require scanning and isolated parsing; markers are conservative preliminary checks.
10. **How would you improve scanner resilience?** Private approved redundant scanners, bounded retries, signature-age monitoring and quarantine workflows, preserving no-clean/no-publication semantics.
11. **System design: why envelope encryption?** Random per-object data keys protect content while managed KMS wraps keys with separate policy/audit. Bind tenant/resource identity in authenticated context; authorization still precedes decryption.
12. **Debugging: a copied ciphertext fails under another tenant. Is the key broken?** AAD intentionally binds organization/resource identity. Confirm authorized scope and metadata; do not remove AAD to make an unauthorized copy decrypt.
13. **Why must AES-GCM nonces not repeat for a key?** Reuse undermines confidentiality/authentication. Generate fresh nonces and data keys; never derive them naively from request text or predictable IDs.
14. **Is LocalKeyProvider a production KMS?** No. It is an explicitly development/test-only adapter without managed identity, region enforcement, audit service or HSM guarantees.
15. **What evidence justifies encryption changes?** Approved threat requirements, managed-key integration review, rotation/recovery drills, interoperability and performance measurements; never replace AEAD with custom cryptography for convenience.
