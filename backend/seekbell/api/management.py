import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool

from seekbell.api.auth import require_administrator
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate, explain
from seekbell.notifiers.configs import channel_schemas
from seekbell.notifiers.credentials import CredentialError
from seekbell.services.collection import SourceBusy
from seekbell.services.configuration import Configuration, ConfigurationConflict
from seekbell.services.delivery_records import DeliveryRecords
from seekbell.services.explicit_sending import SendConflict, SendNotFound
from seekbell.services.management import Management

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_administrator)])


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TargetInput(Input):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["telegram", "bark", "smtp", "webhook"]
    config: dict = Field(default_factory=dict, repr=False, max_length=32)
    enabled: bool = False


class TargetUpdate(Input):
    name: str = Field(min_length=1, max_length=200)
    config: dict = Field(default_factory=dict, repr=False, max_length=32)
    expected_revision: int = Field(ge=1)


class EnabledInput(Input):
    enabled: bool


class TaskInput(Input):
    name: str = Field(min_length=1, max_length=200)
    rule: Rule
    target_ids: list[str] = Field(min_length=1, max_length=64)
    website_id: Literal["nodeseek"] = "nodeseek"
    enabled: bool = True


class TaskUpdate(Input):
    name: str = Field(min_length=1, max_length=200)
    rule: Rule
    target_ids: list[str] = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=1)


class SampleFields(PostFields):
    title: str = Field(default="", max_length=8192)
    summary: str | None = Field(default=None, max_length=65536)
    author: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=500)


class PreviewInput(Input):
    rule: Rule
    sample: SampleFields | None = None


class HistoryInput(Input):
    rule: Rule
    limit: int = Field(default=20, ge=1, le=100)


def configuration(request: Request) -> Configuration:
    return request.app.state.configuration


def management(request: Request) -> Management:
    return Management(request.app.state.engine)


