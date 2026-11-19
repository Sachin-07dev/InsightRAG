"""Real PostgreSQL RLS tests. Never substitute SQLite or owner connections for runtime reads."""

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import sqlalchemy as sa
from fastapi import Request
from insightrag.core.config import Settings
from insightrag.db.session import Database
from insightrag.ingestion.service import process_job
from insightrag.main import create_app
from insightrag.security import schema
from insightrag.security.context import AccessContext
from insightrag.security.controls import JobClaims, object_key
from insightrag.security.dependencies import get_access_context
from pydantic import SecretStr
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration


def service_url(name: str) -> str:
    filename = os.getenv(f"INSIGHTRAG_TEST_{name}_URL_FILE")
    value = os.getenv(f"INSIGHTRAG_TEST_{name}_URL")
    if filename:
        value = Path(filename).read_text(encoding="utf-8").strip()
    if not value:
        if os.getenv("CI"):
            pytest.fail(f"CI requires real {name} security-test configuration")
        pytest.skip(f"Real {name} security-test configuration not supplied")
    return value


async def context(
    connection: AsyncConnection,
    user,
    org,
    *,
    mfa=False,
    purpose="administration",
    analytics_resource=None,
):
    await connection.execute(
        sa.text("""SELECT set_config('app.user_id', :user, true),
            set_config('app.organization_id', :org, true),
            set_config('app.mfa', :mfa, true), set_config('app.purpose', :purpose, true)"""),
        {"user": str(user), "org": str(org), "mfa": str(mfa).lower(), "purpose": purpose},
    )
    if analytics_resource is not None:
        await connection.execute(
            sa.text("SELECT set_config('app.analytics_resource_id', :resource, true)"),
            {"resource": str(analytics_resource)},
        )


@pytest.fixture
async def security_db() -> AsyncIterator[dict]:
    owner = create_async_engine(service_url("MIGRATION_DATABASE"), hide_parameters=True)
    runtime = create_async_engine(
        service_url("DATABASE"), hide_parameters=True, pool_size=1, max_overflow=0
    )
    ids = {
        name: uuid4()
        for name in (
            "org_a",
            "org_b",
            "alice",
            "bob",
            "manager",
            "workspace_a",
            "workspace_b",
            "group_a",
            "document_a",
            "document_b",
            "private_a",
            "secret_a",
            "mfa_a",
            "purpose_a",
            "group_document",
            "dataset_a",
            "dataset_b",
        )
    }
    try:
        async with owner.begin() as connection:
            revision = await connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            assert revision == "0008_analytics_scope", "Apply analytics migration before tests"
            await connection.execute(
                schema.security_users.insert(),
                [
                    {
                        "id": ids["alice"],
                        "issuer": "https://synthetic.invalid",
                        "subject": str(ids["alice"]),
                        "clearance": 1,
                    },
                    {
                        "id": ids["bob"],
                        "issuer": "https://synthetic.invalid",
                        "subject": str(ids["bob"]),
                        "clearance": 3,
                    },
                    {
                        "id": ids["manager"],
                        "issuer": "https://synthetic.invalid",
                        "subject": str(ids["manager"]),
                        "clearance": 3,
                    },
                ],
            )
            await connection.execute(
                schema.orgs.insert(),
                [
                    {"id": ids["org_a"], "name": "Synthetic A", "home_region": "synthetic-region"},
                    {"id": ids["org_b"], "name": "Synthetic B", "home_region": "synthetic-region"},
                ],
            )
            await connection.execute(
                schema.org_memberships.insert(),
                [
                    {"org_id": ids["org_a"], "user_id": ids["alice"], "role": "analyst"},
                    {"org_id": ids["org_a"], "user_id": ids["manager"], "role": "admin"},
                    {"org_id": ids["org_b"], "user_id": ids["bob"], "role": "analyst"},
                ],
            )
            await connection.execute(
                schema.workspaces.insert(),
                [
                    {"org_id": ids["org_a"], "id": ids["workspace_a"], "name": "A workspace"},
                    {"org_id": ids["org_b"], "id": ids["workspace_b"], "name": "B workspace"},
                ],
            )
            await connection.execute(
                schema.workspace_memberships.insert(),
                [
                    {
                        "org_id": ids["org_a"],
                        "workspace_id": ids["workspace_a"],
                        "user_id": ids["alice"],
                        "role": "analyst",
                    },
                    {
                        "org_id": ids["org_a"],
                        "workspace_id": ids["workspace_a"],
                        "user_id": ids["manager"],
                        "role": "manager",
                    },
                    {
                        "org_id": ids["org_b"],
                        "workspace_id": ids["workspace_b"],
                        "user_id": ids["bob"],
                        "role": "analyst",
                    },
                ],
            )
            await connection.execute(
                schema.groups.insert(),
                {
                    "org_id": ids["org_a"],
                    "id": ids["group_a"],
                    "name": "A readers",
                },
            )
            await connection.execute(
                schema.group_memberships.insert(),
                {
                    "org_id": ids["org_a"],
                    "group_id": ids["group_a"],
                    "user_id": ids["alice"],
                },
            )
            resources = []
            for name in (
                "document_a",
                "private_a",
                "secret_a",
                "mfa_a",
                "purpose_a",
                "group_document",
                "dataset_a",
                "document_b",
                "dataset_b",
            ):
                other = name.endswith("_b")
                resources.append(
                    {
                        "org_id": ids["org_b" if other else "org_a"],
                        "id": ids[name],
                        "workspace_id": ids["workspace_b" if other else "workspace_a"],
                        "kind": "dataset" if name.startswith("dataset") else "document",
                        "title": name,
                        "state": "active",
                        "classification": 3 if name == "secret_a" else 0,
                        "require_mfa": name == "mfa_a",
                        "purpose": "knowledge" if name == "purpose_a" else None,
                        "created_by": ids["bob" if other else "manager"],
                    }
                )
            await connection.execute(schema.resources.insert(), resources)
            grants = []
            for resource_name, actor, action in (
                ("document_a", "alice", "read"),
                ("secret_a", "alice", "read"),
                ("secret_a", "manager", "read"),
                ("mfa_a", "alice", "read"),
                ("purpose_a", "alice", "read"),
                ("dataset_a", "alice", "query"),
                ("document_b", "bob", "read"),
                ("dataset_b", "bob", "query"),
            ):
                grants.append(
                    {
                        "org_id": ids["org_b" if actor == "bob" else "org_a"],
                        "id": uuid4(),
                        "resource_id": ids[resource_name],
                        "user_id": ids[actor],
                        "group_id": None,
                        "action": action,
                    }
                )
            grants.append(
                {
                    "org_id": ids["org_a"],
                    "id": uuid4(),
                    "resource_id": ids["group_document"],
                    "user_id": None,
                    "group_id": ids["group_a"],
                    "action": "read",
                }
            )
            await connection.execute(schema.resource_grants.insert(), grants)
            await connection.execute(
                schema.row_entitlements.insert(),
                [
                    {
                        "org_id": ids["org_a"],
                        "resource_id": ids["dataset_a"],
                        "user_id": ids["alice"],
                        "region": "Delhi",
                    },
                    {
                        "org_id": ids["org_b"],
                        "resource_id": ids["dataset_b"],
                        "user_id": ids["bob"],
                        "region": "Delhi",
                    },
                ],
            )
            await connection.execute(
                schema.dataset_rows.insert(),
                [
                    {
                        "org_id": ids["org_a"],
                        "resource_id": ids["dataset_a"],
                        "id": uuid4(),
                        "region": "Delhi",
                        "payload": {"net_sales": "100.10"},
                    },
                    {
                        "org_id": ids["org_a"],
                        "resource_id": ids["dataset_a"],
                        "id": uuid4(),
                        "region": "Mumbai",
                        "payload": {"net_sales": "200.20"},
                    },
                    {
                        "org_id": ids["org_b"],
                        "resource_id": ids["dataset_b"],
                        "id": uuid4(),
                        "region": "Delhi",
                        "payload": {"net_sales": "999.99"},
                    },
                ],
            )
            chunks = []
            for name in (
                "document_a",
                "document_b",
                "private_a",
                "secret_a",
                "mfa_a",
                "purpose_a",
                "group_document",
            ):
                chunks.append(
                    {
                        "org_id": ids["org_b" if name == "document_b" else "org_a"],
                        "resource_id": ids[name],
                        "id": uuid4(),
                        "text": f"{name} synthetic sales report",
                        "embedding": [1.0, 0.0, 0.0],
                    }
                )
            await connection.execute(schema.document_chunks.insert(), chunks)
        yield {"owner": owner, "runtime": runtime, "ids": ids}
    finally:
        async with owner.begin() as connection:
            for table_name in (
                "rag_turns",
                "rag_conversations",
                "ingestion_chunks",
                "ingestion_dataset_rows",
                "ingestion_jobs",
                "document_versions",
            ):
                await connection.execute(
                    sa.text(f"DELETE FROM {table_name} WHERE org_id IN (:a,:b)"),
                    {"a": ids["org_a"], "b": ids["org_b"]},
                )
            for table in (
                schema.security_jobs,
                schema.audit_events,
                schema.row_entitlements,
                schema.document_chunks,
                schema.dataset_rows,
                schema.resource_grants,
                schema.resources,
                schema.group_memberships,
                schema.workspace_memberships,
                schema.groups,
                schema.workspaces,
                schema.org_memberships,
            ):
                await connection.execute(
                    table.delete().where(table.c.org_id.in_([ids["org_a"], ids["org_b"]]))
                )
            await connection.execute(
                schema.orgs.delete().where(schema.orgs.c.id.in_([ids["org_a"], ids["org_b"]]))
            )
            await connection.execute(
                schema.security_users.delete().where(
                    schema.security_users.c.id.in_([ids["alice"], ids["bob"], ids["manager"]])
                )
            )
        await runtime.dispose()
        await owner.dispose()


