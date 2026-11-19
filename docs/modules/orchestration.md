# Query orchestration and evidence

## WHAT

A bounded state graph routes questions to retrieval, analytics or both, handles clarification, and assembles validated evidence-backed responses.

## WHY

A single opaque prompt is difficult to debug or constrain. LangGraph provides explicit state/checkpoint facilities; an ordinary Python state machine remains viable if graph complexity is small. Domain rules stay outside framework internals.

## HOW

Authenticate -> interpret/clarify -> route -> approved tools -> evidence ledger -> compose -> verify schema/claims/citations/numbers -> final access check -> answer. Track provider/tool calls, source versions and decisions, not private chain-of-thought. Persist checkpoints with tenant/owner access and retention policy. Resumed runs reauthorize and reuse idempotent effect receipts.

## IMPLEMENTATION

Proposed `run_query(request, trusted_context, budget)` returns factual claims, interpretations, recommendations, unknowns, evidence and artifact references. Start with a 30-second interactive deadline, bounded calls and one plan-repair attempt; longer reports become jobs. API progress streaming contains no sensitive excerpts until final release. Missing growth period asks clarification; unavailable evidence gives an honest partial/abstaining outcome.

## PRODUCTION

Model schema validity does not establish truth. Pin run/provider/prompt/metric profiles for audit; redact sensitive telemetry. Guard rate limits, token spend, retry multiplication and unbounded loops. Provider fallback requires equivalent approved processing policy, not just technical availability. Partial tool failures are surfaced rather than silently filling facts from model memory.

## IMPROVEMENT

Routing classifiers, bounded decomposition and adaptive evidence budgets need evaluation. Add new tools only after capability/security review. Do not infer causation from coincident reports and trends. Framework checkpoints do not make side effects exactly once or automatically enforce tenant isolation.
