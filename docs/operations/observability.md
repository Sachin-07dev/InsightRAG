# Observability and cost controls

Status: Proposed instrumentation. No monitoring service is connected.

Correlate request -> policy -> retrieval/analytics -> provider -> answer/validation -> artifact using trace/run/job IDs. Instrument stage latency, queue age, retries, denied access, query budgets, scanned bytes, memory termination, provider throttling, invalid citations, abstention and deletion/restore progress. Track error classes and per-stage percentiles.

Logs contain structured safe codes, timing and opaque references, not raw documents, credentials or complete prompts by default. Traces/checkpoints are governed stores with region/access/expiry requirements. Do not export principal identities as unrestricted metric labels. Keep per-tenant billing/usage in access-controlled accounting records; aggregate operational metrics have bounded cardinality.

SLO alerts use fast/slow burn windows and distinguish dependency failures without excluding user-visible impact. Admission limits include organization concurrency, file/page/row sizes, tool calls, tokens, scan budget and spend. Set deadlines at every external call; avoid independent retries multiplying across API, graph, SDK and worker layers.

Cost reports use actual tokens/provider prices and measured infrastructure allocation. A query can be inexpensive in output rows but expensive in scans or model context. Record forecasts as forecasts, not charges. Approve content-bearing Langfuse tracing only after a specific data-handling review.
