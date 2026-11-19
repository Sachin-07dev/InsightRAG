"""Central errors intentionally omit exception strings and invalid input values."""

from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from insightrag.api.contracts import ErrorResponse, ValidationIssue
from insightrag.security.context import SecurityError


def error_response(
    request: Request,
    status: int,
    code: str,
    message: str,
    issues: list[ValidationIssue] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", str(uuid4()))
    body = ErrorResponse(code=code, message=message, request_id=request_id, issues=issues or [])
    return JSONResponse(
        status_code=status,
        content=body.model_dump(),
        headers={
            "X-Request-ID": request_id,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SecurityError)
    async def security_error(request: Request, exc: SecurityError) -> JSONResponse:
        response = error_response(request, exc.status, exc.code, exc.message)
        if exc.status == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        if exc.status == 429 and exc.retry_after is not None:
            response.headers["Retry-After"] = str(exc.retry_after)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        issues = [
            ValidationIssue(location=[str(item) for item in error["loc"]], kind=error["type"])
            for error in exc.errors()
        ]
        return error_response(request, 422, "invalid_request", "Request validation failed", issues)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = {404: "resource_not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        response = error_response(request, exc.status_code, code, "Request could not be completed")
        # Preserve protocol headers (for example Allow), not arbitrary error details.
        if exc.status_code == 405 and exc.headers and "Allow" in exc.headers:
            response.headers["Allow"] = exc.headers["Allow"]
        return response

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        structlog.get_logger().error(
            "unhandled_error",
            error_type=type(exc).__name__,
            request_id=getattr(request.state, "request_id", None),
        )
        return error_response(request, 500, "internal_error", "An unexpected error occurred")
