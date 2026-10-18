"""Single administrator and opaque, persisted browser sessions."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerificationError
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from seekbell.db.models import AccountThrottle, Administrator, AuthThrottle, BrowserSession
from seekbell.db.transactions import write_session

PASSWORD_HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
ANONYMOUS_TTL = 30 * 60
AUTHENTICATED_TTL = 7 * 24 * 60 * 60
COOKIE_NAME = "seekbell_session"


class AuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b"seekbell.csrf.v1", hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class Identity:
    digest: str
    administrator_id: int | None
    expires_at: float
    secure: bool


class Authentication:
    def __init__(self, engine: Engine):
        self.engine = engine
        # Wrong usernames still perform the same password verification.
        self._dummy_hash = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))

    def initialized(self) -> bool:
        with Session(self.engine) as session:
            return session.get(Administrator, 1) is not None

    def username(self) -> str:
        with Session(self.engine) as session:
            return session.get(Administrator, 1).username

    def resolve(self, token: str | None, *, secure: bool) -> Identity | None:
        if not token or len(token) != 43:
            return None
        with Session(self.engine) as session:
            row = session.get(BrowserSession, token_digest(token))
            if row is None or row.expires_at <= time.time() or (row.secure and not secure):
                return None
            return Identity(row.digest, row.administrator_id, row.expires_at, row.secure)

    def _issue(self, session: Session, administrator_id: int | None, secure: bool) -> str:
        now = time.time()
        session.execute(delete(BrowserSession).where(BrowserSession.expires_at <= now))
        # Bound anonymous storage and authenticated sessions independently.
        ids = session.scalars(
            select(BrowserSession.digest)
            .where(
                BrowserSession.administrator_id.is_(None)
                if administrator_id is None
                else BrowserSession.administrator_id == administrator_id
            )
            .order_by(BrowserSession.created_at.desc(), BrowserSession.digest)
            .offset(127 if administrator_id is None else 31)
        ).all()
        if ids:
            session.execute(delete(BrowserSession).where(BrowserSession.digest.in_(ids)))
        token = secrets.token_urlsafe(32)
        ttl = ANONYMOUS_TTL if administrator_id is None else AUTHENTICATED_TTL
        session.add(
            BrowserSession(
                digest=token_digest(token),
                administrator_id=administrator_id,
                created_at=now,
                expires_at=now + ttl,
                secure=secure,
            )
        )
        return token

    def anonymous(self, *, secure: bool) -> str:
        with write_session(self.engine) as session:
            return self._issue(session, None, secure)

    def _reserve_attempt(self, model=AuthThrottle) -> None:
        # Persistent global budget also limits distributed guesses and password-hash work.
        now = time.time()
        with write_session(self.engine) as session:
            row = session.get(model, 1)
            if row is None:
                row = model(id=1, window_started=now, attempts=0)
                session.add(row)
            if now - row.window_started >= 60:
                row.window_started, row.attempts = now, 0
            if row.attempts >= 10:
                raise AuthError(429, "尝试过于频繁，请在一分钟后重试。")
            row.attempts += 1

    def setup(self, username: str, password: str, previous: Identity, *, secure: bool) -> str:
        if self.initialized():
            raise AuthError(409, "管理员已创建，请登录。")
        self._reserve_attempt()
        password_hash = PASSWORD_HASHER.hash(password)
        with write_session(self.engine) as session:
            if session.get(Administrator, 1) is not None:
                raise AuthError(409, "管理员已创建，请登录。")
            session.add(Administrator(id=1, username=username, password_hash=password_hash))
            session.flush()
            session.execute(delete(BrowserSession).where(BrowserSession.digest == previous.digest))
            return self._issue(session, 1, secure)

    def login(self, username: str, password: str, previous: Identity, *, secure: bool) -> str:
        self._reserve_attempt()
        with Session(self.engine) as session:
            admin = session.get(Administrator, 1)
            stored_hash = admin.password_hash if admin else self._dummy_hash
            valid_username = admin is not None and hmac.compare_digest(
                admin.username.encode(), username.encode()
            )
        try:
            valid_password = PASSWORD_HASHER.verify(stored_hash, password)
        except VerificationError:
            valid_password = False
        if not valid_username or not valid_password:
            raise AuthError(401, "用户名或密码不正确。")
        with write_session(self.engine) as session:
            current = session.get(Administrator, 1)
            previous_row = session.get(BrowserSession, previous.digest)
            if (
                current is None
                or current.password_hash != stored_hash
                or current.username != username
                or previous_row is None
                or previous_row.expires_at <= time.time()
            ):
                raise AuthError(401, "账号或会话已变化，请刷新后重新登录。")
            session.delete(previous_row)
            return self._issue(session, 1, secure)

    def change_account(
        self, identity: Identity, *, current_password: str, username: str, new_password: str | None
    ) -> None:
        self._reserve_attempt(AccountThrottle)
        with Session(self.engine) as session:
            admin = session.get(Administrator, 1)
            stored_hash = admin.password_hash
            stored_username = admin.username
        try:
            valid = PASSWORD_HASHER.verify(stored_hash, current_password)
        except VerificationError:
            valid = False
        if not valid:
            raise AuthError(403, "当前密码不正确。")
        replacement = (
            PASSWORD_HASHER.hash(new_password) if new_password is not None else stored_hash
        )
        with write_session(self.engine) as session:
            admin = session.get(Administrator, 1)
            current_session = session.get(BrowserSession, identity.digest)
            if (
                admin.password_hash != stored_hash
                or admin.username != stored_username
                or current_session is None
                or current_session.administrator_id != 1
                or current_session.expires_at <= time.time()
            ):
                raise AuthError(409, "账号或会话已变化，请重新登录后再修改。")
            admin.username, admin.password_hash = username, replacement
            session.execute(delete(BrowserSession).where(BrowserSession.administrator_id == 1))

    def logout(self, identity: Identity) -> None:
        with write_session(self.engine) as session:
            session.execute(delete(BrowserSession).where(BrowserSession.digest == identity.digest))
