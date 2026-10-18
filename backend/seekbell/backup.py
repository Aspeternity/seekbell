"""Offline, authenticated full backups. No archive-controlled paths are extracted."""

import argparse
import getpass
import io
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from alembic.script import ScriptDirectory
from argon2.exceptions import VerificationError
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from seekbell.config import Settings
from seekbell.db.models import (
    Administrator,
    BrowserSession,
    ManualDeliveryAttempt,
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
from seekbell.notifiers.configs import validate_config
from seekbell.notifiers.credentials import CredentialVault
from seekbell.services.auth import PASSWORD_HASHER

MAGIC = b"SEEKBELL-BACKUP-1\n"
CHUNK = 1024 * 1024
MAX_DATABASE = 64 * 1024**3
MEMBERS = {"manifest.json": 16384, "credentials.key": 128, "seekbell.sqlite3": MAX_DATABASE}


class BackupError(ValueError):
    pass


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _key(passphrase: str, salt: bytes) -> bytes:
    if not 15 <= len(passphrase) <= 1024:
        raise BackupError("Backup passphrase must contain 15 to 1024 characters")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())


def _encrypt(source: Path, output, passphrase: str) -> None:
    salt, nonce = os.urandom(16), os.urandom(12)
    header = MAGIC + salt + nonce
    encryptor = Cipher(algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    output.write(header)
    with source.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            output.write(encryptor.update(chunk))
    output.write(encryptor.finalize())
    output.write(encryptor.tag)


def _decrypt(source: Path, output: Path, passphrase: str) -> None:
    with source.open("rb") as stream:
        header = stream.read(len(MAGIC) + 28)
        size = os.fstat(stream.fileno()).st_size
        remaining = size - len(header) - 16
        if not header.startswith(MAGIC) or len(header) != len(MAGIC) + 28 or remaining < 0:
            raise BackupError("Invalid backup envelope")
        if remaining > MAX_DATABASE + 1024 * 1024:
            raise BackupError("Backup exceeds the supported size")
        stream.seek(-16, os.SEEK_END)
        tag = stream.read(16)
        stream.seek(len(header))
        salt, nonce = header[len(MAGIC) : -12], header[-12:]
        decryptor = Cipher(
            algorithms.AES(_key(passphrase, salt)), modes.GCM(nonce, tag)
        ).decryptor()
        decryptor.authenticate_additional_data(header)
        with output.open("xb") as destination:
            while remaining:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    raise BackupError("Truncated backup")
                remaining -= len(chunk)
                destination.write(decryptor.update(chunk))
            destination.write(decryptor.finalize())
        # Never parse or install unauthenticated plaintext (including on final-tag failure).


def _revision(path: Path) -> str:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise BackupError("Database integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise BackupError("Database foreign key check failed")
        rows = connection.execute("SELECT version_num FROM alembic_version").fetchall()
        if len(rows) != 1:
            raise BackupError("Invalid database revision")
        revision = rows[0][0]
    known = {
        item.revision for item in ScriptDirectory.from_config(migration_config()).walk_revisions()
    }
    if revision not in known:
        raise BackupError("Unknown or newer database revision; use a compatible image")
    return revision


def _reauthenticate(engine, password: str) -> None:
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        if admin is None:
            raise BackupError("Create the administrator before making a full backup")
        try:
            PASSWORD_HASHER.verify(admin.password_hash, password)
        except VerificationError:
            raise BackupError("Administrator password verification failed") from None


def _validate_credentials(engine, directory: Path) -> None:
    vault = CredentialVault.open(directory)
    with Session(engine) as session:
        for target in session.scalars(select(NotificationTarget)):
            if target.kind != "mock":
                validate_config(
                    target.kind, vault.unseal(target.id, target.kind, target.config_ciphertext)
                )
        for model in (Outbox, TargetTestAttempt, ManualDeliveryAttempt):
            for row in session.scalars(select(model)):
                snapshot = row.target_snapshot
                if "config_ciphertext" in snapshot:
                    validate_config(
                        snapshot["kind"],
                        vault.unseal(
                            snapshot["id"], snapshot["kind"], snapshot["config_ciphertext"]
                        ),
                    )


def create_backup(settings: Settings, output: Path, *, password: str, passphrase: str) -> None:
    directory = settings.data_dir.resolve()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise BackupError("Backup destination already exists")
    with (
        instance_lock(directory),
        tempfile.TemporaryDirectory(prefix=".backup-", dir=directory) as tmp,
    ):
        stage = Path(tmp)
        database = stage / "seekbell.sqlite3"
        if not settings.database_path.is_file() or settings.database_path.is_symlink():
            raise BackupError("Database unavailable")
        # This includes committed WAL pages; copying just the live main file is unsafe.
        with (
            closing(
                sqlite3.connect(settings.database_path.as_uri() + "?mode=ro", uri=True)
            ) as source,
            closing(sqlite3.connect(database)) as destination,
        ):
            source.backup(destination)
        revision = _revision(database)
        # Do not silently migrate a source backup; use its matching application version.
        head = ScriptDirectory.from_config(migration_config()).get_current_head()
        if revision != head:
            raise BackupError("Upgrade with a compatible image before making this backup")
        CredentialVault.open(directory)
        (stage / "credentials.key").write_bytes((directory / "credentials.key").read_bytes())
        (stage / "credentials.key").chmod(0o600)
        engine = create_database_engine(Settings(data_dir=stage))
        try:
            _reauthenticate(engine, password)
            _validate_credentials(engine, stage)
        finally:
            engine.dispose()
        manifest = {
            "format": 1,
            "database_revision": revision,
            "build_revision": settings.build_revision,
            "created_at": datetime.now(UTC).isoformat(),
            "contains_credentials": True,
        }
        archive = stage / "payload.tar"
        with tarfile.open(archive, "w") as bundle:
            content = json.dumps(manifest).encode()
            entry = tarfile.TarInfo("manifest.json")
            entry.size = len(content)
            entry.mode = 0o600
            bundle.addfile(entry, io.BytesIO(content))
            for name in ("seekbell.sqlite3", "credentials.key"):
                if (stage / name).stat().st_size > MEMBERS[name]:
                    raise BackupError("Backup member exceeds supported size")
                bundle.add(stage / name, arcname=name, recursive=False)
        descriptor, temporary = tempfile.mkstemp(prefix=".seekbell-backup-", dir=output.parent)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                _encrypt(archive, stream, passphrase)
                stream.flush()
                os.fsync(stream.fileno())
            # Publish without clobbering a destination created while encryption was running.
            os.link(temporary, output)
            _sync_directory(output.parent)
        finally:
            Path(temporary).unlink(missing_ok=True)


@contextmanager
def _restore_in_progress(directory: Path):
    marker = directory / ".restore-in-progress"
    with marker.open("x") as stream:
        stream.write("Restore is incomplete. Preserve this directory and use a new empty one.\n")
        stream.flush()
        os.fsync(stream.fileno())
    _sync_directory(directory)
    try:
        yield
    except BaseException:
        # Only clear after cleanup left no partially installed data or staging directory.
        if all(item.name in {".instance.lock", marker.name} for item in directory.iterdir()):
            marker.unlink()
            _sync_directory(directory)
        raise
    else:
        marker.unlink()
        _sync_directory(directory)


def restore_backup(settings: Settings, archive: Path, *, password: str, passphrase: str) -> None:
    directory = settings.data_dir.resolve()
    with instance_lock(directory):
        if any(item.name != ".instance.lock" for item in directory.iterdir()):
            raise BackupError(
                "Restore requires an empty data directory; keep the old volume intact"
            )
        with (
            _restore_in_progress(directory),
            tempfile.TemporaryDirectory(prefix=".restore-", dir=directory) as tmp,
        ):
            stage = Path(tmp)
            payload = stage / "payload.tar"
            _decrypt(archive, payload, passphrase)
            seen = set()
            with tarfile.open(payload, "r:") as bundle:
                for entry in bundle:
                    if (
                        entry.name not in MEMBERS
                        or entry.name in seen
                        or not entry.isfile()
                        or not 0 < entry.size <= MEMBERS[entry.name]
                    ):
                        raise BackupError("Invalid backup member")
                    seen.add(entry.name)
                    with (stage / entry.name).open("xb") as stream:
                        shutil.copyfileobj(bundle.extractfile(entry), stream, CHUNK)
                    (stage / entry.name).chmod(0o600)
            if seen != set(MEMBERS):
                raise BackupError("Incomplete backup")
            manifest = json.loads((stage / "manifest.json").read_bytes())
            revision = _revision(stage / "seekbell.sqlite3")
            if (
                manifest.get("format") != 1
                or manifest.get("database_revision") != revision
                or manifest.get("contains_credentials") is not True
            ):
                raise BackupError("Backup manifest does not match the database")
            engine = create_database_engine(Settings(data_dir=stage))
            try:
                _reauthenticate(engine, password)
                # All migrations and credential checks happen only in the private staging area.
                migrate(engine)
                _validate_credentials(engine, stage)
                with engine.begin() as connection:
                    connection.execute(delete(BrowserSession))
                with engine.connect() as connection:
                    connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                engine.dispose()
            _revision(stage / "seekbell.sqlite3")
            # No writer may run until the complete pair is installed and the lock released.
            installed = []
            try:
                for name in ("credentials.key", "seekbell.sqlite3"):
                    path = stage / name
                    with path.open("rb") as stream:
                        os.fsync(stream.fileno())
                    os.replace(path, directory / name)
                    installed.append(directory / name)
                _sync_directory(directory)
            except BaseException:
                for path in installed:
                    path.unlink(missing_ok=True)
                _sync_directory(directory)
                raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SeekBell stopped-service encrypted backup/restore"
    )
    parser.add_argument("action", choices=["create", "restore"])
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    print(
        "Full backup includes administrator, notification credentials and original encryption key."
    )
    print(
        "Stop the service first. Restore only to an empty data directory; old sessions are revoked."
    )
    if not sys.stdin.isatty():
        parser.exit(
            1, "Run maintenance from an interactive terminal; passwords must not be echoed.\n"
        )
    try:
        password = getpass.getpass("Administrator password (from backup when restoring): ")
        passphrase = getpass.getpass("Backup encryption passphrase (15+ characters): ")
        if args.action == "create" and getpass.getpass("Repeat backup passphrase: ") != passphrase:
            raise BackupError("Backup passphrases do not match")
        operation = create_backup if args.action == "create" else restore_backup
        operation(Settings(), args.archive, password=password, passphrase=passphrase)
    except Exception:
        # Do not log paths, SQL parameters, archive contents, passwords or underlying exceptions.
        parser.exit(
            1,
            "Maintenance failed: check passwords, compatible version, stopped service, "
            "empty restore directory, archive integrity and available space.\n",
        )
    print("Backup created." if args.action == "create" else "Restore complete; sign in again.")


if __name__ == "__main__":
    main()
