import fcntl
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from seekbell import backup
from seekbell.api import backups
from seekbell.config import Settings
from seekbell.main import create_app
from seekbell.services import backup_schedule
from seekbell.services import backups as library
from seekbell.services.backup_demo import ADMIN_PASSWORD, prepare, table_data

from tests.runtime_helpers import SyntheticScenario

CURRENT_PASSWORD = "Synthetic-Current-Administrator"


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


def confirm(password=ADMIN_PASSWORD, **values):
    return {"current_password": password, **values}


def create(client):
    result = client.post("/api/manage/backups")
    assert result.status_code == 200, result.text
    return result.json()["id"]


def status(client):
    return client.get("/api/manage/backups").json()


def download(client, name):
    result = client.post("/api/manage/backups/" + name + "/ticket")
    assert result.status_code == 200, result.text
    response = client.get(result.json()["url"])
    assert response.status_code == 200, response.text
    return response


def upload(client, content, path="/api/manage/backups/import", headers=None):
    return client.post(
        path,
        content=content,
        headers={"content-type": "application/octet-stream", **(headers or {})},
    )


def restore(client, stage, **values):
    return client.post("/api/manage/backups/inspect/" + stage + "/restore", json=confirm(**values))


def remove(client, name):
    return client.delete("/api/manage/backups/" + name)


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


def assert_clean(settings):
    assert not list(settings.data_dir.glob(".seekbell-*"))
    assert not list(settings.backup_dir.glob(".seekbell-*"))


def assert_business_unchanged(settings, before):
    after = table_data(settings.database_path)
    assert after == before


def age_session(settings, seconds):
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute(
            "UPDATE login_sessions SET expires_at=expires_at-?, created_at=created_at-?",
            (seconds, seconds),
        )
        connection.commit()


def test_back_up_now_lists_a_private_archive_and_counts_it_in_storage(web):
    client, settings, _ = web
    before = table_data(settings.database_path)
    name = create(client)
    assert name.startswith("seekbell-") and name.endswith("-manual.tar.gz")
    path = settings.backup_dir / name
    assert path.stat().st_mode & 0o777 == 0o600
    assert settings.backup_dir.stat().st_mode & 0o777 == 0o700
    listing = status(client)
    [entry] = listing["backups"]
    assert entry["id"] == name and entry["valid"] and entry["kind"] == "manual"
    assert entry["bytes"] == path.stat().st_size
    assert entry["summary"]["workspace"] == "合成恢复空间" and entry["summary"]["tasks"] == 1
    assert abs(entry["at"] - time.time()) < 60
    assert listing["directory"] == str(settings.backup_dir)
    assert listing["free_bytes"] > 0
    assert entry["name"] is None
    assert "records" not in listing
    storage = client.get("/api/manage/storage").json()
    assert (storage["backup_count"], storage["backup_bytes"]) == (1, entry["bytes"])
    assert set(storage) == {
        "database_bytes",
        "backup_bytes",
        "backup_count",
        "filesystem_total_bytes",
        "filesystem_free_bytes",
        "checked_at",
    }
    assert_business_unchanged(settings, before)
    # The running instance still owns the lock: an offline backup is refused meanwhile.
    with pytest.raises(RuntimeError):
        backup.create_backup(settings, settings.data_dir / "offline.tar.gz")
    assert_clean(settings)


def rename(client, name, value):
    return client.patch("/api/manage/backups/" + name, json={"name": value})


