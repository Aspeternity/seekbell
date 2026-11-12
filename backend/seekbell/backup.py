"""Consistent tar.gz snapshots without the administrator, offline CLI and isolated restore."""

import argparse
import ctypes
import getpass
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import sqlite3
import sys
import tarfile
import tempfile
import time
import zlib
from contextlib import closing
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from seekbell.config import Settings
from seekbell.db.models import (
    AlertDelivery,
    Base,
    ManualDelivery,
    NotificationTarget,
    Outbox,
    TargetTestAttempt,
)
from seekbell.db.runtime import (
    create_database_engine,
    instance_lock,
    migrate,
    migration_config,
)
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.authentication import password_hash

# The retired encrypted format; only recognised to explain why it is refused.
LEGACY_MAGIC = b"SEEKBELL-BACKUP"
FORMAT = 2
CHUNK = 1024 * 1024
MAX_DATABASE = 2 * 1024**3
MAX_MANIFEST = 16 * 1024
KEY_BYTES = 44
# Exactly these members, in this order; nothing else is ever read from an archive.
MEMBERS = ("manifest.json", "seekbell.sqlite3", "credentials.key")
LIMITS = {
    "manifest.json": MAX_MANIFEST,
    "seekbell.sqlite3": MAX_DATABASE,
    "credentials.key": KEY_BYTES,
}
# Compressed size bound: incompressible data plus tar headers can exceed the raw size a little.
MAX_ARCHIVE = MAX_DATABASE + 64 * 1024**2
KINDS = ("manual", "auto", "pre-restore", "pre-upgrade")


class BackupError(ValueError):
    pass


def expected_revision():
    return ScriptDirectory.from_config(migration_config()).get_current_head()


def known_revisions():
    # Linear history: every known revision is the head or one it upgrades from.
    script = ScriptDirectory.from_config(migration_config())
    return {revision.revision for revision in script.walk_revisions()}


def private_file(path):
    return os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb")


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def new_path(path):
    # Resolve the parent, not a possibly existing destination symlink.
    path = Path(path).absolute()
    path = path.parent.resolve(strict=True) / path.name
    if os.path.lexists(path):
        raise BackupError("目标已存在；请选择新的文件或目录，不能覆盖。")
    return path


def readonly(path):
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA trusted_schema=OFF")
    connection.execute("PRAGMA query_only=ON")
    return connection


