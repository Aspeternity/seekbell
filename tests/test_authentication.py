import time
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
from threading import Barrier

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from pydantic import ValidationError
from seekbell.api.auth import require_administrator
from seekbell.config import Settings
from seekbell.db.models import Administrator, AuthThrottle, BrowserSession
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services.auth import COOKIE_NAME, PASSWORD_HASHER, token_digest
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

CREDENTIALS = {"username": "synthetic-admin", "password": "synthetic long passphrase 123"}


def application(tmp_path, **kwargs):
    app = create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static", **kwargs))

    # Exercise the same dependency every future management router must use.
    @app.api_route(
        "/api/protected-test",
        methods=["GET", "POST"],
        dependencies=[Depends(require_administrator)],
    )
    def protected():
        return {"ok": True}

    return app


def state(client):
    response = client.get("/api/auth/state")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def post(client, action, csrf, credentials=CREDENTIALS, **kwargs):
    headers = {"X-CSRF-Token": csrf, **kwargs.pop("headers", {})}
    return client.post(f"/api/auth/{action}", json=credentials, headers=headers, **kwargs)


def setup(client):
    response = post(client, "setup", state(client)["csrf_token"])
    assert response.status_code == 201, response.text
    return response.json()


def test_atomic_concurrent_setup_and_database_singleton(tmp_path):
    app = application(tmp_path)
    with TestClient(app):
        # Separate cookie jars, deliberately concurrent independent HTTP clients.
        clients = [TestClient(app) for _ in range(8)]
        states = [state(client) for client in clients]
        barrier = Barrier(len(clients))

        def attempt(pair):
            client, auth = pair
            barrier.wait(timeout=10)
            return post(client, "setup", auth["csrf_token"]).status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(attempt, zip(clients, states, strict=True)))
        assert statuses.count(201) == 1
        assert statuses.count(409) == 7
        assert state(clients[0])["initialized"]
        with Session(app.state.engine) as session:
            assert session.scalar(select(func.count()).select_from(Administrator)) == 1
            admin = session.get(Administrator, 1)
            assert admin.password_hash.startswith("$argon2id$")
            assert PASSWORD_HASHER.verify(admin.password_hash, CREDENTIALS["password"])
            assert CREDENTIALS["password"] not in admin.password_hash
        with pytest.raises(IntegrityError), write_session(app.state.engine) as session:
            session.add(Administrator(id=2, username="other", password_hash="synthetic"))
        for client in clients:
            client.close()


