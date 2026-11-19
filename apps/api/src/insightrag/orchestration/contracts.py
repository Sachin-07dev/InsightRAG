"""External contracts for the Phase 7 query graph."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from insightrag.analytics.contracts import AnalyticsResponse
from insightrag.retrieval.contracts import QueryResponse


class OrchestrationRequest(BaseModel):
    workspace_id: UUID
    question: str = Field(min_length=3, max_length=1000)
    document_resource_ids: list[UUID] = Field(default_factory=list, max_length=32)
    dataset_id: UUID | None = None
    document_question: str | None = Field(default=None, min_length=3, max_length=1000)
    analytics_question: str | None = Field(default=None, min_length=3, max_length=1000)
    conversation_id: UUID | None = None
    region: str | None = Field(default=None, min_length=1, max_length=128)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    year: int | None = Field(default=None, ge=1900, le=2100)
    comparison_year: int | None = Field(default=None, ge=1900, le=2100)
    chart: bool = False
    max_context_tokens: int | None = Field(default=None, ge=64, le=12000)
    max_completion_tokens: int | None = Field(default=None, ge=64, le=4096)

    @model_validator(mode="after")
    def validate_scope(self) -> "OrchestrationRequest":
        if self.document_question and not self.document_resource_ids:
            raise ValueError("Document question requires document resources")
        if self.analytics_question and self.dataset_id is None:
            raise ValueError("Analytics question requires a dataset")
        if self.chart and self.dataset_id is None:
            raise ValueError("A chart requires a governed dataset")
        return self


class RouteDecision(BaseModel):
    route: Literal["document", "analytics", "hybrid", "clarification"]
    reason: str = Field(max_length=200)


class ChartSeries(BaseModel):
    name: str
    values: list[str | None]


class ChartSpecification(BaseModel):
    kind: Literal["bar", "line"]
    title: str
    categories: list[str]
    series: list[ChartSeries]
    unit: str
    metric_definition_version: str
    dataset_version_id: UUID


class OrchestrationResponse(BaseModel):
    status: Literal["answered", "partial", "clarification", "abstained"]
    route: Literal["document", "analytics", "hybrid", "clarification"]
    answer: str
    document: QueryResponse | None = None
    analytics: AnalyticsResponse | None = None
    chart: ChartSpecification | None = None
    uncertainty: str | None = None
    executed_nodes: list[str]
