"""Read-only facts for the operations center: no network access and no writes."""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from seekbell.db.models import (
    AlertDelivery,
    AlertSettings,
    DeliveryAttempt,
    HotlistSnapshot,
    NotificationTarget,
    Outbox,
    Source,
    SourceProbe,
    SourceRun,
    SourceState,
    SystemEvent,
    SystemState,
    TargetTestAttempt,
    Website,
    WebsiteInstallation,
)
from seekbell.services.alerts import object_active
from seekbell.services.backup_schedule import COMPONENT as BACKUP_COMPONENT
from seekbell.services.disk import COMPONENT as DISK_COMPONENT
from seekbell.services.fault_guide import (
    ACTION,
    AUTO,
    guide_for,
    guide_view,
    runtime_guide,
    source_guide,
)
from seekbell.services.history import read_session
from seekbell.services.hotlist_settings import configuration
from seekbell.services.overview_preferences import hotlist_catalog
from seekbell.services.request_budget import request_state
from seekbell.services.source_probe import next_source_attempt, probe_backoff
from seekbell.services.stalls import PREFIX as STALL_PREFIX
from seekbell.services.stalls import stalled
from seekbell.sites.hotlists import HOTLIST_SOURCES

VERIFYING = "verifying"
GAP_WINDOW_SECONDS = 7 * 86400
SHORT_PROBLEM_SECONDS = 60
PROBLEM_KINDS = ("source", "delivery", "runtime")
SERVICES = {
    "collection": "采集",
    "delivery": "投递",
    "retention": "历史清理",
    "alerts": "系统告警",
}
SEVERITY = {"none": 0, "ok": 0, "wait": 1, "warn": 2, "fail": 3}
STATUS_ORDER = {ACTION: 0, AUTO: 1, VERIFYING: 2}
OPEN_OUTBOX = ("pending", "retry")
UNCERTAIN_OUTBOX = ("pending", "retry", "leased", "failed")
RESULT_LABELS = {
    "success": ("ok", "成功"),
    "transient_error": ("warn", "暂时失败"),
    "permanent_error": ("fail", "失败"),
    "unknown": ("warn", "结果不确定"),
    "in_progress": ("wait", "发送中"),
}


class MissingProblem(LookupError):
    pass


def node(state, tone, label, detail=None, at=None):
    return {"state": state, "tone": tone, "label": label, "detail": detail, "at": at}


DASH = node("none", "none", "—")
NO_RECORD = node("no_record", "none", "尚无记录")
NO_INPUT = node("no_input", "none", "无新输入")


def _schedule_node(session, website_id, source, state, enabled, active, at):
    if not enabled:
        return node("paused", "none", "已暂停")
    if not active:
        return node("stopped", "fail", "后台已停止")
    if state.last_attempt_at is None:
        return node("first", "wait", "待首次采集")
    until, code = request_state(session, website_id, at)
    if code and until > at:
        return node("limited", "wait", "来源受限", "解除于", until)
    probed = probe_backoff(session.get(SourceProbe, source.id))
    if probed > at:
        return node("limited", "wait", "测试后退避", "解除于", probed)
    return node("scheduled", "ok", "正常")


def _parse_detail(run):
    if run is None:
        return None
    issues = len(run.diagnostics or [])
    return f"{run.raw_count} 条" + (f"，异常 {issues} 项" if issues else "")


def _round_node(run):
    if run is None or run.status != "success":
        return NO_RECORD
    if run.code == "baseline":
        return node("baseline", "ok", "完成", "基线轮，不发送")
    if not run.new_posts:
        return node("done", "ok", "完成", "本轮无新帖")
    parts = [f"新帖 {run.new_posts}", f"命中 {run.hit_count}", f"入队 {run.queued_count}"]
    if run.insufficient_count:
        parts.append(f"信息不足 {run.insufficient_count}")
    return node("done", "ok", "完成", " · ".join(parts))


def _source_nodes(state, run, enabled, active):
    if not enabled or not active:
        return DASH, DASH, DASH
    if state.last_attempt_at is None:
        return NO_RECORD, NO_RECORD, NO_RECORD
    code = state.last_error_code if state.failures else None
    fetched = node("ok", "ok", "正常", None, state.last_success_at)
    if code is None:
        return fetched, node("ok", "ok", "正常", _parse_detail(run)), _round_node(run)
    failed = node("failed", "fail", "失败", code)
    if source_guide(code).stage == "parse":
        return fetched, failed, NO_INPUT
    return failed, NO_INPUT, NO_INPUT


