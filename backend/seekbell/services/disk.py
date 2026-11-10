"""Raise one fault while the data directory's filesystem is nearly full."""

import logging
import shutil
import time
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from seekbell.db.models import Administrator, SystemState
from seekbell.db.transactions import write_session
from seekbell.services.alerts import observe

logger = logging.getLogger(__name__)
COMPONENT = "runtime:disk"
CODE = "disk_space_low"
LABEL = "数据磁盘"
# Warn while there is still room to write the warning; clear only after real headroom returns.
LOW_BYTES = 500 * 1024**2
RECOVERED_BYTES = 600 * 1024**2


class DiskWatch:
    def __init__(self, engine, *, usage=shutil.disk_usage, clock=time.time, interval=60):
        database = engine.url.database
        self.directory = Path(database).parent if database and database != ":memory:" else None
        self.engine, self.usage, self.clock, self.interval = engine, usage, clock, interval
        self.next_at = 0

    def run_once(self, *, at=None):
        at = self.clock() if at is None else at
        if self.directory is None or at < self.next_at:
            return None
        self.next_at = at + self.interval
        try:
            free = self.usage(self.directory).free
            with Session(self.engine) as session:
                if session.get(Administrator, 1) is None:
                    return None
                state = session.get(SystemState, COMPONENT)
                known = bool(state and state.fault)
            low = free < (RECOVERED_BYTES if known else LOW_BYTES)
            if low != known:
                with write_session(self.engine) as session:
                    observe(session, COMPONENT, low, label=LABEL, code=CODE if low else None, at=at)
            return low
        except (OSError, SQLAlchemyError):
            # A full disk can refuse the very write that reports it; the next check retries.
            logger.error("SeekBell disk space check could not be completed")
            return None
