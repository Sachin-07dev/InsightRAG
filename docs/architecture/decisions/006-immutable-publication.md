# ADR 006: Immutable versions and atomic publication

Status: Proposed

## Context

Parsing/indexing spans stores and can fail midway; users need stable evidence and safe updates.

## Decision

Pin verified immutable upload identity, create versioned snapshots/generations, validate staging, and atomically switch the catalog pointer with lifecycle/fencing checks. Preserve real source locators.

## Alternatives

In-place mutation reduces temporary storage but exposes mixed generations, breaks citations and complicates rollback. Full two-phase distributed transactions are unnecessary for immutable staging plus a catalog pointer.

## Consequences

Temporary/historical storage increases; cleanup and policy are required. Prior publication remains available if a new version fails.

## Validation

Test upload mutation, partial indexing, interrupted publication, concurrent update/deletion and historical citation behavior.

## Revisit

Optimize reuse only within compatible tenant/permission/profile boundaries without weakening version identity.
