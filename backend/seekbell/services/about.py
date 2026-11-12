"""Read-only facts for the About page; never touches the network or business data."""

import platform
import time
from importlib.metadata import version
from pathlib import Path

from sqlalchemy.orm import Session

from seekbell.db.models import Website, WorkspacePreferences
from seekbell.db.runtime import schema_revision
from seekbell.services.maintenance import storage_view
from seekbell.sites.registry import BUILTIN_ADAPTERS

CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))


def in_container() -> bool:
    return any(marker.exists() for marker in CONTAINER_MARKERS)


def about_view(app_state) -> dict:
    engine = app_state.engine
    with Session(engine) as session:
        supported = [
            {"id": key, "name": session.get(Website, key).name} for key in BUILTIN_ADAPTERS
        ]
        timezone = session.get(WorkspacePreferences, 1).timezone
    storage = storage_view(app_state.settings)
    return {
        "version": version("seekbell"),
        "build_revision": app_state.settings.build_revision,
        "database_revision": schema_revision(engine),
        "supported_websites": supported,
        "timezone": timezone,
        "started_at": app_state.started_at,
        "environment": {
            "python": platform.python_version(),
            "system": f"{platform.system()} {platform.machine()}".strip(),
            "container": in_container(),
        },
        "storage": {
            "database_bytes": storage["database_bytes"],
            "filesystem_free_bytes": storage["filesystem_free_bytes"],
            "filesystem_total_bytes": storage["filesystem_total_bytes"],
        },
        "checked_at": time.time(),
    }
