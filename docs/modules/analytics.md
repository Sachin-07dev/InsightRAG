# Structured analytics engine

## WHAT

Executes business-defined calculations over authorized structured snapshots or approved connectors. The semantic layer translates business intent into a restricted typed plan.

## WHY

LLMs and vector retrieval cannot establish complete arithmetic. DuckDB offers analytical execution away from transactional state; warehouses are alternatives for greater concurrency/data size. Pandas is restricted preparation tooling, not an unrestricted model execution environment.

## HOW

Intent -> approved metric/dimensions/time/unit -> typed plan -> policy/type/grain validation -> server-owned SQL compiler -> isolated read-only execution -> typed decimal result -> provenance. A row limit does not bound scans or joins; enforce execution/resource limits separately. Canonical snapshots preserve schema and version. Approved joins prevent fan-out.

## IMPLEMENTATION

Proposed interfaces: `resolve_metric(intent, catalog)` may request clarification; `validate_plan(plan, context)` returns a checked plan; `execute_plan(checked_plan, budget)` returns typed result/provenance or classified failure. Money travels as decimal strings plus currency. Example: two permitted INR rows total 300.30; narrative/chart both reference that result. Mixed currencies without approved conversion fail clarification/validation.

## PRODUCTION

No unrelated files, credentials, extension loading or network in the DuckDB sandbox. Limit CPU, memory, temp disk, time, scans and output. Connector credentials allow only approved objects and read-only operations; network/SSRF restrictions apply. Monitor scanned bytes, duration, cancellations, queue age and schema drift. Small-group disclosure policy may be required beyond ordinary grants.

## IMPROVEMENT

Add materialized aggregates, additional plan operators, incremental snapshots or warehouse execution only after measured demand. Live data needs an honest freshness/reproducibility contract. Row/column access requires secure projection/policy design before enabling affected datasets. See [metric concepts](../concepts/metric-semantics.md).
