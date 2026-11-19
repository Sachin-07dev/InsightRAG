"""Authenticated document-question API; no client-provided identity is trusted."""
# ruff: noqa: E501

from fastapi import APIRouter, Request

from insightrag.ingestion.embeddings import OpenAICompatibleEmbedder
from insightrag.retrieval.contracts import QueryRequest, QueryResponse
from insightrag.retrieval.provider import CompatibleChatGenerator
from insightrag.retrieval.rerank import CompatibleReranker
from insightrag.retrieval.service import answer_query
from insightrag.security.dependencies import Context

router = APIRouter(prefix="/api/v1/rag", tags=["retrieval"])


@router.post("/query", response_model=QueryResponse)
async def query(body: QueryRequest, request: Request, context: Context) -> QueryResponse:
    settings = request.app.state.settings
    embedder = (
        OpenAICompatibleEmbedder(
            endpoint=settings.embedding_endpoint,
            api_key=settings.embedding_api_key.get_secret_value(),
            model_id=settings.embedding_model,
        )
        if settings.embedding_endpoint and settings.embedding_api_key and settings.embedding_model
        else None
    )
    generator = (
        CompatibleChatGenerator(
            endpoint=settings.generation_endpoint,
            api_key=settings.generation_api_key.get_secret_value(),
            model=settings.generation_model,
            temperature=settings.generation_temperature,
            max_completion_tokens=min(
                settings.generation_max_completion_tokens,
                body.max_completion_tokens or settings.generation_max_completion_tokens,
            ),
        )
        if settings.generation_endpoint
        and settings.generation_api_key
        and settings.generation_model
        else None
    )
    reranker = (
        CompatibleReranker(
            settings.rerank_endpoint,
            settings.rerank_api_key.get_secret_value(),
            settings.rerank_model,
        )
        if settings.rerank_endpoint and settings.rerank_api_key and settings.rerank_model
        else None
    )
    return await answer_query(
        request.app.state.database, context, body, settings, embedder, generator, reranker
    )
