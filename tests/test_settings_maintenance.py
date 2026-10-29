"""Settings preserve drafts through conflicts and maintenance never mutates business data."""

import json

import pytest
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.runtime import create_database_engine, migrate, schema_revision
from seekbell.main import create_app
from seekbell.services.backup_demo import table_data
from seekbell.services.maintenance import backup_records, record_backup, retention_preview
from seekbell.services.retention import HistoryRetention
from sqlalchemy import text

from tests.history_helpers import seed_history
from tests.runtime_helpers import PassiveRuntime
from tests.test_management import authenticate


@pytest.fixture
def web(tmp_path):
    settings = Settings(data_dir=tmp_path, static_dir=tmp_path / "static")
    app = create_app(settings, runtime_factory=PassiveRuntime)
    with TestClient(app) as client:
        authenticate(client)
        yield client, app, settings


def test_general_save_is_atomic_and_conflicts_with_both_editors(web):
    client, _, _ = web
    original = client.get("/api/manage/preferences").json()
    changed = {
        key: original[key]
        for key in ("name", "description", "timezone", "workspace_revision", "display_revision")
    }
    changed.update(name="New space", timezone="Asia/Tokyo")
    result = client.put("/api/manage/preferences", json=changed)
    assert result.status_code == 200
    assert result.json()["workspace_revision"] == original["workspace_revision"] + 1
    assert result.json()["display_revision"] == original["display_revision"] + 1
    assert client.put("/api/manage/preferences", json=changed).status_code == 409
    assert client.get("/api/manage/preferences").json() == result.json()
    display = client.get("/api/manage/display").json()
    assert (
        client.put(
            "/api/manage/display", json={"timezone": "UTC", "revision": display["revision"]}
        ).status_code
        == 200
    )
    stale = {key: result.json()[key] for key in changed}
    stale.update(name="Must not save")
    assert client.put("/api/manage/preferences", json=stale).status_code == 409
    latest = client.get("/api/manage/preferences").json()
    assert latest["name"] == "New space" and latest["timezone"] == "UTC"
    invalid = {key: latest[key] for key in changed}
    invalid.update(timezone="Invalid/Zone", name="Must not save")
    assert client.put("/api/manage/preferences", json=invalid).status_code == 422
    assert client.get("/api/manage/preferences").json() == latest
    assert (
        client.put(
            "/api/manage/workspace", json={"name": "Legacy change", "description": ""}
        ).status_code
        == 200
    )
    assert (
        client.put("/api/manage/preferences", json={**invalid, "timezone": "UTC"}).status_code
        == 409
    )


def test_revoke_other_sessions_keeps_current_and_requires_csrf(web):
    client, app, _ = web
    other = TestClient(app)
    authenticate(other, setup=False)
    assert client.get("/api/auth/sessions").json()["other_sessions"] == 1
    assert (
        client.delete("/api/auth/sessions/others", headers={"X-CSRF-Token": ""}).status_code == 403
    )
    assert other.get("/api/manage/workspace").status_code == 200
    assert client.delete("/api/auth/sessions/others").json()["revoked"] == 1
    assert other.get("/api/manage/workspace").status_code == 401
    assert client.get("/api/auth/sessions").json()["other_sessions"] == 0
    assert client.get("/api/manage/workspace").status_code == 200
    other.close()


def test_preview_matches_cleaner_and_preserves_all_ledgers(web):
    _, app, settings = web
    ids = seed_history(app.state.engine, app.state.vault)
    at = ids["base"] + 40 * 86400
    before = table_data(settings.database_path)
    preview = retention_preview(app.state.engine, 30, at=at)
    assert table_data(settings.database_path) == before
    assert preview["counts"]["deliveries"] == 3
    assert preview["counts"]["posts"] == 6
    assert preview["protected_posts"] > 0
    result = HistoryRetention(app.state.engine).run_once(at=at)
    for name in preview["counts"]:
        assert preview["counts"][name] == result["counts"][name]
    after = table_data(settings.database_path)
    for name in ("seen_posts", "delivered_posts", "source_items"):
        assert after[name] == before[name]


def test_storage_and_diagnostics_are_readonly_and_exclude_credentials(web):
    client, _, settings = web
    before = table_data(settings.database_path)
    storage = client.get("/api/manage/storage")
    assert storage.status_code == 200
    assert storage.json()["database_bytes"] > 0
    assert storage.json()["filesystem_free_bytes"] > 0
    assert client.get("/api/manage/retention/preview?days=0").status_code == 422
    assert client.get("/api/manage/retention/preview?days=1.5").status_code == 422
    assert client.get("/api/manage/retention/preview?days=30").status_code == 200
    diagnostics = client.get("/api/manage/diagnostics")
    assert diagnostics.status_code == 200
    assert set(diagnostics.json()) == {
        "application",
        "version",
        "build_revision",
        "database_revision",
        "runtime",
        "supported_websites",
        "fault_codes",
        "checked_at",
    }
    assert [row["id"] for row in diagnostics.json()["supported_websites"]] == [
        "nodeseek",
        "linuxdo",
    ]
    assert str(settings.data_dir) not in diagnostics.text
    assert "csrf" not in diagnostics.text and "password" not in diagnostics.text
    assert table_data(settings.database_path) == before


def test_backup_receipts_are_bounded_and_nonsecret(web):
    _, app, _ = web
    for index in range(55):
        record_backup(app.state.engine, "export", "generated", archive_bytes=index)
    rows = backup_records(app.state.engine)
    assert len(rows) == 50
    assert rows[0]["archive_bytes"] == 54
    assert rows[-1]["archive_bytes"] == 5
    assert set(rows[0]) == {
        "id",
        "kind",
        "result",
        "at",
        "archive_bytes",
        "application_version",
        "database_revision",
    }
    assert "password" not in json.dumps(rows)


def test_upgrade_preserves_preferences_and_uses_expected_head(tmp_path):
    settings = Settings(data_dir=tmp_path)
    engine = create_database_engine(settings)
    migrate(engine, "0017_hotlist_settings")
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE workspace_preferences SET name='Existing', "
                "description='Keep', timezone='Asia/Tokyo'"
            )
        )
    migrate(engine)
    assert schema_revision(engine) == "0018_settings_maintenance"
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT name, description, timezone, workspace_revision FROM workspace_preferences"
            )
        ).one() == ("Existing", "Keep", "Asia/Tokyo", 1)
        assert connection.execute(text("SELECT COUNT(*) FROM backup_records")).scalar_one() == 0
    engine.dispose()
