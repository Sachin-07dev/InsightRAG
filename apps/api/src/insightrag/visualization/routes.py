"""Request-local dashboards: every card runs through Phase 7 and Phase 6 authorization."""

import asyncio

from fastapi import APIRouter, Request, Response

from insightrag.orchestration.contracts import OrchestrationRequest
from insightrag.orchestration.routes import query as orchestrate
from insightrag.security.context import SecurityError
from insightrag.security.dependencies import Context
from insightrag.visualization.contracts import DashboardCard, DashboardRequest, DashboardResponse
from insightrag.visualization.service import build_view

router = APIRouter(prefix="/api/v1/visualization", tags=["visualization"])
_DASHBOARD_TIMEOUT_SECONDS = 25.0


@router.post("/dashboard", response_model=DashboardResponse)
async def dashboard(
    body: DashboardRequest, request: Request, response: Response, context: Context
) -> DashboardResponse:
    response.headers["Cache-Control"] = "private, no-store"

    async def assemble() -> list[DashboardCard]:
        cards: list[DashboardCard] = []
        version_id = None
        for view in body.views:
            result = await orchestrate(
                OrchestrationRequest(
                    workspace_id=body.workspace_id,
                    dataset_id=body.dataset_id,
                    question=view.question,
                    region=view.region,
                    currency=view.currency,
                    year=view.year,
                    comparison_year=view.comparison_year,
                    chart=False,
                ),
                request,
                context,
            )
            if result.status != "answered" or result.analytics is None:
                raise SecurityError(
                    422, "visualization_unavailable", "Verified analytics unavailable"
                )
            if version_id is None:
                version_id = result.analytics.version_id
            elif result.analytics.version_id != version_id:
                raise SecurityError(
                    409,
                    "visualization_version_changed",
                    "Dataset version changed; refresh dashboard",
                )
            cards.append(
                DashboardCard(question=view.question, view=build_view(result.analytics, view.kind))
            )
        return cards

    try:
        cards = await asyncio.wait_for(assemble(), timeout=_DASHBOARD_TIMEOUT_SECONDS)
    except TimeoutError:
        raise SecurityError(504, "visualization_timeout", "Dashboard query timed out") from None
    return DashboardResponse(cards=cards)
