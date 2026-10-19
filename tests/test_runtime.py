import asyncio
import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    DeliveryAttempt,
    Outbox,
    Post,
    RuleHit,
    SeenPost,
    Source,
    SourceRun,
    SourceState,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services.async_tools import storage_call
from seekbell.services.runtime import ApplicationRuntime
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.rss_samples import Chunks, rss
from tests.test_authentication import setup
from tests.test_management import target, task


class SimulatedServices:
    def __init__(self):
        self.ids = [9001]
        self.rss_calls = []
        self.deliveries = []
        self.rss_status = 200
        self.runtimes = []

    async def feed(self, request):
        assert str(request.url) == "https://rss.nodeseek.com/"
        self.rss_calls.append(request)
        if self.rss_status != 200:
            return httpx.Response(self.rss_status, headers={"Retry-After": "60"})
        return httpx.Response(
            200,
            headers={"content-type": "application/xml"},
            stream=Chunks(rss([{"id": key, "title": "VPS synthetic offer"} for key in self.ids])),
        )

    async def notify(self, request):
        self.deliveries.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    def factory(self, engine, vault, *, enabled):
        runtime = ApplicationRuntime(
            engine,
            vault,
            enabled=enabled,
            rss_transport=httpx.MockTransport(self.feed),
            notification_transport=httpx.MockTransport(self.notify),
            shutdown_grace=0.05,
        )
        runtime.source.jitter = lambda: 0
        self.runtimes.append(runtime)
        return runtime


