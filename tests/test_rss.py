import asyncio
from datetime import UTC, datetime

import httpx
import pytest
from seekbell.collectors.rss import RssCollector, parse_rss, retry_after_seconds
from seekbell.domain.errors import SourceFailure
from seekbell.sites.nodeseek import NODESEEK_RSS_URL, NodeSeekAdapter

from tests.rss_samples import Chunks, rss


def test_complete_missing_and_empty_summary_are_distinct():
    batch = NodeSeekAdapter().normalize(
        parse_rss(
            rss(
                [
                    {"id": 9001, "summary": "<b>优惠</b> summary"},
                    {"id": 9002, "summary": None},
                    {"id": 9003, "summary": ""},
                ]
            )
        )
    )
    assert batch.raw_count == 3
    assert [post.summary for post in batch.posts] == ["优惠 summary", None, ""]
    first = batch.posts[0]
    assert first.author == "fixture-user"
    assert first.category == "fixture-section"
    assert first.published_at == datetime(2026, 10, 18, 12, tzinfo=UTC)
    assert first.url == "https://www.nodeseek.com/post-9001-1"


def test_anomalies_are_diagnosed_without_losing_valid_entries():
    batch = NodeSeekAdapter().normalize(
        parse_rss(
            rss(
                [
                    {"id": 9001, "guid": "opaque-source-guid", "category": "未知合成版块"},
                    {"id": 9002, "guid": "bad", "link": "https://example.invalid/no-post"},
                    {"id": 9003, "guid": "9004"},
                    {"id": 9005, "published": "synthetic invalid date"},
                ]
            )
        )
    )
    assert [post.external_post_id for post in batch.posts] == ["9001", "9005"]
    assert batch.posts[0].category == "未知合成版块"
    assert {item.code for item in batch.diagnostics} >= {
        "non_numeric_guid",
        "invalid_post_id",
        "identity_conflict",
        "invalid_published_at",
    }


def test_untrusted_link_is_never_forwarded():
    batch = NodeSeekAdapter().normalize(
        parse_rss(
            rss(
                [
                    {"id": 9001, "link": "https://example.invalid/not-a-forum-link"},
                ]
            )
        )
    )
    assert batch.posts[0].url == "https://www.nodeseek.com/post-9001-1"
    assert "noncanonical_link" in {item.code for item in batch.diagnostics}


@pytest.mark.parametrize(
    "link",
    [
        "http://www.nodeseek.com/post-1-1",
        "https://www.nodeseek.com.evil.invalid/post-1-1",
        "https://" + "fixture@" + "www.nodeseek.com/post-1-1",
        "https://www.nodeseek.com:8443/post-1-1",
        "javascript:synthetic",
        "https://www.nodeseek.com/post-not-numeric-1",
    ],
)
def test_link_identity_is_strict(link):
    assert NodeSeekAdapter.post_id(link) is None


@pytest.mark.parametrize(
    "body",
    [
        b"<rss><channel><item>",
        b"<html><body>Synthetic challenge</body></html>",
        b'<!DOCTYPE rss [<!ENTITY sample "value">]><rss><channel/></rss>',
        b'<!DOCTYPE rss SYSTEM "file:///synthetic-private-file"><rss><channel/></rss>',
    ],
)
def test_bad_html_or_unsafe_xml_is_not_empty_success(body):
    with pytest.raises(SourceFailure):
        parse_rss(body)


def test_utf16_dtd_is_also_rejected():
    body = '<!DOCTYPE rss [<!ENTITY sample "value">]><rss><channel/></rss>'.encode("utf-16")
    with pytest.raises(SourceFailure, match="unsafe_xml"):
        parse_rss(body)


def test_valid_empty_feed_is_success_but_all_bad_entries_are_failure():
    assert NodeSeekAdapter().normalize(parse_rss(rss())).posts == ()
    with pytest.raises(SourceFailure, match="no_valid_entries"):
        NodeSeekAdapter().normalize(
            parse_rss(
                rss(
                    [
                        {
                            "id": 9001,
                            "guid": "bad",
                            "link": "https://example.invalid/no-post",
                        }
                    ]
                )
            )
        )


def test_html_is_text_not_executable_content():
    batch = NodeSeekAdapter().normalize(
        parse_rss(
            rss(
                [
                    {
                        "id": 9001,
                        "title": "Synthetic <b>title</b>",
                        "summary": "<script>synthetic()</script><p>safe text</p>",
                        "author": "<fixture-user>",
                    }
                ]
            )
        )
    )
    assert "<script" not in batch.posts[0].summary
    assert "<b>" not in batch.posts[0].title
    assert batch.posts[0].author == "<fixture-user>"


async def fetch_response(status=200, *, body=None, headers=None, max_bytes=1024 * 1024):
    stream = Chunks(rss([{"id": 9001}]) if body is None else body)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            headers={
                "content-type": "application/xml",
                **(headers or {}),
            },
            stream=stream,
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        try:
            result = await RssCollector(client, max_bytes=max_bytes).fetch(NODESEEK_RSS_URL)
        finally:
            assert stream.closed
    assert len(requests) == 1
    assert requests[0].url == NODESEEK_RSS_URL
    assert requests[0].headers["accept-encoding"] == "identity"
    return result


def test_httpx_transport_fetch_is_offline():
    assert len(asyncio.run(fetch_response()).entries) == 1


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (429, {"retry-after": "120"}, "http_429"),
        (403, {}, "http_403"),
        (503, {}, "http_503"),
        (302, {"location": "https://example.invalid/redirect"}, "http_302"),
        (200, {"content-type": "text/html"}, "unexpected_content_type"),
        (200, {"content-encoding": "gzip"}, "unsupported_content_encoding"),
    ],
)
def test_http_errors_redirects_and_challenges_are_failures(status, headers, code):
    with pytest.raises(SourceFailure) as failure:
        asyncio.run(fetch_response(status, headers=headers))
    assert failure.value.code == code
    if status == 429:
        assert failure.value.retry_after == 120


def test_size_limits_apply_to_declared_and_streamed_responses():
    with pytest.raises(SourceFailure, match="response_too_large"):
        asyncio.run(fetch_response(headers={"content-length": "100"}, max_bytes=99))
    with pytest.raises(SourceFailure, match="response_too_large"):
        asyncio.run(fetch_response(body=b"x" * 100, max_bytes=99))


def test_timeout_is_sanitized():
    async def scenario():
        def handler(request):
            raise httpx.ReadTimeout("synthetic-sensitive-detail", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(SourceFailure) as failure:
                await RssCollector(client).fetch(NODESEEK_RSS_URL)
            assert str(failure.value) == "timeout"

    asyncio.run(scenario())


def test_retry_after_seconds_and_http_date():
    now = datetime(2026, 10, 18, 12, tzinfo=UTC).timestamp()
    assert retry_after_seconds("Sun, 18 Oct 2026 12:02:00 GMT", now) == 120
    assert retry_after_seconds("-1", now) == 0
    assert retry_after_seconds("not a date", now) is None
    assert retry_after_seconds("inf", now) is None
