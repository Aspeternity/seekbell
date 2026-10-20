"""Explicit checks share the collector lock and throttle, but never ingest posts."""

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from seekbell.db.models import Source, SourceProbe, SourceState, WebsiteInstallation
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.delivery import SourcePolicy
from seekbell.domain.errors import SourceFailure
from seekbell.sites.nodeseek import BUILTIN_ADAPTERS


class ProbeConflict(Exception):
    def __init__(self, message, retry_after=None):
        self.retry_after = math.ceil(retry_after) if retry_after is not None else None
        super().__init__(message)


def probe_view(probe):
    if probe is None:
        return None
    return {
        "started_at": probe.started_at,
        "finished_at": probe.finished_at,
        "next_attempt_at": probe.next_attempt_at,
        "status": probe.status,
        "code": probe.code,
        "item_count": probe.item_count,
    }


def get_probe(engine, website_id):
    with Session(engine) as session:
        source = session.scalar(select(Source).where(Source.website_id == website_id))
        if source is None or session.get(WebsiteInstallation, website_id) is None:
            raise ProbeConflict("请先添加内置网站。")
        probe = session.get(SourceProbe, source.id)
        result = probe_view(probe)
        if result:
            result["next_attempt_at"] = source_due(
                session.get(SourceState, source.id), source, probe
            )
        return result


def probe_due(probe, interval):
    if probe is None:
        return 0
    return max(probe.next_attempt_at, (probe.finished_at or probe.started_at) + interval)


def source_due(state, source, probe):
    return max(
        state.next_attempt_at,
        state.last_attempt_at + source.interval_seconds if state.last_attempt_at else 0,
        probe_due(probe, source.interval_seconds),
    )


def reserve(engine, source_id, at):
    with write_session(engine) as session:
        source = session.get(Source, source_id)
        if source is None or session.get(WebsiteInstallation, source.website_id) is None:
            raise ProbeConflict("请先添加内置网站。")
        state = session.get(SourceState, source_id)
        probe = session.get(SourceProbe, source_id)
        next_at = source_due(state, source, probe)
        if at < next_at:
            raise ProbeConflict("来源处于采集间隔或退避中，请稍后测试。", next_at - at)
        if probe is None:
            probe = SourceProbe(source_id=source_id)
            session.add(probe)
        probe.started_at, probe.finished_at = at, None
        probe.next_attempt_at = at + source.interval_seconds
        # A crash/cancelled request leaves honest evidence, never a false success.
        probe.status, probe.code, probe.item_count = "unknown", "check_not_completed", None
        return source.website_id, source.url


def finish(engine, source_id, at, *, count=None, error=None):
    with write_session(engine) as session:
        probe = session.get(SourceProbe, source_id)
        source = session.get(Source, source_id)
        probe.finished_at = at
        probe.next_attempt_at = max(probe.next_attempt_at, at + source.interval_seconds)
        if error:
            probe.status, probe.code, probe.item_count = "failure", error.code, None
            probe.next_attempt_at = max(
                probe.next_attempt_at, at + SourcePolicy().retry_delay(1, error.retry_after)
            )
        else:
            probe.status, probe.code, probe.item_count = "success", None, count
        return probe_view(probe)


async def check(runner):
    if runner._lock.locked():
        raise ProbeConflict("来源正在采集或测试，请稍后重试。")
    async with runner._lock:
        website_id, url = await database_call(
            reserve, runner.engine, runner.source_id, runner.clock()
        )
        try:
            adapter = BUILTIN_ADAPTERS.get(website_id)
            if adapter is None or url != adapter.rss_url:
                raise SourceFailure("unsupported_source")
            batch = await runner.fetch_batch(adapter)
        except SourceFailure as error:
            return await database_call(
                finish, runner.engine, runner.source_id, runner.clock(), error=error
            )
        return await database_call(
            finish, runner.engine, runner.source_id, runner.clock(), count=len(batch.posts)
        )
