"""Authentication, current membership and transaction scope for protected operations."""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from insightrag.security.auth import (
    AuthenticationError,
    AuthenticationUnavailable,
    OIDCVerifier,
    Principal,
)
from insightrag.security.context import AccessContext, SecurityError
from insightrag.security.controls import ControlUnavailable, RateLimitExceeded
from insightrag.security.database import set_context, tenant_session

bearer = HTTPBearer(auto_error=False, scheme_name="EnterpriseAccessToken")


async def get_principal(
    request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise SecurityError(401, "authentication_required", "A valid access token is required")
    if request.app.state.settings.environment == "production" and request.url.scheme != "https":
        raise SecurityError(400, "https_required", "HTTPS is required")
    verifier: OIDCVerifier | None = request.app.state.oidc
    if verifier is None:
        raise SecurityError(503, "identity_unavailable", "Enterprise identity is not configured")
    try:
        return await verifier.verify(credentials.credentials)
    except AuthenticationError:
        raise SecurityError(401, "invalid_access_token", "Access token is invalid") from None
    except AuthenticationUnavailable:
        raise SecurityError(
            503, "identity_unavailable", "Enterprise identity is unavailable"
        ) from None


async def get_access_context(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    organization_id: Annotated[UUID, Header(alias="X-Organization-ID")],
) -> AccessContext:
    database = request.app.state.database
    if database.sessions is None:
        raise SecurityError(503, "security_unavailable", "Security database is unavailable")
    async with database.sessions() as session, session.begin():
        identity = (
            (
                await session.execute(
                    text(
                        "SELECT id, clearance FROM "
                        "insightrag_security.security_identity(:issuer, :subject)"
                    ),
                    {"issuer": principal.issuer, "subject": principal.subject},
                )
            )
            .mappings()
            .one_or_none()
        )
        if identity is None:
            raise SecurityError(401, "identity_not_provisioned", "Identity is not provisioned")
        preliminary = AccessContext(
            user_id=identity["id"],
            organization_id=organization_id,
            role="viewer",
            clearance=identity["clearance"],
            mfa=principal.mfa,
            policy_revision=1,
            request_id=request.state.request_id,
        )
        await set_context(session, preliminary)
        member = (
            (
                await session.execute(
                    text(
                        "SELECT m.role, o.policy_revision FROM org_memberships m "
                        "JOIN orgs o ON o.id=m.org_id "
                        "WHERE m.org_id=:org AND m.user_id=:user AND m.status='active'"
                    ),
                    {"org": organization_id, "user": identity["id"]},
                )
            )
            .mappings()
            .one_or_none()
        )
        if member is None:
            raise SecurityError(404, "organization_not_found", "Organization is unavailable")
        context = AccessContext(
            user_id=identity["id"],
            organization_id=organization_id,
            role=member["role"],
            clearance=identity["clearance"],
            mfa=principal.mfa,
            policy_revision=member["policy_revision"],
            request_id=request.state.request_id,
        )
    limiter = request.app.state.rate_limiter
    settings = request.app.state.settings
    try:
        await limiter.check(
            organization_id, context.user_id, limit=settings.rate_limit_per_user, purpose="api-user"
        )
        await limiter.check(
            organization_id,
            organization_id,
            limit=settings.rate_limit_per_organization,
            purpose="api-org",
        )
    except RateLimitExceeded as exc:
        raise SecurityError(429, "rate_limited", "Request limit reached", exc.retry_after) from None
    except ControlUnavailable:
        raise SecurityError(
            503, "quota_unavailable", "Security quota service is unavailable"
        ) from None
    request.state.security_context = context
    return context


async def audit(
    session: AsyncSession,
    context: AccessContext,
    action: str,
    resource_id: UUID | None = None,
    outcome: str = "allowed",
) -> None:
    await session.execute(
        text(
            "INSERT INTO audit_events(org_id,id,actor_id,action,resource_id,outcome,request_id) "
            "VALUES(:org,:id,:actor,:action,:resource,:outcome,:request)"
        ),
        {
            "org": context.organization_id,
            "id": uuid4(),
            "actor": context.user_id,
            "action": action,
            "resource": resource_id,
            "outcome": outcome,
            "request": context.request_id,
        },
    )


async def get_security_session(
    request: Request, context: Annotated[AccessContext, Depends(get_access_context)]
) -> AsyncIterator[AsyncSession]:
    try:
        async with tenant_session(request.app.state.database, context) as session:
            yield session
            # Function-scoped dependency runs before response release; reject mid-flight revocation.
            current = await session.scalar(
                text("SELECT insightrag_security.lock_member_policy_revision(:org)"),
                {"org": context.organization_id},
            )
            expected = getattr(request.state, "expected_policy_revision", context.policy_revision)
            if current != expected:
                raise SecurityError(
                    409, "authorization_changed", "Authorization changed; retry the request"
                )
    except SecurityError:
        # Denied operations roll back. Record a separate denial if still a member.
        try:
            async with tenant_session(request.app.state.database, context) as denied:
                await audit(denied, context, "security.denied", outcome="denied")
        except Exception:
            # Revoked membership can deny audit writes; HTTP outcome logs remain.
            pass
        raise


Context = Annotated[AccessContext, Depends(get_access_context)]
Session = Annotated[AsyncSession, Depends(get_security_session, scope="function")]


async def prepare_policy_write(
    request: Request, session: AsyncSession, context: AccessContext
) -> None:
    """Pin policy before mutation, rather than absorbing unrelated revision changes.

    Every authorization-changing trigger updates this organization row. Holding
    its write lock serializes our mutation with concurrent policy changes until
    transaction completion; compare the baseline before writing anything.
    """
    revision = await session.scalar(
        text("SELECT policy_revision FROM orgs WHERE id=:org FOR UPDATE"),
        {"org": context.organization_id},
    )
    if revision != context.policy_revision:
        raise SecurityError(
            409, "authorization_changed", "Authorization changed; retry the request"
        )
    request.state.policy_write_locked = True
    request.state.expected_policy_revision = context.policy_revision


async def record_own_policy_change(
    request: Request, session: AsyncSession, context: AccessContext
) -> int:
    if not getattr(request.state, "policy_write_locked", False):
        raise SecurityError(
            500, "security_invariant_error", "Security operation could not complete"
        )
    revision = await session.scalar(
        text("SELECT policy_revision FROM orgs WHERE id=:org"), {"org": context.organization_id}
    )
    if revision is None:
        raise SecurityError(409, "authorization_changed", "Authorization changed")
    request.state.expected_policy_revision = int(revision)
    return int(revision)
