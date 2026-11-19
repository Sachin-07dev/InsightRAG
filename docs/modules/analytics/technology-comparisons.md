# Technology and architecture comparisons

| Choice | Selected behavior | Alternative and reason to reconsider |
| --- | --- | --- |
| PostgreSQL row-store versus DuckDB columnar engine | Governed OLTP-linked version/ACL state and bounded analytical scans stay in PostgreSQL; DuckDB compares supplied snapshots offline | A sandboxed DuckDB worker can remove large scans from the shared DB after authorized snapshot, retention and cost controls exist |
| OLTP versus OLAP | Transactional publication and current grants are OLTP; `SUM/GROUP BY` is OLAP-style work on the same small governed table | Dedicated warehouse/ClickHouse when measured concurrency/scan costs justify data movement |
| SQL versus NoSQL | SQL aggregates exact typed decimals with relational grants and RLS | Document/key stores suit flexible records but need another governed computation layer for exact joins/aggregates |
| One fact table versus star/snowflake | One transaction-grain sales fact avoids joins and fanout | Star dimensions improve reuse once approved product/region keys and slowly changing history exist; snowflake normalizes dimensions but adds joins |
| Rule-based typed plan versus raw Text-to-SQL plus AST | Finite metric/dimension templates are inspectable and reject unknown language | Model plans and AST checks can expand coverage only with approved catalog, join and resource contracts, plus adversarial testing |
| SQL versus Pandas | PostgreSQL keeps RLS at the execution layer and avoids loading private rows into API memory | Pandas is useful for bounded offline transformations but needs separate authorization and memory safeguards |
| Analytics versus RAG | Deterministic SQL calculates amounts; RAG retrieves cited explanations | A document may explain a policy but vectors cannot establish the exact sum of all authorized sales rows |
| REST versus SSE/WebSocket | One bounded result returns via ordinary POST response | SSE can stream long jobs/progress; WebSocket only if two-way real-time collaboration is demonstrated |

For this implementation, the selected SQL fragments are compile-time allowlists, so there is no generated SQL AST to inspect. An AST parser becomes essential only if a future product requirement admits a larger SQL grammar; it is not itself a sandbox. The `duckdb` package is locked, but the exposed production API does not execute DuckDB. Evaluate p50/p95 latency, scan bytes, index use, authorization overhead, memory and cost with realistic synthetic load before migrating engines.

The [Phase 6 scoped RLS migration](../../../apps/api/migrations/versions/0008_analytics_scope.py) is an evidence-driven optimization within PostgreSQL: a 10,000-row synthetic query exposed repeated per-row grant checks and timed out under the three-second limit. The revised policy evaluates the resource grant once per transaction-scoped query while retaining row entitlements and active-version checks in PostgreSQL. Its single-user local measurements are in the [test record](../../testing/analytics-tests.md); they do not justify a warehouse or establish production p95 capacity.
