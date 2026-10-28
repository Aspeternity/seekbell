import asyncio
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.collectors.rss import RssCollector
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    Outbox,
    Post,
    SourceProbe,
    SourceState,
    WebsiteRequestState,
)
from seekbell.db.transactions import write_session
from seekbell.domain.errors import SourceDeferred, SourceFailure
from seekbell.main import create_app
from seekbell.services.hotlists import HotlistService
from seekbell.services.request_budget import WebsiteRequestBudget
from seekbell.services.runtime import Runtime
from seekbell.sites.linuxdo import LINUXDO_RSS_URL
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.linuxdo_helpers import linuxdo_rss
from tests.rss_samples import Chunks, rss
from tests.runtime_helpers import SyntheticScenario
from tests.test_management import authenticate, target, task_values
from tests.test_runtime import until


@pytest.mark.parametrize("status", [403, 429, 503])
def test_linuxdo_monitoring_failure_cools_all_hotlists_probes_and_survives_restart(core, status):
    async def run():
        now = [2000]
        calls = []

        async def handler(request):
            calls.append(str(request.url))
            return httpx.Response(
                status,
                headers={"Retry-After": "900", "cf-mitigated": "challenge"}
                if status == 403
                else {"Retry-After": "900"},
            )

        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            collector = RssCollector(client, request_budget=budget, website_id="linuxdo")
            with pytest.raises(SourceFailure):
                await collector.fetch(LINUXDO_RSS_URL)
        assert len(calls) == 1
        # A new in-process budget reads the same persisted origin backoff.
        restored = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        service = HotlistService(
            engine=core.engine,
            request_budget=restored,
            transport=httpx.MockTransport(handler),
            clock=lambda: now[0],
        )
        try:
            for period in ("hot", "daily", "weekly"):
                data = await service.get("linuxdo", period)
                assert data["status"] == "waiting"
                assert data["next_attempt_at"] >= 2900
            assert len(calls) == 1
            with pytest.raises(SourceDeferred):
                async with restored.request("linuxdo"):
                    raise AssertionError("An HTTP operation must not begin")
            async with restored.request("nodeseek"):
                pass
            with Session(core.engine) as session:
                state = session.get(WebsiteRequestState, "linuxdo")
                assert state.failures == 1 and state.blocked_until >= 2900
        finally:
            await service.aclose()

    asyncio.run(run())


def test_linuxdo_shared_budget_excludes_parallel_requests_and_bounds_retries(core):
    async def run():
        now = [2000]
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        entered, release = asyncio.Event(), asyncio.Event()

        async def first():
            async with budget.request("linuxdo"):
                entered.set()
                await release.wait()

        task = asyncio.create_task(first())
        await entered.wait()
        with pytest.raises(SourceDeferred, match="source_busy"):
            async with budget.request("linuxdo"):
                pass
        release.set()
        await task
        with pytest.raises(SourceDeferred, match="source_cooldown"):
            async with budget.request("linuxdo"):
                pass
        now[0] += 2
        async with budget.request("linuxdo"):
            pass

    asyncio.run(run())


def test_linuxdo_hotlist_transport_failure_also_defers_monitoring(core):
    async def run():
        budget = WebsiteRequestBudget(core.engine, clock=lambda: 2000)

        async def handler(request):
            raise httpx.ReadTimeout("synthetic-private-value")

        service = HotlistService(
            request_budget=budget, transport=httpx.MockTransport(handler), clock=lambda: 2000
        )
        try:
            data = await service.get("linuxdo", "hot")
            assert data["status"] == "unavailable" and data["next_attempt_at"] >= 2030
            with pytest.raises(SourceDeferred):
                async with budget.request("linuxdo"):
                    pass
        finally:
            await service.aclose()

    asyncio.run(run())


