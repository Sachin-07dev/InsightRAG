# ruff: noqa: E501
"""Short-lived scoped retrieval and post-generation evidence revalidation."""

import json
import logging
from time import perf_counter
from uuid import uuid4

from sqlalchemy import text

from insightrag.core.config import Settings
from insightrag.db.session import Database
from insightrag.ingestion.embeddings import Embedder, EmbeddingUnavailable, validate_vectors
from insightrag.retrieval.context import assemble_context, verify_citations
from insightrag.retrieval.contracts import Citation, QueryRequest, QueryResponse
from insightrag.retrieval.provider import GenerationUnavailable, Generator
from insightrag.retrieval.query import prepare_query, resolve_followup
from insightrag.retrieval.ranking import maximal_marginal_relevance, reciprocal_rank_fusion
from insightrag.retrieval.repository import retrieve, revalidate_evidence, validate_scope
from insightrag.retrieval.rerank import Reranker, RerankUnavailable
from insightrag.security.context import AccessContext, SecurityError, not_found
from insightrag.security.database import tenant_session
from insightrag.security.dependencies import audit

logger = logging.getLogger(__name__)


async def answer_query(
    database: Database,
    access: AccessContext,
    request: QueryRequest,
    settings: Settings,
    embedder: Embedder | None,
    generator: Generator | None,
    reranker: Reranker | None = None,
) -> QueryResponse:
    started = perf_counter()
    timings: dict[str, float] = {}
    context = access.for_operation("knowledge", request.workspace_id)
    try:
        prepared = prepare_query(request.question)
    except ValueError:
        raise SecurityError(422, "invalid_query", "Query validation failed") from None
    async with tenant_session(database, context) as session:
        await validate_scope(session, context, request.workspace_id, request.resource_ids)
        previous = None
        if request.conversation_id:
            conversation = await session.scalar(
                text("""SELECT id FROM rag_conversations WHERE org_id=:org AND id=:conversation
                  AND workspace_id=:workspace AND owner_id=:user"""),
                {
                    "org": context.organization_id,
                    "conversation": request.conversation_id,
                    "workspace": request.workspace_id,
                    "user": context.user_id,
                },
            )
            if conversation is None:
                raise not_found()
            previous = await session.scalar(
                text("""SELECT question FROM rag_turns WHERE org_id=:org AND conversation_id=:conversation
                  ORDER BY created_at DESC,id DESC LIMIT 1"""),
                {"org": context.organization_id, "conversation": request.conversation_id},
            )
    if prepared.kind == "analytics":
        return QueryResponse(
            conversation_id=request.conversation_id,
            answer="This question requires the authorized structured analytics engine.",
            citations=[],
            uncertainty="Exact calculations are unavailable in document retrieval.",
            status="analytics_required",
        )
    retrieval_query = resolve_followup(prepared.normalized, previous)
    if embedder is None:
        raise SecurityError(503, "embedding_unavailable", "Query embedding is not configured")
    stage_started = perf_counter()
    try:
        vectors = await embedder.embed([retrieval_query])
        validate_vectors(vectors, 1, 1536)
    except EmbeddingUnavailable:
        raise SecurityError(
            503, "embedding_unavailable", "Query embedding is unavailable"
        ) from None
    vector = vectors[0]
    timings["embedding_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    async with tenant_session(database, context) as session:
        await validate_scope(session, context, request.workspace_id, request.resource_ids)
        dense, sparse = await retrieve(
            session,
            context,
            request.workspace_id,
            request.resource_ids,
            retrieval_query,
            vector,
            embedder.model_id,
            dense_k=settings.retrieval_dense_k,
            sparse_k=settings.retrieval_sparse_k,
            include_vectors=request.use_mmr,
            timings=timings,
        )
    if settings.retrieval_max_cosine_distance is not None:
        dense = [
            item
            for item in dense
            if item.distance is not None and item.distance <= settings.retrieval_max_cosine_distance
        ]
    stage_started = perf_counter()
    candidates = reciprocal_rank_fusion(dense, sparse, limit=settings.retrieval_fusion_k)
    timings["fusion_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    if reranker:
        stage_started = perf_counter()
        try:
            reranked = await reranker.rerank(
                retrieval_query, candidates[: settings.retrieval_rerank_k]
            )
            candidates = reranked + candidates[settings.retrieval_rerank_k :]
        except RerankUnavailable:
            logger.warning("rag.rerank.fallback")
        timings["rerank_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    if request.use_mmr:
        candidates = maximal_marginal_relevance(
            candidates, tuple(vector), limit=settings.retrieval_context_k, weight=0.7
        )
    stage_started = perf_counter()
    evidence, prompt_context = assemble_context(
        context.organization_id,
        candidates,
        max_tokens=min(
            settings.retrieval_context_tokens,
            request.max_context_tokens or settings.retrieval_context_tokens,
        ),
        limit=settings.retrieval_context_k,
    )
    timings["context_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    if not evidence:
        return QueryResponse(
            conversation_id=request.conversation_id,
            answer="I could not find enough authorized evidence to answer.",
            citations=[],
            uncertainty="No relevant published document evidence was available.",
            status="abstained",
        )
    if generator is None:
        raise SecurityError(503, "generation_unavailable", "Answer generation is not configured")
    stage_started = perf_counter()
    try:
        completion = await generator.generate(prepared.normalized, prompt_context)
    except GenerationUnavailable:
        raise SecurityError(
            503, "generation_unavailable", "Answer generation is unavailable"
        ) from None
    timings["generation_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    cited = completion.draft.citation_ids
    if cited and not verify_citations(cited, evidence):
        raise SecurityError(502, "citation_invalid", "Generated citations failed verification")
    if not cited:
        answer, status = "I cannot verify an answer from the available evidence.", "abstained"
    else:
        answer, status = completion.draft.answer, "answered"
    by_id = {item.citation_id: item for item in evidence}
    citations = [
        Citation(
            id=label,
            resource_id=by_id[label].candidate.resource_id,
            workspace_id=by_id[label].candidate.workspace_id,
            document_title=by_id[label].candidate.title,
            version_id=by_id[label].candidate.version_id,
            version_number=by_id[label].candidate.version_number,
            locator=by_id[label].candidate.locator,
            chunk_position=by_id[label].candidate.position,
            excerpt=by_id[label].excerpt,
        )
        for label in dict.fromkeys(cited)
    ]
    stage_started = perf_counter()
    async with tenant_session(database, context) as session:
        await validate_scope(session, context, request.workspace_id, request.resource_ids)
        if not await revalidate_evidence(session, context, [item.candidate for item in evidence]):
            raise SecurityError(409, "evidence_changed", "Evidence or access changed; retry")
        revision = await session.scalar(
            text("SELECT insightrag_security.lock_member_policy_revision(:org)"),
            {"org": context.organization_id},
        )
        if revision != context.policy_revision:
            raise SecurityError(409, "authorization_changed", "Authorization changed; retry")
        conversation_id = request.conversation_id or uuid4()
        if request.conversation_id is None:
            await session.execute(
                text("""INSERT INTO rag_conversations(org_id,id,workspace_id,owner_id)
                  VALUES(:org,:id,:workspace,:user)"""),
                {
                    "org": context.organization_id,
                    "id": conversation_id,
                    "workspace": request.workspace_id,
                    "user": context.user_id,
                },
            )
        await session.execute(
            text("""INSERT INTO rag_turns(org_id,conversation_id,id,question,outcome,citation_refs)
              VALUES(:org,:conversation,:id,:question,:outcome,CAST(:refs AS jsonb))"""),
            {
                "org": context.organization_id,
                "conversation": conversation_id,
                "id": uuid4(),
                "question": prepared.normalized,
                # Persist no generated answer or source excerpt: deletion must not
                # leave copied document content in conversation history.
                "outcome": status,
                "refs": json.dumps(
                    [
                        {
                            "id": item.id,
                            "resource_id": str(item.resource_id),
                            "version_id": str(item.version_id),
                            "chunk_position": item.chunk_position,
                        }
                        for item in citations
                    ]
                ),
            },
        )
        await audit(session, context, "rag.query")
    timings["recheck_ms"] = round((perf_counter() - stage_started) * 1000, 2)
    logger.info(
        {
            "event": "rag_query_completed",
            "candidate_count": len(candidates),
            "citation_count": len(citations),
            "rag_status": status,
            "duration_ms": round((perf_counter() - started) * 1000),
            "prompt_tokens": completion.prompt_tokens,
            "completion_tokens": completion.completion_tokens,
            **timings,
        },
    )
    return QueryResponse(
        conversation_id=conversation_id,
        answer=answer,
        citations=citations,
        uncertainty=completion.draft.uncertainty if cited else "Evidence was insufficient.",
        status=status,
        prompt_tokens=completion.prompt_tokens,
        completion_tokens=completion.completion_tokens,
    )
