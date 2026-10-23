"""Read-only display capabilities, independent of RSS monitoring adapters."""

import json
import math
from collections.abc import Callable
from dataclasses import dataclass

from seekbell.sites.labels import category_label
from seekbell.sites.nodeseek import NodeSeekAdapter


def text(value, limit):
    return value.strip()[:limit] if isinstance(value, str) else None


def number(value):
    return (
        value
        if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1e15
        else None
    )


def parse_nodeseek_snapshot(raw, now):
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("posts"), list):
        raise ValueError("invalid_snapshot")
    updated = number(data.get("updated_at"))
    if updated is None or updated == 0 or updated > now + 300 or len(data["posts"]) > 500:
        raise ValueError("invalid_snapshot")
    items, seen = [], set()
    for index, entry in enumerate(data["posts"]):
        post = entry.get("post") if isinstance(entry, dict) else None
        if not isinstance(post, dict):
            continue
        key = post.get("id")
        if type(key) not in (str, int) or not str(key).isascii() or not str(key).isdigit():
            continue
        key = str(int(key)) if len(str(key)) <= 20 else ""
        title = text(post.get("title"), 1000)
        if not key or key == "0" or not title or key in seen:
            continue
        seen.add(key)
        category = text(post.get("category"), 80)
        items.append(
            {
                "id": key,
                "rank": index + 1,
                "title": title,
                "url": NodeSeekAdapter.canonical_url(key),
                "author": text(post.get("author"), 100),
                "category": category_label("nodeseek", category),
                "views": number(post.get("views")),
                "comments": number(post.get("comments")),
            }
        )
    if data["posts"] and not items:
        raise ValueError("invalid_snapshot")
    return {"source_updated_at": updated, "fetched_at": now, "items": items[:100]}


@dataclass(frozen=True)
class HotlistSource:
    website_id: str
    name: str
    provider_id: str
    provider: str
    provider_url: str
    endpoints: dict[str, str]
    parse: Callable[[bytes, float], dict]
    default_period: str = "realtime"

    @property
    def periods(self):
        return tuple(self.endpoints)

    def metadata(self):
        labels = {"realtime": "实时", "daily": "每日", "weekly": "每周"}
        return {
            "website_id": self.website_id,
            "name": self.name,
            "provider_id": self.provider_id,
            "provider": self.provider,
            "provider_url": self.provider_url,
            "default_period": self.default_period,
            "periods": [{"id": key, "label": labels.get(key, key)} for key in self.periods],
        }


HOTLIST_SOURCES = {
    "nodeseek": HotlistSource(
        "nodeseek",
        "NodeSeek",
        "bimg",
        "第三方 NodeSeek 热榜",
        "https://bimg.eu.org/",
        {
            period: "https://api.bimg.eu.org/" + filename + ".json"
            for period, filename in (("realtime", "hot"), ("daily", "daily"), ("weekly", "weekly"))
        },
        parse=parse_nodeseek_snapshot,
    )
}
