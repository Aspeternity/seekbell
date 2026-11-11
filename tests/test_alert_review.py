"""Alert review: new-install delay, recoveries and reminders only for told targets,
readable messages, the last-alert summary and recorded loop stalls."""

import asyncio

import pytest
from seekbell.config import Settings
from seekbell.db.models import AlertDelivery, SystemEvent, SystemState
from seekbell.db.runtime import create_database_engine, migrate
from seekbell.db.transactions import write_session
from seekbell.domain.delivery import SendResult
from seekbell.notifiers.rendering import format_duration, render, telegram_message
from seekbell.services.alerts import AlertWorker, get_settings, observe, update_settings
from seekbell.services.operations import problem_detail, status
from seekbell.services.stalls import LOOP_STALL_SECONDS, PREFIX, StallWatch
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.test_display_alerts import Probe, app, configured, count, fault  # noqa: F401
from tests.test_management import target
from tests.test_operations_status import AT, QUIET_HOTLISTS, running
from tests.test_settings_reorganization import recover

CONFIG = {"include_summary": False}
DISK = "runtime:disk"


def disk(engine, faulty, at):
    with write_session(engine) as session:
        observe(
            session,
            DISK,
            faulty,
            label="数据磁盘",
            code="disk_space_low" if faulty else None,
            at=at,
        )


def send_all(engine, at, probe):
    worker = AlertWorker(engine, {"webhook": probe}, clock=lambda: at)
    while asyncio.run(worker.run_once()):
        pass
    return [message for _, message in probe.calls]


def remind(engine, at):
    return asyncio.run(AlertWorker(engine, {}, clock=lambda: at).remind())


def recipients(engine, phase):
    with Session(engine) as session:
        return sorted(
            session.scalars(
                select(AlertDelivery.target_id).join(SystemEvent).where(SystemEvent.phase == phase)
            )
        )


def test_new_installs_wait_a_minute_and_upgrades_keep_their_delay(tmp_path):
    for name in ("fresh", "old"):
        (tmp_path / name).mkdir()
    fresh = create_database_engine(Settings(data_dir=tmp_path / "fresh"))
    migrate(fresh)
    assert get_settings(fresh)["delay_seconds"] == 60
    assert get_settings(fresh)["remind_seconds"] == 0
    old = create_database_engine(Settings(data_dir=tmp_path / "old"))
    migrate(old, "0022_content_limit")
    with old.begin() as connection:
        connection.execute(
            text("INSERT INTO administrators(id, username, password_hash) VALUES(1, 'a', 'x')")
        )
    migrate(old)
    assert get_settings(old)["delay_seconds"] == 0
    # One fault and one recovery per generation still; reminders may repeat.
    insert = text("INSERT INTO system_events VALUES(:id, 'runtime:disk', 1, :phase, 'x', NULL, 1)")
    with old.begin() as connection:
        connection.execute(
            text("INSERT INTO system_states VALUES('runtime:disk', 1, 1, 'x', NULL, 1)")
        )
        for key, phase in (("a", "fault"), ("b", "reminder"), ("c", "reminder")):
            connection.execute(insert, {"id": key, "phase": phase})
    with pytest.raises(IntegrityError), old.begin() as connection:
        connection.execute(insert, {"id": "d", "phase": "fault"})


def test_recovery_goes_only_to_targets_that_heard_the_fault(configured):  # noqa: F811
    server, client, key = configured
    engine = server.state.engine
    fault(engine, at=100)
    later = target(client, name="Second webhook", enabled=True)
    saved = get_settings(engine)
    update_settings(engine, True, [key, later], saved["revision"])
    recover(engine, at=200)
    assert recipients(engine, "recovery") == [key]
    fault(engine, at=300)
    assert recipients(engine, "fault") == sorted([key, key, later])


