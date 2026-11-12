import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import DeliveredPost, DeliveryAttempt, Outbox, Post, SourceState
from seekbell.db.transactions import database_call, write_session
from seekbell.main import create_app
from seekbell.services.runtime import Runtime
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.runtime_helpers import SyntheticScenario
from tests.test_management import authenticate, target, task_values


def until(check, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("Synthetic runtime did not reach the expected state")


def count(app, model):
    with Session(app.state.engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def state(app):
    with Session(app.state.engine) as session:
        return session.get(SourceState, "nodeseek-rss")


def due(app):
    with write_session(app.state.engine) as session:
        session.get(SourceState, "nodeseek-rss").next_attempt_at = 0


def configure(client):
    authenticate(client)
    assert client.post("/api/manage/websites", json={"adapter_id": "nodeseek"}).status_code == 201
    key = target(client, enabled=True)
    values = {**task_values(key), "enabled": True}
    assert client.post("/api/manage/tasks", json=values).status_code == 201
    return key


def website(client, enabled=True, interval=10):
    response = client.put(
        "/api/manage/websites/nodeseek", json={"enabled": enabled, "interval": interval}
    )
    assert response.status_code == 200, response.text


def test_production_default_starts_without_fetching_before_admin_or_site(tmp_path, monkeypatch):
    # Explicitly exercise the normal constructor, overriding only test network IO.
    import seekbell.main as main

    scenario = SyntheticScenario()
    monkeypatch.setattr(main, "Runtime", scenario.factory)
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))
    with TestClient(app) as client:
        assert client.get("/health/ready").status_code == 200
        assert app.state.runtime.active
        time.sleep(0.1)
        assert not scenario.fetches and not scenario.sends
        authenticate(client)
        time.sleep(0.1)
        assert client.get("/api/manage/runtime").json()["active"]
        assert not scenario.fetches
    assert app.state.runtime.status == "stopped"
    assert app.state.runtime.client.is_closed
    assert all(t.done() for t in app.state.runtime.tasks.values())


def test_automatic_baseline_matches_delivery_continue_after_logout_and_restart(tmp_path):
    scenario = SyntheticScenario()
    settings = Settings(data_dir=tmp_path, static_dir=tmp_path / "static")
    app = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).initialized)
        assert count(app, Post) == 1 and count(app, Outbox) == 0
        scenario.items = [9001, 9002]
        due(app)
        until(lambda: count(app, DeliveredPost) == 1)
        assert len(scenario.sends) == 1
        data = client.get("/api/manage/overview").json()
        assert data["runtime_active"] and data["window"]["matches"] == 1
        assert data["window"]["delivered"] == 1
        client.post("/api/auth/logout")
        assert client.get("/api/manage/runtime").status_code == 401
        scenario.items = [9001, 9002, 9003]
        due(app)
        until(lambda: count(app, DeliveredPost) == 2)
    scenario.items = [9001, 9002, 9003, 9004]
    # Persisted initialized/seen ledger is reused; no rebaseline on process restart.
    restarted = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(restarted) as client:
        due(restarted)
        until(lambda: count(restarted, DeliveredPost) == 3)
        authenticate(client, setup=False)
        assert client.get("/api/manage/history/posts").json()["total"] == 4
        assert len(scenario.sends) == 3
        with Session(restarted.state.engine) as session:
            assert session.get(Post, ("nodeseek", "9001")).baseline
            assert not session.get(Post, ("nodeseek", "9004")).baseline


def test_pause_resume_rebaselines_and_does_not_send_pause_period_posts(tmp_path):
    scenario = SyntheticScenario()
    app = create_app(Settings(data_dir=tmp_path), runtime_factory=scenario.factory)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).initialized)
        website(client, False)
        before = len(scenario.fetches)
        scenario.items = [9001, 9002]
        due(app)
        time.sleep(0.15)
        assert len(scenario.fetches) == before and not scenario.sends
        website(client)
        until(lambda: count(app, Post) == 2)
        assert not scenario.sends
        scenario.items = [9001, 9002, 9003]
        due(app)
        until(lambda: count(app, DeliveredPost) == 1)
        assert len(scenario.sends) == 1


def test_failure_backoff_survives_restart_and_frequency_changes_do_not_bypass_it(tmp_path):
    scenario = SyntheticScenario()
    scenario.failure = 429
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).failures == 1)
        saved = state(app)
        assert not saved.initialized and saved.next_attempt_at >= saved.last_attempt_at + 60
        website(client, interval=20)
        assert state(app).next_attempt_at == saved.next_attempt_at
        time.sleep(0.15)
        assert len(scenario.fetches) == 1
    restarted = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(restarted):
        time.sleep(0.15)
        assert len(scenario.fetches) == 1
        assert state(restarted).next_attempt_at == saved.next_attempt_at


