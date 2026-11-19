# Phase 7 — bounded LangGraph orchestration

**Status:** Implemented for review, with the limitations in [the module guide](modules/orchestration/README.md). The owner explicitly authorized Phase 7 after Phase 6 remediation. This does not approve the unresolved Phase 6 financial definitions or begin Phase 8.

## Objectives and acceptance

The versioned API routes authorized document, governed analytics, hybrid, chart and clarification requests. The graph has finite typed transitions, a wall-clock timeout and an eight-step ceiling. The original Phase 5 and Phase 6 services remain responsible for ACL, RLS, metric and citation controls. Five synthetic execution traces, route/error tests, and a real-database workspace mismatch regression provide bounded verification. The latest runs passed 269 non-integration and 62 real-service integration tests (the last added workspace-wide routing unit passed after the integration run). See [test evidence](testing/orchestration-tests.md).

## Decisions and assumptions

[ADR 016](architecture/decisions/016-bounded-langgraph-orchestration.md) is proposed, not approved. Hybrid requests require separate document and analytics subquestions; the graph does not silently rewrite business semantics. A chart is a validated specification derived only from authorized analytics values, not a rendered or saved dashboard. Graph checkpointing and automatic retries are disabled until private-state retention/revocation and idempotency are designed. This is an intentional secure boundary, with the corresponding requested recovery feature incomplete.

## Next dependencies

Before broad enterprise use, complete the [Phase 6 NO-GO remediation](modules/analytics/PHASE_06_REVIEW_REPORT.md), then evaluate automatic decomposition, dollar-denominated provider-cost admission, durable checkpoint security, and concurrent load with real measurements. Stop after Phase 7 for owner review.

## Understanding questions

1. Why does the graph ask for separate subquestions when both a report and sales dataset are selected?
2. Why can a 503 from document generation become a partial hybrid result while a resource authorization failure cannot?
3. What extra controls would be needed before storing LangGraph checkpoints that contain retrieved evidence?
