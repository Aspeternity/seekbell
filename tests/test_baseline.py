import os
import sqlite3
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest
from alembic import command
from alembic.util.exc import CommandError
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.runtime import (
    create_database_engine,
    instance_lock,
    migrate,
    migration_config,
    schema_revision,
)
from seekbell.main import create_app
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def settings_for(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        static_dir=tmp_path / "static",
        build_revision="test-revision",
    )


def test_health_version_and_restart(tmp_path):
    settings = settings_for(tmp_path)
    app = create_app(settings)
    assert not settings.database_path.exists()
    for _ in range(2):
        with TestClient(app) as client:
            assert client.get("/health/live").json() == {"status": "ok"}
            assert client.get("/health/ready").status_code == 200
            assert client.get("/api/version").json() == {
                "name": "SeekBell",
                "version": version("seekbell"),
                "build_revision": "test-revision",
                "database_revision": "0001_installation",
            }
    assert settings.database_path.is_file()


def test_static_assets_and_unknown_api(tmp_path):
    settings = settings_for(tmp_path)
    settings.static_dir.mkdir()
    (settings.static_dir / "index.html").write_text("<h1>SeekBell</h1>")
    (settings.static_dir / "app.js").write_text("console.log('asset')")
    with TestClient(create_app(settings)) as client:
        assert "SeekBell" in client.get("/").text
        assert client.get("/app.js").status_code == 200
        assert client.get("/api/nonexistent").status_code == 404
        assert client.get("/missing.js").status_code == 404
        assert client.get("/seekbell.sqlite3").status_code == 404
        assert client.get("/%2e%2e/data/seekbell.sqlite3").status_code == 404


def test_backend_only_keeps_api_available(tmp_path):
    with TestClient(create_app(settings_for(tmp_path))) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/version").status_code == 200


def test_migrations_are_idempotent_and_match_models(tmp_path):
    settings = settings_for(tmp_path)
    with instance_lock(settings.data_dir):
        engine = create_database_engine(settings)
        try:
            migrate(engine)
            with engine.connect() as connection:
                installed = connection.execute(text("SELECT * FROM installation")).all()
                assert len(installed) == 1
                assert connection.scalar(text("PRAGMA journal_mode")) == "wal"
                assert connection.scalar(text("PRAGMA foreign_keys")) == 1
                assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
            migrate(engine)
            assert schema_revision(engine) == "0001_installation"
            with engine.begin() as connection:
                assert connection.execute(text("SELECT * FROM installation")).all() == installed
                config = migration_config()
                config.attributes["connection"] = connection
                command.check(config)
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text("INSERT INTO installation (id) VALUES (2)"))
        finally:
            engine.dispose()


def test_same_directory_cannot_start_second_process(tmp_path):
    with instance_lock(tmp_path):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from pathlib import Path; from seekbell.db.runtime import instance_lock; "
                "import sys; "
                "\nwith instance_lock(Path(sys.argv[1])): pass",
                str(tmp_path),
            ],
            text=True,
            capture_output=True,
            timeout=15,
        )
        assert result.returncode != 0
        assert "Another SeekBell process" in result.stderr
    # The descriptor lock is released after shutdown, without deleting a lock file.
    with instance_lock(tmp_path):
        pass


def test_separate_data_directories_are_independent(tmp_path):
    with (
        TestClient(create_app(settings_for(tmp_path / "one"))) as first,
        TestClient(create_app(settings_for(tmp_path / "two"))) as second,
    ):
        assert first.get("/health/ready").status_code == 200
        assert second.get("/health/ready").status_code == 200


def test_invalid_migration_stops_startup_and_releases_lock(tmp_path):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)):
        pass
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("UPDATE alembic_version SET version_num='unknown_revision'")
    with pytest.raises(CommandError, match="unknown_revision"), TestClient(create_app(settings)):
        pytest.fail("Migration failure must not serve requests")
    with sqlite3.connect(settings.database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "unknown_revision",
        )
    with instance_lock(settings.data_dir):
        pass


def test_database_failure_changes_readiness_not_liveness(tmp_path):
    app = create_app(settings_for(tmp_path))
    with TestClient(app) as client:
        with app.state.engine.begin() as connection:
            connection.execute(text("DROP TABLE installation"))
        assert client.get("/health/ready").status_code == 503
        assert client.get("/health/ready").json() == {"status": "unavailable"}
        assert client.get("/health/live").status_code == 200


@pytest.mark.parametrize("action", ["upgrade", "current", "check"])
def test_database_maintenance_commands(tmp_path, action):
    settings = settings_for(tmp_path)
    with TestClient(create_app(settings)):
        pass
    result = subprocess.run(
        [sys.executable, "-m", "seekbell.db", action],
        env={**os.environ, "SEEKBELL_DATA_DIR": str(settings.data_dir)},
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    if action == "current":
        assert result.stdout.strip() == "0001_installation"
