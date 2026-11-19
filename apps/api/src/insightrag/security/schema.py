"""Core security catalog. RLS and grants are installed by the immutable 0002 migration."""

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect

metadata = sa.MetaData()


class IsolationVector(sa.types.UserDefinedType[list[float]]):
    """Three dimensions solely for proving protected vector scans, not production embeddings."""

    cache_ok = True

    def get_col_spec(self, **kwargs: Any) -> str:
        return "vector(3)"

    def bind_processor(self, dialect: Dialect) -> Callable[[Any], str]:
        def encode(value: Any) -> str:
            if isinstance(value, str):
                return value
            return "[" + ",".join(str(float(item)) for item in value) + "]"

        return encode


def tenant_column() -> sa.Column[Any]:
    return sa.Column("org_id", sa.Uuid(as_uuid=True), nullable=False)


def id_column() -> sa.Column[Any]:
    return sa.Column("id", sa.Uuid(as_uuid=True), server_default=sa.text("gen_random_uuid()"))


def tenant_fk(table: str, column: str, *, local: str | None = None) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["org_id", local or column], [f"{table}.org_id", f"{table}.{column}"]
    )


security_users = sa.Table(
    "security_users",
    metadata,
    sa.Column(
        "id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    ),
    sa.Column("issuer", sa.Text(), nullable=False),
    sa.Column("subject", sa.Text(), nullable=False),
    sa.Column("clearance", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.UniqueConstraint("issuer", "subject"),
    sa.CheckConstraint("clearance BETWEEN 0 AND 3"),
)

orgs = sa.Table(
    "orgs",
    metadata,
    sa.Column(
        "id", sa.Uuid(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    ),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("home_region", sa.Text(), nullable=False),
    sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
    sa.Column("policy_revision", sa.BigInteger(), nullable=False, server_default="1"),
    sa.CheckConstraint("retention_days >= 0 AND policy_revision >= 1"),
)
organizations = orgs

org_memberships = sa.Table(
    "org_memberships",
    metadata,
    tenant_column(),
    sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("security_users.id"), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    sa.PrimaryKeyConstraint("org_id", "user_id"),
    sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
    sa.CheckConstraint("role IN ('owner','admin','steward','analyst','viewer','auditor')"),
    sa.CheckConstraint("status IN ('active','suspended') AND revision >= 1"),
)

workspaces = sa.Table(
    "workspaces",
    metadata,
    tenant_column(),
    id_column(),
    sa.Column("name", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "id"),
    sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
)

workspace_memberships = sa.Table(
    "workspace_memberships",
    metadata,
    tenant_column(),
    sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "workspace_id", "user_id"),
    tenant_fk("workspaces", "id", local="workspace_id"),
    tenant_fk("org_memberships", "user_id"),
    sa.CheckConstraint("role IN ('manager','steward','analyst','viewer')"),
)

groups = sa.Table(
    "groups",
    metadata,
    tenant_column(),
    id_column(),
    sa.Column("name", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "id"),
    sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
)
group_memberships = sa.Table(
    "group_memberships",
    metadata,
    tenant_column(),
    sa.Column("group_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "group_id", "user_id"),
    tenant_fk("groups", "id", local="group_id"),
    tenant_fk("org_memberships", "user_id"),
)

resources = sa.Table(
    "resources",
    metadata,
    tenant_column(),
    id_column(),
    sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("kind", sa.Text(), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("classification", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("require_mfa", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("state", sa.Text(), nullable=False, server_default="quarantine"),
    sa.Column("purpose", sa.Text()),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
    sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()),
    sa.Column("retention_until", sa.DateTime(timezone=True)),
    sa.Column("object_key", sa.Text()),
    sa.Column(
        "created_by",
        sa.Uuid(as_uuid=True),
        nullable=False,
        server_default=sa.text("NULLIF(current_setting('app.user_id', true), '')::uuid"),
    ),
    sa.Column(
        "created_in_transaction",
        sa.Text(),
        nullable=False,
        server_default=sa.text("pg_current_xact_id()::text"),
    ),
    sa.PrimaryKeyConstraint("org_id", "id"),
    tenant_fk("workspaces", "id", local="workspace_id"),
    tenant_fk("org_memberships", "user_id", local="created_by"),
    sa.CheckConstraint("kind IN ('document','dataset')"),
    sa.CheckConstraint("classification BETWEEN 0 AND 3"),
    sa.CheckConstraint("state IN ('quarantine','active','deleted')"),
    sa.CheckConstraint("(state = 'deleted') = (deleted_at IS NOT NULL)"),
)

resource_grants = sa.Table(
    "resource_grants",
    metadata,
    tenant_column(),
    id_column(),
    sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.Uuid(as_uuid=True)),
    sa.Column("group_id", sa.Uuid(as_uuid=True)),
    sa.Column("action", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "id"),
    tenant_fk("resources", "id", local="resource_id"),
    tenant_fk("org_memberships", "user_id"),
    tenant_fk("groups", "id", local="group_id"),
    sa.CheckConstraint("(user_id IS NULL) <> (group_id IS NULL)"),
    sa.CheckConstraint("action IN ('read','query','upload','delete','manage')"),
    sa.UniqueConstraint("org_id", "resource_id", "user_id", "action"),
    sa.UniqueConstraint("org_id", "resource_id", "group_id", "action"),
)

dataset_rows = sa.Table(
    "dataset_rows",
    metadata,
    tenant_column(),
    sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
    id_column(),
    sa.Column("region", sa.Text(), nullable=False),
    sa.Column("payload", JSONB(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "resource_id", "id"),
    tenant_fk("resources", "id", local="resource_id"),
)
row_entitlements = sa.Table(
    "row_entitlements",
    metadata,
    tenant_column(),
    sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("region", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "resource_id", "user_id", "region"),
    tenant_fk("resources", "id", local="resource_id"),
    tenant_fk("org_memberships", "user_id"),
)
document_chunks = sa.Table(
    "document_chunks",
    metadata,
    tenant_column(),
    sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
    id_column(),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("embedding", IsolationVector()),
    sa.PrimaryKeyConstraint("org_id", "resource_id", "id"),
    tenant_fk("resources", "id", local="resource_id"),
)
audit_events = sa.Table(
    "audit_events",
    metadata,
    tenant_column(),
    id_column(),
    sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("action", sa.Text(), nullable=False),
    sa.Column("resource_id", sa.Uuid(as_uuid=True)),
    sa.Column("outcome", sa.Text(), nullable=False),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column("request_id", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("org_id", "id"),
    tenant_fk("org_memberships", "user_id", local="actor_id"),
    tenant_fk("resources", "id", local="resource_id"),
)
security_jobs = sa.Table(
    "security_jobs",
    metadata,
    tenant_column(),
    id_column(),
    sa.Column("resource_id", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("requested_by", sa.Uuid(as_uuid=True), nullable=False),
    sa.Column("action", sa.Text(), nullable=False),
    sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
    sa.Column("policy_revision", sa.BigInteger(), nullable=False),
    sa.Column("object_key", sa.Text()),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.PrimaryKeyConstraint("org_id", "id"),
    tenant_fk("resources", "id", local="resource_id"),
    tenant_fk("org_memberships", "user_id", local="requested_by"),
    sa.CheckConstraint("action IN ('read','query','upload','delete','manage')"),
    sa.CheckConstraint("state IN ('queued','running','denied','completed','held','failed')"),
    sa.CheckConstraint("policy_revision >= 1"),
)

sa.Index("ix_resource_workspace", resources.c.org_id, resources.c.workspace_id)
sa.Index("ix_grant_resource", resource_grants.c.org_id, resource_grants.c.resource_id)
sa.Index("ix_group_user", group_memberships.c.org_id, group_memberships.c.user_id)
