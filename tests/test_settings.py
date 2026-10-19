import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    AccountThrottle,
    Administrator,
    BrowserSession,
    DeliveredPost,
    DeliveryAttempt,
    ManualDeliveryAttempt,
    Outbox,
    OutboxContribution,
    Post,
    RuleHit,
    SeenPost,
    SourceItem,
    TargetTestAttempt,
)
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.main import create_app
from seekbell.services.auth import (
    COOKIE_NAME,
    PASSWORD_HASHER,
    AuthError,
    token_digest,
)
from seekbell.services.configuration import ConfigurationConflict
from seekbell.services.delivery import DeliveryWorker
from seekbell.services.manual_delivery import ManualDelivery
from seekbell.services.settings import SystemSettings
from seekbell.services.target_testing import TargetTesting
from sqlalchemy import event, inspect, select, text
from sqlalchemy.orm import Session

from tests.core_helpers import RecordingNotifier
from tests.test_authentication import CREDENTIALS, post, state


def change_body(**overrides):
    return {
        "username": "synthetic-updated",
        "current_password": CREDENTIALS["password"],
        "new_password": "new synthetic long passphrase",
        **overrides,
    }


def update(client, **overrides):
    value = client.get("/api/manage/settings").json()
    return client.put(
        "/api/manage/settings",
        json={
            "expected_revision": value["revision"],
            "timezone": "UTC",
            "retention_days": 30,
            **overrides,
        },
    )


@pytest.mark.parametrize(
    "path,method",
    [
        ("/settings", "GET"),
        ("/settings/timezones", "GET"),
        ("/settings", "PUT"),
        ("/settings/cleanup", "POST"),
        ("/account", "PUT"),
    ],
)
def test_system_routes_require_login(tmp_path, path, method):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        assert (
            client.request(
                method, "/api/manage" + path, json={} if method != "GET" else None
            ).status_code
            == 401
        )


@pytest.mark.parametrize(
    "path,method", [("/settings", "PUT"), ("/settings/cleanup", "POST"), ("/account", "PUT")]
)
def test_settings_mutations_require_csrf(managed, path, method):
    client, _, _ = managed
    client.headers.pop("X-CSRF-Token")
    assert client.request(method, "/api/manage" + path, json={}).status_code == 403


