import asyncio

import httpx
import pytest
from seekbell.collectors.http import public_response
from seekbell.collectors.rss import RssCollector
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
