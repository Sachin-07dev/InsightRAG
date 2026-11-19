"""HTTP security boundaries with real signed tokens; integration uses runtime RLS/Redis.

No authentication/authorization dependency is replaced. Only the provider's public
signing-key source is pinned locally; the same verifier validates actual RSA tokens.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import time
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
import sqlalchemy as sa
from asgi_lifespan import LifespanManager
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from insightrag.core.config import Settings
from insightrag.main import create_app
from insightrag.security import routes as security_routes
from insightrag.security import schema
from insightrag.security.auth import OIDCVerifier
from insightrag.security.controls import JobEnvelopeRejected, SignedJobEnvelope, object_key
from insightrag.security.jobs import run_security_job
from pydantic import SecretStr
from test_rls_integration import security_db as security_db
from test_rls_integration import service_url

ISSUER = "https://synthetic.invalid"
AUDIENCE = "insightrag-api"
JWKS_URL = "https://synthetic.invalid/registered-jwks"
# Public synthetic test material only; production settings must use a private secret.
WORKER_TEST_KEY = b"synthetic-worker-test-signing-material-not-production"


@dataclass
class Tokens:
    private_key: rsa.RSAPrivateKey
    public_jwk: dict[str, Any]

    def issue(self, subject: UUID | str, **claims: Any) -> str:
        now = int(time())
        return jwt.encode(
            {
                "iss": ISSUER,
                "sub": str(subject),
                "aud": AUDIENCE,
                "iat": now,
                "nbf": now - 1,
                "exp": now + 600,
                **claims,
            },
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.public_jwk["kid"], "typ": "at+jwt"},
        )

    def headers(self, subject: UUID | str, organization: UUID, **claims: Any) -> dict[str, str]:
        return {
            "Authorization": "Bearer " + self.issue(subject, **claims),
            "X-Organization-ID": str(organization),
        }

    def verifier(self) -> OIDCVerifier:
        return OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, jwks={"keys": [self.public_jwk]})


@pytest.fixture(scope="module")
def tokens() -> Tokens:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid="synthetic-api-test-key", alg="RS256", use="sig", key_ops=["verify"])
    return Tokens(private, public)


@pytest.fixture
def secured_client(tokens: Tokens) -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, environment="test"))
    with TestClient(app, raise_server_exceptions=False) as client:
        app.state.oidc = tokens.verifier()
        yield client


def assert_safe_error(response: httpx.Response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    if status == 401:
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/v1/me", None),
        ("GET", "/api/v1/workspaces", None),
        ("GET", "/api/v1/directory/memberships", None),
        ("GET", "/api/v1/audit-events", None),
        ("GET", "/api/v1/resources/{id}", None),
        ("GET", "/api/v1/datasets/{id}/rows", None),
        ("GET", "/api/v1/documents/{id}/evidence", None),
        ("GET", "/api/v1/jobs/{id}", None),
        ("POST", "/api/v1/workspaces/{id}/resources", {"kind": "document", "title": "Test"}),
        ("POST", "/api/v1/resources/{id}/grants", {"user_id": str(uuid4()), "action": "read"}),
        ("DELETE", "/api/v1/resources/{id}", None),
        ("DELETE", "/api/v1/resources/{id}/grants/{grant}", None),
        ("POST", "/api/v1/resources/{id}/validate-upload", None),
    ],
)
def test_protected_routes_require_bearer_challenge(secured_client, method, path, body):
    response = secured_client.request(
        method,
        path.format(id=uuid4(), grant=uuid4()),
        headers={"X-Organization-ID": str(uuid4()), "X-Filename": "report.txt"},
        json=body,
    )
    assert_safe_error(response, 401, "authentication_required")


@pytest.mark.parametrize("authorization", ["Basic synthetic", "Bearer", "Digest synthetic"])
def test_missing_or_wrong_bearer_scheme_is_401(secured_client, authorization):
    response = secured_client.get(
        "/api/v1/me", headers={"Authorization": authorization, "X-Organization-ID": str(uuid4())}
    )
    assert_safe_error(response, 401, "authentication_required")


@pytest.mark.parametrize(
    "claims",
    [
        {"iss": "https://other-issuer.invalid"},
        {"aud": "another-api"},
        {"exp": 1},
        {"iat": int(time()) + 600},
    ],
)
def test_invalid_signed_token_returns_safe_401_before_database(secured_client, tokens, claims):
    token = tokens.issue("synthetic-subject", **claims)
    response = secured_client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer " + token, "X-Organization-ID": str(uuid4())},
    )
    assert_safe_error(response, 401, "invalid_access_token")
    assert token not in response.text


@pytest.mark.parametrize("token", ["malformed-token", "a.b.c", "a" * 8193])
def test_malformed_or_oversized_token_is_401(secured_client, token):
    response = secured_client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer " + token, "X-Organization-ID": str(uuid4())},
    )
    assert_safe_error(response, 401, "invalid_access_token")


def test_unconfigured_identity_is_503_not_an_authenticated_principal(tokens):
    app = create_app(Settings(_env_file=None, environment="test"))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/me", headers=tokens.headers("synthetic-subject", uuid4()))
    assert_safe_error(response, 503, "identity_unavailable")
    assert "www-authenticate" not in response.headers


def test_valid_identity_without_database_fails_closed(secured_client, tokens):
    response = secured_client.get(
        "/api/v1/me", headers=tokens.headers("synthetic-subject", uuid4())
    )
    assert_safe_error(response, 503, "security_unavailable")


def test_production_rejects_plain_http_before_identity_or_database(tokens):
    # Lazy pools are never connected: this test stops at the HTTP identity boundary.
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url=SecretStr("postgresql+asyncpg://synthetic.invalid/test"),
        redis_url=SecretStr("redis://synthetic.invalid/0"),
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.get("/api/v1/me", headers=tokens.headers("synthetic-subject", uuid4()))
    assert_safe_error(response, 400, "https_required")


@pytest.fixture
async def security_api(security_db, tokens: Tokens) -> AsyncIterator[dict[str, Any]]:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=SecretStr(service_url("DATABASE")),
        redis_url=SecretStr(service_url("REDIS")),
        pool_size=1,
        pool_max_overflow=0,
        dependency_timeout_seconds=10,
        rate_limit_per_user=10000,
        rate_limit_per_organization=100000,
        upload_max_bytes=64,
    )
    app = create_app(settings)
    verifier = tokens.verifier()
    async with LifespanManager(app):
        app.state.oidc = verifier
        # Deployment readiness pings this dependency before serving traffic. Warm
        # the real pool, while keeping the production two-second EVAL guard intact.
        assert await app.state.redis.ping()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://testserver"
        ) as client:
            try:
                yield {**security_db, "client": client, "tokens": tokens, "app": app}
            finally:
                await verifier.close()


@pytest.mark.integration
class TestSecurityAPIIntegration:
    async def test_me_uses_database_membership_and_ignores_token_roles_and_tenant(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(
            ids["alice"], ids["org_a"], tenant_id=str(ids["org_b"]), roles=["owner"], clearance=3
        )
        response = await api["client"].get("/api/v1/me", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["user_id"] == str(ids["alice"])
        assert response.json()["organization_id"] == str(ids["org_a"])
        assert response.json()["role"] == "analyst"
        assert response.json()["mfa"] is False
        denied = await api["client"].get("/api/v1/directory/memberships", headers=headers)
        assert_safe_error(denied, 403, "administration_denied")
        secret = await api["client"].get(f"/api/v1/resources/{ids['secret_a']}", headers=headers)
        assert_safe_error(secret, 404, "resource_not_found")

    async def test_unknown_identity_is_not_jit_enrolled_from_claims(self, security_api):
        api = security_api
        response = await api["client"].get(
            "/api/v1/me",
            headers=api["tokens"].headers(
                uuid4(), api["ids"]["org_a"], roles=["owner"], tenant_id=str(api["ids"]["org_a"])
            ),
        )
        assert_safe_error(response, 401, "identity_not_provisioned")

    async def test_wrong_organization_header_cannot_switch_tenant(self, security_api):
        api = security_api
        ids = api["ids"]
        response = await api["client"].get(
            "/api/v1/me", headers=api["tokens"].headers(ids["alice"], ids["org_b"])
        )
        assert_safe_error(response, 404, "organization_not_found")

    async def test_analytics_routes_enforce_dataset_and_header_scope(self, security_api):
        api = security_api
        ids = api["ids"]
        alice = api["tokens"].headers(ids["alice"], ids["org_a"])
        schema_response = await api["client"].get(
            f"/api/v1/analytics/datasets/{ids['dataset_b']}/schema", headers=alice
        )
        assert_safe_error(schema_response, 404, "resource_not_found")
        query = await api["client"].post(
            "/api/v1/analytics/query",
            headers=alice,
            json={
                "resource_id": str(ids["dataset_b"]),
                "question": "Revenue in 2025",
                "year": 2025,
            },
        )
        assert_safe_error(query, 404, "resource_not_found")
        forged = await api["client"].post(
            "/api/v1/analytics/query",
            headers=api["tokens"].headers(ids["alice"], ids["org_b"]),
            json={
                "resource_id": str(ids["dataset_b"]),
                "question": "Revenue in 2025",
                "year": 2025,
            },
        )
        assert_safe_error(forged, 404, "organization_not_found")
        orchestration = await api["client"].post(
            "/api/v1/orchestration/query",
            headers=alice,
            json={
                "workspace_id": str(ids["workspace_a"]),
                "dataset_id": str(ids["dataset_b"]),
                "question": "Revenue in 2025",
                "year": 2025,
            },
        )
        assert_safe_error(orchestration, 404, "resource_not_found")
        wrong_workspace = await api["client"].post(
            "/api/v1/orchestration/query",
            headers=alice,
            json={
                "workspace_id": str(ids["workspace_b"]),
                "dataset_id": str(ids["dataset_a"]),
                "question": "Revenue in 2025",
                "year": 2025,
            },
        )
        assert_safe_error(wrong_workspace, 404, "resource_not_found")

    async def test_company_a_cannot_read_or_mutate_company_b_resource_boundaries(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["alice"], ids["org_a"])
        job_b = uuid4()
        async with api["owner"].begin() as connection:
            revision = await connection.scalar(
                sa.select(schema.orgs.c.policy_revision).where(schema.orgs.c.id == ids["org_b"])
            )
            await connection.execute(
                schema.security_jobs.insert().values(
                    org_id=ids["org_b"],
                    id=job_b,
                    resource_id=ids["document_b"],
                    requested_by=ids["bob"],
                    action="read",
                    policy_revision=revision,
                )
            )
        requests = [
            ("GET", f"/api/v1/resources/{ids['document_b']}", None),
            ("GET", f"/api/v1/documents/{ids['document_b']}/evidence", None),
            ("GET", f"/api/v1/datasets/{ids['dataset_b']}/rows", None),
            ("GET", f"/api/v1/jobs/{job_b}", None),
            (
                "POST",
                f"/api/v1/resources/{ids['document_b']}/grants",
                {"user_id": str(ids["alice"]), "action": "read"},
            ),
            ("DELETE", f"/api/v1/resources/{ids['document_b']}/grants/{uuid4()}", None),
            ("DELETE", f"/api/v1/resources/{ids['document_b']}", None),
            (
                "POST",
                f"/api/v1/workspaces/{ids['workspace_b']}/resources",
                {"kind": "document", "title": "Forbidden cross-tenant upload"},
            ),
        ]
        for method, path, body in requests:
            response = await api["client"].request(method, path, headers=headers, json=body)
            assert_safe_error(response, 404, "resource_not_found")
            assert "999.99" not in response.text
            assert "document_b" not in response.text

    async def test_authorized_evidence_and_rows_remain_filtered(self, security_api):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["alice"], ids["org_a"])
        evidence = await api["client"].get(
            f"/api/v1/documents/{ids['document_a']}/evidence", headers=headers
        )
        assert evidence.status_code == 200, evidence.text
        assert [row["text"] for row in evidence.json()] == ["document_a synthetic sales report"]
        rows = await api["client"].get(f"/api/v1/datasets/{ids['dataset_a']}/rows", headers=headers)
        assert rows.status_code == 200, rows.text
        assert [(row["region"], row["payload"]) for row in rows.json()] == [
            ("Delhi", {"net_sales": "100.10"})
        ]
        workspace = await api["client"].get("/api/v1/workspaces", headers=headers)
        assert workspace.status_code == 200, workspace.text
        assert [row["id"] for row in workspace.json()] == [str(ids["workspace_a"])]

    async def test_directory_admin_does_not_receive_implicit_document_permission(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["manager"], ids["org_a"])
        directory = await api["client"].get("/api/v1/directory/memberships", headers=headers)
        assert directory.status_code == 200, directory.text
        assert {row["user_id"] for row in directory.json()} == {
            str(ids["alice"]),
            str(ids["manager"]),
        }
        response = await api["client"].get(
            f"/api/v1/resources/{ids['document_a']}", headers=headers
        )
        assert_safe_error(response, 404, "resource_not_found")

    async def test_create_private_quarantine_bootstraps_creator_without_publication(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["manager"], ids["org_a"])
        created = await api["client"].post(
            f"/api/v1/workspaces/{ids['workspace_a']}/resources",
            headers=headers,
            json={"kind": "document", "title": "Private synthetic upload"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["state"] == "quarantine"
        resource_id = UUID(created.json()["id"])
        async with api["owner"].begin() as connection:
            resource = (
                (
                    await connection.execute(
                        sa.select(schema.resources).where(schema.resources.c.id == resource_id)
                    )
                )
                .mappings()
                .one()
            )
            assert resource["state"] == "quarantine"
            assert resource["created_by"] == ids["manager"]
            grants = (
                await connection.execute(
                    sa.select(
                        schema.resource_grants.c.user_id, schema.resource_grants.c.action
                    ).where(schema.resource_grants.c.resource_id == resource_id)
                )
            ).all()
            assert {(user, action) for user, action in grants} == {
                (ids["manager"], action)
                for action in ("read", "query", "upload", "delete", "manage")
            }
        other = await api["client"].get(
            f"/api/v1/resources/{resource_id}",
            headers=api["tokens"].headers(ids["alice"], ids["org_a"]),
        )
        assert_safe_error(other, 404, "resource_not_found")
        evidence = await api["client"].get(
            f"/api/v1/documents/{resource_id}/evidence", headers=headers
        )
        assert_safe_error(evidence, 404, "resource_not_found")

    async def test_group_and_row_entitlement_revocation_take_effect_on_next_request(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["alice"], ids["org_a"])
        path = f"/api/v1/documents/{ids['group_document']}/evidence"
        assert (await api["client"].get(path, headers=headers)).status_code == 200
        async with api["owner"].begin() as connection:
            await connection.execute(
                schema.group_memberships.delete().where(
                    schema.group_memberships.c.org_id == ids["org_a"]
                )
            )
            await connection.execute(
                schema.row_entitlements.delete().where(
                    schema.row_entitlements.c.org_id == ids["org_a"]
                )
            )
        assert_safe_error(await api["client"].get(path, headers=headers), 404, "resource_not_found")
        rows = await api["client"].get(f"/api/v1/datasets/{ids['dataset_a']}/rows", headers=headers)
        assert rows.status_code == 200, rows.text
        assert rows.json() == []

    async def test_revoked_membership_overrides_still_valid_signed_token(self, security_api):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["alice"], ids["org_a"])
        assert (await api["client"].get("/api/v1/me", headers=headers)).status_code == 200
        async with api["owner"].begin() as connection:
            await connection.execute(
                schema.org_memberships.update()
                .where(schema.org_memberships.c.org_id == ids["org_a"])
                .where(schema.org_memberships.c.user_id == ids["alice"])
                .values(status="suspended")
            )
        response = await api["client"].get("/api/v1/me", headers=headers)
        assert_safe_error(response, 404, "organization_not_found")

    async def test_revocation_during_response_building_blocks_evidence_release(
        self, security_api, monkeypatch
    ):
        api = security_api
        ids = api["ids"]
        original_audit = security_routes.audit

        async def revoke_after_real_audit(
            session, context, action, resource_id=None, outcome="allowed"
        ):
            await original_audit(session, context, action, resource_id, outcome)
            if action == "document.evidence":
                # Deterministic interleaving after real authorization/data reads and before
                # the function-scoped session dependency permits the HTTP response.
                async with api["owner"].begin() as connection:
                    await connection.execute(
                        schema.resource_grants.delete()
                        .where(schema.resource_grants.c.org_id == ids["org_a"])
                        .where(schema.resource_grants.c.resource_id == ids["document_a"])
                        .where(schema.resource_grants.c.user_id == ids["alice"])
                    )

        monkeypatch.setattr(security_routes, "audit", revoke_after_real_audit)
        response = await api["client"].get(
            f"/api/v1/documents/{ids['document_a']}/evidence",
            headers=api["tokens"].headers(ids["alice"], ids["org_a"]),
        )
        assert_safe_error(response, 409, "authorization_changed")
        assert "synthetic sales report" not in response.text

    async def test_explicit_grant_and_revoke_api_changes_effective_access(self, security_api):
        api = security_api
        ids = api["ids"]
        manager = api["tokens"].headers(ids["manager"], ids["org_a"])
        alice = api["tokens"].headers(ids["alice"], ids["org_a"])
        created = await api["client"].post(
            f"/api/v1/workspaces/{ids['workspace_a']}/resources",
            headers=manager,
            json={"kind": "document", "title": "Synthetic ready-to-share resource"},
        )
        assert created.status_code == 201, created.text
        resource_id = UUID(created.json()["id"])
        # Owner-only fixture publication substitutes no production ingestion workflow.
        async with api["owner"].begin() as connection:
            await connection.execute(
                schema.resources.update()
                .where(schema.resources.c.id == resource_id)
                .values(state="active")
            )
        path = f"/api/v1/resources/{resource_id}"
        assert_safe_error(await api["client"].get(path, headers=alice), 404, "resource_not_found")
        granted = await api["client"].post(
            path + "/grants",
            headers=manager,
            json={"user_id": str(ids["alice"]), "action": "read"},
        )
        assert granted.status_code == 201, granted.text
        assert (await api["client"].get(path, headers=alice)).status_code == 200
        revoked = await api["client"].delete(
            path + "/grants/" + granted.json()["id"], headers=manager
        )
        assert revoked.status_code == 200, revoked.text
        assert_safe_error(await api["client"].get(path, headers=alice), 404, "resource_not_found")

    async def test_delete_tombstone_and_cleanup_intent_are_atomic_and_job_is_private(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["manager"], ids["org_a"])
        created = await api["client"].post(
            f"/api/v1/workspaces/{ids['workspace_a']}/resources",
            headers=headers,
            json={"kind": "document", "title": "Synthetic deletion request"},
        )
        assert created.status_code == 201, created.text
        resource_id = UUID(created.json()["id"])
        deleted = await api["client"].delete(f"/api/v1/resources/{resource_id}", headers=headers)
        assert deleted.status_code == 202, deleted.text
        assert deleted.json()["state"] == "access_blocked"
        assert deleted.json()["purge"] == "pending"
        job_id = UUID(deleted.json()["id"])
        async with api["owner"].begin() as connection:
            resource = (
                await connection.execute(
                    sa.select(schema.resources.c.state, schema.resources.c.deleted_at).where(
                        schema.resources.c.id == resource_id
                    )
                )
            ).one()
            assert resource[0] == "deleted"
            assert resource[1] is not None
            job = (
                (
                    await connection.execute(
                        sa.select(schema.security_jobs).where(schema.security_jobs.c.id == job_id)
                    )
                )
                .mappings()
                .one()
            )
            revision = await connection.scalar(
                sa.select(schema.orgs.c.policy_revision).where(schema.orgs.c.id == ids["org_a"])
            )
            assert job["resource_id"] == resource_id
            assert job["requested_by"] == ids["manager"]
            assert job["state"] == "queued"
            assert job["policy_revision"] == revision
        status = await api["client"].get(f"/api/v1/jobs/{job_id}", headers=headers)
        assert status.status_code == 200, status.text
        unauthorized = await api["client"].get(
            f"/api/v1/jobs/{job_id}",
            headers=api["tokens"].headers(ids["alice"], ids["org_a"]),
        )
        assert_safe_error(unauthorized, 404, "resource_not_found")

    async def test_fresh_mfa_is_required_independently_of_new_token_issuance(self, security_api):
        api = security_api
        ids = api["ids"]
        path = f"/api/v1/documents/{ids['mfa_a']}/evidence"
        for claims in ({}, {"amr": ["mfa"]}, {"amr": ["mfa"], "auth_time": int(time()) - 3600}):
            denied = await api["client"].get(
                path, headers=api["tokens"].headers(ids["alice"], ids["org_a"], **claims)
            )
            assert_safe_error(denied, 404, "resource_not_found")
        allowed = await api["client"].get(
            path,
            headers=api["tokens"].headers(
                ids["alice"], ids["org_a"], amr=["mfa"], auth_time=int(time())
            ),
        )
        assert allowed.status_code == 200, allowed.text

    async def test_upload_without_clean_scanner_or_with_oversized_body_never_publishes(
        self, security_api
    ):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["manager"], ids["org_a"])
        created = await api["client"].post(
            f"/api/v1/workspaces/{ids['workspace_a']}/resources",
            headers=headers,
            json={"kind": "document", "title": "Quarantine only"},
        )
        assert created.status_code == 201, created.text
        resource_id = UUID(created.json()["id"])
        upload_headers = {**headers, "X-Filename": "report.txt", "Content-Type": "text/plain"}
        path = f"/api/v1/resources/{resource_id}/validate-upload"
        no_scanner = await api["client"].post(
            path, headers=upload_headers, content=b"Synthetic text"
        )
        assert_safe_error(no_scanner, 503, "scanner_unavailable")
        too_large = await api["client"].post(path, headers=upload_headers, content=b"x" * 65)
        assert_safe_error(too_large, 413, "upload_too_large")

        async def chunked_body():
            yield b"x" * 40
            yield b"x" * 40

        chunked = await api["client"].post(path, headers=upload_headers, content=chunked_body())
        assert_safe_error(chunked, 422, "file_size_limit")
        async with api["owner"].begin() as connection:
            row = (
                await connection.execute(
                    sa.select(schema.resources.c.state, schema.resources.c.object_key).where(
                        schema.resources.c.id == resource_id
                    )
                )
            ).one()
            assert row == ("quarantine", None)

    async def test_metadata_omits_storage_keys_and_denies_kind_confusion(self, security_api):
        api = security_api
        ids = api["ids"]
        headers = api["tokens"].headers(ids["alice"], ids["org_a"])
        response = await api["client"].get(
            f"/api/v1/resources/{ids['document_a']}", headers=headers
        )
        assert response.status_code == 200, response.text
        assert set(response.json()) == {
            "id",
            "workspace_id",
            "kind",
            "title",
            "classification",
            "state",
        }
        for path in (
            f"/api/v1/datasets/{ids['document_a']}/rows",
            f"/api/v1/documents/{ids['dataset_a']}/evidence",
            f"/api/v1/resources/{uuid4()}",
        ):
            assert_safe_error(
                await api["client"].get(path, headers=headers), 404, "resource_not_found"
            )


@pytest.mark.integration
class TestSecurityWorkerIntegration:
    @staticmethod
    def settings() -> Settings:
        return Settings(
            _env_file=None,
            environment="test",
            database_url=SecretStr(service_url("DATABASE")),
            redis_url=SecretStr(service_url("REDIS")),
            signed_job_key=SecretStr(WORKER_TEST_KEY.decode()),
            pool_size=1,
            pool_max_overflow=0,
            dependency_timeout_seconds=10,
        )

    @staticmethod
    async def seed_job(security_db, *, held=False, stored=False):
        ids = security_db["ids"]
        resource_id, job_id = uuid4(), uuid4()
        now = datetime.now(UTC)
        async with security_db["owner"].begin() as connection:
            await connection.execute(
                schema.resources.insert().values(
                    org_id=ids["org_a"],
                    id=resource_id,
                    workspace_id=ids["workspace_a"],
                    kind="document",
                    title="Synthetic expired deletion candidate",
                    state="deleted",
                    created_by=ids["manager"],
                    deleted_at=now - timedelta(days=2),
                    retention_until=now - timedelta(days=1),
                    legal_hold=held,
                    object_key=(
                        object_key(ids["org_a"], ids["workspace_a"], resource_id, uuid4())
                        if stored
                        else None
                    ),
                )
            )
            await connection.execute(
                schema.resource_grants.insert().values(
                    org_id=ids["org_a"],
                    id=uuid4(),
                    resource_id=resource_id,
                    user_id=ids["manager"],
                    action="delete",
                )
            )
            await connection.execute(
                schema.document_chunks.insert().values(
                    org_id=ids["org_a"],
                    resource_id=resource_id,
                    id=uuid4(),
                    text="Synthetic data pending retention-safe deletion",
                    embedding=[1.0, 0.0, 0.0],
                )
            )
            revision = await connection.scalar(
                sa.select(schema.orgs.c.policy_revision).where(schema.orgs.c.id == ids["org_a"])
            )
            await connection.execute(
                schema.security_jobs.insert().values(
                    org_id=ids["org_a"],
                    id=job_id,
                    resource_id=resource_id,
                    requested_by=ids["manager"],
                    action="delete",
                    policy_revision=revision,
                )
            )
        signer = SignedJobEnvelope(WORKER_TEST_KEY)
        token = signer.issue(ids["org_a"], ids["manager"], job_id, resource_id, revision)
        return resource_id, job_id, revision, token

    async def test_signed_expired_db_only_deletion_completes_and_retry_is_idempotent(
        self, security_db
    ):
        resource_id, job_id, _, token = await self.seed_job(security_db)
        settings = self.settings()
        assert await run_security_job(token, settings) == {"state": "completed"}
        # Redelivery of the same signed token observes its terminal DB result safely.
        assert await run_security_job(token, settings) == {"state": "completed"}
        async with security_db["owner"].begin() as connection:
            assert (
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(schema.document_chunks)
                    .where(schema.document_chunks.c.resource_id == resource_id)
                )
                == 0
            )
            assert (
                await connection.scalar(
                    sa.select(schema.security_jobs.c.state).where(
                        schema.security_jobs.c.id == job_id
                    )
                )
                == "completed"
            )
            # Tombstone remains; completing DB deletion is not removal of audit history.
            assert (
                await connection.scalar(
                    sa.select(schema.resources.c.state).where(schema.resources.c.id == resource_id)
                )
                == "deleted"
            )

    async def test_signed_wrong_org_resource_or_stale_revision_cannot_authorize_job(
        self, security_db
    ):
        ids = security_db["ids"]
        resource_id, job_id, revision, _ = await self.seed_job(security_db)
        signer = SignedJobEnvelope(WORKER_TEST_KEY)
        settings = self.settings()
        tokens = [
            signer.issue(ids["org_b"], ids["manager"], job_id, resource_id, revision),
            signer.issue(ids["org_a"], ids["manager"], job_id, ids["private_a"], revision),
            signer.issue(ids["org_a"], ids["manager"], job_id, resource_id, revision - 1),
        ]
        for token in tokens:
            assert await run_security_job(token, settings) == {"state": "denied"}
        async with security_db["owner"].begin() as connection:
            assert (
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(schema.document_chunks)
                    .where(schema.document_chunks.c.resource_id == resource_id)
                )
                == 1
            )
            assert (
                await connection.scalar(
                    sa.select(schema.security_jobs.c.state).where(
                        schema.security_jobs.c.id == job_id
                    )
                )
                == "queued"
            )

    async def test_signed_job_honors_legal_hold_and_preserves_content(self, security_db):
        resource_id, job_id, _, token = await self.seed_job(security_db, held=True)
        assert await run_security_job(token, self.settings()) == {"state": "held"}
        async with security_db["owner"].begin() as connection:
            assert (
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(schema.document_chunks)
                    .where(schema.document_chunks.c.resource_id == resource_id)
                )
                == 1
            )
            assert (
                await connection.scalar(
                    sa.select(schema.security_jobs.c.state).where(
                        schema.security_jobs.c.id == job_id
                    )
                )
                == "held"
            )

    async def test_signed_job_with_blob_stays_pending_and_replay_cannot_repeat_work(
        self, security_db
    ):
        resource_id, job_id, _, token = await self.seed_job(security_db, stored=True)
        settings = self.settings()
        assert await run_security_job(token, settings) == {"state": "pending_storage"}
        with pytest.raises(JobEnvelopeRejected):
            await run_security_job(token, settings)
        async with security_db["owner"].begin() as connection:
            assert (
                await connection.scalar(
                    sa.select(sa.func.count())
                    .select_from(schema.document_chunks)
                    .where(schema.document_chunks.c.resource_id == resource_id)
                )
                == 1
            )
            assert (
                await connection.scalar(
                    sa.select(schema.security_jobs.c.state).where(
                        schema.security_jobs.c.id == job_id
                    )
                )
                == "queued"
            )
