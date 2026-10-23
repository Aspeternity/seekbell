from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PostFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = ""
    summary: str | None = None
    author: str | None = None
    category: str | None = None


class NormalizedPost(PostFields):
    author_display_name: str | None = None
    website_id: str
    external_post_id: str
    source_item_id: str
    url: str
    published_at: datetime | None = None


@dataclass(frozen=True)
class SourceEntry:
    item_id: str | None
    title: str | None
    link: str | None
    summary: str | None
    author: str | None
    category: str | None
    published_at: datetime | None = None
    description_html: str | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    entry_index: int | None = None


@dataclass(frozen=True)
class ParsedFeed:
    entries: tuple[SourceEntry, ...]
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class PostBatch:
    posts: tuple[NormalizedPost, ...]
    raw_count: int
    diagnostics: tuple[Diagnostic, ...] = ()
