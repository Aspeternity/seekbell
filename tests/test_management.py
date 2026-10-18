from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    DeliveredPost,
    NotificationTarget,
    Outbox,
    OutboxContribution,
    Post,
    RuleHit,
    SeenPost,
    SourceItem,
    TargetTestAttempt,
    Task,
    TaskVersion,
)
from seekbell.db.runtime import instance_lock
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.notifiers.credentials import CredentialError
from seekbell.services.ingestion import Ingestion
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.notifier_helpers import CONFIGS
from tests.test_authentication import setup, state


@pytest.fixture
def managed(tmp_path):
    settings = Settings(data_dir=tmp_path, static_dir=tmp_path / "static")
    app = create_app(settings)
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        yield client, app, settings


def target(client, kind="webhook", enabled=True):
    response = client.post(
        "/api/manage/targets",
        json={
            "name": "synthetic target",
            "kind": kind,
            "enabled": enabled,
            "config": CONFIGS[kind],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def task(client, target_id, **changes):
    response = client.post(
        "/api/manage/tasks",
        json={
            "name": "synthetic task",
            "rule": {"groups": [{"all_of": ["VPS"]}]},
            "target_ids": [target_id],
            **changes,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/channels", "GET", None),
        ("/targets", "GET", None),
        ("/targets/missing", "GET", None),
        ("/tasks", "GET", None),
        ("/tasks/missing", "GET", None),
        ("/targets", "POST", {}),
        ("/tasks", "POST", {}),
        ("/targets/missing", "PUT", {}),
        ("/tasks/missing", "PUT", {}),
        ("/tasks/missing", "DELETE", None),
        ("/targets/missing/enabled", "PUT", {"enabled": False}),
        ("/tasks/missing/enabled", "PUT", {"enabled": False}),
        ("/rules/preview", "POST", {"rule": {}}),
        ("/rules/history", "POST", {"rule": {}}),
    ],
)
def test_management_endpoints_require_authentication(tmp_path, path, method, body):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        for anonymous in (False, True):
            if anonymous:
                state(client)
            response = client.request(method, "/api/manage" + path, json=body)
            assert response.status_code == 401


@pytest.mark.parametrize(
    "path,method,body",
    [
        ("/targets", "POST", {"name": "x", "kind": "bark", "config": CONFIGS["bark"]}),
        ("/tasks", "POST", {"name": "x", "rule": {}, "target_ids": ["missing"]}),
        ("/targets/missing", "PUT", {}),
        ("/tasks/missing", "PUT", {}),
        ("/tasks/missing", "DELETE", None),
        ("/targets/missing/enabled", "PUT", {"enabled": False}),
        ("/tasks/missing/enabled", "PUT", {"enabled": False}),
        ("/rules/preview", "POST", {"rule": {}}),
        ("/rules/history", "POST", {"rule": {}}),
    ],
)
def test_management_writes_require_csrf(managed, path, method, body):
    client, _, _ = managed
    client.headers.pop("X-CSRF-Token")
    assert client.request(method, "/api/manage" + path, json=body).status_code == 403


@pytest.mark.parametrize("kind", list(CONFIGS))
def test_channel_configuration_round_trip_and_redaction(managed, kind):
    client, app, _ = managed
    schema = client.get("/api/manage/channels").json()
    assert set(schema) == set(CONFIGS)
    created = target(client, kind)
    assert not created["duplicate_ids"]
    for public in (
        created,
        client.get("/api/manage/targets").json()[0],
        client.get("/api/manage/targets/" + created["id"]).json(),
    ):
        assert "config_ciphertext" not in public
        for field in public["configured_secrets"]:
            assert field not in public["config"]
    response = client.put(
        "/api/manage/targets/" + created["id"],
        json={
            "name": "updated",
            "config": {"include_summary": True},
            "expected_revision": created["revision"],
        },
    )
    assert response.status_code == 200 and response.json()["revision"] == 2
    with Session(app.state.engine) as session:
        row = session.get(NotificationTarget, created["id"])
        values = app.state.configuration.vault.unseal(row.id, row.kind, row.config_ciphertext)
    for field in created["configured_secrets"]:
        assert values[field] == CONFIGS[kind].get(
            field, schema[kind]["properties"][field].get("default")
        )
    assert values["include_summary"]
    assert (
        client.put(
            "/api/manage/targets/" + created["id"],
            json={
                "name": "stale edit",
                "config": {},
                "expected_revision": 1,
            },
        ).status_code
        == 409
    )
    duplicate = target(client, kind)
    assert duplicate["duplicate_ids"] == [created["id"]]


def test_task_versions_copy_concurrency_and_deleted_visibility(managed):
    client, app, _ = managed
    notification = target(client)
    created = task(client, notification["id"])
    payload = {
        "name": "updated rule",
        "rule": {"groups": [{}, {"all_of": ["a phrase with spaces"]}]},
        "target_ids": [notification["id"]],
        "expected_version": 1,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(
                lambda _: (
                    client.put("/api/manage/tasks/" + created["id"], json=payload).status_code
                ),
                range(2),
            )
        )
    assert sorted(responses) == [200, 409]
    current = client.get("/api/manage/tasks/" + created["id"]).json()
    assert current["version"] == 2 and len(current["rule"]["groups"]) == 1
    copied = task(client, notification["id"], name="copy", rule=current["rule"], enabled=False)
    assert copied["id"] != created["id"] and copied["version"] == 1
    assert not copied["enabled"]
    with Session(app.state.engine) as session:
        assert session.get(TaskVersion, (created["id"], 1)).rule != current["rule"]
    assert client.delete("/api/manage/tasks/" + created["id"]).status_code == 204
    assert client.get("/api/manage/tasks/" + created["id"]).status_code == 404
    assert [t["id"] for t in client.get("/api/manage/tasks").json()] == [copied["id"]]
    with Session(app.state.engine) as session:
        assert session.get(Task, created["id"]).deleted_at is not None
        assert session.get(TaskVersion, (created["id"], 1)) is not None


@pytest.mark.parametrize("disabled", ["task", "target"])
def test_pause_api_cancels_pending_contributions_without_reviving(managed, disabled):
    client, app, _ = managed
    notification = target(client)
    monitor = task(client, notification["id"])
    app.state.configuration.set_source_enabled("nodeseek-rss", True, at=1)
    ingestion = Ingestion(app.state.engine)
    ingestion.ingest("nodeseek-rss", batch(9001), at=10)
    ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=20)
    with Session(app.state.engine) as session:
        assert session.scalars(select(Outbox)).one().status == "pending"
    path = (
        "/api/manage/"
        + ("tasks/" + monitor["id"] if disabled == "task" else "targets/" + notification["id"])
        + "/enabled"
    )
    assert client.put(path, json={"enabled": False}).status_code == 200
    assert client.put(path, json={"enabled": True}).status_code == 200
    with Session(app.state.engine) as session:
        assert session.scalars(select(Outbox)).one().status == "cancelled"
        if disabled == "task":
            assert not session.scalars(select(OutboxContribution)).one().active


def test_preview_and_history_share_engine_and_never_change_ledgers(managed):
    client, app, _ = managed
    notification = target(client)
    task(client, notification["id"])
    app.state.configuration.set_source_enabled("nodeseek-rss", True, at=1)
    ingestion = Ingestion(app.state.engine)
    ingestion.ingest("nodeseek-rss", batch(9001), at=10)
    ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=20)
    models = (
        SeenPost,
        SourceItem,
        Post,
        RuleHit,
        Outbox,
        OutboxContribution,
        DeliveredPost,
        TargetTestAttempt,
        TaskVersion,
    )

    def counts():
        with Session(app.state.engine) as session:
            return [session.scalar(select(func.count()).select_from(model)) for model in models]

    before = counts()
    rule = {"scope": "title_summary", "groups": [{"all_of": ["VPS"]}], "exclude": ["已出"]}
    preview = client.post(
        "/api/manage/rules/preview",
        json={
            "rule": rule,
            "sample": {"title": "VPS synthetic offer", "summary": None},
        },
    )
    assert preview.status_code == 200 and preview.json()["result"]["status"] == "insufficient_data"
    assert any(
        reason["code"] == "missing_summary" for reason in preview.json()["result"]["reasons"]
    )
    history = client.post("/api/manage/rules/history", json={"rule": rule, "limit": 1}).json()
    assert history["total"] == 2 and history["sample_count"] == 1
    assert history["oldest_at"] == history["newest_at"] == 20
    assert history["items"][0]["external_post_id"] == "9002"
    assert history["items"][0]["url"] == "https://www.nodeseek.com/post-9002-1"
    assert history["items"][0]["result"]["status"] == "insufficient_data"
    assert counts() == before
    all_posts = client.post("/api/manage/rules/preview", json={"rule": {"groups": [{}]}}).json()
    assert all_posts["warnings"] == ["all_new_posts"] and all_posts["rule"]["groups"] == []
    assert "全部新帖" in all_posts["explanation"]
    assert (
        client.post("/api/manage/rules/history", json={"rule": {}, "limit": 101}).status_code == 422
    )