def _sources(session, active, at):
    rows = []
    for website, source, state in session.execute(
        select(Website, Source, SourceState)
        .join(WebsiteInstallation, WebsiteInstallation.website_id == Website.id)
        .join(Source, Source.website_id == Website.id)
        .join(SourceState, SourceState.source_id == Source.id)
        .order_by(WebsiteInstallation.position, Website.id, Source.id)
    ):
        enabled = website.enabled and source.enabled
        run = session.scalars(
            select(SourceRun)
            .where(SourceRun.source_id == source.id)
            .order_by(SourceRun.id.desc())
            .limit(1)
        ).first()
        fetch, parse, latest = _source_nodes(state, run, enabled, active)
        gap = state.last_gap_at
        rows.append(
            {
                "website_id": website.id,
                "source_id": source.id,
                "name": website.name,
                "enabled": enabled,
                "schedule": _schedule_node(session, website.id, source, state, enabled, active, at),
                "fetch": fetch,
                "parse": parse,
                "latest": latest,
                "last_success_at": state.last_success_at,
                "next_attempt_at": (
                    next_source_attempt(session, state, website.id, at)
                    if enabled and active
                    else None
                ),
                "gap_at": gap if gap is not None and at - gap <= GAP_WINDOW_SECONDS else None,
            }
        )
    return rows


def _targets(session, at):
    queues, sending, expired = {}, {}, {}
    for target_id, status, count, earliest in session.execute(
        select(Outbox.target_id, Outbox.status, func.count(), func.min(Outbox.available_at))
        .where(Outbox.status.in_(OPEN_OUTBOX))
        .group_by(Outbox.target_id, Outbox.status)
    ):
        queue = queues.setdefault(target_id, {"pending": 0, "retry": 0, "earliest_at": None})
        queue[status] = count
        queue["earliest_at"] = min(
            value for value in (queue["earliest_at"], earliest) if value is not None
        )
    for target_id, lease_until in session.execute(
        select(Outbox.target_id, Outbox.lease_until).where(Outbox.status == "leased")
    ):
        bucket = sending if lease_until > at else expired
        bucket[target_id] = bucket.get(target_id, 0) + 1
    uncertain = dict(
        session.execute(
            select(Outbox.target_id, func.count())
            .where(Outbox.uncertain.is_(True), Outbox.status.in_(UNCERTAIN_OUTBOX))
            .group_by(Outbox.target_id)
        ).all()
    )
    newest = (
        select(func.max(DeliveryAttempt.id).label("id"))
        .join(Outbox, Outbox.id == DeliveryAttempt.event_id)
        .where(DeliveryAttempt.finished_at.is_not(None))
        .group_by(Outbox.target_id)
        .subquery()
    )
    latest = {
        target_id: attempt
        for target_id, attempt in session.execute(
            select(Outbox.target_id, DeliveryAttempt)
            .join(Outbox, Outbox.id == DeliveryAttempt.event_id)
            .join(newest, newest.c.id == DeliveryAttempt.id)
        )
    }
    rows = []
    for target in session.scalars(
        select(NotificationTarget)
        .where(NotificationTarget.deleted_at.is_(None), NotificationTarget.kind != "mock")
        .order_by(NotificationTarget.name, NotificationTarget.id)
    ):
        attempt = latest.get(target.id)
        rows.append(
            {
                "id": target.id,
                "name": target.name,
                "kind": target.kind,
                "status": (
                    "unconfigured"
                    if not target.config_ciphertext
                    else "enabled"
                    if target.enabled
                    else "paused"
                ),
                "queue": queues.get(target.id, {"pending": 0, "retry": 0, "earliest_at": None}),
                "sending": sending.get(target.id, 0),
                "expired_leases": expired.get(target.id, 0),
                "uncertain": uncertain.get(target.id, 0),
                "last": (
                    {
                        "result": attempt.result,
                        "code": attempt.error_code,
                        "at": attempt.finished_at,
                    }
                    if attempt is not None
                    else None
                ),
            }
        )
    return rows


