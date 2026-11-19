# Phase 6 analytics interview practice

These answers defend the bounded implementation, not a hypothetical fully general BI platform. In each answer, start with the short response, then use the deeper material when pressed. Code links are relative to this file. The [implementation walkthrough](../modules/analytics/implementation-walkthrough.md) and [test report](../testing/analytics-tests.md) give runnable context.

## Database and data engineering

### 1. What is the difference between OLTP and OLAP?
**Short answer:** OLTP serves many small state-changing transactions; OLAP scans/group-aggregates large data for analysis. One database can do both at modest scale, but the workloads compete.

**Deep explanation:** OLTP emphasizes row lookup, transactional consistency and low write latency. OLAP emphasizes column scans, grouping and compression. [PostgreSQL](../../apps/api/src/insightrag/analytics/service.py) atomically publishes versions and runs bounded sums, so query load can interfere with ingestion unless monitored. **Project example:** `active_version` publication is OLTP; `SUM(revenue) GROUP BY region` is OLAP-style. **Alternatives:** Dedicated warehouse or materialized aggregate reduces scans but adds copy/invalidation complexity. **Follow-ups:** (1) Can PostgreSQL do OLAP? Yes, with indexes, parallelism and bounded workloads. (2) What triggers separation? Measured p95 latency, buffer pressure and tenant interference. **Common mistake:** Calling a query OLAP solely because it uses SQL.

### 2. Why use DuckDB when PostgreSQL already exists?
**Short answer:** DuckDB is a columnar in-process engine well suited to isolated local scans of approved snapshots; PostgreSQL remains the governed source with RLS and current grants.

**Deep explanation:** DuckDB vectorizes column operations and can reduce pressure on a transactional database, but it does not inherit PostgreSQL RLS. [Our adapter](../../apps/api/src/insightrag/analytics/local.py) accepts validated rows, disables external access, caps rows/memory and runs a fixed in-memory aggregate. It is offline only. **Alternatives:** PostgreSQL-only is simplest; a managed warehouse scales concurrent analytics but moves governed data. **Follow-ups:** (1) Can an API pass a raw private CSV path to DuckDB? No; it would bypass grants and storage policy. (2) What must a production bridge add? Authorized snapshot, fencing, isolation, encryption, purge and audit. **Common mistake:** Claiming the installed DuckDB package is already a production analytics service.

### 3. What is dimensional modelling?
**Short answer:** Declare one fact-row grain and the dimensions/measures used to filter and aggregate it.

**Deep explanation:** A fact records an event; a dimension describes it. [Sales rows](../../apps/api/migrations/versions/0007_analytics.py) have one transaction ID per version, with date, region, product and currency dimensions and revenue/cost/units/returns measures. **Alternatives:** A generic JSON table is flexible but weakly typed; a star model supports reusable dimensions after approved keys exist. **Follow-ups:** (1) Why define grain first? To prevent accidental duplication in joins. (2) Can revenue add across currencies? Only after an approved conversion contract. **Common mistake:** Treating every column as an additive measure.

### 4. Explain star schema versus snowflake schema.
**Short answer:** A star keeps denormalized dimension tables directly around a fact; a snowflake normalizes dimensions into more related tables.

**Deep explanation:** A star often needs fewer joins and is easier for BI; a snowflake may reduce repeated dimension attributes but increases join paths and semantic governance. This phase deliberately has a single fact table and no approved joins. **Project example:** A future product dimension might join by stable product key; today's product text is stored on each row. **Alternatives:** One wide fact avoids join fanout but duplicates labels. **Follow-ups:** (1) How handle changing product names? Versioned/slowly changing dimensions. (2) What causes double counting? A one-to-many dimension/tag join before aggregation. **Common mistake:** Assuming normalization guarantees correct totals.

### 5. How would you scale analytical queries to millions of rows?
**Short answer:** Measure first, then optimize predicates/indexes, partitioning or materialized aggregates; move large scans to an authorized analytical worker/warehouse if needed.

