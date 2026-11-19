"""Versioned analytics API contracts; values are decimal strings, never floats."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyticsRequest(BaseModel):
    resource_id: UUID
    question: str = Field(min_length=3, max_length=1000)
    region: str | None = Field(default=None, min_length=1, max_length=128)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    year: int | None = Field(default=None, ge=1900, le=2100)
    comparison_year: int | None = Field(default=None, ge=1900, le=2100)


class AnalyticsRow(BaseModel):
    dimension: str
    value: str | None
    comparison_value: str | None = None
    growth_percent: str | None = None
    source_rows: int
    source_row_min: int | None = None
    source_row_max: int | None = None


class AnalyticsResponse(BaseModel):
    status: Literal["answered"] = "answered"
    metric: str
    definition: str
    metric_definition_version: str
    unit: str
    reporting_timezone: str
    period_start: str
    period_end_exclusive: str
    filters: dict[str, str]
    resource_id: UUID
    version_id: UUID
    version_number: int
    source_sha256: str
    rows: list[AnalyticsRow]
    notes: list[str]


class AnalyticsSchema(BaseModel):
    resource_id: UUID
    version_id: UUID
    columns: dict[str, str]
    metrics: dict[str, str]
    metric_definition_version: str
    reporting_timezone: str
