import asyncio

import httpx
import pytest
from seekbell.collectors.http import LINUXDO_KEEPALIVE, SOURCE_TIMEOUT, public_response
from seekbell.collectors.rss import RssCollector
from seekbell.domain.errors import SourceFailure
from seekbell.services.hotlists import HotlistService
from seekbell.services.runtime import Runtime
from seekbell.sites.linuxdo import LINUXDO_RSS_URL

from tests.linuxdo_helpers import linuxdo_rss
from tests.rss_samples import Chunks


@pytest.mark.parametrize("owner", ["runtime", "hotlists"])
def test_public_clients_route_only_linuxdo_to_http2_and_close_all_pools(core, monkeypatch, owner):
    pools = []

    class RecordingTransport(httpx.AsyncBaseTransport):
        def __init__(self, **options):
            self.options, self.calls, self.closed = options, [], False
            pools.append(self)

        async def handle_async_request(self, request):
            self.calls.append(request)
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/rss+xml",
                    "Set-Cookie": "synthetic_session=value; Path=/",
                },
                stream=Chunks(linuxdo_rss(9001)),
                extensions={"http_version": b"HTTP/2" if self.options["http2"] else b"HTTP/1.1"},
            )

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", RecordingTransport)
    monkeypatch.setattr("httpx._client.AsyncHTTPTransport", RecordingTransport)

    async def run():
        service = Runtime(core.engine, {}) if owner == "runtime" else HotlistService()
        try:
            for url in (
                LINUXDO_RSS_URL,
                "https://linux.do/hot.rss",
                "https://linux.do/top.rss?period=daily",
                "https://linux.do/top.rss?period=weekly",
                "https://rss.nodeseek.com/",
                "https://api.bimg.eu.org/hot.json",
                "https://linux.do.example.invalid/latest.rss",
                "http://linux.do/latest.rss",
            ):
                async with public_response(service.client, url) as response:
                    await response.aread()
            h2 = next(pool for pool in pools if pool.options["http2"])
            h1 = next(pool for pool in pools if not pool.options["http2"])
            assert len(h2.calls) == len(h1.calls) == 4
            assert all(r.url.scheme == "https" and r.url.host == "linux.do" for r in h2.calls)
            assert all("cookie" not in r.headers for pool in pools for r in pool.calls)
            assert all(pool.options["trust_env"] is False for pool in pools)
            # Only Linux DO keeps its connection past a one-minute interval.
            assert h2.options["limits"].keepalive_expiry == LINUXDO_KEEPALIVE
            assert h2.options["limits"].max_connections == h1.options["limits"].max_connections
            assert h1.options["limits"].keepalive_expiry == 5
        finally:
            await service.aclose()
        assert service.client.is_closed
        assert all(pool.closed for pool in pools)

    asyncio.run(run())


@pytest.mark.parametrize("owner", ["runtime", "hotlists"])
def test_public_clients_keep_mock_transport_for_linuxdo_and_http1_responses(
    core, monkeypatch, owner
):
    calls = []

    def unexpected_network_pool(**options):
        raise AssertionError("Injected IO must never construct a real transport")

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", unexpected_network_pool)
    monkeypatch.setattr("httpx._client.AsyncHTTPTransport", unexpected_network_pool)

    async def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            stream=Chunks(linuxdo_rss(9001)),
            extensions={"http_version": b"HTTP/1.1"},
        )

    async def run():
        transport = httpx.MockTransport(handler)
        service = (
            Runtime(core.engine, {}, http_transport=transport)
            if owner == "runtime"
            else HotlistService(transport=transport)
        )
        try:
            collector = RssCollector(service.client)
            feed = await collector.fetch(LINUXDO_RSS_URL)
            assert len(feed.entries) == 1
            if owner == "hotlists":
                result = await service.get("linuxdo", "hot")
                assert len(result["items"]) == 1
        finally:
            await service.aclose()
        assert service.client.is_closed

    asyncio.run(run())
    assert len(calls) == (1 if owner == "runtime" else 2)


