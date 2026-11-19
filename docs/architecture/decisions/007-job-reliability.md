# ADR 007: Durable jobs, idempotent effects and fencing

Status: Proposed

## Context

Broker messages can repeat or disappear; workers can commit an effect and crash before acknowledgement.

## Decision

Store job/outbox intent transactionally in PostgreSQL. Use stable operation keys and payload hashes, leases, increasing fencing generations, bounded retries, terminal failure states and periodic reconciliation. Redis/Celery dispatch is replaceable.

## Alternatives

Broker-only state can lose accepted work. Acks-late alone does not give exactly-once effects. Temporal offers stronger workflow facilities but adds another operational model.

## Consequences

More state bookkeeping is required. Retry only transient errors; publication rejects expired/stale/deleted work. Reconciliation recovers dispatch failures.

## Validation

Inject crashes before/after effect and acknowledgement, duplicate messages, broker loss, stale leases and deletion races.

## Revisit

Evaluate a durable workflow engine if long-running workflows and recovery logic dominate complexity.
