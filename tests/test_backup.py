import gzip
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from cryptography.fernet import Fernet
from seekbell import backup
from seekbell.config import Settings
from seekbell.db.runtime import instance_lock
from seekbell.notifiers.credentials import CredentialError
from seekbell.services.authentication import password_hash, verify_password
from seekbell.services.backup_demo import ADMIN_PASSWORD, exercise, prepare, table_data

NEW_PASSWORD = "Synthetic-New-Administrator"
ADMINISTRATOR = ("new_admin", password_hash(NEW_PASSWORD))


@pytest.fixture
def source(tmp_path):
    settings = Settings(data_dir=tmp_path / "source", build_revision="synthetic-test-revision")
    prepare(settings)
    return settings


@pytest.fixture
def archive(source, tmp_path):
    path = tmp_path / "sample.tar.gz"
    backup.create_backup(source, path)
    return path


def restore(source, archive, destination, **values):
    return backup.restore_backup(
        source,
        archive,
        destination,
        administrator=values.get("administrator", ADMINISTRATOR),
        pause=values.get("pause", False),
    )


def members(archive):
    with tarfile.open(archive, "r:gz") as tar:
        return {entry.name: tar.extractfile(entry).read() for entry in tar.getmembers()}


def write_members(archive, items):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in items:
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o600
            tar.addfile(info, io.BytesIO(data))
    archive.write_bytes(raw.getvalue())


def rewrite_archive(archive, mutate):
    """Re-pack an archive after `mutate(manifest, files)`; hashes are NOT refreshed."""
    files = members(archive)
    manifest = json.loads(files.pop("manifest.json"))
    manifest = mutate(manifest, files) or manifest
    write_members(
        archive,
        [("manifest.json", json.dumps(manifest).encode()), *files.items()],
    )


def refresh(manifest, files):
    for name, data in files.items():
        manifest["files"][name] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def test_complete_rehearsal_preserves_tables_credentials_queues_and_revokes_sessions(tmp_path):
    result = exercise(tmp_path)
    assert result["all_tables_preserved"] and result["source_unchanged"]
    assert result["old_sessions_revoked"] and result["original_key_usable"]
    assert result["pending_automatic"] == result["resumed_sends"] == 1
    assert result["pending_alerts"] == 2
    assert not list(tmp_path.glob(".seekbell-*"))


def test_archive_is_a_standard_tar_gz_without_administrator_or_sessions(source, archive):
    files = members(archive)
    assert list(files) == ["manifest.json", "seekbell.sqlite3", "credentials.key"]
    manifest = json.loads(files["manifest.json"])
    assert manifest["format"] == 2 and manifest["kind"] == "manual"
    assert manifest["summary"] == {
        "workspace": "合成恢复空间",
        "websites": 1,
        "tasks": 1,
        "targets": 1,
        "posts": 3,
    }
    assert files["credentials.key"] == (source.data_dir / "credentials.key").read_bytes()
    database = archive.parent / "unpacked.sqlite3"
    database.write_bytes(files["seekbell.sqlite3"])
    tables = table_data(database)
    assert tables["administrators"] == [] and tables["login_sessions"] == []
    # VACUUM leaves no freed page that still holds the password hash.
    assert b"scrypt$" not in files["seekbell.sqlite3"]
    assert b"backup_admin" not in files["seekbell.sqlite3"]
    assert archive.stat().st_mode & 0o777 == 0o600


