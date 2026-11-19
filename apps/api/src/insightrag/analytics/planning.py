"""Narrow language-to-plan compiler; no model text becomes SQL syntax."""
# ruff: noqa: E501

import re
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from insightrag.analytics.contracts import AnalyticsRequest

METRIC_DEFINITION_VERSION = "sales-assumption-v1"

METRICS = {
    "revenue": ("SUM(revenue)", "Signed revenue including refunds", "currency"),
    "profit": ("SUM(revenue)-SUM(cost)", "Revenue minus cost", "currency"),
    "margin": (
        "CASE WHEN SUM(revenue)=0 THEN NULL ELSE (SUM(revenue)-SUM(cost))*100/SUM(revenue) END",
        "Profit divided by signed revenue, multiplied by 100",
        "percent",
    ),
    "units": ("SUM(units)", "Sum of nonnegative units", "units"),
    "returns": ("SUM(returned_units)", "Sum of nonnegative returned units", "units"),
    "contribution": (
        "SUM(revenue)",
        "Regional revenue divided by national revenue times 100",
        "percent",
    ),
}


@dataclass(frozen=True)
class QueryPlan:
    metric: str
    breakdown: str
    start: date
    end: date
    comparison_start: date | None = None
    comparison_end: date | None = None


def plan_question(request: AnalyticsRequest, today: date, timezone: str) -> QueryPlan:
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise ValueError("Organization reporting timezone is invalid") from None
    q = " ".join(request.question.casefold().split())
    # The signed-revenue convention has not been approved as a gross or net
    # reporting metric. Reject explicit qualifiers instead of relabelling it.
    if re.search(r"\b(?:gross|net)\b|\b(?:before|after|excluding|including)\s+refunds?\b", q):
        raise ValueError("Clarify the financial definition with an approved metric")
    if re.search(
        r"\b(?:mom|month[ -]over[ -]month|month[ -]to[ -]month)\b"
        r"|\bmonthly\b.*\bgrowth\b|\bgrowth\b.*\bmonthly\b",
        q,
    ):
        raise ValueError("Month-over-month growth is not yet an approved calculation")
    if re.search(
        r"\b(?:average|mean|median|minimum|maximum|forecast|predict|predicted|"
        r"projected|estimate|estimated|why|explain|recommend)\b"
        r"|\bper\s+(?:transaction|unit)\b",
        q,
    ):
        raise ValueError("Unsupported analytical intent; request an approved sum or ratio")
    # A recognizable place name must agree with the explicit filter. Unknown
    # language is clarified rather than silently turning a regional request
    # into an all-region total.
    hints = {
        match.group(1)
        for pattern in (
            r"\b(?:our|was|were|for|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:sales|revenue)\b",
            r"\b(?:in|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
        )
        for match in re.finditer(pattern, request.question)
    }
    if hints and (
        request.region is None
        or any(hint.casefold() != request.region.casefold() for hint in hints)
    ):
        raise ValueError("Provide a matching explicit region filter")
    detected = [name for name in METRICS if re.search(rf"\b{name}\b", q)]
    if "sales" in q and "revenue" not in detected:
        detected.append("revenue")
    if "profit margin" in q:
        detected = [name for name in detected if name != "profit"]
        detected.append("margin") if "margin" not in detected else None
    if "national" in q or "percentage of" in q or "contribution" in q:
        if "revenue" not in detected or request.region is None:
            raise ValueError("National revenue share requires revenue and an explicit region")
        detected = ["contribution"]
    if len(set(detected)) != 1:
        raise ValueError("Specify one approved metric: revenue, profit, margin, units, or returns")
    metric = detected[0]
    breakdown = "total"
    if re.search(r"\b(by|across|per) region", q):
        breakdown = "region"
    elif re.search(r"\b(by|across|per) product", q) or "which products" in q:
        breakdown = "product"
    elif "monthly" in q or "by month" in q or "trend" in q:
        breakdown = "month"
    mentioned_years = [int(item) for item in re.findall(r"\b(?:19\d{2}|20\d{2}|2100)\b", q)]
    relative_period = bool(re.search(r"\b(?:previous|last) (?:three|3) complete\b", q))
    if relative_period and (mentioned_years or request.year is not None):
        raise ValueError("Do not mix relative months with explicit years")
    if len(set(mentioned_years)) > 2:
        raise ValueError("Only two explicit calendar years are supported")
    year = request.year
    comparison_year = request.comparison_year
    if year is None and comparison_year is None and len(set(mentioned_years)) == 1:
        year = mentioned_years[0]
    elif year is None and comparison_year is None and len(set(mentioned_years)) == 2:
        if "compare" not in q and "growth" not in q and "year-over-year" not in q:
            raise ValueError("Clarify which two years should be compared")
        year, comparison_year = max(mentioned_years), min(mentioned_years)
    elif mentioned_years and not set(mentioned_years).issubset({year, comparison_year}):
        raise ValueError("Question years conflict with structured year filters")
    asks_growth = bool(re.search(r"\b(?:growth|year[ -]over[ -]year|yoy)\b", q))
    asks_comparison = bool(re.search(r"\b(?:compare|comparison|versus|vs)\b", q))
    asks_ranking = bool(re.search(r"\b(?:highest|lowest|top|bottom)\b", q))
    if comparison_year is None and (asks_growth or asks_comparison or asks_ranking):
        raise ValueError("Specify two years for comparison or ranking")
    if asks_ranking and not ("highest" in q and asks_growth):
        raise ValueError("Unsupported comparison or ranking; specify highest growth")
    if comparison_year is not None:
        if year is None or year == comparison_year:
            raise ValueError("Year comparison requires two different explicit years")
        if metric in ("margin", "contribution"):
            raise ValueError(
                "Compare additive measures; ratio period comparisons need a separate contract"
            )
        return QueryPlan(
            metric,
            breakdown,
            date(year, 1, 1),
            date(year + 1, 1, 1),
            date(comparison_year, 1, 1),
            date(comparison_year + 1, 1, 1),
        )
    if year is not None:
        return QueryPlan(metric, breakdown, date(year, 1, 1), date(year + 1, 1, 1))
    if not relative_period:
        raise ValueError("Specify a year or ask for the previous three complete calendar months")
    end = date(today.year, today.month, 1)
    month_index = end.year * 12 + end.month - 1 - 3
    start = date(month_index // 12, month_index % 12 + 1, 1)
    return QueryPlan(metric, breakdown, start, end)
