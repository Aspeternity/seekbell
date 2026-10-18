import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from seekbell.api.auth import require_administrator
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate, explain
from seekbell.notifiers.configs import channel_schemas
from seekbell.notifiers.credentials import CredentialError
from seekbell.services.configuration import Configuration, ConfigurationConflict
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