def _hotlist_node(period_id, memory, fetched, interval, viewing, source, at):
    if memory is None:
        return node("no_record", "none", "本次启动后尚无记录")
    code = memory["error_code"]
    if memory["refreshing"]:
        return node("refreshing", "ok", "刷新中", None, fetched)
    if code == "collection_priority":
        return node("waiting", "wait", "采集优先", "下次", memory["next_attempt_at"])
    if memory["deferred"] or code in ("source_busy", "source_cooldown"):
        return node("waiting", "wait", "共享退避", "下次", memory["next_attempt_at"])
    if memory["failures"] and code:
        if fetched is None:
            return node("failed", "fail", "刷新失败，暂无数据", code)
        return node("stale", "warn", "刷新失败，旧数据仍可看", code, fetched)
    if not viewing:
        return node("idle", "none", "无人查看，暂停刷新", None, fetched)
    if fetched is None:
        return node("no_record", "none", "尚无快照")
    if period_id in source.staggered and at >= fetched + interval:
        return node("staggered", "wait", "正常错开", None, fetched)
    return node("ok", "ok", "正常", None, fetched)


def _hotlists(session, engine, observed, at):
    visible = dict(hotlist_catalog(engine))
    fetched = {
        (row.website_id, row.provider_id, row.period): row.fetched_at
        for row in session.scalars(select(HotlistSnapshot))
    }
    sites = []
    for installation, website in session.execute(
        select(WebsiteInstallation, Website)
        .join(Website, Website.id == WebsiteInstallation.website_id)
        .order_by(WebsiteInstallation.position, Website.id)
    ):
        source = HOTLIST_SOURCES.get(website.id)
        if source is None or website.id not in visible:
            continue
        policy = configuration(website.id, installation.hotlist_settings)
        lists = []
        for period in policy["periods"]:
            key = website.id, source.provider_id, period["id"]
            lists.append(
                {
                    "period": period["id"],
                    "period_label": period["label"],
                    **_hotlist_node(
                        period["id"],
                        observed["lists"].get(key),
                        fetched.get(key),
                        period["interval_seconds"],
                        observed["viewing"],
                        source,
                        at,
                    ),
                }
            )
        sites.append({"website_id": website.id, "name": website.name, "lists": lists})
    return sites


def _services(observed, at):
    failed = (observed["code"] or "").removesuffix("_stopped")
    if observed["status"] != "failed":
        failed = ""
    rows = []
    for name, label in SERVICES.items():
        actor = observed["actors"].get(name)
        row = {"id": name, "name": label, "last_loop_at": actor and actor["last_loop_at"]}
        if actor is None:
            row["state"] = "unknown"
        elif name == failed:
            row["state"] = "failed"
        elif not actor["alive"]:
            row.update(state="stopped_with", stopped_with=SERVICES.get(failed))
        elif stalled(actor, observed["started_at"], at):
            row["state"] = "stalled"
        else:
            row["state"] = "running"
        rows.append(row)
    return rows


def _source_handling(session, key, guide, at):
    source, state = session.get(Source, key), session.get(SourceState, key)
    return {
        "status": guide.handling,
        "hint": None,
        "next_attempt_at": next_source_attempt(session, state, source.website_id, at),
        "failures": state.failures,
    }


def _delivery_handling(session, key, guide, since):
    """`observe` only clears a fault on the next real success, so judge the rest here."""
    target = session.get(NotificationTarget, key)
    outcome = {"status": VERIFYING, "next_attempt_at": None, "failures": None}
    tested = session.scalar(
        select(func.max(TargetTestAttempt.finished_at)).where(
            TargetTestAttempt.target_id == key,
            TargetTestAttempt.result == "success",
            TargetTestAttempt.finished_at >= since,
        )
    )
    if tested is not None:
        return {**outcome, "hint": "目标测试已通过，下次真实发送成功后恢复"}
    revision = session.scalar(
        select(Outbox.target_snapshot["revision"].as_integer())
        .join(DeliveryAttempt, DeliveryAttempt.event_id == Outbox.id)
        .where(Outbox.target_id == key)
        .order_by(DeliveryAttempt.id.desc())
        .limit(1)
    )
    if revision is not None and revision < target.revision:
        return {**outcome, "hint": "配置已在故障后修改，下次真实发送成功后恢复"}
    if guide.handling == ACTION:
        return {
            **outcome,
            "status": ACTION,
            "hint": "修改目标配置后，下次发送成功时恢复",
        }
    earliest = session.scalar(
        select(func.min(Outbox.available_at)).where(
            Outbox.target_id == key, Outbox.status.in_(OPEN_OUTBOX)
        )
    )
    if earliest is None:
        return {**outcome, "hint": "已没有待重试的消息，下次发送成功后恢复"}
    return {**outcome, "status": AUTO, "hint": None, "next_attempt_at": earliest}


