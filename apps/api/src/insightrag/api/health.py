"""Separate process liveness from bounded dependency/schema readiness."""

import asyncio
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from insightrag.api.contracts import DependencyStatus, Liveness, Readiness

router = APIRouter(tags=["health"])
EXPECTED_REVISION = "0008_analytics_scope"


async def dependency_status(
    check: Callable[[], Awaitable[bool]], budget_seconds: float
) -> DependencyStatus:
    try:
        async with asyncio.timeout(budget_seconds):
            return "ok" if await check() else "unavailable"
    except TimeoutError:
        return "timeout"
    except Exception:
        return "unavailable"


async def check_dependencies(request: Request) -> dict[str, DependencyStatus]:
    database = request.app.state.database
    redis = request.app.state.redis

    async def check_database() -> bool:
        async with database.engine.connect() as connection:
            version = await connection.scalar(
                text("SELECT value FROM platform_metadata WHERE key = 'schema_version'")
            )
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            return bool(version == "phase6" and revision == EXPECTED_REVISION)

    async def check_redis() -> bool:
        return bool(await redis.ping())

    timeout = request.app.state.settings.dependency_timeout_seconds

    async def optional_check(
        check: Callable[[], Awaitable[bool]], configured: bool
    ) -> DependencyStatus:
        if not configured:
            return "not_configured"
        return await dependency_status(check, timeout)

    db, cache = await asyncio.gather(
        optional_check(check_database, database.engine is not None),
        optional_check(check_redis, redis is not None),
    )
    return {"database": db, "redis": cache}


@router.get("/health/live", response_model=Liveness)
async def live() -> Liveness:
    return Liveness()


@router.get("/health/ready", response_model=Readiness, responses={503: {"model": Readiness}})
async def ready(request: Request, response: Response) -> Readiness:
    dependencies = await check_dependencies(request)
    is_ready = all(value == "ok" for value in dependencies.values())
    response.status_code = 200 if is_ready else 503
    return Readiness(status="ready" if is_ready else "not_ready", dependencies=dependencies)