def test_invalid_inputs_never_echo_secrets_and_fixed_scope(managed, caplog):
    client, _, _ = managed
    secret = "synthetic-private-value"
    for body in [
        {"name": "x", "kind": "webhook", "config": {"url": "file:///" + secret}},
        {"name": "x", "kind": "bark", "config": {"device_key": secret, "unexpected": secret}},
        {"name": secret, "kind": "mock", "config": {}},
    ]:
        response = client.post("/api/manage/targets", json=body)
        assert response.status_code == 422
        assert secret not in response.text + caplog.text
    notification = target(client)
    assert (
        client.post(
            "/api/manage/tasks",
            json={
                "name": "unsupported",
                "website_id": "other",
                "rule": {},
                "target_ids": [notification["id"]],
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/manage/tasks",
            json={
                "name": "unknown target",
                "rule": {},
                "target_ids": ["missing"],
            },
        ).status_code
        == 422
    )


@pytest.mark.parametrize("loss", ["missing", "wrong", "unsafe_mode", "snapshot_only"])
def test_vault_restart_missing_or_invalid_key_fails_closed(tmp_path, loss):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        auth = setup(client)
        client.headers["X-CSRF-Token"] = auth["csrf_token"]
        notification = target(client)
        if loss == "snapshot_only":
            task(client, notification["id"])
            app.state.configuration.set_source_enabled("nodeseek-rss", True, at=1)
            ingestion = Ingestion(app.state.engine)
            ingestion.ingest("nodeseek-rss", batch(9001), at=10)
            ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=20)
            with write_session(app.state.engine) as session:
                row = session.get(NotificationTarget, notification["id"])
                row.config_ciphertext = None
                row.kind = "mock"
    key_path = tmp_path / "credentials.key"
    original = key_path.read_bytes()
    if loss in ("missing", "snapshot_only"):
        key_path.unlink()
    elif loss == "wrong":
        key_path.write_bytes(Fernet.generate_key())
    else:
        key_path.chmod(0o644)
    with pytest.raises(CredentialError), TestClient(create_app(settings)):
        pytest.fail("Invalid key must stop startup")
    if loss in ("missing", "snapshot_only"):
        assert not key_path.exists()
    with instance_lock(tmp_path):
        pass
    if loss != "snapshot_only":
        key_path.write_bytes(original)
        key_path.chmod(0o600)
        with TestClient(create_app(settings)) as client:
            auth = state(client)
            assert auth["initialized"]