def test_backups_can_be_named_when_created_and_renamed_later(web):
    client, settings, app = web
    result = client.post("/api/manage/backups", json={"name": "  调整规则前  "})
    assert result.status_code == 200, result.text
    named = result.json()["id"]
    plain = create(client)
    names = {row["id"]: row["name"] for row in status(client)["backups"]}
    assert names == {named: "调整规则前", plain: None}
    # Names live beside the archives and never show up as backups themselves.
    assert (settings.backup_dir / "labels.json").stat().st_mode & 0o777 == 0o600
    assert rename(client, plain, "升级前 手动").json() == {"id": plain, "name": "升级前 手动"}
    assert rename(client, named, "").json() == {"id": named, "name": None}
    names = {row["id"]: row["name"] for row in status(client)["backups"]}
    assert names == {named: None, plain: "升级前 手动"}
    for bad in ("长" * 41, "换\x07行"):
        assert rename(client, plain, bad).status_code == 422
        assert client.post("/api/manage/backups", json={"name": bad}).status_code == 422
    assert len(status(client)["backups"]) == 2
    assert rename(client, "missing.tar.gz", "x").status_code == 404
    # A restore replaces the database, not the names; deleting drops the name.
    stage = client.post("/api/manage/backups/" + plain + "/inspect").json()["stage"]
    assert restore(client, stage).status_code == 200
    client.headers["x-csrf-token"] = client.get("/api/auth/status").json()["csrf"]
    rows = {row["id"]: row["name"] for row in status(client)["backups"]}
    assert rows[plain] == "升级前 手动"
    assert remove(client, plain).status_code == 200
    assert plain not in library.labels(settings)
    assert_clean(settings)


def test_ticketed_download_streams_the_file_once_for_this_session_only(web):
    client, settings, _ = web
    name = create(client)
    ticket = client.post("/api/manage/backups/" + name + "/ticket").json()
    response = client.get(ticket["url"])
    assert response.status_code == 200
    assert response.content == (settings.backup_dir / name).read_bytes()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"] == "application/gzip"
    assert 'attachment; filename="' + name + '"' == response.headers["content-disposition"]
    # One use only.
    assert client.get(ticket["url"]).status_code == 403
    # Another session cannot use this session's ticket.
    ticket = client.post("/api/manage/backups/" + name + "/ticket").json()
    saved = client.cookies.get("seekbell_session")
    client.cookies.set("seekbell_session", "x" * 43)
    assert client.get(ticket["url"]).status_code == 401
    client.cookies.set("seekbell_session", saved)
    # A ticket names one archive.
    other = create(client)
    ticket = client.post("/api/manage/backups/" + name + "/ticket").json()
    assert client.get(ticket["url"].replace(name, other)).status_code == 403


def test_expired_ticket_is_refused(web, monkeypatch):
    client, _, _ = web
    name = create(client)
    monkeypatch.setattr(backups, "TICKET_SECONDS", -1)
    url = client.post("/api/manage/backups/" + name + "/ticket").json()["url"]
    assert client.get(url).status_code == 403


@pytest.mark.parametrize("path", ["create", "ticket", "delete", "import", "restore"])
@pytest.mark.parametrize("kind", ["anonymous", "csrf", "origin"])
def test_backup_requires_session_csrf_and_same_origin(web, path, kind):
    client, settings, _ = web
    name = create(client)
    stage = client.post("/api/manage/backups/" + name + "/inspect").json()["stage"]
    if kind == "anonymous":
        client.cookies.clear()
    if kind == "csrf":
        client.headers.pop("x-csrf-token")
    if kind == "origin":
        client.headers["origin"] = "https://other.example.test"
    if path == "create":
        result = client.post("/api/manage/backups")
    elif path == "ticket":
        result = client.post("/api/manage/backups/" + name + "/ticket")
    elif path == "delete":
        result = remove(client, name)
    elif path == "import":
        result = upload(client, b"invalid")
    else:
        result = restore(client, stage)
    assert result.status_code == {"anonymous": 401, "csrf": 403, "origin": 403}[kind], result.text
    assert (settings.backup_dir / name).exists()
    assert_clean(settings)


def test_restore_requires_the_current_password(web):
    client, settings, _ = web
    name = create(client)
    stage = client.post("/api/manage/backups/" + name + "/inspect").json()["stage"]
    result = restore(client, stage, password="Incorrect-Current-Password")
    assert result.status_code == 400
    assert "Incorrect-Current-Password" not in result.text
    assert (settings.backup_dir / name).exists()
    assert_clean(settings)


