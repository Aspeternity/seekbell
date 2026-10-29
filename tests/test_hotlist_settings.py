"""Refresh settings, source isolation, upgrade preservation and bounded waiting."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import Source, SourceState, Website, WebsiteInstallation
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services.hotlists import HotlistService
from seekbell.services.request_budget import WebsiteRequestBudget
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.hotlist_helpers import snapshot
from tests.linuxdo_helpers import linuxdo_rss
from tests.rss_samples import Chunks
from tests.runtime_helpers import PassiveRuntime
from tests.test_management import authenticate


def install(engine, website_id):
    with write_session(engine) as session:
        if session.get(WebsiteInstallation, website_id) is None:
            session.add(WebsiteInstallation(website_id=website_id))


def raw_source(engine):
    with engine.connect() as connection:
        return (
            connection.execute(select(Source.__table__)).all(),
            connection.execute(select(SourceState.__table__)).all(),
        )


def test_hotlist_upgrade_is_atomic_and_preserves_every_old_column(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0016_site_categories")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO website_installations(website_id,position) "
                    "VALUES ('nodeseek',1),('linuxdo',2)"
                )
            )
        columns = {
            table: [column["name"] for column in inspect(engine).get_columns(table)]
            for table in inspect(engine).get_table_names()
            if table != "alembic_version"
        }

        def original_rows():
            with engine.connect() as connection:
                return {
                    table: connection.exec_driver_sql(
                        "SELECT "
                        + ",".join('"' + col + '"' for col in names)
                        + ' FROM "'
                        + table
                        + '" ORDER BY rowid'
                    ).all()
                    for table, names in columns.items()
                }

        before = original_rows()

        def interrupt(connection, cursor, statement, parameters, context, many):
            if "ADD COLUMN hotlist_settings" in statement:
                raise RuntimeError("Synthetic hotlist migration interruption")

        event.listen(engine, "before_cursor_execute", interrupt)
        with pytest.raises(RuntimeError, match="Synthetic hotlist"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", interrupt)
        assert schema_revision(engine) == "0016_site_categories"
        assert original_rows() == before
        migrate(engine)
        migrate(engine)
        assert schema_revision(engine) == "0018_settings_maintenance"
        assert original_rows() == before
        with Session(engine) as session:
            assert session.get(WebsiteInstallation, "nodeseek").hotlist_settings == {}
            assert session.get(WebsiteInstallation, "linuxdo").hotlist_settings == {}
    finally:
        engine.dispose()


def test_settings_are_authenticated_atomic_independent_and_survive_restart(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, runtime_factory=PassiveRuntime)
    custom = {"mode": "custom", "intervals": {"hot": 300, "daily": 900, "weekly": 7200}}
    with TestClient(app) as client:
        body = {"enabled": True, "interval": 60, "hotlist": custom}
        assert client.put("/api/manage/websites/linuxdo", json=body).status_code == 401
        authenticate(client)
        for site in ("nodeseek", "linuxdo"):
            assert client.post("/api/manage/websites", json={"adapter_id": site}).status_code == 201
        assert (
            client.put(
                "/api/manage/websites/linuxdo", json={"enabled": True, "interval": 60}
            ).status_code
            == 200
        )
        with write_session(app.state.engine) as session:
            source_state = session.get(SourceState, "linuxdo-rss")
            source_state.last_attempt_at = time.time() - 120
            source_state.next_attempt_at = time.time() + 10000
            source_state.initialized, source_state.needs_baseline = True, False
        before = raw_source(app.state.engine)
        assert (
            client.put(
                "/api/manage/websites/linuxdo", json=body, headers={"X-CSRF-Token": "bad"}
            ).status_code
            == 403
        )
        assert client.put("/api/manage/websites/linuxdo", json=body).status_code == 200
        assert raw_source(app.state.engine) == before
        sites = client.get("/api/manage/workspace").json()["websites"]
        linux, node = sites[1]["hotlist"], sites[0]["hotlist"]
        assert linux["mode"] == "custom"
        assert [p["interval_seconds"] for p in linux["periods"]] == [300, 900, 7200]
        assert node["mode"] == "recommended"
        assert [p["interval_seconds"] for p in node["periods"]] == [600, 1800, 3600]
        # Ordinary enable/disable calls do not reset hotlist choices.
        assert (
            client.put(
                "/api/manage/websites/linuxdo", json={"enabled": False, "interval": 60}
            ).status_code
            == 200
        )
    with TestClient(create_app(settings, runtime_factory=PassiveRuntime)) as client:
        authenticate(client, setup=False)
        sites = client.get("/api/manage/workspace").json()["websites"]
        assert sites[1]["hotlist"] == linux
        assert (
            client.put(
                "/api/manage/websites/linuxdo",
                json={"enabled": False, "interval": 60, "hotlist": {"mode": "recommended"}},
            ).status_code
            == 200
        )
        sites = client.get("/api/manage/workspace").json()["websites"]
        assert [p["interval_seconds"] for p in sites[1]["hotlist"]["periods"]] == [900, 1800, 3600]


@pytest.mark.parametrize(
    "bad",
    [
        {"mode": "custom", "intervals": {"hot": 300}},
        {"mode": "custom", "intervals": {"realtime": 300, "daily": 900, "weekly": 3600}},
        {"mode": "custom", "intervals": {"hot": 299, "daily": 900, "weekly": 3600}},
        {"mode": "custom", "intervals": {"hot": True, "daily": 900, "weekly": 3600}},
        {"mode": "custom", "intervals": {"hot": "300", "daily": 900, "weekly": 3600}},
        {"mode": "custom", "intervals": {"hot": 300, "daily": 900, "weekly": 86460}},
        {"mode": "recommended", "intervals": {"hot": 300}},
    ],
)
def test_invalid_hotlist_policy_never_partially_changes_source(tmp_path, bad):
    app = create_app(Settings(data_dir=tmp_path), runtime_factory=PassiveRuntime)
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "linuxdo"})
        before = raw_source(app.state.engine)
        result = client.put(
            "/api/manage/websites/linuxdo", json={"enabled": True, "interval": 300, "hotlist": bad}
        )
        assert result.status_code == 422
        assert raw_source(app.state.engine) == before
        with Session(app.state.engine) as session:
            assert session.get(WebsiteInstallation, "linuxdo").hotlist_settings == {}


@pytest.mark.parametrize(
    ("site", "period", "interval"),
    [
        ("nodeseek", "realtime", 600),
        ("nodeseek", "daily", 1800),
        ("nodeseek", "weekly", 3600),
        ("linuxdo", "hot", 900),
        ("linuxdo", "daily", 1800),
        ("linuxdo", "weekly", 3600),
    ],
)
def test_each_supported_period_refreshes_at_its_own_deadline(core, site, period, interval):
    async def run():
        now, calls = [2000], []

        async def handler(request):
            calls.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"} if site == "linuxdo" else {},
                stream=Chunks(
                    linuxdo_rss(9001)
                    if site == "linuxdo"
                    else json.dumps(snapshot(now=now[0])).encode()
                ),
            )

        service = HotlistService(
            engine=core.engine, clock=lambda: now[0], transport=httpx.MockTransport(handler)
        )
        try:
            first = await service.get(site, period)
            assert first["next_attempt_at"] == 2000 + interval
            now[0] += interval - 1
            assert not (await service.get(site, period))["refreshing"]
            assert len(calls) == 1
            now[0] += 1
            current = await service.get(site, period)
            assert current["items"] == first["items"] and current["refreshing"]
            await asyncio.gather(*service.pending.values())
            assert len(calls) == 2
        finally:
            await service.aclose()

    asyncio.run(run())


def test_shorter_and_longer_intervals_apply_to_existing_snapshot_and_restart(core):
    async def run():
        install(core.engine, "nodeseek")
        now, calls = [2000], []

        async def handler(request):
            calls.append(request)
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=now[0])).encode()))

        def custom(daily):
            with write_session(core.engine) as session:
                session.get(WebsiteInstallation, "nodeseek").hotlist_settings = {
                    "mode": "custom",
                    "intervals": {"realtime": 600, "daily": daily, "weekly": 3600},
                }

        service = HotlistService(
            engine=core.engine, clock=lambda: now[0], transport=httpx.MockTransport(handler)
        )
        try:
            await service.get("nodeseek", "daily")
            now[0] = 2900
            assert not (await service.get("nodeseek", "daily"))["refreshing"]
            custom(900)
            assert (await service.get("nodeseek", "daily"))["refreshing"]
            await asyncio.gather(*service.pending.values())
            assert len(calls) == 2
            custom(7200)
            assert (await service.get("nodeseek", "daily"))["next_attempt_at"] == 10100
        finally:
            await service.aclose()
        restored = HotlistService(
            engine=core.engine, clock=lambda: now[0], transport=httpx.MockTransport(handler)
        )
        try:
            cached = await restored.get("nodeseek", "daily")
            assert cached["fetched_at"] == 2900 and cached["next_attempt_at"] == 10100
            assert len(calls) == 2
        finally:
            await restored.aclose()

    asyncio.run(run())


def test_policy_edits_and_new_service_cannot_bypass_shared_server_wait(core):
    async def run():
        install(core.engine, "linuxdo")
        now, calls = [2000], []

        async def handler(request):
            calls.append(request)
            if len(calls) > 1:
                return httpx.Response(429, headers={"Retry-After": "7200"})
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                stream=Chunks(linuxdo_rss(9001)),
            )

        def service():
            return HotlistService(
                engine=core.engine,
                clock=lambda: now[0],
                request_budget=WebsiteRequestBudget(core.engine, clock=lambda: now[0]),
                transport=httpx.MockTransport(handler),
            )

        first = service()
        try:
            original = await first.get("linuxdo", "hot")
            now[0] = 2900
            assert (await first.get("linuxdo", "hot"))["refreshing"]
            await asyncio.gather(*first.pending.values())
            with write_session(core.engine) as session:
                session.get(WebsiteInstallation, "linuxdo").hotlist_settings = {
                    "mode": "custom",
                    "intervals": {"hot": 300, "daily": 900, "weekly": 1800},
                }
            stale = await first.get("linuxdo", "hot")
            assert stale["error_code"] == "http_429" and not stale["refreshing"]
            assert stale["next_attempt_at"] == 10100
        finally:
            await first.aclose()
        restored = service()
        try:
            stale = await restored.get("linuxdo", "hot")
            assert stale["items"] == original["items"] and not stale["refreshing"]
            assert stale["error_code"] == "http_429" and stale["next_attempt_at"] == 10100
            assert len(calls) == 2 and not restored.pending
        finally:
            await restored.aclose()

    asyncio.run(run())


def test_hotlist_waits_for_due_collection_without_claiming_an_inflight_refresh(core):
    async def run():
        install(core.engine, "linuxdo")
        now, calls = [2000], []
        with write_session(core.engine) as session:
            session.get(Website, "linuxdo").enabled = True
            session.get(Source, "linuxdo-rss").enabled = True

        async def handler(request):
            calls.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                stream=Chunks(linuxdo_rss(9001)),
            )

        service = HotlistService(
            engine=core.engine,
            clock=lambda: now[0],
            collection_active=lambda: True,
            transport=httpx.MockTransport(handler),
        )
        try:
            waiting = await service.get("linuxdo", "hot")
            assert waiting["status"] == "waiting" and not waiting["refreshing"]
            assert waiting["error_code"] == "collection_priority"
            assert not calls and not service.pending
            with write_session(core.engine) as session:
                session.get(SourceState, "linuxdo-rss").next_attempt_at = 2060
            now[0] += 2
            assert (await service.get("linuxdo", "hot"))["status"] == "ready"
            assert len(calls) == 1
        finally:
            await service.aclose()

    asyncio.run(run())


def test_busy_budget_defers_cold_read_without_scheduling_a_background_refresh(core):
    async def run():
        budget = WebsiteRequestBudget(core.engine, clock=lambda: 2000)

        async def handler(request):
            raise AssertionError("A deferred hotlist must not request the forum")

        service = HotlistService(
            request_budget=budget, clock=lambda: 2000, transport=httpx.MockTransport(handler)
        )
        try:
            async with budget.request("linuxdo"):
                waiting = await service.get("linuxdo", "hot")
                assert waiting["status"] == "waiting" and not waiting["refreshing"]
                assert not service.pending
        finally:
            await service.aclose()

    asyncio.run(run())


def test_concurrent_budget_read_rechecks_a_refresh_completed_during_its_wait(core):
    from threading import Event, Lock

    async def run():
        releases = [Event(), Event()]
        both_reading, guard = Event(), Lock()
        views, calls = [], []

        class DelayedBudget(WebsiteRequestBudget):
            def view(self, website_id):
                with guard:
                    index = len(views)
                    views.append(website_id)
                    if len(views) == 2:
                        both_reading.set()
                assert releases[index].wait(3), "Synthetic budget read was not released"
                return 0, None

        async def handler(request):
            calls.append(request)
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=1900)).encode()))

        service = HotlistService(
            request_budget=DelayedBudget(core.engine),
            clock=lambda: 2000,
            transport=httpx.MockTransport(handler),
        )
        try:
            readers = [asyncio.create_task(service.get("nodeseek", "realtime")) for _ in range(2)]
            assert await asyncio.to_thread(both_reading.wait, 3)
            releases[0].set()
            done, pending = await asyncio.wait(
                readers, timeout=3, return_when=asyncio.FIRST_COMPLETED
            )
            assert len(done) == len(pending) == 1
            assert next(iter(done)).result()["status"] == "ready"
            releases[1].set()
            assert (await next(iter(pending)))["status"] == "ready"
            assert len(calls) == 1
        finally:
            for release in releases:
                release.set()
            await service.aclose()

    asyncio.run(run())


@pytest.mark.parametrize("code", ["http_429", "access_challenge"])
def test_shared_origin_wait_is_not_a_failed_hotlist_and_recovers_without_waiting_out_old_state(
    core, code
):
    from seekbell.domain.errors import SourceFailure

    async def run():
        now, calls = [2000], []
        budget = WebsiteRequestBudget(core.engine, clock=lambda: now[0])

        async def handler(request):
            calls.append(request)
            return httpx.Response(
                200,
                headers={"Content-Type": "application/rss+xml"},
                stream=Chunks(linuxdo_rss(9001)),
            )

        service = HotlistService(
            engine=core.engine,
            clock=lambda: now[0],
            request_budget=budget,
            transport=httpx.MockTransport(handler),
        )
        try:
            original = await service.get("linuxdo", "hot")
            now[0] = 2900
            budget.failed(SourceFailure(code, retry_after=600), now[0])
            waiting = await service.get("linuxdo", "hot")
            assert waiting["status"] == "waiting" and not waiting["refreshing"]
            assert waiting["error_code"] == code
            assert waiting["items"] == original["items"]
            assert waiting["next_attempt_at"] == 3500
            assert not service.pending and len(calls) == 1
            # A genuine successful same-origin request can release the shared
            # wait; this period has never made a failed attempt of its own.
            budget.succeeded()
            current = await service.get("linuxdo", "hot")
            assert current["refreshing"]
            await asyncio.gather(*service.pending.values())
            assert len(calls) == 2
            assert (await service.get("linuxdo", "hot"))["status"] == "ready"
        finally:
            await service.aclose()

    asyncio.run(run())
