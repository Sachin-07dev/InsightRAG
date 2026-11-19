"""Authenticated Phase 7 endpoint with server-derived identity and trusted tools."""

from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError

from insightrag.analytics.contracts import AnalyticsRequest, AnalyticsResponse
from insightrag.analytics.routes import _database_error
from insightrag.analytics.service import analyze
from insightrag.orchestration.contracts import OrchestrationRequest, OrchestrationResponse
from insightrag.orchestration.graph import execute
from insightrag.retrieval.contracts import QueryRequest, QueryResponse
from insightrag.retrieval.routes import query as rag_query
from insightrag.security.dependencies import Context

router = APIRouter(prefix="/api/v1/orchestration", tags=["orchestration"])


@router.post("/query", response_model=OrchestrationResponse)
async def query(
    body: OrchestrationRequest, request: Request, context: Context
) -> OrchestrationResponse:
    async def document_tool(selected: OrchestrationRequest, question: str) -> QueryResponse:
        return await rag_query(
            QueryRequest(
                workspace_id=selected.workspace_id,
                question=question,
                resource_ids=selected.document_resource_ids,
                conversation_id=selected.conversation_id,
                max_context_tokens=selected.max_context_tokens,
                max_completion_tokens=selected.max_completion_tokens,
            ),
            request,
            context,
        )

    async def analytics_tool(selected: OrchestrationRequest, question: str) -> AnalyticsResponse:
        assert selected.dataset_id is not None  # Graph routing validated this precondition.
        try:
            return await analyze(
                request.app.state.database,
                context,
                AnalyticsRequest(
                    resource_id=selected.dataset_id,
                    question=question,
                    region=selected.region,
                    currency=selected.currency,
                    year=selected.year,
                    comparison_year=selected.comparison_year,
                ),
                expected_workspace_id=selected.workspace_id,
            )
        except DBAPIError as exc:
            raise _database_error(exc) from None

    return await execute(
        body,
        document_tool,
        analytics_tool,
        timeout_seconds=request.app.state.settings.orchestration_timeout_seconds,
    )
