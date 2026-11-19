"""ASGI application factory; startup owns pools, shutdown releases them."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from insightrag.analytics.routes import router as analytics_router
from insightrag.api import health
from insightrag.api.contracts import ErrorResponse
from insightrag.api.v1.routes import diagnostics_router, router
from insightrag.core.body_limits import BodySizeLimitMiddleware
from insightrag.core.config import Settings
from insightrag.core.errors import register_exception_handlers
from insightrag.core.logging import configure_logging
from insightrag.core.middleware import RequestContextMiddleware
from insightrag.db.session import Database
from insightrag.ingestion.routes import router as ingestion_router
from insightrag.orchestration.routes import router as orchestration_router
from insightrag.retrieval.routes import router as retrieval_router
from insightrag.security.auth import OIDCVerifier
from insightrag.security.controls import RateLimiter
from insightrag.security.routes import router as security_router
from insightrag.security.uploads import ClamAVScanner, UnavailableScanner
from insightrag.visualization.routes import router as visualization_router


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.log_level)
        database = Database(config)
        redis: Redis | None = (
            Redis.from_url(
                config.redis_url.get_secret_value(),
                socket_timeout=config.dependency_timeout_seconds,
                socket_connect_timeout=config.dependency_timeout_seconds,
                decode_responses=True,
            )
            if config.redis_url
            else None
        )
        application.state.database = database
        application.state.redis = redis
        verifier = (
            OIDCVerifier(config.oidc_issuer, config.oidc_audience, config.oidc_jwks_url)
            if (config.oidc_issuer and config.oidc_audience and config.oidc_jwks_url)
            else None
        )
        application.state.oidc = verifier
        application.state.rate_limiter = RateLimiter(redis)
        application.state.scanner = (
            ClamAVScanner(config.clamav_host, config.clamav_port)
            if (config.clamav_host)
            else UnavailableScanner()
        )
        try:
            yield
        finally:
            if verifier:
                await verifier.close()
            if redis:
                await redis.aclose()
            await database.close()

    application = FastAPI(
        title="InsightRAG Enterprise",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json" if config.docs_enabled else None,
        responses={
            413: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    application.state.settings = config
    # add_middleware inserts at the front: context wraps the body cap and assigns
    # correlation before the cap can reject an oversized request.
    application.add_middleware(BodySizeLimitMiddleware)
    application.add_middleware(RequestContextMiddleware)
    register_exception_handlers(application)
    application.include_router(health.router)
    application.include_router(router)
    application.include_router(security_router)
    application.include_router(ingestion_router)
    application.include_router(retrieval_router)
    application.include_router(analytics_router)
    application.include_router(orchestration_router)
    application.include_router(visualization_router)
    if config.docs_enabled:
        application.include_router(diagnostics_router)
    return application


app = create_app()
