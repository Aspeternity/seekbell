"""The backup library, ticketed downloads and inspect-then-restore of the live workspace."""

import asyncio
import hashlib
import hmac
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from seekbell import backup
from seekbell.api.auth import COOKIE, preauth, rate_limit, require_admin, session_response
from seekbell.db.models import Administrator
from seekbell.db.transactions import database_call, write_session
from seekbell.services import backups
from seekbell.services.authentication import (
    initialized,
    new_session,
    password_hash,
    session_info,
    verify_password,
)

router = APIRouter(prefix="/api/manage/backups", dependencies=[Depends(require_admin)])
# A fresh installation may restore a backup instead of creating its first administrator.
setup_router = APIRouter(prefix="/api/auth/setup", dependencies=[Depends(preauth)])
DATA_FILES = ("seekbell.sqlite3", "seekbell.sqlite3-wal", "seekbell.sqlite3-shm", "credentials.key")
QUIESCE_SECONDS = 15
UPLOAD_SECONDS = 300
STAGE_SECONDS = 30 * 60
TICKET_SECONDS = 60


class Confirm(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    # Omitted while the session's last password entry is recent (CONFIRM_SECONDS).
    current_password: str | None = Field(default=None, min_length=1, max_length=128, repr=False)


class RestoreValues(Confirm):
    pause: bool = True


class SetupRestoreValues(BaseModel):
    """A fresh installation restores under a newly chosen administrator."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    stage: str = Field(min_length=1, max_length=64)
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    admin_password: str = Field(min_length=8, max_length=128, repr=False)
    pause: bool = True


@dataclass
class Stage:
    """An inspected archive waiting for confirmation: an upload, or a library entry."""

    archive: Path
    expires: float
    setup: bool
    temporary: tempfile.TemporaryDirectory | None = None

    def discard(self):
        if self.temporary is not None:
            self.temporary.cleanup()


def stages(app):
    """Expired stages are dropped whenever stages are touched."""
    table = app.state.backup_stages
    now = time.monotonic()
    for key in [key for key, stage in table.items() if stage.expires < now]:
        table.pop(key).discard()
    return table


def put_stage(app, stage):
    # One administrator, one restore in preparation: a new inspection replaces older ones.
    table = stages(app)
    for key in list(table):
        table.pop(key).discard()
    key = secrets.token_urlsafe(24)
    table[key] = stage
    return key


def take_stage(app, key, *, setup):
    stage = stages(app).get(key)
    if stage is None or stage.setup != setup:
        raise HTTPException(404, "检查结果已过期，请重新选择备份。")
    return stage


def reauthenticate(request, password=None):
    engine = request.app.state.engine
    token = request.cookies.get(COOKIE, "")
    if password is None:
        info = session_info(engine, token)
        if info is None or not hmac.compare_digest(
            info["csrf"].encode(), request.headers.get("x-csrf-token", "").encode()
        ):
            raise HTTPException(401, "会话已过期，请重新登录。")
        if request.app.state.confirmations.remaining(token, info["started_at"]) <= 0:
            raise HTTPException(403, "请输入当前管理员密码。")
        return
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        encoded = admin.password_hash if admin else None
    if encoded is None or not verify_password(password, encoded):
        raise HTTPException(400, "当前管理员密码不正确。")
    # Account edits/logout during hashing must revoke this privileged operation.
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        info = session_info(engine, token)
        if (
            admin is None
            or admin.password_hash != encoded
            or info is None
            or not hmac.compare_digest(
                info["csrf"].encode(), request.headers.get("x-csrf-token", "").encode()
            )
        ):
            raise HTTPException(401, "会话已过期，请重新登录。")
    request.app.state.confirmations.mark(token)


def current_administrator(engine):
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        return admin.username, admin.password_hash


@asynccontextmanager
async def operation(request):
    gate = request.app.state.backup_gate
    if gate.locked():
        raise HTTPException(409, "已有备份或恢复操作，请等待完成后重试。")
    await gate.acquire()
    try:
        yield
    except ClientDisconnect:
        raise HTTPException(400, "备份上传已中断，请重新选择文件重试。") from None
    except backup.BackupError as error:
        raise HTTPException(422, str(error)) from None
    except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, SQLAlchemyError):
        raise HTTPException(
            422, "操作失败，请检查备份、版本、磁盘空间和权限。原数据未被覆盖。"
        ) from None
    finally:
        gate.release()


def library_status(settings):
    rows = backups.entries(settings)
    disk = shutil.disk_usage(backups.directory(settings))
    return {
        "directory": str(settings.backup_dir),
        "free_bytes": disk.free,
        "total_bytes": disk.total,
        "backups": rows,
    }


@router.get("")
async def status(request: Request):
    token = request.cookies.get(COOKIE, "")
    info = await database_call(session_info, request.app.state.engine, token)
    return {
        # Seconds the current password may still be omitted; 0 means it must be entered.
        "confirm_seconds": int(
            request.app.state.confirmations.remaining(token, info["started_at"]) if info else 0
        ),
        "max_upload_bytes": backup.MAX_ARCHIVE,
        **await database_call(library_status, request.app.state.settings),
    }


class NameValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Bounded here; the library trims it and enforces MAX_LABEL characters.
    name: str = Field(default="", max_length=200)


@router.post("", dependencies=[Depends(rate_limit)])
async def create(request: Request, values: NameValues | None = None):
    """Back up now into the library; nothing leaves the server until it is downloaded."""
    async with operation(request):
        name, _ = await database_call(
            backups.create, request.app.state.settings, "manual", label=values and values.name
        )
    return {"id": name}


def existing(request, name):
    path = backups.path_for(request.app.state.settings, name)
    if path is None:
        raise HTTPException(404, "这份备份不存在或已删除。")
    return path


@router.delete("/{name}", dependencies=[Depends(rate_limit)])
async def remove(name: str, request: Request):
    # Signed-in session plus CSRF is enough: the user chose no password for delete (2026-11-10).
    async with operation(request):
        existing(request, name)
        await database_call(backups.remove, request.app.state.settings, name)
    return {"deleted": name}


@router.patch("/{name}")
async def rename(name: str, values: NameValues, request: Request):
    async with operation(request):
        existing(request, name)
        label = await database_call(
            backups.set_label, request.app.state.settings, name, values.name
        )
    return {"id": name, "name": label}


def session_key(request):
    return hashlib.sha256(request.cookies.get(COOKIE, "").encode()).hexdigest()


@router.post("/{name}/ticket", dependencies=[Depends(rate_limit)])
async def ticket(name: str, request: Request):
    """A one-time, short-lived permission for this session to stream one archive."""
    existing(request, name)
    tickets = request.app.state.backup_tickets
    now = time.monotonic()
    for key in [key for key, value in tickets.items() if value[2] < now]:
        tickets.pop(key)
    key = secrets.token_urlsafe(24)
    tickets[key] = (session_key(request), name, now + TICKET_SECONDS)
    return {"url": "/api/manage/backups/" + name + "/file?ticket=" + key}


@router.get("/{name}/file")
async def file(name: str, ticket: str, request: Request):
    entry = request.app.state.backup_tickets.pop(ticket, None)
    if (
        entry is None
        or entry[2] < time.monotonic()
        or entry[1] != name
        or not hmac.compare_digest(entry[0], session_key(request))
    ):
        raise HTTPException(403, "下载链接已失效，请重新点击下载。")
    # Streamed from disk: the browser saves it directly and shows its own progress.
    return FileResponse(
        existing(request, name),
        media_type="application/gzip",
        filename=name,
        headers={"Cache-Control": "no-store"},
    )


async def receive_upload(request, archive):
    """The raw archive as the request body; the size is counted, not trusted."""
    if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
        raise HTTPException(415, "请上传 SeekBell 备份文件。")
    length = request.headers.get("content-length")
    if length and (not length.isdecimal() or int(length) > backup.MAX_ARCHIVE):
        raise HTTPException(413, "备份超过支持上限。")
    size = 0
    try:
        async with asyncio.timeout(UPLOAD_SECONDS):
            with backup.private_file(archive) as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > backup.MAX_ARCHIVE:
                        raise HTTPException(413, "备份超过支持上限。")
                    if chunk:
                        await database_call(output.write, chunk)
    except TimeoutError:
        raise HTTPException(408, "上传超时，请重新选择文件重试。") from None
    if not size:
        raise HTTPException(422, "备份上传不完整。")


def live_summary(settings):
    return backup.summary(settings.database_path)


async def inspection(request, stage, key):
    settings = request.app.state.settings
    found = await database_call(backup.inspect_backup, stage.archive, settings.data_dir.resolve())
    return {
        "stage": key,
        "backup": {
            name: found[name]
            for name in ("kind", "created_at", "application_version", "summary", "upgrade")
        },
        "current": None if stage.setup else await database_call(live_summary, settings),
    }


async def inspect_upload(request, *, setup):
    temporary = tempfile.TemporaryDirectory(
        prefix=".seekbell-stage-", dir=request.app.state.settings.data_dir.resolve()
    )
    try:
        archive = Path(temporary.name) / "upload.tar.gz"
        await receive_upload(request, archive)
        stage = Stage(archive, time.monotonic() + STAGE_SECONDS, setup, temporary)
        result = await inspection(request, stage, "")
    except BaseException:
        temporary.cleanup()
        raise
    result["stage"] = put_stage(request.app, stage)
    return result


@router.post("/inspect", dependencies=[Depends(rate_limit)])
async def inspect_file(request: Request):
    """Check an uploaded archive without changing anything; returns a stage to confirm."""
    async with operation(request):
        return await inspect_upload(request, setup=False)


@router.post("/{name}/inspect")
async def inspect_entry(name: str, request: Request):
    async with operation(request):
        stage = Stage(existing(request, name), time.monotonic() + STAGE_SECONDS, False)
        result = await inspection(request, stage, "")
        result["stage"] = put_stage(request.app, stage)
        return result


@router.delete("/inspect/{key}")
async def cancel(key: str, request: Request):
    stage = stages(request.app).pop(key, None)
    if stage is not None:
        stage.discard()
    return {"cancelled": stage is not None}


def swap_in(data_dir, restored):
    """Move the live files aside, then move the verified copy in."""
    previous = Path(tempfile.mkdtemp(prefix=".seekbell-previous-", dir=data_dir))
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
    # Waiting hotlist reads return at once instead of holding the restore back.
    if getattr(app.state, "hotlists", None) is not None:
        app.state.hotlists.wake()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + QUIESCE_SECONDS
    while app.state.in_flight > 1:
        if loop.time() > deadline:
            app.state.restoring = False
            raise HTTPException(409, "仍有操作在进行，请稍后重试恢复。")
        await asyncio.sleep(0.05)


def sign_in(engine):
    with write_session(engine) as session:
        return new_session(session, at=time.time())


async def apply_restore(request, response, key, stage, values, administrator):
    """Replace the live workspace, keeping `administrator` and signing the caller in.

    Outside first-run setup the current data is first saved as a pre-restore backup,
    so the restore can be undone from the library."""
    app = request.app
    settings = app.state.settings
    data_dir = settings.data_dir.resolve()
    with tempfile.TemporaryDirectory(prefix=".seekbell-web-", dir=data_dir) as temp:
        staged = Path(temp) / "restored"
        await database_call(
            backup.restore_backup,
            settings,
            stage.archive,
            staged,
            administrator=administrator,
            pause=values.pause,
        )
        if not stage.setup:
            await database_call(backups.create, settings, "pre-restore")
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
    await database_call(shutil.rmtree, previous, True)
    stages(app).pop(key, None)
    stage.discard()
    tokens = await database_call(sign_in, app.state.engine)
    return {
        "restored": True,
        "paused": values.pause,
        **session_response(request, response, administrator[0], tokens),
    }


@router.post("/inspect/{key}/restore", dependencies=[Depends(rate_limit)])
async def restore(key: str, values: RestoreValues, request: Request, response: Response):
    async with operation(request):
        stage = take_stage(request.app, key, setup=False)
        await database_call(reauthenticate, request, values.current_password)
        administrator = await database_call(current_administrator, request.app.state.engine)
        return await apply_restore(request, response, key, stage, values, administrator)


async def require_uninitialized(request):
    if await database_call(initialized, request.app.state.engine):
        raise HTTPException(409, "管理员已创建，请登录后在系统设置中恢复。")


@setup_router.post("/inspect", dependencies=[Depends(rate_limit)])
async def setup_inspect(request: Request):
    await require_uninitialized(request)
    async with operation(request):
        return await inspect_upload(request, setup=True)


@setup_router.post("/restore", dependencies=[Depends(rate_limit)])
async def setup_restore(values: SetupRestoreValues, request: Request, response: Response):
    await require_uninitialized(request)
    async with operation(request):
        stage = take_stage(request.app, values.stage, setup=True)
        await require_uninitialized(request)
        # Hash outside the event loop like setup; never stored in plain text.
        encoded = await database_call(password_hash, values.admin_password)
        administrator = (values.username, encoded)
        return await apply_restore(request, response, values.stage, stage, values, administrator)
