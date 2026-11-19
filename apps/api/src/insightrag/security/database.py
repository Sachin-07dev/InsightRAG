"""Transaction-local identity and explicit current-policy checks for all tools."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from insightrag.db.session import Database
from insightrag.security.context import AccessContext, Action, SecurityError, not_found


async def set_context(session: AsyncSession, context: AccessContext) -> None:
    await session.execute(
        text(
            "SELECT set_config('app.user_id', :user, true), "
            "set_config('app.organization_id', :org, true), "
            "set_config('app.mfa', :mfa, true), "
            "set_config('app.purpose', :purpose, true)"
        ),
        {
            "user": str(context.user_id),
            "org": str(context.organization_id),
            "mfa": "true" if context.mfa else "false",
            "purpose": context.purpose,
        },
    )


@asynccontextmanager
async def tenant_session(database: Database, context: AccessContext) -> AsyncIterator[AsyncSession]:
    if database.sessions is None:
        raise SecurityError(503, "security_unavailable", "Security database is unavailable")
    async with database.sessions() as session, session.begin():
        await set_context(session, context)
        yield session


async def require_resource(
    session: AsyncSession, context: AccessContext, resource_id: UUID, action: Action
) -> dict[str, Any]:
    # The SQL function evaluates current DB membership/grants; context is never proof of access.
    allowed = await session.scalar(
        text("SELECT insightrag_security.can_resource(:resource, :action)"),
        {"resource": resource_id, "action": action},
    )
    if not allowed:
        raise not_found()
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, workspace_id, kind, title, classification, require_mfa, state, "
                    "legal_hold, retention_until, object_key FROM resources "
                    "WHERE org_id=:org AND id=:id"
                ),
                {"org": context.organization_id, "id": resource_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise not_found()
    return dict(row)


async def require_resource_metadata(
    session: AsyncSession, context: AccessContext, resource_id: UUID
) -> dict[str, Any]:
    """Read permitted catalog state without treating quarantine as published content."""
    allowed = await session.scalar(
        text("SELECT insightrag_security.can_resource_metadata(:org, :resource)"),
        {"org": context.organization_id, "resource": resource_id},
    )
    if not allowed:
        raise not_found()
    row = (
        (
            await session.execute(
                text(
                    "SELECT id, workspace_id, kind, title, classification, state FROM resources "
                    "WHERE org_id=:org AND id=:resource"
                ),
                {"org": context.organization_id, "resource": resource_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise not_found()
    return dict(row)
