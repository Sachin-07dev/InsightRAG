# ADR 015: Governed sales projection and bounded analytics

Status: **Proposed** — owner review pending.

## Context

Phase 4 stores CSV/XLSX cells as versioned JSON rows. Generic cells are not a safe or accurate numerical contract. A valid identity may see only some regions. Raw model SQL could join an unauthorized table, cast malformed values, or exhaust the database.

## Decision

The ingestion worker validates an exact nine-column sales contract before staging typed `analytics_sales_rows` in the same publication transaction. PostgreSQL RLS intersects resource `query` permission, region entitlement and active version. A small rule-based compiler selects an allowlisted metric and dimension, then the service executes fixed aggregate SQL with bound values, a 3-second statement timeout, 8 MiB work memory and a 500-group cap. It rechecks policy revision and version before returning. National contribution calls a narrowly scoped security-definer boolean that checks entitlement to all active regions without exposing their names. DuckDB is an offline in-memory validation tool with external access disabled; a production snapshot worker is deferred.

## Alternatives and tradeoffs

Arbitrary SQL plus AST validation supports more questions, but safe name resolution, joins, functions, resource costs and row policies are much harder. Per-tenant physical tables simplify some isolation but multiply migrations and operations. JSONB casts avoid a projection but permit schema drift and runtime failures. A star schema enables approved joins later; the current single fact table avoids accidental fanout. A warehouse or full DuckDB service may reduce heavy scan pressure but requires authorized snapshot publication, isolation, retention and concurrency controls.

## Validation and revisit

Unit tests cover parsing, decimals, duplicates, dates, planner rejection and DuckDB comparison. Real PostgreSQL RLS/migration tests are defined and must run before security assurance. Revisit when an approved business glossary defines joins, conversions and more metrics; when measured query latency exceeds objectives; or when a safe authorized snapshot/connector design is reviewed. This ADR does not approve deployment.

The post-review implementation rejects explicit gross/net/refund qualifiers and month-over-month growth until definitions and comparison rules are approved. It adds a response-level assumed metric-definition version and source-file SHA-256; neither is business approval or a complete row-lineage registry. Real-service tests include a restricted-role SQL comparison and XLSX worker publication. The ADR remains **Proposed**.

A 10,000-row synthetic test exposed a real timeout in the original per-row RLS grant check. [Migration 0008](../../../apps/api/migrations/versions/0008_analytics_scope.py) requires the server to bind a transaction-local resource ID; the RLS policy checks current resource permission once per query and still intersects current-user region entitlement, organization and active version. Missing or wrong scope denies all typed rows. The fixed query passed the measured local test, but concurrent/100,000-row capacity is unknown. This is a performance/security trade-off to review before approving the ADR.
