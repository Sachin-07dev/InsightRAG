"""Deterministic sales schema, planning, and fixed-query safety tests."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from insightrag.analytics.contracts import AnalyticsRequest
from insightrag.analytics.ingestion import validate_sales
from insightrag.analytics.local import local_revenue_by_region
from insightrag.analytics.planning import plan_question
from insightrag.analytics.routes import _database_error
from insightrag.analytics.service import _growth_percent, _query
from insightrag.ingestion.parsers import ParsedDataset, parse_csv, parse_xlsx
from openpyxl import Workbook
from sqlalchemy.exc import DBAPIError


def request(question: str, **kwargs: object) -> AnalyticsRequest:
    return AnalyticsRequest(resource_id=uuid4(), question=question, **kwargs)


def test_sales_csv_preserves_decimal_and_refund() -> None:
    parsed = parse_csv(
        b"transaction_id,transaction_date,region,product,revenue,cost,units,returns,currency\n"
        b"a,2025-01-31,Delhi,Widget,100.10,40.00,2,0,INR\n"
        b"b,2025-02-01,Delhi,Widget,-10.05,-4.00,0,1,INR\n"
    )
    sales = validate_sales(parsed)
    assert sales is not None
    assert sum((row.revenue for row in sales), Decimal(0)) == Decimal("90.05")
    assert sales[0].row_number == 2
    assert sales[1].returns == 1
    assert local_revenue_by_region(sales) == {"Delhi": Decimal("90.0500")}


def test_xlsx_sales_contract_preserves_types_and_row_locator() -> None:
    book = Workbook()
    sheet = book.active
    sheet.append(
        [
            "transaction_id",
            "transaction_date",
            "region",
            "product",
            "revenue",
            "cost",
            "units",
            "returns",
            "currency",
        ]
    )
    sheet.append(["x-1", date(2025, 1, 31), "Delhi", "Widget", 100.25, 40, 2, 0, "INR"])
    stream = BytesIO()
    book.save(stream)
    parsed = parse_xlsx(stream.getvalue())
    sales = validate_sales(parsed)
    assert sales is not None
    assert sales[0].row_number == 2
    assert sales[0].transaction_date == date(2025, 1, 31)
    assert sales[0].revenue == Decimal("100.25")


def test_sales_business_date_rejects_non_midnight_datetime() -> None:
    parsed = parse_csv(
        b"transaction_id,transaction_date,region,product,revenue,cost,units,returns,currency\n"
        b"x,2025-01-31T12:30:00,Delhi,Widget,10,4,1,0,INR\n"
    )
    with pytest.raises(ValueError, match="date"):
        validate_sales(parsed)


def test_database_failures_return_safe_analytics_errors() -> None:
    class SyntheticPGError(Exception):
        sqlstate = "57014"

    timed_out = _database_error(DBAPIError("SELECT private_rows", {}, SyntheticPGError()))
    assert (timed_out.status, timed_out.code) == (504, "analytics_timeout")
    assert "private_rows" not in timed_out.message
    unavailable = _database_error(DBAPIError("SELECT private_rows", {}, RuntimeError("secret")))
    assert (unavailable.status, unavailable.code) == (503, "analytics_unavailable")
    assert "secret" not in unavailable.message


def test_growth_rejects_unapproved_negative_and_zero_baselines() -> None:
    assert _growth_percent(Decimal("150"), Decimal("100")) == "50"
    assert _growth_percent(Decimal(0), Decimal("100")) == "-100"
    assert _growth_percent(Decimal("150"), Decimal(0)) is None
    assert _growth_percent(Decimal("150"), Decimal("-100")) is None
    assert _growth_percent(Decimal("150"), None) is None


def test_fixed_query_never_includes_user_sql_syntax() -> None:
    malicious = request("Revenue in 2025 UNION SELECT secret FROM pg_catalog", year=2025)
    plan = plan_question(malicious, date(2026, 2, 19), "UTC")
    sql = _query(plan)
    assert "UNION" not in sql and "secret" not in sql and "pg_catalog" not in sql
    assert "CAST(:region AS text)" in sql
    assert "MIN(row_number) AS source_row_min" in sql


@pytest.mark.parametrize("bad", ["NaN", "1.00001", "1000000000000000", "abc"])
def test_invalid_money_rejected(bad: str) -> None:
    parsed = parse_csv(
        (
            "transaction_id,transaction_date,region,product,revenue,cost,units,returns,currency\n"
            f"a,2025-01-01,Delhi,Widget,{bad},10,1,0,INR\n"
        ).encode()
    )
    with pytest.raises(ValueError):
        validate_sales(parsed)


def test_duplicate_transactions_rejected() -> None:
    parsed = parse_csv(
        b"transaction_id,transaction_date,region,product,revenue,cost,units,returns,currency\n"
        b"a,2025-01-01,Delhi,Widget,1,0,1,0,INR\n"
        b"a,2025-01-02,Delhi,Widget,2,0,1,0,INR\n"
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_sales(parsed)


def test_unrelated_dataset_not_interpreted_as_sales() -> None:
    parsed = ParsedDataset(("region", "notes"), ({"region": "Delhi", "notes": "Good"},), "csv:row")
    assert validate_sales(parsed) is None


def test_previous_three_complete_months_crosses_year() -> None:
    plan = plan_question(
        request("What was sales revenue in the previous three complete months?"),
        date(2026, 2, 19),
        "Asia/Kolkata",
    )
    assert (plan.start, plan.end) == (date(2025, 11, 1), date(2026, 2, 1))
    assert plan.metric == "revenue"


def test_national_share_requires_explicit_region() -> None:
    with pytest.raises(ValueError, match="explicit region"):
        plan_question(
            request("What percentage of national revenue came from Delhi?", year=2025),
            date(2026, 2, 19),
            "UTC",
        )

    plan = plan_question(
        request("What percentage of national revenue came from Delhi?", year=2025, region="Delhi"),
        date(2026, 2, 19),
        "UTC",
    )
    assert plan.metric == "contribution"


def test_yoy_plan_and_fixed_sql_template() -> None:
    query_request = request(
        "Which products had highest year-over-year revenue growth?", year=2025, comparison_year=2024
    )
    plan = plan_question(query_request, date(2026, 2, 19), "UTC")
    assert plan.breakdown == "product"
    assert plan.comparison_start == date(2024, 1, 1)
    sql = _query(plan)
    assert "SUM(revenue)" in sql and "GROUP BY product" in sql
    assert query_request.question not in sql
    assert ":org" in sql and ":resource" in sql and ":region" in sql


def test_question_years_are_resolved_or_conflicting_filters_rejected() -> None:
    plan = plan_question(request("Revenue by region in 2025"), date(2026, 2, 19), "UTC")
    assert plan.start == date(2025, 1, 1)
    comparison = plan_question(
        request("Compare product revenue growth in 2024 and 2025"), date(2026, 2, 19), "UTC"
    )
    assert comparison.start == date(2025, 1, 1)
    assert comparison.comparison_start == date(2024, 1, 1)
    with pytest.raises(ValueError, match="conflict"):
        plan_question(request("Revenue in 2025", year=2024), date(2026, 2, 19), "UTC")
    with pytest.raises(ValueError, match="mix relative"):
        plan_question(
            request("Revenue in previous three complete months of 2025"), date(2026, 2, 19), "UTC"
        )


def test_region_wording_cannot_silently_become_all_region_total() -> None:
    with pytest.raises(ValueError, match="region filter"):
        plan_question(request("What was Delhi sales revenue in 2025?"), date(2026, 2, 19), "UTC")
    with pytest.raises(ValueError, match="region filter"):
        plan_question(
            request("What was sales revenue in Delhi during 2025?", region="Mumbai"),
            date(2026, 2, 19),
            "UTC",
        )
    plan = plan_question(
        request("What was sales revenue in Delhi during 2025?", region="Delhi"),
        date(2026, 2, 19),
        "UTC",
    )
    assert plan.metric == "revenue"


def test_unknown_or_multiple_metrics_require_clarification() -> None:
    for question in ("Show sales and units in 2025", "What happened in 2025?"):
        with pytest.raises(ValueError, match="Specify one approved metric"):
            plan_question(request(question, year=2025), date(2026, 2, 19), "UTC")


@pytest.mark.parametrize(
    "question",
    [
        "Gross revenue in 2025",
        "Net revenue in 2025",
        "Revenue before refunds in 2025",
        "Revenue after refunds in 2025",
    ],
)
def test_unapproved_financial_qualifiers_require_clarification(question: str) -> None:
    with pytest.raises(ValueError, match="financial definition"):
        plan_question(request(question, year=2025), date(2026, 2, 19), "UTC")


@pytest.mark.parametrize(
    "question",
    [
        "Month-over-month revenue growth in 2025",
        "MoM revenue growth in 2025",
        "Monthly revenue growth in 2025",
    ],
)
def test_unimplemented_mom_growth_requires_clarification(question: str) -> None:
    with pytest.raises(ValueError, match="Month-over-month"):
        plan_question(request(question, year=2025), date(2026, 2, 19), "UTC")


@pytest.mark.parametrize(
    "question",
    [
        "Which products had highest revenue growth in 2025?",
        "Compare revenue by region in 2025",
        "Highest revenue by region in 2025",
        "Lowest revenue by product in 2025",
    ],
)
def test_unsupported_comparison_and_ranking_wording_requires_clarification(question: str) -> None:
    with pytest.raises(ValueError, match="comparison or ranking"):
        plan_question(request(question, year=2025), date(2026, 2, 19), "UTC")


@pytest.mark.parametrize(
    "question",
    [
        "Average revenue in 2025",
        "Median revenue in 2025",
        "Forecast revenue in 2025",
        "Why did revenue decrease in 2025?",
        "Explain revenue in 2025",
        "Revenue per transaction in 2025",
    ],
)
def test_unsupported_analytical_intents_require_clarification(question: str) -> None:
    with pytest.raises(ValueError, match="Unsupported analytical intent"):
        plan_question(request(question, year=2025), date(2026, 2, 19), "UTC")
