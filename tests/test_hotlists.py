import asyncio
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import Outbox, OverviewPreferences, Post, SeenPost, TaskEvaluation
from seekbell.db.runtime import create_database_engine, migrate
from seekbell.main import create_app
from seekbell.services.hotlists import MAX_BYTES, HotlistService
from seekbell.services.overview_preferences import default_modules
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.hotlist_helpers import snapshot, synthetic_hotlists
from tests.rss_samples import Chunks
from tests.runtime_helpers import PassiveRuntime
from tests.test_management import authenticate


def test_layout_migration_auth_conflict_and_separate_selection(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    migrate(engine, "0009_display_alerts")
    migrate(engine)
    with Session(engine) as session:
        assert session.get(OverviewPreferences, 1).modules == default_modules()
    engine.dispose()
    app = create_app(
        Settings(data_dir=tmp_path),
        runtime_factory=PassiveRuntime,
        hotlist_factory=synthetic_hotlists,
    )
    with TestClient(app) as client:
        assert client.get("/api/manage/overview-preferences").status_code == 401
        authenticate(client)
        prefs = client.get("/api/manage/overview-preferences").json()
        assert prefs["sources"] == []
        modules = list(reversed(prefs["modules"]))
        modules[0]["visible"] = False
        body = {"modules": modules, "revision": prefs["revision"]}
        assert (
            client.put(
                "/api/manage/overview-preferences", json=body, headers={"X-CSRF-Token": "bad"}
            ).status_code
            == 403
        )
        assert client.put("/api/manage/overview-preferences", json=body).status_code == 200
        assert client.put("/api/manage/overview-preferences", json=body).status_code == 409
        assert client.get("/api/manage/workspace").json()["settings"]["overviewModules"] == modules
        bad = copy.deepcopy(modules)
        bad[0]["id"] = bad[1]["id"]
        assert (
            client.put(
                "/api/manage/overview-preferences", json={"modules": bad, "revision": 2}
            ).status_code
            == 422
        )
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        assert client.get("/api/manage/overview-preferences").json()["sources"][0]["periods"] == [
            {"id": "realtime", "label": "实时"},
            {"id": "daily", "label": "每日"},
            {"id": "weekly", "label": "每周"},
        ]
        assert (
            client.put(
                "/api/manage/hotlists/selection",
                json={"website_id": "nodeseek", "period": "weekly", "revision": 1},
            ).status_code
            == 200
        )
        # Selection changes never conflict with the independent layout revision.
        assert client.get("/api/manage/overview-preferences").json()["revision"] == 2
        assert client.get("/api/manage/hotlists/nodeseek").status_code == 409
        modules[0]["visible"] = True
        assert (
            client.put(
                "/api/manage/overview-preferences", json={"modules": modules, "revision": 2}
            ).status_code
            == 200
        )
        response = client.get("/api/manage/hotlists/nodeseek?period=weekly")
        assert response.status_code == 200 and response.json()["status"] == "ready"
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/manage/hotlists/nodeseek?period=unsupported").status_code == 404
        with Session(app.state.engine) as session:
            for model in (Post, SeenPost, TaskEvaluation, Outbox):
                assert session.scalar(select(model).limit(1)) is None
    with TestClient(app) as client:
        authenticate(client, setup=False)
        prefs = client.get("/api/manage/overview-preferences").json()
        assert prefs["modules"] == modules
        assert prefs["selection"]["periods"] == {"nodeseek": "weekly"}


def test_cache_merges_concurrent_reads_and_isolates_periods():
    async def scenario():
        calls = []
        now = [2000]

        async def handler(request):
            calls.append(str(request.url))
            await asyncio.sleep(0.01)
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=1900)).encode()))

        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: now[0])
        try:
            responses = await asyncio.gather(*(service.get("nodeseek", "daily") for _ in range(8)))
            assert len(calls) == 1
            assert responses[0]["items"][0]["category"] == "技术"
            assert responses[0]["items"][0]["url"] == "https://www.nodeseek.com/post-8800-1"
            responses[0]["items"].clear()
            assert (await service.get("nodeseek", "daily"))["items"]
            await service.get("nodeseek", "weekly")
            assert len(calls) == 2
            now[0] += 601
            cached = await service.get("nodeseek", "daily")
            assert cached["refreshing"] and cached["items"]
            await asyncio.gather(*service.pending.values())
            assert len(calls) == 3
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_failed_refresh_preserves_snapshot_and_respects_retry_after():
    async def scenario():
        now = [2000]
        calls = []

        async def handler(request):
            calls.append(request)
            if len(calls) > 1:
                return httpx.Response(429, headers={"Retry-After": "1200"})
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=1900)).encode()))

        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: now[0])
        try:
            original = await service.get("nodeseek", "realtime")
            now[0] += 601
            pending = await service.get("nodeseek", "realtime")
            assert pending["refreshing"] and pending["items"] == original["items"]
            await asyncio.gather(*service.pending.values())
            stale = await service.get("nodeseek", "realtime")
            assert stale["status"] == "stale" and stale["items"] == original["items"]
            assert stale["source_updated_at"] == 1900 and stale["fetched_at"] == 2000
            assert stale["next_attempt_at"] == 3801
            await service.get("nodeseek", "realtime")
            assert len(calls) == 2
        finally:
            await service.aclose()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "kind", ["oversize", "bad_json", "bad_posts", "redirect", "compressed", "timeout"]
)
def test_untrusted_responses_are_bounded_and_do_not_expose_content(kind):
    async def scenario():
        async def handler(request):
            if kind == "timeout":
                raise httpx.ReadTimeout("private-remote-value")
            if kind == "redirect":
                return httpx.Response(302, headers={"Location": "https://other.example.test/"})
            raw = (
                b"x" * (MAX_BYTES + 1)
                if kind == "oversize"
                else b"private-remote-value"
                if kind == "bad_json"
                else json.dumps(
                    {"updated_at": 1900, "posts": [{"post": {"id": "../../x", "title": "invalid"}}]}
                ).encode()
            )
            return httpx.Response(
                200,
                headers={"Content-Encoding": "gzip"} if kind == "compressed" else {},
                stream=Chunks(raw),
            )

        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: 2000)
        try:
            data = await service.get("nodeseek", "realtime")
            assert data["status"] == "unavailable" and not data["items"]
            assert "private-remote" not in json.dumps(data)
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_expired_snapshot_returns_without_waiting_and_merges_background_refreshes():
    async def scenario():
        now = [2000]
        calls = []
        started, release = asyncio.Event(), asyncio.Event()

        async def handler(request):
            calls.append(request)
            if len(calls) > 1:
                started.set()
                await release.wait()
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=now[0])).encode()))

        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: now[0])
        try:
            first = await service.get("nodeseek", "daily")
            now[0] += 601
            responses = await asyncio.wait_for(
                asyncio.gather(*(service.get("nodeseek", "daily") for _ in range(8))), 0.5
            )
            await started.wait()
            assert len(calls) == 2 and len(service.pending) == 1
            assert all(row["refreshing"] and row["items"] == first["items"] for row in responses)
            assert responses[0]["source_updated_at"] == 2000
            assert responses[0]["next_attempt_at"] == 2603
            release.set()
            await asyncio.gather(*service.pending.values())
            fresh = await service.get("nodeseek", "daily")
            assert not fresh["refreshing"] and fresh["source_updated_at"] == 2601
            assert len(calls) == 2
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_cold_reader_cancellation_does_not_cancel_shared_fetch():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def handler(request):
            calls.append(request)
            started.set()
            await release.wait()
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=1900)).encode()))

        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: 2000)
        try:
            abandoned = asyncio.create_task(service.get("nodeseek", "daily"))
            other = asyncio.create_task(service.get("nodeseek", "daily"))
            await started.wait()
            abandoned.cancel()
            with pytest.raises(asyncio.CancelledError):
                await abandoned
            release.set()
            assert (await other)["status"] == "ready"
            assert len(calls) == 1
        finally:
            await service.aclose()

    asyncio.run(scenario())


def test_shutdown_cancels_background_refresh_before_closing_http():
    async def scenario():
        now = [2000]
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def handler(request):
            if now[0] > 2000:
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return httpx.Response(200, stream=Chunks(json.dumps(snapshot(now=1900)).encode()))

        service = HotlistService(transport=httpx.MockTransport(handler), clock=lambda: now[0])
        await service.get("nodeseek", "daily")
        now[0] += 601
        assert (await service.get("nodeseek", "daily"))["refreshing"]
        await started.wait()
        await service.aclose()
        assert cancelled.is_set() and not service.pending and service.client.is_closed
        with pytest.raises(RuntimeError, match="closed"):
            await service.get("nodeseek", "daily")

    asyncio.run(scenario())
