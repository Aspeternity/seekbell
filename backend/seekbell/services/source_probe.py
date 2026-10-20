"""Explicit checks have their own cooldown, sharing only network exclusion and error backoff."""

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from seekbell.db.models import Source, SourceProbe, SourceState, WebsiteInstallation
from seekbell.db.transactions import database_call, write_session
from seekbell.domain.delivery import SourcePolicy
from seekbell.domain.errors import SourceFailure
from seekbell.sites.nodeseek import BUILTIN_ADAPTERS

TEST_COOLDOWN_SECONDS = 2


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
            result["next_attempt_at"] = test_due(session.get(SourceState, source.id), probe)
        return result


def probe_due(probe):
    if probe is None:
        return 0
    # A successful legacy probe may store the old monitor interval. Only real
    # failures retain that saved backoff; normal tests use their own cooldown.
    return max(
        probe.next_attempt_at if probe.status == "failure" else 0,
        (probe.finished_at if probe.finished_at is not None else probe.started_at)
        + TEST_COOLDOWN_SECONDS,
    )


def probe_backoff(probe):
    return probe.next_attempt_at if probe is not None and probe.status == "failure" else 0


def test_due(state, probe):
    return max(state.next_attempt_at if state.failures else 0, probe_due(probe))


def reserve(engine, source_id, at):
    with write_session(engine) as session:
        source = session.get(Source, source_id)
        if source is None or session.get(WebsiteInstallation, source.website_id) is None:
            raise ProbeConflict("请先添加内置网站。")
        state = session.get(SourceState, source_id)
        probe = session.get(SourceProbe, source_id)
        next_at = test_due(state, probe)
        if at < next_at:
            delay = next_at - at
            reason = "连接测试操作过于频繁"
            if (
                state.failures
                and state.last_error_code
                and state.next_attempt_at >= probe_due(probe)
            ):
                reason = f"最近采集失败（{state.last_error_code}），来源正在退避"
            elif probe and probe.status == "failure" and probe.code:
                reason = f"最近连接测试失败（{probe.code}），来源正在退避"
            raise ProbeConflict(f"{reason}；约 {math.ceil(delay)} 秒后可再次测试。", delay)
        if probe is None:
            probe = SourceProbe(source_id=source_id)
            session.add(probe)
        probe.started_at, probe.finished_at = at, None
        probe.next_attempt_at = at + TEST_COOLDOWN_SECONDS
        # A crash/cancelled request leaves honest evidence, never a false success.
        probe.status, probe.code, probe.item_count = "unknown", "check_not_completed", None
        return source.website_id, source.url


def finish(engine, source_id, at, *, count=None, error=None):
    with write_session(engine) as session:
        probe = session.get(SourceProbe, source_id)
        probe.finished_at = at
        probe.next_attempt_at = max(probe.next_attempt_at, at + TEST_COOLDOWN_SECONDS)
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
