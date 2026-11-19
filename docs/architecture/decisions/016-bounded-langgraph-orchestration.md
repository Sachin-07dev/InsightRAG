# ADR 016 — Bounded LangGraph orchestration

**Status:** Proposed, awaiting owner review. **Date:** 2026-11-19.

## Context

Phase 5 owns permission-aware document retrieval and citations; Phase 6 owns fixed-SQL analytics and database row security. Cross-source questions need routing without giving model output authority over resources, SQL, or financial definitions. Phase 6 still has unresolved business and capacity gaps; this ADR does not approve them.

## Decision

Introduce a finite LangGraph `StateGraph` over typed request and response contracts. Route deterministically from selected source classes; require explicit document and analytics subquestions for hybrid work. Invoke existing trusted services sequentially. Synthesize separated answer sections and derive optional chart data only from verified SQL rows. Disable graph checkpointing and automatic retries; bound wall time and graph steps.

## Alternatives

Plain async Python is smaller and would satisfy current runtime behavior. LangGraph is selected for explicit conditional graph teaching and inspectable transitions, not proven speed. A model router might classify more natural language but adds drift, injection surface and evaluation burden. Parallel fan-out could reduce latency but complicates authorization snapshot and error handling. Durable checkpoints require a tenant-scoped security and lifecycle design before introduction.

## Consequences

The graph adds a dependency and some per-request construction overhead. Hybrid inputs are less convenient because decomposition is explicit. Source permission checks remain in Phase 5/6; the graph cannot turn a denied access into partial success. A document-provider outage after successful analytics can yield an analytics-only partial result. Persisted dashboards, streaming, provider-cost admission and enterprise financial definitions remain deferred. The decision should be revisited after labeled routing evaluation and representative p95 measurements.