def test_paused_long_interval_observes_enable_and_shorter_frequency_promptly(tmp_path):
    scenario = SyntheticScenario()
    app = create_app(Settings(data_dir=tmp_path), runtime_factory=scenario.factory)
    with TestClient(app) as client:
        configure(client)
        website(client, False, 3600)
        time.sleep(0.1)
        website(client, True, 3600)
        until(lambda: state(app).initialized)
        with write_session(app.state.engine) as session:
            row = session.get(SourceState, "nodeseek-rss")
            row.last_attempt_at = time.time() - 20
            row.next_attempt_at = time.time() + 3500
        scenario.items = [9001, 9002]
        website(client, True, 10)
        until(lambda: count(app, DeliveredPost) == 1)
        assert len(scenario.fetches) == 2
        website(client, True, 3600)
        saved = state(app)
        assert saved.next_attempt_at == saved.last_attempt_at + 3600


@pytest.mark.parametrize("actor", ["source", "worker", "retention", "alerts"])
def test_actor_failure_is_redacted_and_marks_runtime_and_readiness_failed(tmp_path, caplog, actor):
    scenario = SyntheticScenario()

    def factory(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)

        async def fail(stop):
            raise RuntimeError("synthetic-private-runtime-value")

        getattr(runtime, actor).run = fail
        return runtime

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        until(lambda: client.get("/health/ready").status_code == 503)
        assert client.get("/health/live").status_code == 200
        authenticate(client)
        status = client.get("/api/manage/runtime").json()
        assert not status["active"] and status["status"] == "failed"
        assert status["code"] in (
            "collection_stopped",
            "delivery_stopped",
            "retention_stopped",
            "alerts_stopped",
        )
        assert not client.get("/api/manage/overview").json()["runtime_active"]
        assert "synthetic-private" not in caplog.text
    assert all(t.done() for t in app.state.runtime.tasks.values())


def test_whole_fetch_deadline_records_failure_instead_of_hanging_shutdown(tmp_path):
    scenario = SyntheticScenario()

    def factory(engine, notifiers):
        scenario.block = asyncio.Event()
        runtime = scenario.factory(engine, notifiers)
        runtime.source.fetch_timeout = 0.05
        return runtime

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).last_error_code == "timeout")
        assert client.get("/health/ready").status_code == 200
    assert app.state.runtime.client.is_closed


def test_shutdown_allows_an_inflight_send_to_finish_before_disposal(tmp_path):
    scenario = SyntheticScenario()

    def factory(engine, notifiers):
        scenario.send_block = asyncio.Event()
        runtime = scenario.factory(engine, notifiers)
        runtime.shutdown_grace = 1
        return runtime

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).initialized)
        scenario.items = [9001, 9002]
        due(app)
        until(lambda: len(scenario.sends) == 1)
        timer = threading.Timer(0.05, lambda: client.portal.call(scenario.send_block.set))
        timer.start()
    timer.join()
    with Session(app.state.engine) as session:
        assert session.scalar(select(Outbox.status)) == "sent"
        assert session.scalar(select(func.count()).select_from(DeliveredPost)) == 1
    assert app.state.runtime.client.is_closed


def test_forced_shutdown_preserves_lease_and_restart_recovers_with_uncertainty(tmp_path):
    scenario = SyntheticScenario()

    def blocked(engine, notifiers):
        scenario.send_block = asyncio.Event()
        return scenario.factory(engine, notifiers)

    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, runtime_factory=blocked)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).initialized)
        scenario.items = [9001, 9002]
        due(app)
        until(lambda: len(scenario.sends) == 1)
    with Session(app.state.engine) as session:
        row = session.scalar(select(Outbox))
        assert row.status == "leased" and row.attempt_count == 1
        assert session.scalar(select(DeliveryAttempt.result)) == "in_progress"
    scenario.send_block = None
    resumed = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(resumed):
        time.sleep(0.1)
        assert len(scenario.sends) == 1
        with write_session(resumed.state.engine) as session:
            session.scalar(select(Outbox)).lease_until = 0
        until(lambda: count(resumed, DeliveredPost) == 1)
        with Session(resumed.state.engine) as session:
            row = session.scalar(select(Outbox))
            assert row.status == "sent" and row.uncertain and row.attempt_count == 2
            assert (
                session.scalar(select(DeliveryAttempt).where(DeliveryAttempt.sequence == 1)).result
                == "unknown"
            )


