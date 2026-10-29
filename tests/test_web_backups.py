import asyncio
import fcntl
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from seekbell import backup
from seekbell.api import backups
from seekbell.config import Settings
from seekbell.main import create_app
from seekbell.services.backup_demo import ADMIN_PASSWORD, PASSWORD, prepare, table_data

from tests.runtime_helpers import SyntheticScenario


@pytest.fixture
def web(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    token, _ = prepare(settings)
    app = create_app(settings)
    with TestClient(app) as client:
        client.cookies.set("seekbell_session", token)
        csrf = client.get("/api/auth/status").json()["csrf"]
        client.headers["x-csrf-token"] = csrf
        yield client, settings, app


def values(**overrides):
    return {"current_password": ADMIN_PASSWORD, "password": PASSWORD, **overrides}


def upload(archive, **overrides):
    return json.dumps(values(**overrides)).encode() + b"\n" + archive


def download(client):
    response = client.post("/api/manage/backups/download", json=values())
    assert response.status_code == 200, response.text
    return response


def restore(client, body):
    return client.post(
        "/api/manage/backups/restore",
        content=body,
        headers={"content-type": "application/octet-stream"},
    )


def discard(client, password=ADMIN_PASSWORD):
    return client.request(
        "DELETE", "/api/manage/backups/candidate", json={"current_password": password}
    )


def assert_clean(settings):
    assert not list(settings.data_dir.glob(".seekbell-*"))


def assert_business_unchanged(settings, before):
    after = table_data(settings.database_path)
    expected = before.copy()
    # Explicit backup receipts are the only intended write to the active database.
    after.pop("backup_records")
    expected.pop("backup_records")
    assert after == expected


def test_web_round_trip_preserves_all_data_key_queue_and_revokes_only_copy_sessions(web):
    client, settings, _ = web
    before = table_data(settings.database_path)
    response = download(client)
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert b"SQLite format" not in response.content
    with pytest.raises(RuntimeError):
        backup.create_backup(settings, settings.data_dir / "offline.sbbackup", password=PASSWORD)
    assert_clean(settings)
    result = restore(client, upload(response.content))
    assert result.status_code == 200, result.text
    assert result.json() == {"candidate_available": True, "activated": False}
    receipts = client.get("/api/manage/backups").json()["records"]
    assert [(row["kind"], row["result"]) for row in receipts] == [
        ("restore", "verified"),
        ("export", "generated"),
    ]
    assert all(row["archive_bytes"] == len(response.content) for row in receipts)
    destination = settings.data_dir / backups.CANDIDATE
    after = table_data(destination / "seekbell.sqlite3")
    assert after.pop("login_sessions") == []
    expected = before.copy()
    expected.pop("login_sessions")
    assert after == expected
    assert_business_unchanged(settings, before)
    assert (destination / "credentials.key").read_bytes() == (
        settings.data_dir / "credentials.key"
    ).read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o700
    assert (destination / "seekbell.sqlite3").stat().st_mode & 0o777 == 0o600
    assert client.get("/api/auth/status").json()["authenticated"]
    assert client.get("/api/manage/backups").json()["candidate_available"]
    copy_before = table_data(destination / "seekbell.sqlite3")
    assert restore(client, upload(response.content)).status_code == 409
    assert table_data(destination / "seekbell.sqlite3") == copy_before
    assert_clean(settings)


@pytest.mark.parametrize("path", ["download", "restore", "discard"])
@pytest.mark.parametrize("kind", ["anonymous", "csrf", "origin", "password"])
def test_backup_requires_session_csrf_same_origin_and_current_password(web, path, kind):
    client, settings, _ = web
    if kind == "anonymous":
        client.cookies.clear()
    if kind == "csrf":
        client.headers.pop("x-csrf-token")
    if kind == "origin":
        client.headers["origin"] = "https://other.example.test"
    data = values(current_password="Incorrect-Current-Password") if kind == "password" else values()
    if path == "download":
        result = client.post("/api/manage/backups/download", json=data)
    elif path == "discard":
        result = discard(client, data["current_password"])
    else:
        result = restore(client, json.dumps(data).encode() + b"\ninvalid")
    assert (
        result.status_code == {"anonymous": 401, "csrf": 403, "origin": 403, "password": 400}[kind]
    )
    assert "Incorrect-Current-Password" not in result.text
    assert not (settings.data_dir / backups.CANDIDATE).exists()
    assert_clean(settings)


@pytest.mark.parametrize("kind", ["corrupt", "password"])
def test_failed_upload_authentication_preserves_live_database_and_cleans_staging(web, kind):
    client, settings, _ = web
    archive = download(client).content
    before = table_data(settings.database_path)
    if kind == "corrupt":
        archive = archive[:-1] + bytes([archive[-1] ^ 1])
        body = upload(archive)
    else:
        metadata = values(password="Incorrect-Synthetic-Value")
        body = json.dumps(metadata).encode() + b"\n" + archive
    result = restore(client, body)
    assert result.status_code == 422
    assert "Incorrect-Synthetic-Value" not in result.text
    assert_business_unchanged(settings, before)
    assert not (settings.data_dir / backups.CANDIDATE).exists()
    assert_clean(settings)


def test_upload_bounds_framing_and_unknown_fields(web, monkeypatch):
    client, settings, _ = web
    monkeypatch.setattr(backups, "MAX_METADATA", 128)
    monkeypatch.setattr(backups, "MAX_ARCHIVE", 128)
    assert restore(client, b"x" * 258).status_code == 413
    assert restore(client, b"x" * 129 + b"\n").status_code == 413
    assert restore(client, b"no newline").status_code == 422
    assert restore(client, b"{}\nbytes").status_code == 422
    assert restore(client, b"invalid\nbytes").status_code == 422
    assert client.post("/api/manage/backups/restore", json={}).status_code == 415
    monkeypatch.setattr(backups, "MAX_METADATA", 8192)
    metadata = values(destination="../source")
    assert restore(client, json.dumps(metadata).encode() + b"\nbytes").status_code == 422
    assert_clean(settings)


def test_chunked_upload_enforces_actual_size_and_operation_slot_is_reusable(web, monkeypatch):
    client, settings, app = web
    monkeypatch.setattr(backups, "MAX_ARCHIVE", 32)
    body = upload(b"x" * 33)
    assert restore(client, iter(body[i : i + 1] for i in range(len(body)))).status_code == 413
    client.portal.call(app.state.backup_gate.acquire)
    try:
        assert client.post("/api/manage/backups/download", json=values()).status_code == 409
        assert restore(client, upload(b"invalid")).status_code == 409
    finally:
        client.portal.call(app.state.backup_gate.release)
    assert download(client).content.startswith(backup.MAGIC)
    assert_clean(settings)


def test_rate_limit_rejects_repeated_privileged_operations(web):
    client, _, _ = web
    for _ in range(10):
        result = client.post("/api/manage/backups/download", json=values(current_password="wrong"))
        assert result.status_code == 400
    result = client.post("/api/manage/backups/download", json=values())
    assert result.status_code == 429
    assert result.headers["retry-after"] == "60"


def test_active_background_runtime_continues_during_consistent_web_snapshot(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    token, _ = prepare(settings)
    scenario = SyntheticScenario()
    app = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(app) as client:
        client.cookies.set("seekbell_session", token)
        client.headers["x-csrf-token"] = client.get("/api/auth/status").json()["csrf"]
        response = download(client)
        assert app.state.runtime.active
        assert client.get("/health/ready").status_code == 200
        archive = tmp_path / "live.sbbackup"
        archive.write_bytes(response.content)
        destination = tmp_path / "verified"
        backup.restore_backup(
            settings,
            archive,
            destination,
            password=PASSWORD,
        )
        assert backup.validate_database(destination / "seekbell.sqlite3")
        assert_clean(settings)


def test_disconnected_download_releases_slot_and_removes_temporary_files(tmp_path):
    async def exercise():
        gate = asyncio.Lock()
        await gate.acquire()
        temporary = tempfile.TemporaryDirectory(dir=tmp_path)
        path = Path(temporary.name) / "download.sbbackup"
        path.write_bytes(b"encrypted synthetic data")
        response = backups.Download(path, temporary, gate)

        async def disconnect(*args):
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await response(
                {"type": "http", "method": "POST", "headers": []}, disconnect, disconnect
            )
        assert not gate.locked()
        assert not path.parent.exists()

    asyncio.run(exercise())


def test_oversized_snapshot_aborts_before_publishing_and_cleans_web_files(web, monkeypatch):
    client, settings, _ = web
    monkeypatch.setattr(backup, "MAX_DATABASE", 1024)
    result = client.post("/api/manage/backups/download", json=values())
    assert result.status_code == 422
    assert "2 GiB" in result.json()["detail"]
    assert_clean(settings)


def test_write_failure_is_redacted_and_releases_operation_slot(web, monkeypatch):
    client, settings, _ = web
    original = backup.snapshot_backup

    def fail(*args, **kwargs):
        raise OSError("Synthetic-private-path-and-secret")

    monkeypatch.setattr(backup, "snapshot_backup", fail)
    result = client.post("/api/manage/backups/download", json=values())
    assert result.status_code == 422
    assert "Synthetic-private-path-and-secret" not in result.text
    assert_clean(settings)
    monkeypatch.setattr(backup, "snapshot_backup", original)
    assert download(client).status_code == 200


def test_disconnected_upload_cleans_partial_file_and_keeps_live_data(web, monkeypatch):
    from starlette.requests import ClientDisconnect, Request

    client, settings, _ = web
    before = table_data(settings.database_path)
    original = Request.stream

    async def interrupted(request):
        if request.url.path.endswith("/restore"):
            yield upload(b"partial")
            raise ClientDisconnect
        async for chunk in original(request):
            yield chunk

    monkeypatch.setattr(Request, "stream", interrupted)
    result = restore(client, b"ignored")
    assert result.status_code == 400
    assert_business_unchanged(settings, before)
    assert not (settings.data_dir / backups.CANDIDATE).exists()
    assert_clean(settings)


def test_receipt_storage_failure_does_not_expose_database_error(web, monkeypatch):
    client, settings, _ = web

    def unavailable(*args, **kwargs):
        raise backups.SQLAlchemyError("Synthetic sensitive database failure")

    monkeypatch.setattr(backups, "record_backup", unavailable)
    response = client.post("/api/manage/backups/download", json=values())
    assert response.status_code == 422
    assert "Synthetic sensitive" not in response.text
    assert "原数据未被覆盖" in response.text
    assert_clean(settings)


def test_candidate_can_be_discarded_then_restored_again(web):
    client, settings, _ = web
    archive = download(client).content
    assert restore(client, upload(archive)).status_code == 200
    destination = settings.data_dir / backups.CANDIDATE
    before = table_data(settings.database_path)
    assert discard(client, "Incorrect-Current-Password").status_code == 400
    assert destination.is_dir()
    result = discard(client)
    assert result.status_code == 200, result.text
    assert result.json() == {"candidate_available": False}
    assert not os.path.lexists(destination)
    status = client.get("/api/manage/backups").json()
    assert not status["candidate_available"]
    assert (status["records"][0]["kind"], status["records"][0]["result"]) == (
        "discard",
        "deleted",
    )
    assert discard(client).status_code == 404
    assert_business_unchanged(settings, before)
    assert restore(client, upload(archive)).status_code == 200
    assert destination.is_dir()
    assert_clean(settings)


def test_discard_never_follows_a_linked_candidate(web, tmp_path):
    client, settings, _ = web
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("synthetic")
    (settings.data_dir / backups.CANDIDATE).symlink_to(outside, target_is_directory=True)
    assert discard(client).status_code == 200
    assert not os.path.lexists(settings.data_dir / backups.CANDIDATE)
    assert (outside / "keep.txt").read_text() == "synthetic"
    assert_clean(settings)


def test_discard_refuses_a_candidate_held_by_another_instance(web):
    client, settings, _ = web
    destination = settings.data_dir / backups.CANDIDATE
    destination.mkdir(mode=0o700)
    lock = destination / ".instance.lock"
    lock.touch()
    with lock.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = discard(client)
    assert result.status_code == 422
    assert "其他实例" in result.json()["detail"]
    assert destination.is_dir()
    assert client.get("/api/manage/backups").json()["records"][0]["result"] == "failed"
    assert_clean(settings)


def apply_body(archive, **overrides):
    return json.dumps(values(**overrides)).encode() + b"\n" + archive


def apply(client, body):
    return client.post(
        "/api/manage/backups/apply",
        content=body,
        headers={"content-type": "application/octet-stream"},
    )


def login(client, username="backup_admin", password=ADMIN_PASSWORD):
    client.cookies.clear()
    client.headers.pop("x-csrf-token", None)
    csrf = client.get("/api/auth/status").json()["csrf"]
    return client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
        headers={"x-csrf-token": csrf},
    )


def rename_administrator(client):
    result = client.put(
        "/api/auth/administrator",
        json={
            "username": "current_admin",
            "current_password": ADMIN_PASSWORD,
            "new_password": CURRENT_PASSWORD,
        },
    )
    assert result.status_code == 200, result.text
    client.headers["x-csrf-token"] = result.json()["csrf"]


CURRENT_PASSWORD = "Synthetic-Current-Administrator"


def test_apply_replaces_the_live_workspace_in_place_and_keeps_the_previous(web):
    client, settings, app = web
    archive = download(client).content
    before = table_data(settings.database_path)
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE workspace_preferences SET name='恢复前修改'")
        connection.execute("DELETE FROM tasks")
        connection.commit()
    # The backup's own administrator is not needed: the current one is kept.
    rename_administrator(client)
    runtime = app.state.runtime
    result = apply(client, apply_body(archive, current_password=CURRENT_PASSWORD, pause=False))
    assert result.status_code == 200, result.text
    assert result.json()["restored"] and not result.json()["paused"]
    previous = settings.data_dir / result.json()["previous"]
    assert previous.name.startswith("before-restore-")
    assert previous.stat().st_mode & 0o777 == 0o700
    assert table_data(previous / "seekbell.sqlite3")["tasks"] == []
    assert app.state.runtime is not runtime
    after = table_data(settings.database_path)
    for name in ("tasks", "notification_targets", "websites", "posts", "workspace_preferences"):
        assert after[name] == before[name]
    # Old sessions belonged to the replaced workspace; the caller gets one new session.
    assert len(after["login_sessions"]) == 1
    assert result.json()["authenticated"] and result.json()["username"] == "current_admin"
    client.headers["x-csrf-token"] = result.json()["csrf"]
    records = client.get("/api/manage/backups").json()["records"]
    assert (records[0]["kind"], records[0]["result"]) == ("restore", "restored")
    assert not app.state.restoring and app.state.in_flight == 0
    assert login(client).status_code == 401
    assert login(client, "current_admin", CURRENT_PASSWORD).status_code == 200
    assert_clean(settings)


def test_apply_pauses_collection_and_targets_by_default(web):
    client, settings, _ = web
    archive = download(client).content
    result = apply(client, apply_body(archive))
    assert result.status_code == 200, result.text
    assert result.json()["paused"]
    with closing(sqlite3.connect(settings.database_path)) as connection:
        assert connection.execute("SELECT max(enabled) FROM websites").fetchone() == (0,)
        assert connection.execute("SELECT max(enabled) FROM notification_targets").fetchone() == (
            0,
        )


@pytest.mark.parametrize("field", ["password", "current_password"])
def test_failed_apply_keeps_the_live_workspace_running(web, field):
    client, settings, app = web
    archive = download(client).content
    before = table_data(settings.database_path)
    runtime = app.state.runtime
    result = apply(client, apply_body(archive, **{field: "Incorrect-Synthetic-Value"}))
    assert result.status_code in (400, 422)
    assert "Incorrect-Synthetic-Value" not in result.text
    assert app.state.runtime is runtime
    assert not app.state.restoring
    assert not list(settings.data_dir.glob("before-restore-*"))
    assert_business_unchanged(settings, before)
    assert client.get("/api/manage/backups").status_code == 200
    assert_clean(settings)


def test_reopen_failure_returns_to_the_original_workspace(web, monkeypatch):
    client, settings, app = web
    archive = download(client).content
    before = table_data(settings.database_path)
    original = app.state.open_workspace
    calls = []

    async def failing_once(target):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("synthetic open failure")
        await original(target)

    monkeypatch.setattr(app.state, "open_workspace", failing_once)
    result = apply(client, apply_body(archive))
    assert result.status_code == 422
    assert "已回到原数据" in result.json()["detail"]
    assert len(calls) == 2
    assert not list(settings.data_dir.glob("before-restore-*"))
    assert_business_unchanged(settings, before)
    assert client.get("/api/manage/backups").status_code == 200
    assert_clean(settings)


def test_requests_wait_out_a_restore_with_a_clear_503(web):
    client, _, app = web
    app.state.restoring = True
    try:
        result = client.get("/api/manage/backups")
        assert result.status_code == 503
        assert result.headers["retry-after"] == "5"
        assert "正在恢复备份" in result.json()["detail"]
    finally:
        app.state.restoring = False
    assert client.get("/api/manage/backups").status_code == 200


def test_fresh_installation_can_restore_instead_of_creating_an_administrator(web, tmp_path):
    client, _, _ = web
    archive = download(client).content
    fresh = Settings(data_dir=tmp_path / "fresh")
    with TestClient(create_app(fresh)) as other:
        status = other.get("/api/auth/status").json()
        assert not status["initialized"]
        metadata = {"password": PASSWORD, "username": "fresh_admin", "pause": True}
        short = json.dumps({**metadata, "admin_password": "short"}).encode()
        result = other.post(
            "/api/auth/setup/restore",
            content=short + b"\n" + archive,
            headers={"content-type": "application/octet-stream", "x-csrf-token": status["csrf"]},
        )
        assert result.status_code == 422
        body = json.dumps({**metadata, "admin_password": CURRENT_PASSWORD}).encode()
        result = other.post(
            "/api/auth/setup/restore",
            content=body + b"\n" + archive,
            headers={"content-type": "application/octet-stream", "x-csrf-token": status["csrf"]},
        )
        assert result.status_code == 200, result.text
        # Restoring signs in the newly chosen administrator directly.
        assert other.get("/api/auth/status").json()["username"] == "fresh_admin"
        assert login(other).status_code == 401
        assert login(other, "fresh_admin", CURRENT_PASSWORD).status_code == 200
        with closing(sqlite3.connect(fresh.database_path)) as connection:
            name = connection.execute("SELECT name FROM workspace_preferences").fetchone()
        assert name == ("合成恢复空间",)
        # Once an administrator exists the unauthenticated entry is closed.
        csrf = other.get("/api/auth/status").json()["csrf"]
        other.cookies.clear()
        csrf = other.get("/api/auth/status").json()["csrf"]
        again = other.post(
            "/api/auth/setup/restore",
            content=body + b"\n" + archive,
            headers={"content-type": "application/octet-stream", "x-csrf-token": csrf},
        )
        assert again.status_code == 409
    assert not list(fresh.data_dir.glob(".seekbell-*"))


def age_session(settings, seconds):
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE login_sessions SET expires_at=expires_at-?", (seconds,))
        connection.commit()


def test_password_may_be_omitted_shortly_after_it_was_entered(web):
    client, settings, _ = web
    without = {"password": PASSWORD}
    # Signing in just now counts as entering the password.
    assert client.get("/api/manage/backups").json()["confirm_seconds"] > 800
    assert client.post("/api/manage/backups/download", json=without).status_code == 200
    age_session(settings, 16 * 60)
    assert client.get("/api/manage/backups").json()["confirm_seconds"] == 0
    for result in (
        client.post("/api/manage/backups/download", json=without),
        client.request("DELETE", "/api/manage/backups/candidate", json={}),
        apply(client, json.dumps(without).encode() + b"\ninvalid"),
    ):
        assert result.status_code == 403
        assert "当前管理员密码" in result.json()["detail"]
    assert download(client).status_code == 200
    assert client.get("/api/manage/backups").json()["confirm_seconds"] > 800
    assert client.post("/api/manage/backups/download", json=without).status_code == 200
    assert_clean(settings)
