import asyncio
import sqlite3
import time
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from seekbell import backup
from seekbell.config import Settings
from seekbell.db.models import BackupSchedule, SystemEvent, SystemState, WorkspacePreferences
from seekbell.db.runtime import create_database_engine, migrate
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services import backup_schedule as schedule_service
from seekbell.services import backups as library
from seekbell.services.authentication import initialize, password_hash
from seekbell.services.backup_demo import prepare
from seekbell.services.backup_schedule import (
    COMPONENT,
    FAILED,
    OVERDUE,
    BackupScheduler,
    next_slot,
)
from seekbell.services.operations import _storage_problems
from sqlalchemy import select
from sqlalchemy.orm import Session

SHANGHAI = ZoneInfo("Asia/Shanghai")


def local(*parts, zone=SHANGHAI):
    return datetime(*parts, tzinfo=zone).timestamp()


@pytest.fixture
def workspace(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    prepare(settings)
    engine = create_database_engine(settings)
    with write_session(engine) as session:
        session.get(WorkspacePreferences, 1).timezone = "Asia/Shanghai"
    yield settings, engine
    engine.dispose()


def configure(engine, **values):
    with write_session(engine) as session:
        schedule = session.get(BackupSchedule, 1)
        for name, value in values.items():
            setattr(schedule, name, value)


def schedule_row(engine):
    with Session(engine) as session:
        schedule = session.get(BackupSchedule, 1)
        session.expunge(schedule)
        return schedule


def fault(engine):
    with Session(engine) as session:
        state = session.get(SystemState, COMPONENT)
        return state.code if state and state.fault else None


def run(scheduler, at):
    return asyncio.run(scheduler.run_once(at=at))


def automatic(settings):
    return [row for row in library.entries(settings) if row["kind"] == "auto"]


def test_next_slot_follows_the_display_timezone_daily_and_weekly():
    # 2026-11-10 is a Tuesday.
    tuesday_noon = local(2026, 11, 10, 12, 0)
    assert next_slot("daily", 0, 180, "Asia/Shanghai", tuesday_noon) == local(2026, 11, 11, 3, 0)
    assert next_slot("daily", 0, 780, "Asia/Shanghai", tuesday_noon) == local(2026, 11, 10, 13, 0)
    # Exactly at the slot means the following one.
    at_slot = local(2026, 11, 11, 3, 0)
    assert next_slot("daily", 0, 180, "Asia/Shanghai", at_slot) == local(2026, 11, 12, 3, 0)
    assert next_slot("weekly", 0, 180, "Asia/Shanghai", tuesday_noon) == local(2026, 11, 16, 3, 0)
    assert next_slot("weekly", 1, 780, "Asia/Shanghai", tuesday_noon) == local(2026, 11, 10, 13, 0)
    assert next_slot("weekly", 1, 180, "Asia/Shanghai", tuesday_noon) == local(2026, 11, 17, 3, 0)


def test_next_slot_survives_daylight_saving_changes():
    berlin = ZoneInfo("Europe/Berlin")
    # 2026-03-29 02:30 does not exist in Berlin; the run still happens that night.
    before = local(2026, 3, 28, 12, 0, zone=berlin)
    slot = next_slot("daily", 0, 150, "Europe/Berlin", before)
    assert local(2026, 3, 29, 1, 0, zone=berlin) < slot < local(2026, 3, 29, 4, 0, zone=berlin)
    # 2026-10-25 02:30 happens twice; only one run.
    first = next_slot("daily", 0, 150, "Europe/Berlin", local(2026, 10, 24, 12, 0, zone=berlin))
    following = next_slot("daily", 0, 150, "Europe/Berlin", first)
    assert following - first > 23 * 3600


def test_new_schedule_waits_for_the_next_slot_then_catches_up_once(workspace):
    settings, engine = workspace
    since = local(2026, 11, 10, 12, 0)
    configure(engine, since=since)
    scheduler = BackupScheduler(engine, settings, asyncio.Lock())
    assert run(scheduler, since + 60) == "idle"
    assert automatic(settings) == []
    # The container was off at 03:00 and for two more days: one catch-up, not three.
    late = local(2026, 11, 13, 9, 0)
    assert run(scheduler, late) == "created"
    assert run(scheduler, late + 60) == "idle"
    rows = automatic(settings)
    assert len(rows) == 1 and rows[0]["at"] == late
    row = schedule_row(engine)
    assert row.next_run_at == local(2026, 11, 14, 3, 0)
    assert row.last_attempt_at == late and row.last_error is None
    view = schedule_service.get_schedule(engine)
    assert view["next_run_at"] == local(2026, 11, 14, 3, 0)


def test_automatic_backups_keep_the_newest_and_never_touch_manual_ones(workspace):
    settings, engine = workspace
    start = local(2026, 11, 1, 12, 0)
    configure(engine, since=start, keep=3)
    library.create(settings, "manual", at=start)
    scheduler = BackupScheduler(engine, settings, asyncio.Lock())
    for day in range(2, 8):
        assert run(scheduler, local(2026, 11, day, 3, 0)) == "created"
    kept = automatic(settings)
    assert [row["at"] for row in kept] == [local(2026, 11, day, 3, 0) for day in (7, 6, 5)]
    assert [row["kind"] for row in library.entries(settings)].count("manual") == 1


def test_a_busy_gate_postpones_without_waiting(workspace):
    settings, engine = workspace
    configure(engine, since=local(2026, 11, 10, 12, 0))
    gate = asyncio.Lock()
    scheduler = BackupScheduler(engine, settings, gate)

    async def scenario():
        await gate.acquire()
        busy = await scheduler.run_once(at=local(2026, 11, 11, 3, 0))
        gate.release()
        return busy, await scheduler.run_once(at=local(2026, 11, 11, 3, 1))

    assert asyncio.run(scenario()) == ("busy", "created")


def test_failure_raises_one_fault_retries_hourly_and_recovers(workspace, monkeypatch):
    settings, engine = workspace
    configure(engine, since=local(2026, 11, 10, 12, 0))
    scheduler = BackupScheduler(engine, settings, asyncio.Lock())
    real = library.create

    def full(*args, **kwargs):
        raise backup.BackupError("磁盘可用空间不足，无法生成备份；请先清理空间或删除旧备份。")

    monkeypatch.setattr(library, "create", full)
    first = local(2026, 11, 11, 3, 0)
    assert run(scheduler, first) == "failed"
    assert fault(engine) == FAILED
    with Session(engine) as session:
        (problem,) = _storage_problems(session)
    assert problem["key"] == COMPONENT and problem["label"] == "自动备份"
    assert problem["guide"]["summary"] == "自动备份失败"
    row = schedule_row(engine)
    assert row.next_run_at == first + 3600 and row.last_error.startswith("磁盘可用空间不足")
    assert schedule_service.health(engine, library.entries(settings), at=first) == "failed"
    assert run(scheduler, first + 1800) == "idle"
    assert run(scheduler, first + 3600) == "failed"
    monkeypatch.setattr(library, "create", real)
    assert run(scheduler, first + 7200) == "created"
    assert fault(engine) is None
    with Session(engine) as session:
        phases = session.scalars(
            select(SystemEvent.phase).where(SystemEvent.component == COMPONENT)
        ).all()
    assert sorted(phases) == ["fault", "recovery"]
    with Session(engine) as session:
        assert _storage_problems(session) == []


def test_overdue_after_two_periods_without_a_current_backup(workspace):
    settings, engine = workspace
    since = local(2026, 11, 1, 12, 0)
    configure(engine, since=since, next_run_at=local(2026, 12, 1, 3, 0))
    scheduler = BackupScheduler(engine, settings, asyncio.Lock())
    assert run(scheduler, since + 2 * 86400 - 60) == "idle"
    assert fault(engine) is None
    assert run(scheduler, since + 2 * 86400 + 60) == "idle"
    assert fault(engine) == OVERDUE
    rows = library.entries(settings)
    assert schedule_service.health(engine, rows, at=since + 2 * 86400 + 60) == "overdue"
    # A pre-restore copy holds older data and does not count; a manual backup does.
    library.create(settings, "pre-restore", at=since + 3 * 86400)
    run(scheduler, since + 3 * 86400 + 60)
    assert fault(engine) == OVERDUE
    library.create(settings, "manual", at=since + 3 * 86400 + 120)
    run(scheduler, since + 3 * 86400 + 180)
    assert fault(engine) is None
    rows = library.entries(settings)
    assert schedule_service.health(engine, rows, at=since + 3 * 86400 + 180) == "protected"


def test_disabling_clears_faults_and_saving_restarts_the_count(workspace):
    settings, engine = workspace
    configure(engine, since=local(2026, 11, 1, 12, 0), last_error="失败")
    scheduler = BackupScheduler(engine, settings, asyncio.Lock())
    run(scheduler, local(2026, 11, 1, 13, 0))
    assert fault(engine) == FAILED
    values = {"enabled": False, "frequency": "weekly", "weekday": 6, "minute": 90, "keep": 4}
    saved_at = local(2026, 11, 1, 14, 0)
    view = schedule_service.update_schedule(engine, values, 1, at=saved_at)
    assert view["revision"] == 2 and view["next_run_at"] is None and view["last_error"] is None
    run(scheduler, saved_at + 60)
    assert fault(engine) is None
    with pytest.raises(schedule_service.ScheduleConflict):
        schedule_service.update_schedule(engine, values, 1)
    view = schedule_service.update_schedule(engine, {**values, "enabled": True}, 2, at=saved_at)
    # Sunday 01:30 after the save.
    assert view["next_run_at"] == local(2026, 11, 8, 1, 30)
    # Changing only how many to keep does not move the next run.
    configure(engine, next_run_at=local(2026, 11, 8, 1, 30))
    view = schedule_service.update_schedule(engine, {**values, "enabled": True, "keep": 9}, 3)
    assert view["next_run_at"] == local(2026, 11, 8, 1, 30) and view["keep"] == 9


def test_uninitialized_workspace_is_never_backed_up(tmp_path):
    settings = Settings(data_dir=tmp_path / "fresh")
    settings.data_dir.mkdir(mode=0o700)
    app = create_app(settings)
    with TestClient(app):
        engine = app.state.engine
        configure(engine, since=local(2026, 11, 1, 12, 0))
        scheduler = BackupScheduler(engine, settings, asyncio.Lock())
        assert run(scheduler, local(2026, 11, 5, 3, 0)) is None
        assert library.entries(settings) == []


def test_restored_data_counts_its_schedule_from_the_restore(workspace, tmp_path):
    settings, engine = workspace
    configure(engine, next_run_at=1.0, last_error="旧错误", keep=5)
    archive = tmp_path / "old.tar.gz"
    backup.create_backup(settings, archive)
    destination = tmp_path / "restored"
    backup.restore_backup(
        settings,
        archive,
        destination,
        administrator=("someone", password_hash("Synthetic-Restore-Password")),
    )
    with closing(sqlite3.connect(destination / "seekbell.sqlite3")) as connection:
        row = connection.execute(
            "SELECT keep, next_run_at, last_error, last_attempt_at, since FROM backup_schedule"
        ).fetchone()
    assert row[:4] == (5, None, None, None) and row[4] > 1


def test_status_and_schedule_api(tmp_path):
    settings = Settings(data_dir=tmp_path / "source")
    token, _ = prepare(settings)
    app = create_app(settings)
    with TestClient(app) as client:
        client.cookies.set("seekbell_session", token)
        client.headers["x-csrf-token"] = client.get("/api/auth/status").json()["csrf"]
        result = client.get("/api/manage/backups").json()
        assert result["health"] == "none"
        schedule = result["schedule"]
        assert {k: schedule[k] for k in ("enabled", "frequency", "minute", "keep")} == {
            "enabled": True,
            "frequency": "daily",
            "minute": 180,
            "keep": 7,
        }
        assert schedule["next_run_at"] > 0
        values = {"enabled": True, "frequency": "weekly", "weekday": 2, "minute": 600, "keep": 3}
        saved = client.put(
            "/api/manage/backups/schedule", json={**values, "revision": schedule["revision"]}
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["frequency"] == "weekly" and saved.json()["revision"] == 2
        read = client.get("/api/manage/backups/schedule").json()
        assert read == saved.json() and read["timezone"] == "America/Los_Angeles"
        stale = client.put("/api/manage/backups/schedule", json={**values, "revision": 1})
        assert stale.status_code == 409
        for bad in ({"minute": 1440}, {"keep": 0}, {"frequency": "hourly"}, {"weekday": 7}):
            response = client.put(
                "/api/manage/backups/schedule", json={**values, **bad, "revision": 2}
            )
            assert response.status_code == 422
        assert client.post("/api/manage/backups").status_code == 200
        assert client.get("/api/manage/backups").json()["health"] == "protected"


def test_schedule_counts_from_the_first_administrator(tmp_path):
    settings = Settings(data_dir=tmp_path / "fresh")
    settings.data_dir.mkdir(mode=0o700)
    engine = create_database_engine(settings)
    try:
        migrate(engine)
        configure(engine, since=1.0)
        before = time.time()
        initialize(engine, "first_admin", "Synthetic-First-Admin-2026", timezone="Asia/Shanghai")
        row = schedule_row(engine)
        assert row.since >= before and row.next_run_at is None
        scheduler = BackupScheduler(engine, settings, asyncio.Lock())
        assert run(scheduler, row.since + 60) == "idle"
        assert fault(engine) is None
    finally:
        engine.dispose()