def validate_database(path, *, allow_older=False, administrator=True):
    """Integrity, version and (unless `administrator` is False) the single administrator.

    Backups never carry the administrator or sessions; the restoring side supplies one."""
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_DATABASE:
        raise BackupError("数据库文件不可用或超过 2 GiB 限制。")
    with closing(readonly(path)) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise BackupError("数据库完整性检查失败。")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError("数据库关联检查失败。")
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        accepted = known_revisions() if allow_older else {expected_revision()}
        if len(revision) != 1 or revision[0][0] not in accepted:
            raise BackupError("备份数据库版本比当前程序新或无法识别；请先升级 SeekBell。")
        if not administrator:
            return None
        admin = connection.execute(
            "SELECT username,password_hash FROM administrators WHERE id=1"
        ).fetchone()
        if admin is None:
            raise BackupError("尚未创建管理员，不能制作或恢复生产备份。")
        if (
            not isinstance(admin[0], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", admin[0])
            or not isinstance(admin[1], str)
            or not re.fullmatch(r"scrypt\$131072\$8\$1\$[0-9a-f]{32}\$[0-9a-f]{128}", admin[1])
        ):
            raise BackupError("管理员验证数据无效。")
        return admin


def validate_credentials(directory):
    vault = CredentialVault.open(directory)
    engine = create_database_engine(Settings(data_dir=directory))
    try:
        with engine.connect() as connection:
            if compare_metadata(MigrationContext.configure(connection), Base.metadata):
                raise BackupError("数据库结构与当前版本不匹配。")
        with Session(engine) as session:
            for key, kind, ciphertext in session.execute(
                select(
                    NotificationTarget.id,
                    NotificationTarget.kind,
                    NotificationTarget.config_ciphertext,
                ).where(NotificationTarget.config_ciphertext.is_not(None))
            ).yield_per(100):
                vault.unseal(key, kind, ciphertext)
            for model in (Outbox, TargetTestAttempt, ManualDelivery, AlertDelivery):
                for snapshot in session.scalars(select(model.target_snapshot)).yield_per(100):
                    if not isinstance(snapshot, dict):
                        raise BackupError("历史凭据快照格式无效。")
                    if snapshot.get("config_ciphertext"):
                        vault.unseal(
                            snapshot["id"], snapshot["kind"], snapshot["config_ciphertext"]
                        )
    finally:
        engine.dispose()


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def snapshot_database(source_path, database):
    """Copy committed SQLite state including WAL; source is always read-only."""
    with private_file(database):
        pass
    deadline = time.monotonic() + 120

    def progress(status, remaining, total):
        if total * page_size > MAX_DATABASE:
            raise BackupError("数据库超过 2 GiB 限制。")
        if time.monotonic() > deadline:
            raise BackupError("数据库快照超时，请停止其他写入后重试。")

    with (
        closing(readonly(source_path)) as source,
        closing(sqlite3.connect(database)) as snapshot,
    ):
        page_size = source.execute("PRAGMA page_size").fetchone()[0]
        source.backup(snapshot, pages=256, progress=progress)


def summary(path):
    """What a database holds, for the backup list and the restore preview.

    Read-only and tolerant of older schemas: a missing table reads as unknown."""
    queries = {
        "workspace": "SELECT name FROM workspace_preferences WHERE id=1",
        "websites": "SELECT count(*) FROM website_installations",
        "tasks": "SELECT count(*) FROM tasks WHERE deleted_at IS NULL",
        "targets": "SELECT count(*) FROM notification_targets WHERE deleted_at IS NULL",
        "posts": "SELECT count(*) FROM posts",
    }
    result = {}
    with closing(readonly(path)) as connection:
        for name, query in queries.items():
            try:
                row = connection.execute(query).fetchone()
            except sqlite3.Error:
                row = None
            result[name] = row[0] if row else None
    return result


def strip_private(database):
    """Remove the administrator and sessions; VACUUM so no freed page keeps them."""
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute("DELETE FROM login_sessions")
        connection.execute("DELETE FROM administrators")
        connection.commit()
        connection.execute("VACUUM")


def member(name, size, at):
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = size, int(at), 0o600
    return info


def create_backup(settings, destination, *, kind="manual"):
    # Offline callers must still acquire the same exclusive process lock.
    with instance_lock(settings.data_dir.resolve()):
        return snapshot_backup(settings, destination, kind=kind)


def snapshot_backup(settings, destination, *, kind="manual", at=None):
    """Consistent snapshot; caller MUST own the application's lifetime instance lock.

    The running single-process app can safely use SQLite's backup API without
    stopping actors. The installation key is immutable for that lifetime; every
    credential is validated against the resulting snapshot, never the live DB.
    The archive is a plain tar.gz of fixed members, readable with standard tools.

    A pre-restore copy skips validation: a damaged live database must never block the
    restore meant to repair it, and an imperfect copy still beats none.
    """
    strict = kind != "pre-restore"
    if kind not in KINDS:
        raise BackupError("未知的备份类型。")
    destination = new_path(destination)
    directory = settings.data_dir.resolve()
    if settings.database_path.is_symlink() or not settings.database_path.is_file():
        raise BackupError("没有可备份的数据库。")
    with tempfile.TemporaryDirectory(prefix=".seekbell-backup-", dir=destination.parent) as temp:
        stage = Path(temp)
        database = stage / "seekbell.sqlite3"
        snapshot_database(settings.database_path, database)
        if strict:
            validate_database(database)
        key_path = directory / "credentials.key"
        CredentialVault.open(directory)
        key = key_path.read_bytes()
        if len(key) != KEY_BYTES:
            raise BackupError("原凭据密钥格式无效。")
        with private_file(stage / "credentials.key") as output:
            output.write(key)
        if strict:
            validate_credentials(stage)
        strip_private(database)
        at = time.time() if at is None else at
        manifest = {
            "format": FORMAT,
            "kind": kind,
            "application_version": version("seekbell"),
            "build_revision": settings.build_revision,
            "database_revision": expected_revision(),
            "created_at": datetime.fromtimestamp(at, UTC).isoformat(),
            "files": {
                name: {"bytes": (stage / name).stat().st_size, "sha256": file_hash(stage / name)}
                for name in MEMBERS[1:]
            },
            "summary": summary(database),
        }
        encoded = json.dumps(manifest, ensure_ascii=False, separators=(",", ":")).encode()
        descriptor, temporary = tempfile.mkstemp(
            prefix=".seekbell-archive-", dir=destination.parent
        )
        os.close(descriptor)
        try:
            with (
                open(temporary, "wb") as raw,
                tarfile.open(
                    fileobj=raw, mode="w:gz", compresslevel=6, format=tarfile.USTAR_FORMAT
                ) as tar,
            ):
                tar.addfile(member("manifest.json", len(encoded), at), io.BytesIO(encoded))
                for name in MEMBERS[1:]:
                    with (stage / name).open("rb") as source:
                        tar.addfile(member(name, (stage / name).stat().st_size, at), source)
            with open(temporary, "rb") as written:
                os.fsync(written.fileno())
            os.chmod(temporary, 0o600)
            os.link(temporary, destination)  # Atomic, exclusive publish; never overwrite.
            sync_directory(destination.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return manifest


def valid_manifest(manifest):
    files = manifest.get("files") if isinstance(manifest, dict) else None
    return (
        isinstance(manifest, dict)
        and manifest.get("format") == FORMAT
        and manifest.get("kind") in KINDS
        and isinstance(manifest.get("application_version"), str)
        and isinstance(manifest.get("database_revision"), str)
        and isinstance(manifest.get("created_at"), str)
        and isinstance(manifest.get("summary"), dict)
        and isinstance(files, dict)
        and set(files) == set(MEMBERS[1:])
        and all(
            isinstance(entry, dict)
            and type(entry.get("bytes")) is int
            and 0 < entry["bytes"] <= LIMITS[name]
            and isinstance(entry.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            for name, entry in files.items()
        )
    )


def open_archive(archive):
    """A gzip stream; refuses the retired encrypted format with a clear message."""
    archive = Path(archive)
    if archive.is_symlink() or not archive.is_file():
        raise BackupError("备份必须是普通文件。")
    if not 0 < archive.stat().st_size <= MAX_ARCHIVE:
        raise BackupError("备份大小无效或超过支持上限。")
    with archive.open("rb") as probe:
        if probe.read(len(LEGACY_MAGIC)) == LEGACY_MAGIC:
            raise BackupError("这是旧版加密备份，当前版本已不再支持。")
    return gzip.open(archive, "rb")


def read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise BackupError("备份文件不完整。")
    return data


def next_member(stream, name):
    """One plain USTAR header for exactly `name`; returns its size.

    A deliberately tiny reader: extended (PAX/GNU) headers, links and directories are
    refused, so a crafted header can never make the parser buffer unbounded data."""
    block = read_exact(stream, 512)
    stored = block[148:156]
    checksum = sum(block[:148]) + 8 * 32 + sum(block[156:])
    try:
        size = int(block[124:136].rstrip(b"\0 ") or b"x", 8)
        valid = int(stored.rstrip(b"\0 ") or b"x", 8) == checksum
    except ValueError:
        valid = False
    if (
        not valid
        or block[257:263] != b"ustar\0"
        or block[156:157] not in (b"0", b"\0")
        or block[0:100].rstrip(b"\0") != name.encode()
        or block[345:500].strip(b"\0")
        or not 0 < size <= LIMITS[name]
    ):
        raise BackupError("不是有效的 SeekBell 备份文件。")
    return size


def finish_member(stream, size):
    read_exact(stream, -size % 512)


def read_member(stream, name):
    size = next_member(stream, name)
    data = read_exact(stream, size)
    finish_member(stream, size)
    return data


def parse_manifest(data):
    try:
        manifest = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        manifest = None
    if not valid_manifest(manifest):
        raise BackupError("备份清单无效或格式不受支持。")
    return manifest


def read_manifest(archive):
    """Only the leading manifest: cheap enough to list every backup in a directory."""
    try:
        with open_archive(archive) as stream:
            return parse_manifest(read_member(stream, "manifest.json"))
    except BackupError:
        raise
    except (EOFError, zlib.error, gzip.BadGzipFile):
        raise BackupError("不是有效的 SeekBell 备份文件。") from None


def unpack(archive, directory):
    """Extract the fixed members privately, checking sizes and hashes; nothing else is read."""
    try:
        with open_archive(archive) as stream:
            manifest = parse_manifest(read_member(stream, "manifest.json"))
            for name in MEMBERS[1:]:
                size = next_member(stream, name)
                expected = manifest["files"][name]
                if size != expected["bytes"]:
                    raise BackupError("备份内容长度不匹配。")
                digest, remaining = hashlib.sha256(), size
                with private_file(directory / name) as output:
                    while remaining:
                        chunk = read_exact(stream, min(CHUNK, remaining))
                        remaining -= len(chunk)
                        digest.update(chunk)
                        output.write(chunk)
                finish_member(stream, size)
                if not hmac.compare_digest(digest.hexdigest(), expected["sha256"]):
                    raise BackupError("备份文件校验失败，可能已损坏。")
            # Only the end-of-archive marker and record padding (tar pads to 10 KiB) may
            # follow; the read is bounded so trailing data cannot inflate without limit.
            rest = read_exact(stream, 1024) + stream.read(64 * 1024)
            if rest.strip(b"\0") or stream.read(1):
                raise BackupError("不是有效的 SeekBell 备份文件。")
    except BackupError:
        raise
    except (EOFError, zlib.error, gzip.BadGzipFile):
        raise BackupError("不是有效的 SeekBell 备份文件。") from None
    if manifest["database_revision"] not in known_revisions():
        raise BackupError("备份数据库版本比当前程序新或无法识别；请先升级 SeekBell。")
    return manifest


def inspect_backup(archive, workspace):
    """Verify an archive without restoring it; returns its manifest with a fresh summary.

    The summary is read from the verified database, never trusted from the manifest."""
    with tempfile.TemporaryDirectory(prefix=".seekbell-inspect-", dir=workspace) as temp:
        root = Path(temp)
        manifest = unpack(archive, root)
        validate_database(root / "seekbell.sqlite3", allow_older=True, administrator=False)
        CredentialVault.open(root)
        if manifest["database_revision"] == expected_revision():
            validate_credentials(root)
        return {
            **manifest,
            "summary": summary(root / "seekbell.sqlite3"),
            "upgrade": manifest["database_revision"] != expected_revision(),
        }


def publish_directory(source, destination):
    # Linux is the supported runtime; RENAME_NOREPLACE also rejects an empty
    # destination created concurrently. No unsafe replace fallback.
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise BackupError("当前系统不支持安全发布恢复目录。")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1):
        error = ctypes.get_errno()
        raise OSError(error, "Cannot publish restore directory")
    sync_directory(destination.parent)


def pause_activity(database):
    """Stop collection and delivery in a restored copy; queued sends are then cancelled."""
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA trusted_schema=OFF")
        connection.execute("UPDATE websites SET enabled=0")
        connection.execute("UPDATE notification_targets SET enabled=0")
        connection.commit()


def restore_backup(settings, archive, destination, *, administrator, pause=False):
    """Restore into a new directory signed in as `administrator` (username, password_hash).

    Backups carry no administrator; the restoring side always chooses one."""
    destination = new_path(destination)
    if destination == settings.data_dir.resolve():
        raise BackupError("恢复必须使用独立的新数据目录。")
    with tempfile.TemporaryDirectory(prefix=".seekbell-restore-", dir=destination.parent) as temp:
        restored = Path(temp) / "data"
        restored.mkdir(mode=0o700)
        manifest = unpack(archive, restored)
        validate_database(restored / "seekbell.sqlite3", allow_older=True, administrator=False)
        if manifest["database_revision"] != expected_revision():
            # An older backup is upgraded here, inside the private staging copy.
            engine = create_database_engine(Settings(data_dir=restored))
            try:
                migrate(engine)
            except Exception:
                raise BackupError("备份数据无法升级到当前版本。") from None
            finally:
                engine.dispose()
        if pause:
            pause_activity(restored / "seekbell.sqlite3")
        validate_credentials(restored)
        with closing(sqlite3.connect(restored / "seekbell.sqlite3")) as connection:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("DELETE FROM login_sessions")
            connection.execute("DELETE FROM administrators")
            connection.execute(
                "INSERT INTO administrators (id, username, password_hash) VALUES (1, ?, ?)",
                administrator,
            )
            # Restored data counts its automatic backups from now: no immediate catch-up.
            connection.execute(
                "UPDATE backup_schedule SET next_run_at=NULL, since=?, last_attempt_at=NULL, "
                "last_error=NULL",
                (time.time(),),
            )
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("PRAGMA journal_mode=DELETE")
        for name in ("seekbell.sqlite3", "credentials.key"):
            with (restored / name).open("rb") as stream:
                os.fsync(stream.fileno())
        validate_database(restored / "seekbell.sqlite3")
        sync_directory(restored)
        publish_directory(restored, destination)
        return manifest


def main():
    parser = argparse.ArgumentParser(description="SeekBell 停服备份与独立目录恢复（含原凭据密钥）")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create", help="先停服；生成 tar.gz 备份，不覆盖文件")
    create.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore", help="恢复到不存在的新目录，并设置管理员")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        settings = Settings()
        if args.action == "create":
            create_backup(settings, args.output)
            print(
                "备份完成。文件包含通知渠道的凭据（未加密），请像保管密码一样保管，"
                "不要放到公开位置。"
            )
        else:
            if not sys.stdin.isatty() or not sys.stderr.isatty():
                raise BackupError(
                    "请在交互终端运行；管理员密码不接受命令行参数、环境变量或管道输入。"
                )
            username = input("恢复后的管理员用户名: ")
            if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", username):
                raise BackupError("用户名应为 3–32 位字母、数字、下划线或短横线。")
            admin_password = getpass.getpass("管理员密码（8–128字符）: ")
            if not 8 <= len(admin_password) <= 128:
                raise BackupError("管理员密码应为 8–128 个字符。")
            if admin_password != getpass.getpass("再次输入管理员密码: "):
                raise BackupError("两次管理员密码不一致。")
            restore_backup(
                settings,
                args.archive,
                args.destination,
                administrator=(username, password_hash(admin_password)),
            )
            print(
                "独立恢复完成。启动前请停止原实例；"
                "启动后按原启停配置处理待投递任务，备份之后的回执不在此备份内。"
            )
    except BackupError as error:
        # Fixed application messages only; never received configuration/SQL errors.
        print("操作失败：" + str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        sqlite3.Error,
        SQLAlchemyError,
        EOFError,
        KeyboardInterrupt,
    ):
        # No file paths, decrypted values, SQL or exception text in formal output.
        print(
            "操作失败：请检查备份文件、版本、数据完整性、目标路径权限及服务是否已停止。原数据未被覆盖。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
