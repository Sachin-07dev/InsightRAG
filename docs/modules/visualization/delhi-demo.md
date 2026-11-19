# Synthetic Delhi sales dashboard reference

The six-row [synthetic CSV](../../../apps/api/tests/fixtures/phase08_delhi_sales.csv) is a demonstration fixture, not customer data. Its fields match the current Phase 6 sales import contract. Signed refund row `synthetic-d` is `-20.0000 INR`; it reduces Delhi February revenue rather than being discarded. All dates are in 2025 and the organization reporting timezone must be configured separately.

For this fixture, independently adding decimal rows gives Delhi monthly signed revenue `Jan 100.1000`, `Feb 100.0000`, `Mar 50.0000` INR; Delhi total `250.1000`; Mumbai total `180.0000`; national total `430.1000`; Delhi Widget `220.1000`, Gadget `30.0000`. Delhi contribution is exactly `250.1000 / 430.1000 × 100` percent. The precise percent string returned by Phase 6 is authoritative; the chart does not recompute or round it. [test_visualization.py](../../../apps/api/tests/test_visualization.py) checks the source fixture sums using Python `Decimal`. This is an independent synthetic reference, not evidence that the web workflow was run against a live migrated database.

Reference SQL, to be run only against an authorized synthetic fixture under Phase 6 RLS:

```sql
SELECT to_char(transaction_date,'YYYY-MM') AS month, SUM(revenue) AS signed_revenue
FROM analytics_sales_rows
WHERE org_id = :org AND resource_id = :resource AND version_id = :version
  AND currency = 'INR' AND region = 'Delhi'
  AND transaction_date >= DATE '2025-01-01' AND transaction_date < DATE '2026-01-01'
GROUP BY to_char(transaction_date,'YYYY-MM') ORDER BY month;
```

Use the same date, currency, active version and authorized scope for the national denominator. The actual Phase 6 compiler, rather than this example SQL, owns query generation and execution. A real dashboard needs six separately authorized queries. MoM and category breakdown cannot be represented honestly with the current approved semantic layer; product breakdown is displayed and MoM is marked unavailable.