def test_consistent_snapshot_includes_committed_wal_and_has_private_permissions(source, tmp_path):
    with closing(sqlite3.connect(source.database_path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE workspace_preferences SET name='WAL snapshot'")
        writer.commit()
        assert source.database_path.with_name("seekbell.sqlite3-wal").stat().st_size > 0
        path, destination = tmp_path / "wal.tar.gz", tmp_path / "restored"
        backup.create_backup(source, path)
        restore(source, path, destination)
        with closing(sqlite3.connect(destination / "seekbell.sqlite3")) as connection:
            assert connection.execute("SELECT name FROM workspace_preferences").fetchone() == (
                "WAL snapshot",
            )
    assert destination.stat().st_mode & 0o777 == 0o700
    for name in ("credentials.key", "seekbell.sqlite3"):
        assert (destination / name).stat().st_mode & 0o777 == 0o600


def test_restore_signs_in_only_the_chosen_administrator(source, archive, tmp_path):
    destination = tmp_path / "restored"
    restore(source, archive, destination)
    username, encoded = backup.validate_database(destination / "seekbell.sqlite3")
    assert username == "new_admin" and verify_password(NEW_PASSWORD, encoded)
    assert table_data(destination / "seekbell.sqlite3")["login_sessions"] == []
    with pytest.raises(backup.BackupError):
        restore(source, archive, tmp_path / "invalid", administrator=("x", ADMINISTRATOR[1]))
    assert not (tmp_path / "invalid").exists()


def test_inspection_reads_the_database_and_changes_nothing(source, archive, tmp_path):
    before = table_data(source.database_path)
    found = backup.inspect_backup(archive, tmp_path)
    assert found["summary"]["tasks"] == 1 and found["upgrade"] is False
    assert found["kind"] == "manual"
    assert table_data(source.database_path) == before
    assert not list(tmp_path.glob(".seekbell-*"))


def test_manifest_summary_is_not_trusted_by_inspection(source, archive, tmp_path):
    def mutate(manifest, files):
        manifest["summary"]["tasks"] = 99

    rewrite_archive(archive, mutate)
    assert backup.read_manifest(archive)["summary"]["tasks"] == 99
    assert backup.inspect_backup(archive, tmp_path)["summary"]["tasks"] == 1


@pytest.mark.parametrize("damage", ["gzip", "truncated", "append", "legacy", "empty", "garbage"])
def test_damaged_archive_is_rejected_without_publishing(source, archive, tmp_path, damage):
    data = bytearray(archive.read_bytes())
    if damage == "gzip":
        data[len(data) // 2] ^= 0xFF
    elif damage == "truncated":
        del data[-200:]
    elif damage == "append":
        data = bytearray(gzip.compress(gzip.decompress(bytes(data)) + b"x" * 1024))
    elif damage == "legacy":
        data = bytearray(b"SEEKBELL-BACKUP\x01" + bytes(64))
    elif damage == "empty":
        data = bytearray()
    else:
        data = bytearray(b"not a backup at all")
    archive.write_bytes(data)
    with pytest.raises(backup.BackupError) as error:
        restore(source, archive, tmp_path / "restored")
    if damage == "legacy":
        assert "旧版加密备份" in str(error.value)
    assert not (tmp_path / "restored").exists()
    assert not list(tmp_path.glob(".seekbell-*"))


@pytest.mark.parametrize(
    "kind",
    ["order", "extra", "missing", "directory", "symlink", "path", "pax", "oversized"],
)
def test_only_three_plain_members_in_order_are_accepted(source, archive, tmp_path, kind):
    files = members(archive)
    items = list(files.items())
    if kind == "order":
        items = [items[1], items[0], items[2]]
    elif kind == "extra":
        items.append(("notes.txt", b"extra"))
    elif kind == "missing":
        items = items[:2]
    elif kind == "path":
        items[2] = ("../credentials.key", items[2][1])
    elif kind == "oversized":
        items[2] = ("credentials.key", items[2][1] + b"x" * 100)
    if kind in ("directory", "symlink"):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.USTAR_FORMAT) as tar:
            for name, data in items[:2]:
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            info = tarfile.TarInfo("credentials.key")
            if kind == "directory":
                info.type = tarfile.DIRTYPE
            else:
                info.type, info.linkname = tarfile.SYMTYPE, "/etc/passwd"
            tar.addfile(info)
        archive.write_bytes(raw.getvalue())
    elif kind == "pax":
        # Extended headers could make a general tar parser buffer unbounded data.
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz", format=tarfile.PAX_FORMAT) as tar:
            for name, data in items:
                info = tarfile.TarInfo(name)
                info.size, info.pax_headers = len(data), {"comment": "x" * 10}
                tar.addfile(info, io.BytesIO(data))
        archive.write_bytes(raw.getvalue())
    else:
        write_members(archive, items)
    with pytest.raises(backup.BackupError):
        restore(source, archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    assert not (tmp_path / "credentials.key").exists()


@pytest.mark.parametrize(
    "kind", ["format", "revision", "digest", "size", "key", "database_revision", "schema"]
)
def test_incompatible_contents_never_publish(source, archive, tmp_path, kind):
    def mutate(manifest, files):
        if kind == "format":
            manifest["format"] = 1
        elif kind == "revision":
            manifest["database_revision"] = "future"
        elif kind == "digest":
            manifest["files"]["seekbell.sqlite3"]["sha256"] = "0" * 64
        elif kind == "size":
            manifest["files"]["seekbell.sqlite3"]["bytes"] += 1
        elif kind == "key":
            files["credentials.key"] = Fernet.generate_key()
            refresh(manifest, files)
        else:
            path = tmp_path / "change.sqlite3"
            path.write_bytes(files["seekbell.sqlite3"])
            with closing(sqlite3.connect(path)) as connection:
                if kind == "schema":
                    connection.execute("DROP TABLE source_probes")
                else:
                    connection.execute("UPDATE alembic_version SET version_num='future'")
                connection.commit()
            files["seekbell.sqlite3"] = path.read_bytes()
            refresh(manifest, files)

    rewrite_archive(archive, mutate)
    with pytest.raises((backup.BackupError, CredentialError)):
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
    path = tmp_path / "existing.tar.gz"
    path.write_bytes(b"keep")
    with pytest.raises(backup.BackupError):
        backup.create_backup(source, path)
    assert path.read_bytes() == b"keep"
    path.unlink()
    with instance_lock(source.data_dir), pytest.raises(RuntimeError):
        backup.create_backup(source, path)
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
    path = tmp_path / "bad.tar.gz"
    with pytest.raises(CredentialError):
        backup.create_backup(source, path)
    assert not path.exists() and not list(tmp_path.glob(".seekbell-*"))


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
        backup.create_backup(source, tmp_path / "invalid.tar.gz")
    assert not (tmp_path / "invalid.tar.gz").exists()


def test_cli_creates_without_prompts_and_refuses_non_interactive_restore(source, tmp_path):
    environment = {**os.environ, "SEEKBELL_DATA_DIR": str(source.data_dir)}
    created = subprocess.run(
        [
            sys.executable,
            "-m",
            "seekbell.backup",
            "create",
            "--output",
            str(tmp_path / "cli.tar.gz"),
        ],
        text=True,
        capture_output=True,
        env=environment,
    )
    assert created.returncode == 0 and "请像保管密码一样保管" in created.stdout
    assert backup.read_manifest(tmp_path / "cli.tar.gz")["kind"] == "manual"
    restored = subprocess.run(
        [
            sys.executable,
            "-m",
            "seekbell.backup",
            "restore",
            "--archive",
            str(tmp_path / "cli.tar.gz"),
            "--destination",
            str(tmp_path / "restored"),
        ],
        input="secret-in-pipe\n",
        text=True,
        capture_output=True,
        env=environment,
    )
    assert restored.returncode == 1 and "secret-in-pipe" not in restored.stderr
    assert not (tmp_path / "restored").exists()
    help_result = subprocess.run(
        [sys.executable, "-m", "seekbell.backup", "restore", "--help"],
        text=True,
        capture_output=True,
    )
    assert help_result.returncode == 0 and "--password" not in help_result.stdout


def test_interactive_cli_restore_does_not_echo_passwords(source, archive, tmp_path):
    import pty
    import select
    import time

    master, slave = pty.openpty()
    destination = tmp_path / "restored"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "seekbell.backup",
            "restore",
            "--archive",
            str(archive),
            "--destination",
            str(destination),
        ],
        start_new_session=True,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "SEEKBELL_DATA_DIR": str(source.data_dir)},
    )
    os.close(slave)
    output, position = b"", 0
    deadline = time.monotonic() + 30
    answers = [
        ("恢复后的管理员用户名", "new_admin"),
        ("管理员密码（", NEW_PASSWORD),
        ("再次输入管理员密码", NEW_PASSWORD),
    ]
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
        for secret in (ADMIN_PASSWORD, NEW_PASSWORD):
            assert secret.encode() not in output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
    username, encoded = backup.validate_database(destination / "seekbell.sqlite3")
    assert username == "new_admin" and verify_password(NEW_PASSWORD, encoded)


