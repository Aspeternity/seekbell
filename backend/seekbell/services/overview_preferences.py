"""Durable layout and independent per-site browsing choices."""

from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.orm import Session

from seekbell.db.models import OverviewPreferences, WebsiteInstallation
from seekbell.db.transactions import write_session

MODULES = ("tasks", "matches", "hotlist")


def default_modules():
    return [{"id": key, "visible": True} for key in MODULES]


def layout_value(preferences):
    return {"modules": deepcopy(preferences.modules), "revision": preferences.revision}


def selection_value(preferences):
    return {
        "website_id": preferences.website_id,
        "periods": deepcopy(preferences.periods),
        "revision": preferences.selection_revision,
    }


def get_preferences(engine):
    with Session(engine) as session:
        p = session.get(OverviewPreferences, 1)
        return {**layout_value(p), "selection": selection_value(p)}


class OverviewConflict(ValueError):
    pass


def update_layout(engine, modules, revision):
    if len(modules) != len(MODULES) or {row["id"] for row in modules} != set(MODULES):
        raise ValueError("Invalid overview modules")
    with write_session(engine) as session:
        p = session.get(OverviewPreferences, 1)
        if revision != p.revision:
            raise OverviewConflict("概览布局已在其他页面改变，请重新读取后保存。")
        if p.modules != modules:
            p.modules = deepcopy(modules)
            p.revision += 1
        return layout_value(p)


def update_selection(engine, website_id, period, revision):
    from seekbell.sites.hotlists import HOTLIST_SOURCES

    source = HOTLIST_SOURCES.get(website_id)
    if source is None or period not in source.periods:
        raise ValueError("Unsupported hotlist")
    with write_session(engine) as session:
        if session.get(WebsiteInstallation, website_id) is None:
            raise ValueError("Website is not installed")
        p = session.get(OverviewPreferences, 1)
        if p.selection_revision != revision:
            raise OverviewConflict("热榜选择已在其他页面改变，请重新读取。")
        if p.website_id != website_id or p.periods.get(website_id) != period:
            p.website_id = website_id
            p.periods = {**p.periods, website_id: period}
            p.selection_revision += 1
        return selection_value(p)


def installed_sources(engine):
    from seekbell.sites.hotlists import HOTLIST_SOURCES

    with Session(engine) as session:
        installed = set(session.scalars(select(WebsiteInstallation.website_id)))
    return [source.metadata() for key, source in HOTLIST_SOURCES.items() if key in installed]