@pytest.mark.parametrize("owner", ["rss", "hotlist"])
@pytest.mark.parametrize("status", [200, 403, 429])
def test_explicit_cloudflare_challenge_is_not_mislabeled_as_status_or_bad_xml(core, owner, status):
    from seekbell.domain.errors import SourceFailure
    from seekbell.services.request_budget import WebsiteRequestBudget

    async def run():
        async def handler(request):
            return httpx.Response(
                status,
                headers={
                    "Content-Type": "text/html",
                    "cf-mitigated": "challenge",
                    "Retry-After": "120",
                },
                stream=Chunks(b"synthetic-private-challenge-body"),
            )

        budget = WebsiteRequestBudget(core.engine, clock=lambda: 2000)
        if owner == "rss":
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                collector = RssCollector(client, website_id="linuxdo", request_budget=budget)
                with pytest.raises(SourceFailure) as caught:
                    await collector.fetch(LINUXDO_RSS_URL)
                assert caught.value.code == "access_challenge"
                assert caught.value.retry_after == 120
        else:
            service = HotlistService(
                clock=lambda: 2000, request_budget=budget, transport=httpx.MockTransport(handler)
            )
            try:
                result = await service.get("linuxdo", "daily")
                assert result["status"] == "unavailable"
                assert result["error_code"] == "access_challenge"
                assert result["next_attempt_at"] == 2300
                assert "synthetic-private" not in str(result)
            finally:
                await service.aclose()
        assert budget.view("linuxdo") == (2300, "access_challenge")

    asyncio.run(run())


@pytest.mark.parametrize("owner", ["rss", "hotlist"])
def test_ordinary_429_without_challenge_marker_remains_rate_limited(owner):
    from seekbell.domain.errors import SourceFailure

    async def run():
        async def handler(request):
            return httpx.Response(429, headers={"Retry-After": "120"})

        if owner == "rss":
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                with pytest.raises(SourceFailure) as caught:
                    await RssCollector(client).fetch(LINUXDO_RSS_URL)
                assert caught.value.code == "http_429"
        else:
            service = HotlistService(clock=lambda: 2000, transport=httpx.MockTransport(handler))
            try:
                assert (await service.get("linuxdo", "hot"))["error_code"] == "http_429"
            finally:
                await service.aclose()

    asyncio.run(run())


def flaky_handler(failures, calls):
    """Raise the queued connection-phase errors first, then serve a feed."""

    async def handler(request):
        calls.append(request)
        if failures:
            raise failures.pop(0)("synthetic", request=request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            stream=Chunks(linuxdo_rss(9001)),
        )

    return handler


@pytest.mark.parametrize("error", [httpx.ConnectTimeout, httpx.ConnectError])
def test_one_failed_connection_is_retried_at_once(monkeypatch, error):
    monkeypatch.setattr("seekbell.collectors.http.CONNECT_RETRY_GAP", 0)
    calls = []

    async def run():
        transport = httpx.MockTransport(flaky_handler([error], calls))
        async with httpx.AsyncClient(transport=transport) as client:
            return await RssCollector(client).fetch(LINUXDO_RSS_URL)

    assert len(asyncio.run(run()).entries) == 1
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("errors", "code", "attempts"),
    [
        ([httpx.ConnectTimeout, httpx.ConnectTimeout], "connect_timeout", 2),
        ([httpx.ConnectError, httpx.ConnectError], "transport_error", 2),
        # The request went out: a second try would be one more request to the origin.
        ([httpx.ReadTimeout], "timeout", 1),
        ([httpx.ReadError], "transport_error", 1),
    ],
)
def test_failed_reads_keep_connection_and_response_timeouts_apart(
    monkeypatch, errors, code, attempts
):
    monkeypatch.setattr("seekbell.collectors.http.CONNECT_RETRY_GAP", 0)
    calls = []

    async def run():
        transport = httpx.MockTransport(flaky_handler(list(errors), calls))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(SourceFailure) as caught:
                await RssCollector(client).fetch(LINUXDO_RSS_URL)
        return caught.value.code

    assert asyncio.run(run()) == code
    assert len(calls) == attempts


def test_source_reads_bound_connection_apart_from_response():
    assert SOURCE_TIMEOUT.connect == 8 and SOURCE_TIMEOUT.read == 15
