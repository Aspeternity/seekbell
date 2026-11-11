"""System settings: general preferences, alerts, retention and the About facts."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy.orm import Session

from seekbell.api.auth import require_admin
from seekbell.api.history import Paging
from seekbell.api.management import Input
from seekbell.db.models import WorkspacePreferences
from seekbell.db.transactions import write_session
from seekbell.services import alerts
from seekbell.services.about import about_view
from seekbell.services.display import (
    TIMEZONES,
    DisplayConflict,
    get_display,
    timezone_name,
    update_display,
)
from seekbell.services.maintenance import data_overview, retention_preview
from seekbell.services.retention import MAX_POSTS, PolicyConflict, get_policy, update_policy

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


class GeneralInput(Input):
    name: str = Field(min_length=1, max_length=24)
    description: str = Field(default="", max_length=40)
    timezone: str = Field(max_length=80)
    workspace_revision: int = Field(ge=1)
    display_revision: int = Field(ge=1)


def general_view(preferences):
    return {
        "name": preferences.name,
        "description": preferences.description,
        "timezone": preferences.timezone,
        "available": TIMEZONES,
        "workspace_revision": preferences.workspace_revision,
        "display_revision": preferences.display_revision,
    }


@router.get("/preferences")
def general_preferences(request: Request):
    with Session(request.app.state.engine) as session:
        return general_view(session.get(WorkspacePreferences, 1))


@router.put("/preferences")
def save_general_preferences(values: GeneralInput, request: Request):
    name, description = values.name.strip(), values.description.strip()
    if not name:
        raise HTTPException(422, "工作空间名称不能为空。")
    try:
        timezone_name(values.timezone)
    except ValueError:
        raise HTTPException(422, "请选择有效的显示时区。") from None
    with write_session(request.app.state.engine) as session:
        row = session.get(WorkspacePreferences, 1)
        if (row.workspace_revision, row.display_revision) != (
            values.workspace_revision,
            values.display_revision,
        ):
            raise HTTPException(409, "通用设置已在其他页面改变，请重新读取后保存。")
        if (row.name, row.description) != (name, description):
            row.name, row.description = name, description
            row.workspace_revision += 1
        if row.timezone != values.timezone:
            row.timezone = values.timezone
            row.display_revision += 1
        return general_view(row)


class DisplayInput(Input):
    timezone: str = Field(min_length=1, max_length=80)
    revision: int = Field(ge=1)


# The timezone alone, for callers that do not edit the workspace name.
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
    # Omitted by older callers, which keeps the saved delay.
    delay_seconds: int | None = Field(
        default=None, ge=0, le=alerts.MAX_DELAY_SECONDS, multiple_of=60
    )
    remind_seconds: Literal[0, 21600, 86400] | None = None
    revision: int = Field(ge=1)


@router.get("/alerts")
def alert_settings(request: Request):
    return alerts.get_settings(request.app.state.engine)


@router.put("/alerts")
def save_alerts(values: AlertInput, request: Request):
    try:
        return alerts.update_settings(
            request.app.state.engine,
            values.enabled,
            values.target_ids,
            values.revision,
            delay_seconds=values.delay_seconds,
            remind_seconds=values.remind_seconds,
        )
    except alerts.AlertConflict as error:
        raise HTTPException(409, str(error)) from None


# Read-only event feeds kept for the container checks and end-to-end tests; the operations
# center shows the same facts to the administrator as problem history.
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


class AlertTestInput(Input):
    target_ids: list[str] = Field(min_length=1, max_length=64)


@router.post("/alerts/test")
async def test_alerts(values: AlertTestInput, request: Request):
    """Send a marked test message now; only ever started by the administrator."""
    state = request.app.state
    gate: asyncio.Semaphore = state.sending_gate
    if gate.locked():
        raise HTTPException(429, "已有通知操作正在进行，请稍后重试。", headers={"Retry-After": "2"})
    async with gate:
        return {
            "items": await alerts.send_test(state.engine, state.alert_notifiers, values.target_ids)
        }


class RetentionInput(Input):
    days: int = Field(ge=1, le=365)
    # Required and nullable: an omitted limit must never silently clear a saved one.
    max_posts: int | None = Field(ge=1, le=MAX_POSTS)
    revision: int = Field(ge=1)


def retention_view(engine, policy):
    return {**policy, "overview": data_overview(engine)}


@router.get("/retention")
def retention_policy(request: Request):
    engine = request.app.state.engine
    return retention_view(engine, get_policy(engine))


@router.put("/retention")
def save_retention(values: RetentionInput, request: Request):
    engine = request.app.state.engine
    try:
        policy = update_policy(engine, values.days, values.max_posts, values.revision)
    except PolicyConflict as error:
        raise HTTPException(409, str(error)) from None
    return retention_view(engine, policy)


@router.get("/retention/preview")
def preview_retention(request: Request, days: int, max_posts: int | None = None):
    if not 1 <= days <= 365:
        raise HTTPException(422, "保留天数应为1–365天。")
    if max_posts is not None and not 1 <= max_posts <= MAX_POSTS:
        raise HTTPException(422, "内容上限应为1–1000000条。")
    return retention_preview(request.app.state.engine, days, max_posts)


@router.get("/about")
def about(request: Request):
    return about_view(request.app.state)
