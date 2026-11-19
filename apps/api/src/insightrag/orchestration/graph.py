"""Deterministic LangGraph workflow; trusted services retain authorization ownership."""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from opentelemetry import trace

from insightrag.analytics.contracts import AnalyticsResponse
from insightrag.orchestration.contracts import (
    ChartSeries,
    ChartSpecification,
    OrchestrationRequest,
    OrchestrationResponse,
    RouteDecision,
)
from insightrag.retrieval.contracts import QueryResponse
from insightrag.retrieval.query import prepare_query
from insightrag.security.context import SecurityError

DocumentTool = Callable[[OrchestrationRequest, str], Awaitable[QueryResponse]]
AnalyticsTool = Callable[[OrchestrationRequest, str], Awaitable[AnalyticsResponse]]
logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class GraphState(TypedDict, total=False):
    request: OrchestrationRequest
    decision: RouteDecision
    document: QueryResponse | None
    analytics: AnalyticsResponse | None
    document_unavailable: bool
    response: OrchestrationResponse
    executed_nodes: list[str]


def classify(request: OrchestrationRequest) -> RouteDecision:
    """Classify only the supplied scope; no model output can add resources."""
    try:
        prepared = prepare_query(request.question)
    except ValueError:
        return RouteDecision(route="clarification", reason="Question validation failed")
    has_dataset = request.dataset_id is not None
    # Phase 5 intentionally treats an empty document-ID list as all currently
    # readable, active documents in this authorized workspace.
    has_documents = bool(request.document_resource_ids) or (
        not has_dataset and prepared.kind == "document" and not request.chart
    )
    if has_documents and has_dataset:
        if not request.document_question or not request.analytics_question:
            return RouteDecision(
                route="clarification",
                reason="Provide separate document and analytics questions for a combined request",
            )
        return RouteDecision(route="hybrid", reason="Both governed sources were requested")
    if has_dataset:
        return RouteDecision(route="analytics", reason="Governed dataset was selected")
    if has_documents and prepared.kind == "document" and not request.chart:
        return RouteDecision(route="document", reason="Authorized document scope was selected")
    if has_documents:
        return RouteDecision(
            route="clarification", reason="Numerical questions require a governed dataset"
        )
    return RouteDecision(route="clarification", reason="Select authorized source resources")


def build_chart(result: AnalyticsResponse) -> ChartSpecification:
    """Chart data is copied from verified decimal strings; never computed by an LLM."""
    if not result.rows:
        raise ValueError("No verified chart rows")
    return ChartSpecification(
        kind="line" if re.fullmatch(r"\d{4}-\d{2}", result.rows[0].dimension) else "bar",
        title=f"{result.metric} by dimension",
        categories=[row.dimension for row in result.rows],
        series=[ChartSeries(name=result.metric, values=[row.value for row in result.rows])],
        unit=result.unit,
        metric_definition_version=result.metric_definition_version,
        dataset_version_id=result.version_id,
    )


