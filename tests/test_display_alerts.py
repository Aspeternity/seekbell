import asyncio
import copy
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    AlertDelivery,
    AlertSettings,
    DeliveredPost,
    Outbox,
    SeenPost,
    Source,
    SystemEvent,
    SystemState,
    WorkspacePreferences,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.notifiers.http import HTTPNotifier
from seekbell.notifiers.smtp import SMTPNotifier
from seekbell.services.alerts import AlertWorker, get_settings, update_settings
from seekbell.services.configuration import Configuration
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.ingestion import Ingestion
from seekbell.services.retention import HistoryRetention
from sqlalchemy import event, func, inspect, select
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.notifier_helpers import CONFIGS
from tests.runtime_helpers import SyntheticScenario
from tests.test_management import CREDENTIALS, authenticate, target
from tests.test_notifier_smtp import SMTPServer, install
from tests.test_runtime import until


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path))


@pytest.fixture
def configured(app):
    with TestClient(app) as client:
        authenticate(client)
        key = target(client, enabled=True)
        settings = get_settings(app.state.engine)
        update_settings(app.state.engine, True, [key], settings["revision"])
        yield app, client, key


class Probe:
    def __init__(self, result="success"):
        self.calls, self.result = [], result

    async def send(self, snapshot, message):
        self.calls.append((copy.deepcopy(snapshot), copy.deepcopy(message)))
        if self.result == "exception":
            raise OSError("synthetic-private-alert-value")
        if self.result == "timeout":
            await asyncio.sleep(1)
        return SendResult(status=self.result)


def count(engine, model):
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def fault(engine, at=100, code="http_503"):
    return Ingestion(engine).record_failure("nodeseek-rss", code, at=at)


def enable_source(engine):
    with write_session(engine) as session:
        session.get(Source, "nodeseek-rss").enabled = True


def test_setup_initializes_timezone_atomically_and_login_does_not_overwrite(app):
    with TestClient(app) as client:
        csrf = client.get("/api/auth/status").json()["csrf"]
        response = client.post(
            "/api/auth/setup",
            json={**CREDENTIALS, "timezone": "Asia/Tokyo"},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        assert client.get("/api/manage/workspace").json()["settings"]["timezone"] == "Asia/Tokyo"
        display = client.get("/api/manage/display").json()
        response = client.put(
            "/api/manage/display",
            json={"timezone": "America/Los_Angeles", "revision": display["revision"]},
        )
        assert response.status_code == 200
        assert (
            client.put(
                "/api/manage/display", json={"timezone": "UTC", "revision": display["revision"]}
            ).status_code
            == 409
        )
        client.post("/api/auth/logout")
        authenticate(client, setup=False)
        assert client.get("/api/manage/display").json()["timezone"] == "America/Los_Angeles"
        assert client.get("/api/manage/display").headers["cache-control"] == "no-store"


@pytest.mark.parametrize("zone", ["Invalid/Zone", "/etc/passwd", "../UTC", "localtime"])
def test_invalid_setup_and_saved_timezones_are_rejected_without_changing_state(app, zone):
    with TestClient(app) as client:
        csrf = client.get("/api/auth/status").json()["csrf"]
        assert (
            client.post(
                "/api/auth/setup",
                json={**CREDENTIALS, "timezone": zone},
                headers={"X-CSRF-Token": csrf},
            ).status_code
            == 422
        )
        assert not client.get("/api/auth/status").json()["initialized"]
        authenticate(client)
        original = client.get("/api/manage/display").json()
        assert (
            client.put(
                "/api/manage/display", json={"timezone": zone, "revision": original["revision"]}
            ).status_code
            == 422
        )
        assert client.get("/api/manage/display").json() == original
        del client.headers["X-CSRF-Token"]
        assert (
            client.put(
                "/api/manage/display", json={"timezone": "UTC", "revision": original["revision"]}
            ).status_code
            == 403
        )


def test_source_transitions_are_atomic_ordered_once_per_target_and_survive_new_worker(configured):
    app, client, key = configured
    engine = app.state.engine
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda at: fault(engine, at), (100, 101, 102)))
    assert count(engine, SystemEvent) == count(engine, AlertDelivery) == 1
    enable_source(engine)
    Ingestion(engine).ingest("nodeseek-rss", batch(9001), at=103)
    assert count(engine, SystemEvent) == count(engine, AlertDelivery) == 2
    with engine.connect() as connection:
        ledger = connection.execute(select(SeenPost)).all()
    probe = Probe()
    for _ in range(4):
        asyncio.run(AlertWorker(engine, {"webhook": probe}).run_once())
    assert [message["alert"]["phase"] for _, message in probe.calls] == ["fault", "recovery"]
    assert all(
        message["type"] == "system_alert" and "post" not in message for _, message in probe.calls
    )
    assert count(engine, Outbox) == count(engine, DeliveredPost) == 0
    with engine.connect() as connection:
        assert connection.execute(select(SeenPost)).all() == ledger
    assert client.get("/api/manage/alerts/state").json()["total"] == 0
    history = client.get("/api/manage/alerts/history").json()
    assert history["total"] == 2
    detail = client.get("/api/manage/alerts/history/" + history["items"][0]["id"])
    assert (
        detail.status_code == 200
        and detail.json()["items"][0]["target_name"] == "Synthetic webhook"
    )
    assert "synthetic-secret" not in detail.text and "ciphertext" not in detail.text
    assert client.get("/api/manage/alerts/history?page_size=101").status_code == 422