def test_custom_overview_layout_and_selection_survive_restore(source, tmp_path):
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
    path, destination = tmp_path / "overview.tar.gz", tmp_path / "overview-restored"
    backup.create_backup(source, path)
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

    def mutate(manifest, files):
        path = tmp_path / "older.sqlite3"
        path.write_bytes(files["seekbell.sqlite3"])
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("ALTER TABLE alert_settings DROP COLUMN delay_seconds")
            connection.execute("ALTER TABLE login_sessions DROP COLUMN created_at")
            # Before 0022 the policy kept the last-cleanup counts and had no content limit.
            connection.execute("ALTER TABLE retention_policy RENAME TO retention_new")
            connection.execute(
                "CREATE TABLE retention_policy (id INTEGER NOT NULL, days INTEGER NOT NULL, "
                "revision INTEGER NOT NULL, next_run_at FLOAT NOT NULL, last_run_at FLOAT, "
                "last_counts JSON NOT NULL, PRIMARY KEY (id), "
                "CONSTRAINT ck_retention_singleton CHECK (id = 1), "
                "CONSTRAINT ck_retention_days CHECK (days BETWEEN 1 AND 365))"
            )
            connection.execute(
                "INSERT INTO retention_policy SELECT id,days,revision,next_run_at,NULL,'{}' "
                "FROM retention_new"
            )
            connection.execute("DROP TABLE retention_new")
            # 0018 still had the backup operation records that 0020 drops.
            connection.execute(
                "CREATE TABLE backup_records (id VARCHAR(36) PRIMARY KEY, kind VARCHAR(16) "
                "NOT NULL, result VARCHAR(16) NOT NULL, at FLOAT NOT NULL, archive_bytes "
                "INTEGER, application_version VARCHAR(80) NOT NULL, database_revision "
                "VARCHAR(80) NOT NULL)"
            )
            connection.execute("CREATE INDEX ix_backup_records_at ON backup_records (at)")
            connection.execute("DROP TABLE backup_schedule")
            connection.execute("UPDATE alembic_version SET version_num='0018_settings_maintenance'")
            connection.commit()
        files["seekbell.sqlite3"] = path.read_bytes()
        path.unlink()
        manifest["database_revision"] = "0018_settings_maintenance"
        refresh(manifest, files)

    rewrite_archive(archive, mutate)