**Deep explanation:** [The index](../../apps/api/migrations/versions/0007_analytics.py) starts with tenant/resource/version/currency/date. `EXPLAIN (ANALYZE, BUFFERS)` under realistic data shows actual paths; RLS and group cardinality matter. **Alternatives:** DuckDB snapshot or warehouse can improve scan isolation but introduces lifecycle and permission copies. **Follow-ups:** (1) Does `LIMIT 500` cap scan work? No, only output groups. (2) What signals a spill? PostgreSQL temp-file metrics and plan details. **Common mistake:** Adding indexes without testing selectivity or write cost.

## Semantic layer and business meaning

### 6. What is a semantic layer, and why do BI systems need it?
**Short answer:** It maps business terms to approved fields, formulas, dimensions, units, time rules and access constraints so every report calculates the same thing.

**Deep explanation:** “Sales” could mean gross orders, shipped units or net revenue. [Our catalog](../../apps/api/src/insightrag/analytics/planning.py) explicitly maps it to signed revenue and limits allowed breakdowns. **Alternatives:** Free-form SQL is flexible but drifts across analysts; external metric catalogs add governance but need operations. **Follow-ups:** (1) What must be versioned? Formula, filters, time/currency semantics and source lineage. (2) Is a synonym dictionary enough? No, it lacks calculation and access contracts. **Common mistake:** Calling any schema description a semantic layer.

### 7. How do you prevent incorrect totals caused by joins?
**Short answer:** State the fact grain, allow only cardinality-approved join paths, and aggregate before many-to-many expansions.

**Deep explanation:** One sale joined to two tags becomes two rows and doubles `SUM(revenue)`. [The current query](../../apps/api/src/insightrag/analytics/service.py) avoids joins entirely. A future star requires unique dimension keys or preaggregated fact subqueries. **Alternatives:** `SUM(DISTINCT revenue)` is generally wrong because equal-valued independent sales disappear. **Follow-ups:** (1) How detect fanout? Compare row counts before/after each join and unique-key assertions. (2) How handle allocations? Define weights summing to one. **Common mistake:** Fixing duplicate totals with arbitrary `DISTINCT`.

### 8. How do you handle ambiguous business metric definitions?
**Short answer:** Ask for clarification or require an approved glossary definition; never guess gross versus net, timezone or currency.

**Deep explanation:** [The planner](../../apps/api/src/insightrag/analytics/planning.py) rejects unknown or multiple metrics. The current signed-revenue convention is an explicit project assumption, not a universal financial standard. **Alternatives:** LLM intent extraction can suggest a plan, but an owner-approved semantic catalog must validate it. **Follow-ups:** (1) Who approves definitions? A business/data owner with versioned change control. (2) How handle old dashboards? Pin metric definition version and source versions. **Common mistake:** Letting a model rewrite a metric silently.

### 9. How do you manage multiple currencies?
**Short answer:** Filter to one currency or convert with an approved rate table and explicit rate/date policy; never sum unlike currencies.

**Deep explanation:** [The service](../../apps/api/src/insightrag/analytics/service.py) discovers authorized currency codes and asks for one when several are present. It does no conversion. A real FX layer needs source, bid/ask/closing/average rate, effective date, rounding and audit provenance. **Alternatives:** Pre-converted source amounts simplify queries but hide rate revision unless both original and converted values are kept. **Follow-ups:** (1) Which rate for monthly revenue? Business policy must decide. (2) What if a rate is missing? Fail or mark incomplete, never invent. **Common mistake:** Adding INR and USD decimals directly.

### 10. Why shouldn't vector search calculate exact financial totals?
**Short answer:** Vector retrieval samples semantically similar text; it neither enumerates every authorized row nor applies deterministic aggregation and currency semantics.

**Deep explanation:** Approximate nearest-neighbor search may omit relevant rows and score is not a monetary quantity. [RAG routing](../../apps/api/src/insightrag/retrieval/service.py) labels numeric questions `analytics_required`; [Phase 6 SQL](../../apps/api/src/insightrag/analytics/service.py) computes them from typed rows. **Alternatives:** RAG can cite a narrative explaining a decline, after SQL has established the verified amounts. **Follow-ups:** (1) Could an LLM add values from a small table? It may, but deterministic code is auditable. (2) Can retrieval explain a number? Yes, as contextual evidence, not its source of truth. **Common mistake:** Treating cosine score as confidence in a financial result.