async def can_read(connection, resource) -> bool:
    return bool(
        await connection.scalar(
            sa.text("SELECT insightrag_security.can_resource(:resource,'read')"),
            {"resource": resource},
        )
    )


async def policy_revision(connection, org) -> int:
    return await connection.scalar(
        sa.select(schema.orgs.c.policy_revision).where(schema.orgs.c.id == org)
    )


async def test_ingestion_atomic_publication_retry_and_tenant_isolation(security_db):
    ids = security_db["ids"]
    version_one, version_two, job_one, job_two = (uuid4() for _ in range(4))
    async with security_db["owner"].begin() as owner:
        await owner.execute(
            schema.resource_grants.insert(),
            {
                "org_id": ids["org_a"],
                "id": uuid4(),
                "resource_id": ids["document_a"],
                "user_id": ids["manager"],
                "action": "upload",
            },
        )
        await owner.execute(
            schema.resource_grants.insert(),
            {
                "org_id": ids["org_a"],
                "id": uuid4(),
                "resource_id": ids["document_a"],
                "user_id": ids["manager"],
                "action": "read",
            },
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        assert await connection.scalar(
            sa.text("SELECT insightrag_security.can_resource(:resource,'upload')"),
            {"resource": ids["document_a"]},
        )
        key_one = object_key(ids["org_a"], ids["workspace_a"], ids["document_a"], version_one)
        result = await connection.scalar(
            sa.text(
                "SELECT insightrag_security.reserve_ingestion("
                ":org,:resource,:version,:job,:hash,:key,"
                "'report.txt','text/plain')"
            ),
            {
                "org": ids["org_a"],
                "resource": ids["document_a"],
                "version": version_one,
                "job": job_one,
                "hash": "a" * 64,
                "key": key_one,
            },
        )
        assert result == "created"
        assert await connection.scalar(sa.text("SELECT count(*) FROM ingestion_chunks")) == 0

        duplicate_version = uuid4()
        duplicate_key = object_key(
            ids["org_a"], ids["workspace_a"], ids["document_a"], duplicate_version
        )
        duplicate = await connection.scalar(
            sa.text(
                "SELECT insightrag_security.reserve_ingestion("
                ":org,:resource,:version,:job,:hash,:key,"
                "'report.txt','text/plain')"
            ),
            {
                "org": ids["org_a"],
                "resource": ids["document_a"],
                "version": duplicate_version,
                "job": uuid4(),
                "hash": "a" * 64,
                "key": duplicate_key,
            },
        )
        assert duplicate == f"duplicate:{version_one}"
        forced_version = uuid4()
        forced_key = object_key(ids["org_a"], ids["workspace_a"], ids["document_a"], forced_version)
        assert (
            await connection.scalar(
                sa.text(
                    "SELECT insightrag_security.reserve_ingestion_force("
                    ":org,:resource,:version,:job,:hash,:key,'report.txt','text/plain')"
                ),
                {
                    "org": ids["org_a"],
                    "resource": ids["document_a"],
                    "version": forced_version,
                    "job": uuid4(),
                    "hash": "a" * 64,
                    "key": forced_key,
                },
            )
            == "created"
        )
        key_two = object_key(ids["org_a"], ids["workspace_a"], ids["document_a"], version_two)
        assert (
            await connection.scalar(
                sa.text(
                    "SELECT insightrag_security.reserve_ingestion("
                    ":org,:resource,:version,:job,:hash,:key,"
                    "'report.txt','text/plain')"
                ),
                {
                    "org": ids["org_a"],
                    "resource": ids["document_a"],
                    "version": version_two,
                    "job": job_two,
                    "hash": "b" * 64,
                    "key": key_two,
                },
            )
            == "created"
        )
        await connection.execute(
            sa.text(
                "UPDATE ingestion_jobs SET state='running' WHERE org_id=:org AND id IN (:one,:two)"
            ),
            {"org": ids["org_a"], "one": job_one, "two": job_two},
        )
        await connection.execute(
            sa.text(
                "INSERT INTO ingestion_chunks(org_id,resource_id,version_id,position,text,locator,"
                "token_count,embedding) VALUES(:org,:resource,:version,0,'verified','line:1',1,"
                "CAST(:vector AS vector))"
            ),
            {
                "org": ids["org_a"],
                "resource": ids["document_a"],
                "version": version_two,
                "vector": str([1.0] + [0.0] * 1535),
            },
        )
        assert (
            await connection.scalar(
                sa.text("SELECT insightrag_security.publish_ingestion(:org,:job,'synthetic-1536')"),
                {"org": ids["org_a"], "job": job_one},
            )
            == "stale"
        )
        assert (
            await connection.scalar(
                sa.text("SELECT insightrag_security.publish_ingestion(:org,:job,'synthetic-1536')"),
                {"org": ids["org_a"], "job": job_two},
            )
            == "published"
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"], purpose="knowledge")
        assert await connection.scalar(sa.text("SELECT count(*) FROM ingestion_chunks")) == 1
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["bob"], ids["org_b"], purpose="knowledge")
        assert await connection.scalar(sa.text("SELECT count(*) FROM ingestion_chunks")) == 0


async def test_ingestion_deletion_waits_for_versioned_storage(security_db):
    ids = security_db["ids"]
    version, job = uuid4(), uuid4()
    key = object_key(ids["org_a"], ids["workspace_a"], ids["document_a"], version)
    async with security_db["owner"].begin() as owner:
        await owner.execute(
            schema.resource_grants.insert(),
            {
                "org_id": ids["org_a"],
                "id": uuid4(),
                "resource_id": ids["document_a"],
                "user_id": ids["manager"],
                "action": "delete",
            },
        )
        await owner.execute(
            sa.text(
                "INSERT INTO document_versions(org_id,resource_id,id,version_number,sha256,"
                "object_key,filename,media_type,created_by) VALUES(:org,:resource,:version,1,:hash,"
                ":key,'report.txt','text/plain',:actor)"
            ),
            {
                "org": ids["org_a"],
                "resource": ids["document_a"],
                "version": version,
                "hash": "a" * 64,
                "key": key,
                "actor": ids["manager"],
            },
        )
        await owner.execute(
            sa.text(
                "UPDATE resources SET state='deleted',deleted_at=now(),"
                "retention_until=now()-interval '1 day' "
                "WHERE org_id=:org AND id=:resource"
            ),
            {"org": ids["org_a"], "resource": ids["document_a"]},
        )
        revision = await owner.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )
        await owner.execute(
            schema.security_jobs.insert(),
            {
                "org_id": ids["org_a"],
                "id": job,
                "resource_id": ids["document_a"],
                "requested_by": ids["manager"],
                "action": "delete",
                "state": "queued",
                "policy_revision": revision,
            },
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"], purpose="deletion")
        assert (
            await connection.scalar(
                sa.text("SELECT insightrag_security.purge_deleted_resource(:job)"), {"job": job}
            )
            == "pending_storage"
        )
        assert await connection.scalar(
            sa.text("SELECT insightrag_security.ingestion_deletion_keys(:job)"), {"job": job}
        ) == [key]
        # In production this call follows a confirmed object-store delete.
        assert (
            await connection.scalar(
                sa.text("SELECT insightrag_security.finish_ingestion_deletion(:job)"), {"job": job}
            )
            == "completed"
        )
        assert (
            await connection.scalar(
                sa.text(
                    "SELECT count(*) FROM document_versions "
                    "WHERE org_id=:org AND resource_id=:resource"
                ),
                {"org": ids["org_a"], "resource": ids["document_a"]},
            )
            == 0
        )


async def test_ingestion_worker_publishes_synthetic_text_with_fake_dependencies(security_db):
    ids = security_db["ids"]
    version, job = uuid4(), uuid4()
    body = b"Delhi quarterly revenue decreased."
    import hashlib

    digest = hashlib.sha256(body).hexdigest()
    key = object_key(ids["org_a"], ids["workspace_a"], ids["document_a"], version)
    async with security_db["owner"].begin() as owner:
        for action in ("upload", "read"):
            await owner.execute(
                schema.resource_grants.insert(),
                {
                    "org_id": ids["org_a"],
                    "id": uuid4(),
                    "resource_id": ids["document_a"],
                    "user_id": ids["manager"],
                    "action": action,
                },
            )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        assert (
            await connection.scalar(
                sa.text(
                    "SELECT insightrag_security.reserve_ingestion("
                    ":org,:resource,:version,:job,:hash,:key,'report.txt','text/plain')"
                ),
                {
                    "org": ids["org_a"],
                    "resource": ids["document_a"],
                    "version": version,
                    "job": job,
                    "hash": digest,
                    "key": key,
                },
            )
            == "created"
        )
    async with security_db["owner"].connect() as owner:
        revision = await owner.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )

    class FakeStore:
        async def get(self, requested_key, maximum):
            assert requested_key == key and maximum >= len(body)
            return body

    class FakeEmbedder:
        model_id = "synthetic-1536"
        dimensions = 1536

        async def embed(self, texts):
            assert texts and "Delhi" in texts[0]
            return [[1.0] + [0.0] * 1535 for _ in texts]

    database = Database(
        Settings(
            _env_file=None, database_url=SecretStr(service_url("DATABASE")), database_url_file=None
        )
    )
    claims = JobClaims(
        ids["org_a"], ids["manager"], job, ids["document_a"], revision, 1, 2, uuid4()
    )
    try:
        assert await process_job(database, claims, FakeStore(), FakeEmbedder()) == "published"
        assert await process_job(database, claims, FakeStore(), FakeEmbedder()) == "denied"
    finally:
        await database.close()
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"], purpose="knowledge")
        assert (
            await connection.scalar(
                sa.text("SELECT count(*) FROM ingestion_chunks WHERE version_id=:version"),
                {"version": version},
            )
            == 1
        )