def wait_for(predicate, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "Timed out waiting for simulated lifecycle"


def one(engine, model):
    with Session(engine) as session:
        return session.scalars(select(model)).one()


def count(engine, model):
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def site_update(client, enabled, interval=1):
    current = client.get("/api/manage/site").json()
    response = client.put(
        "/api/manage/site",
        json={
            "enabled": enabled,
            "interval_seconds": interval,
            "expected_revision": current["revision"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_paused_defaults_and_connection_probe_does_not_establish_baseline(tmp_path):
    simulated = SimulatedServices()
    app = create_app(
        Settings(data_dir=tmp_path, background_enabled=True), runtime_factory=simulated.factory
    )
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        assert client.get("/health/ready").status_code == 200
        status = client.get("/api/manage/overview").json()
        assert status["scheduler"]["components"] == {
            "collector": "running",
            "delivery": "running",
            "maintenance": "running",
        }
        assert not status["site"]["enabled"] and simulated.rss_calls == []
        probe = client.post("/api/manage/site/test", json={})
        assert probe.status_code == 200 and probe.json()["valid_count"] == 1
        assert len(simulated.rss_calls) == 1
        assert not one(app.state.engine, SourceState).initialized
        assert count(app.state.engine, SeenPost) == count(app.state.engine, Outbox) == 0
        assert count(app.state.engine, SourceRun) == 0
    runtime = simulated.runtimes[-1]
    assert runtime.rss_client.is_closed and all(task.done() for task in runtime._tasks)


def test_application_collects_delivers_rebaselines_on_pause_and_recovers_restart(tmp_path):
    simulated = SimulatedServices()
    settings = Settings(data_dir=tmp_path, background_enabled=True)

    def make_app():
        return create_app(settings, runtime_factory=simulated.factory)

    app = make_app()
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        notification = target(client)
        task(client, notification["id"], rule={})
        site_update(client, True)
        wait_for(lambda: one(app.state.engine, SourceState).initialized)
        assert not simulated.deliveries and count(app.state.engine, Outbox) == 0
        simulated.ids.append(9002)
        wait_for(lambda: count(app.state.engine, DeliveredPost) == 1)
        assert len(simulated.deliveries) == 1
        assert count(app.state.engine, RuleHit) == 1 and count(app.state.engine, Post) == 2
        filtered = client.get("/api/manage/content?matched_only=true").json()
        assert filtered["total"] == 1 and filtered["items"][0]["external_post_id"] == "9002"
        site_update(client, False)
        wait_for(lambda: not app.state.runtime.source._lock.locked())
        calls = len(simulated.rss_calls)
        site_update(client, False)
        time.sleep(0.1)
        assert len(simulated.rss_calls) == calls
        simulated.ids.append(9003)
        site_update(client, True)
        wait_for(lambda: one(app.state.engine, SourceState).window_count == 3)
        assert count(app.state.engine, DeliveredPost) == 1
        simulated.ids.append(9004)
        wait_for(lambda: count(app.state.engine, DeliveredPost) == 2)
        cookie = client.cookies["seekbell_session"]
    simulated.ids.append(9005)
    restarted = make_app()
    with TestClient(restarted) as client:
        client.cookies.set("seekbell_session", cookie, domain="testserver.local")
        assert client.get("/api/auth/state").json()["authenticated"]
        wait_for(lambda: count(restarted.state.engine, DeliveredPost) == 3)
        assert len(simulated.deliveries) == 3
        assert not one(restarted.state.engine, SourceState).needs_baseline
        assert count(restarted.state.engine, Outbox) == 3
    assert all(runtime.rss_client.is_closed for runtime in simulated.runtimes)


def test_manual_probe_backoff_cannot_be_bypassed_by_site_edits(tmp_path):
    simulated = SimulatedServices()
    simulated.rss_status = 429
    app = create_app(
        Settings(data_dir=tmp_path, background_enabled=True), runtime_factory=simulated.factory
    )
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        first = client.post("/api/manage/site/test", json={}).json()
        assert first["status"] == "failure" and first["code"] == "http_429"
        assert first["next_attempt_at"] >= first["at"] + 59
        current = site_update(client, True)
        assert current["next_attempt_at"] >= first["next_attempt_at"]
        second = client.post("/api/manage/site/test", json={}).json()
        assert second["status"] == "backoff" and len(simulated.rss_calls) == 1
        assert (
            client.get("/health/live").status_code == client.get("/health/ready").status_code == 200
        )
        assert (
            count(app.state.engine, Post) == 0
            and not one(app.state.engine, SourceState).initialized
        )


def test_unexpected_background_failure_is_redacted_and_changes_readiness(tmp_path, caplog):
    simulated = SimulatedServices()

    def failing_factory(engine, vault, *, enabled):
        runtime = simulated.factory(engine, vault, enabled=enabled)

        async def fail(*args, **kwargs):
            raise RuntimeError("synthetic-private-loop-value")

        runtime.source.run = fail
        return runtime

    app = create_app(
        Settings(data_dir=tmp_path, background_enabled=True), runtime_factory=failing_factory
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        assert "synthetic-private-loop-value" not in caplog.text
        assert "background_collector_failed" in caplog.text


def test_shutdown_cancels_unfinished_network_and_leaves_recoverable_lease(core):
    core.queued()
    simulated = SimulatedServices()
    simulated.ids = [9001, 9002]
    entered = asyncio.Event()

    class Hanging:
        async def send(self, *_):
            entered.set()
            await asyncio.Event().wait()

    async def exercise():
        from cryptography.fernet import Fernet
        from seekbell.notifiers.credentials import CredentialVault

        runtime = simulated.factory(
            core.engine, CredentialVault(Fernet.generate_key()), enabled=True
        )
        runtime.worker.notifiers = {"mock": Hanging()}
        await runtime.start()
        await asyncio.wait_for(entered.wait(), timeout=2)
        await asyncio.wait_for(runtime.aclose(), timeout=2)
        assert all(task.done() for task in runtime._tasks)
        assert runtime.rss_client.is_closed

    asyncio.run(exercise())
    assert core.one(Outbox).status == "leased"
    assert core.one(DeliveryAttempt).result == "in_progress"


def test_cancelled_storage_work_drains_before_returning():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def operation():
        entered.set()
        assert release.wait(timeout=2)
        finished.set()

    async def exercise():
        running = asyncio.create_task(storage_call(operation))
        assert await asyncio.to_thread(entered.wait, 1)
        running.cancel()
        await asyncio.sleep(0.01)
        assert not running.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert finished.is_set()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/site", "GET", None),
        ("/site", "PUT", {}),
        ("/site/test", "POST", {}),
        ("/overview", "GET", None),
        ("/content", "GET", None),
        ("/content/options", "GET", None),
    ],
)
def test_new_management_routes_require_authentication(tmp_path, path, method, body):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert client.request(method, "/api/manage" + path, json=body).status_code == 401


@pytest.mark.parametrize("path", ["/site", "/site/test"])
def test_site_writes_require_csrf(managed, path):
    client, _, _ = managed
    client.headers.pop("X-CSRF-Token")
    response = client.request("PUT" if path == "/site" else "POST", "/api/manage" + path, json={})
    assert response.status_code == 403


def test_source_revision_and_fixed_scope(managed):
    client, app, _ = managed
    current = client.get("/api/manage/site").json()
    updated = site_update(client, True, 30)
    assert updated["revision"] == current["revision"] + 1
    assert (
        client.put(
            "/api/manage/site",
            json={
                "enabled": False,
                "interval_seconds": 30,
                "expected_revision": current["revision"],
            },
        ).status_code
        == 409
    )
    assert one(app.state.engine, Source).enabled
    assert (
        client.put(
            "/api/manage/site",
            json={
                "enabled": False,
                "interval_seconds": 0,
                "expected_revision": updated["revision"],
            },
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/manage/site",
            json={
                "enabled": False,
                "interval_seconds": 30,
                "expected_revision": updated["revision"],
                "url": "https://other.example.invalid/",
            },
        ).status_code
        == 422
    )


def test_content_filters_preserve_historical_versions_and_do_not_write(managed):
    client, app, _ = managed
    notification = target(client)
    monitor = task(client, notification["id"], rule={})
    config = app.state.configuration
    config.set_source_enabled("nodeseek-rss", True, at=1)
    from seekbell.services.ingestion import Ingestion

    ingestion = Ingestion(app.state.engine)
    ingestion.ingest("nodeseek-rss", batch(9001, title="ordinary", author="alice"), at=10)
    ingestion.ingest(
        "nodeseek-rss",
        batch(9001, 9002, title="100%_offer", author="Alice", category="Offers", summary=""),
        at=20,
    )
    with write_session(app.state.engine) as session:
        post = session.get(Post, ("nodeseek", "9002"))
        post.url = "javascript:unsafe"
        post.summary = "<img src=x onerror=unsafe>" + "x" * 70000
    before = (
        count(app.state.engine, SeenPost),
        count(app.state.engine, Outbox),
        count(app.state.engine, RuleHit),
    )
    result = client.get(
        "/api/manage/content",
        params={
            "query": "%_",
            "author": "Alice",
            "category": "Offers",
            "matched_only": True,
        },
    ).json()
    assert result["total"] == 1 and result["items"][0]["external_post_id"] == "9002"
    post = result["items"][0]
    assert post["url"] == "https://www.nodeseek.com/post-9002-1"
    assert len(post["summary"]) == 65536 and post["display_truncated"]
    assert post["hits"][0]["version"] == 1
    assert client.get("/api/manage/content", params={"author": "alice"}).json()["total"] == 1
    assert client.get("/api/manage/content", params={"limit": 1}).json()["total"] == 2
    assert (
        client.get("/api/manage/content", params={"offset": 1, "limit": 1}).json()["items"][0][
            "external_post_id"
        ]
        == "9001"
    )
    assert client.delete("/api/manage/tasks/" + monitor["id"]).status_code == 204
    options = client.get("/api/manage/content/options").json()
    assert options[0]["deleted"]
    historical = client.get("/api/manage/content", params={"task_id": monitor["id"]}).json()
    assert historical["items"][0]["hits"][0]["deleted"]
    assert before == (
        count(app.state.engine, SeenPost),
        count(app.state.engine, Outbox),
        count(app.state.engine, RuleHit),
    )
    assert client.get("/api/manage/content", params={"limit": 101}).status_code == 422


def test_source_revision_migration_preserves_config_and_rolls_back_fault(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0004_authentication")
        with engine.begin() as connection:
            connection.execute(text("UPDATE sources SET enabled=1,interval_seconds=17"))

        def fail(_connection, _cursor, statement, *_args):
            if "ADD COLUMN revision" in statement:
                raise RuntimeError("synthetic migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="synthetic migration"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0004_authentication"
        assert "revision" not in {c["name"] for c in inspect(engine).get_columns("sources")}
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            source = session.get(Source, "nodeseek-rss")
            assert source.enabled and source.interval_seconds == 17 and source.revision == 1
    finally:
        engine.dispose()


def test_background_loop_auto_recovers_after_transient_fault(tmp_path):
    simulated = SimulatedServices()
    attempts = 0

    def recovering_factory(engine, vault, *, enabled):
        runtime = simulated.factory(engine, vault, enabled=enabled)
        runtime.recovery_backoff = 0.02
        real_run = runtime.source.run

        async def flaky_run(stop, *, wake=None, on_cycle=None):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient-collector-fault")
            await real_run(stop, wake=wake, on_cycle=on_cycle)

        runtime.source.run = flaky_run
        return runtime

    app = create_app(
        Settings(data_dir=tmp_path, background_enabled=True),
        runtime_factory=recovering_factory,
    )
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        wait_for(lambda: attempts >= 2 and client.get("/health/ready").status_code == 200)
        overview = client.get("/api/manage/overview").json()
        assert overview["scheduler"]["healthy"]
        assert overview["scheduler"]["restarts"]["collector"] >= 1
