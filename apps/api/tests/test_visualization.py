"""Synthetic verified-result and authorization-boundary regression checks."""

import asyncio
import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from insightrag.analytics.contracts import AnalyticsResponse, AnalyticsRow
from insightrag.orchestration.contracts import OrchestrationResponse
from insightrag.security.context import AccessContext, SecurityError
from insightrag.visualization import routes
from insightrag.visualization.contracts import DashboardRequest, ViewQuery
from insightrag.visualization.service import build_view
from pydantic import ValidationError
from starlette.responses import Response

_FIXTURE = Path(__file__).parent / "fixtures" / "phase08_delhi_sales.csv"


def verified(rows: list[tuple[str, str | None]]) -> AnalyticsResponse:
    return AnalyticsResponse(
        metric="revenue",
        definition="Signed revenue including refunds",
        metric_definition_version="sales-assumption-v1",
        unit="INR",
        reporting_timezone="Asia/Kolkata",
        period_start="2025-01-01",
        period_end_exclusive="2026-01-01",
        filters={"region": "Delhi"},
        resource_id=uuid4(),
        version_id=uuid4(),
        version_number=1,
        source_sha256="a" * 64,
        rows=[AnalyticsRow(dimension=label, value=value, source_rows=1) for label, value in rows],
        notes=[],
    )


def test_monthly_revenue_copies_exact_values_and_provenance():
    result = verified([("2025-01", "100.1000"), ("2025-02", "-4.2500")])
    view = build_view(result)
    assert view.kind == "line"
    assert [p.value for p in view.points] == ["100.1000", "-4.2500"]
    assert view.source.version_id == result.version_id
    assert view.definition == result.definition
    assert view.insights[0].kind == "verified_observation"
    assert "100.1000 INR" in view.insights[0].text


def test_synthetic_delhi_dashboard_reference_values():
    monthly: dict[str, Decimal] = defaultdict(Decimal)
    products: dict[str, Decimal] = defaultdict(Decimal)
    regions: dict[str, Decimal] = defaultdict(Decimal)
    with _FIXTURE.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            value = Decimal(row["revenue"])
            regions[row["region"]] += value
            if row["region"] == "Delhi":
                monthly[row["transaction_date"][:7]] += value
                products[row["product"]] += value
    assert monthly == {
        "2025-01": Decimal("100.1000"),
        "2025-02": Decimal("100.0000"),
        "2025-03": Decimal("50.0000"),
    }
    assert products == {"Widget": Decimal("220.1000"), "Gadget": Decimal("30.0000")}
    assert regions == {"Delhi": Decimal("250.1000"), "Mumbai": Decimal("180.0000")}
    assert regions["Delhi"] + regions["Mumbai"] == Decimal("430.1000")
    assert regions["Delhi"] / Decimal("430.1000") * 100 > Decimal("58")


def test_table_preserves_null_and_unit():
    view = build_view(verified([("Delhi", None)]), "table")
    assert view.points[0].value is None
    assert view.unit == "INR"


@pytest.mark.parametrize("kind", ["stacked", "scatter", "geo"])
def test_unsupported_shapes_fail_closed(kind: str):
    with pytest.raises(SecurityError, match="visualization_unsupported"):
        build_view(verified([("Delhi", "1")]), kind)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "not-a-number"])
def test_invalid_numeric_values_rejected(value: str):
    with pytest.raises(SecurityError, match="visualization_invalid"):
        build_view(verified([("Delhi", value)]))


def test_line_requires_monthly_shape():
    with pytest.raises(SecurityError, match="visualization_invalid"):
        build_view(verified([("Delhi", "1")]), "line")


def test_monthly_gaps_and_invalid_months_are_not_connected():
    with pytest.raises(SecurityError, match="visualization_invalid"):
        build_view(verified([("2025-01", "1"), ("2025-03", "3")]), "line")
    with pytest.raises(SecurityError, match="visualization_invalid"):
        build_view(verified([("2025-13", "1")]), "line")


