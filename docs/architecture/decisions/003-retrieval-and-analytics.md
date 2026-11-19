# ADR 003: Separate retrieval and numerical analytics

Status: Proposed

## Context

Semantic relevance cannot guarantee complete financial aggregation or correct business definitions.

## Decision

Retrieve narrative evidence separately from deterministic metric execution. Combined questions assemble both into one provenance-bearing answer with facts, hypotheses and recommendations distinguished.

## Alternatives

Vector-only chat omits rows and conflates prose with computation. SQL-only access cannot effectively answer policy/report interpretation questions.

## Consequences

Two tool paths and an evidence contract add orchestration work. Metric ownership, versions, date boundaries and units become product requirements.

## Validation

Compare exact synthetic totals, document citations and combined questions with missing/conflicting evidence.

## Revisit

Keep the correctness boundary even if execution moves to a warehouse or new search platform.