## Natural language, SQL and validation

### 11. How does Text-to-SQL work?
**Short answer:** A system links language to schema/metrics, builds a query plan, validates it, compiles SQL and executes under database authorization.

**Deep explanation:** Models often generate SQL tokens from schema context, but may choose wrong joins, units or filters. [Our planner](../../apps/api/src/insightrag/analytics/planning.py) is a narrow rule-based form of intent resolution; [the service](../../apps/api/src/insightrag/analytics/service.py) compiles only fixed expressions. **Alternatives:** An LLM can emit a typed plan for review; raw SQL grants much more flexibility and attack surface. **Follow-ups:** (1) What is schema linking? Matching question entities to approved tables/columns. (2) Why separate planning from execution? To validate semantics and authority before SQL. **Common mistake:** Assuming syntactically valid SQL means a correct answer.

### 12. Why is executing raw LLM-generated SQL dangerous?
**Short answer:** The model can select unauthorized data, dangerous functions or unbounded scans, and can miscalculate even with read-only syntax.

**Deep explanation:** Prompt injection or schema confusion can request cross-tenant joins. A DB read-only account still permits costly or sensitive reads unless RLS and allowlists hold. This phase exposes no raw SQL API. **Project example:** [The fixed template](../../apps/api/src/insightrag/analytics/service.py) only accepts metric/dimension identifiers from server constants. **Alternatives:** A reviewed AST subset plus database RLS is possible but substantially more complex. **Follow-ups:** (1) Is `SELECT` safe? No, it can leak or exhaust resources. (2) Is prompting “read-only” enough? No, enforce in database/contract. **Common mistake:** Relying solely on a model system prompt.

### 13. How does SQL AST validation work?
**Short answer:** Parse SQL into a syntax tree, traverse every node and permit only approved statement types, relations, columns, joins, expressions and functions.

**Deep explanation:** Name resolution, CTEs, subqueries and dialect-specific functions complicate a safe allowlist. This implementation does not need an AST because SQL syntax comes only from [sealed constants](../../apps/api/src/insightrag/analytics/service.py); values are bound. **Alternatives:** AST validation is useful for an expanded reviewed SQL subset, but RLS, timeouts and semantic metric checks remain essential. **Follow-ups:** (1) Can a valid AST prove a correct denominator? No, business semantics are separate. (2) How test a validator? Mutation/fuzz cases with nested and quoted identifiers. **Common mistake:** Treating parsing as sandboxing.

### 14. How do you prevent SQL injection in an AI analytics system?
**Short answer:** Keep SQL structure server-owned, bind all values, validate structured plan enums, and execute with least-privileged RLS role.

**Deep explanation:** String-concatenating `region` or LLM output into SQL changes syntax. [The query builder](../../apps/api/src/insightrag/analytics/service.py) interpolates only constant expressions; `region`, IDs, dates and currency are bound parameters. **Alternatives:** A query builder or ORM may help structure, but cannot replace authorization. **Follow-ups:** (1) Can bound values replace column names? No; identifiers require allowlists. (2) Does escaping alone suffice? Binding is safer and dialect-aware. **Common mistake:** Regex-filtering a raw SQL string as the only defense.

### 15. How would you design a secure enterprise Text-to-SQL platform?
**Short answer:** Identity → authorized catalog → typed metric plan → semantic/ACL validation → fixed or AST-constrained SQL → RLS read-only execution → provenance, audit and result checks.

**Deep explanation:** [Our API](../../apps/api/src/insightrag/analytics/routes.py) implements a bounded subset with resource grants, row RLS, timeouts and version checks. Expanding to connectors requires per-source credentials, table/column policy, safe join graph, query cost admission and snapshot consistency. **Alternatives:** Dedicated warehouse isolates load but must duplicate authorization correctly. **Follow-ups:** (1) How handle prompt injection? Treat model output as untrusted plan proposal. (2) How handle revoked access during execution? Version/policy fencing and cancellation. **Common mistake:** Equating a valid JWT with data entitlement.

