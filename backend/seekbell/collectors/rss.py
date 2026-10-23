import asyncio
import calendar
import io
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from xml.etree.ElementTree import ParseError

import feedparser
import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from seekbell.collectors.http import public_response
from seekbell.domain.errors import SourceFailure
from seekbell.domain.http import retry_after_seconds
from seekbell.domain.posts import Diagnostic, ParsedFeed, SourceEntry

MAX_RESPONSE_BYTES = 1024 * 1024


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        elif tag in ("br", "p", "div", "li"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1
        elif tag in ("p", "div", "li"):
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainText()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts).strip()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_rss(data: bytes, *, max_bytes: int = MAX_RESPONSE_BYTES) -> ParsedFeed:
    if len(data) > max_bytes:
        raise SourceFailure("response_too_large")
    try:
        root = ElementTree.fromstring(
            data, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except (ParseError, DefusedXmlException, ValueError):
        raise SourceFailure("invalid_or_unsafe_xml") from None
    if local_name(root.tag) != "rss":
        raise SourceFailure("not_rss")
    channel = next((item for item in root if local_name(item.tag) == "channel"), None)
    if channel is None:
        raise SourceFailure("missing_rss_channel")
    raw_items = [item for item in channel if local_name(item.tag) == "item"]
    # Passing a stream prevents feedparser from treating input as a path or URL.
    feed = feedparser.parse(io.BytesIO(data))
    if feed.get("bozo"):
        raise SourceFailure("feed_parse_error")
    if len(feed.entries) != len(raw_items):
        raise SourceFailure("entry_count_mismatch")
    entries, diagnostics = [], []
    for index, (entry, raw) in enumerate(zip(feed.entries, raw_items, strict=True)):
        raw_fields = {local_name(child.tag): child for child in raw}
        summary = None
        if "description" in raw_fields:
            summary = plain_text(entry.get("summary", ""))
        author = None
        creator = raw_fields.get("creator")
        if creator is not None:
            author = "".join(creator.itertext()).strip() or None
        elif entry.get("author"):
            author = plain_text(entry["author"]) or None
        published_at = None
        if entry.get("published_parsed") is not None:
            try:
                published_at = datetime.fromtimestamp(
                    calendar.timegm(entry["published_parsed"]), UTC
                )
            except (ValueError, OverflowError, OSError):
                diagnostics.append(Diagnostic("invalid_published_at", index))
        elif entry.get("published"):
            diagnostics.append(Diagnostic("invalid_published_at", index))
        categories = entry.get("tags", [])
        if len(categories) > 1:
            diagnostics.append(Diagnostic("multiple_categories", index))
        entries.append(
            SourceEntry(
                item_id=str(entry["id"]).strip() if entry.get("id") is not None else None,
                title=plain_text(entry["title"]) if entry.get("title") is not None else None,
                link=entry.get("link"),
                summary=summary,
                author=author,
                category=plain_text(categories[0].get("term", "")) or None if categories else None,
                published_at=published_at,
                description_html=raw_fields["description"].text
                if "description" in raw_fields
                else None,
            )
        )
    return ParsedFeed(tuple(entries), tuple(diagnostics))


class RssCollector:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        max_bytes: int = MAX_RESPONSE_BYTES,
        request_budget=None,
        website_id=None,
    ):
        self.client = client
        self.max_bytes = max_bytes
        self._limit = asyncio.Semaphore(1)
        self.request_budget, self.website_id = request_budget, website_id

    async def fetch(self, url: str) -> ParsedFeed:
        if self.request_budget is None:
            return await self._fetch(url)
        async with self.request_budget.request(self.website_id):
            return await self._fetch(url)

    async def _fetch(self, url: str) -> ParsedFeed:
        async with self._limit:
            try:
                async with public_response(
                    self.client,
                    url,
                    timeout=httpx.Timeout(10.0, connect=5.0),
                    headers={
                        "Accept": "application/rss+xml, application/xml, text/xml",
                        "Accept-Encoding": "identity",
                        "User-Agent": "SeekBell/0.1",
                    },
                ) as response:
                    if response.status_code != 200:
                        raise SourceFailure(
                            (
                                "access_challenge"
                                if response.status_code == 403
                                and response.headers.get("cf-mitigated") == "challenge"
                                else f"http_{response.status_code}"
                            ),
                            retry_after=retry_after_seconds(
                                response.headers.get("retry-after"), time.time()
                            ),
                        )
                    content_type = response.headers.get("content-type", "").split(";", 1)[0]
                    if content_type.lower() not in (
                        "application/rss+xml",
                        "application/xml",
                        "text/xml",
                    ):
                        raise SourceFailure("unexpected_content_type")
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise SourceFailure("unsupported_content_encoding")
                    try:
                        declared = int(response.headers.get("content-length", "0"))
                    except ValueError:
                        declared = 0
                    if declared > self.max_bytes:
                        raise SourceFailure("response_too_large")
                    parts, size = [], 0
                    async for chunk in response.aiter_raw(chunk_size=64 * 1024):
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise SourceFailure("response_too_large")
                        parts.append(chunk)
                return await asyncio.to_thread(parse_rss, b"".join(parts), max_bytes=self.max_bytes)
            except httpx.TimeoutException:
                raise SourceFailure("timeout") from None
            except httpx.HTTPError:
                raise SourceFailure("transport_error") from None
