"""Authenticated Web snapshots and isolated restore candidates; never switch live data."""

import asyncio
import fcntl
import hmac
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from seekbell import backup
from seekbell.api.auth import COOKIE, preauth, rate_limit, require_admin
from seekbell.db.models import Administrator
from seekbell.db.transactions import database_call
from seekbell.services.authentication import initialized, session_info, verify_password
from seekbell.services.maintenance import backup_records, record_backup

router = APIRouter(prefix="/api/manage/backups", dependencies=[Depends(require_admin)])
# A fresh installation may restore a backup instead of creating its first administrator.
setup_router = APIRouter(prefix="/api/auth/setup", dependencies=[Depends(preauth)])
MAX_METADATA = 8192
MAX_ARCHIVE = backup.HEADER_SIZE + backup.MAX_PAYLOAD + 16
CANDIDATE = "web-restore"
DATA_FILES = ("seekbell.sqlite3", "seekbell.sqlite3-wal", "seekbell.sqlite3-shm", "credentials.key")
QUIESCE_SECONDS = 15


class CreateValues(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    password: str = Field(min_length=12, max_length=1024, repr=False)


class DiscardValues(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    current_password: str = Field(min_length=1, max_length=128, repr=False)


class RestoreValues(CreateValues):
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    admin_password: str = Field(min_length=1, max_length=128, repr=False)


class ApplyValues(RestoreValues):
    pause: bool = True


class SetupRestoreValues(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    password: str = Field(min_length=12, max_length=1024, repr=False)
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    admin_password: str = Field(min_length=1, max_length=128, repr=False)
    pause: bool = True


def candidate(request):
    return request.app.state.settings.data_dir.resolve() / CANDIDATE


def reauthenticate(request, password):
    engine = request.app.state.engine
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        encoded = admin.password_hash if admin else None
    if encoded is None or not verify_password(password, encoded):
        raise HTTPException(400, "当前管理员密码不正确。")
    # Account edits/logout during hashing must revoke this privileged operation.
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        info = session_info(engine, request.cookies.get(COOKIE, ""))
        if (
            admin is None
            or admin.password_hash != encoded
            or info is None
            or not hmac.compare_digest(
                info["csrf"].encode(), request.headers.get("x-csrf-token", "").encode()
            )
        ):
            raise HTTPException(401, "会话已过期，请重新登录。")
    request.state.backup_authenticated = True


def record_failure(request):
    if getattr(request.state, "backup_authenticated", False):
        # Keep the fixed original failure response if receipt storage also fails.
        with suppress(SQLAlchemyError):
            kind = {"restore": "restore", "apply": "restore", "candidate": "discard"}
            record_backup(
                request.app.state.engine,
                kind.get(request.url.path.rsplit("/", 1)[-1], "export"),
                "failed",
            )


@asynccontextmanager
async def operation(request):
    gate = request.app.state.backup_gate
    if gate.locked():
        raise HTTPException(409, "已有备份或恢复操作，请等待完成后重试。")
    await gate.acquire()
    lease = {"transferred": False}
    try:
        yield lease
    except ClientDisconnect:
        raise HTTPException(400, "备份上传已中断，请重新选择文件重试。") from None
    except backup.BackupError as error:
        await database_call(record_failure, request)
        raise HTTPException(422, str(error)) from None
    except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, SQLAlchemyError):
        await database_call(record_failure, request)
        raise HTTPException(
            422, "操作失败，请检查备份、版本、磁盘空间和权限。原数据未被覆盖。"
        ) from None
    finally:
        if not lease["transferred"]:
            gate.release()


class Download(FileResponse):
    def __init__(self, path, temporary, gate):
        super().__init__(
            path,
            media_type="application/octet-stream",
            filename="seekbell-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + ".sbbackup",
            headers={"Cache-Control": "no-store"},
        )
        self.temporary, self.gate = temporary, gate

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                self.temporary.cleanup()
            finally:
                self.gate.release()


@router.get("")
def status(request: Request):
    return {
        "candidate_available": os.path.lexists(candidate(request)),
        "max_archive_bytes": MAX_ARCHIVE,
        "records": backup_records(request.app.state.engine),
    }


@router.post("/download", dependencies=[Depends(rate_limit)])
async def download(values: CreateValues, request: Request):
    temporary = None
    async with operation(request) as lease:
        await database_call(reauthenticate, request, values.current_password)
        try:
            temporary = tempfile.TemporaryDirectory(
                prefix=".seekbell-web-", dir=request.app.state.settings.data_dir.resolve()
            )
            path = Path(temporary.name) / "download.sbbackup"
            manifest = await database_call(
                backup.snapshot_backup, request.app.state.settings, path, password=values.password
            )
            await database_call(
                record_backup,
                request.app.state.engine,
                "export",
                "generated",
                archive_bytes=path.stat().st_size,
                manifest=manifest,
            )
            # Keep the single-operation slot until the response has finished or disconnected.
            response = Download(path, temporary, request.app.state.backup_gate)
            lease["transferred"] = True
        except BaseException:
            if temporary is not None:
                temporary.cleanup()
            raise
    return response


async def read_upload(request, archive, model=None, check=None):
    """One bounded UTF-8 JSON line, then raw encrypted archive bytes (no multipart)."""
    model = model or RestoreValues
    if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
        raise HTTPException(415, "请上传 SeekBell 加密备份。")
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > MAX_ARCHIVE + MAX_METADATA + 1):
        raise HTTPException(413, "备份超过支持上限。")
    metadata, values, size = bytearray(), None, 0
    with backup.private_file(archive) as output:
        async for chunk in request.stream():
            if values is None:
                prefix, separator, remainder = chunk.partition(b"\n")
                metadata.extend(prefix)
                if len(metadata) > MAX_METADATA:
                    raise HTTPException(413, "备份验证信息过长。")
                if not separator:
                    continue
                try:
                    values = model.model_validate(json.loads(metadata))
                except (ValueError, ValidationError):
                    raise HTTPException(422, "备份验证字段无效。") from None
                if check:
                    await check(values)
                else:
                    await database_call(reauthenticate, request, values.current_password)
                chunk = remainder
            size += len(chunk)
            if size > MAX_ARCHIVE:
                raise HTTPException(413, "备份超过支持上限。")
            if chunk:
                await database_call(output.write, chunk)
    if values is None or not size:
        raise HTTPException(422, "备份上传不完整。")
    return values


@router.post("/restore", dependencies=[Depends(rate_limit)])
async def restore(request: Request):
    async with operation(request):
        if os.path.lexists(candidate(request)):
            raise HTTPException(409, "已有独立恢复副本，请先按维护说明处理；不能覆盖。")
        with tempfile.TemporaryDirectory(
            prefix=".seekbell-web-", dir=request.app.state.settings.data_dir.resolve()
        ) as temp:
            archive = Path(temp) / "upload.sbbackup"
            try:
                async with asyncio.timeout(300):
                    values = await read_upload(request, archive)
            except TimeoutError:
                raise HTTPException(408, "上传超时，请重新选择文件重试。") from None
            manifest = await database_call(
                backup.restore_backup,
                request.app.state.settings,
                archive,
                candidate(request),
                password=values.password,
                username=values.username,
                admin_password=values.admin_password,
            )
            await database_call(
                record_backup,
                request.app.state.engine,
                "restore",
                "verified",
                archive_bytes=archive.stat().st_size,
                manifest=manifest,
            )
        return {"candidate_available": True, "activated": False}


def remove_candidate(path):
    """Delete only the fixed candidate: never follow a link, refuse one an instance holds."""
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return
    lock = path / ".instance.lock"
    if lock.is_file() and not lock.is_symlink():
        with lock.open("rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise backup.BackupError("恢复副本正在被其他实例使用，不能删除。") from None
            fcntl.flock(handle, fcntl.LOCK_UN)
    # Move aside first so a failed removal never leaves a half-deleted candidate in place.
    discarded = Path(tempfile.mkdtemp(prefix=".seekbell-discard-", dir=path.parent)) / "copy"
    os.rename(path, discarded)
    shutil.rmtree(discarded.parent)


@router.delete("/candidate", dependencies=[Depends(rate_limit)])
async def discard(values: DiscardValues, request: Request):
    async with operation(request):
        await database_call(reauthenticate, request, values.current_password)
        path = candidate(request)
        if not os.path.lexists(path):
            raise HTTPException(404, "没有可删除的恢复副本。")
        await database_call(remove_candidate, path)
        await database_call(record_backup, request.app.state.engine, "discard", "deleted")
    return {"candidate_available": False}


def swap_in(data_dir, restored):
    """Keep the replaced workspace beside the data, then move the verified copy in."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    previous = Path(tempfile.mkdtemp(prefix="before-restore-" + stamp + "-", dir=data_dir))
    moved, placed = [], []
    try:
        for name in DATA_FILES:
            if os.path.lexists(data_dir / name):
                os.rename(data_dir / name, previous / name)
                moved.append(name)
        for name in ("seekbell.sqlite3", "credentials.key"):
            os.rename(restored / name, data_dir / name)
            placed.append(name)
    except BaseException:
        # Undo exactly the completed steps; nothing that was not moved is touched.
        for name in placed:
            os.rename(data_dir / name, restored / name)
        for name in moved:
            os.rename(previous / name, data_dir / name)
        previous.rmdir()
        raise
    backup.sync_directory(previous)
    backup.sync_directory(data_dir)
    return previous


def swap_back(data_dir, previous):
    for name in DATA_FILES:
        if os.path.lexists(data_dir / name):
            (data_dir / name).unlink()
    for name in DATA_FILES:
        if os.path.lexists(previous / name):
            os.rename(previous / name, data_dir / name)
    previous.rmdir()
    backup.sync_directory(data_dir)


async def quiesce(app):
    """Refuse new requests and wait for others; only the restore request stays in flight."""
    app.state.restoring = True
    loop = asyncio.get_running_loop()
    deadline = loop.time() + QUIESCE_SECONDS
    while app.state.in_flight > 1:
        if loop.time() > deadline:
            app.state.restoring = False
            raise HTTPException(409, "仍有操作在进行，请稍后重试恢复。")
        await asyncio.sleep(0.05)


async def apply_restore(request, values, archive):
    app = request.app
    settings = app.state.settings
    data_dir = settings.data_dir.resolve()
    with tempfile.TemporaryDirectory(prefix=".seekbell-web-", dir=data_dir) as temp:
        staged = Path(temp) / "restored"
        manifest = await database_call(
            backup.restore_backup,
            settings,
            archive,
            staged,
            password=values.password,
            username=values.username,
            admin_password=values.admin_password,
            pause=values.pause,
        )
        await quiesce(app)
        try:
            await app.state.close_workspace(app)
            try:
                previous = await database_call(swap_in, data_dir, staged)
            except BaseException:
                await app.state.open_workspace(app)
                raise
            try:
                await app.state.open_workspace(app)
            except Exception:
                await database_call(swap_back, data_dir, previous)
                await app.state.open_workspace(app)
                raise backup.BackupError("恢复的数据无法启动，已回到原数据。") from None
        finally:
            app.state.restoring = False
    await database_call(
        record_backup,
        app.state.engine,
        "restore",
        "restored",
        archive_bytes=archive.stat().st_size,
        manifest=manifest,
    )
    return {"restored": True, "paused": values.pause, "previous": previous.name}


@router.post("/apply", dependencies=[Depends(rate_limit)])
async def apply(request: Request):
    async with operation(request):
        with tempfile.TemporaryDirectory(
            prefix=".seekbell-web-", dir=request.app.state.settings.data_dir.resolve()
        ) as temp:
            archive = Path(temp) / "upload.sbbackup"
            try:
                async with asyncio.timeout(300):
                    values = await read_upload(request, archive, ApplyValues)
            except TimeoutError:
                raise HTTPException(408, "上传超时，请重新选择文件重试。") from None
            return await apply_restore(request, values, archive)


async def require_uninitialized(request):
    if await database_call(initialized, request.app.state.engine):
        raise HTTPException(409, "管理员已创建，请登录后在系统设置中恢复。")


@setup_router.post("/restore")
async def setup_restore(request: Request):
    await require_uninitialized(request)
    async with operation(request):
        with tempfile.TemporaryDirectory(
            prefix=".seekbell-web-", dir=request.app.state.settings.data_dir.resolve()
        ) as temp:
            archive = Path(temp) / "upload.sbbackup"

            async def check(values):
                await require_uninitialized(request)

            try:
                async with asyncio.timeout(300):
                    values = await read_upload(request, archive, SetupRestoreValues, check)
            except TimeoutError:
                raise HTTPException(408, "上传超时，请重新选择文件重试。") from None
            await require_uninitialized(request)
            return await apply_restore(request, values, archive)
