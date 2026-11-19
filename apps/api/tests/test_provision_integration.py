"""Real operator provisioning: repeatable identities, explicit roles, no clearance escalation."""

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from insightrag.core.config import Settings
from insightrag.security import schema
from insightrag.security.provision import provision_identity
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import create_async_engine
from test_rls_integration import service_url

pytestmark = pytest.mark.integration


@pytest.fixture
async def provision_db():
    owner_url = service_url("MIGRATION_DATABASE")
    runtime_url = service_url("DATABASE")
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=None,
        database_url_file=None,
        migration_database_url=SecretStr(owner_url),
        migration_database_url_file=None,
        redis_url=None,
        redis_url_file=None,
    )
    engine = create_async_engine(owner_url, hide_parameters=True)
    issuer = f"https://provision.synthetic.invalid/{uuid4()}"
    org_ids = set()
    defaults = {
        "issuer": issuer,
        "subject": "synthetic-operator",
        "organization_name": "Synthetic provisioning organization",
        "home_region": "synthetic-region",
        "role": "steward",
        "workspace_name": "Synthetic workspace",
        "group_name": "Synthetic group",
        "clearance": 1,
        "retention_days": 14,
    }

    async def provision(**overrides):
        result = await provision_identity(settings, **(defaults | overrides))
        org_ids.add(UUID(result["organization_id"]))
        return result

    try:
        yield {
            "owner": engine,
            "settings": settings,
            "runtime_url": runtime_url,
            "issuer": issuer,
            "provision": provision,
        }
    finally:
        async with engine.begin() as connection:
            for table in (
                schema.audit_events,
                schema.group_memberships,
                schema.workspace_memberships,
                schema.groups,
                schema.workspaces,
                schema.org_memberships,
            ):
                await connection.execute(table.delete().where(table.c.org_id.in_(org_ids)))
            await connection.execute(schema.orgs.delete().where(schema.orgs.c.id.in_(org_ids)))
            await connection.execute(
                schema.security_users.delete().where(schema.security_users.c.issuer == issuer)
            )
        await engine.dispose()


async def test_provision_reuses_catalog_records_without_raising_existing_clearance(provision_db):
    initial = await provision_db["provision"]()
    org_id = UUID(initial["organization_id"])
    user_id = UUID(initial["user_id"])
    async with provision_db["owner"].begin() as connection:
        initial_revision = await connection.scalar(
            sa.select(schema.orgs.c.policy_revision).where(schema.orgs.c.id == org_id)
        )
    repeated = await provision_db["provision"](
        organization_id=org_id,
        organization_name="Must not replace existing organization",
        home_region="must-not-replace-region",
        retention_days=1,
        clearance=3,
        role="viewer",
    )
    assert repeated == initial, "Reprovisioning an existing org reuses identity/workspace/group IDs"
    async with provision_db["owner"].begin() as connection:
        assert (
            await connection.scalar(
                sa.select(schema.security_users.c.clearance).where(
                    schema.security_users.c.id == user_id
                )
            )
            == 1
        )
        org = (
            (await connection.execute(sa.select(schema.orgs).where(schema.orgs.c.id == org_id)))
            .mappings()
            .one()
        )
        assert (org["name"], org["home_region"], org["retention_days"]) == (
            "Synthetic provisioning organization",
            "synthetic-region",
            14,
        )
        assert org["policy_revision"] > initial_revision
        membership = (
            await connection.execute(
                sa.select(schema.org_memberships.c.role, schema.org_memberships.c.revision).where(
                    schema.org_memberships.c.org_id == org_id,
                    schema.org_memberships.c.user_id == user_id,
                )
            )
        ).one()
        assert membership == ("viewer", 2), "Explicit operator role changes remain auditable"
        for table in (schema.workspaces, schema.groups, schema.group_memberships):
            assert (
                await connection.scalar(
                    sa.select(sa.func.count()).select_from(table).where(table.c.org_id == org_id)
                )
                == 1
            )
        assert (
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(schema.audit_events)
                .where(schema.audit_events.c.org_id == org_id)
            )
            == 2
        )
    another_org = await provision_db["provision"](clearance=3, role="analyst")
    assert another_org["user_id"] == initial["user_id"]
    assert another_org["organization_id"] != initial["organization_id"]


async def test_provision_runtime_credentials_cannot_perform_operator_work(provision_db):
    settings = provision_db["settings"].model_copy(
        update={"migration_database_url": SecretStr(provision_db["runtime_url"])}
    )
    with pytest.raises(PermissionError, match="approved database operator"):
        await provision_identity(
            settings,
            issuer=provision_db["issuer"],
            subject="unauthorized",
            organization_name="Forbidden",
            home_region="synthetic-region",
        )
    async with provision_db["owner"].begin() as connection:
        assert (
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(schema.security_users)
                .where(schema.security_users.c.issuer == provision_db["issuer"])
            )
            == 0
        )


async def test_provision_missing_existing_org_rolls_back_new_identity(provision_db):
    with pytest.raises(ValueError, match="Organization does not exist"):
        await provision_db["provision"](organization_id=uuid4())
    async with provision_db["owner"].begin() as connection:
        assert (
            await connection.scalar(
                sa.select(sa.func.count())
                .select_from(schema.security_users)
                .where(schema.security_users.c.issuer == provision_db["issuer"])
            )
            == 0
        )
