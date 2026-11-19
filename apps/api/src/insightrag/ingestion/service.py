"""Durable ingestion effects; no content is visible until one DB publication commits."""
# ruff: noqa: E501

import asyncio
import hashlib
import json
from dataclasses import replace
from uuid import uuid4

from redis.asyncio import Redis
from sqlalchemy import text

from insightrag.analytics.ingestion import validate_sales
from insightrag.core.config import Settings
from insightrag.db.session import Database
from insightrag.ingestion.chunking import chunk_segments
from insightrag.ingestion.embeddings import (
    Embedder,
    EmbeddingUnavailable,
    OpenAICompatibleEmbedder,
    validate_vectors,
)
from insightrag.ingestion.parsers import ParsedDataset, ParsedDocument, parse
from insightrag.ingestion.storage import ObjectStore, S3ObjectStore, StorageUnavailable
from insightrag.security.context import AccessContext
from insightrag.security.controls import JobClaims, SignedJobEnvelope, assert_object_scope
from insightrag.security.database import require_resource, tenant_session
from insightrag.security.dependencies import audit


def configured_store(settings: Settings) -> ObjectStore | None:
    if not all((settings.object_bucket, settings.object_region, settings.object_kms_key_id)):
        return None
    return S3ObjectStore(
        bucket=settings.object_bucket or "",
        region=settings.object_region or "",
        kms_key_id=settings.object_kms_key_id or "",
        endpoint_url=settings.object_endpoint,
    )


def configured_embedder(settings: Settings) -> Embedder | None:
    if not all((settings.embedding_endpoint, settings.embedding_api_key, settings.embedding_model)):
        return None
    return OpenAICompatibleEmbedder(
        endpoint=settings.embedding_endpoint or "",
        api_key=settings.embedding_api_key.get_secret_value(),  # type: ignore[union-attr]
        model_id=settings.embedding_model or "",
    )


async def load_context(database: Database, claims: JobClaims) -> AccessContext | None:
    preliminary = AccessContext(
        claims.user_id,
        claims.organization_id,
        "viewer",
        0,
        False,
        claims.policy_revision,
        str(uuid4()),
        purpose="administration",
    )
    async with tenant_session(database, preliminary) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT m.role,u.clearance,o.policy_revision,j.resource_id,j.state "
                        "FROM org_memberships m JOIN security_users u ON u.id=m.user_id "
                        "JOIN orgs o ON o.id=m.org_id JOIN ingestion_jobs j ON j.org_id=o.id "
                        "AND j.requested_by=u.id WHERE m.org_id=:org AND m.user_id=:user "
                        "AND m.status='active' AND u.active AND j.id=:job"
                    ),
                    {"org": claims.organization_id, "user": claims.user_id, "job": claims.job_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row["resource_id"] != claims.resource_id
            or row["state"] not in ("queued", "running", "failed")
        ):
            return None
        if row["policy_revision"] != claims.policy_revision:
            return None
        return replace(preliminary, role=row["role"], clearance=row["clearance"])


