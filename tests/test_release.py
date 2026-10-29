import importlib.util
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from seekbell import backup, release
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine, instance_lock, migrate
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.authentication import password_hash
from seekbell.services.backup_demo import ADMIN_PASSWORD, PASSWORD, prepare, table_data
from sqlalchemy import event


@pytest.fixture
def source(tmp_path):
    settings = Settings(data_dir=tmp_path / "source", build_revision="a" * 40)
    prepare(settings)
    with instance_lock(settings.data_dir):
        pass
    return settings


def candidate(source, tmp_path):
    destination = tmp_path / "candidate"
    release.prepare(source, destination)
    return Settings(data_dir=destination, build_revision=source.build_revision)


def test_candidate_preserves_all_tables_key_and_revokes_only_copy_sessions(source, tmp_path):
    before = table_data(source.database_path)
    target = candidate(source, tmp_path)
    copied = table_data(target.database_path)
    assert copied.pop("login_sessions") == []
    expected = before.copy()
    expected.pop("login_sessions")
    assert copied == expected
    assert table_data(source.database_path) == before
    assert (target.data_dir / "credentials.key").read_bytes() == (
        source.data_dir / "credentials.key"
    ).read_bytes()
    assert target.data_dir.stat().st_mode & 0o777 == 0o700
    assert (target.data_dir / release.MARKER).stat().st_mode & 0o777 == 0o600
    for _ in range(2):
        assert release.check(target)["prepared"]
        release.check_source(source, target.data_dir)
    assert not list(tmp_path.glob(".seekbell-*"))


def test_running_source_is_rejected_and_existing_candidate_is_preserved(source, tmp_path):
    destination = tmp_path / "candidate"
    with instance_lock(source.data_dir), pytest.raises(backup.BackupError):
        release.prepare(source, destination)
    assert not destination.exists()
    release.prepare(source, destination)
    before = table_data(destination / "seekbell.sqlite3")
    with pytest.raises(backup.BackupError):
        release.prepare(source, destination)
    assert table_data(destination / "seekbell.sqlite3") == before
    with pytest.raises(backup.BackupError):
        release.prepare(source, source.data_dir / "nested")


def test_known_old_schema_is_migrated_only_in_candidate(tmp_path):
    source = Settings(data_dir=tmp_path / "old", build_revision="a" * 40)
    source.data_dir.mkdir(mode=0o700)
    with instance_lock(source.data_dir):
        engine = create_database_engine(source)
        migrate(engine, "0008_retention")
        engine.dispose()
        CredentialVault.open(source.data_dir, create=True)
        with closing(sqlite3.connect(source.database_path)) as connection:
            connection.execute(
                "INSERT INTO administrators(id,username,password_hash) VALUES(1,?,?)",
                ("release_admin", password_hash(ADMIN_PASSWORD)),
            )
            connection.execute("UPDATE workspace_preferences SET name='Old workspace'")
            connection.commit()
    before = table_data(source.database_path)
    destination = tmp_path / "new"
    result = release.prepare(source, destination)
    assert result == {
        "source_revision": "0008_retention",
        "database_revision": "0018_settings_maintenance",
    }
    assert table_data(source.database_path) == before
    with closing(backup.readonly(destination / "seekbell.sqlite3")) as connection:
        assert connection.execute("SELECT name,timezone FROM workspace_preferences").fetchone() == (
            "Old workspace",
            "Asia/Shanghai",
        )
    assert release.check(Settings(data_dir=destination, build_revision=source.build_revision))[
        "prepared"
    ]


def test_migration_failure_never_publishes_candidate_or_writes_original(
    source, tmp_path, monkeypatch
):
    before = table_data(source.database_path)
    real = release.migrate

    def fail(engine):
        def interrupted(connection, cursor, statement, parameters, context, many):
            if "SELECT" in statement.upper():
                raise RuntimeError("Synthetic-private-failure")

        event.listen(engine, "before_cursor_execute", interrupted)
        real(engine)

    monkeypatch.setattr(release, "migrate", fail)
    with pytest.raises(RuntimeError):
        release.prepare(source, tmp_path / "failed")
    assert not (tmp_path / "failed").exists()
    assert table_data(source.database_path) == before
    assert not list(tmp_path.glob(".seekbell-*"))