def test_display_settings_validation_conflict_and_restart(managed):
    client, app, settings = managed
    initial = client.get("/api/manage/settings").json()
    assert initial["timezone"] is None and initial["retention_days"] == 30
    zones = client.get("/api/manage/settings/timezones").json()
    assert "UTC" in zones and "Asia/Shanghai" in zones
    saved = update(client, timezone="Asia/Shanghai", retention_days=7)
    assert saved.status_code == 200 and saved.json()["revision"] == initial["revision"] + 1
    assert saved.json()["alert_target_id"] is None
    assert update(client, alert_target_id="nonexistent-target").status_code == 422
    assert update(client, timezone="../../secret").status_code == 422
    for days in (0, 3651):
        assert update(client, retention_days=days).status_code == 422
    assert update(client, expected_revision=initial["revision"]).status_code == 409
    engine = create_database_engine(settings)
    try:
        assert SystemSettings(engine).get()["timezone"] == "Asia/Shanghai"
    finally:
        engine.dispose()
    assert (
        client.post(
            "/api/manage/settings/cleanup",
            json={"confirmed": False, "expected_revision": saved.json()["revision"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/manage/settings/cleanup",
            json={"confirmed": 1, "expected_revision": saved.json()["revision"]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/manage/settings/cleanup",
            json={"confirmed": True, "expected_revision": initial["revision"]},
        ).status_code
        == 409
    )


def test_account_change_verifies_password_revokes_all_sessions_and_rotates_credentials(managed):
    client, app, _ = managed
    other = TestClient(app)
    try:
        anonymous = state(other)
        assert post(other, "login", anonymous["csrf_token"]).status_code == 200
        tokens = [client.cookies[COOKIE_NAME], other.cookies[COOKIE_NAME]]
        bad = client.put(
            "/api/manage/account", json=change_body(current_password="synthetic wrong password")
        )
        assert bad.status_code == 403 and client.get("/api/manage/settings").status_code == 200
        assert "synthetic wrong password" not in bad.text
        response = client.put("/api/manage/account", json=change_body())
        assert response.status_code == 204 and COOKIE_NAME not in client.cookies
        assert client.get("/api/manage/settings").status_code == 401
        assert other.get("/api/manage/settings").status_code == 401
        with Session(app.state.engine) as session:
            for token in tokens:
                assert session.get(BrowserSession, token_digest(token)) is None
        anonymous = state(client)
        assert post(client, "login", anonymous["csrf_token"], CREDENTIALS).status_code == 401
        credentials = {"username": "synthetic-updated", "password": "new synthetic long passphrase"}
        assert post(client, "login", anonymous["csrf_token"], credentials).status_code == 200
    finally:
        other.close()


def test_username_only_change_keeps_password_and_reauth_budget_is_persistent(managed):
    client, app, settings = managed
    for _ in range(9):
        assert (
            client.put(
                "/api/manage/account", json=change_body(current_password="wrong synthetic pass")
            ).status_code
            == 403
        )
    body = {"username": "renamed-admin", "current_password": CREDENTIALS["password"]}
    assert client.put("/api/manage/account", json=body).status_code == 204
    anonymous = state(client)
    auth = post(
        client,
        "login",
        anonymous["csrf_token"],
        {"username": "renamed-admin", "password": CREDENTIALS["password"]},
    ).json()
    response = client.put(
        "/api/manage/account", headers={"X-CSRF-Token": auth["csrf_token"]}, json=body
    )
    assert response.status_code == 429 and response.headers["Retry-After"] == "60"
    engine = create_database_engine(settings)
    try:
        with Session(engine) as session:
            assert session.get(AccountThrottle, 1).attempts == 10
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "field,value", [("username", "  "), ("new_password", "short"), ("current_password", "")]
)
def test_account_validation_never_echoes_input(managed, field, value):
    client, _, _ = managed
    response = client.put("/api/manage/account", json=change_body(**{field: value}))
    assert response.status_code == 422 and "new synthetic long passphrase" not in response.text
    assert client.get("/api/manage/settings").status_code == 200


def test_login_verified_before_account_change_cannot_issue_a_new_session(managed, monkeypatch):
    client, app, _ = managed
    entered, release = Event(), Event()
    anonymous = app.state.authentication.anonymous(secure=False)
    identity = app.state.authentication.resolve(anonymous, secure=False)
    original = PASSWORD_HASHER.verify

    def paused(stored, password):
        result = original(stored, password)
        if password == CREDENTIALS["password"]:
            entered.set()
            assert release.wait(3)
        return result

    monkeypatch.setattr(
        "seekbell.services.auth.PASSWORD_HASHER",
        SimpleNamespace(verify=paused, hash=PASSWORD_HASHER.hash),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            app.state.authentication.login,
            CREDENTIALS["username"],
            CREDENTIALS["password"],
            identity,
            secure=False,
        )
        assert entered.wait(2)
        with write_session(app.state.engine) as session:
            session.get(Administrator, 1).password_hash = PASSWORD_HASHER.hash(
                "concurrent synthetic password"
            )
        release.set()
        with pytest.raises(AuthError) as error:
            pending.result(timeout=3)
        assert error.value.status == 401


def test_account_reauth_cannot_commit_after_session_revocation(managed, monkeypatch):
    client, app, _ = managed
    entered, release = Event(), Event()
    identity = app.state.authentication.resolve(client.cookies[COOKIE_NAME], secure=False)
    original = PASSWORD_HASHER.verify

    def paused(stored, password):
        result = original(stored, password)
        entered.set()
        assert release.wait(3)
        return result

    monkeypatch.setattr(
        "seekbell.services.auth.PASSWORD_HASHER",
        SimpleNamespace(verify=paused, hash=PASSWORD_HASHER.hash),
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            app.state.authentication.change_account,
            identity,
            current_password=CREDENTIALS["password"],
            username="blocked",
            new_password=None,
        )
        assert entered.wait(2)
        app.state.authentication.logout(identity)
        release.set()
        with pytest.raises(AuthError) as error:
            pending.result(timeout=3)
        assert error.value.status == 409
    assert app.state.authentication.username() == CREDENTIALS["username"]


def test_history_cleanup_preserves_tombstones_and_never_requeues_old_posts(core):
    core.queued()
    asyncio.run(
        DeliveryWorker(core.engine, {"mock": RecordingNotifier()}, clock=lambda: 30).run_once()
    )
    service = SystemSettings(core.engine)
    before = {
        model.__tablename__: core.count(model) for model in (SeenPost, DeliveredPost, SourceItem)
    }
    result = service.cleanup(at=40 * 86400)
    assert result["counts"]["posts"] == 2 and result["counts"]["outbox"] == 1
    assert (
        core.count(Post)
        == core.count(Outbox)
        == core.count(DeliveryAttempt)
        == core.count(RuleHit)
        == core.count(OutboxContribution)
        == 0
    )
    assert before == {
        model.__tablename__: core.count(model) for model in (SeenPost, DeliveredPost, SourceItem)
    }
    report = core.ingest(9001, 9002, at=40 * 86400 + 1)
    assert report.new_posts == report.queued == 0 and core.count(Outbox) == 0
    assert service.get()["last_cleanup_at"] == 40 * 86400


@pytest.mark.parametrize(
    "status", ["pending", "retry", "leased", "uncertain", "recent_attempt", "unfinished_attempt"]
)
def test_cleanup_preserves_unfinished_uncertain_or_recent_delivery_evidence(core, status):
    core.queued()
    if status in ("pending", "retry", "leased"):
        with write_session(core.engine) as session:
            row = session.scalars(select(Outbox)).one()
            row.status = status
            if status == "leased":
                row.lease_token, row.lease_until = str(uuid4()), 100
    else:
        asyncio.run(
            DeliveryWorker(core.engine, {"mock": RecordingNotifier()}, clock=lambda: 30).run_once()
        )
        with write_session(core.engine) as session:
            row = session.scalars(select(Outbox)).one()
            if status == "uncertain":
                row.uncertain = True
            if status == "recent_attempt":
                session.scalars(select(DeliveryAttempt)).one().late_finished_at = 39 * 86400
            if status == "unfinished_attempt":
                session.scalars(select(DeliveryAttempt)).one().finished_at = None
    before = copy.deepcopy(core.one(Outbox).payload)
    result = SystemSettings(core.engine).cleanup(at=40 * 86400)
    assert (
        result["counts"]["outbox"] == 0
        and core.count(Outbox) == core.count(RuleHit) == core.count(OutboxContribution) == 1
    )
    assert core.count(Post) == 1 and core.one(Outbox).payload == before


def test_cleanup_preserves_recent_manual_reference_and_unknown_explicit_results(core):
    core.queued()
    asyncio.run(
        DeliveryWorker(core.engine, {"mock": RecordingNotifier()}, clock=lambda: 30).run_once()
    )
    sender = ManualDelivery(core.engine, {"mock": RecordingNotifier()}, clock=lambda: 39 * 86400)
    asyncio.run(sender.run(core.one(Outbox).id, key=str(uuid4()), expected_revision=1))
    tester = TargetTesting(
        core.engine,
        {"mock": RecordingNotifier(SendResult(status="unknown", code="synthetic_unknown"))},
        clock=lambda: 1,
    )
    asyncio.run(tester.run(core.target))
    tester._start(core.target)
    result = SystemSettings(core.engine).cleanup(at=40 * 86400)
    assert (
        result["counts"]["outbox"] == 0
        and core.count(ManualDeliveryAttempt) == 1
        and core.count(TargetTestAttempt) == 2
    )
    # When completed manual history ages out, its old automatic parent may follow.
    later = SystemSettings(core.engine).cleanup(at=80 * 86400)
    assert later["counts"]["manual_delivery_attempts"] == later["counts"]["outbox"] == 1
    assert core.count(TargetTestAttempt) == 2 and core.count(DeliveredPost) == 1


def test_cleanup_is_bounded_and_transactional_and_rejects_old_policy(core):
    core.ingest(9001, 9002, 9003, 9004, at=10)
    service = SystemSettings(core.engine)
    service.update(expected_revision=1, timezone="UTC", retention_days=1)
    with pytest.raises(ConfigurationConflict):
        service.cleanup(at=10 * 86400, expected_revision=1)
    assert core.count(Post) == 4

    def fail(_connection, _cursor, statement, *_args):
        if statement.startswith("UPDATE application_settings"):
            raise RuntimeError("synthetic cleanup fault")

    event.listen(core.engine, "before_cursor_execute", fail)
    with pytest.raises(RuntimeError, match="cleanup fault"):
        service.cleanup(at=10 * 86400, limit=2)
    event.remove(core.engine, "before_cursor_execute", fail)
    assert core.count(Post) == 4
    assert service.cleanup(at=10 * 86400, limit=2)["counts"]["posts"] == 2
    assert core.count(Post) == 2 and core.count(SeenPost) == 4


def test_settings_migration_rolls_back_and_does_not_reset_existing_data(tmp_path):
    engine = create_database_engine(Settings(data_dir=tmp_path))
    try:
        migrate(engine, "0006_manual_deliveries")
        with engine.begin() as connection:
            connection.execute(text("UPDATE sources SET interval_seconds=17"))

        def fail(_connection, _cursor, statement, *_args):
            if "CREATE TABLE account_throttle" in statement:
                raise RuntimeError("synthetic migration fault")

        event.listen(engine, "before_cursor_execute", fail)
        with pytest.raises(RuntimeError, match="migration fault"):
            migrate(engine, "0007_settings")
        event.remove(engine, "before_cursor_execute", fail)
        assert (
            schema_revision(engine) == "0006_manual_deliveries"
            and "application_settings" not in inspect(engine).get_table_names()
        )
        migrate(engine, "0007_settings")
        migrate(engine, "0007_settings")
        assert SystemSettings(engine).get()["retention_days"] == 30
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT interval_seconds FROM sources")) == 17
    finally:
        engine.dispose()


def test_background_maintenance_prunes_without_fetching_or_sending(core):
    import httpx
    from cryptography.fernet import Fernet
    from seekbell.notifiers.credentials import CredentialVault
    from seekbell.services.runtime import ApplicationRuntime

    core.queued()
    asyncio.run(
        DeliveryWorker(core.engine, {"mock": RecordingNotifier()}, clock=lambda: 30).run_once()
    )
    core.config.set_source_enabled("nodeseek-rss", False, at=31)

    def forbidden(request):
        raise AssertionError("maintenance must not access network")

    async def exercise():
        runtime = ApplicationRuntime(
            core.engine,
            CredentialVault(Fernet.generate_key()),
            enabled=True,
            rss_transport=httpx.MockTransport(forbidden),
            notification_transport=httpx.MockTransport(forbidden),
        )
        await runtime.start()
        try:
            for _ in range(100):
                if core.count(Post) == 0:
                    break
                await asyncio.sleep(0.01)
            assert core.count(Post) == 0
            assert runtime.snapshot()["healthy"]
            assert SystemSettings(core.engine).get()["last_cleanup_at"] is not None
        finally:
            await runtime.aclose()

    asyncio.run(exercise())
    assert core.count(SeenPost) == 2 and core.count(DeliveredPost) == 1
