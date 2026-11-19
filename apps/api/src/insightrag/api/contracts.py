"""Public foundation contracts; protected data routes require enterprise identity."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlatformInfo(Contract):
    service: str = "InsightRAG Enterprise"
    version: str = "0.1.0"
    phase: Literal[3] = 3
    tenant_data_enabled: Literal[True] = True


class EchoRequest(Contract):
    message: str = Field(min_length=1, max_length=128, strict=True)


class EchoResponse(Contract):
    message: str
    request_id: str


class Liveness(Contract):
    status: Literal["ok"] = "ok"


DependencyStatus = Literal["ok", "unavailable", "timeout", "not_configured"]


class Readiness(Contract):
    status: Literal["ready", "not_ready"]
    dependencies: dict[str, DependencyStatus]


class ValidationIssue(Contract):
    location: list[str]
    kind: str


class ErrorResponse(Contract):
    code: str
    message: str
    request_id: str
    issues: list[ValidationIssue] = Field(default_factory=list)