## Calculations and correctness

### 16. How do you calculate year-over-year growth correctly?
**Short answer:** Compare like-for-like whole periods using the same metric/currency/filter; growth is `100*(current-prior)/prior` for a positive prior baseline, null when prior is absent, zero or negative pending an approved interpretation.

**Deep explanation:** [The planner](../../apps/api/src/insightrag/analytics/planning.py) takes explicit `year` and `comparison_year`; [the service](../../apps/api/src/insightrag/analytics/service.py) runs both aggregates under one authorization transaction. A product absent this year but present last year is reported as zero current and -100% only for a positive baseline. **Alternatives:** SQL window functions can perform this in one query after calendar bucketing. **Follow-ups:** (1) Why exclude partial current year? Otherwise comparison is not like-for-like. (2) What if baseline is negative? The signed formula is mathematically calculable but the business interpretation is unapproved, so the API returns null. **Common mistake:** Dividing by current rather than prior.

### 17. How do you handle refunds and negative revenue?
**Short answer:** Use an approved signed convention; negative adjustments reduce revenue, with separate return-unit counts.

**Deep explanation:** [Validation](../../apps/api/src/insightrag/analytics/ingestion.py) permits negative decimal revenue/cost but requires nonnegative `returns`. A 100.10 sale and -10.05 refund total 90.05. **Alternatives:** Separate sale/refund event types with a derived net metric offer clearer accounting if the source provides them. **Follow-ups:** (1) What if refund occurs next month? Count it by its own transaction date unless business policy assigns it back. (2) What if cost reverses? Store a signed adjustment, then document it. **Common mistake:** Dropping negative rows as “outliers.”

### 18. What does “previous three complete months” mean?
**Short answer:** In the organization's reporting timezone, start at the first day three months before this month and end *before* the first day of this month.

**Deep explanation:** On 19 February 2026 local business date, [the planner](../../apps/api/src/insightrag/analytics/planning.py) produces `[2025-11-01,2026-02-01)`. An exclusive end prevents end-of-day timestamp errors; here source dates are already local dates. **Alternatives:** Rolling 90 days answers a different question. **Follow-ups:** (1) What at a timezone boundary? Use organization-local clock, not client clock. (2) Are periods complete if source data is late? Not proven; watermark/completeness metadata is deferred. **Common mistake:** Including the current partial month.

### 19. How would you debug an incorrect revenue calculation?
**Short answer:** Verify metric definition, source version, entitlement, currency, date bounds, row grain and signed adjustments before suspecting SQL arithmetic.

**Deep explanation:** Compare [response provenance](../../apps/api/src/insightrag/analytics/contracts.py) with an independent approved `SUM` under the same runtime identity. Inspect duplicate transaction IDs, missing rows, refund dates and RLS region grants using synthetic reproduction. **Alternatives:** An offline DuckDB comparison can catch SQL/regression errors only after both engines receive the same authorized snapshot. **Follow-ups:** (1) What if national share looks too high? Check complete-region access and denominator. (2) What if values vary by month boundary? Check reporting timezone/source date semantics. **Common mistake:** Querying as DB owner, bypassing the user's RLS view.

### 20. Why calculate margin from totals rather than average row margins?
**Short answer:** The aggregate ratio must weight each row by revenue: `100*SUM(revenue-cost)/SUM(revenue)`.

**Deep explanation:** A 100 revenue/10 profit row and 900 revenue/180 profit row have margins 10% and 20%; average row margin is 15%, but combined margin is 190/1000 = 19%. [The metric expression](../../apps/api/src/insightrag/analytics/planning.py) uses aggregate sums. **Alternatives:** Weighted average of row margins with revenue weights is equivalent only with carefully handled zero/negative rows. **Follow-ups:** (1) What if total revenue is zero? Return null. (2) What if refund rows make weights negative? Use aggregate signed totals and business review. **Common mistake:** `AVG(profit/revenue)`.

## Security, operations and API choice