async def test_ingestion_http_upload_commits_before_dispatch(security_db, monkeypatch):
    ids = security_db["ids"]
    async with security_db["owner"].begin() as owner:
        await owner.execute(
            schema.resource_grants.insert(),
            {
                "org_id": ids["org_a"],
                "id": uuid4(),
                "resource_id": ids["document_a"],
                "user_id": ids["manager"],
                "action": "upload",
            },
        )
        revision = await owner.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )

    class FakeStore:
        def __init__(self):
            self.keys = []

        async def put(self, key, data, media_type):
            assert data == b"Delhi sales report"
            self.keys.append(key)

        async def delete(self, key):
            self.keys.remove(key)

    class CleanScanner:
        async def scan(self, data):
            return "clean"

    store = FakeStore()
    monkeypatch.setattr("insightrag.ingestion.routes.configured_store", lambda settings: store)
    dispatched = []

    async def fake_dispatch(settings, token):
        # Background task must see a committed job through an independent connection.
        async with security_db["owner"].connect() as owner:
            count = await owner.scalar(
                sa.text("SELECT count(*) FROM ingestion_jobs WHERE org_id=:org"),
                {"org": ids["org_a"]},
            )
            assert count == 1
        dispatched.append(token)

    monkeypatch.setattr("insightrag.ingestion.routes._dispatch", fake_dispatch)
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=SecretStr(service_url("DATABASE")),
        database_url_file=None,
        redis_url=SecretStr(service_url("REDIS")),
        redis_url_file=None,
        signed_job_key=SecretStr("synthetic-signing-key-32-bytes-minimum"),
    )
    app = create_app(settings)

    async def context_override(request: Request):
        return AccessContext(
            ids["manager"], ids["org_a"], "admin", 3, False, revision, request.state.request_id
        )

    app.dependency_overrides[get_access_context] = context_override
    async with app.router.lifespan_context(app):
        app.state.scanner = CleanScanner()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/resources/{ids['document_a']}/versions",
                headers={
                    "X-Organization-ID": str(ids["org_a"]),
                    "X-Filename": "report.txt",
                    "Content-Type": "text/plain",
                },
                content=b"Delhi sales report",
            )
    assert response.status_code == 202, response.text
    assert response.json()["state"] == "queued"
    assert len(store.keys) == 1 and len(dispatched) == 1


async def test_rls_database_role_and_function_privileges(security_db):
    async with security_db["runtime"].begin() as connection:
        assert not await connection.scalar(
            sa.text(
                "SELECT rolsuper OR rolbypassrls OR rolcreaterole "
                "FROM pg_roles WHERE rolname=current_user"
            )
        )
        assert not await connection.scalar(
            sa.text("SELECT pg_has_role(current_user,'insightrag_policy_reader','MEMBER')")
        )
        protected = await connection.execute(
            sa.text(
                "SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class "
                "WHERE relnamespace='public'::regnamespace AND relname::text = ANY(:names)"
            ),
            {"names": list(schema.metadata.tables)},
        )
        assert len(protected_rows := protected.all()) == len(schema.metadata.tables)
        assert all(enabled and forced for _, enabled, forced in protected_rows)
        assert not await connection.scalar(
            sa.text(
                "SELECT EXISTS (SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a "
                "WHERE n.nspname='insightrag_security' "
                "AND a.grantee=0 AND a.privilege_type='EXECUTE')"
            )
        )


async def test_rls_missing_and_wrong_tenant_context_returns_no_content(security_db):
    ids = security_db["ids"]
    async with security_db["runtime"].begin() as connection:
        assert (
            await connection.scalar(sa.select(sa.func.count()).select_from(schema.document_chunks))
            == 0
        )
        await context(connection, ids["alice"], ids["org_b"])
        assert (
            await connection.scalar(sa.select(sa.func.count()).select_from(schema.resources)) == 0
        )
        assert (
            await connection.scalar(sa.select(sa.func.count()).select_from(schema.dataset_rows))
            == 0
        )
        await context(connection, ids["bob"], ids["org_a"])
        assert not await can_read(connection, ids["document_a"])


async def test_rls_identity_resolution_is_exact_and_active_only(security_db):
    ids = security_db["ids"]
    statement = sa.text(
        "SELECT id,clearance FROM insightrag_security.security_identity(:issuer,:subject)"
    )
    async with security_db["runtime"].begin() as connection:
        resolved = await connection.execute(
            statement, {"issuer": "https://synthetic.invalid", "subject": str(ids["alice"])}
        )
        assert resolved.one() == (ids["alice"], 1)
        unknown = await connection.execute(
            statement, {"issuer": "https://other-issuer.invalid", "subject": str(ids["alice"])}
        )
        assert unknown.first() is None
        assert (
            await connection.scalar(sa.select(sa.func.count()).select_from(schema.security_users))
            == 0
        )
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.security_users.update()
            .where(schema.security_users.c.id == ids["alice"])
            .values(active=False)
        )
    async with security_db["runtime"].begin() as connection:
        disabled = await connection.execute(
            statement, {"issuer": "https://synthetic.invalid", "subject": str(ids["alice"])}
        )
        assert disabled.first() is None


