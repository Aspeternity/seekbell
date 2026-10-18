import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from seekbell.domain.errors import SourceFailure
from seekbell.domain.posts import Diagnostic, NormalizedPost, ParsedFeed, PostBatch

NODESEEK_RSS_URL = "https://rss.nodeseek.com/"


@dataclass(frozen=True)
class NodeSeekAdapter:
    website_id: str = "nodeseek"
    source_id: str = "nodeseek-rss"
    rss_url: str = NODESEEK_RSS_URL
    capabilities: frozenset[str] = frozenset({"title", "summary", "author", "category"})

    @staticmethod
    def post_id(link: str | None) -> str | None:
        if not link:
            return None
        try:
            url = urlsplit(link)
            if (
                url.scheme != "https"
                or url.hostname not in ("nodeseek.com", "www.nodeseek.com")
                or url.username is not None
                or url.password is not None
                or url.port not in (None, 443)
            ):
                return None
        except ValueError:
            return None
        match = re.fullmatch(r"/post-([0-9]{1,20})-[0-9]+/?", url.path)
        if match is None or int(match[1]) < 1:
            return None
        return str(int(match[1]))

    @staticmethod
    def canonical_url(post_id: str) -> str:
        return f"https://www.nodeseek.com/post-{post_id}-1"

    def normalize(self, feed: ParsedFeed) -> PostBatch:
        posts, diagnostics = [], list(feed.diagnostics)
        for index, entry in enumerate(feed.entries):
            link_id = self.post_id(entry.link)
            guid_id = (
                str(int(entry.item_id))
                if entry.item_id
                and re.fullmatch(r"[0-9]{1,20}", entry.item_id)
                and int(entry.item_id) > 0
                else None
            )
            if guid_id and link_id and guid_id != link_id:
                diagnostics.append(Diagnostic("identity_conflict", index))
                continue
            post_id = link_id or guid_id
            if post_id is None:
                diagnostics.append(Diagnostic("invalid_post_id", index))
                continue
            if not entry.title:
                diagnostics.append(Diagnostic("missing_title", index))
                continue
            if entry.item_id and guid_id is None:
                diagnostics.append(Diagnostic("non_numeric_guid", index))
            if link_id is None:
                diagnostics.append(Diagnostic("noncanonical_link", index))
            if entry.category is None:
                diagnostics.append(Diagnostic("missing_category", index))
            posts.append(
                NormalizedPost(
                    website_id=self.website_id,
                    external_post_id=post_id,
                    source_item_id=entry.item_id or self.canonical_url(post_id),
                    url=self.canonical_url(post_id),
                    title=entry.title,
                    summary=entry.summary,
                    author=entry.author,
                    category=entry.category,
                    published_at=entry.published_at,
                )
            )
        if feed.entries and not posts:
            raise SourceFailure("no_valid_entries")
        return PostBatch(tuple(posts), len(feed.entries), tuple(diagnostics))


BUILTIN_ADAPTERS = {"nodeseek": NodeSeekAdapter()}