def test_enabling_alerts_never_backfills_previous_fault_and_repeated_fault_is_suppressed(app):
    with TestClient(app) as client:
        authenticate(client)
        key = target(client, enabled=True)
        fault(app.state.engine)
        assert (
            count(app.state.engine, SystemEvent) == 1
            and count(app.state.engine, AlertDelivery) == 0
        )
        update_settings(app.state.engine, True, [key], 1)
        fault(app.state.engine, at=101)
        assert count(app.state.engine, AlertDelivery) == 0
        enable_source(app.state.engine)
        Ingestion(app.state.engine).ingest("nodeseek-rss", batch(9001), at=102)
        assert (
            count(app.state.engine, SystemEvent) == 2
            and count(app.state.engine, AlertDelivery) == 1
        )


@pytest.mark.parametrize(
    "result", ["permanent_error", "transient_error", "unknown", "exception", "timeout"]
)
def test_alert_send_failures_are_readable_do_not_retry_and_do_not_recurse(configured, result):
    app, client, key = configured
    fault(app.state.engine)
    probe = Probe(result)
    worker = AlertWorker(app.state.engine, {"webhook": probe}, timeout=0.02)
    assert asyncio.run(worker.run_once())
    assert not asyncio.run(worker.run_once()) and len(probe.calls) == 1
    assert count(app.state.engine, SystemEvent) == 1
    listing = client.get("/api/manage/alerts/history").json()
    response = client.get("/api/manage/alerts/history/" + listing["items"][0]["id"])
    expected = "unknown" if result in ("timeout", "exception") else result
    assert response.json()["items"][0]["result"] == expected
    assert "synthetic-private-alert-value" not in response.text
    assert client.get("/api/manage/alerts/state").json()["total"] == 1


def test_cancelled_send_leaves_unknown_and_is_not_claimed_again(configured):
    app, _, _ = configured
    fault(app.state.engine)

    async def exercise():
        started = asyncio.Event()

        class Blocked:
            async def send(self, snapshot, message):
                started.set()
                await asyncio.Event().wait()

        worker = AlertWorker(app.state.engine, {"webhook": Blocked()})
        task = asyncio.create_task(worker.run_once())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not await worker.run_once()

    asyncio.run(exercise())
    with Session(app.state.engine) as session:
        item = session.scalars(select(AlertDelivery)).one()
        assert item.result == "unknown" and item.started_at is not None and item.finished_at is None


def test_disable_deselect_and_target_dependency_cancel_waiting_but_keep_evidence(configured):
    app, client, key = configured
    engine = app.state.engine
    fault(engine)
    assert client.delete("/api/manage/targets/" + key).status_code == 409
    old = get_settings(engine)
    updated = update_settings(engine, False, [key], old["revision"], at=110)
    assert client.put("/api/manage/alerts", json={**old, "enabled": False}).status_code == 409
    assert client.delete("/api/manage/targets/" + key).status_code == 409
    update_settings(engine, False, [], updated["revision"])
    assert client.delete("/api/manage/targets/" + key).status_code == 200
    with Session(engine) as session:
        item = session.scalars(select(AlertDelivery)).one()
        assert item.result == "cancelled" and item.finished_at == 110
    assert count(engine, SystemEvent) == 1


