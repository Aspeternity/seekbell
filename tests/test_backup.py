import json
import os
import sqlite3
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from cryptography.fernet import Fernet
from seekbell import backup
from seekbell.config import Settings
from seekbell.db.runtime import instance_lock
from seekbell.notifiers.credentials import CredentialError
from seekbell.services.authentication import password_hash, verify_password
from seekbell.services.backup_demo import (
    ADMIN_PASSWORD,
    PASSWORD,
    exercise,
    prepare,
    table_data,
)

NEW_PASSWORD = "Synthetic-New-Administrator"


@pytest.fixture
def source(tmp_path):
    settings = Settings(data_dir=tmp_path / "source", build_revision="synthetic-test-revision")
    prepare(settings)
    return settings


@pytest.fixture
def archive(source, tmp_path):
    path = tmp_path / "sample.sbbackup"
    backup.create_backup(source, path, password=PASSWORD)
    return path


def restore(source, archive, destination, **values):
    return backup.restore_backup(
        source,
        archive,
        destination,
        password=values.get("password", PASSWORD),
        administrator=values.get("administrator"),
    )


def test_complete_rehearsal_preserves_tables_credentials_queues_and_revokes_sessions(tmp_path):
    result = exercise(tmp_path)
    assert result["all_tables_preserved"] and result["source_unchanged"]
    assert result["old_sessions_revoked"] and result["original_key_usable"]
    assert result["pending_automatic"] == result["resumed_sends"] == 1
    assert result["pending_alerts"] == 2
    assert not list(tmp_path.glob(".seekbell-*"))


