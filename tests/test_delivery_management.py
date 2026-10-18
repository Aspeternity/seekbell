import asyncio
import copy
import json
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    DeliveryAttempt,
    ManualDeliveryAttempt,
    Outbox,
    RuleHit,
    SeenPost,
    TargetTestAttempt,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.main import create_app
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.explicit_sending import SendConflict
from seekbell.services.manual_delivery import ManualDelivery
from seekbell.services.runtime import ApplicationRuntime
from seekbell.services.target_testing import TargetTesting
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.core_helpers import RecordingNotifier, batch
from tests.notifier_helpers import CONFIGS
from tests.test_management import target, task


def request_body(revision=1, key=None):
    return {"request_id": key or str(uuid4()), "expected_revision": revision, "confirmed": True}


def record_count(engine, model):
    with Session(engine) as session:
        return len(session.scalars(select(model)).all())


def queued(managed):
    client, app, _ = managed
    notification = target(client)
    task(client, notification["id"], rule={})
    app.state.configuration.set_source_enabled("nodeseek-rss", True, at=1)
    from seekbell.services.ingestion import Ingestion

    ingestion = Ingestion(app.state.engine)
    ingestion.ingest("nodeseek-rss", batch(9001), at=10)
    ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=20)
    with Session(app.state.engine) as session:
        event_id = session.scalars(select(Outbox.id)).one()
    return notification, event_id


def terminal(managed):
    notification, event_id = queued(managed)
    _, app, _ = managed
    asyncio.run(
        DeliveryWorker(
            app.state.engine, {"webhook": RecordingNotifier()}, clock=lambda: 30
        ).run_once()
    )
    return notification, event_id


@pytest.mark.parametrize("kind", CONFIGS)
def test_target_send_api_works_for_disabled_targets_and_is_idempotent(managed, kind):
    client, app, _ = managed
    value = client.post(
        "/api/manage/targets",
        json={"name": "synthetic " + kind, "kind": kind, "config": CONFIGS[kind], "enabled": False},
    ).json()
    recorder = RecordingNotifier()
    app.state.runtime.target_testing.notifiers = {kind: recorder}
    body = request_body(value["revision"])
    a = client.post(f"/api/manage/targets/{value['id']}/test", json=body)
    b = client.post(f"/api/manage/targets/{value['id']}/test", json=body)
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert a.json()["result"] == "success" and len(recorder.calls) == 1
    result = client.get(
        "/api/manage/deliveries", params={"kind": "test", "target_id": value["id"]}
    ).json()
    assert result["total"] == 1 and result["items"][0]["target_revision"] == 1
    detail = client.get(
        "/api/manage/deliveries/" + body["request_id"], params={"kind": "test"}
    ).json()
    assert detail["current_target"]["enabled"] is False and detail["attempts"] == []
    assert "config_ciphertext" not in json.dumps([a.json(), detail, result])
    for model in (Outbox, DeliveredPost, SeenPost, RuleHit, ManualDeliveryAttempt):
        assert record_count(app.state.engine, model) == 0


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/deliveries"),
        ("GET", "/deliveries/missing"),
        ("POST", "/targets/missing/test"),
        ("POST", "/deliveries/missing/resend"),
    ],
)
def test_delivery_management_requires_authentication(tmp_path, method, path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert (
            client.request(
                method, "/api/manage" + path, json=request_body() if method == "POST" else None
            ).status_code
            == 401
        )


@pytest.mark.parametrize("path", ["/targets/missing/test", "/deliveries/missing/resend"])
def test_explicit_send_requires_csrf_and_confirmation(managed, path):
    client, app, _ = managed
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/manage" + path, json=request_body()).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    for body in [
        {**request_body(), "confirmed": False},
        {**request_body(), "confirmed": 1},
        {**request_body(), "request_id": "bad"},
        {**request_body(), "config": {"secret": "synthetic-private"}},
    ]:
        assert client.post("/api/manage" + path, json=body).status_code == 422
    assert (
        record_count(app.state.engine, TargetTestAttempt)
        == record_count(app.state.engine, ManualDeliveryAttempt)
        == 0
    )


