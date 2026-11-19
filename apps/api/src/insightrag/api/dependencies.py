"""Small request-scoped dependency; verified identity arrives in Phase 3."""

from fastapi import Request


def get_request_id(request: Request) -> str:
    return str(request.state.request_id)
