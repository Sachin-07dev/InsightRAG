"""Public visualization contracts; clients never supply authoritative values."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ViewQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=1000)
    kind: Literal["auto", "line", "bar", "stacked", "scatter", "table", "geo", "kpi"] = "auto"
    region: str | None = Field(default=None, min_length=1, max_length=128)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    year: int | None = Field(default=None, ge=1900, le=2100)
    comparison_year: int | None = Field(default=None, ge=1900, le=2100)


class DashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    dataset_id: UUID
    views: list[ViewQuery] = Field(min_length=1, max_length=8)


class SourceReference(BaseModel):
    resource_id: UUID
    version_id: UUID
    version_number: int
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    metric_definition_version: str


class ViewPoint(BaseModel):
    label: str
    value: str | None
    source_rows: int = Field(ge=0)


class BusinessInsight(BaseModel):
    kind: Literal["verified_observation", "hypothesis", "recommendation"]
    text: str = Field(min_length=1, max_length=300)


class ViewSpecification(BaseModel):
    kind: Literal["line", "bar", "table", "kpi"]
    metric: str
    definition: str
    unit: str
    period_start: str
    period_end_exclusive: str
    reporting_timezone: str
    filters: dict[str, str]
    points: list[ViewPoint]
    source: SourceReference
    insights: list[BusinessInsight]


class DashboardCard(BaseModel):
    question: str
    view: ViewSpecification


class DashboardResponse(BaseModel):
    status: Literal["answered"] = "answered"
    cards: list[DashboardCard]