async def process_job(
    database: Database,
    claims: JobClaims,
    store: ObjectStore,
    embedder: Embedder | None,
    *,
    ocr: bool = False,
) -> str:
    context = await load_context(database, claims)
    if context is None:
        return "denied"
    async with tenant_session(database, context) as session:
        resource = await require_resource(session, context, claims.resource_id, "upload")
        row = (
            (
                await session.execute(
                    text(
                        "SELECT v.id,v.object_key,v.sha256,v.filename,j.state,j.policy_revision "
                        "FROM document_versions v JOIN ingestion_jobs j ON j.org_id=v.org_id "
                        "AND j.resource_id=v.resource_id AND j.version_id=v.id "
                        "WHERE j.org_id=:org AND j.id=:job AND j.requested_by=:actor"
                    ),
                    {"org": claims.organization_id, "job": claims.job_id, "actor": claims.user_id},
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["policy_revision"] != claims.policy_revision:
            return "denied"
        key, expected_hash, filename = row["object_key"], row["sha256"], row["filename"]
        assert_object_scope(key, claims.organization_id, resource["workspace_id"])
        await session.execute(
            text(
                "UPDATE ingestion_jobs SET state='running',stage='parsing',attempts=attempts+1,"
                "updated_at=now(),error_code=NULL WHERE org_id=:org AND id=:job "
                "AND state IN ('queued','running','failed') "
                "AND attempts<10"
            ),
            {"org": claims.organization_id, "job": claims.job_id},
        )
    data = await store.get(key, 50 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("Stored object hash mismatch")
    parsed = await asyncio.to_thread(
        parse, data, "." + filename.rsplit(".", 1)[-1].lower(), ocr=ocr
    )
    chunks = chunk_segments(parsed.segments) if isinstance(parsed, ParsedDocument) else ()
    if isinstance(parsed, ParsedDocument) and (not chunks or embedder is None):
        raise ValueError("Document has no chunks or embedding provider is unavailable")
    if chunks:
        async with tenant_session(database, context) as progress:
            await progress.execute(
                text(
                    "UPDATE ingestion_jobs SET stage='embedding',updated_at=now() "
                    "WHERE org_id=:org AND id=:job AND state='running'"
                ),
                {"org": claims.organization_id, "job": claims.job_id},
            )
    vectors = await embedder.embed([chunk.text for chunk in chunks]) if chunks and embedder else []
    if len(vectors) != len(chunks):
        raise ValueError("Embedding count mismatch")
    if chunks:
        validate_vectors(vectors, len(chunks), 1536)
    async with tenant_session(database, context) as session:
        await require_resource(session, context, claims.resource_id, "upload")
        await session.execute(
            text(
                "UPDATE ingestion_jobs SET stage='indexing',updated_at=now() "
                "WHERE org_id=:org AND id=:job AND state='running'"
            ),
            {"org": claims.organization_id, "job": claims.job_id},
        )
        revision = await session.scalar(
            text("SELECT insightrag_security.lock_member_policy_revision(:org)"),
            {"org": claims.organization_id},
        )
        if revision != claims.policy_revision:
            return "stale"
        if isinstance(parsed, ParsedDocument):
            for position, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
                await session.execute(
                    text(
                        "INSERT INTO ingestion_chunks(org_id,resource_id,version_id,position,text,"
                        "locator,heading,token_count,embedding) "
                        "VALUES(:org,:resource,:version,:position,"
                        ":body,:locator,:heading,:tokens,CAST(:vector AS vector))"
                    ),
                    {
                        "org": claims.organization_id,
                        "resource": claims.resource_id,
                        "version": row["id"],
                        "position": position,
                        "body": chunk.text,
                        "locator": chunk.locator,
                        "heading": chunk.heading,
                        "tokens": chunk.token_count,
                        "vector": str(vector),
                    },
                )
        elif isinstance(parsed, ParsedDataset):
            if "region" not in parsed.columns or not parsed.rows:
                raise ValueError("Dataset requires region column and at least one row")
            sales_rows = validate_sales(parsed)
            for number, item in enumerate(parsed.rows, 2):
                region = item["region"]
                if not isinstance(region, str) or not 1 <= len(region) <= 128:
                    raise ValueError("Dataset has invalid region")
                await session.execute(
                    text(
                        "INSERT INTO ingestion_dataset_rows(org_id,resource_id,version_id,"
                        "row_number,region,payload) "
                        "VALUES(:org,:resource,:version,:number,:region,CAST(:payload AS jsonb))"
                    ),
                    {
                        "org": claims.organization_id,
                        "resource": claims.resource_id,
                        "version": row["id"],
                        "number": number,
                        "region": region,
                        "payload": json.dumps(item),
                    },
                )
            if sales_rows is not None:
                for sale in sales_rows:
                    await session.execute(
                        text(
                            "INSERT INTO analytics_sales_rows(org_id,resource_id,version_id,row_number,"
                            "transaction_id,transaction_date,region,product,revenue,cost,units,returned_units,currency) "
                            "VALUES(:org,:resource,:version,:row_number,:transaction_id,:transaction_date,"
                            ":region,:product,:revenue,:cost,:units,:returns,:currency)"
                        ),
                        {
                            "org": claims.organization_id,
                            "resource": claims.resource_id,
                            "version": row["id"],
                            "row_number": sale.row_number,
                            "transaction_id": sale.transaction_id,
                            "transaction_date": sale.transaction_date,
                            "region": sale.region,
                            "product": sale.product,
                            "revenue": sale.revenue,
                            "cost": sale.cost,
                            "units": sale.units,
                            "returns": sale.returns,
                            "currency": sale.currency,
                        },
                    )
        result = await session.scalar(
            text("SELECT insightrag_security.publish_ingestion(:org,:job,:model)"),
            {
                "org": claims.organization_id,
                "job": claims.job_id,
                "model": embedder.model_id if embedder else None,
            },
        )
        if result != "published":
            raise ValueError("Ingestion publication denied or incomplete")
        await audit(session, context, "ingestion.published", claims.resource_id)
    return "published"


async def run_ingestion_job(token: str, settings: Settings) -> dict[str, str]:
    if not settings.signed_job_key or not settings.redis_url:
        raise RuntimeError("Signed worker identity is unavailable")
    store = configured_store(settings)
    if store is None:
        raise RuntimeError("Object storage is unavailable")
    envelope = SignedJobEnvelope(settings.signed_job_key.get_secret_value().encode())
    claims = envelope.verify(token)
    database = Database(settings)
    redis = Redis.from_url(
        settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
    )
    try:
        if await load_context(database, claims) is None:
            return {"state": "denied"}
        await envelope.verify_once(token, redis)
        embedder = configured_embedder(settings)
        for attempt in range(3):
            try:
                state = await process_job(
                    database, claims, store, embedder, ocr=settings.ingestion_ocr_enabled
                )
                return {"state": state}
            except (StorageUnavailable, EmbeddingUnavailable):
                if attempt < 2:
                    await asyncio.sleep(2**attempt)
                    continue
                code = "dependency_unavailable"
            except Exception:
                code = "processing_failed"
            context = await load_context(database, claims)
            if context is not None:
                async with tenant_session(database, context) as session:
                    await session.execute(
                        text(
                            "UPDATE ingestion_jobs SET state='failed',stage='failed',"
                            "error_code=:code,updated_at=now() WHERE org_id=:org AND id=:job "
                            "AND state IN ('queued','running')"
                        ),
                        {"code": code, "org": claims.organization_id, "job": claims.job_id},
                    )
            return {"state": "failed"}
        return {"state": "failed"}
    finally:
        await redis.aclose()
        await database.close()
