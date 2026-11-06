"""Persistent per-site automatic backoff and bounded manual connection checks."""

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager

import httpx
from sqlalchemy.orm import Session

from seekbell.db.models import WebsiteRequestState
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.errors import SourceDeferred, SourceFailure

REQUEST_GAP = 2
MANUAL_RETRY_GAP = 60
# Linux DO challenged bursts of three requests within 6-13 seconds. Hotlists stay below
# that: at most two requests in any window, unviewed lists well apart from any request.
BURST_WINDOW = 15
BURST_LIMIT = 2
BACKGROUND_GAP = 30
MAX_RETRY_AFTER = 86400
SITE_FAILURES = (
    "access_challenge",
    "http_403",
    "http_429",
    "timeout",
    "transport_error",
    "http_500",
    "http_502",
    "http_503",
    "http_504",
)
# Signals that the origin limits this address as a whole, whichever path was read.
ORIGIN_FAILURES = ("access_challenge", "http_429")


def retry_delay(code, failures):
    if code in ("http_403", "access_challenge"):
        base, maximum = 300, 600
    elif code == "http_429":
        base, maximum = 60, 600
    else:
        base, maximum = 30, 300
    return min(maximum, base * 2 ** min(5, max(0, failures - 1)))


def request_state(session, website_id, now, *, manual=False):
    row = session.get(WebsiteRequestState, website_id) if website_id == "linuxdo" else None
    if row is None:
        return 0, None
    if manual:
        until = max(row.next_request_at, row.next_manual_at, row.retry_after_until)
        code = (
            "server_retry_after"
            if row.retry_after_until > now and row.retry_after_until == until
            else "manual_cooldown"
            if row.next_manual_at > now
            else "source_cooldown"
        )
    else:
        until = max(row.next_request_at, row.blocked_until, row.retry_after_until)
        code = row.error_code if until > now else None
    return until, code


class WebsiteRequestBudget:
    def __init__(self, engine, *, clock=time.time):
        self.engine, self.clock = engine, clock
        self.lock = asyncio.Lock()
        self.sent = deque(maxlen=BURST_LIMIT)

    def pace(self, website_id, *, background=False, collection_soon=False):
        """When a hotlist read may be sent; every other request is only counted."""
        if website_id != "linuxdo":
            return 0
        now = self.clock()
        recent = [at for at in self.sent if now - at < BURST_WINDOW]
        excess = len(recent) + collection_soon - (BURST_LIMIT - 1)
        until = recent[excess - 1] + BURST_WINDOW if excess > 0 else 0
        if background and self.sent:
            until = max(until, self.sent[-1] + BACKGROUND_GAP)
        return until

    def reserve(self, now, *, manual=False):
        with write_session(self.engine) as session:
            row = session.get(WebsiteRequestState, "linuxdo")
            until, code = request_state(session, "linuxdo", now, manual=manual)
            if until <= now:
                row.next_request_at = now + REQUEST_GAP
                if manual:
                    row.next_manual_at = now + MANUAL_RETRY_GAP
            return until, code

    def failed(self, error, now):
        with write_session(self.engine) as session:
            row = session.get(WebsiteRequestState, "linuxdo")
            row.failures = min(6, row.failures + 1)
            if error.retry_after:
                row.retry_after_until = max(
                    row.retry_after_until, now + min(MAX_RETRY_AFTER, error.retry_after)
                )
            row.blocked_until = max(
                row.blocked_until,
                now + retry_delay(error.code, row.failures),
                row.retry_after_until,
            )
            row.error_code = error.code

    def succeeded(self):
        with write_session(self.engine) as session:
            row = session.get(WebsiteRequestState, "linuxdo")
            row.blocked_until, row.failures, row.error_code = 0, 0, None
            row.retry_after_until = 0
            # Successful manual checks still keep their own persisted cooldown.

    @asynccontextmanager
    async def request(self, website_id, *, manual=False, auxiliary=False):
        """Serialize one site request; auxiliary reads share only origin-wide limits.

        An auxiliary read (a hotlist) neither clears the site's backoff on success nor
        extends it for path-local failures such as one feed's 403/5xx or a timeout.
        """
        if website_id != "linuxdo":
            yield
            return
        if self.lock.locked():
            raise SourceDeferred(self.clock() + REQUEST_GAP, "source_busy")
        async with self.lock:
            until, code = await database_call(self.reserve, self.clock(), manual=manual)
            if until > self.clock():
                raise SourceDeferred(until, code or "source_cooldown")
            self.sent.append(self.clock())
            try:
                yield
            except (SourceFailure, httpx.HTTPError, TimeoutError) as error:
                if not isinstance(error, SourceFailure):
                    error = SourceFailure(
                        "timeout"
                        if isinstance(error, (TimeoutError, httpx.TimeoutException))
                        else "transport_error"
                    )
                if error.code in SITE_FAILURES and (
                    not auxiliary or error.code in ORIGIN_FAILURES or error.retry_after
                ):
                    await database_call(self.failed, error, self.clock())
                raise
            else:
                if not auxiliary:
                    await database_call(self.succeeded)

    def view(self, website_id):
        with Session(self.engine) as session:
            return request_state(session, website_id, self.clock())
