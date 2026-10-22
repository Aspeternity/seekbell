import asyncio
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from seekbell.api.auth import require_admin
from seekbell.notifiers.preview import telegram_preview
from seekbell.services.display import get_display
from seekbell.services.history import History
from seekbell.services.manual_sending import MissingSend, preview
from seekbell.services.target_testing import OperationConflict

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


class SendInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    request_id: UUID
    revision: int = Field(ge=1, strict=True)


def services(request: Request):
    return request.app.state.target_testing, request.app.state.manual_sending


Services = Annotated[tuple, Depends(services)]


class MessagePreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    include_summary: bool = True
    summary_limit: int = Field(default=160, ge=0, le=1000)


@router.get("/notification-preview/telegram")
def telegram_message_preview(values: Annotated[MessagePreviewInput, Query()], request: Request):
    return telegram_preview(
        get_display(request.app.state.engine)["timezone"],
        include_summary=values.include_summary,
        summary_limit=values.summary_limit,
    )


@router.get("/targets/{key}/test-preview")
def target_preview(key: str, request: Request):
    return preview(request.app.state.engine, key)


@router.get("/deliveries/{key}/resend-preview")
def resend_preview(key: str, request: Request):
    return preview(request.app.state.engine, key, manual=True)


async def execute(request, sender, key, values):
    gate: asyncio.Semaphore = request.app.state.sending_gate
    if gate.locked():
        raise HTTPException(429, "已有通知操作正在进行，请稍后重试。", headers={"Retry-After": "2"})
    async with gate:
        return await sender.run(key, key=str(values.request_id), revision=values.revision)


@router.post("/targets/{key}/test")
async def test_target(key: str, values: SendInput, request: Request, senders: Services):
    result = await execute(request, senders[0], key, values)
    return History(request.app.state.engine).get_test(result)


@router.post("/deliveries/{key}/resend")
async def resend(key: str, values: SendInput, request: Request, senders: Services):
    result = await execute(request, senders[1], key, values)
    return History(request.app.state.engine).get_manual(result)


def install_errors(app):
    from fastapi.responses import JSONResponse

    @app.exception_handler(MissingSend)
    async def missing(request: Request, error: MissingSend):
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(OperationConflict)
    async def conflict(request: Request, error: OperationConflict):
        return JSONResponse({"detail": str(error)}, status_code=409)
