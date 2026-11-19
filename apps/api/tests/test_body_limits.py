"""Exercise actual ASGI receive chunks rather than trusting Content-Length."""

import json
from uuid import UUID, uuid4

import pytest
from insightrag.core.body_limits import MAX_NON_UPLOAD_BODY_BYTES, BodySizeLimitMiddleware
from insightrag.core.middleware import RequestContextMiddleware


async def invoke(chunks, *, path="/api/v1/diagnostics/echo", method="POST", headers=()):
    received = []
    sent = []
    consumed = []
    request_id = str(uuid4())
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [(b"x-request-id", request_id.encode()), *headers],
        "server": ("test", 80),
        "client": ("test", 1234),
    }

    async def downstream(scope, receive, send):
        while True:
            message = await receive()
            received.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]

    async def receive():
        consumed.append(True)
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    app = RequestContextMiddleware(BodySizeLimitMiddleware(downstream))
    await app(scope, receive, send)
    return received, sent, consumed, request_id


def assert_safe_rejection(result):
    received, sent, _, request_id = result
    assert received == []
    assert sent[0]["status"] == 413
    headers = dict(sent[0]["headers"])
    assert headers[b"x-request-id"].decode() == request_id
    assert headers[b"cache-control"] == b"no-store"
    body = json.loads(sent[1]["body"])
    assert body["code"] == "request_too_large"
    assert body["request_id"] == request_id
    assert body["issues"] == []
    assert b"secret-canary" not in sent[1]["body"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        (),
        ((b"content-length", b"1"),),
        ((b"transfer-encoding", b"chunked"),),
        ((b"content-type", b"application/json"),),
        ((b"content-type", b"application/octet-stream"),),
    ],
)
async def test_actual_byte_limit_covers_missing_misleading_chunked_and_any_type(headers):
    result = await invoke([b"secret-canary", b"x" * MAX_NON_UPLOAD_BODY_BYTES], headers=headers)
    assert_safe_rejection(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "length",
    [str(MAX_NON_UPLOAD_BODY_BYTES + 1).encode(), b"9" * 5000, b"-1", b"", b"1, 2"],
)
async def test_declared_oversize_or_invalid_length_rejects_without_consuming_body(length):
    result = await invoke([b"not read"], headers=((b"content-length", length),))
    assert_safe_rejection(result)
    assert result[2] == []


@pytest.mark.asyncio
async def test_duplicate_content_lengths_fail_closed_without_reading():
    result = await invoke(
        [b"not read"], headers=((b"content-length", b"1"), (b"content-length", b"1"))
    )
    assert_safe_rejection(result)
    assert result[2] == []


@pytest.mark.asyncio
async def test_small_chunked_body_is_replayed_exactly_to_application():
    received, sent, _, _ = await invoke([b'{"message":', b'"synthetic"}'])
    assert b"".join(received) == b'{"message":"synthetic"}'
    assert sent[0]["status"] == 204


@pytest.mark.asyncio
async def test_exact_limit_is_accepted():
    received, sent, _, _ = await invoke([b"x" * MAX_NON_UPLOAD_BODY_BYTES])
    assert len(b"".join(received)) == MAX_NON_UPLOAD_BODY_BYTES
    assert sent[0]["status"] == 204


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path",
    [
        ("PUT", f"/api/v1/resources/{uuid4()}/validate-upload"),
        ("POST", "/api/v1/resources/not-a-uuid/validate-upload"),
        ("POST", f"/api/v1/resources/{uuid4()}/validate-upload/"),
        ("POST", f"/api/v1/resources/{uuid4()}/validate-upload/extra"),
    ],
)
async def test_only_exact_upload_post_route_is_exempt(method, path):
    result = await invoke([b"x" * (MAX_NON_UPLOAD_BODY_BYTES + 1)], method=method, path=path)
    assert_safe_rejection(result)


@pytest.mark.asyncio
async def test_exact_upload_route_preserves_streaming_chunks():
    chunks = [b"x" * MAX_NON_UPLOAD_BODY_BYTES, b"extra"]
    received, sent, _, _ = await invoke(
        chunks,
        path=f"/api/v1/resources/{uuid4()}/validate-upload",
        headers=((b"content-length", b"52428800"),),
    )
    assert received == chunks
    assert sent[0]["status"] == 204


def test_fastapi_body_cap_precedes_json_parsing_and_preserves_request_id(client):
    request_id = str(uuid4())
    response = client.post(
        f"/api/v1/workspaces/{uuid4()}/resources",
        content=b"{secret-canary" + b"x" * MAX_NON_UPLOAD_BODY_BYTES,
        headers={"Content-Type": "application/json", "X-Request-ID": request_id},
    )
    assert response.status_code == 413
    assert response.json()["request_id"] == request_id
    assert response.headers["X-Request-ID"] == request_id
    assert "secret-canary" not in response.text


def test_small_normal_route_still_works(client):
    response = client.post("/api/v1/diagnostics/echo", json={"message": "synthetic"})
    assert response.status_code == 200
    assert response.json()["message"] == "synthetic"


def test_large_upload_remains_authentication_gated(client):
    response = client.post(
        f"/api/v1/resources/{uuid4()}/validate-upload",
        content=b"x" * (MAX_NON_UPLOAD_BODY_BYTES + 1),
        headers={"X-Organization-ID": str(uuid4()), "X-Filename": "synthetic.txt"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    UUID(response.json()["request_id"])