def test_session_rotation_authorization_and_logout(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/protected-test").status_code == 401
        preauth = state(client)
        old = client.cookies[COOKIE_NAME]
        assert not preauth["initialized"] and not preauth["authenticated"]
        assert client.get("/api/protected-test").status_code == 401
        auth = post(client, "setup", preauth["csrf_token"]).json()
        token = client.cookies[COOKIE_NAME]
        assert token != old and auth["csrf_token"] != preauth["csrf_token"]
        assert auth["username"] == CREDENTIALS["username"]
        assert client.get("/api/protected-test").status_code == 200
        assert client.post("/api/protected-test").status_code == 403
        assert (
            client.post(
                "/api/protected-test", headers={"X-CSRF-Token": auth["csrf_token"]}
            ).status_code
            == 200
        )
        with Session(app.state.engine) as session:
            assert session.get(BrowserSession, token) is None
            assert session.get(BrowserSession, token_digest(token)) is not None
        stolen = TestClient(app)
        stolen.cookies.set(COOKIE_NAME, old)
        assert stolen.get("/api/protected-test").status_code == 401
        stolen.close()
        assert post(client, "logout", preauth["csrf_token"], None).status_code == 403
        response = post(client, "logout", auth["csrf_token"], None)
        assert response.status_code == 204 and not response.content
        assert COOKIE_NAME not in client.cookies
        replay = TestClient(app)
        replay.cookies.set(COOKIE_NAME, token)
        assert replay.get("/api/protected-test").status_code == 401
        replay.close()


def test_restart_preserves_admin_session_csrf_and_login_throttle(tmp_path):
    settings = Settings(data_dir=tmp_path, static_dir=tmp_path / "static")
    app = create_app(settings)
    with TestClient(app) as client:
        auth = setup(client)
        token = client.cookies[COOKIE_NAME]
        bad = {**CREDENTIALS, "password": "wrong synthetic password"}
        assert post(client, "login", auth["csrf_token"], bad).status_code == 401
    with TestClient(create_app(settings)) as client:
        client.cookies.set(COOKIE_NAME, token, domain="testserver.local")
        restored = state(client)
        assert restored == auth
        assert post(client, "setup", restored["csrf_token"]).status_code == 409
        assert post(client, "logout", restored["csrf_token"], None).status_code == 204
        preauth = state(client)
        logged_in = post(client, "login", preauth["csrf_token"])
        assert logged_in.status_code == 200 and logged_in.json()["authenticated"]
        assert client.cookies[COOKIE_NAME] != token
        with Session(client.app.state.engine) as session:
            assert session.get(AuthThrottle, 1).attempts == 3


@pytest.mark.parametrize("action", ["setup", "login", "logout"])
@pytest.mark.parametrize("violation", ["missing", "wrong", "origin", "null", "fetch-site"])
def test_csrf_required_for_all_auth_mutations(tmp_path, action, violation):
    with TestClient(application(tmp_path)) as client:
        auth = setup(client) if action == "logout" else state(client)
        token = auth["csrf_token"] if violation != "wrong" else "x" * 64
        headers = {} if violation == "missing" else {"X-CSRF-Token": token}
        if violation == "origin":
            headers["Origin"] = "https://external.invalid"
        elif violation == "null":
            headers["Origin"] = "null"
        elif violation == "fetch-site":
            headers["Sec-Fetch-Site"] = "cross-site"
        response = client.post(f"/api/auth/{action}", json=CREDENTIALS, headers=headers)
        assert response.status_code == 403
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("trusted", "peer", "base_url", "forwarded", "secure"),
    [
        ([], "10.1.1.2", "http://seekbell.test", "https", False),
        (["10.1.1.2"], "10.1.1.3", "http://seekbell.test", "https", False),
        (["10.1.1.2"], "10.1.1.2", "https://seekbell.test", "https", True),
        (["10.1.1.0/24"], "10.1.1.2", "https://seekbell.test", "https", True),
        ([], "10.1.1.2", "https://seekbell.test", None, True),
        ([], "10.1.1.2", "http://seekbell.test", None, False),
    ],
)
def test_http_https_and_trusted_proxy_cookies(tmp_path, trusted, peer, base_url, forwarded, secure):
    app = application(tmp_path, trusted_proxies=trusted)
    # The ASGI transport scheme is HTTP when TLS terminates at the trusted proxy.
    if forwarded:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        class BackendHTTP:
            async def __call__(self, scope, receive, send):
                if scope["type"] == "http":
                    scope = {**scope, "scheme": "http"}
                await app(scope, receive, send)

        transport = BackendHTTP()
        assert any(m.cls is ProxyHeadersMiddleware for m in app.user_middleware)
    else:
        transport = app
    with TestClient(app):
        client = TestClient(transport, base_url=base_url, client=(peer, 12345))
        try:
            if forwarded:
                client.headers["X-Forwarded-Proto"] = forwarded
                client.headers["X-Forwarded-Host"] = "attacker.invalid"
                client.headers["Forwarded"] = "proto=https;host=attacker.invalid"
            initial_response = client.get("/api/auth/state")
            auth = initial_response.json()
            response = post(client, "setup", auth["csrf_token"], headers={"Origin": base_url})
            assert response.status_code == 201, response.text
            for cookie_header in [
                initial_response.headers["set-cookie"],
                response.headers["set-cookie"],
            ]:
                cookie = SimpleCookie(cookie_header)[COOKIE_NAME]
                assert bool(cookie["secure"]) is secure
                assert cookie["httponly"] and cookie["samesite"] == "strict"
                assert cookie["path"] == "/" and not cookie["domain"]
            assert state(client)["authenticated"]
            response = post(client, "logout", state(client)["csrf_token"], None)
            assert response.status_code == 204
            deleted = SimpleCookie(response.headers["set-cookie"])[COOKIE_NAME]
            assert bool(deleted["secure"]) is secure and deleted["max-age"] == "0"
        finally:
            client.close()


