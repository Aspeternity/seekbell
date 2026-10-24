from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    Administrator,
    LoginSession,
    NotificationTarget,
    Source,
    Task,
    TaskVersion,
    WebsiteInstallation,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.rules import Rule
from seekbell.main import create_app
from seekbell.services.authentication import initialize, token_hash
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

PASSWORD = "Synthetic-Password-2026"
CREDENTIALS = {"username": "test_admin", "password": PASSWORD}


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, static_dir=tmp_path / "static"))


def authenticate(client, setup=True):
    csrf = client.get("/api/auth/status").json()["csrf"]
    response = client.post(
        "/api/auth/setup" if setup else "/api/auth/login",
        json=CREDENTIALS,
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return response


def target(client, **overrides):
    values = {
        "name": "Synthetic webhook",
        "kind": "webhook",
        "enabled": False,
        "config": {
            "url": "https://receiver.example.test/synthetic-secret",
            "headers": {"X-Test": "synthetic-header-secret"},
        },
    }
    values.update(overrides)
    response = client.post("/api/manage/targets", json=values)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def task_values(target_id):
    return {
        "name": "VPS radar",
        "description": "Keep this note after restart",
        "website_id": "nodeseek",
        "enabled": False,
        "rule": Rule(groups=[{"all_of": ["VPS"]}]).model_dump(mode="json"),
        "target_ids": [target_id],
    }


def test_real_configuration_survives_restart_login_and_preserves_notes(app):
    with TestClient(app) as client:
        status = client.get("/api/auth/status").json()
        assert not status["initialized"] and not status["authenticated"]
        response = authenticate(client)
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        initial = client.get("/api/manage/workspace")
        assert initial.headers["cache-control"] == "no-store"
        assert initial.json()["websites"] == []
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "nodeseek"}).status_code == 201
        )
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "nodeseek"}).status_code == 409
        )
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "unknown"}).status_code == 422
        )
        key = target(client)
        values = task_values(key)
        response = client.post("/api/manage/tasks", json=values)
        assert response.status_code == 201, response.text
        task_id = response.json()["id"]
        assert (
            client.put(
                "/api/manage/workspace", json={"name": "真实信息空间", "description": "配置持久化"}
            ).status_code
            == 200
        )
        assert (
            client.put(
                "/api/manage/websites/nodeseek", json={"enabled": True, "interval": 25}
            ).status_code
            == 200
        )
        assert client.delete("/api/manage/websites/nodeseek").status_code == 409
        assert client.post("/api/auth/logout").status_code == 200
        assert client.get("/api/manage/workspace").status_code == 401
    with TestClient(app) as client:
        authenticate(client, setup=False)
        data = client.get("/api/manage/workspace").json()
        assert data["tasks"][0]["description"] == values["description"]
        assert data["tasks"][0]["rule"]["groups"][0]["all_of"] == ["VPS"]
        assert data["tasks"][0]["target_ids"] == [key]
        assert data["websites"][0]["interval"] == 25
        assert data["settings"]["workspaceName"] == "真实信息空间"
        assert not data["runtime_active"]
        values["description"] = "A new version"
        assert client.put(f"/api/manage/tasks/{task_id}", json=values).status_code == 200
        with Session(app.state.engine) as session:
            assert (
                session.get(TaskVersion, (task_id, 1)).description == "Keep this note after restart"
            )
            assert session.get(TaskVersion, (task_id, 2)).description == "A new version"
        assert client.delete(f"/api/manage/tasks/{task_id}").status_code == 200
        assert client.delete("/api/manage/websites/nodeseek").status_code == 200
        assert client.get("/api/manage/workspace").json()["websites"] == []
        with Session(app.state.engine) as session:
            assert session.get(Task, task_id) is not None
            assert session.get(Source, "nodeseek-rss") is not None


