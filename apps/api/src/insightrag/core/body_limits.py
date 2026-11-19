"""Bound request bytes before FastAPI can parse an unauthenticated JSON body.

Only the exact upload-validation route streams through: that endpoint authorizes
before reading and enforces its own larger streaming file limit. All other HTTP
methods, paths and content types share a small bounded control-plane body budget.
"""

import re

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from insightrag.core.errors import error_response

MAX_NON_UPLOAD_BODY_BYTES = 16 * 1024
_UPLOAD_PATH = re.compile(
    r"/api/v1/resources/"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/(?:validate-upload|versions)"
)


class BodySizeLimitMiddleware:
    """Pure ASGI middleware with a fixed, pre-parser memory bound per request."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = MAX_NON_UPLOAD_BODY_BYTES) -> None:
        if type(max_body_bytes) is not int or max_body_bytes < 1:
            raise ValueError("Body limit must be a positive byte count")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (
            scope["method"] == "POST" and _UPLOAD_PATH.fullmatch(scope["path"]) is not None
        ):
            await self.app(scope, receive, send)
            return

        lengths = Headers(scope=scope).getlist("content-length")
        if lengths and (
            len(lengths) != 1
            or re.fullmatch(r"[0-9]{1,20}", lengths[0]) is None
            or int(lengths[0]) > self.max_body_bytes
        ):
            await self._reject(scope, receive, send)
            return

        # Content-Length is only an early rejection hint. Always count actual
        # chunks, including missing, misleading and Transfer-Encoding requests.
        # Never append an oversized chunk to the bounded application buffer.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(chunk) > self.max_body_bytes - len(body):
                await self._reject(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        # RequestContextMiddleware must wrap this middleware so the standard
        # error contract and all response headers carry the same request ID.
        response = error_response(
            Request(scope), 413, "request_too_large", "Request body exceeds the configured limit"
        )
        await response(scope, receive, send)