def _handling(session, kind, key, guide, since, at):
    if kind == "source":
        return _source_handling(session, key, guide, at)
    if kind == "delivery":
        return _delivery_handling(session, key, guide, since)
    return {"status": ACTION, "hint": None, "next_attempt_at": None, "failures": None}


def _fault_event_id(session, component, generation):
    return session.scalar(
        select(SystemEvent.id).where(
            SystemEvent.component == component,
            SystemEvent.generation == generation,
            SystemEvent.phase == "fault",
        )
    )


def _open_fault_id(session, component):
    state = session.get(SystemState, component)
    if state is None or not state.fault:
        return None
    return _fault_event_id(session, component, state.generation)


def _runtime_problems(session, observed, at):
    if observed["status"] == "failed":
        code = observed["code"]
        name = (code or "").removesuffix("_stopped")
        component = "runtime:" + name
        state = session.get(SystemState, component)
        guide = runtime_guide(code)
        return [
            {
                "key": component,
                "kind": "runtime",
                "event_id": _fault_event_id(session, component, state.generation)
                if state is not None
                else None,
                "label": SERVICES.get(name, name) + "服务",
                "code": code,
                "stage": guide.stage,
                "summary": guide.summary,
                "since": state.updated_at if state is not None else observed["started_at"],
                "status": ACTION,
                "hint": "重启容器后恢复",
                "next_attempt_at": None,
                "failures": None,
                "guide": guide_view(guide),
            }
        ]
    guide = runtime_guide("loop_stalled")
    return [
        {
            "key": "stall:" + name,
            "kind": "stall",
            # Set once the stall watch has recorded it (within its check interval).
            "event_id": _open_fault_id(session, STALL_PREFIX + name),
            "label": SERVICES.get(name, name) + "服务",
            "code": "loop_stalled",
            "stage": guide.stage,
            "summary": guide.summary,
            "since": actor["last_loop_at"] or observed["started_at"],
            "status": ACTION,
            "hint": None,
            "next_attempt_at": None,
            "failures": None,
            "guide": guide_view(guide),
        }
        for name, actor in observed["actors"].items()
        if stalled(actor, observed["started_at"], at)
    ]


# Storage faults raised outside the background actors, with how each one clears.
STORAGE_HINTS = {
    DISK_COMPONENT: "释放磁盘空间后自动恢复",
    BACKUP_COMPONENT: "下次备份成功后自动恢复",
}


def _storage_problems(session):
    problems = []
    for component, hint in STORAGE_HINTS.items():
        state = session.get(SystemState, component)
        if state is None or not state.fault:
            continue
        guide = runtime_guide(state.code)
        problems.append(
            {
                "key": state.component,
                "kind": "runtime",
                "event_id": _fault_event_id(session, state.component, state.generation),
                "label": state.label,
                "code": state.code,
                "stage": guide.stage,
                "summary": guide.summary,
                "since": state.updated_at,
                "status": ACTION,
                "hint": hint,
                "next_attempt_at": None,
                "failures": None,
                "guide": guide_view(guide),
            }
        )
    return problems


def _problems(session, observed, at):
    # Storage faults are reported even when the background has stopped: they may be the cause.
    problems = _runtime_problems(session, observed, at) + _storage_problems(session)
    # A stopped background is the single root cause; older faults cannot retry meanwhile.
    if observed["active"]:
        for state in session.scalars(select(SystemState).where(SystemState.fault.is_(True))):
            kind, _, key = state.component.partition(":")
            if kind not in ("source", "delivery") or not object_active(session, kind, key):
                continue
            guide = guide_for(kind, state.code)
            problems.append(
                {
                    "key": state.component,
                    "kind": kind,
                    "event_id": _fault_event_id(session, state.component, state.generation),
                    "label": state.label,
                    "code": state.code,
                    "stage": guide.stage,
                    "summary": guide.summary,
                    "since": state.updated_at,
                    "guide": guide_view(guide),
                    **_handling(session, kind, key, guide, state.updated_at, at),
                }
            )
    return sorted(problems, key=lambda row: (STATUS_ORDER[row["status"]], -(row["since"] or 0)))