def test_paused_targets_only_get_cancelled_alert_records_and_reenable_never_replays(configured):
    app, _, key = configured
    config = Configuration(app.state.engine, app.state.vault)
    config.set_target_enabled(key, False, at=90)
    fault(app.state.engine)
    config.set_target_enabled(key, True, at=101)
    probe = Probe()
    assert not asyncio.run(AlertWorker(app.state.engine, {"webhook": probe}).run_once())
    assert not probe.calls
    with Session(app.state.engine) as session:
        assert session.scalars(select(AlertDelivery)).one().result == "cancelled"


def test_retention_preserves_transition_anchor_after_pruning_event_history(configured):
    app, _, key = configured
    fault(app.state.engine)
    asyncio.run(AlertWorker(app.state.engine, {"webhook": Probe()}, clock=lambda: 101).run_once())
    # Initial admin exists. Readable event can expire, transition anchor cannot.
    result = HistoryRetention(app.state.engine).run_once(at=100 + 40 * 86400)
    assert result["counts"]["system_events"] == result["counts"]["alerts"] == 1
    assert count(app.state.engine, SystemEvent) == 0
    fault(app.state.engine, at=100 + 40 * 86400 + 1)
    assert count(app.state.engine, SystemEvent) == 0
    with Session(app.state.engine) as session:
        assert session.get(SystemState, "source:nodeseek-rss").generation == 1


def test_automatic_target_fault_recovery_ignores_results_from_an_old_configuration(configured):
    app, _, key = configured
    engine = app.state.engine
    config = Configuration(engine, app.state.vault)
    config.create_task("Synthetic rule", Rule(), [key], at=1)
    enable_source(engine)
    Ingestion(engine).ingest("nodeseek-rss", batch(9001), at=10)
    Ingestion(engine).ingest("nodeseek-rss", batch(9001, 9002), at=20)
    worker = DeliveryWorker(engine, {})
    claim = worker.claim(at=20)
    worker.finish(claim, SendResult(status="transient_error", code="http_retry"), at=21)
    retry = worker.claim(at=30)
    worker.finish(retry, SendResult(status="success"), at=31)
    with Session(engine) as session:
        assert not session.get(SystemState, "delivery:" + key).fault
    assert count(engine, SystemEvent) == 2
    # A stale attempt with unchanged credentials must not regress recovered health.
    assert not worker.finish(
        claim, SendResult(status="permanent_error", code="late_rejection"), at=32
    )
    with Session(engine) as session:
        assert not session.get(SystemState, "delivery:" + key).fault
    assert count(engine, SystemEvent) == 2
    config.update_target(key, name="Changed target", config={})
    worker.finish(claim, SendResult(status="permanent_error", code="old_credentials"), at=32)
    assert count(engine, SystemEvent) == 2


def test_runtime_fault_still_sends_alert_and_restart_records_one_recovery(tmp_path, caplog):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        authenticate(client)
        key = target(client, enabled=True)
        data = client.get("/api/manage/alerts").json()
        assert (
            client.put(
                "/api/manage/alerts",
                json={"enabled": True, "target_ids": [key], "revision": data["revision"]},
            ).status_code
            == 200
        )
    scenario = SyntheticScenario()

    def failing(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)

        async def fail(stop):
            await asyncio.sleep(0.05)
            raise RuntimeError("synthetic-private-runtime-alert")

        runtime.worker.run = fail
        return runtime

    app = create_app(settings, runtime_factory=failing)
    with TestClient(app) as client:
        until(lambda: scenario.sends)
        assert client.get("/health/ready").status_code == 503
        assert scenario.sends[-1]["alert"]["phase"] == "fault"
        assert "synthetic-private-runtime-alert" not in caplog.text
    recovered = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(recovered):
        until(lambda: len(scenario.sends) == 2)
        assert scenario.sends[-1]["alert"]["phase"] == "recovery"
    assert len(scenario.sends) == 2


