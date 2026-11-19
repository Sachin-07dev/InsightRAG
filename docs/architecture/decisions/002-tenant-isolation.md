# ADR 002: Shared tenant tables and resource authorization

Status: Proposed

## Context

Many organizations need economical isolation plus document-level access, including derived answers.

## Decision

Use organization keys, composite foreign keys, forced RLS, non-owner runtime roles, workspace membership and explicit resource grants. Admin capability does not imply content access. Reauthorize artifacts and cache scopes.

## Alternatives

Database-per-tenant provides stronger operational separation but increases migrations/pooling cost. Schema-per-tenant complicates operations and is not a complete access policy. API filters alone are too easy to omit.

## Consequences

Shared infrastructure retains noisy-neighbor and trusted-API risks. Dataset-level analytics is the MVP boundary; deny unsupported finer-grained policies. Dedicated placement remains possible.

## Validation

Negative tests must cover SQL roles, pool reuse, API IDs, cache, workers, artifacts, connectors and restoration.

## Revisit

Contractual isolation, sensitive classification or measured tenant interference may require dedicated databases/cells.
