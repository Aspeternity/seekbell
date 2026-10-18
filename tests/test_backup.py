import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from seekbell.backup import (
    BackupError,
    _decrypt,
    _encrypt,
    create_backup,
    restore_backup,
)
from seekbell.config import Settings
from seekbell.db.models import BrowserSession, DeliveredPost, Outbox, SeenPost
from seekbell.db.runtime import create_database_engine, instance_lock, schema_revision
from seekbell.main import create_app
from seekbell.notifiers.credentials import CredentialError, CredentialVault
from seekbell.services.configuration import Configuration
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tests.test_authentication import CREDENTIALS, setup

PASSWORD = CREDENTIALS["password"]
PASSPHRASE = "synthetic archive encryption phrase"


@pytest.fixture
def saved(tmp_path):
    settings = Settings(data_dir=tmp_path / "source", build_revision="synthetic-sha")
    with TestClient(create_app(settings)) as client:
        setup(client)
        config = client.app.state.configuration
        target = config.create_target(
            "Synthetic webhook",
            kind="webhook",
            config={"url": "https://example.com/hook", "headers": {"X-Key": "synthetic-secret"}},
        )
        from seekbell.domain.rules import Rule
        from seekbell.services.ingestion import Ingestion

        from tests.core_helpers import batch

        config.create_task("Synthetic task", Rule(), [target], at=1)
        config.configure_site(enabled=True, interval_seconds=60, at=1)
        ingestion = Ingestion(client.app.state.engine)
        ingestion.ingest("nodeseek-rss", batch(9001), at=10)
        ingestion.ingest("nodeseek-rss", batch(9001, 9002), at=20)
        from seekbell.domain.delivery import SendResult
        from seekbell.services.delivery import DeliveryWorker

        worker = DeliveryWorker(client.app.state.engine, {})
        lease = worker.claim(at=21)
        worker.finish(lease, SendResult(status="success"), at=22)
        old_cookie = client.cookies.get("seekbell_session")
    output = tmp_path / "backup.sbb"
    create_backup(settings, output, password=PASSWORD, passphrase=PASSPHRASE)
    return settings, output, target, old_cookie


def restore_to(saved, directory, **kwargs):
    return restore_backup(
        Settings(data_dir=directory),
        saved[1],
        password=kwargs.get("password", PASSWORD),
        passphrase=kwargs.get("passphrase", PASSPHRASE),
    )


def test_encrypted_backup_restores_credentials_identity_and_dedup(saved, tmp_path):
    source, archive, target, cookie = saved
    assert archive.stat().st_mode & 0o777 == 0o600
    assert b"synthetic-secret" not in archive.read_bytes()
    assert (source.data_dir / "credentials.key").read_bytes() not in archive.read_bytes()
    restored = Settings(data_dir=tmp_path / "restored")
    restore_to(saved, restored.data_dir)
    assert (restored.data_dir / "credentials.key").read_bytes() == (
        source.data_dir / "credentials.key"
    ).read_bytes()
    assert (restored.data_dir / "credentials.key").stat().st_mode & 0o777 == 0o600
    with TestClient(create_app(restored)) as client:
        engine = client.app.state.engine
        with Session(engine) as session:
            for model, count in ((SeenPost, 2), (DeliveredPost, 1), (Outbox, 1)):
                assert session.scalar(select(func.count()).select_from(model)) == count
            assert session.scalar(select(func.count()).select_from(BrowserSession)) == 0
        config = Configuration(engine, CredentialVault.open(restored.data_dir))
        assert config.get_target(target)["configured_secrets"] == ["headers", "url"]
        from seekbell.services.ingestion import Ingestion

        from tests.core_helpers import batch

        Ingestion(engine).ingest("nodeseek-rss", batch(9001, 9002), at=30)
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Outbox)) == 1
        client.cookies.set("seekbell_session", cookie)
        assert client.get("/api/manage/settings").status_code == 401
        assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("which", ["password", "passphrase"])
def test_wrong_password_leaves_destination_empty(saved, tmp_path, which):
    target = tmp_path / "bad"
    with pytest.raises((BackupError, InvalidTag)):
        restore_to(saved, target, **{which: "incorrect synthetic passphrase"})
    assert {p.name for p in target.iterdir()} == {".instance.lock"}
    restore_to(saved, target)


