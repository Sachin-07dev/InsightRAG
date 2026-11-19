"""Server-derived context is not a client-controlled authorization credential."""

from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID

Action = Literal["read", "query", "upload", "delete", "manage"]


@dataclass(frozen=True, slots=True)
class AccessContext:
    user_id: UUID
    organization_id: UUID
    role: str
    clearance: int
    mfa: bool
    policy_revision: int
    request_id: str
    workspace_id: UUID | None = None
    purpose: str = "administration"

    def for_operation(self, purpose: str, workspace_id: UUID | None = None) -> "AccessContext":
        if purpose not in {"administration", "knowledge", "analytics", "deletion"}:
            raise ValueError("Unknown server operation purpose")
        return replace(self, purpose=purpose, workspace_id=workspace_id)


class SecurityError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


def not_found() -> SecurityError:
    return SecurityError(404, "resource_not_found", "Resource is unavailable")