def test_older_backup_is_inspected_and_upgraded_inside_the_restored_copy(source, archive, tmp_path):
    older_archive(archive, tmp_path)
    assert backup.inspect_backup(archive, tmp_path)["upgrade"] is True
    destination = tmp_path / "restored"
    manifest = restore(source, archive, destination)
    assert manifest["database_revision"] == "0018_settings_maintenance"
    backup.validate_database(destination / "seekbell.sqlite3")
    backup.validate_credentials(destination)
    expected = table_data(source.database_path)
    restored = table_data(destination / "seekbell.sqlite3")
    for name in ("tasks", "notification_targets", "websites", "posts"):
        assert restored[name] == expected[name]
    assert not list(tmp_path.glob(".seekbell-*"))


def test_pause_disables_collection_and_targets_in_the_restored_copy(source, archive, tmp_path):
    destination = tmp_path / "restored"
    restore(source, archive, destination, pause=True)
    with closing(sqlite3.connect(destination / "seekbell.sqlite3")) as connection:
        assert connection.execute("SELECT max(enabled) FROM websites").fetchone() == (0,)
        assert connection.execute("SELECT max(enabled) FROM notification_targets").fetchone() == (
            0,
        )
    with closing(sqlite3.connect(source.database_path)) as connection:
        assert connection.execute("SELECT max(enabled) FROM websites").fetchone() == (1,)
