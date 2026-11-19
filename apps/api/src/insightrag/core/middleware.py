"""Pure ASGI context middleware; no buffering of request/response bodies."""

from time import perf_counter
from uuid import UUID, uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw = Headers(scope=scope).get("x-request-id", "")
        try:
            request_id = str(UUID(raw)) if len(raw) <= 36 else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        tokens = structlog.contextvars.bind_contextvars(request_id=request_id)
        started, status = perf_counter(), 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            # Log the route template, never raw URLs/query strings or request payloads.
            route = getattr(scope.get("route"), "path", "<unmatched>")
            structlog.get_logger().info(
                "http_request",
                method=scope["method"],
                route=route,
                status=status,
                duration_ms=round((perf_counter() - started) * 1000, 3),
            )
            structlog.contextvars.reset_contextvars(**tokens)
