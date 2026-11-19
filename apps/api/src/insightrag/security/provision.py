"""Operator-only provisioning. No signup, token minting or request-role escalation."""

import argparse
import asyncio
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from insightrag.core.config import Settings


async def provision_identity(
    settings: Settings,
    *,
    issuer: str,
    subject: str,
    organization_name: str,
    home_region: str,
    organization_id: UUID | None = None,
    role: str = "admin",
    workspace_name: str = "Default",
    group_name: str | None = None,
    clearance: int = 0,
    retention_days: int = 30,
) -> dict[str, str]:
    if settings.migration_database_url is None:
        raise ValueError("Operator provisioning requires separate migration credentials")
    if role not in {"owner", "admin", "steward", "analyst", "viewer", "auditor"}:
        raise ValueError("Unknown role")
    if not issuer.startswith("https://") or not subject or len(subject) > 255:
        raise ValueError("A registered HTTPS issuer and bounded subject are required")
    if not home_region or not 0 <= clearance <= 3 or not 0 <= retention_days <= 3650:
        raise ValueError("Region, clearance and retention must be explicit and valid")
    engine = create_async_engine(
        settings.migration_database_url.get_secret_value(), hide_parameters=True
    )
    try:
        async with engine.begin() as connection:
            # Require the operator role; never fall back to a request-level administrative claim.
            privilege = await connection.scalar(
                text("SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname=current_user")
            )
            if not privilege:
                raise PermissionError("Provisioning requires the approved database operator role")
            user_id = await connection.scalar(
                text("SELECT id FROM security_users WHERE issuer=:issuer AND subject=:subject"),
                {"issuer": issuer, "subject": subject},
            )
            if user_id is None:
                user_id = uuid4()
                await connection.execute(
                    text(
                        "INSERT INTO security_users(id,issuer,subject,clearance) "
                        "VALUES(:id,:issuer,:subject,:clearance)"
                    ),
                    {"id": user_id, "issuer": issuer, "subject": subject, "clearance": clearance},
                )
            # Existing identity clearance is not silently raised by organization provisioning.
            org_id = organization_id or uuid4()
            if organization_id is None:
                await connection.execute(
                    text(
                        "INSERT INTO orgs(id,name,home_region,retention_days) "
                        "VALUES(:id,:name,:region,:days)"
                    ),
                    {
                        "id": org_id,
                        "name": organization_name,
                        "region": home_region,
                        "days": retention_days,
                    },
                )
            elif not await connection.scalar(
                text("SELECT id FROM orgs WHERE id=:id"), {"id": org_id}
            ):
                raise ValueError("Organization does not exist")
            await connection.execute(
                text(
                    "INSERT INTO org_memberships(org_id,user_id,role) VALUES(:org,:user,:role) "
                    "ON CONFLICT(org_id,user_id) DO UPDATE SET role=EXCLUDED.role,status='active', "
                    "revision=org_memberships.revision+1"
                ),
                {"org": org_id, "user": user_id, "role": role},
            )
            workspace_id = await connection.scalar(
                text(
                    "SELECT id FROM workspaces WHERE org_id=:org AND name=:name ORDER BY id LIMIT 1"
                ),
                {"org": org_id, "name": workspace_name},
            )
            if workspace_id is None:
                workspace_id = uuid4()
                await connection.execute(
                    text("INSERT INTO workspaces(org_id,id,name) VALUES(:org,:id,:name)"),
                    {"org": org_id, "id": workspace_id, "name": workspace_name},
                )
            workspace_role = {
                "owner": "manager",
                "admin": "manager",
                "steward": "steward",
                "analyst": "analyst",
                "viewer": "viewer",
                "auditor": "viewer",
            }[role]
            await connection.execute(
                text(
                    "INSERT INTO workspace_memberships(org_id,workspace_id,user_id,role) "
                    "VALUES(:org,:workspace,:user,:role) ON CONFLICT(org_id,workspace_id,user_id) "
                    "DO UPDATE SET role=EXCLUDED.role"
                ),
                {"org": org_id, "workspace": workspace_id, "user": user_id, "role": workspace_role},
            )
            result = {
                "user_id": str(user_id),
                "organization_id": str(org_id),
                "workspace_id": str(workspace_id),
            }
            if group_name:
                group_id = await connection.scalar(
                    text(
                        "SELECT id FROM groups WHERE org_id=:org AND name=:name ORDER BY id LIMIT 1"
                    ),
                    {"org": org_id, "name": group_name},
                )
                if group_id is None:
                    group_id = uuid4()
                    await connection.execute(
                        text("INSERT INTO groups(org_id,id,name) VALUES(:org,:id,:name)"),
                        {"org": org_id, "id": group_id, "name": group_name},
                    )
                await connection.execute(
                    text(
                        "INSERT INTO group_memberships(org_id,group_id,user_id) "
                        "VALUES(:org,:group,:user) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {"org": org_id, "group": group_id, "user": user_id},
                )
                result["group_id"] = str(group_id)
            await connection.execute(
                text(
                    "INSERT INTO audit_events(org_id,id,actor_id,action,outcome,request_id) "
                    "VALUES(:org,:id,:actor,'operator.provisioned','allowed',:request)"
                ),
                {"org": org_id, "id": uuid4(), "actor": user_id, "request": str(uuid4())},
            )
            return result
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Approved operator: provision enterprise identity")
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--organization-id", type=UUID)
    parser.add_argument("--role", default="admin")
    parser.add_argument("--workspace", default="Default")
    parser.add_argument("--group")
    parser.add_argument("--clearance", type=int, default=0)
    parser.add_argument("--retention-days", type=int, default=30)
    args = parser.parse_args()
    result = asyncio.run(
        provision_identity(
            Settings(),
            issuer=args.issuer,
            subject=args.subject,
            organization_name=args.organization,
            home_region=args.region,
            organization_id=args.organization_id,
            role=args.role,
            workspace_name=args.workspace,
            group_name=args.group,
            clearance=args.clearance,
            retention_days=args.retention_days,
        )
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