async def test_rls_vector_and_keyword_candidates_obey_document_grants(security_db):
    ids = security_db["ids"]
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        expected = {ids["document_a"], ids["group_document"]}
        vectors = await connection.execute(
            sa.text(
                "SELECT resource_id FROM document_chunks "
                "ORDER BY embedding <-> CAST(:query AS vector) LIMIT 50"
            ),
            {"query": "[1,0,0]"},
        )
        assert set(vectors.scalars()) == expected
        keywords = await connection.execute(
            sa.text(
                "SELECT resource_id FROM document_chunks WHERE "
                "to_tsvector('english',text) @@ plainto_tsquery('english','sales')"
            )
        )
        assert set(keywords.scalars()) == expected
        assert not await can_read(connection, ids["private_a"])
        await context(connection, ids["manager"], ids["org_a"])
        assert not await can_read(connection, ids["document_a"]), (
            "Admin is not an automatic content grant"
        )


async def test_rls_clearance_mfa_and_purpose_are_independent_gates(security_db):
    ids = security_db["ids"]
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"], purpose="analytics")
        assert not await can_read(connection, ids["secret_a"])
        assert not await can_read(connection, ids["mfa_a"])
        assert not await can_read(connection, ids["purpose_a"])
        await context(connection, ids["alice"], ids["org_a"], mfa=True, purpose="knowledge")
        assert await can_read(connection, ids["mfa_a"])
        assert await can_read(connection, ids["purpose_a"])
        assert not await can_read(connection, ids["secret_a"])
        await context(connection, ids["manager"], ids["org_a"])
        assert await can_read(connection, ids["secret_a"])


async def test_rls_dataset_entitlements_filter_before_aggregation(security_db):
    ids = security_db["ids"]
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"], purpose="analytics")
        rows = await connection.execute(sa.select(schema.dataset_rows.c.region))
        assert rows.scalars().all() == ["Delhi"]
        total = await connection.scalar(
            sa.text("SELECT sum((payload->>'net_sales')::numeric) FROM dataset_rows")
        )
        assert total == Decimal("100.10")


async def test_rls_pool_context_clears_on_commit_and_rollback(security_db):
    ids = security_db["ids"]
    engine: AsyncEngine = security_db["runtime"]
    async with engine.begin() as connection:
        pid = await connection.scalar(sa.text("SELECT pg_backend_pid()"))
        await context(connection, ids["alice"], ids["org_a"])
        assert await can_read(connection, ids["document_a"])
    async with engine.begin() as connection:
        assert await connection.scalar(sa.text("SELECT pg_backend_pid()")) == pid
        assert await connection.scalar(
            sa.text("SELECT NULLIF(current_setting('app.user_id',true),'') IS NULL")
        )
        await context(connection, ids["bob"], ids["org_b"])
        assert await can_read(connection, ids["document_b"])
        await connection.rollback()
    async with engine.begin() as connection:
        assert await connection.scalar(sa.text("SELECT pg_backend_pid()")) == pid
        assert (
            await connection.scalar(sa.select(sa.func.count()).select_from(schema.document_chunks))
            == 0
        )


async def test_rls_revoked_group_and_membership_take_effect_without_cache(security_db):
    ids = security_db["ids"]
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.group_memberships.delete().where(
                schema.group_memberships.c.org_id == ids["org_a"]
            )
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        assert not await can_read(connection, ids["group_document"])
        assert await can_read(connection, ids["document_a"])
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.org_memberships.update()
            .where(schema.org_memberships.c.org_id == ids["org_a"])
            .where(schema.org_memberships.c.user_id == ids["alice"])
            .values(status="suspended")
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        assert not await can_read(connection, ids["document_a"])
        assert (
            await connection.scalar(sa.select(sa.func.count()).select_from(schema.dataset_rows))
            == 0
        )


async def test_rls_new_resource_grants_only_bootstrap_in_the_creation_transaction(security_db):
    ids = security_db["ids"]
    new = uuid4()
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        await connection.execute(
            schema.resources.insert().values(
                org_id=ids["org_a"],
                id=new,
                workspace_id=ids["workspace_a"],
                kind="document",
                title="Fresh private source",
            )
        )
        await connection.execute(
            schema.resource_grants.insert().values(
                org_id=ids["org_a"],
                id=uuid4(),
                resource_id=new,
                user_id=ids["manager"],
                action="upload",
            )
        )
        assert (
            await connection.scalar(
                sa.select(schema.resources.c.id).where(schema.resources.c.id == new)
            )
            == new
        )
    with pytest.raises(DBAPIError):
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["manager"], ids["org_a"])
            await connection.execute(
                schema.resource_grants.insert().values(
                    org_id=ids["org_a"],
                    id=uuid4(),
                    resource_id=new,
                    user_id=ids["manager"],
                    action="read",
                )
            )
    with pytest.raises(DBAPIError):
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["manager"], ids["org_a"])
            await connection.execute(
                schema.resource_grants.insert().values(
                    org_id=ids["org_a"],
                    id=uuid4(),
                    resource_id=ids["private_a"],
                    user_id=ids["manager"],
                    action="manage",
                )
            )


async def test_rls_runtime_cannot_escalate_or_tamper_with_audit(security_db):
    ids = security_db["ids"]
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        await connection.execute(
            schema.audit_events.insert().values(
                org_id=ids["org_a"],
                id=uuid4(),
                actor_id=ids["alice"],
                action="synthetic.read",
                outcome="allowed",
                request_id="synthetic-test",
            )
        )
    statements = [
        "UPDATE org_memberships SET role='owner' WHERE user_id=:user",
        "UPDATE resources SET classification=0 WHERE id=:resource",
        "DELETE FROM audit_events WHERE org_id=:org",
        "UPDATE audit_events SET outcome='allowed' WHERE org_id=:org",
        "INSERT INTO group_memberships(org_id,group_id,user_id) VALUES (:org,:group,:user)",
    ]
    for statement in statements:
        with pytest.raises(DBAPIError):
            async with security_db["runtime"].begin() as connection:
                await context(connection, ids["alice"], ids["org_a"])
                await connection.execute(
                    sa.text(statement),
                    {
                        "user": ids["alice"],
                        "resource": ids["secret_a"],
                        "org": ids["org_a"],
                        "group": ids["group_a"],
                    },
                )


async def test_rls_runtime_cannot_publish_quarantined_resources(security_db):
    ids = security_db["ids"]
    resource_id = uuid4()
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        await connection.execute(
            schema.resources.insert().values(
                org_id=ids["org_a"],
                id=resource_id,
                workspace_id=ids["workspace_a"],
                kind="document",
                title="Not scanned or published",
            )
        )
        await connection.execute(
            schema.resource_grants.insert().values(
                org_id=ids["org_a"],
                id=uuid4(),
                resource_id=resource_id,
                user_id=ids["manager"],
                action="manage",
            )
        )
    with pytest.raises(DBAPIError):
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["manager"], ids["org_a"])
            await connection.execute(
                schema.resources.update()
                .where(schema.resources.c.id == resource_id)
                .values(state="active")
            )


async def test_rls_jobs_require_current_grant_and_cannot_reset_terminal_state(security_db):
    ids = security_db["ids"]
    job_id = uuid4()
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        await connection.execute(
            schema.security_jobs.insert().values(
                org_id=ids["org_a"],
                id=job_id,
                resource_id=ids["document_a"],
                requested_by=ids["alice"],
                action="read",
                policy_revision=await policy_revision(connection, ids["org_a"]),
            )
        )
        await connection.execute(
            schema.security_jobs.update()
            .where(schema.security_jobs.c.id == job_id)
            .values(state="completed")
        )
    with pytest.raises(DBAPIError):
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["alice"], ids["org_a"])
            await connection.execute(
                schema.security_jobs.update()
                .where(schema.security_jobs.c.id == job_id)
                .values(state="queued")
            )
    with pytest.raises(DBAPIError):
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["alice"], ids["org_a"])
            await connection.execute(
                schema.security_jobs.insert().values(
                    org_id=ids["org_a"],
                    id=uuid4(),
                    resource_id=ids["private_a"],
                    requested_by=ids["alice"],
                    action="read",
                    policy_revision=await policy_revision(connection, ids["org_a"]),
                )
            )
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.resources.update()
            .where(schema.resources.c.org_id == ids["org_a"])
            .where(schema.resources.c.id == ids["document_a"])
            .values(state="deleted", deleted_at=sa.func.now())
        )
    with pytest.raises(DBAPIError):
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["alice"], ids["org_a"])
            await connection.execute(
                schema.security_jobs.insert().values(
                    org_id=ids["org_a"],
                    id=uuid4(),
                    resource_id=ids["document_a"],
                    requested_by=ids["alice"],
                    action="read",
                    policy_revision=await policy_revision(connection, ids["org_a"]),
                )
            )


