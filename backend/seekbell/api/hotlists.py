from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy.orm import Session

from seekbell.api.auth import require_admin
from seekbell.api.management import Input
from seekbell.db.models import OverviewPreferences, WebsiteInstallation
from seekbell.services.overview_preferences import (
    OverviewConflict,
    get_preferences,
    installed_sources,
    update_layout,
    update_selection,
)
from seekbell.sites.hotlists import HOTLIST_SOURCES

router = APIRouter(prefix="/api/manage", dependencies=[Depends(require_admin)])


class ModuleInput(Input):
    id: Literal["tasks", "matches", "hotlist"]
    visible: bool


class LayoutInput(Input):
    modules: list[ModuleInput] = Field(min_length=3, max_length=3)
    revision: int = Field(ge=1)


class SelectionInput(Input):
    website_id: str = Field(min_length=1, max_length=80)
    period: str = Field(min_length=1, max_length=32)
    revision: int = Field(ge=1)


@router.get("/overview-preferences")
def preferences(request: Request):
    engine = request.app.state.engine
    return {**get_preferences(engine), "sources": installed_sources(engine)}


@router.put("/overview-preferences")
def save_preferences(values: LayoutInput, request: Request):
    try:
        return update_layout(
            request.app.state.engine, [row.model_dump() for row in values.modules], values.revision
        )
    except OverviewConflict as error:
        raise HTTPException(409, str(error)) from None


@router.put("/hotlists/selection")
def save_selection(values: SelectionInput, request: Request):
    try:
        return update_selection(
            request.app.state.engine, values.website_id, values.period, values.revision
        )
    except OverviewConflict as error:
        raise HTTPException(409, str(error)) from None


@router.get("/hotlists/{website_id}")
async def hotlist(website_id: str, request: Request, period: str | None = None):
    source = HOTLIST_SOURCES.get(website_id)
    if source is not None and period is None:
        period = source.default_period
    if source is None or period not in source.periods:
        raise HTTPException(404, "该网站或榜单周期尚未支持。")
    with Session(request.app.state.engine) as session:
        if session.get(WebsiteInstallation, website_id) is None:
            raise HTTPException(409, "请先添加该内置网站。")
        modules = session.get(OverviewPreferences, 1).modules
        if not any(row["id"] == "hotlist" and row["visible"] for row in modules):
            raise HTTPException(409, "社区热榜模块已隐藏。")
    return await request.app.state.hotlists.get(website_id, period)
