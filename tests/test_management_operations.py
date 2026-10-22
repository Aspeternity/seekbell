import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    DeliveryAttempt,
    ManualDelivery,
    NotificationTarget,
    Outbox,
    Post,
    RuleHit,
    SeenPost,
    Source,
    SourceProbe,
    SourceRun,
    SourceState,
    TargetTestAttempt,
    TaskEvaluation,
    TaskVersion,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.services.configuration import Configuration, TargetInUse
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.manual_sending import ConfiguredTargetTesting
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.history_helpers import PRIVATE, seed_history
from tests.runtime_helpers import SyntheticScenario
from tests.test_management import authenticate, target, task_values
from tests.test_runtime import until, website


@pytest.fixture
def history(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        yield app, client, ids, Configuration(app.state.engine, app.state.vault)


def tables(engine):
    # Stronger than comparing counts: trials/checks must leave every ledger byte intact.
    names = [
        Post,
        SeenPost,
        RuleHit,
        Outbox,
        DeliveredPost,
        DeliveryAttempt,
        TaskEvaluation,
        TaskVersion,
        TargetTestAttempt,
        ManualDelivery,
        SourceState,
        SourceRun,
    ]
    with engine.connect() as connection:
        return {model.__tablename__: connection.execute(select(model)).all() for model in names}


def test_target_delete_blocks_paused_dependencies_and_preserves_history_and_receipts(history):
    app, client, ids, config = history
    config.set_task_enabled(ids["primary"], False)
    assert client.delete("/api/manage/targets/" + ids["target"]).status_code == 409
    config.delete_task(ids["primary"], at=ids["base"] + 3000)
    with Session(app.state.engine) as session:
        event = session.get(Outbox, ids["sent"])
        payload, snapshot = copy.deepcopy(event.payload), copy.deepcopy(event.target_snapshot)
        receipt = session.get(DeliveredPost, ("nodeseek", "8001", ids["target"])).delivered_at
    assert client.delete("/api/manage/targets/" + ids["target"]).status_code == 200
    assert client.delete("/api/manage/targets/" + ids["target"]).status_code == 200
    assert client.get("/api/manage/workspace").json()["targets"] == []
    assert client.get("/api/manage/overview").json()["configuration"]["targets"] == 0
    assert client.get("/api/manage/history/deliveries").json()["total"] == 24
    assert client.get("/api/manage/history/tests/history-test-success").status_code == 200
    assert client.get("/api/manage/targets/" + ids["target"] + "/test-preview").status_code == 404
    assert (
        client.get("/api/manage/deliveries/" + ids["sent"] + "/resend-preview").status_code == 404
    )
    assert client.post("/api/manage/tasks", json=task_values(ids["target"])).status_code == 422
    assert (
        client.put(
            "/api/manage/targets/" + ids["target"],
            json={
                "name": "revive",
                "kind": "webhook",
                "enabled": True,
                "config": {},
            },
        ).status_code
        == 422
    )
    with pytest.raises(ValueError):
        config.set_target_enabled(ids["target"], True)
    assert config.duplicate_targets(ids["target"]) == []
    with Session(app.state.engine) as session:
        deleted = session.get(NotificationTarget, ids["target"])
        assert deleted.deleted_at and not deleted.enabled and deleted.config_ciphertext is None
        event = session.get(Outbox, ids["sent"])
        assert (
            event.status == "sent"
            and event.payload == payload
            and event.target_snapshot == snapshot
        )
        assert (
            session.get(DeliveredPost, ("nodeseek", "8001", ids["target"])).delivered_at == receipt
        )
        assert all(
            e.cancel_requested
            for e in session.scalars(
                select(Outbox).where(Outbox.status.in_(("pending", "retry", "leased", "cancelled")))
            )
        )
    detail = client.get("/api/manage/history/deliveries/" + ids["sent"])
    assert (
        detail.status_code == 200 and PRIVATE not in detail.text and "ciphertext" not in detail.text
    )


def test_target_delete_and_task_creation_are_serialized_atomically(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        key = target(client)
        config = Configuration(app.state.engine, app.state.vault)

        def create():
            try:
                return config.create_task("Concurrent task", Rule(), [key], at=1, managed=True)
            except ValueError:
                return "blocked"

        def remove():
            try:
                config.delete_target(key, at=2)
                return "deleted"
            except TargetInUse:
                return "in_use"

        with ThreadPoolExecutor(max_workers=2) as pool:
            created, removed = list(pool.map(lambda fn: fn(), (create, remove)))
        assert (created == "blocked" and removed == "deleted") or (
            created != "blocked" and removed == "in_use"
        )


def test_inflight_test_can_finish_and_idempotently_replay_after_deletion(history):
    app, client, ids, config = history
    config.delete_task(ids["primary"], at=10)
    calls = []

    class Notifier:
        async def send(self, snapshot, payload):
            calls.append(snapshot)
            config.delete_target(ids["target"], at=11)
            return SendResult(status="success")

    sender = ConfiguredTargetTesting(app.state.engine, {"webhook": Notifier()})
    key = str(uuid4())
    asyncio.run(sender.run(ids["target"], key=key))
    asyncio.run(sender.run(ids["target"], key=key))
    assert len(calls) == 1
    with Session(app.state.engine) as session:
        assert session.get(TargetTestAttempt, key).result == "success"
    assert (
        client.post(
            "/api/manage/targets/" + ids["target"] + "/test",
            json={
                "request_id": str(uuid4()),
                "revision": 1,
            },
        ).status_code
        == 404
    )


def test_deleted_target_keeps_late_success_receipt_without_claiming_queued_messages(history):
    app, _, ids, config = history
    worker = DeliveryWorker(app.state.engine, {})
    claim = worker.claim(at=ids["base"] + 390)
    assert claim
    config.delete_task(ids["primary"], at=ids["base"] + 391)
    config.delete_target(ids["target"], at=ids["base"] + 392)
    assert worker.finish(claim, SendResult(status="success"), at=ids["base"] + 393)
    assert worker.claim(at=ids["base"] + 10000) is None
    with Session(app.state.engine) as session:
        event = session.get(Outbox, claim.event_id)
        assert session.get(DeliveredPost, (event.website_id, event.external_post_id, ids["target"]))


def test_history_trial_uses_draft_rule_recent_local_rows_and_missing_vs_empty_without_writes(
    history,
):
    app, client, ids, _ = history
    before = tables(app.state.engine)
    rule = Rule(scope="summary", groups=[{"all_of": ["VPS"]}]).model_dump(mode="json")
    response = client.post(
        "/api/manage/rules/history",
        json={
            "website_id": "nodeseek",
            "rule": rule,
            "limit": 100,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["available"] == data["sample_count"] == 27
    assert data["from_at"] <= data["to_at"] and data["website_id"] == "nodeseek"
    missing = [item for item in data["items"] if item["sample"]["summary"] is None]
    empty = [item for item in data["items"] if item["sample"]["summary"] == ""]
    assert missing and empty
    assert all(item["result"]["status"] == "insufficient_data" for item in missing)
    assert all(item["result"]["status"] == "no_match" for item in empty)
    assert any(
        reason["code"] == "missing_summary"
        for item in missing
        for reason in item["result"]["reasons"]
    )
    small = client.post(
        "/api/manage/rules/history",
        json={
            "website_id": "nodeseek",
            "rule": {},
            "limit": 2,
        },
    ).json()
    assert small["available"] == 27 and small["sample_count"] == 2
    assert all(item["result"]["status"] == "match" for item in small["items"])
    assert small["from_at"] >= data["from_at"]
    assert "ciphertext" not in response.text and PRIVATE not in response.text
    assert tables(app.state.engine) == before


def test_combined_scope_manual_and_history_trials_use_received_fields_without_writes(history):
    app, client, _, _ = history
    before = tables(app.state.engine)
    rule = {
        "scope": "title_summary",
        "groups": [{"all_of": ["读取样本"]}],
        "exclude": ["求购", "已出"],
    }
    response = client.post(
        "/api/manage/rules/history",
        json={"website_id": "nodeseek", "rule": rule, "limit": 100},
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    missing = [item for item in items if item["sample"]["summary"] is None]
    empty = [item for item in items if item["sample"]["summary"] == ""]
    assert missing and empty
    assert all(item["result"]["status"] == "match" for item in missing + empty)
    for item in items:
        trial = client.post(
            "/api/manage/rules/evaluate", json={"rule": rule, "post": item["sample"]}
        )
        assert trial.status_code == 200, trial.text
        assert trial.json() == item["result"]
        assert item["result"]["status"] != "insufficient_data"
    example = client.post(
        "/api/manage/rules/evaluate",
        json={
            "rule": {
                "scope": "title_summary",
                "groups": [{"all_of": ["vmiss", "tri"]}],
                "exclude": ["core", "收"],
            },
            "post": {"title": "[出]180出Vmiss Tri 来", "summary": None},
        },
    )
    assert example.status_code == 200 and example.json()["status"] == "match"
    assert tables(app.state.engine) == before


@pytest.mark.parametrize(
    "values",
    [
        {"limit": 101},
        {"limit": 0},
        {"limit": True},
        {"website_id": "custom"},
        {"url": "https://receiver.example.test"},
        {"rule": {"scope": "fulltext"}},
    ],
)
def test_history_trial_rejects_unbounded_or_unsupported_input(history, values):
    _, client, _, _ = history
    response = client.post(
        "/api/manage/rules/history",
        json={
            "website_id": "nodeseek",
            "rule": {},
            **values,
        },
    )
    assert response.status_code == 422


def test_history_trial_empty_scope_authentication_and_csrf(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        assert client.post("/api/manage/rules/history", json={}).status_code == 401
        authenticate(client)
        body = {"website_id": "nodeseek", "rule": {}}
        assert client.post("/api/manage/rules/history", json=body).status_code == 409
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        result = client.post("/api/manage/rules/history", json=body).json()
        assert result["sample_count"] == result["available"] == 0 and result["from_at"] is None
        del client.headers["X-CSRF-Token"]
        assert client.post("/api/manage/rules/history", json=body).status_code == 403


def test_operations_migration_from_0006_rolls_back_atomically_and_preserves_rows(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0006_manual_delivery")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_targets(id,name,kind,revision,enabled) "
                    "VALUES ('legacy','Legacy','mock',1,0)"
                )
            )

        def fail(_conn, _cursor, statement, _params, _context, _many):
            if "CREATE TABLE source_probes" in statement:
                raise RuntimeError("synthetic probe migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0006_manual_delivery"
        assert "source_probes" not in inspect(engine).get_table_names()
        assert "deleted_at" not in {
            col["name"] for col in inspect(engine).get_columns("notification_targets")
        }
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            legacy = session.get(NotificationTarget, "legacy")
            assert legacy.name == "Legacy" and legacy.deleted_at is None
    finally:
        engine.dispose()


PROBE = "/api/manage/websites/nodeseek/connection-test"


def test_connection_check_is_separate_persistent_and_keeps_its_own_cooldown(tmp_path):
    scenario = SyntheticScenario()
    now = [1780000000.0]

    def factory(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)
        runtime.source.clock = lambda: now[0]
        return runtime

    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, runtime_factory=factory)
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        assert client.get(PROBE).json() is None
        before = tables(app.state.engine)
        response = client.post(PROBE, json={})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "success" and result["item_count"] == 1
        assert result["next_attempt_at"] == now[0] + 2
        assert len(scenario.fetches) == 1
        assert tables(app.state.engine) == before
        assert client.get(PROBE).json() == result
        assert client.post(PROBE, json={}).status_code == 429
    restarted = create_app(settings, runtime_factory=factory)
    with TestClient(restarted) as client:
        authenticate(client, setup=False)
        assert client.get(PROBE).json() == result
        assert client.post(PROBE, json={}).status_code == 429
        website(client, interval=20)
        assert client.get(PROBE).json()["next_attempt_at"] == result["next_attempt_at"]
        # Monitor changes do not alter the test cooldown. A fresh successful
        # monitor request likewise cannot block the independent explicit check.
        with write_session(restarted.state.engine) as session:
            session.get(SourceState, "nodeseek-rss").next_attempt_at = now[0] + 20
        now[0] = result["next_attempt_at"] + 1
        before = tables(restarted.state.engine)
        assert client.post(PROBE, json={}).status_code == 200
        assert len(scenario.fetches) == 2 and tables(restarted.state.engine) == before
        assert (
            restarted.state.runtime.source._snapshot()["next_attempt_at"]
            == result["started_at"] + 20
        )
        now[0] = result["started_at"] + 21
        until(lambda: len(scenario.fetches) == 3)
        until(lambda: bool(client.get("/api/manage/history/posts").json()["total"]))
        with Session(restarted.state.engine) as session:
            assert session.get(Post, ("nodeseek", "9001")).baseline


@pytest.mark.parametrize("failure", [429, 503])
def test_connection_failure_persists_retry_after_without_changing_collection_health(
    tmp_path, failure
):
    scenario = SyntheticScenario()
    scenario.failure = failure
    app = create_app(Settings(data_dir=tmp_path), runtime_factory=scenario.factory)
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        before = tables(app.state.engine)
        result = client.post(PROBE, json={}).json()
        assert result["status"] == "failure" and result["code"] == f"http_{failure}"
        assert result["item_count"] is None
        assert result["next_attempt_at"] >= result["finished_at"] + 60
        response = client.post(PROBE, json={})
        assert response.status_code == 429 and int(response.headers["retry-after"]) >= 59
        assert f"http_{failure}" in response.json()["detail"]
        assert str(response.headers["retry-after"]) in response.json()["detail"]
        assert len(scenario.fetches) == 1 and tables(app.state.engine) == before
        website(client, interval=10)
        assert client.post(PROBE, json={}).status_code == 429
        overview = client.get("/api/manage/overview").json()
        assert overview["sources"][0]["next_attempt_at"] >= result["next_attempt_at"]
        assert overview["sources"][0]["failures"] == 0
        assert overview["window"]["source_failures"] == 0


def test_connection_check_honors_collector_errors_deadline_and_fixed_url(tmp_path):
    scenario = SyntheticScenario()

    def factory(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)
        runtime.source.fetch_timeout = 0.03
        scenario.block = asyncio.Event()
        return runtime

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        assert client.post(PROBE, json={}).status_code == 401
        authenticate(client)
        assert client.post(PROBE, json={}).status_code == 409
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        assert client.post(PROBE, json={"url": "https://receiver.example.test"}).status_code == 422
        result = client.post(PROBE, json={}).json()
        assert result["status"] == "failure" and result["code"] == "timeout"
        assert scenario.fetches == ["https://rss.nodeseek.com/"]
        with write_session(app.state.engine) as session:
            session.get(SourceProbe, "nodeseek-rss").next_attempt_at = 0
            session.get(SourceProbe, "nodeseek-rss").finished_at = 1
            session.get(Source, "nodeseek-rss").url = "https://receiver.example.test/private"
        result = client.post(PROBE, json={}).json()
        assert result["code"] == "unsupported_source" and len(scenario.fetches) == 1
        csrf = client.headers.pop("X-CSRF-Token")
        assert client.post(PROBE, json={}).status_code == 403
        client.headers["X-CSRF-Token"] = csrf
        assert (
            client.post("/api/manage/websites/custom/connection-test", json={}).status_code == 422
        )


def test_connection_checks_and_scheduled_collection_share_nonoverlapping_lock(tmp_path):
    scenario = SyntheticScenario()

    def factory(engine, notifiers):
        scenario.block = asyncio.Event()
        return scenario.factory(engine, notifiers)

    app = create_app(Settings(data_dir=tmp_path), runtime_factory=factory)
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        before = tables(app.state.engine)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(lambda: client.post(PROBE, json={}))
            until(lambda: scenario.fetches)
            assert client.post(PROBE, json={}).status_code == 409
            client.portal.call(scenario.block.set)
            assert pending.result().json()["status"] == "success"
        assert len(scenario.fetches) == 1 and tables(app.state.engine) == before


def test_shutdown_joins_and_cancels_inflight_probe_leaving_unknown_evidence(core):
    from seekbell.db.models import WebsiteInstallation

    scenario = SyntheticScenario()
    with write_session(core.engine) as session:
        session.add(WebsiteInstallation(website_id="nodeseek"))
        session.get(Source, "nodeseek-rss").enabled = False

    async def run():
        scenario.block = asyncio.Event()
        runtime = scenario.factory(core.engine, {})
        await runtime.start()
        while runtime.source._lock.locked():
            await asyncio.sleep(0.005)
        operation = asyncio.create_task(runtime.check_source())
        for _ in range(100):
            if scenario.fetches:
                break
            await asyncio.sleep(0.005)
        assert scenario.fetches
        await runtime.aclose()
        assert operation.cancelled() and runtime.client.is_closed and not runtime.probes

    asyncio.run(run())
    with Session(core.engine) as session:
        result = session.get(SourceProbe, "nodeseek-rss")
        assert result.status == "unknown" and result.finished_at is None
        assert result.next_attempt_at > result.started_at


def test_deleted_last_target_with_encrypted_history_still_requires_original_key(tmp_path):
    from cryptography.fernet import Fernet

    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        authenticate(client)
        ids = seed_history(app.state.engine, app.state.vault)
        config = Configuration(app.state.engine, app.state.vault)
        config.delete_task(ids["primary"], at=10)
        config.delete_target(ids["target"], at=11)
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
        assert client.get("/api/manage/workspace").json()["targets"] == []
        assert client.get("/api/manage/history/deliveries").json()["total"] == 24
