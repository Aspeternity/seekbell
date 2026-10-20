"""Persistent display preference; timestamps remain UTC."""

from zoneinfo import available_timezones

from sqlalchemy.orm import Session

from seekbell.db.models import WorkspacePreferences
from seekbell.db.transactions import write_session

PREFIXES = (
    "Africa/",
    "America/",
    "Antarctica/",
    "Arctic/",
    "Asia/",
    "Atlantic/",
    "Australia/",
    "Europe/",
    "Indian/",
    "Pacific/",
    "Etc/",
)
TIMEZONES = tuple(
    sorted(zone for zone in available_timezones() if zone == "UTC" or zone.startswith(PREFIXES))
)


def timezone_name(value):
    if value not in TIMEZONES:
        raise ValueError("Unknown display timezone")
    return value


class DisplayConflict(ValueError):
    pass


def get_display(engine):
    with Session(engine) as session:
        preferences = session.get(WorkspacePreferences, 1)
        return {
            "timezone": preferences.timezone,
            "revision": preferences.display_revision,
            "available": TIMEZONES,
        }


def update_display(engine, timezone, revision):
    timezone_name(timezone)
    with write_session(engine) as session:
        preferences = session.get(WorkspacePreferences, 1)
        if preferences.display_revision != revision:
            raise DisplayConflict("时区已在其他页面改变，请重新读取后保存。")
        if preferences.timezone != timezone:
            preferences.timezone = timezone
            preferences.display_revision += 1
        return {
            "timezone": preferences.timezone,
            "revision": preferences.display_revision,
            "available": TIMEZONES,
        }
