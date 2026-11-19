# ADR 009: Regional tenant data boundary

Status: Proposed

## Context

Residency can constrain much more than database placement, including model processing, telemetry and recovery.

## Decision

Assign each organization an approved home region/cell. Govern sources, vectors, queries, artifacts, providers, backups and support access consistently. Region migration is explicit; private-data admission waits for policy approval.

## Alternatives

Unrestricted global routing can violate customer requirements. Single-region-only deployment is simpler but needs an explicit disaster-risk acceptance if no approved recovery location exists.

## Consequences

Provider choices, telemetry backends and failover routes are constrained. No exact cloud/region or compliance claim is approved yet.

## Validation

Review data-flow inventory, provider contract/settings, network routes, backup location and regional recovery exercises.

## Revisit

New jurisdictions, suppliers, classifications or contracts require updated policy and threat review.
