"""Public Discourse topic RSS; display names never become rule usernames."""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from seekbell.collectors.rss import plain_text
from seekbell.domain.errors import SourceFailure
from seekbell.domain.posts import Diagnostic, NormalizedPost, PostBatch

LINUXDO_RSS_URL = "https://linux.do/latest.rss?order=created"


def topic_id(link):
    if not isinstance(link, str):
        return None
    try:
        url = urlsplit(link)
        if (
            url.scheme != "https"
            or url.hostname != "linux.do"
            or url.username is not None
            or url.password is not None
            or url.port not in (None, 443)
        ):
            return None
    except ValueError:
        return None
    parts = url.path.strip("/").split("/")
    if not 2 <= len(parts) <= 4 or parts[0] != "t":
        return None
    if parts[1].isascii() and parts[1].isdigit():
        if len(parts) not in (2, 3):
            return None
        identifier, suffix = parts[1], parts[2:]
    elif len(parts) in (3, 4):
        identifier, suffix = parts[2], parts[3:]
    else:
        return None
    if (
        re.fullmatch(r"[0-9]{1,20}", identifier) is None
        or int(identifier) < 1
        or any(re.fullmatch(r"[0-9]{1,20}", value) is None for value in suffix)
    ):
        return None
    return str(int(identifier))


def summary_text(entry):
    if entry.description_html is None:
        return entry.summary
    raw = entry.description_html
    # Remove only the trailing two paragraphs added by Discourse's list RSS
    # template, checking that its final link points to this same topic.
    footer = re.search(
        r"""<p>\s*<small>[^<]*</small>\s*</p>\s*<p>\s*<a\s+[^>]*href=["']([^"']+)["'][^>]*>[^<]*</a>\s*</p>\s*$""",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if footer and topic_id(footer[1]) == topic_id(entry.link):
        raw = raw[: footer.start()]
    return plain_text(raw)


@dataclass(frozen=True)
class LinuxDoAdapter:
    website_id: str = "linuxdo"
    source_id: str = "linuxdo-rss"
    rss_url: str = LINUXDO_RSS_URL
    capabilities: frozenset[str] = frozenset({"title", "summary", "category"})
    default_interval: int = 60
    minimum_interval: int = 60

    post_id = staticmethod(topic_id)

    @staticmethod
    def canonical_url(post_id):
        return f"https://linux.do/t/topic/{post_id}"

    def normalize(self, feed):
        posts, diagnostics = [], list(feed.diagnostics)
        for index, entry in enumerate(feed.entries):
            link_id = topic_id(entry.link)
            guid = re.fullmatch(r"linux\.do-topic-([0-9]{1,20})", entry.item_id or "")
            guid_id = str(int(guid[1])) if guid and int(guid[1]) > 0 else None
            if guid_id and link_id and guid_id != link_id:
                diagnostics.append(Diagnostic("identity_conflict", index))
                continue
            key = link_id or guid_id
            if key is None or not entry.title:
                diagnostics.append(Diagnostic("invalid_topic", index))
                continue
            posts.append(
                NormalizedPost(
                    website_id=self.website_id,
                    external_post_id=key,
                    source_item_id=entry.item_id or self.canonical_url(key),
                    url=self.canonical_url(key),
                    title=entry.title,
                    summary=summary_text(entry),
                    author=None,
                    author_display_name=entry.author,
                    category=entry.category,
                    published_at=entry.published_at,
                )
            )
        if feed.entries and not posts:
            raise SourceFailure("no_valid_entries")
        return PostBatch(tuple(posts), len(feed.entries), tuple(diagnostics))
