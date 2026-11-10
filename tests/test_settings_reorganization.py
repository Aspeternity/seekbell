"""Alert delay and test sends, low disk space, restore leftovers and remembered sign-ins."""

import asyncio
import re
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
from seekbell.db.models import AlertDelivery, LoginSession, SystemEvent
from seekbell.notifiers.rendering import render, telegram_message, webhook_payload
from seekbell.services import authentication as auth
from seekbell.services.alerts import RECOVERED_EARLY, AlertWorker, get_settings, update_settings
from seekbell.services.backup_demo import ADMIN_PASSWORD
from seekbell.services.disk import CODE, LOW_BYTES, RECOVERED_BYTES, DiskWatch
from seekbell.services.ingestion import Ingestion
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.core_helpers import batch
from tests.test_display_alerts import Probe, app, configured, count, enable_source, fault  # noqa: F401
from tests.test_management import CREDENTIALS, authenticate, target
from tests.test_web_backups import apply, apply_body, discard, download, leftover_ids, web  # noqa: F401


def deliveries(engine):
    with Session(engine) as session:
        return [
            (phase, item.result, item.error_code)
            for item, phase in session.execute(
                select(AlertDelivery, SystemEvent.phase)
                .join(SystemEvent)
                .order_by(SystemEvent.at, AlertDelivery.id)
            )
        ]


def delay(engine, seconds):
    settings = get_settings(engine)
    return update_settings(
        engine, True, settings["target_ids"], settings["revision"], delay_seconds=seconds
    )


def recover(engine, at):
    enable_source(engine)
    Ingestion(engine).ingest("nodeseek-rss", batch(9001), at=at)


def test_alert_delay_is_saved_validated_and_kept_when_omitted(configured):  # noqa: F811
    server, client, key = configured
    saved = client.get("/api/manage/alerts").json()
    assert saved["delay_seconds"] == 0
    body = {"enabled": True, "target_ids": [key], "revision": saved["revision"]}
    assert client.put("/api/manage/alerts", json={**body, "delay_seconds": 45}).status_code == 422
    result = client.put("/api/manage/alerts", json={**body, "delay_seconds": 300})
    assert result.status_code == 200 and result.json()["delay_seconds"] == 300
    body["revision"] = result.json()["revision"]
    # A caller that does not know the field leaves the saved delay alone.
    unchanged = client.put("/api/manage/alerts", json=body)
    assert unchanged.json()["delay_seconds"] == 300
    assert unchanged.json()["revision"] == body["revision"]


def test_fault_clearing_inside_the_delay_sends_nothing(configured):  # noqa: F811
    server, _, _ = configured
    engine = server.state.engine
    delay(engine, 60)
    fault(engine, at=100)
    probe = Probe()
    worker = AlertWorker(engine, {"webhook": probe}, clock=lambda: 130)
    assert not asyncio.run(worker.run_once())
    recover(engine, at=140)
    assert deliveries(engine) == [("fault", "cancelled", RECOVERED_EARLY)]
    assert not asyncio.run(AlertWorker(engine, {"webhook": probe}, clock=lambda: 500).run_once())
    assert probe.calls == []


def test_fault_outlasting_the_delay_is_sent_then_its_recovery(configured):  # noqa: F811
    server, _, _ = configured
    engine = server.state.engine
    delay(engine, 60)
    fault(engine, at=100)
    probe = Probe()
    assert not asyncio.run(AlertWorker(engine, {"webhook": probe}, clock=lambda: 159).run_once())
    recover(engine, at=200)
    worker = AlertWorker(engine, {"webhook": probe}, clock=lambda: 200)
    assert asyncio.run(worker.run_once()) and asyncio.run(worker.run_once())
    assert [message["alert"]["phase"] for _, message in probe.calls] == ["fault", "recovery"]


def test_raising_the_delay_after_a_sent_fault_still_announces_recovery(configured):  # noqa: F811
    server, _, _ = configured
    engine = server.state.engine
    fault(engine, at=100)
    probe = Probe()
    assert asyncio.run(AlertWorker(engine, {"webhook": probe}).run_once())
    delay(engine, 300)
    recover(engine, at=120)
    assert [row[:2] for row in deliveries(engine)] == [
        ("fault", "success"),
        ("recovery", "pending"),
    ]