async def test_rls_composite_foreign_key_rejects_cross_tenant_workspace(security_db):
    ids = security_db["ids"]
    with pytest.raises(DBAPIError):
        async with security_db["owner"].begin() as connection:
            await connection.execute(
                schema.resources.insert().values(
                    org_id=ids["org_a"],
                    id=uuid4(),
                    workspace_id=ids["workspace_b"],
                    kind="document",
                    title="Invalid cross-tenant fixture",
                    created_by=ids["manager"],
                )
            )


async def test_rls_owner_policy_mutations_invalidate_revision(security_db):
    ids = security_db["ids"]
    async with security_db["owner"].begin() as connection:
        before = await policy_revision(connection, ids["org_a"])
        await connection.execute(
            schema.resource_grants.delete()
            .where(schema.resource_grants.c.org_id == ids["org_a"])
            .where(schema.resource_grants.c.resource_id == ids["document_a"])
        )
        assert await policy_revision(connection, ids["org_a"]) > before
        before = await policy_revision(connection, ids["org_a"])
        await connection.execute(
            schema.security_users.update()
            .where(schema.security_users.c.id == ids["alice"])
            .values(clearance=0)
        )
        assert await policy_revision(connection, ids["org_a"]) > before
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        assert not await can_read(connection, ids["document_a"])


@pytest.mark.parametrize("role", ["analyst", "viewer"])
async def test_rls_read_member_policy_revision_locking_read(security_db, role):
    ids = security_db["ids"]
    if role == "viewer":
        async with security_db["owner"].begin() as connection:
            await connection.execute(
                schema.org_memberships.update()
                .where(schema.org_memberships.c.org_id == ids["org_a"])
                .where(schema.org_memberships.c.user_id == ids["alice"])
                .values(role="viewer")
            )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        baseline = await policy_revision(connection, ids["org_a"])
        assert (
            await connection.scalar(
                sa.select(schema.orgs.c.policy_revision)
                .where(schema.orgs.c.id == ids["org_a"])
                .with_for_update(read=True)
            )
            is None
        ), "Direct locking SELECT also applies the writer RLS policy"
        actual = await connection.scalar(
            sa.text("SELECT insightrag_security.lock_member_policy_revision(:org)"),
            {"org": ids["org_a"]},
        )
        assert actual == baseline
        assert (
            await connection.scalar(
                sa.text("SELECT insightrag_security.lock_member_policy_revision(:org)"),
                {"org": ids["org_b"]},
            )
            is None
        )


async def test_rls_steward_can_lock_revision_for_policy_mutation(security_db):
    ids = security_db["ids"]
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.org_memberships.update()
            .where(schema.org_memberships.c.org_id == ids["org_a"])
            .where(schema.org_memberships.c.user_id == ids["manager"])
            .values(role="steward")
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        assert (
            await connection.scalar(
                sa.select(schema.orgs.c.policy_revision)
                .where(schema.orgs.c.id == ids["org_a"])
                .with_for_update()
            )
            is not None
        )


async def test_rls_steward_can_grant_without_browsing_membership_directory(security_db):
    ids = security_db["ids"]
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.org_memberships.update()
            .where(schema.org_memberships.c.org_id == ids["org_a"])
            .where(schema.org_memberships.c.user_id == ids["manager"])
            .values(role="steward")
        )
        await connection.execute(
            schema.resource_grants.insert().values(
                org_id=ids["org_a"],
                id=uuid4(),
                resource_id=ids["private_a"],
                user_id=ids["manager"],
                action="manage",
            )
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        assert list(
            (await connection.execute(sa.select(schema.org_memberships.c.user_id))).scalars()
        ) == [ids["manager"]]
        allowed = sa.text("SELECT insightrag_security.can_grant_to_member(:org,:resource,:target)")
        params = {"org": ids["org_a"], "resource": ids["private_a"], "target": ids["alice"]}
        assert await connection.scalar(allowed, params)
        assert not await connection.scalar(allowed, {**params, "target": ids["bob"]})
        await connection.execute(
            schema.resource_grants.insert().values(
                org_id=ids["org_a"],
                id=uuid4(),
                resource_id=ids["private_a"],
                user_id=ids["alice"],
                action="read",
            )
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"])
        assert await can_read(connection, ids["private_a"])


async def test_rls_resource_creation_applies_organization_retention(security_db):
    ids = security_db["ids"]
    resource = uuid4()
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        await connection.execute(
            schema.resources.insert().values(
                org_id=ids["org_a"],
                id=resource,
                workspace_id=ids["workspace_a"],
                kind="document",
                title="Retention policy example",
            )
        )
    async with security_db["owner"].begin() as connection:
        duration = await connection.scalar(
            sa.select(schema.resources.c.retention_until - sa.func.current_timestamp()).where(
                schema.resources.c.org_id == ids["org_a"], schema.resources.c.id == resource
            )
        )
        assert timedelta(days=29, hours=23) < duration <= timedelta(days=30)


@pytest.mark.parametrize(
    ("protection", "expected"),
    [
        ("none", "completed"),
        ("hold", "held"),
        ("retention", "held"),
        ("blob", "pending_storage"),
        ("revoked", "denied"),
    ],
)
async def test_rls_purge_preserves_holds_retention_and_unwired_blobs(
    security_db, protection, expected
):
    ids = security_db["ids"]
    resource, job = uuid4(), uuid4()
    object_key = f"synthetic/{resource}" if protection == "blob" else None
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            schema.resources.insert().values(
                org_id=ids["org_a"],
                id=resource,
                workspace_id=ids["workspace_a"],
                kind="dataset",
                title="Synthetic deletion target",
                state="deleted",
                deleted_at=sa.func.now(),
                created_by=ids["manager"],
                legal_hold=protection == "hold",
                retention_until=datetime.now(UTC)
                + timedelta(days=1 if protection == "retention" else -1),
                object_key=object_key,
            )
        )
        await connection.execute(
            schema.resource_grants.insert().values(
                org_id=ids["org_a"],
                id=uuid4(),
                resource_id=resource,
                user_id=ids["manager"],
                action="delete",
            )
        )
        await connection.execute(
            schema.dataset_rows.insert().values(
                org_id=ids["org_a"],
                resource_id=resource,
                id=uuid4(),
                region="Delhi",
                payload={"synthetic": True},
            )
        )
        await connection.execute(
            schema.document_chunks.insert().values(
                org_id=ids["org_a"],
                resource_id=resource,
                id=uuid4(),
                text="Synthetic source fragment",
                embedding=[1, 0, 0],
            )
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"], purpose="deletion")
        await connection.execute(
            schema.security_jobs.insert().values(
                org_id=ids["org_a"],
                id=job,
                resource_id=resource,
                requested_by=ids["manager"],
                action="delete",
                policy_revision=await policy_revision(connection, ids["org_a"]),
                object_key=object_key,
            )
        )
    if protection == "revoked":
        async with security_db["owner"].begin() as connection:
            await connection.execute(
                schema.resource_grants.delete().where(
                    schema.resource_grants.c.resource_id == resource
                )
            )
    purge = sa.text("SELECT insightrag_security.purge_deleted_resource(:job)")
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["bob"], ids["org_b"], purpose="deletion")
        assert await connection.scalar(purge, {"job": job}) == "denied"
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"], purpose="deletion")
        assert await connection.scalar(purge, {"job": job}) == expected
        assert await connection.scalar(purge, {"job": job}) == expected
    async with security_db["owner"].begin() as connection:
        for table in (schema.dataset_rows, schema.document_chunks):
            remaining = await connection.scalar(
                sa.select(sa.func.count()).select_from(table).where(table.c.resource_id == resource)
            )
            assert remaining == (0 if expected == "completed" else 1)
        assert (
            await connection.scalar(
                sa.select(schema.resources.c.state).where(schema.resources.c.id == resource)
            )
            == "deleted"
        ), "The tombstone is preserved after purge"
        assert await connection.scalar(
            sa.select(schema.security_jobs.c.state).where(schema.security_jobs.c.id == job)
        ) == ("queued" if expected == "pending_storage" else expected)


async def test_phase5_dense_sparse_scope_and_deleted_exclusion(security_db):
    from insightrag.retrieval.repository import retrieve, validate_scope
    from insightrag.security.context import not_found

    ids = security_db["ids"]
    versions = {"a": uuid4(), "b": uuid4()}
    vector = "[" + ",".join(["1"] + ["0"] * 1535) + "]"
    async with security_db["owner"].begin() as connection:
        for org, resource, actor, label in (
            (ids["org_a"], ids["document_a"], ids["alice"], "a"),
            (ids["org_b"], ids["document_b"], ids["bob"], "b"),
        ):
            await connection.execute(
                sa.text("""INSERT INTO document_versions(org_id,resource_id,id,version_number,
                  sha256,object_key,filename,media_type,state,model_id,created_by)
                  VALUES(:org,:resource,:version,1,:hash,:key,'report.txt','text/plain',
                  'published','synthetic-1536',:actor)"""),
                {
                    "org": org,
                    "resource": resource,
                    "version": versions[label],
                    "hash": "a" * 64,
                    "key": f"synthetic/{label}",
                    "actor": actor,
                },
            )
            await connection.execute(
                sa.text("""UPDATE resources SET active_version=:version,latest_version=:version
                  WHERE org_id=:org AND id=:resource"""),
                {"version": versions[label], "org": org, "resource": resource},
            )
            await connection.execute(
                sa.text("""INSERT INTO ingestion_chunks(org_id,resource_id,version_id,position,
                  text,locator,token_count,embedding) VALUES(:org,:resource,:version,0,
                  'Synthetic invoice INV-42 policy','page:1',8,CAST(:vector AS vector))"""),
                {"org": org, "resource": resource, "version": versions[label], "vector": vector},
            )
    access = AccessContext(ids["alice"], ids["org_a"], "analyst", 1, False, 1, "test")
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"], purpose="knowledge")
        await validate_scope(connection, access, ids["workspace_a"], [])
        dense, sparse = await retrieve(
            connection,
            access,
            ids["workspace_a"],
            [],
            "INV-42 policy",
            [1.0] + [0.0] * 1535,
            "synthetic-1536",
            dense_k=5,
            sparse_k=5,
        )
        assert {item.resource_id for item in dense + sparse} == {ids["document_a"]}
        with pytest.raises(type(not_found())):
            await validate_scope(connection, access, ids["workspace_a"], [ids["document_b"]])
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            sa.text(
                "UPDATE resources SET state='deleted', deleted_at=now() "
                "WHERE org_id=:org AND id=:id"
            ),
            {"org": ids["org_a"], "id": ids["document_a"]},
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["alice"], ids["org_a"], purpose="knowledge")
        dense, sparse = await retrieve(
            connection,
            access,
            ids["workspace_a"],
            [],
            "INV-42 policy",
            [1.0] + [0.0] * 1535,
            "synthetic-1536",
            dense_k=5,
            sparse_k=5,
        )
        assert dense == sparse == []