@pytest.mark.parametrize("damage", ["source", "candidate", "key", "image", "marker"])
def test_changed_source_candidate_key_or_image_refuses_switch(source, tmp_path, damage):
    target = candidate(source, tmp_path)
    if damage in ("source", "candidate"):
        with closing(
            sqlite3.connect((source if damage == "source" else target).database_path)
        ) as connection:
            connection.execute("UPDATE workspace_preferences SET name='Changed after prepare'")
            connection.commit()
    elif damage == "key":
        (target.data_dir / "credentials.key").write_bytes(b"x" * 44)
    elif damage == "image":
        target = target.model_copy(update={"build_revision": "b" * 40})
    else:
        (target.data_dir / release.MARKER).unlink()
    with pytest.raises((backup.BackupError, OSError)):
        if damage == "source":
            release.check_source(source, target.data_dir)
        else:
            release.check(target)


def test_unknown_revision_fails_closed_without_modifying_source(source, tmp_path):
    with closing(sqlite3.connect(source.database_path)) as connection:
        connection.execute("UPDATE alembic_version SET version_num='unknown_revision'")
        connection.commit()
    before = table_data(source.database_path)
    with pytest.raises(backup.BackupError):
        release.prepare(source, tmp_path / "failed")
    assert table_data(source.database_path) == before
    assert not (tmp_path / "failed").exists()


def test_web_restore_candidate_uses_parent_lock_and_preserves_original(source, tmp_path):
    archive = tmp_path / "backup.sbbackup"
    backup.create_backup(source, archive, password=PASSWORD)
    restored = source.data_dir / "web-restore"
    backup.restore_backup(
        source,
        archive,
        restored,
        password=PASSWORD,
        username="backup_admin",
        admin_password=ADMIN_PASSWORD,
    )
    settings = Settings(data_dir=restored, build_revision=source.build_revision)
    with instance_lock(source.data_dir), pytest.raises(backup.BackupError):
        release.prepare(settings, tmp_path / "blocked")
    target = tmp_path / "restored-release"
    release.prepare(settings, target)
    release.check_source(settings, target)
    assert table_data(restored / "seekbell.sqlite3") == table_data(target / "seekbell.sqlite3")


