from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import Administrator, LoginSession
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services import authentication as auth
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.test_management import CREDENTIALS, PASSWORD, authenticate

NEW_PASSWORD = "Synthetic-New-Password-2026"


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))


def values(**overrides):
    return {"username": "renamed_admin", "current_password": PASSWORD, **overrides}


def test_password_change_rotates_all_sessions_and_survives_restart(app):
    with TestClient(app, base_url="https://testserver") as client:
        original = authenticate(client).json()
        old_cookie = client.cookies.get("seekbell_session")
        other, other_csrf = auth.login(app.state.engine, **CREDENTIALS)
        response = client.put("/api/auth/administrator", json=values(new_password=NEW_PASSWORD))
        assert response.status_code == 200, response.text
        assert "secure" in response.headers["set-cookie"].lower()
        assert response.json()["csrf"] != original["csrf"]
        assert client.cookies.get("seekbell_session") != old_cookie
        client.headers["X-CSRF-Token"] = response.json()["csrf"]
        assert client.get("/api/auth/status").json()["username"] == "renamed_admin"
        assert (
            client.put(
                "/api/manage/workspace", json={"name": "保留的工作空间", "description": ""}
            ).status_code
            == 200
        )
        assert auth.session_info(app.state.engine, old_cookie) is None
        assert auth.session_info(app.state.engine, other) is None
        assert auth.login(app.state.engine, **CREDENTIALS) is None
        assert auth.login(app.state.engine, "renamed_admin", PASSWORD) is None
        with Session(app.state.engine) as session:
            assert len(session.scalars(select(LoginSession)).all()) == 1
            assert NEW_PASSWORD not in session.get(Administrator, 1).password_hash
        assert NEW_PASSWORD not in response.text and PASSWORD not in response.text
    with TestClient(app) as client:
        csrf = client.get("/api/auth/status").json()["csrf"]
        response = client.post(
            "/api/auth/login",
            json={"username": "renamed_admin", "password": NEW_PASSWORD},
            headers={"X-CSRF-Token": csrf},
        )
        assert response.status_code == 200
        assert (
            client.get("/api/manage/workspace").json()["settings"]["workspaceName"]
            == "保留的工作空间"
        )


def test_username_only_change_retains_password_and_rotates_hash_and_cookie(app):
    with TestClient(app) as client:
        authenticate(client)
        with Session(app.state.engine) as session:
            old_hash = session.get(Administrator, 1).password_hash
        response = client.put("/api/auth/administrator", json=values())
        assert response.status_code == 200
        assert auth.login(app.state.engine, "renamed_admin", PASSWORD)
        assert auth.login(app.state.engine, **CREDENTIALS) is None
        with Session(app.state.engine) as session:
            assert session.get(Administrator, 1).password_hash != old_hash


def test_incorrect_current_password_does_not_change_credentials_or_session(app):
    with TestClient(app) as client:
        authenticate(client)
        cookie = client.cookies.get("seekbell_session")
        response = client.put(
            "/api/auth/administrator", json=values(current_password="synthetic-wrong-password")
        )
        assert response.status_code == 400
        assert "synthetic-wrong-password" not in response.text
        assert auth.session_info(app.state.engine, cookie)["username"] == CREDENTIALS["username"]
        assert client.cookies.get("seekbell_session") == cookie


def test_validation_origin_csrf_and_expired_session_fail_closed(app):
    with TestClient(app) as client:
        assert client.put("/api/auth/administrator", json=values()).status_code == 401
        authenticate(client)
        assert (
            client.put(
                "/api/auth/administrator", json=values(), headers={"X-CSRF-Token": ""}
            ).status_code
            == 403
        )
        assert (
            client.put(
                "/api/auth/administrator",
                json=values(),
                headers={"Origin": "https://other.example.test"},
            ).status_code
            == 403
        )
        for invalid in [
            values(username="bad name"),
            values(new_password="short"),
            values(current_password=""),
            values(extra="never-echo-secret"),
            values(username=CREDENTIALS["username"]),
        ]:
            response = client.put("/api/auth/administrator", json=invalid)
            assert response.status_code == 422
            assert "never-echo-secret" not in response.text
        cookie = client.cookies.get("seekbell_session")
        with write_session(app.state.engine) as session:
            session.get(LoginSession, auth.token_hash(cookie)).expires_at = 0
        assert client.put("/api/auth/administrator", json=values()).status_code == 401


def test_reauthentication_is_rate_limited_before_hashing(app, monkeypatch):
    with TestClient(app) as client:
        authenticate(client)

        def reject(*args):
            raise AssertionError("Rate-limited requests must not hash")

        for _ in range(9):
            assert (
                client.put("/api/auth/administrator", json=values(new_password="x")).status_code
                == 422
            )
        monkeypatch.setattr(auth, "update_administrator", reject)
        response = client.put("/api/auth/administrator", json=values())
        assert response.status_code == 429 and response.headers["retry-after"] == "60"


@pytest.mark.parametrize("revoke", ["change", "logout", "expire"])
def test_reauthentication_rechecks_session_after_hashing(app, monkeypatch, revoke):
    with TestClient(app) as client:
        info = authenticate(client).json()
        cookie = client.cookies.get("seekbell_session")
        original_hash = auth.password_hash

        def hash_then_revoke(*args, **kwargs):
            result = original_hash(*args, **kwargs)
            if revoke == "change":
                # Simulate another committed administrator edit while hashing.
                with write_session(app.state.engine) as session:
                    session.get(Administrator, 1).password_hash = "changed-elsewhere"
            else:
                with write_session(app.state.engine) as session:
                    row = session.get(LoginSession, auth.token_hash(cookie))
                    if revoke == "logout":
                        session.delete(row)
                    else:
                        row.expires_at = 0
            return result

        # verify_password also uses password_hash; intervene only on fresh-salt rehash.
        def intercept(password, salt=None):
            return original_hash(password, salt) if salt else hash_then_revoke(password)

        monkeypatch.setattr(auth, "password_hash", intercept)
        with pytest.raises(auth.InvalidSession):
            auth.update_administrator(
                app.state.engine, cookie, info["csrf"], "new_admin", PASSWORD, NEW_PASSWORD
            )
        with Session(app.state.engine) as session:
            assert session.get(Administrator, 1).username == CREDENTIALS["username"]


def test_old_login_cannot_create_a_session_after_password_change(app, monkeypatch):
    with TestClient(app) as client:
        info = authenticate(client).json()
        cookie = client.cookies.get("seekbell_session")
        verified, release = Event(), Event()
        original = auth.verify_password

        def verify_then_wait(*args):
            result = original(*args)
            verified.set()
            assert release.wait(10)
            return result

        monkeypatch.setattr(auth, "verify_password", verify_then_wait)
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(auth.login, app.state.engine, **CREDENTIALS)
            assert verified.wait(10)
            monkeypatch.setattr(auth, "verify_password", original)
            try:
                auth.update_administrator(
                    app.state.engine, cookie, info["csrf"], "new_admin", PASSWORD, NEW_PASSWORD
                )
            finally:
                release.set()
            assert pending.result(timeout=10) is None
        assert auth.login(app.state.engine, "new_admin", NEW_PASSWORD)