def test_test_alert_reaches_chosen_targets_without_queue_or_history(configured):  # noqa: F811
    server, client, key = configured
    paused = target(client, name="Paused webhook")
    probe = Probe()
    server.state.alert_notifiers = {"webhook": probe}
    result = client.post("/api/manage/alerts/test", json={"target_ids": [key, paused]})
    assert result.status_code == 200, result.text
    assert [(row["target_id"], row["result"]) for row in result.json()["items"]] == [
        (key, "success"),
        (paused, "cancelled"),
    ]
    assert len(probe.calls) == 1
    message = probe.calls[0][1]
    assert message["type"] == "system_alert" and message["alert"]["phase"] == "test"
    config = {"include_summary": False}
    assert "告警测试" in render(message, config) and "状态：测试" in render(message, config)
    assert "告警测试" in telegram_message(message, config)["text"]
    assert webhook_payload(message, config)["alert"]["code"] == "test_alert"
    assert count(server.state.engine, SystemEvent) == count(server.state.engine, AlertDelivery) == 0
    assert "synthetic-secret" not in result.text and "ciphertext" not in result.text


def test_test_alert_rejects_unknown_targets_and_reports_failures(configured):  # noqa: F811
    server, client, key = configured
    server.state.alert_notifiers = {"webhook": Probe("exception")}
    assert client.post("/api/manage/alerts/test", json={"target_ids": []}).status_code == 422
    assert (
        client.post("/api/manage/alerts/test", json={"target_ids": ["missing"]}).status_code == 422
    )
    result = client.post("/api/manage/alerts/test", json={"target_ids": [key]})
    assert result.json()["items"][0]["result"] == "unknown"
    assert "synthetic-private-alert-value" not in result.text
    csrf = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/manage/alerts/test", json={"target_ids": [key]}).status_code == 403
    client.headers["X-CSRF-Token"] = csrf


def test_low_disk_space_raises_one_problem_and_clears_with_headroom(configured):  # noqa: F811
    server, client, _ = configured
    engine = server.state.engine
    free = {"bytes": LOW_BYTES - 1}
    watch = DiskWatch(engine, usage=lambda path: SimpleNamespace(free=free["bytes"]))
    now = time.time()
    assert watch.run_once(at=now) is True
    assert watch.run_once(at=now + 1) is None  # not due yet
    assert watch.run_once(at=now + 61) is True
    assert count(engine, SystemEvent) == count(engine, AlertDelivery) == 1
    problems = client.get("/api/manage/operations/status").json()["problems"]
    assert [(row["kind"], row["code"], row["stage"]) for row in problems] == [
        ("runtime", CODE, "storage")
    ]
    detail = client.get("/api/manage/operations/problems/" + problems[0]["event_id"]).json()
    assert detail["status"] == "ongoing" and detail["guide"]["known"]
    # Just above the warning line is not yet a recovery.
    free["bytes"] = LOW_BYTES + 1
    assert watch.run_once(at=now + 122) is True
    free["bytes"] = RECOVERED_BYTES
    assert watch.run_once(at=now + 183) is False
    assert client.get("/api/manage/operations/status").json()["problems"] == []
    assert count(engine, SystemEvent) == 2


def test_disk_check_survives_a_failing_filesystem(configured):  # noqa: F811
    server, _, _ = configured

    def broken(path):
        raise OSError("synthetic")

    assert DiskWatch(server.state.engine, usage=broken).run_once(at=time.time()) is None
    assert count(server.state.engine, SystemEvent) == 0


