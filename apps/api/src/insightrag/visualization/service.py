"""Copy verified Phase 6 values into bounded chart specs without recalculation."""

import re
from decimal import Decimal, InvalidOperation
from typing import Literal, cast

from insightrag.analytics.contracts import AnalyticsResponse
from insightrag.security.context import SecurityError
from insightrag.visualization.contracts import (
    BusinessInsight,
    SourceReference,
    ViewPoint,
    ViewSpecification,
)

_MONTH = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])\Z")


def build_view(result: AnalyticsResponse, requested_kind: str = "auto") -> ViewSpecification:
    """Validate chart shape and preserve exact strings, source version and metric semantics."""
    if result.status != "answered" or not result.rows:
        raise SecurityError(422, "visualization_unavailable", "No verified analytical rows")
    if len(result.rows) > 500:
        raise SecurityError(422, "visualization_too_large", "Chart row limit exceeded")
    labels = [row.dimension for row in result.rows]
    if len(labels) != len(set(labels)):
        raise SecurityError(422, "visualization_invalid", "Duplicate chart labels")
    for row in result.rows:
        if row.value is not None:
            try:
                value = Decimal(row.value)
            except InvalidOperation:
                raise SecurityError(
                    422, "visualization_invalid", "Invalid numeric result"
                ) from None
            if not value.is_finite():
                raise SecurityError(422, "visualization_invalid", "Non-finite numeric result")
    monthly = all(_MONTH.fullmatch(label) for label in labels)
    if monthly and labels != sorted(labels):
        raise SecurityError(422, "visualization_invalid", "Monthly rows must be ordered")
    if monthly and len(labels) > 1:
        indices = [int(label[:4]) * 12 + int(label[5:]) for label in labels]
        if any(right - left != 1 for left, right in zip(indices, indices[1:], strict=False)):
            raise SecurityError(422, "visualization_invalid", "Missing months require a table view")
    observed = [
        (Decimal(row.value), row.dimension, row.value)
        for row in result.rows
        if row.value is not None
    ]
    insights = []
    if observed and len(result.rows) > 1:
        highest = max(observed, key=lambda item: item[0])
        insights = [
            BusinessInsight(
                kind="verified_observation",
                text=(
                    f"Highest displayed {result.metric}: {highest[1]} ({highest[2]} {result.unit})."
                ),
            )
        ]
    if requested_kind == "auto":
        kind = "line" if monthly else ("kpi" if len(labels) == 1 else "bar")
    elif requested_kind in {"stacked", "scatter", "geo"}:
        raise SecurityError(
            422,
            "visualization_unsupported",
            "This view needs approved paired, geographic, or multi-series analytical data",
        )
    elif requested_kind == "line" and not monthly:
        raise SecurityError(422, "visualization_invalid", "Line charts require monthly results")
    elif requested_kind == "kpi" and len(labels) != 1:
        raise SecurityError(422, "visualization_invalid", "KPI requires one result row")
    elif requested_kind in {"bar", "table", "line", "kpi"}:
        kind = requested_kind
    else:
        raise SecurityError(422, "visualization_unsupported", "Unsupported view type")
    return ViewSpecification(
        kind=cast(Literal["line", "bar", "table", "kpi"], kind),
        metric=result.metric,
        definition=result.definition,
        unit=result.unit,
        period_start=result.period_start,
        period_end_exclusive=result.period_end_exclusive,
        reporting_timezone=result.reporting_timezone,
        filters=result.filters,
        points=[
            ViewPoint(label=row.dimension, value=row.value, source_rows=row.source_rows)
            for row in result.rows
        ],
        source=SourceReference(
            resource_id=result.resource_id,
            version_id=result.version_id,
            version_number=result.version_number,
            source_sha256=result.source_sha256,
            metric_definition_version=result.metric_definition_version,
        ),
        insights=insights,  # Hypotheses and recommendations require separate evidence.
    )
