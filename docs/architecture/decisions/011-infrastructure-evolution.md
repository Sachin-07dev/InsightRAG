# ADR 011: Defer infrastructure specialization

Status: Proposed

## Context

The preferred stack contains tools with meaningful operational costs; adopting all of them would not establish production quality.

## Decision

Use managed regional services and containers first. Retain modular adapters for dedicated search, warehouses, queues and Kubernetes. Measure quality, load, resource pressure and operator burden before migration.

## Alternatives

Kubernetes/microservices/warehouse from day one provide platform features but expand on-call and security responsibilities. A purely local prototype does not meet the production baseline either.

## Consequences

Initial topology is smaller. Future movement needs migration/reconciliation plans, versioned contracts and funded operating ownership. No instance sizes or universal scaling claims are selected.

## Validation

Track declared SLOs, tenant skew, cost, recovery and deployment constraints through controlled experiments.

## Revisit

Reopen when a measured target, contractual isolation requirement or established platform standard demands a different deployment boundary.
