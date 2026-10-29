"""Single administrator and opaque, revocable server sessions."""

import hashlib
import hmac
import secrets
import threading
import time
from collections import deque

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from seekbell.db.models import Administrator, LoginSession
from seekbell.db.transactions import write_session

SESSION_SECONDS = 12 * 60 * 60
# Backup operations skip the password prompt this long after it was last entered.
CONFIRM_SECONDS = 15 * 60


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    key = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=2**17, r=8, p=1, maxmem=256 * 1024**2
    )
    return "scrypt$131072$8$1$" + salt + "$" + key.hex()


def verify_password(password: str, encoded: str) -> bool:
    return hmac.compare_digest(password_hash(password, encoded.split("$")[4]), encoded)


class LoginLimiter:
    """Bounded process-local limit; SeekBell supports one service process."""

    def __init__(self):
        self.attempts = {}
        self.lock = threading.Lock()
        self.hash_lock = threading.Lock()

    def allow(self, peer: str) -> bool:
        now = time.monotonic()
        with self.lock:
            for key in list(self.attempts):
                if not self.attempts[key] or self.attempts[key][-1] <= now - 60:
                    del self.attempts[key]
            for key, limit in (("*", 30), (peer, 10)):
                queue = self.attempts.get(key, deque())
                while queue and queue[0] <= now - 60:
                    queue.popleft()
                self.attempts[key] = queue
                if len(queue) >= limit:
                    return False
            self.attempts["*"].append(now)
            self.attempts[peer].append(now)
            return True


class Confirmations:
    """Process-local recent password confirmations per session; a restart only asks again."""

    def __init__(self):
        self.at = {}
        self.lock = threading.Lock()

    def mark(self, token: str):
        now = time.time()
        with self.lock:
            for key in [key for key, at in self.at.items() if at <= now - CONFIRM_SECONDS]:
                del self.at[key]
            self.at[token_hash(token)] = now

    def remaining(self, token: str, expires_at: float) -> float:
        # Signing in (or changing the account) entered the password when the session began.
        started = expires_at - SESSION_SECONDS
        with self.lock:
            last = max(started, self.at.get(token_hash(token), 0))
        return max(0.0, last + CONFIRM_SECONDS - time.time())


def new_session(session, *, at: float) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    session.execute(delete(LoginSession).where(LoginSession.expires_at <= at))
    session.add(
        LoginSession(token_hash=token_hash(token), csrf=csrf, expires_at=at + SESSION_SECONDS)
    )
    return token, csrf


def initialize(engine, username: str, password: str, *, timezone: str = "UTC") -> tuple[str, str]:
    from seekbell.db.models import WorkspacePreferences
    from seekbell.services.display import timezone_name

    timezone_name(timezone)
    encoded = password_hash(password)
    with write_session(engine) as session:
        if session.get(Administrator, 1):
            raise ValueError("管理员已创建，请登录。")
        session.add(Administrator(id=1, username=username, password_hash=encoded))
        session.get(WorkspacePreferences, 1).timezone = timezone
        return new_session(session, at=time.time())


def login(engine, username: str, password: str, previous: str = "") -> tuple[str, str] | None:
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        if admin:
            valid = verify_password(password, admin.password_hash)
        else:
            password_hash(password)
            valid = False
        valid = (
            valid
            and admin is not None
            and hmac.compare_digest(username.encode(), admin.username.encode())
        )
    if not valid:
        return None
    expected = (admin.username, admin.password_hash)
    with write_session(engine) as session:
        current = session.get(Administrator, 1)
        # Re-check after hashing: an administrator change may have committed
        # while this login was verifying the old credentials.
        if current is None or (current.username, current.password_hash) != expected:
            return None
        if previous:
            session.execute(
                delete(LoginSession).where(LoginSession.token_hash == token_hash(previous))
            )
        return new_session(session, at=time.time())


def session_info(engine, token: str):
    with Session(engine) as session:
        record = session.get(LoginSession, token_hash(token)) if token else None
        admin = session.get(Administrator, 1)
        if record is None or record.expires_at <= time.time() or admin is None:
            return None
        return {"username": admin.username, "csrf": record.csrf, "expires_at": record.expires_at}


def initialized(engine) -> bool:
    with Session(engine) as session:
        return session.scalar(select(Administrator.id)) is not None


class InvalidSession(PermissionError):
    pass


class IncorrectPassword(ValueError):
    pass


def update_administrator(engine, token, csrf, username, current_password, new_password=None):
    with Session(engine) as session:
        admin = session.get(Administrator, 1)
        record = session.get(LoginSession, token_hash(token)) if token else None
        if record is None or record.expires_at <= time.time() or admin is None:
            raise InvalidSession
        expected = admin.password_hash
        if not verify_password(current_password, expected):
            raise IncorrectPassword
        if username == admin.username and new_password is None:
            raise ValueError("No changes")
    # A fresh salt even for username-only changes prevents stale login checks
    # from succeeding after a rename away and back. Do expensive work outside
    # the SQLite write lock.
    encoded = password_hash(new_password if new_password is not None else current_password)
    with write_session(engine) as session:
        admin = session.get(Administrator, 1)
        record = session.get(LoginSession, token_hash(token))
        if (
            record is None
            or record.expires_at <= time.time()
            or not hmac.compare_digest(record.csrf.encode(), csrf.encode())
            or admin is None
            or admin.password_hash != expected
        ):
            raise InvalidSession
        admin.username = username
        admin.password_hash = encoded
        session.execute(delete(LoginSession))
        return new_session(session, at=time.time())
