"""Authenticated upload, progress and published evidence endpoints."""

import asyncio
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, Header, Request
from sqlalchemy import text

from insightrag.ingestion.service import configured_store
from insightrag.ingestion.storage import StorageUnavailable
from insightrag.security.context import SecurityError, not_found
from insightrag.security.controls import SignedJobEnvelope, object_key
from insightrag.security.database import require_resource, set_context
from insightrag.security.dependencies import Context, Session, audit
from insightrag.security.routes import check_upload_content_length
from insightrag.security.uploads import ScannerUnavailable, UploadRejected, validate_upload

router = APIRouter(prefix="/api/v1", tags=["ingestion"])


async def _dispatch(settings: Any, token: str) -> None:
    from insightrag.worker import create_celery

    celery = create_celery(settings)
    try:
        await asyncio.to_thread(
            celery.send_task, "insightrag.ingestion.execute", args=[token], argsrepr="(<redacted>,)"
        )
    finally:
        celery.close()


@router.post("/resources/{resource_id}/versions", status_code=202)
async def upload_version(
    resource_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    context: Context,
    session: Session,
    filename: Annotated[str, Header(alias="X-Filename", max_length=200)],
    reindex: Annotated[bool, Header(alias="X-Reindex")] = False,
) -> dict[str, Any]:
    resource = await require_resource(session, context, resource_id, "upload")
    check_upload_content_length(
        request.headers.get("content-length"), request.app.state.settings.upload_max_bytes
    )
    settings = request.app.state.settings
    store = configured_store(settings)
    if store is None or settings.signed_job_key is None or settings.redis_url is None:
        raise SecurityError(503, "ingestion_unavailable", "Ingestion dependencies are unavailable")
    try:
        validated = await validate_upload(
            request.stream(),
            filename=filename,
            content_type=request.headers.get("content-type"),
            scanner=request.app.state.scanner,
            max_file_bytes=settings.upload_max_bytes,
        )
    except ScannerUnavailable:
        raise SecurityError(503, "scanner_unavailable", "Malware scanner is unavailable") from None
    except UploadRejected as exc:
        raise SecurityError(422, exc.code, "Upload validation failed") from None
    if resource["kind"] != ("dataset" if validated.suffix in (".csv", ".xlsx") else "document"):
        raise SecurityError(422, "resource_kind_mismatch", "File type does not match resource kind")
    await require_resource(session, context, resource_id, "upload")
    version_id, job_id = uuid4(), uuid4()
    key = object_key(context.organization_id, resource["workspace_id"], resource_id, version_id)
    try:
        await store.put(key, validated.data, validated.media_type)
    except StorageUnavailable:
        raise SecurityError(503, "storage_unavailable", "Private storage is unavailable") from None
    reservation = (
        "insightrag_security.reserve_ingestion_force"
        if reindex
        else "insightrag_security.reserve_ingestion"
    )
    result = await session.scalar(
        text(f"SELECT {reservation}(:org,:resource,:version,:job,:hash,:key,:name,:media)"),
        {
            "org": context.organization_id,
            "resource": resource_id,
            "version": version_id,
            "job": job_id,
            "hash": validated.sha256,
            "key": key,
            "name": validated.filename,
            "media": validated.media_type,
        },
    )
    if isinstance(result, str) and result.startswith("duplicate:"):
        await store.delete(key)
        return {"state": "duplicate", "version_id": result.split(":", 1)[1]}
    if result != "created":
        await store.delete(key)
        raise not_found()
    await audit(session, context, "ingestion.queued", resource_id)
    # The durable job survives broker failure and can be redispatched by an operator.
    token = SignedJobEnvelope(settings.signed_job_key.get_secret_value().encode()).issue(
        context.organization_id, context.user_id, job_id, resource_id, context.policy_revision
    )
    background_tasks.add_task(_dispatch, settings, token)
    return {
        "state": "queued",
        "job_id": str(job_id),
        "version_id": str(version_id),
        "sha256": validated.sha256,
    }


@router.get("/ingestion-jobs/{job_id}")
async def ingestion_status(job_id: UUID, context: Context, session: Session) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    "SELECT id,resource_id,version_id,state,stage,attempts,error_code,"
                    "created_at,updated_at "
                    "FROM ingestion_jobs WHERE org_id=:org AND id=:job AND requested_by=:actor"
                ),
                {"org": context.organization_id, "job": job_id, "actor": context.user_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise not_found()
    await require_resource(session, context, row["resource_id"], "upload")
    await audit(session, context, "ingestion.status", row["resource_id"])
    return dict(row)


@router.get("/ingested-documents/{resource_id}/evidence")
async def published_evidence(
    resource_id: UUID, context: Context, session: Session
) -> list[dict[str, Any]]:
    scoped = context.for_operation("knowledge")
    await set_context(session, scoped)
    resource = await require_resource(session, scoped, resource_id, "read")
    if resource["kind"] != "document":
        raise not_found()
    rows = (
        (
            await session.execute(
                text(
                    "SELECT position,text,locator,heading,token_count FROM ingestion_chunks "
                    "WHERE org_id=:org AND resource_id=:resource ORDER BY position LIMIT 100"
                ),
                {"org": context.organization_id, "resource": resource_id},
            )
        )
        .mappings()
        .all()
    )
    await require_resource(session, scoped, resource_id, "read")
    await audit(session, context, "ingestion.evidence", resource_id)
    return [dict(row) for row in rows]


@router.get("/ingested-datasets/{resource_id}/rows")
async def published_rows(
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
                    "SELECT row_number,region,payload FROM ingestion_dataset_rows "
                    "WHERE org_id=:org AND resource_id=:resource ORDER BY row_number LIMIT 100"
                ),
                {"org": context.organization_id, "resource": resource_id},
            )
        )
        .mappings()
        .all()
    )
    await require_resource(session, scoped, resource_id, "query")
    await audit(session, context, "ingestion.dataset_rows", resource_id)
    return [dict(row) for row in rows]
