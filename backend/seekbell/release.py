"""Offline candidate preparation. Original data stays on its unchanged, read-only volume."""

import argparse
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy.exc import SQLAlchemyError

from seekbell import backup
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine, instance_lock, migrate, migration_config
from seekbell.notifiers.credentials import CredentialVault

MARKER = "release.json"


@contextmanager
def stopped_source(directory):
    # Open the SAME lock inode as Runtime, without creating or writing anything.
    lock = directory / ".instance.lock"
    if lock.is_symlink() or not lock.is_file():
        raise backup.BackupError("来源缺少实例锁，请先核对已停服的数据目录。")
    with lock.open("rb") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise backup.BackupError("来源服务仍在运行，不能准备切换副本。") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def source_locks(source):
    with ExitStack() as stack:
        if source.name == "web-restore":
            stack.enter_context(stopped_source(source.parent))
            if (source / ".instance.lock").exists():
                stack.enter_context(stopped_source(source))
        else:
            stack.enter_context(stopped_source(source))
        yield


def prepare(settings, destination):
    destination = backup.new_path(destination)
    source = settings.data_dir.resolve(strict=True)
    if destination.is_relative_to(source):
        raise backup.BackupError("候选目录必须位于独立的新数据卷。")
    if settings.database_path.is_symlink() or not settings.database_path.is_file():
        raise backup.BackupError("来源数据库不可用。")
    with (
        source_locks(source),
        tempfile.TemporaryDirectory(prefix=".seekbell-release-", dir=destination.parent) as temp,
    ):
        stage = Path(temp) / "data"
        stage.mkdir(mode=0o700)
        database = stage / "seekbell.sqlite3"
        backup.snapshot_database(settings.database_path, database)
        with closing(backup.readonly(database)) as connection:
            if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
                raise backup.BackupError("来源数据库完整性检查失败。")
            revisions = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        supported = {
            item.revision
            for item in ScriptDirectory.from_config(migration_config()).walk_revisions()
        }
        if len(revisions) != 1 or revisions[0][0] not in supported:
            raise backup.BackupError("来源迁移版本未知，请保留原卷并使用匹配程序核对。")
        source_hash = backup.file_hash(database)
        CredentialVault.open(source)
        with backup.private_file(stage / "credentials.key") as output:
            output.write((source / "credentials.key").read_bytes())
        engine = create_database_engine(Settings(data_dir=stage))
        try:
            migrate(engine)  # Only the NEW candidate is ever migrated.
        finally:
            engine.dispose()
        backup.validate_database(database)
        backup.validate_credentials(stage)
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("DELETE FROM login_sessions")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA journal_mode=DELETE")
        marker = {
            "format": 1,
            "source_revision": revisions[0][0],
            "source_database_sha256": source_hash,
            "source_key_sha256": backup.file_hash(source / "credentials.key"),
            "database_revision": backup.expected_revision(),
            "build_revision": settings.build_revision,
            "database_sha256": backup.file_hash(database),
            "key_sha256": backup.file_hash(stage / "credentials.key"),
        }
        with backup.private_file(stage / MARKER) as output:
            output.write(json.dumps(marker, separators=(",", ":")).encode())
        for name in ("seekbell.sqlite3", "credentials.key", MARKER):
            with (stage / name).open("rb") as stream:
                os.fsync(stream.fileno())
        backup.sync_directory(stage)
        backup.publish_directory(stage, destination)
        return {
            "source_revision": marker["source_revision"],
            "database_revision": marker["database_revision"],
        }


def check(settings):
    directory = settings.data_dir.resolve(strict=True)
    with instance_lock(directory):
        path = directory / MARKER
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
            raise backup.BackupError("候选准备记录不可用。")
        marker = json.loads(path.read_bytes())
        if (
            not isinstance(marker, dict)
            or marker.get("format") != 1
            or marker.get("build_revision") != settings.build_revision
            or marker.get("database_revision") != backup.expected_revision()
            or marker.get("database_sha256") != backup.file_hash(settings.database_path)
            or marker.get("key_sha256") != backup.file_hash(directory / "credentials.key")
        ):
            raise backup.BackupError("候选已改变或镜像不匹配，拒绝切换；请重新准备新卷。")
        # No engine/WAL pragmas: checking must not change the attested snapshot.
        backup.validate_database(settings.database_path)
        return {"prepared": True, "database_revision": marker["database_revision"]}


def check_source(settings, candidate):
    """Refuse a stale candidate if the stopped source changed after preparation."""
    source = settings.data_dir.resolve(strict=True)
    marker = json.loads((candidate / MARKER).read_bytes())
    with (
        source_locks(source),
        tempfile.TemporaryDirectory(
            prefix=".seekbell-source-check-", dir=candidate.parent
        ) as temporary,
    ):
        snapshot = Path(temporary) / "source.sqlite3"
        backup.snapshot_database(settings.database_path, snapshot)
        if (
            backup.file_hash(snapshot) != marker["source_database_sha256"]
            or backup.file_hash(source / "credentials.key") != marker["source_key_sha256"]
        ):
            raise backup.BackupError("来源在准备后发生变化，请重新准备新卷。")


def main():
    parser = argparse.ArgumentParser(description="停服后准备独立升级候选；永不覆盖原卷")
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("prepare")
    create.add_argument("--destination", type=Path, required=True)
    actions.add_parser("check")
    args = parser.parse_args()
    try:
        settings = Settings()
        result = (
            prepare(settings, args.destination) if args.action == "prepare" else check(settings)
        )
        print(json.dumps(result))
    except (ValueError, OSError, RuntimeError, KeyError, sqlite3.Error, SQLAlchemyError):
        print(
            "操作失败：请检查停服状态、数据/密钥、版本及磁盘权限；原卷未被迁移或覆盖。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
