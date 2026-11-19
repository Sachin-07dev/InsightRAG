"""Database-side ACL filtering before candidate materialization."""
# ruff: noqa: E501

import json
from time import perf_counter
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from insightrag.retrieval.ranking import Candidate
from insightrag.security.context import AccessContext, not_found
from insightrag.security.database import require_resource


async def validate_scope(
    session: AsyncSession, context: AccessContext, workspace_id: UUID, resource_ids: list[UUID]
) -> None:
    member = await session.scalar(
        text(
            "SELECT 1 FROM workspace_memberships WHERE org_id=:org AND workspace_id=:workspace AND user_id=:user"
        ),
        {"org": context.organization_id, "workspace": workspace_id, "user": context.user_id},
    )
    if not member:
        raise not_found()
    for resource_id in resource_ids:
        resource = await require_resource(session, context, resource_id, "read")
        if resource["workspace_id"] != workspace_id or resource["kind"] != "document":
            raise not_found()


def _candidate(row: dict[str, object], channel: str) -> Candidate:
    vector = row.get("vector_text")
    embedding = tuple(json.loads(str(vector))) if vector is not None else None
    return Candidate(
        resource_id=UUID(str(row["resource_id"])),
        version_id=UUID(str(row["version_id"])),
        position=int(str(row["position"])),
        title=str(row["title"]),
        version_number=int(str(row["version_number"])),
        workspace_id=UUID(str(row["workspace_id"])),
        text=str(row["text"]),
        locator=str(row["locator"]),
        heading=str(row["heading"]) if row["heading"] is not None else None,
        embedding=embedding,
        distance=float(str(row["score"])) if channel == "dense" else None,
        sparse_score=float(str(row["score"])) if channel == "sparse" else None,
        channels=(channel,),
    )


_BASE = """FROM ingestion_chunks c
JOIN resources r ON r.org_id=c.org_id AND r.id=c.resource_id AND r.active_version=c.version_id
JOIN document_versions v ON v.org_id=c.org_id AND v.resource_id=c.resource_id AND v.id=c.version_id
WHERE c.org_id=:org AND r.workspace_id=:workspace AND r.kind='document' AND r.state='active'
  AND v.state='published' AND v.model_id=:model
  AND (:all_resources OR c.resource_id = ANY(CAST(:resources AS uuid[])))
  AND insightrag_security.can_resource(c.org_id,c.resource_id,'read')"""


async def retrieve(
    session: AsyncSession,
    context: AccessContext,
    workspace_id: UUID,
    resource_ids: list[UUID],
    query: str,
    vector: list[float],
    model_id: str,
    *,
    dense_k: int,
    sparse_k: int,
    include_vectors: bool = False,
    timings: dict[str, float] | None = None,
) -> tuple[list[Candidate], list[Candidate]]:
    params = {
        "org": context.organization_id,
        "workspace": workspace_id,
        "resources": [str(value) for value in resource_ids],
        "all_resources": not resource_ids,
        "model": model_id,
        "query": query,
        "vector": "[" + ",".join(str(value) for value in vector) + "]",
    }
    columns = (
        "c.resource_id,c.version_id,c.position,c.text,c.locator,c.heading,"
        "r.title,r.workspace_id,v.version_number,"
        + ("c.embedding::text AS vector_text," if include_vectors else "NULL::text AS vector_text,")
    )
    stage_started = perf_counter()
    dense = (
        (
            await session.execute(
                text(
                    "SELECT "
                    + columns
                    + " c.embedding <=> CAST(:vector AS vector) AS score "
                    + _BASE
                    + " AND c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:vector AS vector),"
                    " c.resource_id,c.version_id,c.position LIMIT :limit"
                ),
                {**params, "limit": dense_k},
            )
        )
        .mappings()
        .all()
    )
    if timings is not None:
        timings["dense_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    stage_started = perf_counter()
    sparse = (
        (
            await session.execute(
                text(
                    "SELECT "
                    + columns
                    + " ts_rank_cd(to_tsvector('english',c.text),websearch_to_tsquery('english',:query)) AS score "
                    + _BASE
                    + " AND to_tsvector('english',c.text) @@ websearch_to_tsquery('english',:query)"
                    " ORDER BY score DESC,c.resource_id,c.version_id,c.position LIMIT :limit"
                ),
                {**params, "limit": sparse_k},
            )
        )
        .mappings()
        .all()
    )
    if timings is not None:
        timings["sparse_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    return (
        [_candidate(dict(row), "dense") for row in dense],
        [_candidate(dict(row), "sparse") for row in sparse],
    )


async def revalidate_evidence(
    session: AsyncSession, context: AccessContext, items: list[Candidate]
) -> bool:
    for item in items:
        row = (
            await session.execute(
                text("""SELECT c.text FROM ingestion_chunks c JOIN resources r
                      ON r.org_id=c.org_id AND r.id=c.resource_id AND r.active_version=c.version_id
                      WHERE c.org_id=:org AND c.resource_id=:resource AND c.version_id=:version
                      AND c.position=:position AND r.state='active' AND
                      insightrag_security.can_resource(c.org_id,c.resource_id,'read')"""),
                {
                    "org": context.organization_id,
                    "resource": item.resource_id,
                    "version": item.version_id,
                    "position": item.position,
                },
            )
        ).scalar_one_or_none()
        if row != item.text:
            return False
    return True
