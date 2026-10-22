import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from seekbell.api.auth import require_admin
from seekbell.api.history import Paging
from seekbell.db.models import (
    AlertSettings,
    NotificationTarget,
    RetentionPolicy,
    Source,
    SourceState,
    Task,
    TaskVersion,
    Website,
    WebsiteInstallation,
    WorkspacePreferences,
)
from seekbell.db.transactions import write_session
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate
from seekbell.services import alerts
from seekbell.services.configuration import Configuration, TargetDeleteChanged, TargetInUse
from seekbell.services.display import DisplayConflict, get_display, update_display
from seekbell.services.retention import PolicyConflict, get_policy, update_policy
from seekbell.services.rule_trial import trial_history
from seekbell.services.runtime import status as runtime_status
from seekbell.services.source_probe import ProbeConflict, get_probe

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


def config(request):
    return Configuration(request.app.state.engine, request.app.state.vault)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class WebsiteInput(Input):
    adapter_id: Literal["nodeseek"]


class WebsiteUpdate(Input):
    enabled: bool
    interval: int = Field(ge=10, le=3600)


class WorkspaceInput(Input):
    name: str = Field(min_length=1, max_length=24)
    description: str = Field(default="", max_length=40)


class TaskInput(Input):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=160)
    website_id: Literal["nodeseek"]
    enabled: bool = True
    rule: Rule
    target_ids: list[str] = Field(min_length=1, max_length=64)


class TargetInput(Input):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["telegram", "bark", "smtp", "webhook"]
    enabled: bool = True
    config: dict


class RuleTest(Input):
    rule: Rule
    post: PostFields


def installed(session, website_id):
    if session.get(WebsiteInstallation, website_id) is None:
        raise HTTPException(409, "请先添加该内置网站。")


def websites(session):
    result = []
    for installation in session.scalars(
        select(WebsiteInstallation).order_by(WebsiteInstallation.website_id)
    ):
        website = session.get(Website, installation.website_id)
        source = session.scalar(select(Source).where(Source.website_id == website.id))
        state = session.get(SourceState, source.id)
        result.append(
            {
                "id": website.id,
                "adapterId": website.id,
                "enabled": website.enabled and source.enabled,
                "interval": source.interval_seconds,
                "health": "error"
                if state.last_error_code
                else "healthy"
                if state.last_success_at
                else "pending",
                "lastSuccess": state.last_success_at,
            }
        )
    return result


def tasks(session):
    result = []
    for task in session.scalars(
        select(Task).where(Task.deleted_at.is_(None)).order_by(Task.created_at, Task.id)
    ):
        version = session.get(TaskVersion, (task.id, task.current_version))
        result.append(
            {
                "id": task.id,
                "website_id": task.website_id,
                "name": version.name,
                "description": version.description,
                "enabled": task.enabled,
                "rule": version.rule,
                "target_ids": version.target_ids,
                "version": version.version,
            }
        )
    return result


@router.get("/workspace")
def workspace(request: Request):
    engine = request.app.state.engine
    with Session(engine) as session:
        preferences = session.get(WorkspacePreferences, 1)
        target_ids = list(
            session.scalars(
                select(NotificationTarget.id).where(
                    NotificationTarget.kind != "mock", NotificationTarget.deleted_at.is_(None)
                )
            )
        )
        result = {
            "websites": websites(session),
            "tasks": tasks(session),
            "settings": {
                "workspaceName": preferences.name,
                "workspaceDescription": preferences.description,
                "retention": session.get(RetentionPolicy, 1).days,
                "timezone": preferences.timezone,
                "alertTargets": session.get(AlertSettings, 1).target_ids,
                "recoveryAlerts": session.get(AlertSettings, 1).enabled,
            },
        }
    result["targets"] = [config(request).get_target(key) for key in target_ids]
    result["runtime"] = runtime_status(request)
    result["runtime_active"] = result["runtime"]["active"]
    return result