def test_two_runtime_sources_baseline_deduplicate_and_recover_independently(tmp_path):
    scenario = SyntheticScenario()
    linux_ids = [9001]
    calls = []
    advance = [0]

    async def feed(request):
        calls.append(str(request.url))
        if request.url.host == "linux.do":
            raw = linuxdo_rss(*linux_ids)
        else:
            raw = rss([{"id": key, "title": "Synthetic VPS"} for key in scenario.items])
        return httpx.Response(
            200, headers={"Content-Type": "application/rss+xml"}, stream=Chunks(raw)
        )

    def factory(engine, notifiers):
        runtime = Runtime(
            engine,
            {kind: scenario for kind in ("telegram", "bark", "smtp", "webhook")},
            http_transport=httpx.MockTransport(feed),
            tick=0.02,
        )

        def clock():
            return time.time() + advance[0]

        runtime.request_budget.clock = clock
        runtime.worker.clock = clock
        for source in runtime.sources.values():
            source.clock = clock
        return runtime

    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, runtime_factory=factory)

    def initialized(website):
        with Session(app.state.engine) as session:
            return session.get(SourceState, website + "-rss").initialized

    def due(website):
        advance[0] += 3
        with write_session(app.state.engine) as session:
            session.get(SourceState, website + "-rss").next_attempt_at = 0

    with TestClient(app) as client:
        authenticate(client)
        key = target(client, enabled=True)
        for website in ("nodeseek", "linuxdo"):
            assert (
                client.post("/api/manage/websites", json={"adapter_id": website}).status_code == 201
            )
            assert (
                client.post(
                    "/api/manage/tasks",
                    json={
                        **task_values(key),
                        "website_id": website,
                        "enabled": True,
                    },
                ).status_code
                == 201
            )
            assert (
                client.put(
                    "/api/manage/websites/" + website,
                    json={
                        "enabled": True,
                        "interval": 60 if website == "linuxdo" else 10,
                    },
                ).status_code
                == 200
            )
            until(lambda website=website: initialized(website))
        assert not scenario.sends
        scenario.items = [9001, 9002]
        linux_ids.append(9002)
        due("nodeseek")
        due("linuxdo")
        until(lambda: len(scenario.sends) == 2)
        with Session(app.state.engine) as session:
            assert session.get(Post, ("nodeseek", "9002"))
            assert session.get(Post, ("linuxdo", "9002"))
            until(lambda: len(scenario.sends) == 2)
        assert {p["post"]["website_id"] for p in scenario.sends} == {"nodeseek", "linuxdo"}
        linux_payload = next(p for p in scenario.sends if p["post"]["website_id"] == "linuxdo")
        assert linux_payload["post"]["author"] is None
        assert linux_payload["post"]["author_display_name"] == "Synthetic Display Name"
        # A pause/resume makes only this site's current window a baseline.
        assert (
            client.put(
                "/api/manage/websites/linuxdo", json={"enabled": False, "interval": 60}
            ).status_code
            == 200
        )
        linux_ids.append(9003)
        assert (
            client.put(
                "/api/manage/websites/linuxdo", json={"enabled": True, "interval": 60}
            ).status_code
            == 200
        )
        due("linuxdo")
        until(lambda: history_count(app, Post) == 5)
        assert len(scenario.sends) == 2
    linux_ids.append(9004)
    app = create_app(settings, runtime_factory=factory)
    with TestClient(app):
        due("linuxdo")
        until(lambda: len(scenario.sends) == 3)
        with Session(app.state.engine) as session:
            assert not session.get(Post, ("linuxdo", "9004")).baseline
        until(lambda: history_count(app, DeliveredPost) == 3)
    assert all(t.done() for t in app.state.runtime.tasks.values())
    assert app.state.runtime.client.is_closed


def history_count(app, model):
    with Session(app.state.engine) as session:
        return len(session.scalars(select(model)).all())


def test_linuxdo_slow_or_challenged_source_does_not_delay_nodeseek_or_readiness(tmp_path):
    scenario = SyntheticScenario()
    entered = None

    async def feed(request):
        nonlocal entered
        if request.url.host == "linux.do":
            entered = True
            await asyncio.Event().wait()
        return await scenario.feed(request)

    def factory(engine, notifiers):
        runtime = Runtime(
            engine, {}, http_transport=httpx.MockTransport(feed), tick=0.02, collector_timeout=0.1
        )
        return runtime

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        authenticate(client)
        for website in ("linuxdo", "nodeseek"):
            client.post("/api/manage/websites", json={"adapter_id": website})
            client.put(
                "/api/manage/websites/" + website,
                json={
                    "enabled": True,
                    "interval": 60 if website == "linuxdo" else 10,
                },
            )
        until(lambda: bool(scenario.fetches))
        until(lambda: entered)
        until(
            lambda: (
                next(
                    s
                    for s in client.get("/api/manage/overview").json()["sources"]
                    if s["website_id"] == "linuxdo"
                )["error_code"]
                == "timeout"
            )
        )
        assert client.get("/health/ready").status_code == 200
        sources = client.get("/api/manage/overview").json()["sources"]
        assert next(s for s in sources if s["website_id"] == "nodeseek")["last_success_at"]
        assert app.state.runtime.active


def test_linuxdo_explicit_probe_is_read_only_and_routes_to_selected_site(tmp_path):
    calls = []

    async def feed(request):
        calls.append(str(request.url))
        return (
            httpx.Response(
                403,
                headers={"cf-mitigated": "challenge"},
            )
            if request.url.host == "linux.do"
            else httpx.Response(
                200, headers={"Content-Type": "application/rss+xml"}, stream=Chunks(rss())
            )
        )

    def factory(engine, notifiers):
        return Runtime(engine, {}, http_transport=httpx.MockTransport(feed), tick=0.02)

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "linuxdo"})
        response = client.post("/api/manage/websites/linuxdo/connection-test", json={})
        assert response.status_code == 200 and response.json()["code"] == "access_challenge"
        assert calls == [LINUXDO_RSS_URL]
        assert (
            client.post("/api/manage/websites/linuxdo/connection-test", json={}).status_code == 429
        )
        assert len(calls) == 1 and history_count(app, Post) == history_count(app, Outbox) == 0
        with Session(app.state.engine) as session:
            assert not session.get(SourceState, "linuxdo-rss").initialized
            assert session.get(SourceProbe, "linuxdo-rss").code == "access_challenge"


def test_anonymous_collectors_never_replay_remote_cookies():
    async def run():
        requests = []

        async def handler(request):
            requests.append(request)
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "application/rss+xml",
                    "Set-Cookie": "synthetic_session=value; Path=/",
                },
                stream=Chunks(linuxdo_rss(9001)),
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            collector = RssCollector(client)
            await collector.fetch(LINUXDO_RSS_URL)
            assert client.cookies
            await collector.fetch(LINUXDO_RSS_URL)
        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: 2000)
        try:
            await service.get("linuxdo", "hot")
            await service.get("linuxdo", "daily")
        finally:
            await service.aclose()
        assert len(requests) == 4
        assert all("cookie" not in request.headers for request in requests)

    asyncio.run(run())