@pytest.mark.parametrize("kind", ["telegram", "bark", "webhook", "smtp"])
def test_system_alert_has_a_separate_plaintext_or_versioned_wire_contract(monkeypatch, kind):
    message = {
        "schema_version": 2,
        "event_id": "synthetic-system-alert",
        "type": "system_alert",
        "alert": {
            "id": "synthetic-event",
            "phase": "fault",
            "component": "source:nodeseek-rss",
            "label": "NodeSeek <img src=x>",
            "code": "http_503",
            "at": 100,
        },
    }
    if kind == "smtp":
        server = SMTPServer()
        install(monkeypatch, server)
        from seekbell.notifiers.configs import validate_config

        result = asyncio.run(SMTPNotifier().send(validate_config(kind, CONFIGS[kind]), message))
        assert result.status == "success"
        mail = next(call[1] for call in server.calls if call[0] == "data")
        assert "系统故障" in str(mail["Subject"]) and mail.get_content_type() == "text/plain"
        return

    def handle(request):
        body = json.loads(request.content)
        if kind == "telegram":
            assert "系统故障" in body["text"] and "parse_mode" not in body
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 7}})
        if kind == "bark":
            assert "系统故障" in body["title"] and "url" not in body
            return httpx.Response(200, json={"code": 200})
        assert body["schema_version"] == 2 and body["type"] == "system_alert"
        assert "post" not in body and request.headers["Idempotency-Key"] == message["event_id"]
        return httpx.Response(200, json={"ok": True})

    from seekbell.notifiers.configs import validate_config

    async def exercise():
        notifier = HTTPNotifier(kind, transport=httpx.MockTransport(handle))
        try:
            return await notifier.send(validate_config(kind, CONFIGS[kind]), message)
        finally:
            await notifier.aclose()

    assert asyncio.run(exercise()).status == "success"


def test_new_schema_upgrade_keeps_legacy_timezone_and_rolls_back_on_failure(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0008_retention")

        def fail(_c, _cursor, statement, _params, _context, _many):
            if "CREATE TABLE alert_deliveries" in statement:
                raise RuntimeError("synthetic alert migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        try:
            with pytest.raises(RuntimeError):
                migrate(engine)
        finally:
            event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0008_retention"
        assert "timezone" not in {
            c["name"] for c in inspect(engine).get_columns("workspace_preferences")
        }
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            assert session.get(WorkspacePreferences, 1).timezone == "Asia/Shanghai"
            assert not session.get(AlertSettings, 1).enabled
    finally:
        engine.dispose()


def test_only_retained_alert_ciphertext_still_requires_original_installation_key(tmp_path):
    from cryptography.fernet import Fernet

    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        authenticate(client)
        key = target(client, enabled=True)
        update_settings(app.state.engine, True, [key], 1)
        fault(app.state.engine)
        update_settings(app.state.engine, False, [], 2)
        assert client.delete("/api/manage/targets/" + key).status_code == 200
    key_path = tmp_path / "credentials.key"
    original = key_path.read_bytes()
    key_path.unlink()
    with pytest.raises(ValueError, match="key"), TestClient(create_app(settings)):
        pass
    assert not key_path.exists()
    key_path.write_bytes(Fernet.generate_key())
    key_path.chmod(0o600)
    with pytest.raises(ValueError, match="key"), TestClient(create_app(settings)):
        pass
    key_path.write_bytes(original)
    with TestClient(create_app(settings)) as client:
        authenticate(client, setup=False)
        records = client.get("/api/manage/alerts/history").json()
        detail = client.get("/api/manage/alerts/history/" + records["items"][0]["id"]).json()
        assert detail["items"][0]["result"] == "cancelled"


def test_pending_and_unfinished_alerts_protect_expired_event_history(configured):
    app, _, _ = configured
    fault(app.state.engine)
    cleaner = HistoryRetention(app.state.engine)
    at = 100 + 40 * 86400
    assert cleaner.run_once(at=at)["counts"]["system_events"] == 0
    claim = AlertWorker(app.state.engine, {}, clock=lambda: 100)._claim()
    assert claim is not None
    with write_session(app.state.engine) as session:
        from seekbell.db.models import RetentionPolicy

        session.get(RetentionPolicy, 1).next_run_at = 0
    assert cleaner.run_once(at=at + 1)["counts"]["system_events"] == 0
    with Session(app.state.engine) as session:
        delivery = session.get(AlertDelivery, claim[0])
        assert delivery.result == "unknown" and delivery.finished_at is None