### 21. How do you prevent cross-tenant data leakage?
**Short answer:** Enforce current membership and resource query grant, bind organization/resource/version in SQL, and let PostgreSQL RLS enforce tenant, region and active-version predicates.

**Deep explanation:** [The service](../../apps/api/src/insightrag/analytics/service.py) sets transaction-local identity through [tenant_session](../../apps/api/src/insightrag/security/database.py). [RLS](../../apps/api/migrations/versions/0007_analytics.py) checks current database policy, not a stale JWT claim. **Alternatives:** Separate databases per tenant offer stronger placement but higher operational cost. **Follow-ups:** (1) Why recheck policy after query? To reject revocation racing the calculation. (2) How test? Seed A/B plus region entitlements under restricted runtime role. **Common mistake:** Filtering results only after aggregation.

### 22. Why is a valid JWT not sufficient for dataset access?
**Short answer:** Authentication identifies a principal; authorization depends on current org membership, workspace/resource grant, purpose, classification and row entitlement.

**Deep explanation:** [The security dependency](../../apps/api/src/insightrag/security/dependencies.py) maps issuer/subject to a provisioned user, while [require_resource](../../apps/api/src/insightrag/security/database.py) asks current DB policy. A revoked grant invalidates query authority without waiting for token expiry. **Alternatives:** Token-embedded grants are fast but stale and hard to revoke. **Follow-ups:** (1) Does an org header prove membership? No. (2) Can schema discovery bypass access? No, it uses the same grant and RLS. **Common mistake:** Trusting a client-selected tenant ID.

### 23. Why can a “national” denominator be wrong for a regional analyst?
**Short answer:** RLS may hide other regions, so a normal `SUM` returns only authorized rows and mislabelling it national would be false.

**Deep explanation:** [The complete-scope function](../../apps/api/migrations/versions/0007_analytics.py) checks whether *any* active row belongs to a region without an entitlement; [the service](../../apps/api/src/insightrag/analytics/service.py) rejects national contribution if so. It discloses only a boolean. **Alternatives:** A separately approved public national aggregate could be exposed by policy, with disclosure review. **Follow-ups:** (1) Can `SUM` itself be correct? Yes, for the visible scope. (2) What if a new region is uploaded? The check reevaluates active rows. **Common mistake:** Assuming a dataset-level grant implies all rows.

### 24. Why choose REST rather than WebSocket or SSE here?
**Short answer:** The current 3-second bounded analytics calculation has one request and one structured response; REST over HTTPS is sufficient.

**Deep explanation:** [The FastAPI route](../../apps/api/src/insightrag/analytics/routes.py) uses POST and returns Pydantic data. SSE would help async progress/streamed results; WebSocket supports bidirectional sessions but adds connection/auth/reconnect/backpressure complexity. Both ride application protocols over transport/TLS; neither changes SQL authorization. **Alternatives:** An async job plus polling suits longer warehouse scans. **Follow-ups:** (1) What if client disconnects? Cancel/timeout work where possible; ensure DB timeout. (2) What if 10,000 simultaneous scans arrive? Admission and worker isolation, not WebSocket alone. **Common mistake:** Choosing WebSockets because the product is AI-branded.

### 25. How does the local DuckDB comparison differ from a secure production connector?
**Short answer:** It computes one fixed aggregate on caller-supplied validated rows; it has no identity, dataset discovery, remote credentials or production snapshot lifecycle.

**Deep explanation:** [The adapter](../../apps/api/src/insightrag/analytics/local.py) limits rows/memory and disables external access. That reduces accidental file access but does not prove process isolation or full resource quotas. A production connector needs approved read-only credentials, table/column policy, TLS, query cost limits, network egress controls, audit and deletion propagation. **Alternatives:** Stay in PostgreSQL until measured load justifies this complexity. **Follow-ups:** (1) Does disabling external access enforce tenant ACL? No, filter/authorize before snapshot. (2) Why not expose arbitrary DuckDB SQL? It would widen the attack surface. **Common mistake:** Calling an in-memory adapter a sandbox.

The configured engine memory limit is not a hard process quota; the project requires OS/container isolation before processing real private snapshots.
