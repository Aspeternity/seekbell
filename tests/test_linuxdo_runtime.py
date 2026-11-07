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
    Source,
    SourceProbe,
    SourceState,
    Website,
    WebsiteRequestState,
)
from seekbell.db.transactions import database_call, write_session
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
from tests.test_hotlist_settings import install
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


@pytest.mark.parametrize(
    ("status", "headers", "shared"),
    [
        (None, {}, False),
        (403, {}, False),
        (502, {}, False),
        (503, {"Retry-After": "900"}, True),
        (429, {}, True),
        (403, {"cf-mitigated": "challenge"}, True),
    ],
)
def test_linuxdo_hotlist_shares_only_origin_wide_limits_with_monitoring(
    core, status, headers, shared
):
    async def run():
        now = [2000]
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])

        async def handler(request):
            if status is None:
                raise httpx.ReadTimeout("synthetic-private-value")
            return httpx.Response(status, headers=headers)

        service = HotlistService(
            request_budget=budget, transport=httpx.MockTransport(handler), clock=lambda: now[0]
        )
        try:
            data = await service.get("linuxdo", "hot")
            assert data["status"] in ("unavailable", "waiting")
            # The hotlist keeps its own retry time for path-local failures.
            assert data["next_attempt_at"] >= 2030
            now[0] += 2
            with Session(core.engine) as session:
                state = session.get(WebsiteRequestState, "linuxdo")
                assert (state.failures == 1) is shared and (state.blocked_until > now[0]) is shared
            if shared:
                with pytest.raises(SourceDeferred):
                    async with budget.request("linuxdo"):
                        raise AssertionError("Monitoring must wait for the origin")
            else:
                async with budget.request("linuxdo"):
                    pass
        finally:
            await service.aclose()

    asyncio.run(run())


def test_linuxdo_hotlist_success_does_not_clear_monitoring_backoff_evidence(core):
    async def run():
        now = [2000]
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        await database_call(budget.failed, SourceFailure("http_503"), now[0])
        now[0] += 31

        async def handler(request):
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                stream=Chunks(linuxdo_rss(9001)),
            )

        service = HotlistService(
            request_budget=budget, transport=httpx.MockTransport(handler), clock=lambda: now[0]
        )
        try:
            assert (await service.get("linuxdo", "hot"))["status"] == "ready"
            with Session(core.engine) as session:
                state = session.get(WebsiteRequestState, "linuxdo")
                assert state.failures == 1 and state.error_code == "http_503"
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


def rss_handler(calls):
    async def handler(request):
        calls.append(str(request.url))
        return httpx.Response(
            200,
            headers={"Content-Type": "application/rss+xml"},
            stream=Chunks(linuxdo_rss(9001)),
        )

    return handler


HOT = "https://linux.do/hot.rss"
DAILY = "https://linux.do/top.rss?period=daily"
WEEKLY = "https://linux.do/top.rss?period=weekly"


def test_linuxdo_hot_and_daily_go_at_once_and_weekly_a_minute_later(core):
    async def run():
        now, calls = [2000], []
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        service = HotlistService(
            request_budget=budget,
            transport=httpx.MockTransport(rss_handler(calls)),
            clock=lambda: now[0],
        )
        # Even with weekly selected, the time-sensitive lists go first.
        service.catalog = lambda: [("linuxdo", ["weekly", "hot", "daily"])]
        service.viewed_at = now[0]
        try:
            assert await service.warm_once() == 2002
            assert calls == [HOT]
            lists = (await service._board())["lists"]
            assert [(row["period"], row["status"], row["error_code"]) for row in lists] == [
                ("weekly", "unavailable", None),
                ("hot", "ready", None),
                ("daily", "waiting", "source_cooldown"),
            ]
            now[0] = 2002
            assert await service.warm_once() == 2062
            assert calls == [HOT, DAILY]
            # The weekly wait leaves its state and the board alone.
            tag = (await service._board())["tag"]
            now[0] = 2061
            assert await service.warm_once() == 2062 and len(calls) == 2
            assert (await service._board())["tag"] == tag
            now[0] = 2062
            assert await service.warm_once() == 2900
            assert calls == [HOT, DAILY, WEEKLY]
            with Session(core.engine) as session:
                assert session.get(WebsiteRequestState, "linuxdo").failures == 0
        finally:
            await service.aclose()

    asyncio.run(run())