def test_unresolved_fault_is_repeated_only_to_told_targets_at_the_chosen_interval(configured):  # noqa: F811
    server, client, key = configured
    engine = server.state.engine
    saved = client.get("/api/manage/alerts").json()
    body = {"enabled": True, "target_ids": [key], "delay_seconds": 0, "revision": saved["revision"]}
    assert (
        client.put("/api/manage/alerts", json={**body, "remind_seconds": 3600}).status_code == 422
    )
    result = client.put("/api/manage/alerts", json={**body, "remind_seconds": 21600})
    assert result.status_code == 200 and result.json()["remind_seconds"] == 21600

    disk(engine, True, at=100)
    probe = Probe()
    assert [m["alert"]["phase"] for m in send_all(engine, 100, probe)] == ["fault"]
    assert remind(engine, 100 + 21599) == 0
    assert remind(engine, 100 + 21600) == 1
    # The interval restarts from the reminder just queued.
    assert remind(engine, 100 + 21600 + 60) == 0
    reminder = send_all(engine, 100 + 21600, probe)[-1]
    assert reminder["alert"]["phase"] == "reminder"
    assert reminder["alert"]["duration_seconds"] == 21600
    assert reminder["alert"]["started_at"] == 100
    message = render(reminder, CONFIG)
    assert "故障仍未恢复：数据磁盘" in message and "已持续：6 小时" in message
    assert "原因：磁盘可用空间不足 500 MiB" in message and "开始时间：" in message

    disk(engine, False, at=100 + 30000)
    recovery = send_all(engine, 100 + 30000, probe)[-1]
    assert recovery["alert"]["phase"] == "recovery"
    text_ = render(recovery, CONFIG)
    assert "状态：已恢复" in text_ and "持续：8 小时 20 分钟" in text_
    assert "诊断代码" not in text_ and "recovered" not in text_
    assert "持续：8 小时 20 分钟" in telegram_message(recovery, CONFIG)["text"]

    with Session(engine) as session:
        fault_id = session.scalar(
            select(SystemEvent.id).where(
                SystemEvent.component == DISK, SystemEvent.phase == "fault"
            )
        )
    detail = problem_detail(engine, fault_id, [], at=100 + 30001)
    assert [row["phase"] for row in detail["alerts"]] == ["fault", "reminder", "recovery"]


def test_no_reminder_when_off_untold_or_the_object_is_paused(configured):  # noqa: F811
    server, _, key = configured
    engine = server.state.engine
    disk(engine, True, at=100)
    send_all(engine, 100, Probe())
    assert remind(engine, 100 + 86400) == 0  # reminders are off by default
    saved = get_settings(engine)
    update_settings(engine, True, [key], saved["revision"], remind_seconds=86400)
    # The source is not in use (no website enabled), so it cannot recover: never repeat it.
    fault(engine, at=100)
    send_all(engine, 100, Probe())
    assert remind(engine, 100 + 86400) == 1
    assert count(engine, SystemEvent) == 3
    with Session(engine) as session:
        event = session.scalars(select(SystemEvent).where(SystemEvent.phase == "reminder")).one()
        assert event.component == DISK


def test_fault_message_explains_the_code_and_test_failures_are_explained(configured):  # noqa: F811
    server, client, key = configured
    engine = server.state.engine
    fault(engine, at=100, code="http_503")
    message = send_all(engine, 100, Probe())[0]
    assert message["alert"]["summary"] and message["alert"]["duration_seconds"] is None
    rendered = render(message, CONFIG)
    assert "原因：" + message["alert"]["summary"] in rendered and "诊断代码：http_503" in rendered

    class Rejecting:
        async def send(self, snapshot, message):
            return SendResult(status="permanent_error", code="target_credentials_invalid")

    server.state.alert_notifiers = {"webhook": Rejecting()}
    row = client.post("/api/manage/alerts/test", json={"target_ids": [key]}).json()["items"][0]
    assert row["result"] == "permanent_error" and row["summary"] == "目标配置无法解密或已失效"


def test_durations_read_naturally():
    assert format_duration(30) == "不到 1 分钟"
    assert format_duration(300) == "5 分钟"
    assert format_duration(3600) == "1 小时"
    assert format_duration(90061) == "1 天 1 小时"


def test_a_stalled_loop_is_recorded_alerted_cleared_and_reset_on_restart(configured):  # noqa: F811
    server, _, _ = configured
    engine = server.state.engine
    now = [AT]
    observed = running()
    watch = StallWatch(engine, lambda: observed, clock=lambda: now[0])
    asyncio.run(watch.check())
    assert count(engine, SystemEvent) == 0

    observed["actors"]["delivery"]["last_loop_at"] = AT - LOOP_STALL_SECONDS - 1
    asyncio.run(watch.check())
    asyncio.run(watch.check())  # an unchanged verdict writes nothing new
    with Session(engine) as session:
        state = session.get(SystemState, PREFIX + "delivery")
        assert state.fault and state.code == "loop_stalled" and state.label == "投递服务"
    assert count(engine, SystemEvent) == count(engine, AlertDelivery) == 1
    message = send_all(engine, AT, Probe())[0]
    assert message["alert"]["summary"] == "后台循环长时间未完成"
    problem = next(row for row in status(engine, observed, QUIET_HOTLISTS, at=AT)["problems"])
    assert problem["kind"] == "stall" and problem["event_id"] is not None

    # A restarted process starts from scratch and clears what the previous one left.
    observed["actors"]["delivery"]["last_loop_at"] = AT - 1
    asyncio.run(StallWatch(engine, lambda: observed, clock=lambda: now[0]).check())
    with Session(engine) as session:
        assert not session.get(SystemState, PREFIX + "delivery").fault
    assert [m["alert"]["phase"] for m in send_all(engine, AT, Probe())] == ["recovery"]