def test_restore_leftovers_are_listed_counted_and_removed_with_the_password(web):  # noqa: F811
    client, settings, _ = web
    archive = download(client).content
    result = apply(client, apply_body(archive, pause=False))
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf"]
    previous = result.json()["previous"]
    status = client.get("/api/manage/backups").json()
    assert [(row["id"], row["kind"]) for row in status["leftovers"]] == [(previous, "previous")]
    assert status["leftovers"][0]["bytes"] > 0
    assert abs(status["leftovers"][0]["at"] - time.time()) < 120
    storage = client.get("/api/manage/storage").json()
    assert storage["leftover_count"] == 1
    assert storage["leftover_bytes"] == status["leftovers"][0]["bytes"]
    assert set(storage) == {
        "database_bytes",
        "leftover_bytes",
        "leftover_count",
        "filesystem_total_bytes",
        "filesystem_free_bytes",
        "checked_at",
    }
    assert discard(client, "Incorrect-Current-Password", previous).status_code == 400
    for name in ("credentials.key", "seekbell.sqlite3", "before-restore-x", previous + "x"):
        assert discard(client, ADMIN_PASSWORD, name).status_code == 404
    assert (settings.data_dir / "credentials.key").is_file()
    removed = discard(client, ADMIN_PASSWORD, previous)
    assert removed.status_code == 200 and removed.json() == {"leftovers": []}
    assert not (settings.data_dir / previous).exists()
    assert leftover_ids(client) == []
    assert client.get("/api/manage/storage").json()["leftover_count"] == 0
    assert client.get("/api/manage/workspace").status_code == 200
    assert not list(settings.data_dir.glob(".seekbell-*"))


def test_leftover_names_cannot_reach_other_directories(web, tmp_path):  # noqa: F811
    client, settings, _ = web
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("synthetic")
    name = "before-restore-20260101T000000Z-abcdefgh"
    (settings.data_dir / name).symlink_to(outside, target_is_directory=True)
    assert leftover_ids(client) == [name]
    assert client.get("/api/manage/backups").json()["leftovers"][0]["bytes"] == 0
    assert discard(client, ADMIN_PASSWORD, name).status_code == 200
    assert (outside / "keep.txt").read_text() == "synthetic"


def sign_in(client, **extra):
    csrf = client.get("/api/auth/status").json()["csrf"]
    return client.post(
        "/api/auth/login", json={**CREDENTIALS, **extra}, headers={"X-CSRF-Token": csrf}
    )


def test_remembered_sign_in_lasts_thirty_days_and_survives_account_changes(app):  # noqa: F811
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/auth/logout")
        ordinary = sign_in(client)
        assert f"Max-Age={auth.SESSION_SECONDS}" in ordinary.headers["set-cookie"]
        client.headers["X-CSRF-Token"] = ordinary.json()["csrf"]
        assert not client.get("/api/auth/sessions").json()["remembered"]
        client.post("/api/auth/logout")
        remembered = sign_in(client, remember=True)
        assert remembered.status_code == 200
        age = int(re.search(r"Max-Age=(\d+)", remembered.headers["set-cookie"])[1])
        assert age == auth.REMEMBER_SECONDS
        client.headers["X-CSRF-Token"] = remembered.json()["csrf"]
        session = client.get("/api/auth/sessions").json()
        assert session["remembered"]
        assert abs(session["expires_at"] - time.time() - auth.REMEMBER_SECONDS) < 30
        # The password was just entered, however long the session lasts.
        assert 800 < client.get("/api/manage/backups").json()["confirm_seconds"] <= 900
        changed = client.put(
            "/api/auth/administrator",
            json={"username": "renamed_admin", "current_password": CREDENTIALS["password"]},
        )
        assert changed.status_code == 200
        client.headers["X-CSRF-Token"] = changed.json()["csrf"]
        assert client.get("/api/auth/sessions").json()["remembered"]
        with Session(app.state.engine) as database:
            rows = database.scalars(select(LoginSession)).all()
            assert len(rows) == 1 and rows[0].created_at is not None


def test_sessions_from_before_the_upgrade_keep_their_fixed_lifetime(app):  # noqa: F811
    with TestClient(app) as client:
        authenticate(client)
        with Session(app.state.engine) as database, database.begin():
            database.scalars(select(LoginSession)).one().created_at = None
        assert not client.get("/api/auth/sessions").json()["remembered"]
        assert client.get("/api/manage/backups").json()["confirm_seconds"] > 800
