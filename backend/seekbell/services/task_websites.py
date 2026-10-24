"""The versioned website scope is authoritative; the task origin is historical."""

from sqlalchemy import func, select

from seekbell.db.models import TaskVersion
from seekbell.sites.registry import BUILTIN_ADAPTERS


def normalize_websites(website_ids):
    if isinstance(website_ids, str):
        raise ValueError("Select at least one supported website")
    selected = list(dict.fromkeys(website_ids))
    if not selected or len(selected) > len(BUILTIN_ADAPTERS):
        raise ValueError("Select at least one supported website")
    if any(key not in BUILTIN_ADAPTERS for key in selected):
        raise ValueError("Unsupported website")
    return selected


def applies_to(website_id):
    sites = func.json_each(TaskVersion.website_ids).table_valued("value")
    return select(1).select_from(sites).where(sites.c.value == website_id).exists()