@pytest.mark.parametrize("status", ["success", "unknown", "permanent_error", "transient_error"])
def test_manual_resend_is_separate_and_preserves_all_automatic_evidence(managed, status):
    client, app, _ = managed
    notification, event_id = terminal(managed)
    with Session(app.state.engine) as session:
        original = session.get(Outbox, event_id)
        original_state = {
            c.name: copy.deepcopy(getattr(original, c.name)) for c in Outbox.__table__.columns
        }
    app.state.configuration.update_target(
        notification["id"],
        name="current target",
        config={"url": "https://new.example.invalid/changed"},
    )
    recorder = RecordingNotifier(
        SendResult(status=status, code="synthetic_result" if status != "success" else None)
    )
    app.state.runtime.manual_delivery.notifiers = {"webhook": recorder}
    body = request_body(2)
    a = client.post("/api/manage/deliveries/" + event_id + "/resend", json=body)
    assert a.status_code == 200 and a.json()["result"] == status
    assert (
        client.post("/api/manage/deliveries/" + event_id + "/resend", json=body).json() == a.json()
    )
    assert len(recorder.calls) == 1
    snapshot, payload = recorder.calls[0]
    assert snapshot["revision"] == 2 and snapshot["name"] == "current target"
    assert payload["event_id"] == body["request_id"] != event_id
    assert payload["post"]["title"].startswith("【手动重发】")
    assert payload["matched_tasks"] == original_state["payload"]["matched_tasks"]
    assert (
        app.state.configuration.vault.unseal(
            snapshot["id"], "webhook", snapshot["config_ciphertext"]
        )["url"]
        == "https://new.example.invalid/changed"
    )
    with Session(app.state.engine) as session:
        original = session.get(Outbox, event_id)
        assert {
            c.name: getattr(original, c.name) for c in Outbox.__table__.columns
        } == original_state
        assert session.scalars(select(DeliveredPost)).one().event_id == event_id
    assert (
        record_count(app.state.engine, DeliveredPost)
        == record_count(app.state.engine, DeliveryAttempt)
        == record_count(app.state.engine, ManualDeliveryAttempt)
        == 1
    )
    assert (
        asyncio.run(
            DeliveryWorker(app.state.engine, {"webhook": recorder}, clock=lambda: 1000).run_once()
        )
        is None
    )
    result = client.get(
        "/api/manage/deliveries", params={"kind": "manual", "status": status}
    ).json()
    assert result["total"] == 1 and result["items"][0]["original_event_id"] == event_id
    detail = client.get("/api/manage/deliveries/" + event_id).json()
    assert detail["status"] == "sent" and detail["attempts"][0]["result"] == "success"
    assert detail["target_revision"] == 1 and detail["current_target"]["revision"] == 2
    assert "ciphertext" not in json.dumps([detail, result])


@pytest.mark.parametrize("state", ["pending", "retry", "leased"])
def test_unfinished_automatic_events_cannot_be_manually_resent(managed, state):
    client, app, _ = managed
    _, event_id = queued(managed)
    with write_session(app.state.engine) as session:
        row = session.get(Outbox, event_id)
        row.status = state
        if state == "leased":
            row.lease_token, row.lease_until = str(uuid4()), 100
    assert (
        client.post(
            "/api/manage/deliveries/" + event_id + "/resend", json=request_body()
        ).status_code
        == 409
    )
    assert record_count(app.state.engine, ManualDeliveryAttempt) == 0


def test_resend_rejects_stale_config_disabled_target_and_missing_original(managed):
    client, app, _ = managed
    notification, event_id = terminal(managed)
    app.state.configuration.update_target(notification["id"], name="updated", config={})
    assert (
        client.post(
            "/api/manage/deliveries/" + event_id + "/resend", json=request_body()
        ).status_code
        == 409
    )
    app.state.configuration.set_target_enabled(notification["id"], False)
    assert (
        client.post(
            "/api/manage/deliveries/" + event_id + "/resend", json=request_body(2)
        ).status_code
        == 409
    )
    assert (
        client.post("/api/manage/deliveries/missing/resend", json=request_body()).status_code == 404
    )
    assert client.get("/api/manage/deliveries/missing").status_code == 404
    assert record_count(app.state.engine, ManualDeliveryAttempt) == 0


def test_result_unknown_and_idempotency_survive_service_recreation(core):
    core.queued()
    worker = DeliveryWorker(core.engine, {"mock": RecordingNotifier()}, clock=lambda: 30)
    asyncio.run(worker.run_once())
    event_id = core.one(Outbox).id
    key = str(uuid4())
    first = ManualDelivery(
        core.engine, {"mock": RecordingNotifier(SendResult(status="unknown", code="send_timeout"))}
    )
    asyncio.run(first.run(event_id, key=key, expected_revision=1))
    recorder = RecordingNotifier()
    second = ManualDelivery(core.engine, {"mock": recorder})
    asyncio.run(second.run(event_id, key=key, expected_revision=1))
    assert recorder.calls == [] and second.get_result(key)["result"] == "unknown"
    with pytest.raises(SendConflict):
        asyncio.run(
            TargetTesting(core.engine, {"mock": recorder}).run(
                core.target, key=key, expected_revision=1
            )
        )
    assert core.count(DeliveredPost) == 1


def test_explicit_shutdown_cancels_network_keeps_unknown_and_prevents_overlap(core):
    entered = asyncio.Event()

    class Hanging:
        async def send(self, *_):
            entered.set()
            await asyncio.Event().wait()

    async def exercise():
        runtime = ApplicationRuntime(
            core.engine, CredentialVault(Fernet.generate_key()), enabled=False, shutdown_grace=0.01
        )
        runtime.target_testing.notifiers = {"mock": Hanging()}
        await runtime.start()
        key = str(uuid4())
        running = asyncio.create_task(
            runtime.send_explicit("test", core.target, key=key, expected_revision=1)
        )
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(SendConflict):
            await runtime.send_explicit("test", core.target, key=str(uuid4()), expected_revision=1)
        await asyncio.wait_for(runtime.aclose(), 1)
        with pytest.raises(asyncio.CancelledError):
            await running
        result = runtime.target_testing.get_result(key)
        assert result["result"] == "unknown" and result["finished_at"] is None
        assert runtime.rss_client.is_closed

    asyncio.run(exercise())
    assert core.count(TargetTestAttempt) == 1