def test_cancelled_database_work_is_joined_before_clients_close(tmp_path):
    entered, release, completed = threading.Event(), threading.Event(), threading.Event()

    def blocking():
        entered.set()
        assert release.wait(3)
        completed.set()

    async def run():
        async def actor(stop):
            await database_call(blocking)

        # No enabled source or notifier request is needed to exercise actor ownership.
        from seekbell.db.runtime import create_database_engine, migrate

        engine = create_database_engine(Settings(data_dir=tmp_path))
        migrate(engine)
        runtime = Runtime(engine, {}, shutdown_grace=0.01)
        runtime.worker.run = actor
        try:
            await runtime.start()
            assert await asyncio.to_thread(entered.wait, 1)
            closing = asyncio.create_task(runtime.aclose())
            await asyncio.sleep(0.05)
            assert not closing.done() and not runtime.client.is_closed
            release.set()
            await closing
            assert completed.is_set() and runtime.client.is_closed
        finally:
            release.set()
            engine.dispose()

    asyncio.run(run())


def test_lifespan_routes_automatic_messages_through_encrypted_channel_registry(
    tmp_path, monkeypatch
):
    import json

    import httpx
    import seekbell.main as main
    from seekbell.notifiers.registry import NotifierRegistry

    scenario = SyntheticScenario()
    requests = []

    def handler(request):
        requests.append(request)
        assert request.url.host == "receiver.example.test"
        assert request.headers["x-test"] == "synthetic-header-secret"
        return httpx.Response(200, json={"ok": True})

    def registry(vault):
        return NotifierRegistry(vault, http_transport=httpx.MockTransport(handler))

    def factory(engine, notifiers):
        return Runtime(
            engine, notifiers, http_transport=httpx.MockTransport(scenario.feed), tick=0.03
        )

    monkeypatch.setattr(main, "NotifierRegistry", registry)
    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        configure(client)
        website(client)
        until(lambda: state(app).initialized)
        scenario.items = [9001, 9002]
        due(app)
        until(lambda: count(app, DeliveredPost) == 1)
        assert len(requests) == 1
        payload = json.loads(requests[0].content)
        assert payload["matched_tasks"][0]["name"] == "VPS radar"
        assert payload["event_id"] == requests[0].headers["idempotency-key"]


def test_a_container_stop_fits_dockers_default_ten_seconds():
    """Uvicorn first waits for open requests (a hotlist long poll lasts up to 25 s), then
    the runtime for its actors; both bounds together stay below Docker's SIGKILL."""
    import inspect
    import json
    import re
    from pathlib import Path

    root = Path(__file__).parents[1]
    command = json.loads(re.search(r"^CMD (\[.*\])$", (root / "Dockerfile").read_text(), re.M)[1])
    requests = float(command[command.index("--timeout-graceful-shutdown") + 1])
    actors = inspect.signature(Runtime).parameters["shutdown_grace"].default
    assert requests + actors < 10
    assert (
        f"timeout_graceful_shutdown={requests:g},"
        in (root / "backend/seekbell/__main__.py").read_text()
    )


def test_a_crash_during_startup_is_not_overwritten_by_its_startup_recovery(tmp_path):
    from seekbell.db.models import SystemEvent, SystemState

    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        authenticate(client)
    scenario = SyntheticScenario()

    def crashing(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)
        crash, loops = asyncio.Event(), []

        async def fail(stop):
            loops.append(asyncio.get_running_loop())
            await crash.wait()
            raise RuntimeError("synthetic startup crash")

        runtime.worker.run = fail
        original = runtime._runtime_transition

        def transition(name, fault):
            if name == "delivery" and not fault:
                # The crash and its fault land while startup is about to record recovery.
                loops[0].call_soon_threadsafe(crash.set)
                until(lambda: fault_written(engine))
            return original(name, fault)

        runtime._runtime_transition = transition
        return runtime

    def fault_written(engine):
        with Session(engine) as session:
            state = session.get(SystemState, "runtime:delivery")
            return state is not None and state.fault

    app = create_app(settings, runtime_factory=crashing)
    with TestClient(app):
        engine = app.state.engine
        until(lambda: fault_written(engine))
        time.sleep(0.2)
        assert fault_written(engine)
        with Session(engine) as session:
            phases = session.scalars(
                select(SystemEvent.phase).where(SystemEvent.component == "runtime:delivery")
            ).all()
        assert phases == ["fault"]
