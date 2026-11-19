import asyncio
import json
from uuid import UUID, uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi.testclient import TestClient
from insightrag.api.health import dependency_status
from insightrag.core.config import Settings
from insightrag.main import create_app


def test_liveness_does_not_claim_unconfigured_dependencies_are_ready(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"database": "not_configured", "redis": "not_configured"},
    }


def test_versioned_metadata_and_no_tenant_data_routes(client):
    assert client.get("/api/v1/meta").json()["tenant_data_enabled"] is True
    assert client.get("/api/v1/meta").json()["phase"] == 3
    for route in ["/api/v1/organizations", "/api/v1/resources", "/api/v1/query-runs"]:
        assert client.get(route).status_code == 404


def test_openapi_describes_validation_and_success_contracts(client):
    schema = client.get("/api/v1/openapi.json").json()
    operation = schema["paths"]["/api/v1/diagnostics/echo"]["post"]
    assert "requestBody" in operation
    assert operation["responses"]["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "ErrorResponse"
    )
    assert client.get("/docs").status_code == 200


def test_request_ids_are_canonical_validated_and_returned(client):
    supplied = str(uuid4())
    response = client.post(
        "/api/v1/diagnostics/echo",
        json={"message": "synthetic"},
        headers={"X-Request-ID": supplied},
    )
    assert response.json() == {"message": "synthetic", "request_id": supplied}
    assert response.headers["x-request-id"] == supplied
    invalid = client.get("/health/live", headers={"X-Request-ID": "untrusted-content"})
    assert str(UUID(invalid.headers["x-request-id"])) == invalid.headers["x-request-id"]


@pytest.mark.parametrize(
    "payload",
    [
        {"message": 42},
        {"message": ""},
        {"message": "x" * 129},
        {"message": "hi", "secret": "must-not-leak"},
    ],
)
def test_validation_redacts_values_and_rejects_extra_or_invalid_fields(client, payload):
    response = client.post("/api/v1/diagnostics/echo", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "must-not-leak" not in response.text
    assert all("input" not in issue for issue in response.json()["issues"])
    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_unexpected_errors_redact_details_and_keep_correlation(settings):
    app = create_app(settings)

    @app.get("/test-error")
    async def error():
        raise RuntimeError("synthetic-secret-do-not-disclose")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-error")
    assert response.status_code == 500
    assert "synthetic-secret" not in response.text
    assert response.json()["request_id"] == response.headers["x-request-id"]


def test_production_disables_docs_and_diagnostic_echo():
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+asyncpg://test@127.0.0.1/test",
        redis_url="redis://127.0.0.1:6379/0",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/api/v1/openapi.json").status_code == 404
        assert client.post("/api/v1/diagnostics/echo", json={"message": "hi"}).status_code == 404
        assert client.get("/health/live").status_code == 200


async def test_parallel_requests_have_isolated_request_context(settings):
    app = create_app(settings)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:

            async def send():
                request_id = str(uuid4())
                response = await client.post(
                    "/api/v1/diagnostics/echo",
                    json={"message": "parallel"},
                    headers={"X-Request-ID": request_id},
                )
                assert response.json()["request_id"] == request_id
                return response.headers["x-request-id"]

            assert len(set(await asyncio.gather(*(send() for _ in range(30))))) == 30


async def test_dependency_failures_are_bounded_and_redacted():
    async def slow():
        await asyncio.sleep(1)
        return True

    async def fail():
        raise RuntimeError("private-connection-details")

    async def good():
        return True

    assert await dependency_status(slow, 0.01) == "timeout"
    assert await dependency_status(fail, 0.1) == "unavailable"
    assert await dependency_status(good, 0.1) == "ok"


def test_access_logs_omit_query_and_payload_values(settings, capsys):
    with TestClient(create_app(settings)) as client:
        client.post("/api/v1/diagnostics/echo?token=query-canary", json={"message": "body-canary"})
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "query-canary" not in output and "body-canary" not in output
    events = [json.loads(line) for line in output.splitlines() if line.startswith("{")]
    assert any(
        event.get("event") == "http_request" and event.get("route") == "/api/v1/diagnostics/echo"
        for event in events
    )


async def test_lifespan_disposes_resources(settings, monkeypatch):
    disposed = []

    async def close(self):
        disposed.append(True)

    monkeypatch.setattr("insightrag.main.Database.close", close)
    async with LifespanManager(create_app(settings)):
        assert not disposed
    assert disposed == [True]