def operator():
    spec = importlib.util.spec_from_file_location(
        "manage_release", Path(__file__).resolve().parents[1] / "scripts/manage_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operator_state_is_private_atomic_and_rejects_overwrite_or_symlink(tmp_path):
    tool = operator()
    path = tmp_path / "state.json"
    state = {"format": 1, "phase": "prepared"}
    tool.save(path, state, new=True)
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(tool.ReleaseError):
        tool.save(path, {"format": 1}, new=True)
    assert tool.load(path) == state
    tool.save(path, {**state, "phase": "active"})
    assert tool.load(path)["phase"] == "active"
    link = tmp_path / "link.json"
    link.symlink_to(path)
    with pytest.raises(tool.ReleaseError):
        tool.save(link, state)
    assert not list(tmp_path.glob(".release-*"))


def test_operator_refuses_running_original_and_unacknowledged_rollback(tmp_path, monkeypatch):
    tool = operator()
    pair = {"image": "fixed", "volume": "original", "data_dir": "/data", "running": True}
    monkeypatch.setattr(tool, "current", lambda project: pair)
    monkeypatch.setattr(tool, "verify", lambda state: None)

    def forbidden(*args, **kwargs):
        pytest.fail("Unsafe operation must not call Docker")

    monkeypatch.setattr(tool, "docker", forbidden)
    with pytest.raises(tool.ReleaseError):
        tool.prepare(tmp_path / "state.json", "test", "new")
    state = {
        "phase": "prepared",
        "project": "test",
        "previous": pair,
        "next": {**pair, "volume": "new"},
    }
    with pytest.raises(tool.ReleaseError):
        tool.switch(tmp_path / "state.json", state)
    with pytest.raises(tool.ReleaseError):
        tool.switch(tmp_path / "state.json", state, rollback=True)


def test_operator_stale_configuration_and_daemon_are_rejected(monkeypatch):
    tool = operator()
    monkeypatch.setattr(tool, "daemon", lambda: "current")
    monkeypatch.setattr(tool, "configuration", lambda: {"compose": "current"})
    with pytest.raises(tool.ReleaseError):
        tool.verify({"daemon": "other", "configuration": {"compose": "current"}})
    with pytest.raises(tool.ReleaseError):
        tool.verify({"daemon": "current", "configuration": {"compose": "old"}})


def test_operator_activation_failure_stops_only_candidate_and_never_starts_original(
    tmp_path, monkeypatch
):
    tool = operator()
    old = {
        "image": "old",
        "volume": "original",
        "data_dir": "/data",
        "running": False,
        "container": "old-id",
        "started_at": "same",
    }
    new = {
        **old,
        "image": "new",
        "volume": "candidate",
        "data_dir": "/data/release",
        "container": "new-id",
        "running": True,
    }
    state = {
        "format": 1,
        "phase": "prepared",
        "project": "test",
        "previous": old,
        "next": new,
        "restored": False,
    }
    path = tmp_path / "state.json"
    tool.save(path, state, new=True)
    observed = iter((old, new))
    monkeypatch.setattr(tool, "current", lambda project: next(observed))
    monkeypatch.setattr(tool, "verify", lambda state: None)
    monkeypatch.setattr(tool, "image", lambda name: name)
    monkeypatch.setattr(tool, "inspect", lambda *args: {})
    monkeypatch.setattr(tool, "unused", lambda *args: None)
    monkeypatch.setattr(tool, "run", lambda *args, **kwargs: None)
    calls = []
    monkeypatch.setattr(tool, "docker", lambda *args, **kwargs: calls.append(args))

    def fail(state, pair):
        assert pair["volume"] == "candidate"
        raise tool.ReleaseError("Synthetic startup failure")

    monkeypatch.setattr(tool, "compose", fail)
    with pytest.raises(tool.ReleaseError):
        tool.switch(path, state)
    assert calls == [("stop", "--time", "30", "new-id")]
    assert tool.load(path)["phase"] == "activation_failed"


def test_readonly_source_materialization_includes_committed_wal_without_changing_original(
    source, tmp_path
):
    with closing(sqlite3.connect(source.database_path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("UPDATE workspace_preferences SET name='Committed WAL release'")
        writer.commit()
        wal = source.database_path.with_name("seekbell.sqlite3-wal")
        assert wal.stat().st_size > 0
        database_before, wal_before = source.database_path.read_bytes(), wal.read_bytes()
        target = candidate(source, tmp_path)
        release.check_source(source, target.data_dir)
        with closing(backup.readonly(target.database_path)) as connection:
            assert connection.execute("SELECT name FROM workspace_preferences").fetchone() == (
                "Committed WAL release",
            )
        assert source.database_path.read_bytes() == database_before
        assert wal.read_bytes() == wal_before


def test_symlink_wal_is_rejected_without_publishing(source, tmp_path):
    # A stopped source with a forged WAL must not read outside the data volume.
    wal = source.database_path.with_name("seekbell.sqlite3-wal")
    wal.unlink(missing_ok=True)
    (tmp_path / "private").write_text("Synthetic-private-not-a-WAL")
    wal.symlink_to(tmp_path / "private")
    with pytest.raises(backup.BackupError):
        release.prepare(source, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()
    assert (tmp_path / "private").read_text() == "Synthetic-private-not-a-WAL"
