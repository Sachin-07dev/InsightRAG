"""Versioned request/response contracts for document RAG."""

from uuid import UUID

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    workspace_id: UUID
    question: str = Field(min_length=3, max_length=2048)
    resource_ids: list[UUID] = Field(default_factory=list, max_length=32)
    conversation_id: UUID | None = None
    use_mmr: bool = False
    max_context_tokens: int | None = Field(default=None, ge=64, le=12000)
    max_completion_tokens: int | None = Field(default=None, ge=64, le=4096)


class Citation(BaseModel):
    id: str
    resource_id: UUID
    workspace_id: UUID
    document_title: str
    version_id: UUID
    version_number: int
    locator: str
    chunk_position: int
    excerpt: str


class QueryResponse(BaseModel):
    conversation_id: UUID | None
    answer: str
    citations: list[Citation]
    uncertainty: str | None = None
    status: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