@router.put("/workspace")
def update_workspace(values: WorkspaceInput, request: Request):
    name = values.name.strip()
    if not name:
        raise HTTPException(422, "工作空间名称不能为空。")
    with write_session(request.app.state.engine) as session:
        preferences = session.get(WorkspacePreferences, 1)
        preferences.name, preferences.description = name, values.description.strip()
    return {"ok": True}


@router.post("/websites", status_code=201)
def add_website(values: WebsiteInput, request: Request):
    with write_session(request.app.state.engine) as session:
        if session.get(WebsiteInstallation, values.adapter_id):
            raise HTTPException(409, "该网站已添加。")
        website = session.get(Website, values.adapter_id)
        source = session.scalar(select(Source).where(Source.website_id == website.id))
        website.enabled = False
        source.enabled = False
        session.get(SourceState, source.id).needs_baseline = True
        session.add(WebsiteInstallation(website_id=values.adapter_id))
    return {"id": values.adapter_id}


@router.put("/websites/{key}")
def update_website(key: str, values: WebsiteUpdate, request: Request):
    with write_session(request.app.state.engine) as session:
        installed(session, key)
        website = session.get(Website, key)
        source = session.scalar(select(Source).where(Source.website_id == key))
        state = session.get(SourceState, source.id)
        if website.enabled and not values.enabled:
            state.needs_baseline = True
        was_enabled = website.enabled and source.enabled
        website.enabled = source.enabled = values.enabled
        source.interval_seconds = values.interval
        if values.enabled:
            now = time.time()
            if state.failures:
                earliest = (
                    state.last_attempt_at + values.interval
                    if state.last_attempt_at is not None
                    else now
                )
                state.next_attempt_at = max(now, state.next_attempt_at, earliest)
            elif not was_enabled:
                state.next_attempt_at = now
            elif state.last_attempt_at is not None:
                state.next_attempt_at = max(now, state.last_attempt_at + values.interval)
    return {"ok": True}


@router.delete("/websites/{key}")
def remove_website(key: str, request: Request):
    with write_session(request.app.state.engine) as session:
        installed(session, key)
        if session.scalar(
            select(Task.id).where(Task.website_id == key, Task.deleted_at.is_(None)).limit(1)
        ):
            raise HTTPException(409, "请先处理该网站关联的任务。")
        session.get(Website, key).enabled = False
        source = session.scalar(select(Source).where(Source.website_id == key))
        source.enabled = False
        session.get(SourceState, source.id).needs_baseline = True
        session.delete(session.get(WebsiteInstallation, key))
    return {"ok": True}


def validate_task(values, request, key=None):
    with Session(request.app.state.engine) as session:
        installed(session, values.website_id)
        if key:
            task = session.get(Task, key)
            if task is None or task.deleted_at is not None:
                raise HTTPException(404, "任务不存在。")
            if task.website_id != values.website_id:
                raise HTTPException(409, "已有任务不能更换所属网站。")
        for target_id in values.target_ids:
            target = session.get(NotificationTarget, target_id)
            if (
                target is None
                or target.deleted_at is not None
                or target.kind == "mock"
                or not target.config_ciphertext
            ):
                raise HTTPException(422, "请选择已配置的通知目标。")


@router.post("/tasks", status_code=201)
def create_task(values: TaskInput, request: Request):
    validate_task(values, request)
    key = config(request).create_task(
        values.name,
        values.rule,
        values.target_ids,
        at=time.time(),
        website_id=values.website_id,
        enabled=values.enabled,
        description=values.description,
        managed=True,
    )
    return {"id": key}


@router.put("/tasks/{key}")
def update_task(key: str, values: TaskInput, request: Request):
    validate_task(values, request, key)
    version = config(request).update_task(
        key,
        values.name,
        values.rule,
        values.target_ids,
        at=time.time(),
        enabled=values.enabled,
        description=values.description,
    )
    return {"version": version}


@router.delete("/tasks/{key}")
def delete_task(key: str, request: Request):
    config(request).delete_task(key, at=time.time())
    return {"ok": True}


@router.post("/targets", status_code=201)
def create_target(values: TargetInput, request: Request):
    key = config(request).create_target(
        values.name, kind=values.kind, enabled=values.enabled, config=values.config
    )
    return {"id": key}