def _alerts(session):
    settings = session.get(AlertSettings, 1)
    ready = 0
    for key in settings.target_ids:
        target = session.get(NotificationTarget, key)
        if target and target.deleted_at is None and target.enabled and target.config_ciphertext:
            ready += 1
    return {"enabled": settings.enabled, "ready_targets": ready}


def status(engine, observed, hotlists, *, at):
    with read_session(engine) as session:
        return {
            "checked_at": at,
            "runtime": {
                "active": observed["active"],
                "status": observed["status"],
                "code": observed["code"],
            },
            "problems": _problems(session, observed, at),
            "sources": _sources(session, observed["active"], at),
            "targets": _targets(session, at),
            "hotlists": _hotlists(session, engine, hotlists, at),
            "services": _services(observed, at),
            "alerts": _alerts(session),
        }


def _problem_state(session, fault, recovery, kind, key):
    if recovery is not None:
        return "recovered"
    state = session.get(SystemState, fault.component)
    if state is None or not state.fault or state.generation != fault.generation:
        return "recovered"
    return "ongoing" if object_active(session, kind, key) else "paused"


def _recovery_of(fault_alias):
    recovery = aliased(SystemEvent)
    return recovery, and_(
        recovery.component == fault_alias.component,
        recovery.generation == fault_alias.generation,
        recovery.phase == "recovery",
    )


