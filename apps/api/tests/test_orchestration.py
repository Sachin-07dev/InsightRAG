"""Synthetic end-to-end LangGraph traces; no tenant data or provider calls."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from insightrag.analytics.contracts import AnalyticsResponse, AnalyticsRow
from insightrag.core.config import Settings
from insightrag.orchestration import routes as orchestration_routes
from insightrag.orchestration.contracts import OrchestrationRequest
from insightrag.orchestration.graph import classify, execute
from insightrag.retrieval.contracts import Citation, QueryResponse
from insightrag.security.context import AccessContext, SecurityError
from pydantic import ValidationError


def _analytics(request: OrchestrationRequest) -> AnalyticsResponse:
    assert request.dataset_id
    return AnalyticsResponse(
        metric="revenue",
        definition="Signed revenue including refunds",
        metric_definition_version="sales-assumption-v1",
        unit="INR",
        reporting_timezone="Asia/Kolkata",
        period_start="2025-01-01",
        period_end_exclusive="2026-01-01",
        filters={"region": "Delhi"},
        resource_id=request.dataset_id,
        version_id=uuid4(),
        version_number=1,
        source_sha256="a" * 64,
        rows=[AnalyticsRow(dimension="Delhi", value="100.1000", source_rows=1)],
        notes=[],
    )


def _document(request: OrchestrationRequest) -> QueryResponse:
    return QueryResponse(
        conversation_id=None,
        answer="The report attributes the decline to delayed shipments.",
        citations=[
            Citation(
                id="c1",
                resource_id=request.document_resource_ids[0],
                workspace_id=request.workspace_id,
                document_title="Annual report",
                version_id=uuid4(),
                version_number=1,
                locator="page 2",
                chunk_position=0,
                excerpt="Shipments were delayed.",
            )
        ],
        status="answered",
    )


@pytest.mark.parametrize(
    ("kind", "expected_route", "expected_nodes"),
    [
        ("document", "document", ["classify", "document", "verify", "synthesize"]),
        ("analytics", "analytics", ["classify", "analytics", "verify", "synthesize"]),
        (
            "hybrid",
            "hybrid",
            ["classify", "analytics", "document", "verify", "synthesize"],
        ),
        ("chart", "analytics", ["classify", "analytics", "verify", "synthesize", "chart"]),
        ("clarification", "clarification", ["classify", "clarify"]),
    ],
)
async def test_five_graph_traces(kind: str, expected_route: str, expected_nodes: list[str]):
    workspace = uuid4()
    docs = [uuid4()] if kind in {"document", "hybrid"} else []
    dataset = uuid4() if kind in {"analytics", "hybrid", "chart"} else None
    request = OrchestrationRequest(
        workspace_id=workspace,
        question="Summarize the report" if kind == "document" else "Revenue by region in 2025",
        document_resource_ids=docs,
        dataset_id=dataset,
        document_question="Summarize shipment delays" if kind == "hybrid" else None,
        analytics_question="Revenue by region in 2025" if kind == "hybrid" else None,
        chart=kind == "chart",
    )
    called: list[str] = []

    async def document_tool(selected: OrchestrationRequest, question: str) -> QueryResponse:
        called.append("document")
        assert question == (selected.document_question or selected.question)
        return _document(selected)

    async def analytics_tool(selected: OrchestrationRequest, question: str) -> AnalyticsResponse:
        called.append("analytics")
        assert question == (selected.analytics_question or selected.question)
        return _analytics(selected)

    result = await execute(request, document_tool, analytics_tool)
    assert result.route == expected_route
    assert result.executed_nodes == expected_nodes
    assert called == [node for node in expected_nodes if node in {"document", "analytics"}]
    if kind == "chart":
        assert result.chart and result.chart.series[0].values == ["100.1000"]
    if kind == "hybrid":
        assert result.document and result.analytics
        assert "100.1000" in result.answer
        assert "delayed shipments" in result.answer
    if kind == "clarification":
        assert result.status == "clarification"


async def test_unauthorized_tool_failure_is_not_converted_to_partial_answer():
    request = OrchestrationRequest(
        workspace_id=uuid4(), question="Revenue in 2025", dataset_id=uuid4()
    )

    async def document_tool(_request: OrchestrationRequest, _question: str) -> QueryResponse:
        raise AssertionError("Document tool must not run")

    async def analytics_tool(_request: OrchestrationRequest, _question: str) -> AnalyticsResponse:
        raise SecurityError(404, "resource_not_found", "Resource is unavailable")

    with pytest.raises(SecurityError, match="resource_not_found"):
        await execute(request, document_tool, analytics_tool)


async def test_timeout_terminates_graph():
    request = OrchestrationRequest(
        workspace_id=uuid4(), question="Revenue in 2025", dataset_id=uuid4()
    )

    async def document_tool(_request: OrchestrationRequest, _question: str) -> QueryResponse:
        raise AssertionError("Document tool must not run")

    async def analytics_tool(_request: OrchestrationRequest, _question: str) -> AnalyticsResponse:
        await asyncio.sleep(0.1)
        return _analytics(_request)

    with pytest.raises(SecurityError, match="orchestration_timeout"):
        await execute(request, document_tool, analytics_tool, timeout_seconds=0.01)


async def test_hybrid_provider_outage_returns_only_verified_analytics():
    request = OrchestrationRequest(
        workspace_id=uuid4(),
        question="Compare revenue with the report",
        document_resource_ids=[uuid4()],
        dataset_id=uuid4(),
        document_question="Summarize the report",
        analytics_question="Revenue in 2025",
    )

    async def document_tool(_request: OrchestrationRequest, _question: str) -> QueryResponse:
        raise SecurityError(503, "generation_unavailable", "Provider unavailable")

    async def analytics_tool(selected: OrchestrationRequest, _question: str) -> AnalyticsResponse:
        return _analytics(selected)

    result = await execute(request, document_tool, analytics_tool)
    assert result.status == "partial"
    assert result.document is None
    assert result.analytics and result.analytics.rows[0].value == "100.1000"
    assert result.uncertainty and "unavailable" in result.uncertainty


async def test_hybrid_analytics_failure_does_not_fall_back_to_document():
    request = OrchestrationRequest(
        workspace_id=uuid4(),
        question="Compare revenue with the report",
        document_resource_ids=[uuid4()],
        dataset_id=uuid4(),
        document_question="Summarize the report",
        analytics_question="Revenue in 2025",
    )
    called = []

    async def document_tool(_request: OrchestrationRequest, _question: str) -> QueryResponse:
        called.append("document")
        return _document(request)

    async def analytics_tool(_request: OrchestrationRequest, _question: str) -> AnalyticsResponse:
        raise SecurityError(503, "analytics_unavailable", "Analytics unavailable")

    with pytest.raises(SecurityError, match="analytics_unavailable"):
        await execute(request, document_tool, analytics_tool)
    assert called == []


def test_invalid_chart_without_dataset_is_rejected():
    with pytest.raises(ValidationError):
        OrchestrationRequest(workspace_id=uuid4(), question="Show a chart", chart=True)


async def test_document_token_caps_are_forwarded_to_phase5(monkeypatch):
    request = OrchestrationRequest(
        workspace_id=uuid4(),
        question="Summarize the report",
        document_resource_ids=[uuid4()],
        max_context_tokens=256,
        max_completion_tokens=128,
    )
    access = AccessContext(uuid4(), uuid4(), "viewer", 1, False, 1, "trace")
    captured = []

    async def fake_rag(body, _request, _context):
        captured.append(body)
        return _document(request)

    monkeypatch.setattr(orchestration_routes, "rag_query", fake_rag)
    app_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=Settings(_env_file=None)))
    )
    result = await orchestration_routes.query(request, app_request, access)
    assert result.status == "answered"
    assert captured[0].max_context_tokens == 256
    assert captured[0].max_completion_tokens == 128


async def test_chart_word_creates_spec_without_flag():
    request = OrchestrationRequest(
        workspace_id=uuid4(), question="Chart revenue by region in 2025", dataset_id=uuid4()
    )

    async def document_tool(_request: OrchestrationRequest, _question: str) -> QueryResponse:
        raise AssertionError("Document tool must not run")

    async def analytics_tool(selected: OrchestrationRequest, _question: str) -> AnalyticsResponse:
        return _analytics(selected)

    result = await execute(request, document_tool, analytics_tool)
    assert result.chart and result.chart.series[0].values == ["100.1000"]


def test_hybrid_requires_explicit_decomposition():
    request = OrchestrationRequest(
        workspace_id=uuid4(),
        question="Why did revenue fall?",
        document_resource_ids=[uuid4()],
        dataset_id=uuid4(),
    )
    assert classify(request).route == "clarification"


def test_document_query_can_use_authorized_workspace_scope():
    request = OrchestrationRequest(workspace_id=uuid4(), question="Summarize our policy")
    assert request.document_resource_ids == []
    assert classify(request).route == "document"
