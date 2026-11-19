from typing import Annotated

from fastapi import APIRouter, Depends

from insightrag.api.contracts import EchoRequest, EchoResponse, PlatformInfo
from insightrag.api.dependencies import get_request_id

router = APIRouter(prefix="/api/v1")
diagnostics_router = APIRouter(prefix="/api/v1/diagnostics", tags=["development diagnostics"])


@router.get("/meta", response_model=PlatformInfo, tags=["platform"])
async def metadata() -> PlatformInfo:
    return PlatformInfo()


@diagnostics_router.post("/echo", response_model=EchoResponse)
async def echo(
    payload: EchoRequest, request_id: Annotated[str, Depends(get_request_id)]
) -> EchoResponse:
    """Contract demonstration only; never registered in production."""
    return EchoResponse(message=payload.message, request_id=request_id)
