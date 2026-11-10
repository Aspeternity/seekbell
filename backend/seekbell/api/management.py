import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from seekbell.api.auth import require_admin
from seekbell.api.history import Paging
from seekbell.db.models import (
    NotificationTarget,
    OverviewPreferences,
    Post,
    Source,
    SourceState,
    Task,
    TaskVersion,
    Website,
    WebsiteInstallation,
    WorkspacePreferences,
)
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.posts import PostFields
from seekbell.domain.rules import Rule, evaluate
from seekbell.services import operations
from seekbell.services.configuration import Configuration, TargetDeleteChanged, TargetInUse
from seekbell.services.hotlist_settings import configuration as hotlist_configuration
from seekbell.services.hotlist_settings import validate_settings as validate_hotlist_settings
from seekbell.services.request_budget import request_state
from seekbell.services.rule_trial import trial_history
from seekbell.services.rule_values import normalized_rule
from seekbell.services.runtime import status as runtime_status
from seekbell.services.source_probe import ProbeConflict, get_probe
from seekbell.services.task_websites import applies_to
from seekbell.sites.categories import NODESEEK_ALIASES, category_options
from seekbell.sites.registry import BUILTIN_ADAPTERS, WebsiteId, validate_rule_capabilities

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


def config(request):
    return Configuration(request.app.state.engine, request.app.state.vault)


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class WebsiteInput(Input):
    adapter_id: WebsiteId


class HotlistSettingsInput(Input):
    mode: Literal["recommended", "custom"]
    intervals: dict[str, int] = Field(default_factory=dict, max_length=16)


class WebsiteUpdate(Input):
    enabled: bool
    interval: int = Field(ge=10, le=3600)
    hotlist: HotlistSettingsInput | None = None


class WebsiteSelection(Input):
    website_ids: list[WebsiteId] | None = Field(default=None, min_length=1, max_length=64)
    website_id: WebsiteId | None = None

    @model_validator(mode="after")
    def validate_selection(self):
        if (self.website_ids is None) == (self.website_id is None):
            raise ValueError("Select websites using website_ids or legacy website_id")
        if self.website_ids and len(set(self.website_ids)) != len(self.website_ids):
            raise ValueError("Duplicate websites")
        return self

    @property
    def selected_websites(self):
        return self.website_ids if self.website_ids is not None else [self.website_id]


class TaskInput(WebsiteSelection):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=160)
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
    website_id: WebsiteId | None = None


def installed(session, website_id):
    if session.get(WebsiteInstallation, website_id) is None:
        raise HTTPException(409, "请先添加该内置网站。")


def websites(session):
    result = []
    for installation in session.scalars(
        select(WebsiteInstallation).order_by(
            WebsiteInstallation.position, WebsiteInstallation.website_id
        )
    ):
        website = session.get(Website, installation.website_id)
        source = session.scalar(select(Source).where(Source.website_id == website.id))
        state = session.get(SourceState, source.id)
        result.append(
            {
                "id": website.id,
                "adapterId": website.id,
                "categoryOptions": category_options(
                    website.id,
                    session.scalars(
                        select(Post.category)
                        .where(Post.website_id == website.id, Post.category.is_not(None))
                        .distinct()
                        .order_by(Post.category)
                        .limit(100)
                    ),
                ),
                "enabled": website.enabled and source.enabled,
                "interval": source.interval_seconds,
                "hotlist": hotlist_configuration(website.id, installation.hotlist_settings),
                "health": "error"
                if state.last_error_code or request_state(session, website.id, time.time())[1]
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
                "website_id": version.website_ids[0],
                "website_ids": version.website_ids,
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
                "timezone": preferences.timezone,
                "overviewModules": session.get(OverviewPreferences, 1).modules,
            },
        }
    result["targets"] = [config(request).get_target(key) for key in target_ids]
    result["runtime"] = runtime_status(request)
    result["runtime_active"] = result["runtime"]["active"]
    return result


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
        position = (session.scalar(select(func.max(WebsiteInstallation.position))) or 0) + 1
        session.add(WebsiteInstallation(website_id=values.adapter_id, position=position))
    return {"id": values.adapter_id}