def test_delivery_filters_pagination_and_late_evidence_are_safe(managed):
    client, app, _ = managed
    _, event_id = terminal(managed)
    with write_session(app.state.engine) as session:
        event_row = session.get(Outbox, event_id)
        event_row.payload = {
            **event_row.payload,
            "post": {
                **event_row.payload["post"],
                "title": "<img src=x onerror=unsafe>",
                "url": "javascript:unsafe",
            },
        }
        attempt = session.scalars(select(DeliveryAttempt)).one()
        attempt.late_result, attempt.late_finished_at = "success", 40
    detail = client.get("/api/manage/deliveries/" + event_id).json()
    assert (
        detail["title"] == "<img src=x onerror=unsafe>"
        and detail["url"] == "https://www.nodeseek.com/post-9002-1"
    )
    assert detail["attempts"][0]["late_result"] == "success"
    assert (
        client.get(
            "/api/manage/deliveries", params={"status": "sent", "limit": 1, "offset": 1}
        ).json()["items"]
        == []
    )
    assert client.get("/api/manage/deliveries", params={"status": "failed"}).json()["total"] == 0
    assert client.get("/api/manage/deliveries", params={"kind": "invalid"}).status_code == 422
    assert client.get("/api/manage/deliveries", params={"limit": 101}).status_code == 422


def test_manual_migration_rolls_back_and_preserves_previous_data(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0005_source_revision")

        def fail(_connection, _cursor, statement, *_args):
            if "CREATE INDEX ix_manual_delivery" in statement:
                raise RuntimeError("synthetic migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="synthetic migration"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0005_source_revision"
        assert "manual_delivery_attempts" not in inspect(engine).get_table_names()
        migrate(engine)
        migrate(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT revision FROM sources")) == 1
        assert schema_revision(engine) == "0006_manual_deliveries"
    finally:
        engine.dispose()


@pytest.mark.parametrize("original_status", ["failed", "cancelled"])
def test_resending_failed_or_cancelled_event_does_not_create_automatic_receipt(
    managed, original_status
):
    client, app, _ = managed
    notification, event_id = queued(managed)
    if original_status == "cancelled":
        app.state.configuration.set_target_enabled(notification["id"], False)
        app.state.configuration.set_target_enabled(notification["id"], True)
    else:
        asyncio.run(
            DeliveryWorker(
                app.state.engine,
                {
                    "webhook": RecordingNotifier(
                        SendResult(status="permanent_error", code="synthetic_rejected")
                    )
                },
                clock=lambda: 30,
            ).run_once()
        )
    app.state.runtime.manual_delivery.notifiers = {"webhook": RecordingNotifier()}
    assert (
        client.post(
            "/api/manage/deliveries/" + event_id + "/resend",
            json=request_body(app.state.configuration.get_target(notification["id"])["revision"]),
        ).json()["result"]
        == "success"
    )
    assert client.get("/api/manage/deliveries/" + event_id).json()["status"] == original_status
    assert record_count(app.state.engine, DeliveredPost) == 0


def test_manual_wire_event_is_distinct_and_uses_current_encrypted_configuration(core):
    import httpx
    from seekbell.notifiers.registry import NotifierRegistry

    from tests.test_notification_integration import configured

    vault, config, targets = configured(core, ["webhook"])
    core.queued()
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(204)

    async def exercise():
        registry = NotifierRegistry(vault, http_transport=httpx.MockTransport(handle))
        try:
            await DeliveryWorker(core.engine, registry.notifiers, clock=lambda: 30).run_once()
            original = core.one(Outbox)
            config.update_target(
                targets["webhook"],
                name="updated",
                config={"url": "https://new.example.invalid/changed"},
            )
            sender = ManualDelivery(core.engine, registry.notifiers)
            key = str(uuid4())
            await sender.run(original.id, key=key, expected_revision=2)
            await sender.run(original.id, key=key, expected_revision=2)
            assert len(calls) == 2
            assert json.loads(calls[0].content)["event_id"] == original.id
            assert (
                json.loads(calls[1].content)["event_id"]
                == calls[1].headers["idempotency-key"]
                == key
            )
            assert str(calls[1].url) == "https://new.example.invalid/changed"
            assert json.loads(calls[1].content)["post"]["title"].startswith("【手动重发】")
        finally:
            await registry.aclose()

    asyncio.run(exercise())
    assert core.count(DeliveredPost) == core.count(ManualDeliveryAttempt) == 1
