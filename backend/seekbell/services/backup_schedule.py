"""Automatic backups into the library at a daily or weekly slot in the display timezone.

The schedule lives in the database; the backups themselves and therefore "when was the
last backup" live in the library directory. One fault component reports a failed
automatic backup, or no backup for more than two periods."""

import asyncio
import logging
import sqlite3
import time
from contextlib import suppress
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from seekbell import backup
from seekbell.db.models import Administrator, BackupSchedule, SystemState, WorkspacePreferences
from seekbell.db.transactions import database_call, write_session
from seekbell.services import backups
from seekbell.services.alerts import observe

logger = logging.getLogger(__name__)
COMPONENT = "runtime:backup"
LABEL = "自动备份"
FAILED = "backup_failed"
OVERDUE = "backup_overdue"
PERIODS = {"daily": 86400, "weekly": 7 * 86400}
# A failed run is retried hourly until the next regular slot.
RETRY_SECONDS = 3600
# Without a schedule the page still turns orange after this long, but raises no fault.
STALE_SECONDS = 30 * 86400
# Kinds that are a copy of the data as it is now; safety copies hold older data.
CURRENT_KINDS = ("manual", "auto")
SLOT_FIELDS = ("enabled", "frequency", "weekday", "minute")
FIELDS = (*SLOT_FIELDS, "keep")


class ScheduleConflict(ValueError):
    pass


def next_slot(frequency, weekday, minute, zone, after):
    """The first scheduled moment strictly after `after`, as UTC seconds."""
    tz = ZoneInfo(zone)
    day = datetime.fromtimestamp(after, tz).date()
    for offset in range(9):
        date = day + timedelta(days=offset)
        if frequency == "weekly" and date.weekday() != weekday:
            continue
        # A wall time skipped by a DST change maps to the instant just after the gap.
        moment = datetime(
            date.year, date.month, date.day, minute // 60, minute % 60, tzinfo=tz
        ).timestamp()
        if moment > after:
            return moment
    raise AssertionError("No slot within nine days")


def zone_of(session):
    return session.get(WorkspacePreferences, 1).timezone


def due_at(schedule, zone):
    if schedule.next_run_at is not None:
        return schedule.next_run_at
    return next_slot(schedule.frequency, schedule.weekday, schedule.minute, zone, schedule.since)


def schedule_view(schedule, zone):
    return {
        **{name: getattr(schedule, name) for name in FIELDS},
        "revision": schedule.revision,
        "timezone": zone,
        "next_run_at": due_at(schedule, zone) if schedule.enabled else None,
        "last_attempt_at": schedule.last_attempt_at,
        "last_error": schedule.last_error,
    }


def get_schedule(engine):
    with Session(engine) as session:
        return schedule_view(session.get(BackupSchedule, 1), zone_of(session))


def update_schedule(engine, values, revision, *, at=None):
    """Save the schedule; changing when it runs starts counting again from now."""
    at = time.time() if at is None else at
    with write_session(engine) as session:
        schedule = session.get(BackupSchedule, 1)
        if schedule.revision != revision:
            raise ScheduleConflict("自动备份设置已在其他页面改变，请重新读取后保存。")
        changed = {name for name in FIELDS if getattr(schedule, name) != values[name]}
        if changed:
            for name in changed:
                setattr(schedule, name, values[name])
            schedule.revision += 1
        if changed & set(SLOT_FIELDS):
            schedule.next_run_at, schedule.since = None, at
            if not schedule.enabled:
                schedule.last_error = None
        return schedule_view(schedule, zone_of(session))


def last_backup_at(rows):
    times = [row["at"] for row in rows if row["valid"] and row["kind"] in CURRENT_KINDS]
    return max(times, default=None)


def overdue(schedule, last, at):
    if not schedule.enabled:
        return False
    return at - max(last or 0, schedule.since) > 2 * PERIODS[schedule.frequency]


def health(engine, rows, *, at=None):
    """protected, overdue, failed or none: the colour of the backup status card."""
    at = time.time() if at is None else at
    with Session(engine) as session:
        schedule = session.get(BackupSchedule, 1)
        last = last_backup_at(rows)
        if schedule.enabled and schedule.last_error:
            return "failed"
        if overdue(schedule, last, at):
            return "overdue"
        if last is None:
            return "none"
        if not schedule.enabled and at - last > STALE_SECONDS:
            return "overdue"
        return "protected"


class BackupScheduler:
    """One in-process actor; it never waits for the backup gate, it tries again later."""

    def __init__(self, engine, settings, gate, *, clock=time.time, tick=60):
        self.engine, self.settings, self.gate = engine, settings, gate
        self.clock, self.tick = clock, tick
        self.stop = asyncio.Event()
        self.task = None

    def start(self):
        self.task = asyncio.create_task(self.run(self.stop), name="seekbell-backup")

    async def aclose(self):
        self.stop.set()
        if self.task is not None:
            await asyncio.gather(self.task, return_exceptions=True)

    async def run(self, stop):
        while not stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.error("SeekBell automatic backup check could not be completed")
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.tick)

    async def run_once(self, *, at=None):
        at = self.clock() if at is None else at
        due = await database_call(self._due, at)
        if due is None:
            return None
        result = "idle"
        if due:
            if self.gate.locked():
                return "busy"
            await self.gate.acquire()
            try:
                result = await database_call(self._backup, at)
            finally:
                self.gate.release()
        await database_call(self._observe, at)
        return result

    def _due(self, at):
        with Session(self.engine) as session:
            if session.get(Administrator, 1) is None:
                return None
            schedule = session.get(BackupSchedule, 1)
            return schedule.enabled and at >= due_at(schedule, zone_of(session))

    def _backup(self, at):
        with Session(self.engine) as session:
            schedule = session.get(BackupSchedule, 1)
            keep, zone, revision = schedule.keep, zone_of(session), schedule.revision
            slot = (schedule.frequency, schedule.weekday, schedule.minute)
        error = None
        try:
            backups.create(self.settings, "auto", at=at, keep=keep)
        except backup.BackupError as failure:
            error = str(failure)[:200]
        except (OSError, RuntimeError, ValueError, KeyError, sqlite3.Error, SQLAlchemyError):
            error = "备份写入失败，请检查磁盘空间和备份目录权限。"
        following = next_slot(*slot, zone, at)
        with write_session(self.engine) as session:
            schedule = session.get(BackupSchedule, 1)
            schedule.last_attempt_at, schedule.last_error = at, error
            # A schedule saved meanwhile has already restarted its own count.
            if schedule.revision == revision:
                retry = following if error is None else min(following, at + RETRY_SECONDS)
                schedule.next_run_at = retry
        if error is not None:
            logger.error("SeekBell automatic backup failed")
        return "failed" if error else "created"

    def _observe(self, at):
        with Session(self.engine) as session:
            schedule = session.get(BackupSchedule, 1)
            state = session.get(SystemState, COMPONENT)
            current = state.code if state and state.fault else None
            if not schedule.enabled:
                wanted = None
            elif schedule.last_error:
                wanted = FAILED
            elif overdue(schedule, last_backup_at(backups.entries(self.settings)), at):
                wanted = OVERDUE
            else:
                wanted = None
        if wanted != current:
            with write_session(self.engine) as session:
                observe(session, COMPONENT, wanted is not None, label=LABEL, code=wanted, at=at)
        return wanted