def build_graph(
    document_tool: DocumentTool, analytics_tool: AnalyticsTool
) -> CompiledStateGraph[GraphState, None, GraphState, GraphState]:
    """Compile a request-local graph without a sensitive-content checkpointer."""

    async def classifier(state: GraphState) -> GraphState:
        return {
            "decision": classify(state["request"]),
            "executed_nodes": [*state.get("executed_nodes", []), "classify"],
        }

    async def document(state: GraphState) -> GraphState:
        request = state["request"]
        question = request.document_question or request.question
        try:
            result = await document_tool(request, question)
        except SecurityError as exc:
            if state["decision"].route != "hybrid" or exc.status not in {503, 504}:
                raise
            return {
                "document_unavailable": True,
                "executed_nodes": [*state["executed_nodes"], "document"],
            }
        return {"document": result, "executed_nodes": [*state["executed_nodes"], "document"]}

    async def analytics(state: GraphState) -> GraphState:
        request = state["request"]
        question = request.analytics_question or request.question
        result = await analytics_tool(request, question)
        return {"analytics": result, "executed_nodes": [*state["executed_nodes"], "analytics"]}

    async def verify(state: GraphState) -> GraphState:
        decision = state["decision"].route
        document_result = state.get("document")
        analytics_result = state.get("analytics")
        if (
            decision in {"document", "hybrid"}
            and document_result is None
            and not state.get("document_unavailable", False)
        ):
            raise SecurityError(502, "orchestration_invalid", "Document result is missing")
        if decision in {"analytics", "hybrid"} and analytics_result is None:
            raise SecurityError(502, "orchestration_invalid", "Analytics result is missing")
        if document_result and document_result.status not in {"answered", "abstained"}:
            raise SecurityError(
                422, "orchestration_clarification", "Document query needs clarification"
            )
        if analytics_result and analytics_result.status != "answered":
            raise SecurityError(502, "orchestration_invalid", "Analytics result is unverified")
        return {"executed_nodes": [*state["executed_nodes"], "verify"]}

    async def synthesize(state: GraphState) -> GraphState:
        decision = state["decision"]
        document_result = state.get("document")
        analytics_result = state.get("analytics")
        parts: list[str] = []
        if analytics_result:
            rows = ", ".join(
                f"{row.dimension}: {row.value if row.value is not None else 'undefined'}"
                for row in analytics_result.rows
            )
            parts.append(
                f"Verified {analytics_result.metric} ({analytics_result.unit}), "
                f"{analytics_result.period_start} to {analytics_result.period_end_exclusive} "
                f"(end exclusive): {rows}."
            )
        if document_result and document_result.status == "answered":
            parts.append(f"Document evidence: {document_result.answer}")
        status: Literal["answered", "partial", "abstained"] = "answered"
        uncertainty = None
        if document_result and document_result.status == "abstained":
            status = "partial" if analytics_result else "abstained"
            uncertainty = "No sufficient authorized document evidence was available."
        if state.get("document_unavailable"):
            status = "partial"
            uncertainty = "Document retrieval was unavailable; only verified analytics is included."
        if not parts:
            parts.append("I could not verify an answer from the available evidence.")
        response = OrchestrationResponse(
            status=status,
            route=decision.route,
            answer="\n\n".join(parts),
            document=document_result,
            analytics=analytics_result,
            uncertainty=uncertainty,
            executed_nodes=[*state["executed_nodes"], "synthesize"],
        )
        return {"response": response, "executed_nodes": response.executed_nodes}

    async def chart(state: GraphState) -> GraphState:
        analytics_result = state.get("analytics")
        if analytics_result is None:
            raise SecurityError(502, "orchestration_invalid", "Verified chart data is missing")
        response = OrchestrationResponse.model_validate(
            {
                **state["response"].model_dump(),
                "chart": build_chart(analytics_result),
                "executed_nodes": [*state["executed_nodes"], "chart"],
            }
        )
        return {"response": response, "executed_nodes": response.executed_nodes}

    async def clarify(state: GraphState) -> GraphState:
        response = OrchestrationResponse(
            status="clarification",
            route="clarification",
            answer=state["decision"].reason,
            executed_nodes=[*state["executed_nodes"], "clarify"],
        )
        return {"response": response, "executed_nodes": response.executed_nodes}

    graph = StateGraph(GraphState)
    graph.add_node("classify", classifier)
    graph.add_node("document", document)
    graph.add_node("analytics", analytics)
    graph.add_node("verify", verify)
    graph.add_node("synthesize", synthesize)
    graph.add_node("chart", chart)
    graph.add_node("clarify", clarify)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        lambda state: state["decision"].route,
        {
            "document": "document",
            "analytics": "analytics",
            "hybrid": "analytics",
            "clarification": "clarify",
        },
    )
    graph.add_conditional_edges(
        "analytics",
        lambda state: "document" if state["decision"].route == "hybrid" else "verify",
        {"document": "document", "verify": "verify"},
    )
    graph.add_edge("document", "verify")
    graph.add_edge("verify", "synthesize")
    graph.add_conditional_edges(
        "synthesize",
        lambda state: (
            "chart"
            if state.get("analytics")
            and (
                state["request"].chart
                or re.search(r"\b(?:chart|graph|plot)\b", state["request"].question, re.I)
            )
            else "done"
        ),
        {"chart": "chart", "done": END},
    )
    graph.add_edge("chart", END)
    graph.add_edge("clarify", END)
    return graph.compile()


async def execute(
    request: OrchestrationRequest,
    document_tool: DocumentTool,
    analytics_tool: AnalyticsTool,
    *,
    timeout_seconds: float = 20.0,
) -> OrchestrationResponse:
    """Bound total execution; never retry side-effecting RAG conversation writes."""
    graph = build_graph(document_tool, analytics_tool)
    started = perf_counter()
    with tracer.start_as_current_span("orchestration.query") as span:
        try:
            state = await asyncio.wait_for(
                graph.ainvoke(
                    {"request": request, "executed_nodes": []}, config={"recursion_limit": 8}
                ),
                timeout_seconds,
            )
        except TimeoutError:
            span.set_attribute("orchestration.timeout", True)
            raise SecurityError(
                504, "orchestration_timeout", "Query orchestration timed out"
            ) from None
    response = state.get("response")
    if not isinstance(response, OrchestrationResponse):
        raise SecurityError(502, "orchestration_invalid", "Query orchestration failed")
    logger.info(
        {
            "event": "orchestration_completed",
            "route": response.route,
            "status": response.status,
            "nodes": response.executed_nodes,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
            "prompt_tokens": response.document.prompt_tokens if response.document else None,
            "completion_tokens": response.document.completion_tokens if response.document else None,
        }
    )
    return response