@router.put("/websites/{key}")
def update_website(key: str, values: WebsiteUpdate, request: Request):
    with write_session(request.app.state.engine) as session:
        installed(session, key)
        adapter = BUILTIN_ADAPTERS.get(key)
        if adapter is None or values.interval < adapter.minimum_interval:
            raise HTTPException(422, "采集间隔小于该网站支持的最小值。")
        website = session.get(Website, key)
        source = session.scalar(select(Source).where(Source.website_id == key))
        if values.hotlist is not None:
            try:
                settings = validate_hotlist_settings(
                    key, values.hotlist.mode, values.hotlist.intervals
                )
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
            session.get(WebsiteInstallation, key).hotlist_settings = settings
        # A hotlist-only edit must not move the monitoring schedule or baseline.
        if (
            website.enabled == source.enabled == values.enabled
            and source.interval_seconds == values.interval
        ):
            return {"ok": True}
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
            select(Task.id)
            .join(
                TaskVersion,
                (TaskVersion.task_id == Task.id) & (TaskVersion.version == Task.current_version),
            )
            .where(applies_to(key), Task.deleted_at.is_(None))
            .limit(1)
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
        for website_id in values.selected_websites:
            installed(session, website_id)
            validate_rule_capabilities(website_id, values.rule)
        if key:
            task = session.get(Task, key)
            if task is None or task.deleted_at is not None:
                raise HTTPException(404, "任务不存在。")
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
        website_ids=values.selected_websites,
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
        website_ids=values.selected_websites,
        managed=True,
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
    rule, post = values.rule, values.post
    if rule.site_categories is not None:
        if values.website_id is None or any(
            key not in BUILTIN_ADAPTERS for key in rule.site_categories
        ):
            raise ValueError("Select a supported sample website")
        rule = normalized_rule(rule, list(rule.site_categories))
    if values.website_id:
        validate_rule_capabilities(values.website_id, rule)
        if rule.site_categories is None:
            rule = normalized_rule(rule, [values.website_id])
        if values.website_id == "nodeseek" and post.category:
            post = post.model_copy(
                update={"category": NODESEEK_ALIASES.get(post.category, post.category)}
            )
    return evaluate(rule, post, website_id=values.website_id)


@router.get("/runtime")
def runtime(request: Request):
    return runtime_status(request)


class TargetDeleteInput(Input):
    confirmation: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


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


class HistoryTrial(WebsiteSelection):
    rule: Rule
    limit: int = Field(default=20, ge=1, le=100, strict=True)


@router.post("/rules/history")
def evaluate_history(values: HistoryTrial, request: Request):
    with Session(request.app.state.engine) as session:
        for website_id in values.selected_websites:
            installed(session, website_id)
            validate_rule_capabilities(website_id, values.rule)
    return trial_history(
        request.app.state.engine, values.selected_websites, values.rule, values.limit
    )


@router.get("/websites/{key}/connection-test")
def connection_result(key: WebsiteId, request: Request):
    with Session(request.app.state.engine) as session:
        installed(session, key)
    try:
        return get_probe(request.app.state.engine, key)
    except ProbeConflict as error:
        raise HTTPException(409, str(error)) from None


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


@router.post("/websites/{key}/connection-test")
async def connection_test(key: WebsiteId, values: ConnectionInput, request: Request):
    try:
        return await request.app.state.runtime.check_source(key)
    except ProbeConflict as error:
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
        raise HTTPException(
            429 if error.retry_after else 409, str(error), headers=headers
        ) from None


@router.get("/operations/status")
async def operations_status(request: Request):
    state = request.app.state
    # Actor and hotlist state live on the event loop; read them there, then query off it.
    observed, hotlists = state.runtime.observation(), state.hotlists.observation()
    return await database_call(operations.status, state.engine, observed, hotlists, at=time.time())


@router.get("/operations/problems")
def operations_problems(
    request: Request,
    params: Paging,
    kind: Literal["", "source", "delivery", "runtime"] = "",
    days: int = Query(7, ge=1, le=365),
    show_short: bool = False,
):
    return operations.problem_history(
        request.app.state.engine,
        at=time.time(),
        kind=kind,
        days=days,
        show_short=show_short,
        **params,
    )


@router.get("/operations/problems/{key}")
def operations_problem(key: str, request: Request):
    state = request.app.state
    try:
        return operations.problem_detail(
            state.engine, key, state.crash_records.read(), at=time.time()
        )
    except operations.MissingProblem as error:
        raise HTTPException(404, str(error)) from None
