from importlib.metadata import version
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from seekbell.db.runtime import database_ready, schema_revision

router = APIRouter()


class VersionInfo(BaseModel):
    name: Literal["SeekBell"] = "SeekBell"
    version: str
    build_revision: str
    database_revision: str | None


@router.get("/api/version", response_model=VersionInfo)
def get_version(request: Request) -> VersionInfo:
    return VersionInfo(
        version=version("seekbell"),
        build_revision=request.app.state.settings.build_revision,
        database_revision=schema_revision(request.app.state.engine),
    )


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(request: Request) -> JSONResponse:
    try:
        healthy = database_ready(request.app.state.engine) and request.app.state.runtime.healthy
    except SQLAlchemyError:
        healthy = False
    return JSONResponse(
        {"status": "ok" if healthy else "unavailable"}, status_code=200 if healthy else 503
    )