def test_delete_only_addresses_archives_by_name(web, tmp_path):
    client, settings, _ = web
    name = create(client)
    outside = tmp_path / "outside.tar.gz"
    outside.write_bytes(b"keep")
    (settings.backup_dir / "linked.tar.gz").symlink_to(outside)
    for bad in ("linked.tar.gz", "..%2Fseekbell.sqlite3", "missing.tar.gz", "seekbell.sqlite3"):
        assert remove(client, bad).status_code in (404, 405)
        assert client.post("/api/manage/backups/" + bad + "/ticket").status_code in (404, 405)
    assert outside.read_bytes() == b"keep"
    # Links and unknown files never appear in the list.
    assert [row["id"] for row in status(client)["backups"]] == [name]
    assert remove(client, name).status_code == 200
    assert not (settings.backup_dir / name).exists()
    assert status(client)["backups"] == []


def test_unreadable_files_are_listed_for_deletion_but_never_restored(web):
    client, settings, _ = web
    create(client)
    (settings.backup_dir / "copied-in.tar.gz").write_bytes(b"not a backup")
    rows = {row["id"]: row for row in status(client)["backups"]}
    assert rows["copied-in.tar.gz"]["valid"] is False
    assert rows["copied-in.tar.gz"]["kind"] is None
    result = client.post("/api/manage/backups/copied-in.tar.gz/inspect")
    assert result.status_code == 422
    assert remove(client, "copied-in.tar.gz").status_code == 200


def import_elsewhere(client, settings):
    """A backup file that came from somewhere else: its archive is no longer in the library."""
    name = create(client)
    archive = (settings.backup_dir / name).read_bytes()
    assert remove(client, name).status_code == 200
    return archive


def test_import_keeps_a_verified_file_as_an_imported_row(web):
    client, settings, _ = web
    archive = import_elsewhere(client, settings)
    before = table_data(settings.database_path)
    result = upload(client, archive)
    assert result.status_code == 200, result.text
    name = result.json()["id"]
    assert result.json()["duplicate"] is False
    assert library.IMPORTED.fullmatch(name)
    path = settings.backup_dir / name
    assert path.read_bytes() == archive and path.stat().st_mode & 0o777 == 0o600
    [row] = status(client)["backups"]
    assert row["id"] == name and row["valid"] and row["kind"] == "imported"
    assert row["summary"]["workspace"] == "合成恢复空间"
    # An imported file is not a backup of this workspace and is never pruned.
    assert backup_schedule.last_backup_at([row]) is None
    library.prune(settings, keep=1)
    assert path.exists()
    # The same bytes again point at the row already there.
    again = upload(client, archive)
    assert again.json() == {"id": name, "duplicate": True}
    assert [row["id"] for row in status(client)["backups"]] == [name]
    assert_business_unchanged(settings, before)
    assert_clean(settings)


def test_import_is_refused_without_room_for_the_file(web, monkeypatch):
    client, settings, _ = web
    archive = import_elsewhere(client, settings)
    real = library.shutil.disk_usage
    monkeypatch.setattr(
        library.shutil, "disk_usage", lambda path: real(path)._replace(free=len(archive) - 1)
    )
    result = upload(client, archive)
    assert result.status_code == 422 and "磁盘可用空间不足" in result.json()["detail"]
    monkeypatch.undo()
    assert status(client)["backups"] == []
    assert_clean(settings)


def test_inspection_shows_backup_and_current_contents_without_changing_data(web):
    client, settings, _ = web
    name = upload(client, import_elsewhere(client, settings)).json()["id"]
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE tasks SET deleted_at=1")
        connection.commit()
    before = table_data(settings.database_path)
    result = client.post("/api/manage/backups/" + name + "/inspect")
    assert result.status_code == 200, result.text
    found = result.json()
    assert found["backup"]["summary"]["tasks"] == 1 and found["current"]["tasks"] == 0
    # The archive's own kind is shown when checking it; the list calls it imported.
    assert found["backup"]["kind"] == "manual" and found["backup"]["upgrade"] is False
    assert found["stage"]
    assert_business_unchanged(settings, before)
    cancelled = client.delete("/api/manage/backups/inspect/" + found["stage"])
    assert cancelled.json() == {"cancelled": True}
    assert_clean(settings)
    assert restore(client, found["stage"]).status_code == 404
    assert (settings.backup_dir / name).exists()