async def test_phase6_sales_aggregation_obeys_row_rls_and_version(security_db):
    from insightrag.analytics.contracts import AnalyticsRequest
    from insightrag.analytics.service import analyze
    from insightrag.security.context import SecurityError

    ids = security_db["ids"]
    versions = {"a": uuid4(), "b": uuid4()}
    async with security_db["owner"].begin() as connection:
        for org, resource, actor, label in (
            (ids["org_a"], ids["dataset_a"], ids["alice"], "a"),
            (ids["org_b"], ids["dataset_b"], ids["bob"], "b"),
        ):
            await connection.execute(
                sa.text("""INSERT INTO document_versions(org_id,resource_id,id,version_number,
                  sha256,object_key,filename,media_type,state,created_by)
                  VALUES(:org,:resource,:version,1,:hash,:key,'sales.csv','text/csv',
                  'published',:actor)"""),
                {
                    "org": org,
                    "resource": resource,
                    "version": versions[label],
                    "hash": "a" * 64,
                    "key": f"synthetic/{label}",
                    "actor": actor,
                },
            )
            await connection.execute(
                sa.text("""UPDATE resources SET active_version=:version,latest_version=:version
                  WHERE org_id=:org AND id=:resource"""),
                {"version": versions[label], "org": org, "resource": resource},
            )
        for number, region, value in ((2, "Delhi", "100.10"), (3, "Mumbai", "200.20")):
            await connection.execute(
                sa.text("""INSERT INTO analytics_sales_rows(org_id,resource_id,version_id,
                  row_number,transaction_id,transaction_date,region,product,revenue,cost,units,
                  returned_units,currency) VALUES(:org,:resource,:version,:row,:transaction,
                  '2025-01-31',:region,'Widget',:revenue,10,1,0,'INR')"""),
                {
                    "org": ids["org_a"],
                    "resource": ids["dataset_a"],
                    "version": versions["a"],
                    "row": number,
                    "transaction": f"a-{number}",
                    "region": region,
                    "revenue": value,
                },
            )
        await connection.execute(
            sa.text("""INSERT INTO analytics_sales_rows(org_id,resource_id,version_id,
              row_number,transaction_id,transaction_date,region,product,revenue,cost,units,
              returned_units,currency) VALUES(:org,:resource,:version,2,'b-2','2025-01-31',
              'Delhi','Widget',900,10,1,0,'INR')"""),
            {"org": ids["org_b"], "resource": ids["dataset_b"], "version": versions["b"]},
        )
        revision = await connection.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )
    database = Database(
        Settings(
            _env_file=None, environment="test", database_url=SecretStr(service_url("DATABASE"))
        )
    )
    try:
        access = AccessContext(
            ids["alice"], ids["org_a"], "analyst", 1, False, revision, "phase6-test"
        )
        response = await analyze(
            database,
            access,
            AnalyticsRequest(
                resource_id=ids["dataset_a"], question="Revenue by region in 2025", year=2025
            ),
            expected_workspace_id=ids["workspace_a"],
        )
        with pytest.raises(SecurityError, match="resource_not_found"):
            await analyze(
                database,
                access,
                AnalyticsRequest(
                    resource_id=ids["dataset_a"], question="Revenue by region in 2025", year=2025
                ),
                expected_workspace_id=ids["workspace_b"],
            )
        assert [(row.dimension, row.value) for row in response.rows] == [("Delhi", "100.1000")]
        assert response.version_id == versions["a"]
        assert response.metric_definition_version == "sales-assumption-v1"
        assert response.source_sha256 == "a" * 64
        assert (response.rows[0].source_row_min, response.rows[0].source_row_max) == (2, 2)
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["alice"], ids["org_a"], purpose="analytics")
            assert (
                await connection.scalar(
                    sa.text("SELECT count(*) FROM analytics_sales_rows WHERE org_id=:org"),
                    {"org": ids["org_a"]},
                )
                == 0
            )
            await context(
                connection,
                ids["alice"],
                ids["org_a"],
                purpose="analytics",
                analytics_resource=ids["dataset_b"],
            )
            assert (
                await connection.scalar(
                    sa.text("SELECT count(*) FROM analytics_sales_rows WHERE org_id=:org"),
                    {"org": ids["org_a"]},
                )
                == 0
            )
            await context(
                connection,
                ids["alice"],
                ids["org_a"],
                purpose="analytics",
                analytics_resource=ids["dataset_a"],
            )
            await connection.execute(sa.text("SET LOCAL statement_timeout = '3000ms'"))
            reference = await connection.execute(
                sa.text("""SELECT SUM(revenue),SUM(revenue-cost),COUNT(*)
                    FROM analytics_sales_rows WHERE org_id=:org AND resource_id=:resource
                    AND version_id=:version AND currency='INR'
                    AND transaction_date >= '2025-01-01' AND transaction_date < '2026-01-01'"""),
                {"org": ids["org_a"], "resource": ids["dataset_a"], "version": versions["a"]},
            )
            revenue, profit, visible_count = reference.one()
            measured_plan = await connection.scalar(
                sa.text("""EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
                    SELECT SUM(revenue) FROM analytics_sales_rows
                    WHERE org_id=:org AND resource_id=:resource AND version_id=:version
                    AND currency='INR' AND transaction_date >= '2025-01-01'
                    AND transaction_date < '2026-01-01'"""),
                {"org": ids["org_a"], "resource": ids["dataset_a"], "version": versions["a"]},
            )
            assert measured_plan[0]["Execution Time"] >= 0
            assert measured_plan[0]["Plan"]["Actual Rows"] == 1
        assert (revenue, profit, visible_count) == (Decimal("100.1000"), Decimal("90.1000"), 1)
        assert Decimal(response.rows[0].value) == revenue
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["alice"], ids["org_a"], purpose="analytics")
            assert (
                await connection.scalar(
                    sa.text("SELECT count(*) FROM analytics_sales_rows WHERE org_id=:org"),
                    {"org": ids["org_a"]},
                )
                == 0
            )
        margin = await analyze(
            database,
            access,
            AnalyticsRequest(
                resource_id=ids["dataset_a"], question="Profit margin in 2025", year=2025
            ),
        )
        assert Decimal(margin.rows[0].value).quantize(Decimal("0.01")) == (
            profit * 100 / revenue
        ).quantize(Decimal("0.01"))
        for ambiguous in ("Gross revenue in 2025", "Monthly revenue growth in 2025"):
            with pytest.raises(SecurityError) as rejected:
                await analyze(
                    database,
                    access,
                    AnalyticsRequest(resource_id=ids["dataset_a"], question=ambiguous, year=2025),
                )
            assert rejected.value.code == "analytics_clarification_required"

        with pytest.raises(SecurityError) as incomplete:
            await analyze(
                database,
                access,
                AnalyticsRequest(
                    resource_id=ids["dataset_a"],
                    question="What percentage of national revenue came from Delhi?",
                    year=2025,
                    region="Delhi",
                ),
            )
        assert incomplete.value.code == "analytics_scope_incomplete"
        async with security_db["owner"].begin() as connection:
            await connection.execute(
                schema.row_entitlements.insert(),
                {
                    "org_id": ids["org_a"],
                    "resource_id": ids["dataset_a"],
                    "user_id": ids["alice"],
                    "region": "Mumbai",
                },
            )
            full_revision = await connection.scalar(
                sa.text("SELECT policy_revision FROM orgs WHERE id=:org"),
                {"org": ids["org_a"]},
            )
        full_access = AccessContext(
            ids["alice"], ids["org_a"], "analyst", 1, False, full_revision, "phase6-complete"
        )
        contribution = await analyze(
            database,
            full_access,
            AnalyticsRequest(
                resource_id=ids["dataset_a"],
                question="What percentage of national revenue came from Delhi?",
                year=2025,
                region="Delhi",
            ),
        )
        assert Decimal(contribution.rows[0].value).quantize(Decimal("0.01")) == Decimal("33.33")

        async with security_db["owner"].begin() as connection:
            await connection.execute(
                schema.row_entitlements.delete().where(
                    schema.row_entitlements.c.org_id == ids["org_a"],
                    schema.row_entitlements.c.resource_id == ids["dataset_a"],
                    schema.row_entitlements.c.user_id == ids["alice"],
                    schema.row_entitlements.c.region == "Mumbai",
                )
            )
            revoked_revision = await connection.scalar(
                sa.text("SELECT policy_revision FROM orgs WHERE id=:org"),
                {"org": ids["org_a"]},
            )
        revoked_access = AccessContext(
            ids["alice"], ids["org_a"], "analyst", 1, False, revoked_revision, "phase6-revoked"
        )
        with pytest.raises(SecurityError) as revoked:
            await analyze(
                database,
                revoked_access,
                AnalyticsRequest(
                    resource_id=ids["dataset_a"],
                    question="What percentage of national revenue came from Delhi?",
                    year=2025,
                    region="Delhi",
                ),
            )
        assert revoked.value.code == "analytics_scope_incomplete"

        with pytest.raises(SecurityError):
            await analyze(
                database,
                access,
                AnalyticsRequest(
                    resource_id=ids["dataset_b"], question="Revenue in 2025", year=2025
                ),
            )
        async with security_db["owner"].begin() as connection:
            await connection.execute(
                sa.text("""UPDATE resources SET state='deleted',deleted_at=now()
              WHERE org_id=:org AND id=:resource"""),
                {"org": ids["org_a"], "resource": ids["dataset_a"]},
            )
        with pytest.raises(SecurityError):
            await analyze(
                database,
                access,
                AnalyticsRequest(
                    resource_id=ids["dataset_a"], question="Revenue in 2025", year=2025
                ),
            )
    finally:
        await database.close()