@router.put("/targets/{key}")
def update_target(key: str, values: TargetInput, request: Request):
    configuration = config(request)
    if configuration.get_target(key)["kind"] != values.kind:
        raise HTTPException(409, "已有目标不能更换渠道。")
    configuration.update_target(key, name=values.name, config=values.config, enabled=values.enabled)
    return {"ok": True}


@router.post("/rules/evaluate")
def evaluate_rule(values: RuleTest):
    return evaluate(values.rule, values.post)


@router.get("/runtime")
def runtime(request: Request):
    return runtime_status(request)


class TargetDeleteInput(Input):
    confirmation: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/targets/{key}/delete-preview")
def target_delete_preview(key: str, request: Request):
    return config(request).target_delete_preview(key)


@router.delete("/targets/{key}")
def delete_target(key: str, request: Request, values: TargetDeleteInput | None = None):
    try:
        config(request).delete_target(
            key, at=time.time(), confirmation=values.confirmation if values else None
        )
    except (TargetInUse, TargetDeleteChanged) as error:
        raise HTTPException(409, str(error)) from None
    return {"ok": True}


class HistoryTrial(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    website_id: Literal["nodeseek"]
    rule: Rule
    limit: int = Field(default=20, ge=1, le=100, strict=True)


@router.post("/rules/history")
def evaluate_history(values: HistoryTrial, request: Request):
    with Session(request.app.state.engine) as session:
        installed(session, values.website_id)
    return trial_history(request.app.state.engine, values.website_id, values.rule, values.limit)


@router.get("/websites/{key}/connection-test")
def connection_result(key: Literal["nodeseek"], request: Request):
    with Session(request.app.state.engine) as session:
        installed(session, key)
    try:
        return get_probe(request.app.state.engine, key)
    except ProbeConflict as error:
        raise HTTPException(409, str(error)) from None


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


@router.post("/websites/{key}/connection-test")
async def connection_test(key: Literal["nodeseek"], values: ConnectionInput, request: Request):
    try:
        return await request.app.state.runtime.check_source()
    except ProbeConflict as error:
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
        raise HTTPException(
            429 if error.retry_after else 409, str(error), headers=headers
        ) from None


class RetentionInput(Input):
    days: int = Field(ge=1, le=365)
    revision: int = Field(ge=1)


@router.get("/retention")
def retention_policy(request: Request):
    return get_policy(request.app.state.engine)


@router.put("/retention")
def save_retention(values: RetentionInput, request: Request):
    try:
        return update_policy(request.app.state.engine, values.days, values.revision)
    except PolicyConflict as error:
        raise HTTPException(409, str(error)) from None


class DisplayInput(Input):
    timezone: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)


@router.get("/display")
def display_settings(request: Request):
    return get_display(request.app.state.engine)


@router.put("/display")
def save_display(values: DisplayInput, request: Request):
    try:
        return update_display(request.app.state.engine, values.timezone, values.revision)
    except DisplayConflict as error:
        raise HTTPException(409, str(error)) from None


class AlertInput(Input):
    enabled: bool
    target_ids: list[str] = Field(max_length=64)
    revision: int = Field(ge=1)


@router.get("/alerts")
def alert_settings(request: Request):
    return alerts.get_settings(request.app.state.engine)


@router.put("/alerts")
def save_alerts(values: AlertInput, request: Request):
    try:
        return alerts.update_settings(
            request.app.state.engine, values.enabled, values.target_ids, values.revision
        )
    except alerts.AlertConflict as error:
        raise HTTPException(409, str(error)) from None


@router.get("/alerts/state")
def alert_states(request: Request, params: Paging):
    return alerts.states(request.app.state.engine, **params)


@router.get("/alerts/history")
def alert_history(request: Request, params: Paging):
    return alerts.history(request.app.state.engine, **params)


@router.get("/alerts/history/{key}")
def alert_detail(key: str, request: Request, params: Paging):
    try:
        return alerts.detail(request.app.state.engine, key, **params)
    except LookupError as error:
        raise HTTPException(404, str(error)) from None