def test_client_cannot_submit_authoritative_chart_values():
    with pytest.raises(ValidationError):
        DashboardRequest.model_validate(
            {
                "workspace_id": str(uuid4()),
                "dataset_id": str(uuid4()),
                "views": [{"question": "Revenue in 2025", "points": [{"value": "999999"}]}],
            }
        )


def test_dashboard_http_requires_authentication(client):
    response = client.post(
        "/api/v1/visualization/dashboard",
        json={
            "workspace_id": str(uuid4()),
            "dataset_id": str(uuid4()),
            "views": [{"question": "Revenue in 2025"}],
        },
    )
    assert response.status_code == 401


async def test_dashboard_reauthorizes_each_card_through_orchestration(monkeypatch):
    access = AccessContext(uuid4(), uuid4(), "viewer", 1, False, 1, "trace")
    dataset, workspace = uuid4(), uuid4()
    body = DashboardRequest(
        workspace_id=workspace,
        dataset_id=dataset,
        views=[
            ViewQuery(question="Revenue in 2025", year=2025),
            ViewQuery(question="Revenue by region in 2025", year=2025),
        ],
    )
    calls = []
    stable_result = verified([("Delhi", "10.0000")])

    async def fake_orchestrate(query, request, context):
        assert context is access
        assert query.workspace_id == workspace and query.dataset_id == dataset
        calls.append(query)
        return OrchestrationResponse(
            status="answered",
            route="analytics",
            answer="Verified",
            analytics=stable_result,
            executed_nodes=["classify", "analytics", "verify", "synthesize"],
        )

    monkeypatch.setattr(routes, "orchestrate", fake_orchestrate)
    response = Response()
    output = await routes.dashboard(body, SimpleNamespace(), response, access)
    assert len(calls) == 2 and len(output.cards) == 2
    assert response.headers["Cache-Control"] == "private, no-store"


async def test_denial_on_second_card_aborts_entire_dashboard(monkeypatch):
    body = DashboardRequest(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        views=[ViewQuery(question="Revenue in 2025"), ViewQuery(question="Profit in 2025")],
    )
    count = 0

    async def fake_orchestrate(query, request, context):
        nonlocal count
        count += 1
        if count == 2:
            raise SecurityError(404, "resource_not_found", "Resource unavailable")
        return OrchestrationResponse(
            status="answered",
            route="analytics",
            answer="Verified",
            analytics=verified([("all", "1")]),
            executed_nodes=[],
        )

    monkeypatch.setattr(routes, "orchestrate", fake_orchestrate)
    with pytest.raises(SecurityError, match="resource_not_found"):
        await routes.dashboard(body, SimpleNamespace(), Response(), SimpleNamespace())


async def test_version_change_aborts_dashboard(monkeypatch):
    body = DashboardRequest(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        views=[ViewQuery(question="Revenue in 2025"), ViewQuery(question="Profit in 2025")],
    )

    async def fake_orchestrate(query, request, context):
        return OrchestrationResponse(
            status="answered",
            route="analytics",
            answer="Verified",
            analytics=verified([("all", "1")]),
            executed_nodes=[],
        )

    monkeypatch.setattr(routes, "orchestrate", fake_orchestrate)
    with pytest.raises(SecurityError, match="visualization_version_changed"):
        await routes.dashboard(body, SimpleNamespace(), Response(), SimpleNamespace())


async def test_dashboard_timeout_is_bounded(monkeypatch):
    body = DashboardRequest(
        workspace_id=uuid4(),
        dataset_id=uuid4(),
        views=[ViewQuery(question="Revenue in 2025")],
    )

    async def slow_orchestrate(query, request, context):
        await asyncio.sleep(0.1)
        raise AssertionError("Timeout should cancel this tool")

    monkeypatch.setattr(routes, "orchestrate", slow_orchestrate)
    monkeypatch.setattr(routes, "_DASHBOARD_TIMEOUT_SECONDS", 0.001)
    with pytest.raises(SecurityError, match="visualization_timeout"):
        await routes.dashboard(body, SimpleNamespace(), Response(), SimpleNamespace())