async def test_phase6_xlsx_worker_publishes_typed_sales_once(security_db):
    import hashlib
    from io import BytesIO

    from insightrag.analytics.contracts import AnalyticsRequest
    from insightrag.analytics.service import analyze
    from openpyxl import Workbook

    ids = security_db["ids"]
    book = Workbook()
    sheet = book.active
    sheet.append(
        [
            "transaction_id",
            "transaction_date",
            "region",
            "product",
            "revenue",
            "cost",
            "units",
            "returns",
            "currency",
        ]
    )
    sheet.append(["x-1", datetime(2025, 1, 31), "Delhi", "Widget", 100.25, 40, 2, 0, "INR"])
    stream = BytesIO()
    book.save(stream)
    body = stream.getvalue()
    version, job = uuid4(), uuid4()
    key = object_key(ids["org_a"], ids["workspace_a"], ids["dataset_a"], version)
    async with security_db["owner"].begin() as owner:
        await owner.execute(
            schema.resource_grants.insert(),
            {
                "org_id": ids["org_a"],
                "id": uuid4(),
                "resource_id": ids["dataset_a"],
                "user_id": ids["manager"],
                "action": "upload",
            },
        )
    async with security_db["runtime"].begin() as connection:
        await context(connection, ids["manager"], ids["org_a"])
        assert (
            await connection.scalar(
                sa.text("""SELECT insightrag_security.reserve_ingestion(
              :org,:resource,:version,:job,:hash,:key,'sales.xlsx',
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')"""),
                {
                    "org": ids["org_a"],
                    "resource": ids["dataset_a"],
                    "version": version,
                    "job": job,
                    "hash": hashlib.sha256(body).hexdigest(),
                    "key": key,
                },
            )
            == "created"
        )
    async with security_db["owner"].connect() as owner:
        revision = await owner.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )

    class FakeStore:
        async def get(self, requested_key, maximum):
            assert requested_key == key and maximum >= len(body)
            return body

    database = Database(
        Settings(
            _env_file=None, database_url=SecretStr(service_url("DATABASE")), database_url_file=None
        )
    )
    claims = JobClaims(ids["org_a"], ids["manager"], job, ids["dataset_a"], revision, 1, 2, uuid4())
    try:
        assert await process_job(database, claims, FakeStore(), None) == "published"
        assert await process_job(database, claims, FakeStore(), None) == "denied"
        async with security_db["owner"].connect() as owner:
            published_revision = await owner.scalar(
                sa.text("SELECT policy_revision FROM orgs WHERE id=:org"),
                {"org": ids["org_a"]},
            )
        access = AccessContext(
            ids["alice"], ids["org_a"], "analyst", 1, False, published_revision, "xlsx"
        )
        response = await analyze(
            database,
            access,
            AnalyticsRequest(resource_id=ids["dataset_a"], question="Revenue in 2025", year=2025),
        )
        assert response.version_id == version
        assert response.source_sha256 == hashlib.sha256(body).hexdigest()
        assert Decimal(response.rows[0].value) == Decimal("100.2500")
        assert (response.rows[0].source_row_min, response.rows[0].source_row_max) == (2, 2)
    finally:
        await database.close()


async def test_phase6_runtime_statement_timeout_is_enforced(security_db):
    ids = security_db["ids"]
    with pytest.raises(sa.exc.DBAPIError) as canceled:
        async with security_db["runtime"].begin() as connection:
            await context(connection, ids["alice"], ids["org_a"], purpose="analytics")
            await connection.execute(sa.text("SET LOCAL statement_timeout = '5ms'"))
            await connection.execute(sa.text("SELECT pg_sleep(0.2)"))
    assert getattr(canceled.value.orig, "sqlstate", None) == "57014"