def test_https_session_cannot_be_replayed_over_http(tmp_path):
    app = application(tmp_path)
    with TestClient(app, base_url="https://seekbell.test") as client:
        setup(client)
        token = client.cookies[COOKIE_NAME]
        http = TestClient(app, base_url="http://seekbell.test")
        http.cookies.set(COOKIE_NAME, token)
        assert http.get("/api/protected-test").status_code == 401
        http.close()


def test_invalid_expired_sessions_and_anonymous_storage_bound(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        auth = setup(client)
        with write_session(app.state.engine) as session:
            session.get(BrowserSession, token_digest(client.cookies[COOKIE_NAME])).expires_at = 0
        assert post(client, "logout", auth["csrf_token"], None).status_code == 401
        assert not state(client)["authenticated"]
        for _ in range(135):
            client.cookies.clear()
            assert not state(client)["authenticated"]
        with Session(app.state.engine) as session:
            assert session.scalar(select(func.count()).select_from(BrowserSession)) == 128
        client.cookies.set(COOKIE_NAME, "malformed")
        assert not state(client)["authenticated"]


def test_generic_login_failure_and_persisted_global_rate_limit(tmp_path):
    app = application(tmp_path)
    with TestClient(app) as client:
        auth = setup(client)
        failures = []
        for i in range(9):
            credentials = {**CREDENTIALS}
            credentials["username" if i % 2 else "password"] = "wrong synthetic credentials"
            response = post(client, "login", auth["csrf_token"], credentials)
            assert response.status_code == 401
            failures.append(response.json())
        assert all(value == failures[0] for value in failures)
        limited = post(client, "login", auth["csrf_token"])
        assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
        with write_session(app.state.engine) as session:
            session.get(AuthThrottle, 1).window_started = time.time() - 61
        assert post(client, "login", auth["csrf_token"]).status_code == 200


@pytest.mark.parametrize(
    "changes",
    [
        {"password": "short"},
        {"password": "x" * 129},
        {"username": " "},
        {"username": "x" * 65},
        {"username": "bad\nname"},
        {"unexpected": "synthetic"},
    ],
)
def test_validation_does_not_echo_credentials(tmp_path, changes, caplog):
    with TestClient(application(tmp_path)) as client:
        credentials = {**CREDENTIALS, **changes}
        response = post(client, "setup", state(client)["csrf_token"], credentials)
        assert response.status_code == 422
        assert CREDENTIALS["password"] not in response.text + caplog.text
        assert response.json() == {"detail": "请求参数无效，请检查输入。"}


def test_unicode_passwords_and_trimmed_usernames(tmp_path):
    with TestClient(application(tmp_path)) as client:
        credentials = {"username": "  示例用户  ", "password": " 中文密码长短语 和空格 123456 "}
        response = post(client, "setup", state(client)["csrf_token"], credentials)
        assert response.status_code == 201
        assert response.json()["username"] == "示例用户"
        response = post(client, "login", response.json()["csrf_token"], credentials)
        assert response.status_code == 200


@pytest.mark.parametrize("values", [["*"], ["0.0.0.0/0"], ["::/0"], ["localhost"]])
def test_proxy_configuration_requires_explicit_networks(values):
    with pytest.raises(ValidationError):
        Settings(trusted_proxies=values)


def test_auth_migration_from_m2_and_failure_rollback(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0003_notifications")
        with engine.connect() as connection:
            marker = connection.execute(text("SELECT * FROM installation")).all()

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "CREATE TABLE browser_sessions" in statement:
                raise RuntimeError("synthetic authentication migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="authentication migration"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0003_notifications"
        assert "administrators" not in inspect(engine).get_table_names()
        migrate(engine)
        migrate(engine)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM installation")).all() == marker
            assert connection.scalar(text("SELECT COUNT(*) FROM administrators")) == 0
            assert connection.execute(text("SELECT enabled FROM sources")).all() == [(0,)]
    finally:
        engine.dispose()
