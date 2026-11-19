"""Authenticated metadata and guarded data/tool entry points; no RAG/LLM execution."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from insightrag.security.context import SecurityError, not_found
from insightrag.security.database import require_resource, require_resource_metadata, set_context
from insightrag.security.dependencies import (
    Context,
    Session,
    audit,
    prepare_policy_write,
    record_own_policy_change,
)
from insightrag.security.uploads import ScannerUnavailable, UploadRejected, validate_upload

router = APIRouter(prefix="/api/v1", tags=["enterprise security"])


class ResourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["document", "dataset"]
    title: str = Field(min_length=1, max_length=200)
    classification: int = Field(default=0, ge=0, le=3, strict=True)
    require_mfa: bool = False


class ResourceGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID | None = None
    group_id: UUID | None = None
    action: Literal["read", "query", "upload", "delete", "manage"]


def require_admin(context: Context) -> None:
    if context.role not in {"owner", "admin"}:
        raise SecurityError(403, "administration_denied", "Organization administration is required")


def check_upload_content_length(value: str | None, maximum: int) -> None:
    """Reject malformed/oversized lengths without unbounded integer conversion."""
    if value is not None and (re.fullmatch(r"[0-9]{1,20}", value) is None or int(value) > maximum):
        raise SecurityError(413, "upload_too_large", "Upload exceeds the configured limit")


@router.get("/me")
async def me(context: Context, session: Session) -> dict[str, Any]:
    await audit(session, context, "identity.me")
    return {
        "user_id": str(context.user_id),
        "organization_id": str(context.organization_id),
        "role": context.role,
        "policy_revision": context.policy_revision,
        "mfa": context.mfa,
    }


@router.get("/workspaces")
async def workspaces(context: Context, session: Session) -> list[dict[str, Any]]:
    rows = (
        await session.execute(text("SELECT id,name FROM workspaces ORDER BY name LIMIT 100"))
    ).mappings()
    await audit(session, context, "workspaces.list")
    return [dict(row) for row in rows]


@router.get("/directory/{kind}")
async def directory(
    kind: Literal["memberships", "groups", "roles"], context: Context, session: Session
) -> list[dict[str, Any]]:
    require_admin(context)
    queries = {
        "memberships": "SELECT user_id,role,status FROM org_memberships LIMIT 100",
        "groups": "SELECT id,name FROM groups LIMIT 100",
    }
    if kind == "roles":
        await audit(session, context, "directory.roles")
        return [
            {"role": role} for role in ["owner", "admin", "steward", "analyst", "viewer", "auditor"]
        ]
    rows = (await session.execute(text(queries[kind]))).mappings()
    await audit(session, context, f"directory.{kind}")
    return [dict(row) for row in rows]


@router.post("/workspaces/{workspace_id}/resources", status_code=201)
async def create_resource(
    workspace_id: UUID,
    payload: ResourceCreate,
    context: Context,
    session: Session,
    request: Request,
) -> dict[str, str]:
    permitted = await session.scalar(
        text("SELECT insightrag_security.has_workspace_capability(:org,:workspace,'upload')"),
        {"org": context.organization_id, "workspace": workspace_id},
    )
    if (
        not permitted
        or payload.classification > context.clearance
        or (payload.require_mfa and not context.mfa)
    ):
        raise not_found()
    await prepare_policy_write(request, session, context)
    resource_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO resources(org_id,id,workspace_id,kind,title,classification,"
            "require_mfa,state) "
            "VALUES(:org,:id,:workspace,:kind,:title,:classification,:mfa,'quarantine')"
        ),
        {
            "org": context.organization_id,
            "id": resource_id,
            "workspace": workspace_id,
            "kind": payload.kind,
            "title": payload.title,
            "classification": payload.classification,
            "mfa": payload.require_mfa,
        },
    )
    for action in ("read", "query", "upload", "delete", "manage"):
        await session.execute(
            text(
                "INSERT INTO resource_grants(org_id,id,resource_id,user_id,action) "
                "VALUES(:org,:id,:resource,:user,:action)"
            ),
            {
                "org": context.organization_id,
                "id": uuid4(),
                "resource": resource_id,
                "user": context.user_id,
                "action": action,
            },
        )
    await audit(session, context, "resource.created", resource_id)
    await record_own_policy_change(request, session, context)
    return {"id": str(resource_id), "state": "quarantine"}


@router.get("/resources/{resource_id}")
async def resource_metadata(
    resource_id: UUID, context: Context, session: Session
) -> dict[str, Any]:
    resource = await require_resource_metadata(session, context, resource_id)
    await audit(session, context, "resource.read", resource_id)
    # Do not disclose physical object paths or operational hold metadata.
    return {
        key: resource[key]
        for key in ("id", "workspace_id", "kind", "title", "classification", "state")
    }


@router.get("/datasets/{resource_id}/rows")
async def dataset_rows(
    resource_id: UUID, context: Context, session: Session
) -> list[dict[str, Any]]:
    scoped = context.for_operation("analytics")
    await set_context(session, scoped)
    resource = await require_resource(session, scoped, resource_id, "query")
    if resource["kind"] != "dataset":
        raise not_found()
    rows = (
        (
            await session.execute(
                text(
                    "SELECT id,region,payload FROM dataset_rows "
                    "WHERE org_id=:org AND resource_id=:resource LIMIT 100"
                ),
                {"org": context.organization_id, "resource": resource_id},
            )
        )
        .mappings()
        .all()
    )
    await require_resource(session, scoped, resource_id, "query")
    await audit(session, context, "dataset.rows", resource_id)
    return [dict(row) for row in rows]


@router.get("/documents/{resource_id}/evidence")
async def evidence(resource_id: UUID, context: Context, session: Session) -> list[dict[str, Any]]:
    scoped = context.for_operation("knowledge")
    await set_context(session, scoped)
    resource = await require_resource(session, scoped, resource_id, "read")
    if resource["kind"] != "document":
        raise not_found()
    rows = (
        (
            await session.execute(
                text(
                    "SELECT id,text FROM document_chunks "
                    "WHERE org_id=:org AND resource_id=:resource LIMIT 20"
                ),
                {"org": context.organization_id, "resource": resource_id},
            )
        )
        .mappings()
        .all()
    )
    await require_resource(session, scoped, resource_id, "read")
    await audit(session, context, "document.evidence", resource_id)
    return [dict(row) for row in rows]


@router.post("/resources/{resource_id}/grants", status_code=201)
async def add_grant(
    resource_id: UUID, payload: ResourceGrant, context: Context, session: Session, request: Request
) -> dict[str, str]:
    if (payload.user_id is None) == (payload.group_id is None):
        raise SecurityError(422, "invalid_grant", "Choose one user or group principal")
    # Deny inaccessible resources uniformly before a privileged revision lock.
    # Recheck under the lock so a concurrent revocation cannot authorize a write.
    await require_resource(session, context, resource_id, "manage")
    await prepare_policy_write(request, session, context)
    await require_resource(session, context, resource_id, "manage")
    if payload.user_id:
        member = await session.scalar(
            text("SELECT insightrag_security.can_grant_to_member(:org,:resource,:user)"),
            {"org": context.organization_id, "resource": resource_id, "user": payload.user_id},
        )
        if not member:
            raise not_found()
    if payload.group_id:
        group = await session.scalar(
            text("SELECT id FROM groups WHERE org_id=:org AND id=:group"),
            {"org": context.organization_id, "group": payload.group_id},
        )
        if group is None:
            raise not_found()
    grant_id = uuid4()
    await session.execute(
        text(
            "INSERT INTO resource_grants(org_id,id,resource_id,user_id,group_id,action) "
            "VALUES(:org,:id,:resource,:user,:group,:action)"
        ),
        {
            "org": context.organization_id,
            "id": grant_id,
            "resource": resource_id,
            "user": payload.user_id,
            "group": payload.group_id,
            "action": payload.action,
        },
    )
    # Triggers advance the locked organization's revision; record our own changes.
    await audit(session, context, "resource.granted", resource_id)
    await record_own_policy_change(request, session, context)
    return {"id": str(grant_id)}


@router.delete("/resources/{resource_id}/grants/{grant_id}", status_code=200)
async def revoke_grant(
    resource_id: UUID, grant_id: UUID, context: Context, session: Session, request: Request
) -> dict[str, str]:
    await require_resource(session, context, resource_id, "manage")
    await prepare_policy_write(request, session, context)
    await require_resource(session, context, resource_id, "manage")
    await session.execute(
        text(
            "DELETE FROM resource_grants WHERE org_id=:org AND resource_id=:resource AND id=:grant"
        ),
        {"org": context.organization_id, "resource": resource_id, "grant": grant_id},
    )
    await audit(session, context, "resource.revoked", resource_id)
    await record_own_policy_change(request, session, context)
    return {"status": "revoked"}


@router.delete("/resources/{resource_id}", status_code=202)
async def delete_resource(
    resource_id: UUID, context: Context, session: Session, request: Request
) -> dict[str, str]:
    await require_resource(session, context, resource_id, "delete")
    await prepare_policy_write(request, session, context)
    resource = await require_resource(session, context, resource_id, "delete")
    job_id = uuid4()
    await audit(session, context, "resource.deleted", resource_id)
    await session.execute(
        text(
            "UPDATE resources SET state='deleted',deleted_at=:now "
            "WHERE org_id=:org AND id=:resource"
        ),
        {"now": datetime.now(UTC), "org": context.organization_id, "resource": resource_id},
    )
    revision = await record_own_policy_change(request, session, context)
    # Tombstone and cleanup intent commit together; job uses the new policy revision.
    await session.execute(
        text(
            "INSERT INTO security_jobs(org_id,id,resource_id,requested_by,action,state,"
            "policy_revision,object_key) "
            "VALUES(:org,:job,:resource,:user,'delete','queued',:revision,:key)"
        ),
        {
            "org": context.organization_id,
            "job": job_id,
            "resource": resource_id,
            "user": context.user_id,
            "revision": revision,
            "key": resource["object_key"],
        },
    )
    return {"id": str(job_id), "state": "access_blocked", "purge": "pending"}


@router.get("/jobs/{job_id}")
async def job_status(job_id: UUID, context: Context, session: Session) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    "SELECT id,state,action,resource_id FROM security_jobs "
                    "WHERE org_id=:org AND id=:job"
                ),
                {"org": context.organization_id, "job": job_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise not_found()
    await audit(session, context, "job.status")
    return dict(row)


@router.get("/audit-events")
async def audit_events(context: Context, session: Session) -> list[dict[str, Any]]:
    if context.role not in {"owner", "admin", "auditor"}:
        raise SecurityError(403, "audit_denied", "Audit reviewer role is required")
    rows = (
        (
            await session.execute(
                text(
                    "SELECT id,actor_id,action,outcome,created_at,request_id "
                    "FROM audit_events ORDER BY created_at DESC LIMIT 100"
                )
            )
        )
        .mappings()
        .all()
    )
    await audit(session, context, "audit.review")
    return [dict(row) for row in rows]


@router.post("/resources/{resource_id}/validate-upload")
async def validate_resource_upload(
    resource_id: UUID,
    request: Request,
    context: Context,
    session: Session,
    filename: Annotated[str, Header(alias="X-Filename", max_length=200)],
) -> dict[str, Any]:
    await require_resource(session, context, resource_id, "upload")
    length = request.headers.get("content-length")
    maximum = request.app.state.settings.upload_max_bytes
    check_upload_content_length(length, maximum)
    try:
        result = await validate_upload(
            request.stream(),
            filename=filename,
            content_type=request.headers.get("content-type"),
            scanner=request.app.state.scanner,
            max_file_bytes=maximum,
        )
    except ScannerUnavailable:
        raise SecurityError(503, "scanner_unavailable", "Malware scanner is unavailable") from None
    except UploadRejected as exc:
        raise SecurityError(422, exc.code, "Upload validation failed") from None
    await require_resource(session, context, resource_id, "upload")
    await audit(session, context, "upload.validated", resource_id)
    return {
        "status": "validated",
        "sha256": result.sha256,
        "size_bytes": result.size_bytes,
        "stored": False,
        "published": False,
    }
