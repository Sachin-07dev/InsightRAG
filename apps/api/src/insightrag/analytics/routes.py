"""Non-streamed, bounded analytics request/response API."""

from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy.exc import DBAPIError

from insightrag.analytics.contracts import AnalyticsRequest, AnalyticsResponse, AnalyticsSchema
from insightrag.analytics.service import analyze, discover
from insightrag.security.context import SecurityError
from insightrag.security.dependencies import Context

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


def _database_error(exc: DBAPIError) -> SecurityError:
    if getattr(exc.orig, "sqlstate", None) == "57014":
        return SecurityError(504, "analytics_timeout", "Analytics query timed out")
    return SecurityError(503, "analytics_unavailable", "Analytics database is unavailable")


@router.post("/query", response_model=AnalyticsResponse)
async def query(body: AnalyticsRequest, request: Request, context: Context) -> AnalyticsResponse:
    try:
        return await analyze(request.app.state.database, context, body)
    except DBAPIError as exc:
        raise _database_error(exc) from None


@router.get("/datasets/{resource_id}/schema", response_model=AnalyticsSchema)
async def schema(resource_id: UUID, request: Request, context: Context) -> AnalyticsSchema:
    try:
        return await discover(request.app.state.database, context, resource_id)
    except DBAPIError as exc:
        raise _database_error(exc) from None