def test_access_control_csrf_origin_and_safe_validation_errors(app):
    with TestClient(app) as client:
        assert client.get("/api/manage/workspace").status_code == 401
        assert client.post("/api/auth/setup", json=CREDENTIALS).status_code == 403
        csrf = client.get("/api/auth/status").json()["csrf"]
        assert (
            client.post(
                "/api/auth/setup",
                json=CREDENTIALS,
                headers={"X-CSRF-Token": csrf, "Origin": "https://other.example.test"},
            ).status_code
            == 403
        )
        authenticate(client)
        csrf = client.headers.pop("X-CSRF-Token")
        assert (
            client.post("/api/manage/websites", json={"adapter_id": "nodeseek"}).status_code == 403
        )
        client.headers["X-CSRF-Token"] = csrf
        assert (
            client.post(
                "/api/manage/websites",
                json={"adapter_id": "nodeseek"},
                headers={"Origin": "http://testserver"},
            ).status_code
            == 201
        )
        assert client.put("/api/manage/workspace", json={"name": " "}).status_code == 422
        assert (
            client.post(
                "/api/manage/targets",
                json={
                    "name": "invalid",
                    "kind": "webhook",
                    "enabled": False,
                    "config": {"url": "synthetic-private-value"},
                },
            ).status_code
            == 422
        )
        response = client.post(
            "/api/manage/targets",
            json={"kind": "unsupported", "password": "never-echo-this-private-value"},
        )
        assert response.status_code == 422
        assert "never-echo" not in response.text and "password" not in response.text
        old_cookie = client.cookies.get("seekbell_session")
        client.post("/api/auth/logout")
        client.cookies.set("seekbell_session", old_cookie)
        assert client.get("/api/manage/workspace").status_code == 401


def test_parallel_initialization_allows_exactly_one_admin(app):
    with TestClient(app):

        def create(index):
            try:
                return initialize(app.state.engine, f"admin_{index}", PASSWORD)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, range(2)))
        assert sum(item is not None for item in results) == 1
        with Session(app.state.engine) as session:
            assert len(session.scalars(select(Administrator)).all()) == 1
            stored = session.get(Administrator, 1).password_hash
            assert stored.startswith("scrypt$") and PASSWORD not in stored


def test_duplicate_setup_login_failure_and_throttling(app):
    with TestClient(app) as client:
        authenticate(client)
        client.post("/api/auth/logout")
        csrf = client.get("/api/auth/status").json()["csrf"]
        client.headers["X-CSRF-Token"] = csrf
        assert client.post("/api/auth/setup", json=CREDENTIALS).status_code == 409
        assert (
            client.post(
                "/api/auth/login", json={**CREDENTIALS, "password": "incorrect"}
            ).status_code
            == 401
        )
        # Invalid short input consumes a rate-limit slot without doing expensive hashes.
        for _ in range(10):
            response = client.post("/api/auth/login", json={**CREDENTIALS, "password": ""})
        assert response.status_code == 429 and response.headers["retry-after"] == "60"


def test_session_persists_restart_expires_and_https_cookie(app):
    with TestClient(app, base_url="https://testserver") as client:
        response = authenticate(client)
        assert "secure" in response.headers["set-cookie"].lower()
        cookie = client.cookies.get("seekbell_session")
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set("seekbell_session", cookie)
        assert client.get("/api/manage/workspace").status_code == 200
        with write_session(app.state.engine) as session:
            session.get(LoginSession, token_hash(cookie)).expires_at = 0
        assert client.get("/api/manage/workspace").status_code == 401


