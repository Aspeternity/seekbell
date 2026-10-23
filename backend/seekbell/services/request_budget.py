"""A persistent host budget shared by Linux DO monitoring, probes and hotlists."""

import asyncio
import time
from contextlib import asynccontextmanager

import httpx
from sqlalchemy.orm import Session

from seekbell.db.models import WebsiteRequestState
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.errors import SourceDeferred, SourceFailure

REQUEST_GAP = 2


def request_state(session, website_id, now):
    row = session.get(WebsiteRequestState, website_id) if website_id == "linuxdo" else None
    if row is None:
        return 0, None
    return max(row.next_request_at, row.blocked_until), (
        row.error_code if row.blocked_until > now else None
    )


class WebsiteRequestBudget:
    def __init__(self, engine, *, clock=time.time):
        self.engine, self.clock = engine, clock
        self.lock = asyncio.Lock()

    def reserve(self, now):
        with write_session(self.engine) as session:
            row = session.get(WebsiteRequestState, "linuxdo")
            until, code = request_state(session, "linuxdo", now)
            if until <= now:
                row.next_request_at = now + REQUEST_GAP
            return until, code

    def failed(self, error, now):
        with write_session(self.engine) as session:
            row = session.get(WebsiteRequestState, "linuxdo")
            row.failures = min(6, row.failures + 1)
            minimum = 300 if error.code in ("http_403", "access_challenge") else 30
            delay = max(
                min(1800, minimum * 2 ** (row.failures - 1)),
                min(86400, error.retry_after or 0),
            )
            row.blocked_until = max(row.blocked_until, now + delay)
            row.error_code = error.code

    def succeeded(self):
        with write_session(self.engine) as session:
            row = session.get(WebsiteRequestState, "linuxdo")
            row.blocked_until, row.failures, row.error_code = 0, 0, None

    @asynccontextmanager
    async def request(self, website_id):
        if website_id != "linuxdo":
            yield
            return
        if self.lock.locked():
            raise SourceDeferred(self.clock() + REQUEST_GAP, "source_busy")
        async with self.lock:
            until, code = await database_call(self.reserve, self.clock())
            if until > self.clock():
                raise SourceDeferred(until, code or "source_cooldown")
            try:
                yield
            except (SourceFailure, httpx.HTTPError, TimeoutError) as error:
                if not isinstance(error, SourceFailure):
                    error = SourceFailure(
                        "timeout"
                        if isinstance(error, (TimeoutError, httpx.TimeoutException))
                        else "transport_error"
                    )
                if error.code in (
                    "access_challenge",
                    "http_403",
                    "http_429",
                    "timeout",
                    "transport_error",
                    "http_500",
                    "http_502",
                    "http_503",
                    "http_504",
                ):
                    await database_call(self.failed, error, self.clock())
                raise
            else:
                await database_call(self.succeeded)

    def view(self, website_id):
        with Session(self.engine) as session:
            return request_state(session, website_id, self.clock())
