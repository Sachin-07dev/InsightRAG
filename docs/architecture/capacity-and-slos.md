# Capacity planning and service objectives

Status: **Planning assumptions, not measured benchmarks or contractual promises**. Revisit using a pilot corpus, approved model profiles, and load experiments.

## Workload assumptions and formulas

Machine-readable inputs: [capacity assumptions](capacity-assumptions.json). Per organization: 1,000 active documents, 20 chunks/document, 1 GB original files, 1 GB canonical structured data, and 100 questions/day. Illustrative vectors have 1,536 float32 dimensions; no embedding model has been selected. Peak arrival is 10x daily average; use conservative 20-second occupancy for concurrency planning.

```text
chunks = organizations * documents_per_org * chunks_per_document
raw_vector_GB = chunks * dimensions * bytes_per_dimension / 1e9
average_QPS = organizations * queries_per_org_per_day / 86400
peak_QPS = average_QPS * peak_multiplier
in_flight = ceil(peak_QPS * occupancy_seconds)
```

The table is checked against those inputs by the documentation validator. Decimal GB; no index/replica/version overhead included.

<!-- capacity-table:start -->
| Organizations | Chunks | Original GB | Structured GB | Raw vector GB | Average QPS | Peak QPS | In-flight queries |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 200000 | 10 | 10 | 1.23 | 0.012 | 0.12 | 3 |
| 100 | 2000000 | 100 | 100 | 12.29 | 0.116 | 1.16 | 24 |
| 1000 | 20000000 | 1000 | 1000 | 122.88 | 1.157 | 11.57 | 232 |
| 10000 | 200000000 | 10000 | 10000 | 1228.80 | 11.574 | 115.74 | 2315 |
<!-- capacity-table:end -->

In-flight query occupancy does not equal open DB connections. Release DB transactions before waiting on model/network calls. A bounded pool serves short queries; executor and provider admission limits are separate. Dashboard panel fan-out and scheduled refreshes are additional load, not hidden within question counts.

## Storage, ingestion, and cost

At 2 KB average chunk text, 20,000 chunks add roughly 40 MB text per organization, beyond about 122.88 MB raw vectors. Historical generations, HNSW/GIN/B-tree indexes, tuple overhead, WAL, replication and backups increase storage. Two searchable versions double raw vector/text payload; measure the remaining multipliers instead of promising a universal index ratio.

At 500 tokens/chunk, a full initial pass is 10 million embedding tokens/organization: 100 million, 1 billion, 10 billion and 100 billion across the four tiers. Ingest time depends on parser/OCR throughput, batching, embedding provider token quotas and retry rates. Formula: required embedding throughput = accepted tokens / ingestion deadline. Reserve ingestion capacity separately from query traffic.

Cost = storage/replicas/backups + compute + network + ingestion tokens + query input/output tokens + reranking + analytical execution. Record prices at budget approval time, not as static architectural truth. Track cost by tenant/run; enforce spend and token limits before calls.

## Deployment hypotheses by tier

| Organizations | Hypothesis to test |
| --- | --- |
| 10 | One region; managed PostgreSQL; separate API, ingestion and analytical processes |
| 100 | Same topology with HA DB, API replicas, worker autoscaling and strict quotas |
| 1000 | Benchmark partitioning/cells, isolate heavy tenants, consider analytical aggregates |
| 10000 | Multiple regional cells; dedicated large-tenant placement; evaluate specialized search/warehouse where measurements justify it |

Do not assert a single PostgreSQL instance will meet the 200-million-vector tier. Measure filtered recall, resident index pressure, I/O, write maintenance, skew and operational limits. A larger organization can dominate thousands of small ones.

## Proposed latency and availability objectives

| Measure | Target and envelope |
| --- | --- |
| Core availability | 99.9% monthly at production baseline; 99.95% enterprise target after failover validation |
| Metadata read | p95 <=300 ms at declared concurrency and response size |
| Document Q&A | p95 <=15 s, p99 <=30 s; 30-second interactive deadline, bounded evidence/output |
| Small analytics | p95 <=5 s over <=1 million rows, approved joins and bounded groups; larger work async |
| Chart display | p95 <=1 s after result receipt on agreed reference browser/device |
| Text ingestion | p95 <=2 min for a valid 100-page reference fixture excluding upload time |
| OCR ingestion | p95 <=10 min for agreed 100-page scanned fixture and language profile |
| Deletion | New access blocked at committed tombstone; live-store purge <=24 h excluding declared holds |

Metadata availability = successful eligible requests / all eligible requests. AI availability = completed valid answers or truthful clarification/abstention outcomes / eligible query requests. Provider errors count as user-visible failures; invalid inputs/client cancellations are reported separately. Empty fabricated responses are not successes. Report p50/p95/p99, timeout rate, workload envelope, and separate safety/quality metrics. Thirty days at 99.9% allows 43.2 minutes; at 99.95%, 21.6 minutes. Burn-rate alerts need short and long windows, not only a monthly report.

## Recovery objectives

Baseline PostgreSQL RPO <=5 min, regional recovery RTO <=60 min. Source objects and referenced versions must recover consistently with metadata; reconciliation identifies orphaned/missing objects and blocks affected resources. Indexes are rebuildable but large reindex time must be budgeted; store sufficient durable generations to meet availability targets.

Regional-disaster RTO <=4 h is an enterprise proposal only with an approved secondary location and tested recovery. No zero-data-loss or active-active claim. Protect the deletion ledger outside ordinary rollback scope and reconcile it before reopening traffic; if it cannot be verified, fail closed. See [recovery design](../operations/recovery.md).

## Required experiments

Test four corpus tiers where affordable plus a representative extrapolation model; tenant sizes at median/p95/max; selective document ACLs; exact-versus-ANN recall; concurrent indexing; OCR bursts; dashboard fan-out; expensive joins; provider throttling; worker loss; DB failover; permission revocation; and restoration. Publish assumptions and observed limits separately.
