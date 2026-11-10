"""The server-side backup library: one directory of tar.gz archives is the source of truth."""

import contextlib
import fcntl
import json
import os
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from seekbell import backup

# Ids are file names inside the backup directory; nothing else is ever addressed.
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,150}\.tar\.gz")
PROTECTED_DAYS = 30
# Kinds a restore or an upgrade writes on its own; the newest of each is always kept.
AUTOMATIC_SAFETY = ("pre-restore", "pre-upgrade")
# Directories earlier versions left in the data directory; removed on start.
LEGACY = re.compile(r"web-restore|before-restore-\d{8}T\d{6}Z-[A-Za-z0-9_]{8}")
STALE = re.compile(
    r"\.seekbell-(web|stage|inspect|restore|backup|archive|previous|discard|encrypted)-.+"
)
_manifests = {}
# Names live beside the archives, not in the database a restore replaces.
LABELS = "labels.json"
MAX_LABEL = 40


def directory(settings):
    path = settings.backup_dir
    path.mkdir(mode=0o700, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise backup.BackupError("备份目录不可用。")
    return path


def path_for(settings, name):
    """The archive called `name`, or None: no separators, links or other files."""
    if not isinstance(name, str) or not SAFE_NAME.fullmatch(name):
        return None
    path = settings.backup_dir / name
    try:
        return path if path.is_file() and not path.is_symlink() else None
    except OSError:
        return None


def manifest_of(path):
    """Cached by name, size and modification time; None for an unreadable file."""
    stat = path.stat()
    key = (path.name, stat.st_size, stat.st_mtime_ns)
    if key not in _manifests:
        try:
            _manifests[key] = backup.read_manifest(path)
        except backup.BackupError:
            _manifests[key] = None
    return _manifests[key]


def at_of(manifest, path):
    try:
        return datetime.fromisoformat(manifest["created_at"]).timestamp()
    except (TypeError, KeyError, ValueError):
        return path.stat().st_mtime


def labels(settings):
    """Archive id -> name; a missing or damaged file means no names, never an error."""
    try:
        data = json.loads((settings.backup_dir / LABELS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if isinstance(value, str) and value}


def normalize_label(value):
    label = " ".join((value or "").split())
    if any(unicodedata.category(char).startswith("C") for char in label):
        raise backup.BackupError("名称不能包含控制字符。")
    if len(label) > MAX_LABEL:
        raise backup.BackupError("名称最多 40 个字。")
    return label


def set_label(settings, name, value):
    """Name one archive (empty clears it); names of archives that are gone are dropped."""
    label = normalize_label(value)
    folder = directory(settings)
    current = {key: text for key, text in labels(settings).items() if path_for(settings, key)}
    if label:
        current[name] = label
    else:
        current.pop(name, None)
    handle, temporary = tempfile.mkstemp(prefix=".seekbell-backup-labels-", dir=folder)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(current, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, folder / LABELS)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    backup.sync_directory(folder)
    return label or None


def entries(settings):
    rows = []
    names_by_id = labels(settings)
    try:
        names = [entry.name for entry in os.scandir(directory(settings))]
    except OSError:
        return rows
    for name in names:
        path = path_for(settings, name)
        if path is None:
            continue
        try:
            manifest = manifest_of(path)
            size = path.stat().st_size
        except OSError:
            continue
        rows.append(
            {
                "id": name,
                "name": names_by_id.get(name),
                "valid": manifest is not None,
                "kind": manifest["kind"] if manifest else None,
                "at": at_of(manifest, path),
                "bytes": size,
                "application_version": manifest["application_version"] if manifest else None,
                "database_revision": manifest["database_revision"] if manifest else None,
                "summary": manifest["summary"] if manifest else None,
            }
        )
    return sorted(rows, key=lambda row: (-row["at"], row["id"]))


def usage(settings):
    rows = entries(settings)
    return {"count": len(rows), "bytes": sum(row["bytes"] for row in rows)}


def ensure_space(settings):
    """A snapshot needs room for the copy and its archive; fail early with a clear reason."""
    needed = 2 * settings.database_path.stat().st_size
    if shutil.disk_usage(directory(settings)).free < needed:
        raise backup.BackupError("磁盘可用空间不足，无法生成备份；请先清理空间或删除旧备份。")


def create(settings, kind, *, at=None, label=None, keep=None):
    """Write one archive into the library; the caller owns the backup operation slot.

    `keep` (automatic backups) removes all but that many newest automatic backups, and
    only after the new one is safely written."""
    label = normalize_label(label)  # Reject a bad name before any work.
    ensure_space(settings)
    at = time.time() if at is None else at
    stamp = datetime.fromtimestamp(at, UTC).strftime("%Y%m%dT%H%M%SZ")
    folder = directory(settings)
    name = "seekbell-" + stamp + "-" + kind + ".tar.gz"
    suffix = 2
    while os.path.lexists(folder / name):
        name = "seekbell-" + stamp + "-" + kind + "-" + str(suffix) + ".tar.gz"
        suffix += 1
    manifest = backup.snapshot_backup(settings, folder / name, kind=kind, at=at)
    if label:
        set_label(settings, name, label)
    prune(settings, at=at, keep=keep)
    return name, manifest


def remove(settings, name):
    path = path_for(settings, name)
    if path is None:
        return False
    path.unlink()
    backup.sync_directory(path.parent)
    if name in labels(settings):
        set_label(settings, name, "")
    return True


def prune(settings, *, at=None, keep=None):
    """Safety copies expire after 30 days, except the newest of each kind; automatic
    backups beyond `keep` go when given. Manual backups are never removed."""
    at = time.time() if at is None else at
    cutoff = at - PROTECTED_DAYS * 86400
    newest = set()
    automatic = 0
    for row in entries(settings):
        if row["kind"] == "auto" and keep is not None:
            automatic += 1
            if automatic > keep:
                remove(settings, row["id"])
            continue
        if row["kind"] not in AUTOMATIC_SAFETY:
            continue
        if row["kind"] not in newest:
            newest.add(row["kind"])
            continue
        if row["at"] < cutoff:
            remove(settings, row["id"])


def remove_directory(path):
    """Delete a leftover directory: never follow a link, refuse one an instance holds."""
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return
    lock = path / ".instance.lock"
    if lock.is_file() and not lock.is_symlink():
        with lock.open("rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            fcntl.flock(handle, fcntl.LOCK_UN)
    # Move aside first so a failed removal never leaves a half-deleted copy in place.
    discarded = Path(tempfile.mkdtemp(prefix=".seekbell-discard-", dir=path.parent)) / "copy"
    os.rename(path, discarded)
    shutil.rmtree(discarded.parent)


def remove_leftovers(data_dir):
    """Run on start: earlier restore directories and interrupted temporary files go away."""
    for target in (data_dir, data_dir / "backups"):
        try:
            names = [entry.name for entry in os.scandir(target)]
        except OSError:
            continue
        for name in names:
            path = target / name
            if (target == data_dir and LEGACY.fullmatch(name)) or STALE.fullmatch(name):
                try:
                    remove_directory(path)
                except OSError:
                    continue
