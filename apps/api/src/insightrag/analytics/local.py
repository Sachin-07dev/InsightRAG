"""Offline DuckDB comparison on an already-authorized, bounded sales snapshot.

This adapter never accepts SQL, file paths, or network locations. It is not a
production export path: callers must first authorize and materialize rows.
"""

from decimal import Decimal

import duckdb

from insightrag.analytics.ingestion import SalesRow


def local_revenue_by_region(rows: tuple[SalesRow, ...]) -> dict[str, Decimal]:
    if len(rows) > 100_000:
        raise ValueError("Local analytical snapshot exceeds row limit")
    connection = duckdb.connect(
        ":memory:",
        config={"enable_external_access": "false", "threads": "1", "memory_limit": "64MB"},
    )
    try:
        connection.execute("CREATE TABLE sales(region VARCHAR, revenue DECIMAL(20,4))")
        connection.executemany(
            "INSERT INTO sales VALUES (?, ?)",
            [(row.region, row.revenue) for row in rows],
        )
        return {
            region: value
            for region, value in connection.execute(
                "SELECT region,SUM(revenue) FROM sales GROUP BY region ORDER BY region"
            ).fetchall()
        }
    finally:
        connection.close()
