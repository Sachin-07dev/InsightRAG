# Residency, retention, deletion and compliance discovery

Status: Proposed policy; launch region, jurisdictions and contracts remain unresolved. No legal compliance or certification is asserted.

## Residency

An organization selects an approved home region/cell. This applies to source bytes, canonical datasets, extracted text, embeddings, prompts, answers, checkpoints, cache, telemetry, exports and backups. Model inference endpoints and subprocessors must be reviewed, not just the object bucket. Regional migration is controlled and audited; ordinary request routing cannot silently relocate data. Cross-region recovery and support access need explicit policy approval.

Provider profiles record approved region, data classification, retention behavior, training-use restrictions, contractual controls, timeout/token limits and capabilities. OpenAI-compatible HTTP format does not imply equivalent data handling. Verify actual vendor terms/settings during integration and maintain evidence.

## Proposed retention defaults

| Data | Proposed duration / trigger |
| --- | --- |
| Active sources | Until customer deletion or contract expiry |
| Superseded source versions | 30 days unless approved policy/hold requires otherwise |
| Abandoned quarantine uploads | 24 hours |
| Query history and checkpoints | 30 days |
| Cached results | <=24 hours, invalidated sooner on source/access changes |
| Generated export objects | 7 days |
| Redacted operational logs | 30 days |
| Minimal audit metadata | 365 days, subject to approved requirements |
| Backups | 35-day expiry window |

Retention is a versioned tenant policy with legal-hold exceptions. Store expiry metadata; lifecycle rules and cleanup jobs reconcile receipts. Audit references should not preserve deleted excerpts. Identity erasure and tenant-content deletion are distinct workflows and need jurisdiction-specific review.

## Deletion protocol

Commit tombstone, authorization revision, durable deletion ledger and job before acknowledging blocked access. Purge chunks, vectors, source/object versions, canonical files, local scratch, results, caches, conversations/checkpoints containing copied content, chart materializations and export objects through recorded dependencies. Invalidate mixed-source outputs conservatively; regenerate only after reauthorization.

Use live_purged, backup_expired and held states explicitly. Object versioning, replicas, temporary files and model-provider retained requests are part of the deletion inventory. Do not describe a soft delete or expired signed URL as complete erasure. A legal hold blocks destruction but does not authorize content use. Restore reconciles the latest ledger before access; backups age out under approved policy and must not resurrect deleted content.

## Compliance work required

Inventory data, classifications, controllers/processors and applicable jurisdictions with qualified stakeholders. Establish processing agreements, supplier/subprocessor review, access reviews, incident response, retention/erasure procedures, security evidence and audit ownership. Evaluate customer needs for SOC 2 assurance or ISO 27001 certification as separate programs; a design document grants neither. Map requirements to controls and acceptance evidence before claiming compliance.

Outstanding owner decisions: cloud/region, data categories, cross-border restrictions, provider processing approval, backup region, support access, retention durations, holds authority and audit duration. No private production data should be admitted until these are resolved.