def problem_history(engine, *, at, kind="", days=7, show_short=False, page=1, page_size=20):
    fault = aliased(SystemEvent)
    recovery, joined = _recovery_of(fault)
    kinds = [kind] if kind else PROBLEM_KINDS
    conditions = [
        fault.phase == "fault",
        fault.at >= at - days * 86400,
        or_(*(fault.component.startswith(item + ":", autoescape=True) for item in kinds)),
    ]
    if not show_short:
        conditions.append(
            or_(recovery.id.is_(None), recovery.at - fault.at >= SHORT_PROBLEM_SECONDS)
        )
    with read_session(engine) as session:
        total = session.scalar(
            select(func.count()).select_from(fault).outerjoin(recovery, joined).where(*conditions)
        )
        rows = session.execute(
            select(fault, recovery)
            .outerjoin(recovery, joined)
            .where(*conditions)
            .order_by(fault.at.desc(), fault.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        keys = [row[0].id for row in rows]
        results = {key: {} for key in keys}
        if keys:
            for key, result, count in session.execute(
                select(AlertDelivery.event_id, AlertDelivery.result, func.count())
                .where(AlertDelivery.event_id.in_(keys))
                .group_by(AlertDelivery.event_id, AlertDelivery.result)
            ):
                results[key][result] = count
        items = []
        for event, ended in rows:
            item_kind, _, key = event.component.partition(":")
            items.append(
                {
                    "id": event.id,
                    "kind": item_kind,
                    "label": event.label,
                    "code": event.code,
                    "summary": guide_for(item_kind, event.code).summary,
                    "status": _problem_state(session, event, ended, item_kind, key),
                    "started_at": event.at,
                    "ended_at": ended.at if ended is not None else None,
                    "alerts": results[event.id],
                }
            )
        return {"total": total, "page": page, "page_size": page_size, "items": items}


def _run_view(run):
    if run.status == "success":
        return {
            "at": run.at,
            "tone": "ok",
            "label": "成功",
            "text": f"{run.raw_count} 条 · 新帖 {run.new_posts} · 命中 {run.hit_count}",
        }
    return {"at": run.at, "tone": "fail", "label": "失败", "text": run.code or ""}


def _recent(session, kind, key, end):
    if kind == "source":
        runs = session.scalars(
            select(SourceRun)
            .where(SourceRun.source_id == key, SourceRun.at <= end)
            .order_by(SourceRun.id.desc())
            .limit(8)
        )
        return [_run_view(run) for run in runs]
    if kind == "delivery":
        attempts = session.scalars(
            select(DeliveryAttempt)
            .join(Outbox, Outbox.id == DeliveryAttempt.event_id)
            .where(Outbox.target_id == key, DeliveryAttempt.started_at <= end)
            .order_by(DeliveryAttempt.id.desc())
            .limit(8)
        )
        return [
            {
                "at": attempt.finished_at or attempt.started_at,
                "tone": RESULT_LABELS.get(attempt.result, ("none", attempt.result))[0],
                "label": RESULT_LABELS.get(attempt.result, ("none", attempt.result))[1],
                "text": attempt.error_code or "",
            }
            for attempt in attempts
        ]
    return []


def _alert_rows(session, events):
    rows = session.execute(
        select(AlertDelivery, SystemEvent.phase)
        .join(SystemEvent, SystemEvent.id == AlertDelivery.event_id)
        .where(SystemEvent.id.in_([event.id for event in events]))
        .order_by(SystemEvent.at, AlertDelivery.id)
        .limit(50)
    )
    return [
        {
            "phase": phase,
            "target_name": item.target_snapshot.get("name", ""),
            "kind": item.target_snapshot.get("kind"),
            "result": item.result,
            "error_code": item.error_code,
            "finished_at": item.finished_at,
        }
        for item, phase in rows
    ]


def _verification(session, kind, key, guide):
    if guide.verify is None:
        return None
    if kind == "source":
        source = session.get(Source, key)
        return {"kind": guide.verify, "website_id": source.website_id} if source else None
    if kind == "delivery":
        target = session.get(NotificationTarget, key)
        active = target is not None and target.deleted_at is None
        return {"kind": guide.verify, "target_id": key} if active else None
    return {"kind": guide.verify}


def _crash_near(crashes, name, at):
    nearby = [
        row
        for row in crashes
        if row.get("actor") == name
        and isinstance(row.get("at"), int | float)
        and abs(row["at"] - at) <= 60
    ]
    return min(nearby, key=lambda row: abs(row["at"] - at), default=None)


def problem_detail(engine, key, crashes, *, at):
    with read_session(engine) as session:
        fault = session.get(SystemEvent, key)
        if fault is None or fault.phase != "fault":
            raise MissingProblem("问题不存在或已清理。")
        kind, _, object_key = fault.component.partition(":")
        recovery = session.scalar(
            select(SystemEvent).where(
                SystemEvent.component == fault.component,
                SystemEvent.generation == fault.generation,
                SystemEvent.phase == "recovery",
            )
        )
        state = _problem_state(session, fault, recovery, kind, object_key)
        current = session.get(SystemState, fault.component)
        code = current.code if state == "ongoing" and current is not None else fault.code
        guide = guide_for(kind, code)
        end = recovery.at if recovery is not None else at
        handling = (
            _handling(session, kind, object_key, guide, fault.at, at) if state == "ongoing" else {}
        )
        failures = None
        if kind == "source":
            failures = session.scalar(
                select(func.count())
                .select_from(SourceRun)
                .where(
                    SourceRun.source_id == object_key,
                    SourceRun.status == "failure",
                    SourceRun.at >= fault.at,
                    SourceRun.at <= end,
                )
            )
        return {
            "id": fault.id,
            "kind": kind,
            "label": fault.label,
            "status": state,
            "handling": handling.get("status"),
            "hint": handling.get("hint"),
            "next_attempt_at": handling.get("next_attempt_at"),
            "first_code": fault.code,
            "code": code,
            "started_at": fault.at,
            "ended_at": recovery.at if recovery is not None else None,
            "failures": failures,
            "guide": guide_view(guide),
            "recent": _recent(session, kind, object_key, end),
            # Fault, any reminders and the recovery of this one problem.
            "alerts": _alert_rows(
                session,
                session.scalars(
                    select(SystemEvent).where(
                        SystemEvent.component == fault.component,
                        SystemEvent.generation == fault.generation,
                    )
                ).all(),
            ),
            "verify": _verification(session, kind, object_key, guide),
            "crash": _crash_near(crashes, object_key, fault.at) if kind == "runtime" else None,
        }
