import time
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request

from seekbell.api.auth import require_admin
from seekbell.services.overview import overview

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


def snapshot_time():
    return time.time()


@router.get("/overview")
def get_overview(
    request: Request,
    at: Annotated[float, Depends(snapshot_time)],
    range: Literal["24h", "7d"] = "24h",
):
    return overview(request.app.state.engine, range, at=at)
