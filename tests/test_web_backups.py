import asyncio
import json
import tempfile
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
    metadata = values(username="backup_admin", admin_password=ADMIN_PASSWORD, **overrides)
    return json.dumps(metadata).encode() + b"\n" + archive


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


@pytest.mark.parametrize("path", ["download", "restore"])
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
    else:
        metadata = {**data, "username": "backup_admin", "admin_password": ADMIN_PASSWORD}
        result = restore(client, json.dumps(metadata).encode() + b"\ninvalid")
    assert (
        result.status_code == {"anonymous": 401, "csrf": 403, "origin": 403, "password": 400}[kind]
    )
    assert "Incorrect-Current-Password" not in result.text
    assert not (settings.data_dir / backups.CANDIDATE).exists()
    assert_clean(settings)


@pytest.mark.parametrize("kind", ["corrupt", "password", "admin_password", "username"])
def test_failed_upload_authentication_preserves_live_database_and_cleans_staging(web, kind):
    client, settings, _ = web
    archive = download(client).content
    before = table_data(settings.database_path)
    if kind == "corrupt":
        archive = archive[:-1] + bytes([archive[-1] ^ 1])
        body = upload(archive)
    else:
        metadata = values(username="backup_admin", admin_password=ADMIN_PASSWORD)
        metadata[kind] = "Incorrect-Synthetic-Value"
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
    metadata = values(
        username="backup_admin", admin_password=ADMIN_PASSWORD, destination="../source"
    )
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
            username="backup_admin",
            admin_password=ADMIN_PASSWORD,
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
