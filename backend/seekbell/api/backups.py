"""Authenticated Web snapshots and isolated restore candidates; never switch live data."""

import asyncio
import hmac
import json
import os
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from seekbell import backup
from seekbell.api.auth import COOKIE, rate_limit, require_admin
from seekbell.db.models import Administrator
from seekbell.db.transactions import database_call
from seekbell.services.authentication import session_info, verify_password

router = APIRouter(prefix="/api/manage/backups", dependencies=[Depends(require_admin)])
MAX_METADATA = 8192
MAX_ARCHIVE = backup.HEADER_SIZE + backup.MAX_PAYLOAD + 16
CANDIDATE = "web-restore"


class CreateValues(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    password: str = Field(min_length=12, max_length=1024, repr=False)


class RestoreValues(CreateValues):
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    admin_password: str = Field(min_length=1, max_length=128, repr=False)


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
        raise HTTPException(422, str(error)) from None
    except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, SQLAlchemyError):
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
            filename="seekbell.sbbackup",
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
            await database_call(
                backup.snapshot_backup, request.app.state.settings, path, password=values.password
            )
            # Keep the single-operation slot until the response has finished or disconnected.
            response = Download(path, temporary, request.app.state.backup_gate)
            lease["transferred"] = True
        except BaseException:
            if temporary is not None:
                temporary.cleanup()
            raise
    return response


async def read_upload(request, archive):
    """One bounded UTF-8 JSON line, then raw encrypted archive bytes (no multipart)."""
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
                    values = RestoreValues.model_validate(json.loads(metadata))
                except (ValueError, ValidationError):
                    raise HTTPException(422, "备份验证字段无效。") from None
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
            await database_call(
                backup.restore_backup,
                request.app.state.settings,
                archive,
                candidate(request),
                password=values.password,
                username=values.username,
                admin_password=values.admin_password,
            )
        return {"candidate_available": True, "activated": False}