def test_backup_requires_stopped_service_and_correct_password(saved, tmp_path):
    settings = saved[0]
    output = tmp_path / "new.sbb"
    with instance_lock(settings.data_dir), pytest.raises(RuntimeError):
        create_backup(settings, output, password=PASSWORD, passphrase=PASSPHRASE)
    with pytest.raises(BackupError):
        create_backup(settings, output, password="wrong", passphrase=PASSPHRASE)
    assert not output.exists()
    assert not list(settings.data_dir.glob(".backup-*"))


def test_refuses_existing_backup_or_restore_directory(saved, tmp_path):
    original = saved[1].read_bytes()
    with pytest.raises(BackupError):
        create_backup(saved[0], saved[1], password=PASSWORD, passphrase=PASSPHRASE)
    with pytest.raises(BackupError):
        restore_to(saved, saved[0].data_dir)
    assert saved[1].read_bytes() == original
    with instance_lock(tmp_path / "busy"), pytest.raises(RuntimeError):
        restore_to(saved, tmp_path / "busy")


@pytest.mark.parametrize("change", ["tamper", "truncate", "header"])
def test_corrupt_backup_is_never_installed(saved, tmp_path, change):
    archive = bytearray(saved[1].read_bytes())
    if change == "truncate":
        archive = archive[:-10]
    else:
        archive[0 if change == "header" else 100] ^= 1
    saved[1].write_bytes(archive)
    with pytest.raises((BackupError, InvalidTag)):
        restore_to(saved, tmp_path / "corrupt")
    assert not (tmp_path / "corrupt" / "seekbell.sqlite3").exists()


def repack(saved, tmp_path, change):
    payload = tmp_path / "decrypted.tar"
    _decrypt(saved[1], payload, PASSPHRASE)
    with tarfile.open(payload) as bundle:
        entries = {member.name: bundle.extractfile(member).read() for member in bundle}
    change(entries)
    with tarfile.open(payload, "w") as bundle:
        for name, content in entries.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            bundle.addfile(member, io.BytesIO(content))
    with saved[1].open("wb") as stream:
        _encrypt(payload, stream, PASSPHRASE)


@pytest.mark.parametrize("change", ["traversal", "missing_key", "wrong_key", "manifest", "future"])
def test_authenticated_but_invalid_payload_rejected(saved, tmp_path, change):
    def alter(entries):
        if change == "traversal":
            entries["../escaped"] = b"bad"
        elif change == "missing_key":
            del entries["credentials.key"]
        elif change == "wrong_key":
            from cryptography.fernet import Fernet

            entries["credentials.key"] = Fernet.generate_key()
        elif change == "manifest":
            manifest = json.loads(entries["manifest.json"])
            manifest["database_revision"] = "mismatch"
            entries["manifest.json"] = json.dumps(manifest).encode()
        else:
            db = tmp_path / "edit.sqlite3"
            db.write_bytes(entries["seekbell.sqlite3"])
            with sqlite3.connect(db) as connection:
                connection.execute("UPDATE alembic_version SET version_num='future_revision'")
            connection.close()
            entries["seekbell.sqlite3"] = db.read_bytes()

    repack(saved, tmp_path, alter)
    with pytest.raises((BackupError, CredentialError)):
        restore_to(saved, tmp_path / "invalid")
    assert not (tmp_path / "invalid" / "seekbell.sqlite3").exists()
    assert not (tmp_path / "escaped").exists()


def test_migration_failure_keeps_destination_empty_and_original_backup(
    saved, tmp_path, monkeypatch
):
    import seekbell.backup as module

    original = saved[1].read_bytes()

    def fail(engine):
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE synthetic_failed_migration (id INTEGER)")
        raise RuntimeError("synthetic migration failure")

    with monkeypatch.context() as patch:
        patch.setattr(module, "migrate", fail)
        with pytest.raises(RuntimeError):
            restore_to(saved, tmp_path / "recovered")
    assert saved[1].read_bytes() == original
    assert not (tmp_path / "recovered" / "seekbell.sqlite3").exists()
    restore_to(saved, tmp_path / "recovered")
    engine = create_database_engine(Settings(data_dir=tmp_path / "recovered"))
    try:
        assert schema_revision(engine) == "0007_settings"
    finally:
        engine.dispose()


