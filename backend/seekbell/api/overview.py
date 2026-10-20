import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from seekbell.api.auth import require_admin
from seekbell.services.overview import overview
from seekbell.services.runtime import status as runtime_status

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


def snapshot_time():
    return time.time()


@router.get("/overview")
def get_overview(
    request: Request,
    at: Annotated[float, Depends(snapshot_time)],
    range: Literal["24h", "7d"] = "24h",
):
    result = overview(request.app.state.engine, range, at=at)
    result["runtime"] = runtime_status(request)
    result["runtime_active"] = result["runtime"]["active"]
    return result
