# ADR 010: Derived artifacts inherit evidence dependencies

Status: Proposed

## Context

Answers, charts and exports can retain private information after a source is revoked or deleted.

## Decision

Store source/metric/result dependencies and reauthorize on view, refresh, execution and download. Permission revisions invalidate caches; deletion conservatively invalidates copied content and materializations. Retain minimal audit receipts.

## Alternatives

Authorizing only at generation time leaves permanent leakage paths. Copying source grants into artifacts can drift. Private MVP artifacts avoid complex sharing semantics initially.

## Consequences

Lineage traversal and cleanup add storage/work. Some historical outputs become unavailable; downloaded external copies cannot be revoked. Strict revocation uses mediated downloads.

## Validation

Revoke/delete one source in mixed-source outputs, reopen answers, refresh dashboards and download exports; all affected paths must deny or regenerate safely.

## Revisit

Sharing and redaction need explicit policy extensions before launch, not automatic union of source permissions.