def test_consistent_snapshot_includes_committed_wal_and_has_private_permissions(source, tmp_path):
    with closing(sqlite3.connect(source.database_path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE workspace_preferences SET name='WAL snapshot'")
        writer.commit()
        assert source.database_path.with_name("seekbell.sqlite3-wal").stat().st_size > 0
        path, destination = tmp_path / "wal.sbbackup", tmp_path / "restored"
        backup.create_backup(source, path, password=PASSWORD)
        restore(source, path, destination)
        with closing(sqlite3.connect(destination / "seekbell.sqlite3")) as connection:
            assert connection.execute("SELECT name FROM workspace_preferences").fetchone() == (
                "WAL snapshot",
            )
    assert path.stat().st_mode & 0o777 == 0o600
    assert destination.stat().st_mode & 0o777 == 0o700
    for name in ("credentials.key", "seekbell.sqlite3"):
        assert (destination / name).stat().st_mode & 0o777 == 0o600
    assert b"SQLite format" not in path.read_bytes()
    assert b"backup-synthetic-private" not in path.read_bytes()
    assert (source.data_dir / "credentials.key").read_bytes() not in path.read_bytes()


def test_failed_authentication_never_publishes_or_changes_source(source, archive, tmp_path):
    before = table_data(source.database_path)
    destination = tmp_path / "restored"
    with pytest.raises(backup.BackupError):
        restore(source, archive, destination, password="Incorrect-backup-password")
    assert not destination.exists()
    assert table_data(source.database_path) == before
    assert not list(tmp_path.glob(".seekbell-*"))


def test_restore_can_replace_the_backup_administrator(source, archive, tmp_path):
    destination = tmp_path / "restored"
    encoded = password_hash(NEW_PASSWORD)
    restore(source, archive, destination, administrator=("new_admin", encoded))
    assert backup.validate_database(destination / "seekbell.sqlite3") == ("new_admin", encoded)
    with pytest.raises(backup.BackupError):
        restore(source, archive, tmp_path / "invalid", administrator=("x", encoded))
    assert not (tmp_path / "invalid").exists()


@pytest.mark.parametrize("damage", ["tag", "header", "truncated", "append"])
def test_corrupt_archive_is_rejected_before_database_access(
    source, archive, tmp_path, monkeypatch, damage
):
    data = bytearray(archive.read_bytes())
    if damage == "tag":
        data[-1] ^= 1
    elif damage == "header":
        data[0] ^= 1
    elif damage == "truncated":
        del data[-40:]
    else:
        data.extend(b"unexpected")
    archive.write_bytes(data)

    def forbidden(*args):
        pytest.fail("Unauthenticated payload must never be inspected")

    monkeypatch.setattr(backup, "unpack_payload", forbidden)
    with pytest.raises(backup.BackupError):
        restore(source, archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize("kind", ["file", "directory", "empty", "symlink"])
def test_existing_destinations_are_never_replaced(source, archive, tmp_path, kind):
    destination = tmp_path / "existing"
    if kind == "file":
        destination.write_text("keep")
    elif kind == "symlink":
        destination.symlink_to(source.data_dir, target_is_directory=True)
    else:
        destination.mkdir()
        if kind == "directory":
            (destination / "marker").write_text("keep")
    before = table_data(source.database_path)
    with pytest.raises(backup.BackupError):
        restore(source, archive, destination)
    assert os.path.lexists(destination) and table_data(source.database_path) == before
    if kind == "directory":
        assert (destination / "marker").read_text() == "keep"


def test_create_rejects_existing_archive_and_running_instance(source, tmp_path):
    path = tmp_path / "existing.sbbackup"
    path.write_bytes(b"keep")
    with pytest.raises(backup.BackupError):
        backup.create_backup(source, path, password=PASSWORD)
    assert path.read_bytes() == b"keep"
    path.unlink()
    with instance_lock(source.data_dir), pytest.raises(RuntimeError):
        backup.create_backup(source, path, password=PASSWORD)
    assert not path.exists()


@pytest.mark.parametrize("kind", ["missing", "wrong", "public"])
def test_unusable_original_key_cannot_produce_an_unrestorable_backup(source, tmp_path, kind):
    key = source.data_dir / "credentials.key"
    if kind == "missing":
        key.unlink()
    elif kind == "wrong":
        key.write_bytes(Fernet.generate_key())
    else:
        key.chmod(0o644)
    path = tmp_path / "bad.sbbackup"
    with pytest.raises(CredentialError):
        backup.create_backup(source, path, password=PASSWORD)
    assert not path.exists() and not list(tmp_path.glob(".seekbell-*"))


def rewrite_archive(archive, tmp_path, mutate):
    payload = tmp_path / "raw"
    backup.decrypt_file(archive, payload, PASSWORD)
    raw = payload.read_bytes()
    length = struct.unpack(">I", raw[:4])[0]
    manifest = json.loads(raw[4 : 4 + length])
    key, database = raw[4 + length : 4 + length + 44], raw[4 + length + 44 :]
    manifest, key, database = mutate(manifest, key, database)
    encoded = json.dumps(manifest).encode()
    payload.write_bytes(struct.pack(">I", len(encoded)) + encoded + key + database)
    backup.encrypt_file(payload, archive, PASSWORD)
    payload.unlink()


@pytest.mark.parametrize(
    "kind", ["format", "revision", "digest", "size", "key", "database_revision", "schema"]
)
def test_authenticated_but_incompatible_payload_never_publishes(source, archive, tmp_path, kind):
    def mutate(manifest, key, database):
        if kind == "format":
            manifest["format"] = 2
        elif kind == "revision":
            manifest["database_revision"] = "future"
        elif kind == "digest":
            manifest["database_sha256"] = "0" * 64
        elif kind == "size":
            manifest["database_bytes"] += 1
        elif kind == "key":
            key = Fernet.generate_key()
        else:
            path = tmp_path / "change.sqlite3"
            path.write_bytes(database)
            with closing(sqlite3.connect(path)) as connection:
                if kind == "schema":
                    connection.execute("DROP TABLE source_probes")
                else:
                    connection.execute("UPDATE alembic_version SET version_num='future'")
                connection.commit()
            database = path.read_bytes()
            import hashlib

            manifest["database_sha256"] = hashlib.sha256(database).hexdigest()
        return manifest, key, database

    rewrite_archive(archive, tmp_path, mutate)
    with pytest.raises((backup.BackupError, CredentialError)):
        restore(source, archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_concurrent_restores_publish_one_complete_directory(source, archive, tmp_path):
    destination = tmp_path / "restored"

    def attempt():
        try:
            restore(source, archive, destination)
            return True
        except (backup.BackupError, OSError):
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == [False, True]
    assert backup.validate_database(destination / "seekbell.sqlite3")
    backup.validate_credentials(destination)
    assert not list(tmp_path.glob(".seekbell-*"))


def test_atomic_directory_publish_rejects_even_a_concurrently_created_empty_target(tmp_path):
    stage, target = tmp_path / "stage", tmp_path / "target"
    stage.mkdir()
    (stage / "marker").write_text("keep")
    target.mkdir()
    with pytest.raises(OSError):
        backup.publish_directory(stage, target)
    assert (stage / "marker").read_text() == "keep"
    assert not list(target.iterdir())


def test_cli_refuses_secret_arguments_and_non_interactive_input(source, tmp_path):
    command = [
        sys.executable,
        "-m",
        "seekbell.backup",
        "create",
        "--output",
        str(tmp_path / "cli.sbbackup"),
    ]
    result = subprocess.run(
        command,
        input="secret-in-pipe",
        text=True,
        capture_output=True,
        env={**os.environ, "SEEKBELL_DATA_DIR": str(source.data_dir)},
    )
    assert result.returncode == 1 and "secret-in-pipe" not in result.stderr
    assert not (tmp_path / "cli.sbbackup").exists()
    help_result = subprocess.run(
        [sys.executable, "-m", "seekbell.backup", "restore", "--help"],
        text=True,
        capture_output=True,
    )
    assert help_result.returncode == 0 and "--password" not in help_result.stdout


@pytest.mark.parametrize("kind", ["revision", "admin_hash", "historical_key"])
def test_invalid_database_or_historical_key_never_creates_backup(source, tmp_path, kind):
    with closing(sqlite3.connect(source.database_path)) as connection:
        if kind == "revision":
            connection.execute("UPDATE alembic_version SET version_num='future'")
        elif kind == "admin_hash":
            connection.execute("UPDATE administrators SET password_hash='invalid'")
        else:
            connection.execute("UPDATE notification_targets SET config_ciphertext=NULL")
        connection.commit()
    if kind == "historical_key":
        (source.data_dir / "credentials.key").write_bytes(Fernet.generate_key())
    with pytest.raises((backup.BackupError, CredentialError)):
        backup.create_backup(source, tmp_path / "invalid.sbbackup", password=PASSWORD)
    assert not (tmp_path / "invalid.sbbackup").exists()


def test_interactive_cli_roundtrip_does_not_echo_passwords(source, tmp_path):
    import pty
    import select
    import time

    def command(arguments, answers):
        master, slave = pty.openpty()
        process = subprocess.Popen(
            [sys.executable, "-m", "seekbell.backup", *arguments],
            start_new_session=True,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env={**os.environ, "SEEKBELL_DATA_DIR": str(source.data_dir)},
        )
        os.close(slave)
        output, position = b"", 0
        deadline = time.monotonic() + 30
        try:
            for prompt, value in answers:
                while prompt.encode() not in output[position:]:
                    if time.monotonic() > deadline:
                        pytest.fail("Interactive command did not prompt")
                    readable, _, _ = select.select([master], [], [], 0.1)
                    if readable:
                        output += os.read(master, 65536)
                position = len(output)
                os.write(master, value.encode() + b"\n")
            while process.poll() is None:
                readable, _, _ = select.select([master], [], [], 0.1)
                if readable:
                    try:
                        output += os.read(master, 65536)
                    except OSError:
                        break
            assert process.wait(timeout=10) == 0
            for secret in (PASSWORD, ADMIN_PASSWORD, NEW_PASSWORD):
                assert secret.encode() not in output
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)

    archive, destination = tmp_path / "cli.sbbackup", tmp_path / "restored"
    command(
        ["create", "--output", str(archive)],
        [
            ("备份口令（", PASSWORD),
            ("再次输入备份口令", PASSWORD),
        ],
    )
    command(
        ["restore", "--archive", str(archive), "--destination", str(destination)],
        [
            ("备份口令（", PASSWORD),
            ("恢复后的管理员用户名", "new_admin"),
            ("管理员密码（", NEW_PASSWORD),
            ("再次输入管理员密码", NEW_PASSWORD),
        ],
    )
    username, encoded = backup.validate_database(destination / "seekbell.sqlite3")
    assert username == "new_admin" and verify_password(NEW_PASSWORD, encoded)
    kept = tmp_path / "kept"
    command(
        ["restore", "--archive", str(archive), "--destination", str(kept)],
        [("备份口令（", PASSWORD), ("恢复后的管理员用户名", "")],
    )
    assert backup.validate_database(kept / "seekbell.sqlite3")[0] == "backup_admin"


def test_custom_overview_layout_and_selection_survive_encrypted_restore(source, tmp_path):
    modules = [
        {"id": "hotlist", "visible": True},
        {"id": "tasks", "visible": False},
        {"id": "matches", "visible": True},
    ]
    with closing(sqlite3.connect(source.database_path)) as connection:
        connection.execute(
            "UPDATE overview_preferences SET modules=?,revision=7,website_id=?,"
            "periods=?,selection_revision=4",
            (json.dumps(modules), "nodeseek", json.dumps({"nodeseek": "weekly"})),
        )
        connection.commit()
    path, destination = tmp_path / "overview.sbbackup", tmp_path / "overview-restored"
    backup.create_backup(source, path, password=PASSWORD)
    restore(source, path, destination)
    with closing(sqlite3.connect(destination / "seekbell.sqlite3")) as connection:
        row = connection.execute(
            "SELECT modules,revision,website_id,periods,selection_revision "
            "FROM overview_preferences"
        ).fetchone()
        assert json.loads(row[0]) == modules
        assert row[1:3] == (7, "nodeseek")
        assert json.loads(row[3]) == {"nodeseek": "weekly"}
        assert row[4] == 4


def older_archive(archive, tmp_path):
    """Hand-revert the latest migration to stand in for a backup from the previous release."""

    def mutate(manifest, key, database):
        import hashlib

        path = tmp_path / "older.sqlite3"
        path.write_bytes(database)
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("DROP TABLE backup_records")
            connection.execute("ALTER TABLE workspace_preferences DROP COLUMN workspace_revision")
            connection.execute("UPDATE alembic_version SET version_num='0017_hotlist_settings'")
            connection.commit()
        database = path.read_bytes()
        path.unlink()
        manifest["database_revision"] = "0017_hotlist_settings"
        manifest["database_bytes"] = len(database)
        manifest["database_sha256"] = hashlib.sha256(database).hexdigest()
        return manifest, key, database

    rewrite_archive(archive, tmp_path, mutate)


def test_older_backup_is_upgraded_inside_the_restored_copy(source, archive, tmp_path):
    older_archive(archive, tmp_path)
    destination = tmp_path / "restored"
    manifest = restore(source, archive, destination)
    assert manifest["database_revision"] == "0017_hotlist_settings"
    backup.validate_database(destination / "seekbell.sqlite3")
    backup.validate_credentials(destination)
    expected = table_data(source.database_path)
    restored = table_data(destination / "seekbell.sqlite3")
    for name in ("tasks", "notification_targets", "websites", "posts"):
        assert restored[name] == expected[name]
    assert not list(tmp_path.glob(".seekbell-*"))


def test_pause_disables_collection_and_targets_in_the_restored_copy(source, archive, tmp_path):
    destination = tmp_path / "restored"
    backup.restore_backup(
        source,
        archive,
        destination,
        password=PASSWORD,
        pause=True,
    )
    with closing(sqlite3.connect(destination / "seekbell.sqlite3")) as connection:
        assert connection.execute("SELECT max(enabled) FROM websites").fetchone() == (0,)
        assert connection.execute("SELECT max(enabled) FROM notification_targets").fetchone() == (
            0,
        )
    with closing(sqlite3.connect(source.database_path)) as connection:
        assert connection.execute("SELECT max(enabled) FROM websites").fetchone() == (1,)