@pytest.mark.parametrize("kind", ["corrupt", "legacy", "empty"])
def test_failed_import_keeps_live_data_and_cleans_staging(web, kind):
    client, settings, _ = web
    name = create(client)
    archive = (settings.backup_dir / name).read_bytes()
    before = table_data(settings.database_path)
    if kind == "corrupt":
        archive = archive[: len(archive) // 2]
    elif kind == "legacy":
        archive = b"SEEKBELL-BACKUP\x01" + bytes(64)
    else:
        archive = b""
    result = upload(client, archive)
    assert result.status_code == 422
    if kind == "legacy":
        assert "旧版加密备份" in result.json()["detail"]
    assert [row["id"] for row in status(client)["backups"]] == [name]
    assert_business_unchanged(settings, before)
    assert_clean(settings)


def test_upload_bounds_and_type(web, monkeypatch):
    client, settings, _ = web
    monkeypatch.setattr(backup, "MAX_ARCHIVE", 32)
    assert upload(client, b"x" * 33).status_code == 413
    chunks = iter([b"x"] * 33)
    assert upload(client, chunks).status_code == 413
    assert client.post("/api/manage/backups/import", json={}).status_code == 415
    assert_clean(settings)


def test_operation_slot_is_exclusive_and_reusable(web):
    client, settings, app = web
    client.portal.call(app.state.backup_gate.acquire)
    try:
        assert client.post("/api/manage/backups").status_code == 409
        assert upload(client, b"invalid").status_code == 409
    finally:
        client.portal.call(app.state.backup_gate.release)
    create(client)
    assert_clean(settings)


def test_restore_replaces_the_live_workspace_after_a_pre_restore_backup(web):
    client, settings, app = web
    name = create(client)
    before = table_data(settings.database_path)
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE workspace_preferences SET name='恢复前修改'")
        connection.execute("DELETE FROM tasks")
        connection.commit()
    # The current administrator is kept; the backup carries none.
    rename_administrator(client)
    runtime = app.state.runtime
    stage = client.post("/api/manage/backups/" + name + "/inspect").json()["stage"]
    result = restore(client, stage, password=CURRENT_PASSWORD, pause=False)
    assert result.status_code == 200, result.text
    assert result.json()["restored"] and not result.json()["paused"]
    assert result.json()["username"] == "current_admin"
    assert app.state.runtime is not runtime
    after = table_data(settings.database_path)
    for table in ("tasks", "notification_targets", "websites", "posts", "workspace_preferences"):
        assert after[table] == before[table]
    assert len(after["login_sessions"]) == 1
    client.headers["x-csrf-token"] = result.json()["csrf"]
    # The replaced data became a pre-restore backup; nothing else stays behind.
    rows = status(client)["backups"]
    assert [row["kind"] for row in rows] == ["pre-restore", "manual"]
    assert rows[0]["summary"]["workspace"] == "恢复前修改" and rows[0]["summary"]["tasks"] == 0
    assert not list(settings.data_dir.glob("before-restore-*"))
    assert not app.state.restoring and app.state.in_flight == 0
    assert login(client).status_code == 401
    assert login(client, "current_admin", CURRENT_PASSWORD).status_code == 200
    assert_clean(settings)


def test_a_restore_can_be_undone_from_the_pre_restore_backup(web):
    client, settings, _ = web
    name = create(client)
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE workspace_preferences SET name='撤销前'")
        connection.commit()
    stage = client.post("/api/manage/backups/" + name + "/inspect").json()["stage"]
    result = restore(client, stage)
    client.headers["x-csrf-token"] = result.json()["csrf"]
    previous = status(client)["backups"][0]
    assert previous["kind"] == "pre-restore"
    stage = client.post("/api/manage/backups/" + previous["id"] + "/inspect").json()["stage"]
    result = restore(client, stage)
    assert result.status_code == 200, result.text
    with closing(sqlite3.connect(settings.database_path)) as connection:
        assert connection.execute("SELECT name FROM workspace_preferences").fetchone() == (
            "撤销前",
        )


def test_restore_pauses_collection_and_targets_by_default(web):
    client, settings, _ = web
    stage = client.post("/api/manage/backups/" + create(client) + "/inspect").json()["stage"]
    result = restore(client, stage)
    assert result.status_code == 200, result.text
    assert result.json()["paused"]
    with closing(sqlite3.connect(settings.database_path)) as connection:
        assert connection.execute("SELECT max(enabled) FROM websites").fetchone() == (0,)
        assert connection.execute("SELECT max(enabled) FROM notification_targets").fetchone() == (
            0,
        )


def test_wrong_password_keeps_the_live_workspace_and_the_stage(web):
    client, settings, app = web
    stage = client.post("/api/manage/backups/" + create(client) + "/inspect").json()["stage"]
    before = table_data(settings.database_path)
    runtime = app.state.runtime
    result = restore(client, stage, password="Incorrect-Synthetic-Value")
    assert result.status_code == 400
    assert "Incorrect-Synthetic-Value" not in result.text
    assert app.state.runtime is runtime and not app.state.restoring
    assert_business_unchanged(settings, before)
    assert len(status(client)["backups"]) == 1
    # The same inspection can be confirmed again without checking the archive twice.
    assert restore(client, stage).status_code == 200
    assert_clean(settings)


def test_reopen_failure_returns_to_the_original_workspace(web, monkeypatch):
    client, settings, app = web
    stage = client.post("/api/manage/backups/" + create(client) + "/inspect").json()["stage"]
    with closing(sqlite3.connect(settings.database_path)) as connection:
        connection.execute("UPDATE workspace_preferences SET name='保持原样'")
        connection.commit()
    before = table_data(settings.database_path)
    original = app.state.open_workspace
    calls = []

    async def failing_once(target):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("synthetic open failure")
        await original(target)

    monkeypatch.setattr(app.state, "open_workspace", failing_once)
    result = restore(client, stage)
    assert result.status_code == 422
    assert "已回到原数据" in result.json()["detail"]
    assert len(calls) == 2
    assert_business_unchanged(settings, before)
    assert client.get("/api/manage/backups").status_code == 200
    assert_clean(settings)


def test_pre_restore_backup_failure_stops_the_restore(web, monkeypatch):
    client, settings, app = web
    stage = client.post("/api/manage/backups/" + create(client) + "/inspect").json()["stage"]
    before = table_data(settings.database_path)
    runtime = app.state.runtime

    def no_space(*args, **kwargs):
        raise backup.BackupError("磁盘可用空间不足，无法生成备份；请先清理空间或删除旧备份。")

    monkeypatch.setattr(library, "ensure_space", no_space)
    result = restore(client, stage)
    assert result.status_code == 422 and "磁盘可用空间不足" in result.json()["detail"]
    assert app.state.runtime is runtime
    assert_business_unchanged(settings, before)
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


def test_expired_stage_is_refused(web, monkeypatch):
    client, settings, _ = web
    monkeypatch.setattr(backups, "STAGE_SECONDS", -1)
    stage = client.post("/api/manage/backups/" + create(client) + "/inspect").json()["stage"]
    assert restore(client, stage).status_code == 404
    assert_clean(settings)


def test_fresh_installation_can_inspect_then_restore_with_a_new_administrator(web, tmp_path):
    client, settings, _ = web
    archive = (settings.backup_dir / create(client)).read_bytes()
    fresh = Settings(data_dir=tmp_path / "fresh")
    with TestClient(create_app(fresh)) as other:
        state = other.get("/api/auth/status").json()
        assert not state["initialized"]
        headers = {"x-csrf-token": state["csrf"]}
        found = upload(other, archive, "/api/auth/setup/inspect", headers)
        assert found.status_code == 200, found.text
        assert found.json()["current"] is None
        assert found.json()["backup"]["summary"]["workspace"] == "合成恢复空间"
        stage = found.json()["stage"]
        values = {"stage": stage, "username": "fresh_admin", "pause": True}
        short = other.post(
            "/api/auth/setup/restore", json={**values, "admin_password": "short"}, headers=headers
        )
        assert short.status_code == 422
        result = other.post(
            "/api/auth/setup/restore",
            json={**values, "admin_password": CURRENT_PASSWORD},
            headers=headers,
        )
        assert result.status_code == 200, result.text
        # Restoring signs in the newly chosen administrator directly; no pre-restore copy.
        assert other.get("/api/auth/status").json()["username"] == "fresh_admin"
        assert login(other).status_code == 401
        assert login(other, "fresh_admin", CURRENT_PASSWORD).status_code == 200
        assert not list(fresh.backup_dir.glob("*.tar.gz"))
        with closing(sqlite3.connect(fresh.database_path)) as connection:
            name = connection.execute("SELECT name FROM workspace_preferences").fetchone()
        assert name == ("合成恢复空间",)
        # Once an administrator exists the unauthenticated entry is closed.
        other.cookies.clear()
        csrf = other.get("/api/auth/status").json()["csrf"]
        again = upload(other, archive, "/api/auth/setup/inspect", {"x-csrf-token": csrf})
        assert again.status_code == 409
    assert not list(fresh.data_dir.glob(".seekbell-*"))


def test_setup_and_administrator_stages_are_not_interchangeable(web, tmp_path):
    client, settings, app = web
    admin_stage = client.post("/api/manage/backups/" + create(client) + "/inspect").json()["stage"]
    fresh = Settings(data_dir=tmp_path / "fresh")
    with TestClient(create_app(fresh)) as other:
        csrf = other.get("/api/auth/status").json()["csrf"]
        result = other.post(
            "/api/auth/setup/restore",
            json={
                "stage": admin_stage,
                "username": "fresh_admin",
                "admin_password": CURRENT_PASSWORD,
            },
            headers={"x-csrf-token": csrf},
        )
        assert result.status_code == 404
    app.state.backup_stages[admin_stage].setup = True
    assert restore(client, admin_stage).status_code == 404


def test_restore_password_may_be_omitted_shortly_after_it_was_entered(web):
    client, settings, _ = web
    name = create(client)
    stage = client.post("/api/manage/backups/" + name + "/inspect").json()["stage"]
    # Signing in just now counts as entering the password.
    assert status(client)["confirm_seconds"] > 800
    age_session(settings, 16 * 60)
    assert status(client)["confirm_seconds"] == 0
    result = client.post("/api/manage/backups/inspect/" + stage + "/restore", json={})
    assert result.status_code == 403
    assert "当前管理员密码" in result.json()["detail"]
    # Downloading and deleting never ask for the password (user decision 2026-11-10).
    download(client, name)
    assert remove(client, name).status_code == 200


def test_rate_limit_rejects_repeated_privileged_operations(web):
    client, _, _ = web
    name = create(client)
    stage = client.post("/api/manage/backups/" + name + "/inspect").json()["stage"]
    for _ in range(9):
        assert restore(client, stage, password="wrong").status_code == 400
    result = restore(client, stage)
    assert result.status_code == 429
    assert result.headers["retry-after"] == "60"


def test_active_background_runtime_continues_during_a_live_backup(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    token, _ = prepare(settings)
    scenario = SyntheticScenario()
    app = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(app) as client:
        client.cookies.set("seekbell_session", token)
        client.headers["x-csrf-token"] = client.get("/api/auth/status").json()["csrf"]
        name = create(client)
        assert app.state.runtime.active
        assert client.get("/health/ready").status_code == 200
        destination = tmp_path / "verified"
        backup.restore_backup(
            settings,
            settings.backup_dir / name,
            destination,
            administrator=("verified_admin", "scrypt$131072$8$1$" + "0" * 32 + "$" + "0" * 128),
        )
        assert backup.validate_database(destination / "seekbell.sqlite3")
        assert_clean(settings)


def test_oversized_snapshot_aborts_and_cleans_files(web, monkeypatch):
    client, settings, _ = web
    monkeypatch.setattr(backup, "MAX_DATABASE", 1024)
    result = client.post("/api/manage/backups")
    assert result.status_code == 422
    assert "2 GiB" in result.json()["detail"]
    assert status(client)["backups"] == []
    assert_clean(settings)


def test_too_little_disk_space_is_refused_before_writing(web, monkeypatch):
    client, settings, _ = web
    real = library.shutil.disk_usage

    def tight(path):
        usage = real(path)
        return usage._replace(free=1024)

    monkeypatch.setattr(library.shutil, "disk_usage", tight)
    result = client.post("/api/manage/backups")
    assert result.status_code == 422 and "磁盘可用空间不足" in result.json()["detail"]
    monkeypatch.undo()
    assert status(client)["backups"] == []


def test_write_failure_is_redacted_and_releases_operation_slot(web, monkeypatch):
    client, settings, _ = web
    original = backup.snapshot_backup

    def fail(*args, **kwargs):
        raise OSError("Synthetic-private-path-and-secret")

    monkeypatch.setattr(backup, "snapshot_backup", fail)
    result = client.post("/api/manage/backups")
    assert result.status_code == 422
    assert "Synthetic-private-path-and-secret" not in result.text
    assert_clean(settings)
    monkeypatch.setattr(backup, "snapshot_backup", original)
    create(client)


def test_disconnected_upload_cleans_partial_file_and_keeps_live_data(web, monkeypatch):
    from starlette.requests import ClientDisconnect, Request

    client, settings, _ = web
    before = table_data(settings.database_path)
    original = Request.stream

    async def interrupted(request):
        if request.url.path.endswith("/import"):
            yield b"partial"
            raise ClientDisconnect
        async for chunk in original(request):
            yield chunk

    monkeypatch.setattr(Request, "stream", interrupted)
    result = upload(client, b"ignored")
    assert result.status_code == 400
    assert_business_unchanged(settings, before)
    assert_clean(settings)


def test_snapshot_failure_does_not_expose_database_error(web, monkeypatch):
    client, settings, _ = web

    def unavailable(*args, **kwargs):
        raise backups.SQLAlchemyError("Synthetic sensitive database failure")

    monkeypatch.setattr(library, "create", unavailable)
    response = client.post("/api/manage/backups")
    assert response.status_code == 422
    assert "Synthetic sensitive" not in response.text
    assert "原数据未被覆盖" in response.text
    assert_clean(settings)


def test_safety_copies_expire_after_thirty_days_except_the_newest(web):
    client, settings, _ = web
    day = 86400
    now = time.time()
    names = {}
    for kind, age in (
        ("pre-restore", 40),
        ("pre-restore", 35),
        ("manual", 90),
        ("pre-upgrade", 50),
    ):
        names[(kind, age)] = library.create(settings, kind, at=now - age * day)[0]
    library.prune(settings, at=now)
    left = {row["id"] for row in status(client)["backups"]}
    # The newest pre-restore (35 days) stays; the older one goes; manual is never pruned.
    assert names[("pre-restore", 35)] in left and names[("pre-restore", 40)] not in left
    assert names[("manual", 90)] in left and names[("pre-upgrade", 50)] in left


def test_start_removes_earlier_restore_directories_and_temporary_files(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    prepare(settings)
    root = settings.data_dir
    for name in ("before-restore-20261101T000000Z-abcd1234", "web-restore", ".seekbell-web-x"):
        (root / name).mkdir()
        (root / name / "seekbell.sqlite3").write_bytes(b"old")
    held = root / "held"
    held.mkdir()
    (root / "other-directory").mkdir()
    settings.backup_dir.mkdir(mode=0o700)
    (settings.backup_dir / ".seekbell-archive-x").write_bytes(b"partial")
    with TestClient(create_app(settings)):
        pass
    assert sorted(path.name for path in root.iterdir() if path.is_dir()) == [
        "backups",
        "held",
        "other-directory",
    ]
    assert list(settings.backup_dir.iterdir()) == []


def test_start_keeps_a_restore_copy_another_instance_is_using(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    prepare(settings)
    copy = settings.data_dir / "web-restore"
    copy.mkdir()
    lock = copy / ".instance.lock"
    lock.write_bytes(b"")
    with lock.open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        with TestClient(create_app(settings)):
            pass
        assert copy.exists()


def test_library_path_never_follows_links(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    settings.data_dir.mkdir()
    settings.backup_dir.mkdir()
    target = tmp_path / "secret.tar.gz"
    target.write_bytes(b"x")
    os.symlink(target, settings.backup_dir / "link.tar.gz")
    assert library.path_for(settings, "link.tar.gz") is None
    assert library.path_for(settings, "../secret.tar.gz") is None
    assert library.path_for(settings, Path("x").name + "/y.tar.gz") is None
