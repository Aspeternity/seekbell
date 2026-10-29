import hashlib
import hmac
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from seekbell.db.models import LoginSession
from seekbell.db.transactions import write_session
from seekbell.services import authentication as auth
from seekbell.services.display import timezone_name

router = APIRouter(prefix="/api/auth")
COOKIE = "seekbell_session"
PREAUTH = "seekbell_preauth"


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if request.headers.get("sec-fetch-site") == "cross-site" or (
        origin and origin != str(request.base_url).rstrip("/")
    ):
        raise HTTPException(403, "请求来源无效，请从当前站点重试。")


def signed_nonce(request: Request) -> str:
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(request.app.state.csrf_key, nonce.encode(), hashlib.sha256).hexdigest()
    return nonce + "." + signature


def preauth(request: Request):
    check_origin(request)
    cookie = request.cookies.get(PREAUTH, "")
    supplied = request.headers.get("x-csrf-token", "")
    nonce, _, signature = cookie.partition(".")
    expected = hmac.new(request.app.state.csrf_key, nonce.encode(), hashlib.sha256).hexdigest()
    if (
        not supplied
        or not hmac.compare_digest(cookie.encode(), supplied.encode())
        or not hmac.compare_digest(signature.encode(), expected.encode())
    ):
        raise HTTPException(403, "登录页面已过期，请刷新后重试。")
    rate_limit(request)


def rate_limit(request: Request):
    peer = request.client.host if request.client else "unknown"
    if not request.app.state.login_limiter.allow(peer):
        raise HTTPException(429, "尝试过于频繁，请一分钟后重试。", headers={"Retry-After": "60"})


def require_admin(request: Request):
    info = auth.session_info(request.app.state.engine, request.cookies.get(COOKIE, ""))
    if info is None:
        raise HTTPException(401, "会话已过期，请重新登录。")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        check_origin(request)
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(supplied.encode(), info["csrf"].encode()):
            raise HTTPException(403, "安全校验失败，请刷新后重试。")
    return info


def set_cookie(request: Request, response: Response, name: str, token: str, age: int):
    response.set_cookie(
        name,
        token,
        max_age=age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    password: str = Field(min_length=1, max_length=128, repr=False)


class SetupCredentials(Credentials):
    timezone: str = Field(default="UTC", max_length=80)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        return timezone_name(value)

    password: str = Field(min_length=8, max_length=128, repr=False)


@router.get("/status")
def status(request: Request, response: Response):
    info = auth.session_info(request.app.state.engine, request.cookies.get(COOKIE, ""))
    csrf = info["csrf"] if info else signed_nonce(request)
    if info is None:
        set_cookie(request, response, PREAUTH, csrf, 3600)
    return {
        "initialized": auth.initialized(request.app.state.engine),
        "authenticated": info is not None,
        "username": info["username"] if info else "",
        "csrf": csrf,
    }


def session_response(request, response, credentials, tokens):
    token, csrf = tokens
    set_cookie(request, response, COOKIE, token, auth.SESSION_SECONDS)
    response.delete_cookie(PREAUTH, path="/")
    return {
        "initialized": True,
        "authenticated": True,
        "username": credentials.username,
        "csrf": csrf,
    }


@router.post("/setup", dependencies=[Depends(preauth)])
def setup(credentials: SetupCredentials, request: Request, response: Response):
    with request.app.state.login_limiter.hash_lock:
        try:
            tokens = auth.initialize(
                request.app.state.engine,
                credentials.username,
                credentials.password,
                timezone=credentials.timezone,
            )
        except ValueError:
            raise HTTPException(409, "管理员已创建，请登录。") from None
    return session_response(request, response, credentials, tokens)


@router.post("/login", dependencies=[Depends(preauth)])
def login(credentials: Credentials, request: Request, response: Response):
    with request.app.state.login_limiter.hash_lock:
        tokens = auth.login(
            request.app.state.engine,
            credentials.username,
            credentials.password,
            request.cookies.get(COOKIE, ""),
        )
    if tokens is None:
        raise HTTPException(401, "用户名或密码不正确。")
    return session_response(request, response, credentials, tokens)


@router.post("/logout", dependencies=[Depends(require_admin)])
def logout(request: Request, response: Response):
    with write_session(request.app.state.engine) as session:
        session.execute(
            delete(LoginSession).where(
                LoginSession.token_hash == auth.token_hash(request.cookies.get(COOKIE, ""))
            )
        )
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


class AdministratorUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    username: str = Field(pattern=r"^[A-Za-z0-9_-]{3,32}$")
    current_password: str = Field(min_length=1, max_length=128, repr=False)
    new_password: str | None = Field(default=None, min_length=8, max_length=128, repr=False)


@router.put("/administrator", dependencies=[Depends(require_admin), Depends(rate_limit)])
def administrator(values: AdministratorUpdate, request: Request, response: Response):
    with request.app.state.login_limiter.hash_lock:
        try:
            tokens = auth.update_administrator(
                request.app.state.engine,
                request.cookies.get(COOKIE, ""),
                request.headers.get("x-csrf-token", ""),
                values.username,
                values.current_password,
                values.new_password,
            )
        except auth.InvalidSession:
            raise HTTPException(401, "会话已过期，请重新登录。") from None
        except auth.IncorrectPassword:
            raise HTTPException(400, "当前密码不正确。") from None
    return session_response(request, response, values, tokens)


@router.get("/sessions", dependencies=[Depends(require_admin)])
def sessions(request: Request):
    current = auth.token_hash(request.cookies.get(COOKIE, ""))
    with Session(request.app.state.engine) as session:
        row = session.get(LoginSession, current)
        if row is None or row.expires_at <= time.time():
            raise HTTPException(401, "会话已过期，请重新登录。")
        return {
            "expires_at": row.expires_at,
            "other_sessions": session.scalar(
                select(func.count())
                .select_from(LoginSession)
                .where(LoginSession.token_hash != current, LoginSession.expires_at > time.time())
            ),
        }


@router.delete("/sessions/others", dependencies=[Depends(require_admin)])
def revoke_other_sessions(request: Request):
    current = auth.token_hash(request.cookies.get(COOKIE, ""))
    with write_session(request.app.state.engine) as session:
        row = session.get(LoginSession, current)
        supplied = request.headers.get("x-csrf-token", "")
        if (
            row is None
            or row.expires_at <= time.time()
            or not hmac.compare_digest(row.csrf.encode(), supplied.encode())
        ):
            raise HTTPException(401, "会话已过期，请重新登录。")
        removed = session.execute(
            delete(LoginSession).where(LoginSession.token_hash != current)
        ).rowcount
    return {"revoked": removed}