async def test_phase6_authorized_10k_row_query_and_plan(security_db):
    from time import perf_counter

    from insightrag.analytics.contracts import AnalyticsRequest
    from insightrag.analytics.service import analyze

    ids = security_db["ids"]
    version = uuid4()
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            sa.text("""INSERT INTO document_versions(org_id,resource_id,id,version_number,
              sha256,object_key,filename,media_type,state,created_by)
              VALUES(:org,:resource,:version,1,:hash,'synthetic/scale','sales.csv',
              'text/csv','published',:actor)"""),
            {
                "org": ids["org_a"],
                "resource": ids["dataset_a"],
                "version": version,
                "hash": "c" * 64,
                "actor": ids["alice"],
            },
        )
        await connection.execute(
            sa.text("""UPDATE resources SET active_version=:version,latest_version=:version
              WHERE org_id=:org AND id=:resource"""),
            {"org": ids["org_a"], "resource": ids["dataset_a"], "version": version},
        )
        await connection.execute(
            sa.text("""INSERT INTO analytics_sales_rows(org_id,resource_id,version_id,
              row_number,transaction_id,transaction_date,region,product,revenue,cost,units,
              returned_units,currency) VALUES(:org,:resource,:version,:row,:transaction,
              '2025-01-31','Delhi','Widget',1,0,1,0,'INR')"""),
            [
                {
                    "org": ids["org_a"],
                    "resource": ids["dataset_a"],
                    "version": version,
                    "row": number + 2,
                    "transaction": f"scale-{number}",
                }
                for number in range(10_000)
            ],
        )
        revision = await connection.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )
    database = Database(
        Settings(
            _env_file=None, database_url=SecretStr(service_url("DATABASE")), database_url_file=None
        )
    )
    try:
        access = AccessContext(ids["alice"], ids["org_a"], "analyst", 1, False, revision, "scale")
        async with security_db["runtime"].begin() as connection:
            await context(
                connection,
                ids["alice"],
                ids["org_a"],
                purpose="analytics",
                analytics_resource=ids["dataset_a"],
            )
            await connection.execute(sa.text("SET LOCAL statement_timeout = '30000ms'"))
            for label, sql in (
                (
                    "currency",
                    "SELECT DISTINCT currency FROM analytics_sales_rows WHERE org_id=:org "
                    "AND resource_id=:resource AND version_id=:version LIMIT 2",
                ),
                (
                    "aggregate",
                    "SELECT region,SUM(revenue) FROM analytics_sales_rows WHERE org_id=:org "
                    "AND resource_id=:resource AND version_id=:version AND currency='INR' "
                    "AND transaction_date>='2025-01-01' AND transaction_date<'2026-01-01' "
                    "GROUP BY region LIMIT 500",
                ),
            ):
                plan = await connection.scalar(
                    sa.text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql),
                    {"org": ids["org_a"], "resource": ids["dataset_a"], "version": version},
                )
                print(
                    f"phase6_10k_{label}_execution_ms={plan[0]['Execution Time']:.3f} "
                    f"node={plan[0]['Plan']['Node Type']}"
                )
        started = perf_counter()
        response = await analyze(
            database,
            access,
            AnalyticsRequest(
                resource_id=ids["dataset_a"], question="Revenue by region in 2025", year=2025
            ),
        )
        elapsed_ms = (perf_counter() - started) * 1000
        assert [(row.dimension, row.value, row.source_rows) for row in response.rows] == [
            ("Delhi", "10000.0000", 10_000)
        ]
        print(f"phase6_synthetic_10k_query_elapsed_ms={elapsed_ms:.3f}")
        started = perf_counter()
        contribution = await analyze(
            database,
            access,
            AnalyticsRequest(
                resource_id=ids["dataset_a"],
                question="What percentage of national revenue came from Delhi?",
                year=2025,
                region="Delhi",
            ),
        )
        assert Decimal(contribution.rows[0].value) == Decimal(100)
        print(
            f"phase6_synthetic_10k_contribution_elapsed_ms={(perf_counter() - started) * 1000:.3f}"
        )
    finally:
        await database.close()


async def test_phase5_grounded_answer_and_conversation_owner(security_db):
    import re

    from insightrag.retrieval.contracts import QueryRequest
    from insightrag.retrieval.provider import Completion, Draft
    from insightrag.retrieval.service import answer_query

    ids = security_db["ids"]
    version = uuid4()
    vector = "[" + ",".join(["1"] + ["0"] * 1535) + "]"
    async with security_db["owner"].begin() as connection:
        await connection.execute(
            sa.text("""INSERT INTO document_versions(org_id,resource_id,id,version_number,
              sha256,object_key,filename,media_type,state,model_id,created_by)
              VALUES(:org,:resource,:version,1,:hash,'synthetic/a','report.txt','text/plain',
              'published','synthetic-1536',:actor)"""),
            {
                "org": ids["org_a"],
                "resource": ids["document_a"],
                "version": version,
                "hash": "a" * 64,
                "actor": ids["alice"],
            },
        )
        await connection.execute(
            sa.text("""UPDATE resources SET active_version=:version,latest_version=:version
              WHERE org_id=:org AND id=:resource"""),
            {"version": version, "org": ids["org_a"], "resource": ids["document_a"]},
        )
        await connection.execute(
            sa.text("""INSERT INTO ingestion_chunks(org_id,resource_id,version_id,position,
              text,locator,token_count,embedding) VALUES(:org,:resource,:version,0,
              'Invoice INV-42 must be approved by finance.','page:1',10,
              CAST(:vector AS vector))"""),
            {
                "org": ids["org_a"],
                "resource": ids["document_a"],
                "version": version,
                "vector": vector,
            },
        )
        revision = await connection.scalar(
            sa.text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": ids["org_a"]}
        )

    class FakeEmbedder:
        model_id = "synthetic-1536"
        dimensions = 1536

        async def embed(self, texts):
            return [[1.0] + [0.0] * 1535 for _ in texts]

    class FakeGenerator:
        async def generate(self, question, evidence):
            label = re.search(r"src_[0-9a-f]{24}", evidence)
            assert label is not None
            return Completion(
                Draft(answer="Finance approval is required.", citation_ids=[label.group()]), 100, 12
            )

    settings = Settings(database_url=SecretStr(service_url("DATABASE")))
    database = Database(settings)
    access = AccessContext(ids["alice"], ids["org_a"], "analyst", 1, False, revision, "test")
    try:
        handoff = await answer_query(
            database,
            access,
            QueryRequest(workspace_id=ids["workspace_a"], question="Total sales in Delhi?"),
            settings,
            None,
            None,
        )
        assert handoff.status == "analytics_required" and handoff.citations == []
        response = await answer_query(
            database,
            access,
            QueryRequest(workspace_id=ids["workspace_a"], question="Who approves invoice INV-42?"),
            settings,
            FakeEmbedder(),
            FakeGenerator(),
        )
        assert response.status == "answered" and response.citations[0].version_id == version
        async with security_db["owner"].begin() as owner:
            stored = (
                (
                    await owner.execute(
                        sa.text("""SELECT outcome,citation_refs FROM rag_turns
                      WHERE org_id=:org AND conversation_id=:conversation"""),
                        {"org": ids["org_a"], "conversation": response.conversation_id},
                    )
                )
                .mappings()
                .one()
            )
            assert stored["outcome"] == "answered"
            assert "excerpt" not in str(stored["citation_refs"])
            assert "Finance approval" not in str(stored["citation_refs"])
        followup = await answer_query(
            database,
            access,
            QueryRequest(
                workspace_id=ids["workspace_a"],
                question="Who approves it?",
                conversation_id=response.conversation_id,
            ),
            settings,
            FakeEmbedder(),
            FakeGenerator(),
        )
        assert followup.conversation_id == response.conversation_id
        foreign = AccessContext(ids["bob"], ids["org_b"], "analyst", 3, False, 1, "test")
        from insightrag.security.context import SecurityError

        with pytest.raises(SecurityError):
            await answer_query(
                database,
                foreign,
                QueryRequest(
                    workspace_id=ids["workspace_b"],
                    question="Who approves it?",
                    conversation_id=response.conversation_id,
                ),
                settings,
                FakeEmbedder(),
                FakeGenerator(),
            )

        class RevokingGenerator(FakeGenerator):
            async def generate(self, question, evidence):
                result = await super().generate(question, evidence)
                async with security_db["owner"].begin() as owner:
                    await owner.execute(
                        schema.resource_grants.delete()
                        .where(schema.resource_grants.c.org_id == ids["org_a"])
                        .where(schema.resource_grants.c.resource_id == ids["document_a"])
                        .where(schema.resource_grants.c.user_id == ids["alice"])
                    )
                return result

        with pytest.raises(SecurityError) as changed:
            await answer_query(
                database,
                access,
                QueryRequest(workspace_id=ids["workspace_a"], question="Who approves INV-42?"),
                settings,
                FakeEmbedder(),
                RevokingGenerator(),
            )
        assert changed.value.code in {"evidence_changed", "authorization_changed"}
    finally:
        await database.close()