def mutate(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except ConfigurationConflict:
        raise HTTPException(409, "配置已被修改，请重新打开编辑后重试。") from None
    except CredentialError:
        raise HTTPException(503, "凭据不可用，请检查原始密钥。") from None
    except ValueError as error:
        # validate_config only supplies allowlisted field names, never rejected values.
        message = "配置无效，请检查名称、规则和通知目标。"
        if str(error).startswith("Invalid notification fields: "):
            fields = str(error).removeprefix("Invalid notification fields: ")
            message = "通知配置字段无效：" + fields
        raise HTTPException(422, message) from None


def target(request: Request, key: str) -> dict:
    try:
        view = configuration(request).get_target(key)
        return {**view, "duplicate_ids": configuration(request).duplicate_targets(key)}
    except CredentialError:
        raise HTTPException(503, "凭据不可用，请检查原始密钥。") from None
    except ValueError:
        raise HTTPException(404, "通知目标不存在。") from None


def task(request: Request, key: str) -> dict:
    view = management(request).task(key)
    if view is None:
        raise HTTPException(404, "监控任务不存在。")
    return view


@router.get("/channels")
def channels():
    return channel_schemas()


@router.get("/targets")
def targets(request: Request):
    return mutate(configuration(request).list_targets)


@router.get("/targets/{key}")
def get_target(request: Request, key: str):
    return target(request, key)


@router.post("/targets", status_code=201)
def create_target(request: Request, body: TargetInput):
    key = mutate(
        configuration(request).create_target,
        body.name,
        kind=body.kind,
        config=body.config,
        enabled=body.enabled,
    )
    return target(request, key)


@router.put("/targets/{key}")
def update_target(request: Request, key: str, body: TargetUpdate):
    target(request, key)
    mutate(
        configuration(request).update_target,
        key,
        name=body.name,
        config=body.config,
        expected_revision=body.expected_revision,
    )
    return target(request, key)


@router.put("/targets/{key}/enabled")
def target_enabled(request: Request, key: str, body: EnabledInput):
    target(request, key)
    mutate(configuration(request).set_target_enabled, key, body.enabled)
    return target(request, key)


@router.get("/tasks")
def tasks(request: Request):
    return management(request).tasks()


@router.get("/tasks/{key}")
def get_task(request: Request, key: str):
    return task(request, key)


@router.post("/tasks", status_code=201)
def create_task(request: Request, body: TaskInput):
    key = mutate(
        configuration(request).create_task,
        body.name,
        body.rule,
        body.target_ids,
        website_id=body.website_id,
        enabled=body.enabled,
        at=time.time(),
    )
    return task(request, key)


@router.put("/tasks/{key}")
def update_task(request: Request, key: str, body: TaskUpdate):
    task(request, key)
    mutate(
        configuration(request).update_task,
        key,
        body.name,
        body.rule,
        body.target_ids,
        expected_version=body.expected_version,
        at=time.time(),
    )
    return task(request, key)


@router.put("/tasks/{key}/enabled")
def task_enabled(request: Request, key: str, body: EnabledInput):
    task(request, key)
    mutate(configuration(request).set_task_enabled, key, body.enabled)
    return task(request, key)


@router.delete("/tasks/{key}", status_code=204)
def delete_task(request: Request, key: str):
    task(request, key)
    mutate(configuration(request).delete_task, key, at=time.time())


@router.post("/rules/preview")
def preview(body: PreviewInput):
    return {
        "rule": body.rule.model_dump(mode="json"),
        "explanation": explain(body.rule),
        "result": evaluate(body.rule, body.sample).model_dump(mode="json") if body.sample else None,
        "warnings": evaluate(body.rule, PostFields()).warnings,
    }


@router.post("/rules/history")
def history(request: Request, body: HistoryInput):
    return management(request).history(body.rule, body.limit)


class SiteInput(Input):
    expected_revision: int = Field(ge=1)
    enabled: bool
    interval_seconds: int = Field(ge=1, le=86400)


@router.get("/site")
def site(request: Request):
    return {**management(request).site(), "scheduler": request.app.state.runtime.snapshot()}


@router.put("/site")
async def configure_site(request: Request, body: SiteInput):
    await run_in_threadpool(
        mutate,
        configuration(request).configure_site,
        enabled=body.enabled,
        interval_seconds=body.interval_seconds,
        expected_revision=body.expected_revision,
        at=time.time(),
    )
    request.app.state.runtime.notify_configuration()
    return await run_in_threadpool(site, request)


@router.post("/site/test")
async def test_site(request: Request, _body: Input):
    try:
        return await request.app.state.runtime.check_source()
    except SourceBusy:
        raise HTTPException(409, "来源请求正在进行，请稍后重试。") from None


@router.get("/overview")
def overview(request: Request):
    return {
        "site": management(request).site(),
        "counts": management(request).overview(),
        "scheduler": request.app.state.runtime.snapshot(),
    }


@router.get("/content/options")
def content_options(request: Request):
    return management(request).content_options()


@router.get("/content")
def content(
    request: Request,
    offset: int = Query(default=0, ge=0, le=1000000),
    limit: int = Query(default=20, ge=1, le=100),
    query: str = Query(default="", max_length=200),
    author: str = Query(default="", max_length=500),
    category: str = Query(default="", max_length=500),
    task_id: str | None = Query(default=None, max_length=36),
    matched_only: bool = False,
):
    return management(request).content(
        offset=offset,
        limit=limit,
        query=query,
        author=author,
        category=category,
        task_id=task_id,
        matched_only=matched_only,
    )


class SendInput(Input):
    request_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    expected_revision: int = Field(ge=1)
    confirmed: bool

    @field_validator("confirmed")
    @classmethod
    def confirmed_action(cls, value: bool):
        if not value:
            raise ValueError("Explicit confirmation required")
        return value


async def explicit_send(request: Request, kind: str, key: str, body: SendInput):
    try:
        return await request.app.state.runtime.send_explicit(
            kind, key, key=body.request_id, expected_revision=body.expected_revision
        )
    except SendNotFound:
        raise HTTPException(404, "通知目标或投递记录不存在。") from None
    except SendConflict:
        raise HTTPException(
            409,
            "发送条件已变化或正在发送，请刷新记录；原事件须已结束，重发目标须启用，配置版本须一致。",
        ) from None


@router.post("/targets/{key}/test")
async def test_target(request: Request, key: str, body: SendInput):
    return await explicit_send(request, "test", key, body)


@router.post("/deliveries/{key}/resend")
async def resend_delivery(request: Request, key: str, body: SendInput):
    return await explicit_send(request, "manual", key, body)


@router.get("/deliveries")
def deliveries(
    request: Request,
    kind: Literal["automatic", "manual", "test"] = "automatic",
    target_id: str | None = Query(default=None, max_length=36),
    status: str | None = Query(default=None, max_length=32),
    offset: int = Query(default=0, ge=0, le=1000000),
    limit: int = Query(default=20, ge=1, le=100),
):
    return DeliveryRecords(request.app.state.engine).list(
        kind=kind, target_id=target_id, status=status, offset=offset, limit=limit
    )


@router.get("/deliveries/{key}")
def delivery_detail(
    request: Request, key: str, kind: Literal["automatic", "manual", "test"] = "automatic"
):
    try:
        return DeliveryRecords(request.app.state.engine).detail(key, kind)
    except SendNotFound:
        raise HTTPException(404, "投递记录不存在。") from None
