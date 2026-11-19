# ADR 001: Modular backend and separate workers

Status: Proposed

## Context

One team needs to learn and build a system with clear domain boundaries without operating many services immediately.

## Decision

Use one modular FastAPI backend. Separate ingestion, analytical execution and export processes for resource/failure containment. Keep repositories, provider interfaces and typed contracts at boundaries.

## Alternatives

Microservices enable independent ownership/scaling but add distributed transactions, deployment and debugging. A single undifferentiated process is simpler initially but lets OCR/analytics exhaust API resources.

## Consequences

Local calls simplify domain work. Discipline is required to prevent direct cross-module storage access. Worker boundaries still require authentication, durable intent and version contracts.

## Validation

Review imports/contracts, then load-test API latency during ingestion and analytics. No such test has run yet.

## Revisit

Extract services when measured scaling, failure containment, team ownership or release cadence warrants the cost.