def test_backup_includes_committed_wal_pages(saved, tmp_path):
    settings, _, target, _ = saved
    connection = sqlite3.connect(settings.database_path)
    try:
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute(
            "UPDATE notification_targets SET name='committed-in-wal' WHERE id=?", (target,)
        )
        connection.commit()
        assert Path(str(settings.database_path) + "-wal").stat().st_size > 0
        output = tmp_path / "wal.sbb"
        create_backup(settings, output, password=PASSWORD, passphrase=PASSPHRASE)
    finally:
        connection.close()
    destination = Settings(data_dir=tmp_path / "wal-restored")
    restore_backup(destination, output, password=PASSWORD, passphrase=PASSPHRASE)
    engine = create_database_engine(destination)
    try:
        assert (
            Configuration(engine, CredentialVault.open(destination.data_dir)).get_target(target)[
                "name"
            ]
            == "committed-in-wal"
        )
    finally:
        engine.dispose()


def test_old_schema_upgrades_in_staging_and_backup_supports_rollback(saved, tmp_path):
    from alembic import command
    from seekbell.db.runtime import migration_config

    def older(entries):
        directory = tmp_path / "old"
        directory.mkdir()
        database = directory / "seekbell.sqlite3"
        database.write_bytes(entries["seekbell.sqlite3"])
        engine = create_database_engine(Settings(data_dir=directory))
        try:
            with engine.begin() as connection:
                config = migration_config()
                config.attributes["connection"] = connection
                command.downgrade(config, "0006_manual_deliveries")
        finally:
            engine.dispose()
        entries["seekbell.sqlite3"] = database.read_bytes()
        manifest = json.loads(entries["manifest.json"])
        manifest["database_revision"] = "0006_manual_deliveries"
        entries["manifest.json"] = json.dumps(manifest).encode()

    repack(saved, tmp_path, older)
    original = saved[1].read_bytes()
    restore_to(saved, tmp_path / "upgraded")
    engine = create_database_engine(Settings(data_dir=tmp_path / "upgraded"))
    try:
        assert schema_revision(engine) == "0007_settings"
    finally:
        engine.dispose()
    assert saved[1].read_bytes() == original
    # The original version remains available, independently of the migrated volume.
    payload = tmp_path / "rollback.tar"
    _decrypt(saved[1], payload, PASSPHRASE)
    with tarfile.open(payload) as bundle:
        database = tmp_path / "rollback.sqlite3"
        database.write_bytes(bundle.extractfile("seekbell.sqlite3").read())
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "0006_manual_deliveries",
        )


def test_interrupted_install_is_cleaned_or_blocks_startup(saved, tmp_path, monkeypatch):
    import seekbell.backup as module

    original = module.os.replace

    def fail_database(source, destination):
        if Path(destination).name == "seekbell.sqlite3":
            raise OSError("synthetic disk failure")
        return original(source, destination)

    destination = tmp_path / "interrupted"
    with monkeypatch.context() as patch:
        patch.setattr(module.os, "replace", fail_database)
        with pytest.raises(OSError):
            restore_to(saved, destination)
    assert {p.name for p in destination.iterdir()} == {".instance.lock"}
    (destination / ".restore-in-progress").write_text("synthetic crash marker")
    with (
        pytest.raises(RuntimeError, match="Incomplete restore"),
        TestClient(create_app(Settings(data_dir=destination))),
    ):
        pytest.fail("Incomplete restore must never serve requests")
    assert not (destination / "seekbell.sqlite3").exists()
    (destination / ".restore-in-progress").unlink()
    restore_to(saved, destination)


def test_process_killed_during_staging_leaves_startup_blocked(saved, tmp_path):
    import subprocess
    import sys

    destination = tmp_path / "killed-restore"
    code = """
import os
import signal
import sys
from pathlib import Path
import seekbell.backup as module
from seekbell.config import Settings

def crash(*args):
    os.kill(os.getpid(), signal.SIGKILL)
module._decrypt = crash
module.restore_backup(Settings(data_dir=Path(sys.argv[1])), Path(sys.argv[2]),
    password='synthetic unused', passphrase='synthetic unused phrase')
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(destination), str(saved[1])],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == -9
    assert (destination / ".restore-in-progress").is_file()
    with (
        pytest.raises(RuntimeError, match="Incomplete restore"),
        TestClient(create_app(Settings(data_dir=destination))),
    ):
        pytest.fail("A killed restore must never silently initialize an empty instance")
    assert not (destination / "seekbell.sqlite3").exists()
