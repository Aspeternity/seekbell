"""Consistent encrypted snapshots, stopped-service CLI and isolated authenticated restore."""

import argparse
import ctypes
import getpass
import hashlib
import hmac
import json
import os
import re
import sqlite3
import struct
import sys
import tempfile
import time
from contextlib import closing
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
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
from seekbell.db.runtime import create_database_engine, instance_lock, migration_config
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.authentication import verify_password

MAGIC = b"SEEKBELL-BACKUP\x01"
HEADER_SIZE = len(MAGIC) + 16 + 12
CHUNK = 1024 * 1024
MAX_DATABASE = 2 * 1024**3
MAX_MANIFEST = 16 * 1024
MAX_PAYLOAD = MAX_DATABASE + MAX_MANIFEST + 48


class BackupError(ValueError):
    pass


def expected_revision():
    return ScriptDirectory.from_config(migration_config()).get_current_head()


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


def validate_database(path):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_DATABASE:
        raise BackupError("数据库文件不可用或超过 2 GiB 限制。")
    with closing(readonly(path)) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise BackupError("数据库完整性检查失败。")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError("数据库关联检查失败。")
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        if revision != [(expected_revision(),)]:
            raise BackupError("备份数据库版本与当前程序不匹配；请使用匹配版本恢复。")
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


