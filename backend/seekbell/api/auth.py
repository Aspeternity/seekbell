import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from seekbell.services.auth import (
    ANONYMOUS_TTL,
    AUTHENTICATED_TTL,
    COOKIE_NAME,
    Authentication,
    AuthError,
    Identity,
    csrf_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=6, max_length=128)

    @field_validator("username")
    @classmethod
    def clean_username(cls, value: str) -> str:
        value = value.strip()
        if not value or not value.isprintable():
            raise ValueError("Invalid username")
        return value


class AuthState(BaseModel):
    initialized: bool
    authenticated: bool
    username: str | None
    csrf_token: str


def authentication(request: Request) -> Authentication:
    return request.app.state.authentication


def current_identity(request: Request) -> Identity:
    identity = authentication(request).resolve(
        request.cookies.get(COOKIE_NAME), secure=request.url.scheme == "https"
    )
    if identity is None:
        raise AuthError(401, "会话已过期，请刷新后重新登录。")
    return identity


def require_csrf(
    request: Request, identity: Annotated[Identity, Depends(current_identity)]
) -> Identity:
    origin = request.headers.get("origin")
    expected_origin = f"{request.url.scheme}://{request.url.netloc}"
    if (origin is not None and origin != expected_origin) or request.headers.get(
        "sec-fetch-site"
    ) == "cross-site":
        raise AuthError(403, "请求来源校验失败，请刷新后重试。")
    provided = request.headers.get("x-csrf-token", "")
    expected = csrf_token(request.cookies[COOKIE_NAME])
    if len(provided) != len(expected) or not hmac.compare_digest(
        provided.encode(), expected.encode()
    ):
        raise AuthError(403, "安全校验失败，请刷新后重试。")
    return identity


def require_administrator(
    request: Request, identity: Annotated[Identity, Depends(current_identity)]
) -> Identity:
    if identity.administrator_id is None:
        raise AuthError(401, "请先登录。")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_csrf(request, identity)
    return identity


def set_session(response: Response, token: str, *, secure: bool, authenticated: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
        max_age=AUTHENTICATED_TTL if authenticated else ANONYMOUS_TTL,
    )


def state_for(auth: Authentication, token: str, authenticated: bool) -> AuthState:
    return AuthState(
        initialized=auth.initialized(),
        authenticated=authenticated,
        username=auth.username() if authenticated else None,
        csrf_token=csrf_token(token),
    )


@router.get("/state", response_model=AuthState)
def state(request: Request, response: Response) -> AuthState:
    auth = authentication(request)
    secure = request.url.scheme == "https"
    token = request.cookies.get(COOKIE_NAME)
    identity = auth.resolve(token, secure=secure)
    if identity is None:
        token = auth.anonymous(secure=secure)
        set_session(response, token, secure=secure, authenticated=False)
    return state_for(auth, token, identity is not None and identity.administrator_id is not None)


@router.post("/setup", response_model=AuthState, status_code=201)
def setup(
    credentials: Credentials,
    request: Request,
    response: Response,
    identity: Annotated[Identity, Depends(require_csrf)],
) -> AuthState:
    secure = request.url.scheme == "https"
    auth = authentication(request)
    token = auth.setup(
        credentials.username, credentials.password.get_secret_value(), identity, secure=secure
    )
    set_session(response, token, secure=secure, authenticated=True)
    return state_for(auth, token, True)


@router.post("/login", response_model=AuthState)
def login(
    credentials: Credentials,
    request: Request,
    response: Response,
    identity: Annotated[Identity, Depends(require_csrf)],
) -> AuthState:
    secure = request.url.scheme == "https"
    auth = authentication(request)
    token = auth.login(
        credentials.username, credentials.password.get_secret_value(), identity, secure=secure
    )
    set_session(response, token, secure=secure, authenticated=True)
    return state_for(auth, token, True)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    identity: Annotated[Identity, Depends(require_administrator)],
) -> None:
    authentication(request).logout(identity)
    response.delete_cookie(
        COOKIE_NAME, httponly=True, secure=request.url.scheme == "https", samesite="strict"
    )