def test_credentials_are_encrypted_omitted_and_retained_on_update(app):
    with TestClient(app) as client:
        authenticate(client)
        key = target(client)
        response = client.get("/api/manage/workspace")
        assert "synthetic-secret" not in response.text
        assert "synthetic-header-secret" not in response.text
        with Session(app.state.engine) as session:
            ciphertext = session.get(NotificationTarget, key).config_ciphertext
            assert "synthetic-secret" not in ciphertext
            assert app.state.vault.unseal(key, "webhook", ciphertext)["url"].endswith(
                "synthetic-secret"
            )
        response = client.put(
            f"/api/manage/targets/{key}",
            json={
                "name": "renamed",
                "kind": "webhook",
                "enabled": False,
                "config": {"summary_limit": 50},
            },
        )
        assert response.status_code == 200, response.text
        with Session(app.state.engine) as session:
            values = app.state.vault.unseal(
                key, "webhook", session.get(NotificationTarget, key).config_ciphertext
            )
            assert values["url"].endswith("synthetic-secret")
            assert values["summary_limit"] == 50
    app.state.settings.data_dir.joinpath("credentials.key").unlink()
    with pytest.raises(ValueError, match="key"), TestClient(app):
        pass
    assert not app.state.settings.data_dir.joinpath("credentials.key").exists()


def test_task_requires_installed_site_and_configured_target_and_server_rule_engine(app):
    with TestClient(app) as client:
        authenticate(client)
        key = target(client)
        values = task_values(key)
        assert client.post("/api/manage/tasks", json=values).status_code == 409
        client.post("/api/manage/websites", json={"adapter_id": "nodeseek"})
        assert (
            client.post("/api/manage/tasks", json={**values, "target_ids": []}).status_code == 422
        )
        assert (
            client.post("/api/manage/tasks", json={**values, "target_ids": ["missing"]}).status_code
            == 422
        )
        result = client.post(
            "/api/manage/rules/evaluate",
            json={
                "rule": Rule(groups=[{"all_of": ["STRASSE"]}]).model_dump(mode="json"),
                "post": {"title": "Straße"},
            },
        )
        assert result.status_code == 200, result.text
        assert result.json()["status"] == "match"


def test_legacy_m2_upgrade_retains_installed_site_tasks_and_source_settings(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0003_notifications")
        key, task_id = "legacy-target", "legacy-task"
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO notification_targets(id,name,kind,revision,enabled) "
                    "VALUES (:id,'Old synthetic','mock',1,1)"
                ),
                {"id": key},
            )
            connection.execute(
                text(
                    "INSERT INTO tasks (id,website_id,current_version,enabled,created_at) "
                    "VALUES (:id,'nodeseek',1,1,1)"
                ),
                {"id": task_id},
            )
            connection.execute(
                text(
                    "INSERT INTO task_versions (task_id,version,name,rule,target_ids,created_at) "
                    "VALUES (:id,1,'Existing task',:rule,:targets,1)"
                ),
                {"id": task_id, "rule": Rule().model_dump_json(), "targets": '["' + key + '"]'},
            )
        with write_session(engine) as session:
            session.get(Source, "nodeseek-rss").interval_seconds = 31
        migrate(engine)
        migrate(engine)
        with Session(engine) as session:
            assert session.get(WebsiteInstallation, "nodeseek")
            assert session.get(Source, "nodeseek-rss").interval_seconds == 31
            assert session.get(TaskVersion, (task_id, 1)).description == ""
    finally:
        engine.dispose()


def test_failed_management_upgrade_rolls_back_and_can_retry(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0003_notifications")

        def fail(_connection, _cursor, statement, _parameters, _context, _many):
            if "CREATE TABLE login_sessions" in statement:
                raise RuntimeError("synthetic management migration failure")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="migration failure"):
            migrate(engine)
        event.remove(engine, "before_cursor_execute", fail)
        assert schema_revision(engine) == "0003_notifications"
        assert "administrators" not in inspect(engine).get_table_names()
        with Session(engine) as session:
            assert session.get(Source, "nodeseek-rss")
        migrate(engine)
        assert schema_revision(engine) == "0014_task_websites"
        with Session(engine) as session:
            assert session.get(WebsiteInstallation, "nodeseek")
    finally:
        engine.dispose()