def key_for(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise BackupError("备份口令需为 12–1024 个字符。")
    return hashlib.scrypt(
        password.encode(), salt=salt, n=2**17, r=8, p=1, maxmem=256 * 1024**2, dklen=32
    )


def encrypt_file(plain, target, password):
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + salt + nonce
    encryptor = Cipher(algorithms.AES(key_for(password, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    with plain.open("rb") as source, target.open("wb") as output:
        output.write(header)
        while chunk := source.read(CHUNK):
            output.write(encryptor.update(chunk))
        output.write(encryptor.finalize())
        output.write(encryptor.tag)
        output.flush()
        os.fsync(output.fileno())


def decrypt_file(archive, plain, password):
    with archive.open("rb") as source:
        size = os.fstat(source.fileno()).st_size
        if not HEADER_SIZE + 16 < size <= HEADER_SIZE + MAX_PAYLOAD + 16:
            raise BackupError("备份大小无效或超过支持上限。")
        header = source.read(HEADER_SIZE)
        if header[: len(MAGIC)] != MAGIC:
            raise BackupError("不是支持的 SeekBell 加密备份。")
        salt, nonce = header[len(MAGIC) : -12], header[-12:]
        source.seek(-16, os.SEEK_END)
        tag = source.read(16)
        source.seek(HEADER_SIZE)
        decryptor = Cipher(
            algorithms.AES(key_for(password, salt)), modes.GCM(nonce, tag)
        ).decryptor()
        decryptor.authenticate_additional_data(header)
        remaining = size - HEADER_SIZE - 16
        # Unauthenticated bytes stay private and are NEVER parsed before finalize.
        with private_file(plain) as output:
            while remaining:
                chunk = source.read(min(CHUNK, remaining))
                if not chunk:
                    raise BackupError("备份文件不完整。")
                remaining -= len(chunk)
                output.write(decryptor.update(chunk))
            try:
                output.write(decryptor.finalize())
            except InvalidTag:
                raise BackupError("备份口令错误或文件损坏。") from None


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


def create_backup(settings, destination, *, password):
    # Offline callers must still acquire the same exclusive process lock.
    with instance_lock(settings.data_dir.resolve()):
        return snapshot_backup(settings, destination, password=password)


def snapshot_backup(settings, destination, *, password):
    """Consistent snapshot; caller MUST own the application's lifetime instance lock.

    The running single-process app can safely use SQLite's backup API without
    stopping actors. The installation key is immutable for that lifetime; every
    credential is validated against the resulting snapshot, never the live DB.
    """
    destination = new_path(destination)
    directory = settings.data_dir.resolve()
    if settings.database_path.is_symlink() or not settings.database_path.is_file():
        raise BackupError("没有可备份的数据库。")
    with tempfile.TemporaryDirectory(prefix=".seekbell-backup-", dir=destination.parent) as temp:
        stage = Path(temp)
        database = stage / "seekbell.sqlite3"
        snapshot_database(settings.database_path, database)
        validate_database(database)
        key_path = directory / "credentials.key"
        CredentialVault.open(directory)
        key = key_path.read_bytes()
        if len(key) != 44:
            raise BackupError("原凭据密钥格式无效。")
        with private_file(stage / "credentials.key") as output:
            output.write(key)
        validate_credentials(stage)
        manifest = {
            "format": 1,
            "application_version": version("seekbell"),
            "build_revision": settings.build_revision,
            "database_revision": expected_revision(),
            "created_at": datetime.now(UTC).isoformat(),
            "database_bytes": database.stat().st_size,
            "database_sha256": file_hash(database),
        }
        encoded = json.dumps(manifest, separators=(",", ":")).encode()
        payload = stage / "payload"
        with private_file(payload) as output, database.open("rb") as source:
            output.write(struct.pack(">I", len(encoded)))
            output.write(encoded)
            output.write((stage / "credentials.key").read_bytes())
            while chunk := source.read(CHUNK):
                output.write(chunk)
        descriptor, temporary = tempfile.mkstemp(
            prefix=".seekbell-encrypted-", dir=destination.parent
        )
        os.close(descriptor)
        try:
            encrypt_file(payload, Path(temporary), password)
            os.link(temporary, destination)  # Atomic, exclusive publish; never overwrite.
            sync_directory(destination.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return manifest


def unpack_payload(payload, directory):
    with payload.open("rb") as source:
        prefix = source.read(4)
        if len(prefix) != 4 or not 0 < (length := struct.unpack(">I", prefix)[0]) <= MAX_MANIFEST:
            raise BackupError("备份清单无效。")
        manifest = json.loads(source.read(length))
        if (
            not isinstance(manifest, dict)
            or type(manifest.get("format")) is not int
            or manifest["format"] != 1
            or manifest.get("database_revision") != expected_revision()
            or type(manifest.get("database_bytes")) is not int
            or not 0 < manifest["database_bytes"] <= MAX_DATABASE
            or not isinstance(manifest.get("database_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", manifest["database_sha256"])
        ):
            raise BackupError("备份格式或数据库版本不匹配。")
        if payload.stat().st_size != 4 + length + 44 + manifest["database_bytes"]:
            raise BackupError("备份内容长度不匹配。")
        key = source.read(44)
        with private_file(directory / "credentials.key") as output:
            output.write(key)
        database = directory / "seekbell.sqlite3"
        with private_file(database) as output:
            while chunk := source.read(CHUNK):
                output.write(chunk)
        if not hmac.compare_digest(file_hash(database), manifest["database_sha256"]):
            raise BackupError("备份数据库校验失败。")
        return manifest


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


def restore_backup(settings, archive, destination, *, password, username, admin_password):
    destination = new_path(destination)
    if destination == settings.data_dir.resolve():
        raise BackupError("恢复必须使用独立的新数据目录。")
    archive = Path(archive).resolve(strict=True)
    if not archive.is_file():
        raise BackupError("备份必须是普通文件。")
    with tempfile.TemporaryDirectory(prefix=".seekbell-restore-", dir=destination.parent) as temp:
        root = Path(temp)
        payload, restored = root / "payload", root / "data"
        restored.mkdir(mode=0o700)
        decrypt_file(archive, payload, password)
        manifest = unpack_payload(payload, restored)
        actual_name, encoded = validate_database(restored / "seekbell.sqlite3")
        if not hmac.compare_digest(username.encode(), actual_name.encode()) or not verify_password(
            admin_password, encoded
        ):
            raise BackupError("备份中的管理员验证失败。")
        validate_credentials(restored)
        # Revoke old server sessions; keep configuration, ledgers and queues unchanged.
        with closing(sqlite3.connect(restored / "seekbell.sqlite3")) as connection:
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("DELETE FROM login_sessions")
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
    create = sub.add_parser("create", help="先停服；加密数据库和原密钥，不覆盖文件")
    create.add_argument("--output", type=Path, required=True)
    restore = sub.add_parser("restore", help="验证口令/备份管理员，只恢复到不存在的新目录")
    restore.add_argument("--archive", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        if not sys.stdin.isatty() or not sys.stderr.isatty():
            raise BackupError("请在交互终端运行；口令不接受命令行参数、环境变量或管道输入。")
        password = getpass.getpass("备份加密口令（12–1024字符）: ")
        settings = Settings()
        if args.action == "create":
            if password != getpass.getpass("再次输入备份口令: "):
                raise BackupError("两次备份口令不一致。")
            create_backup(settings, args.output, password=password)
            print("加密备份完成（包含数据库与原密钥）。请安全保管备份及独立口令。")
        else:
            username = input("备份中的管理员用户名: ")
            admin_password = getpass.getpass("备份中的管理员密码: ")
            restore_backup(
                settings,
                args.archive,
                args.destination,
                password=password,
                username=username,
                admin_password=admin_password,
            )
            print(
                "独立恢复完成，旧会话已清除。启动前请停止原实例；"
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
            "操作失败：请检查口令、管理员、版本、数据完整性、目标路径权限及服务是否已停止。原数据未被覆盖。",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
