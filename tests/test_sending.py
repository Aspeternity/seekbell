import asyncio
import copy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from seekbell.api.sending import services
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    ManualDelivery,
    Outbox,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.main import create_app
from seekbell.notifiers.registry import NotifierRegistry
from seekbell.services.configuration import Configuration
from seekbell.services.manual_sending import ConfiguredTargetTesting, ManualSending
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.history_helpers import PRIVATE, seed_history
from tests.notifier_helpers import CONFIGS
from tests.test_management import authenticate
from tests.test_notifier_smtp import SMTPServer, install


class Probe:
    def __init__(self, result="success", delay=0):
        self.result, self.delay, self.calls = result, delay, []

    async def send(self, snapshot, payload):
        self.calls.append((copy.deepcopy(snapshot), copy.deepcopy(payload)))
        await asyncio.sleep(self.delay)
        if self.result == "exception":
            raise OSError(PRIVATE)
        return SendResult(status=self.result)


@pytest.fixture
def sending(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        config = Configuration(app.state.engine, app.state.vault)
        config.update_target(ids["target"], name="当前目标名称", config={}, enabled=True)
        probe = Probe()
        tests = ConfiguredTargetTesting(app.state.engine, {"webhook": probe})
        manual = ManualSending(app.state.engine, {"webhook": probe})
        app.dependency_overrides[services] = lambda: (tests, manual)
        yield app, client, ids, probe


def intent(client, key, *, manual=False, request_id=None):
    prefix, action = ("deliveries", "resend") if manual else ("targets", "test")
    base = f"/api/manage/{prefix}/{key}/{action}"
    response = client.get(base + "-preview")
    assert response.status_code == 200, response.text
    return base, {"request_id": request_id or str(uuid4()), "revision": response.json()["revision"]}


def test_manual_uses_current_credentials_original_message_and_independent_idempotent_history(
    sending,
):
    app, client, ids, probe = sending
    with Session(app.state.engine) as session:
        event_before = session.get(Outbox, ids["sent"])
        original_payload = copy.deepcopy(event_before.payload)
        original_status = event_before.status
        receipt_before = session.get(
            DeliveredPost, ("nodeseek", "8001", ids["target"])
        ).delivered_at
    base, body = intent(client, ids["sent"], manual=True)
    response = client.post(base, json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_event_id"] == ids["sent"]
    assert data["target_name"] == "当前目标名称"
    assert data["tasks"]["items"][0]["name"] == "摘要关注"
    assert data["result"] == "success"
    assert response.headers["cache-control"] == "no-store"
    assert data["id"] == body["request_id"] != ids["sent"]
    assert PRIVATE not in response.text and "ciphertext" not in response.text
    assert "lease_token" not in response.text
    assert client.post(base, json=body).json()["id"] == data["id"]
    assert len(probe.calls) == 1
    assert probe.calls[0][1] == {
        **original_payload,
        "event_id": data["id"],
        "display_timezone": "UTC",
    }
    assert probe.calls[0][0]["name"] == "当前目标名称"
    with Session(app.state.engine) as session:
        original = session.get(Outbox, ids["sent"])
        assert original.payload == original_payload and original.status == original_status
        assert (
            session.get(DeliveredPost, ("nodeseek", "8001", ids["target"])).delivered_at
            == receipt_before
        )
        assert session.get(ManualDelivery, data["id"]).target_snapshot["config_ciphertext"]
        assert session.scalar(select(text("count(*)")).select_from(Outbox)) == 24
    listing = client.get(
        "/api/manage/history/manual", params={"source_event_id": ids["sent"]}
    ).json()
    assert listing["total"] == 1 and listing["items"][0]["id"] == data["id"]
    assert client.get("/api/manage/history/manual?q=%25_").json()["total"] == 0


@pytest.mark.parametrize("kind", ["telegram", "bark", "smtp", "webhook"])
def test_test_endpoint_runs_configured_channels_even_when_disabled(sending, monkeypatch, kind):
    app, client, ids, probe = sending
    config = Configuration(app.state.engine, app.state.vault)
    key = config.create_target("合成渠道", kind=kind, config=CONFIGS[kind], enabled=False)
    server = SMTPServer()
    install(monkeypatch, server)
    calls = []

    def handle(request):
        calls.append(request)
        if kind == "telegram":
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
        return httpx.Response(200, json={"code": 200, "ok": True})

    # Use the real registry within the endpoint loop, with simulated transports.
    class EndpointTester:
        async def run(self, target_id, **kwargs):
            registry = NotifierRegistry(app.state.vault, http_transport=httpx.MockTransport(handle))
            try:
                return await ConfiguredTargetTesting(app.state.engine, registry.notifiers).run(
                    target_id, **kwargs
                )
            finally:
                await registry.aclose()

    app.dependency_overrides[services] = lambda: (EndpointTester(), app.state.manual_sending)
    base, body = intent(client, key)
    response = client.post(base, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["result"] == "success"
    assert response.json()["kind"] == kind
    assert PRIVATE not in response.text
    assert sum(item[0] == "data" for item in server.calls) == (1 if kind == "smtp" else 0)
    assert len(calls) == (0 if kind == "smtp" else 1)


@pytest.mark.parametrize(
    "result", ["success", "unknown", "transient_error", "permanent_error", "exception"]
)
def test_manual_results_never_auto_retry_or_modify_source(sending, result):
    app, client, ids, probe = sending
    probe.result = result
    base, body = intent(client, ids["failed"], manual=True)
    response = client.post(base, json=body)
    assert response.status_code == 200
    assert response.json()["result"] == ("unknown" if result == "exception" else result)
    assert client.post(base, json=body).json()["id"] == body["request_id"]
    assert len(probe.calls) == 1
    with Session(app.state.engine) as session:
        assert session.get(Outbox, ids["failed"]).status == "failed"
        assert session.get(DeliveredPost, ("nodeseek", "8002", ids["target"])) is None


def test_authentication_csrf_origin_missing_target_and_revision_are_checked(sending):
    app, client, ids, probe = sending
    base, body = intent(client, ids["target"])
    assert client.post(base, json=body, headers={"X-CSRF-Token": ""}).status_code == 403
    assert (
        client.post(base, json=body, headers={"Origin": "https://other.example.test"}).status_code
        == 403
    )
    assert client.post(base, json={**body, "revision": 0}).status_code == 422
    assert client.post(base, json={**body, "request_id": "bad"}).status_code == 422
    assert client.post(base, json={**body, "config": PRIVATE}).status_code == 422
    assert client.get("/api/manage/targets/missing/test-preview").status_code == 404
    Configuration(app.state.engine, app.state.vault).update_target(
        ids["target"], name="changed", config={}
    )
    assert client.post(base, json=body).status_code == 409
    assert not probe.calls
    client.post("/api/auth/logout")
    assert client.post(base, json=body).status_code == 401
    assert client.get("/api/manage/history/manual").status_code == 401


def test_manual_rejects_paused_targets_and_nonterminal_automatic_events(sending):
    app, client, ids, probe = sending
    assert client.get(f"/api/manage/deliveries/{ids['leased']}/resend-preview").status_code == 409
    Configuration(app.state.engine, app.state.vault).set_target_enabled(ids["target"], False)
    assert client.get(f"/api/manage/deliveries/{ids['sent']}/resend-preview").status_code == 409
    assert not probe.calls
    # Explicit target testing remains available while paused.
    base, body = intent(client, ids["target"])
    assert client.post(base, json=body).status_code == 200


def test_reused_request_id_is_bound_to_the_original_operation(sending):
    app, client, ids, probe = sending
    base, body = intent(client, ids["sent"], manual=True)
    assert client.post(base, json=body).status_code == 200
    other = f"/api/manage/deliveries/{ids['failed']}/resend"
    assert client.post(other, json=body).status_code == 409
    test_base, test_body = intent(client, ids["target"])
    assert client.post(test_base, json=test_body).status_code == 200
    key = Configuration(app.state.engine, app.state.vault).create_target(
        "another", kind="webhook", config=CONFIGS["webhook"]
    )
    assert client.post(f"/api/manage/targets/{key}/test", json=test_body).status_code == 409
    assert len(probe.calls) == 2


def test_concurrent_duplicate_requests_dispatch_once_and_gate_is_bounded(sending):
    app, client, ids, probe = sending
    base, body = intent(client, ids["target"])
    csrf = client.headers["X-CSRF-Token"]
    cookie = client.cookies.get("seekbell_session")

    async def run():
        probe.delay = 0.15
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={"X-CSRF-Token": csrf, "Cookie": "seekbell_session=" + cookie},
        ) as concurrent:
            first = asyncio.create_task(concurrent.post(base, json=body))
            while not probe.calls:
                await asyncio.sleep(0.001)
            duplicate = await concurrent.post(base, json=body)
            assert duplicate.status_code == 200
            assert duplicate.json()["finished_at"] is None
            assert (await first).status_code == 200
            a = asyncio.create_task(
                concurrent.post(base, json={**body, "request_id": str(uuid4())})
            )
            b = asyncio.create_task(
                concurrent.post(base, json={**body, "request_id": str(uuid4())})
            )
            while len(probe.calls) < 3:
                await asyncio.sleep(0.001)
            rejected = await concurrent.post(base, json={**body, "request_id": str(uuid4())})
            assert rejected.status_code == 429
            await asyncio.gather(a, b)

    asyncio.run(asyncio.wait_for(run(), timeout=5))
    assert len(probe.calls) == 3


def test_timeout_and_cancellation_leave_durable_unknown_evidence(sending):
    app, client, ids, probe = sending
    probe.delay = 0.1
    tester = ConfiguredTargetTesting(app.state.engine, {"webhook": probe}, timeout=0.01)

    async def run():
        key = await tester.run(ids["target"])
        assert tester.get_result(key)["result"] == "unknown"
        key2 = str(uuid4())
        tester.timeout = 1
        task = asyncio.create_task(tester.run(ids["target"], key=key2))
        while len(probe.calls) < 2:
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert tester.get_result(key2)["finished_at"] is None
        await tester.run(ids["target"], key=key2)
        assert len(probe.calls) == 2

    asyncio.run(asyncio.wait_for(run(), timeout=5))


def test_manual_snapshot_remains_readable_when_original_is_pruned_and_paginates(sending):
    app, client, ids, probe = sending
    base, body = intent(client, ids["sent"], manual=True)
    result = client.post(base, json=body).json()
    with write_session(app.state.engine) as session:
        row = session.get(ManualDelivery, result["id"])
        row.source_event_id = "pruned-source"
        row.payload = {
            **row.payload,
            "matched_tasks": [{"name": "历史任务" + str(i), "version": 1} for i in range(24)],
        }
    value = client.get("/api/manage/history/manual/" + result["id"], params={"task_page": 2}).json()
    assert not value["source_exists"] and value["tasks"]["total"] == 24
    assert len(value["tasks"]["items"]) == 4
    assert client.get("/api/manage/history/manual/missing").status_code == 404


def test_manual_migration_preserves_existing_data_and_rolls_back(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0005_history")
        with engine.begin() as connection:
            before = list(
                connection.execute(
                    text("SELECT * FROM source_states WHERE source_id='nodeseek-rss'")
                )
            )

        def fail(c, cu, statement, p, ctx, many):
            if "CREATE INDEX ix_manual_target" in statement:
                raise RuntimeError("synthetic manual migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0005_history"
        assert "manual_deliveries" not in inspect(engine).get_table_names()
        migrate(engine)
        migrate(engine)
        assert schema_revision(engine) == "0013_site_order"
        with engine.connect() as connection:
            assert (
                list(
                    connection.execute(
                        text("SELECT * FROM source_states WHERE source_id='nodeseek-rss'")
                    )
                )
                == before
            )
    finally:
        engine.dispose()


def test_manual_evidence_survives_service_restart_without_repeating_send(tmp_path):
    settings = Settings(data_dir=tmp_path, static_dir=tmp_path / "static")
    app = create_app(settings)
    probe = Probe()
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        app.dependency_overrides[services] = lambda: (
            ConfiguredTargetTesting(app.state.engine, {"webhook": probe}),
            ManualSending(app.state.engine, {"webhook": probe}),
        )
        base, body = intent(client, ids["sent"], manual=True)
        original = client.post(base, json=body).json()
        assert original["result"] == "success"
        cookie = client.cookies.get("seekbell_session")
    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.set("seekbell_session", cookie)
        response = restarted.get("/api/manage/history/manual/" + original["id"])
        assert response.status_code == 200
        assert response.json() == original
        assert len(probe.calls) == 1


def test_manual_resend_reads_saved_timezone_without_changing_original_snapshot(sending):
    from seekbell.services.display import get_display, update_display

    app, client, ids, probe = sending
    with Session(app.state.engine) as session:
        original = copy.deepcopy(session.get(Outbox, ids["sent"]).payload)
    update_display(app.state.engine, "Asia/Shanghai", get_display(app.state.engine)["revision"])
    base, body = intent(client, ids["sent"], manual=True)
    assert client.post(base, json=body).json()["result"] == "success"
    assert probe.calls[0][1]["display_timezone"] == "Asia/Shanghai"
    assert probe.calls[0][1]["post"] == original["post"]
    with Session(app.state.engine) as session:
        assert session.get(Outbox, ids["sent"]).payload == original
        assert "display_timezone" not in session.get(ManualDelivery, body["request_id"]).payload
