import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    AlertSettings,
    DeliveredPost,
    NotificationTarget,
    Outbox,
    Task,
    TaskVersion,
)
from seekbell.db.transactions import write_session
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.services.configuration import Configuration, TargetDeleteChanged
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from tests.test_management import authenticate, target
from tests.test_management_operations import history as history
from tests.test_management_operations import tables


@pytest.fixture
def configured(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        old = target(client, name="Deleting", enabled=True)
        other = target(client, name="Other", enabled=True)
        yield app, client, Configuration(app.state.engine, app.state.vault), old, other


def add_task(config, name, targets, enabled=True):
    return config.create_task(
        name,
        Rule(groups=[{"all_of": ["VPS"]}]),
        targets,
        at=1,
        enabled=enabled,
        description="Preserved note",
        managed=True,
    )


def preview(client, key):
    response = client.get("/api/manage/targets/" + key + "/delete-preview")
    assert response.status_code == 200, response.text
    return response.json()


def remove(client, key, data):
    return client.request(
        "DELETE", "/api/manage/targets/" + key, json={"confirmation": data["confirmation"]}
    )


def test_preview_only_lists_tasks_losing_last_target_and_does_not_write(configured):
    app, client, config, old, other = configured
    active = add_task(config, "<b>Active</b>", [old])
    paused = add_task(config, "Paused", [old], False)
    add_task(config, "Multiple active", [old, other])
    add_task(config, "Multiple paused", [old, other], False)
    deleted = add_task(config, "Deleted", [old])
    config.delete_task(deleted, at=2)
    before = tables(app.state.engine)
    data = preview(client, old)
    assert {row["id"] for row in data["tasks"]} == {active, paused}
    assert {row["name"] for row in data["tasks"]} == {"<b>Active</b>", "Paused"}
    assert {row["enabled"] for row in data["tasks"]} == {True, False}
    assert "Multiple" not in str(data)
    assert len(data["confirmation"]) == 64
    assert tables(app.state.engine) == before
    assert "ciphertext" not in str(data) and "synthetic-secret" not in str(data)


def test_confirmed_deletion_detaches_all_tasks_and_preserves_versions(configured):
    app, client, config, old, other = configured
    keys = [
        add_task(config, "Sole active", [old]),
        add_task(config, "Sole paused", [old], False),
        add_task(config, "Multiple active", [old, other]),
        add_task(config, "Multiple paused", [old, other], False),
    ]
    with Session(app.state.engine) as session:
        versions = {key: copy.deepcopy(session.get(TaskVersion, (key, 1)).rule) for key in keys}
    data = preview(client, old)
    response = remove(client, old, data)
    assert response.status_code == 200, response.text
    assert remove(client, old, data).status_code == 200
    with Session(app.state.engine) as session:
        for i, key in enumerate(keys):
            task = session.get(Task, key)
            assert task.current_version == 2
            assert task.enabled == (i == 2)
            previous = session.get(TaskVersion, (key, 1))
            current = session.get(TaskVersion, (key, 2))
            assert previous.target_ids == ([old] if i < 2 else [old, other])
            assert current.target_ids == ([] if i < 2 else [other])
            assert current.rule == previous.rule == versions[key]
            assert current.name == previous.name and current.description == "Preserved note"
        deleted = session.get(NotificationTarget, old)
        assert deleted.deleted_at and not deleted.enabled and deleted.config_ciphertext is None
    with pytest.raises(ValueError, match="请先为任务选择通知目标"):
        config.set_task_enabled(keys[0], True)
    config.update_task(keys[0], "Sole active", Rule(), [other], at=4, enabled=True)
    with Session(app.state.engine) as session:
        assert session.get(Task, keys[0]).enabled


@pytest.mark.parametrize("change", ["task", "pause", "new_task", "target", "alerts"])
def test_changed_dependencies_require_fresh_confirmation_without_partial_writes(configured, change):
    app, client, config, old, other = configured
    key = add_task(config, "Sole", [old])
    data = preview(client, old)
    if change == "task":
        config.update_task(key, "Updated", Rule(), [old, other], at=2)
    elif change == "pause":
        config.set_task_enabled(key, False, at=2)
    elif change == "new_task":
        add_task(config, "New dependency", [old])
    elif change == "target":
        config.update_target(old, name="Renamed", config={})
    else:
        with write_session(app.state.engine) as session:
            alerts = session.get(AlertSettings, 1)
            alerts.enabled, alerts.target_ids = True, [old]
            alerts.revision += 1
    before = tables(app.state.engine)
    response = remove(client, old, data)
    assert response.status_code == 409 and "重新查看" in response.json()["detail"]
    assert tables(app.state.engine) == before
    assert remove(client, old, preview(client, old)).status_code == 200


def test_failure_rolls_back_all_detaches_and_target_deletion(configured):
    app, client, config, old, _ = configured
    key = add_task(config, "Rollback", [old])
    data = preview(client, old)
    before = tables(app.state.engine)

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO task_versions"):
            raise RuntimeError("synthetic deletion failure")

    event.listen(app.state.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="synthetic deletion failure"):
            remove(client, old, data)
    finally:
        event.remove(app.state.engine, "before_cursor_execute", fail)
    assert tables(app.state.engine) == before
    with Session(app.state.engine) as session:
        assert session.get(Task, key).enabled
        assert session.get(NotificationTarget, old).deleted_at is None


@pytest.mark.parametrize("remaining", [False, True])
def test_system_alert_dependencies_are_removed_consistently(configured, remaining):
    app, client, _, old, other = configured
    with write_session(app.state.engine) as session:
        settings = session.get(AlertSettings, 1)
        settings.enabled = True
        settings.target_ids = [old, other] if remaining else [old]
        settings.revision += 1
        previous = settings.revision
    data = preview(client, old)
    assert data["alerts_disabled"] is not remaining
    assert remove(client, old, data).status_code == 200
    with Session(app.state.engine) as session:
        settings = session.get(AlertSettings, 1)
        assert settings.target_ids == ([other] if remaining else [])
        assert settings.enabled == remaining and settings.revision == previous + 1


def test_existing_delivery_history_remains_and_pending_messages_cancel(history):
    app, client, ids, config = history
    current = config.create_task("New sole task", Rule(), [ids["target"]], at=ids["base"] + 4000)
    with Session(app.state.engine) as session:
        originals = {
            row.id: (row.status, copy.deepcopy(row.payload), row.target_snapshot)
            for row in session.scalars(select(Outbox))
        }
        receipts = list(
            session.execute(
                select(
                    DeliveredPost.website_id,
                    DeliveredPost.external_post_id,
                    DeliveredPost.target_id,
                    DeliveredPost.delivered_at,
                )
            )
        )
        saved = session.get(Outbox, ids["sent"])
        payload = copy.deepcopy(saved.payload)
        snapshot = saved.target_snapshot
    data = preview(client, ids["target"])
    assert current in {task["id"] for task in data["tasks"]}
    assert remove(client, ids["target"], data).status_code == 200
    with Session(app.state.engine) as session:
        saved = session.get(Outbox, ids["sent"])
        assert (
            saved.status == "sent"
            and saved.payload == payload
            and saved.target_snapshot == snapshot
        )
        for row in session.scalars(select(Outbox)):
            previous, old_payload, old_snapshot = originals[row.id]
            assert row.payload == old_payload and row.target_snapshot == old_snapshot
            if previous in ("pending", "retry"):
                assert row.status == "cancelled" and row.cancel_requested
            elif previous == "leased":
                assert row.status == "leased" and row.cancel_requested
        assert (
            list(
                session.execute(
                    select(
                        DeliveredPost.website_id,
                        DeliveredPost.external_post_id,
                        DeliveredPost.target_id,
                        DeliveredPost.delivered_at,
                    )
                )
            )
            == receipts
        )
    assert client.get("/api/manage/history/deliveries").json()["total"] == 24
    assert client.get("/api/manage/history/tests/history-test-success").status_code == 200


def test_preview_and_confirmation_require_authentication_csrf_and_valid_body(configured):
    app, client, config, old, _ = configured
    add_task(config, "Sole", [old])
    data = preview(client, old)
    assert (
        client.request(
            "DELETE", "/api/manage/targets/" + old, json={"confirmation": "bad"}
        ).status_code
        == 422
    )
    csrf = client.headers.pop("X-CSRF-Token")
    assert remove(client, old, data).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    client.post("/api/auth/logout")
    assert client.get("/api/manage/targets/" + old + "/delete-preview").status_code == 401
    assert remove(client, old, data).status_code == 401


def test_confirmed_deletion_and_concurrent_task_creation_cannot_leave_dangling_reference(
    configured,
):
    app, client, config, old, _ = configured
    add_task(config, "Existing", [old])
    data = preview(client, old)

    def delete():
        try:
            config.delete_target(old, at=5, confirmation=data["confirmation"])
            return "deleted"
        except TargetDeleteChanged:
            return "changed"

    def create():
        try:
            return add_task(config, "Concurrent", [old])
        except ValueError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        removed, created = list(pool.map(lambda fn: fn(), (delete, create)))
    assert (removed == "deleted" and created == "blocked") or (
        removed == "changed" and created != "blocked"
    )
    with Session(app.state.engine) as session:
        deleted = session.get(NotificationTarget, old).deleted_at is not None
        for task in session.scalars(select(Task).where(Task.deleted_at.is_(None))):
            version = session.get(TaskVersion, (task.id, task.current_version))
            assert not deleted or old not in version.target_ids


@pytest.mark.parametrize("body", [None, {}])
def test_legacy_empty_body_keeps_dependency_guard_and_allows_unlinked_delete(configured, body):
    app, client, config, old, other = configured
    key = add_task(config, "Legacy dependency", [old])
    response = client.request("DELETE", "/api/manage/targets/" + old, json=body)
    assert response.status_code == 409
    with Session(app.state.engine) as session:
        assert session.get(Task, key).enabled
        assert session.get(Task, key).current_version == 1
        assert session.get(NotificationTarget, old).deleted_at is None
    response = client.request("DELETE", "/api/manage/targets/" + other, json=body)
    assert response.status_code == 200, response.text
    with Session(app.state.engine) as session:
        assert session.get(NotificationTarget, other).deleted_at is not None