def test_weekly_waits_for_hot_and_daily_due_within_a_minute(core):
    async def run():
        now, sent = [2000], []
        calls = rss_handler([])

        async def handler(request):
            sent.append((now[0], str(request.url)))
            return await calls(request)

        service = HotlistService(
            request_budget=WebsiteRequestBudget(core.engine, clock=lambda: now[0]),
            transport=httpx.MockTransport(handler),
            clock=lambda: now[0],
        )
        service.catalog = lambda: [("linuxdo", ["weekly", "hot", "daily"])]
        try:
            # Due times: weekly 5700, hot 5730, daily 5800.
            for period, at in (("weekly", 2100), ("daily", 4000), ("hot", 4830)):
                now[0] = at
                await service.get("linuxdo", period)
            sent.clear()
            service.viewed_at = 5700
            for second in range(5700, 5900):
                now[0] = second
                await service.warm_once()
            assert sent == [(5730, HOT), (5800, DAILY), (5860, WEEKLY)]
        finally:
            await service.aclose()

    asyncio.run(run())


def test_explicit_read_is_not_staggered(core):
    async def run():
        now, calls = [2000], []
        service = HotlistService(
            request_budget=WebsiteRequestBudget(core.engine, clock=lambda: now[0]),
            transport=httpx.MockTransport(rss_handler(calls)),
            clock=lambda: now[0],
        )
        try:
            await service.get("linuxdo", "hot")
            now[0] = 2002
            await service.get("linuxdo", "weekly")
            assert calls == [HOT, WEEKLY]
        finally:
            await service.aclose()

    asyncio.run(run())


def test_failed_refresh_logs_only_the_list_and_fixed_code(core, caplog):
    async def run():
        async def handler(request):
            return httpx.Response(
                429,
                headers={"cf-mitigated": "challenge"},
                text="SECRET-BODY",
            )

        service = HotlistService(
            request_budget=WebsiteRequestBudget(core.engine, clock=lambda: 2000),
            transport=httpx.MockTransport(handler),
            clock=lambda: 2000,
        )
        try:
            await service.get("linuxdo", "weekly")
        finally:
            await service.aclose()

    asyncio.run(run())
    assert "website=linuxdo period=weekly code=access_challenge" in caplog.text
    assert "SECRET-BODY" not in caplog.text and "cf-mitigated" not in caplog.text


def test_entering_after_a_long_absence_stays_within_three_requests_a_minute(core):
    """Linux DO challenged the fourth request within about a minute; collection runs
    once a minute, so hot and daily may share a minute with it but weekly may not."""

    async def run():
        install(core.engine, "linuxdo")
        with write_session(core.engine) as session:
            session.get(Website, "linuxdo").enabled = True
            session.get(Source, "linuxdo-rss").enabled = True
            session.get(SourceState, "linuxdo-rss").next_attempt_at = 2005
        now, sent, hotlists = [2000], [], []
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])
        collect = rss_handler(hotlists)

        async def handler(request):
            sent.append(now[0])
            return await collect(request)

        service = HotlistService(
            engine=core.engine,
            request_budget=budget,
            collection_active=lambda: True,
            transport=httpx.MockTransport(handler),
            clock=lambda: now[0],
        )
        service.catalog = lambda: [("linuxdo", ["weekly", "daily", "hot"])]
        service.viewed_at = 2000
        rss_due = 2005
        try:
            for second in range(2000, 2200):
                now[0] = second
                if second >= rss_due:
                    async with budget.request("linuxdo"):
                        sent.append(second)
                    rss_due = second + 60
                    with write_session(core.engine) as session:
                        session.get(SourceState, "linuxdo-rss").next_attempt_at = rss_due
                await service.warm_once()
            assert hotlists == [DAILY, HOT, WEEKLY]
            assert sent == [2000, 2002, 2005, 2062, 2065, 2125, 2185]
            assert all(sum(at <= other < at + 60 for other in sent) <= 3 for at in sent)
        finally:
            await service.aclose()

    asyncio.run(run())
