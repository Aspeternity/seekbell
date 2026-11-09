"""Operations center read models; every source of truth here is synthetic and local."""

import asyncio
import json
import re
from pathlib import Path

import pytest
import seekbell
from fastapi.testclient import TestClient
from seekbell.config import Settings
from seekbell.db.models import (
    AlertDelivery,
    DeliveryAttempt,
    NotificationTarget,
    Outbox,
    SeenPost,
    SystemEvent,
    TargetTestAttempt,
    Website,
    WebsiteInstallation,
)
from seekbell.db.transactions import write_session
from seekbell.main import create_app
from seekbell.services.alerts import observe
from seekbell.services.crash_records import LIMIT, CrashRecords
from seekbell.services.fault_guide import (
    DELIVERY_OUTCOMES,
    DELIVERY_PREFIXES,
    delivery_guide,
    runtime_guide,
    source_guide,
)
from seekbell.services.operations import (
    LOOP_STALL_SECONDS,
    _hotlist_node,
    problem_detail,
    problem_history,
    status,
)
from seekbell.sites.hotlists import HOTLIST_SOURCES

from tests.hotlist_helpers import synthetic_hotlists
from tests.runtime_helpers import SyntheticScenario
from tests.test_management import authenticate
from tests.test_runtime import until

AT = 1_000_000.0
QUIET_HOTLISTS = {"viewing": False, "lists": {}}
SOURCE = "source:nodeseek-rss"


def running(**fields):
    actors = {
        name: {"alive": True, "last_loop_at": AT - 1}
        for name in ("collection", "delivery", "retention", "alerts")
    }
    return {
        "active": True,
        "status": "running",
        "code": None,
        "started_at": AT - 100,
        "actors": actors,
        "sources": {},
        **fields,
    }


def view(core, observed=None, at=AT):
    return status(core.engine, observed or running(), QUIET_HOTLISTS, at=at)


def only(rows):
    assert len(rows) == 1
    return rows[0]


def fault(core, component, code, *, at=AT - 60, label="合成对象"):
    with write_session(core.engine) as session:
        return observe(session, component, True, label=label, code=code, at=at)


def recover(core, component, *, at, label="合成对象"):
    with write_session(core.engine) as session:
        return observe(session, component, False, label=label, at=at)


@pytest.fixture
def site(core):
    with write_session(core.engine) as session:
        session.get(Website, "nodeseek").enabled = True
        if session.get(WebsiteInstallation, "nodeseek") is None:
            session.add(WebsiteInstallation(website_id="nodeseek", position=0))
    return core


def attempt(core, *, code="smtp_rejected", status_value="failed", available=AT + 60, revision=None):
    target_id = core.target
    with write_session(core.engine) as session:
        target = session.get(NotificationTarget, target_id)
        if session.get(SeenPost, ("nodeseek", "1")) is None:
            session.add(SeenPost(website_id="nodeseek", external_post_id="1", first_seen_at=AT))
            session.flush()
        event = Outbox(
            id="event-" + status_value,
            website_id="nodeseek",
            external_post_id="1",
            target_id=target_id,
            target_snapshot={"revision": revision or target.revision},
            payload={},
            status=status_value,
            attempt_count=1,
            available_at=available,
            created_at=AT - 70,
        )
        session.add(event)
        session.flush()
        session.add(
            DeliveryAttempt(
                event_id=event.id,
                sequence=1,
                lease_token="token-" + status_value,
                started_at=AT - 62,
                finished_at=AT - 60,
                result="permanent_error",
                error_code=code,
            )
        )


def test_source_failure_marks_fetch_and_clears_on_success(site):
    site.ingest(9001, at=AT - 300)
    site.ingestion.record_failure("nodeseek-rss", "timeout", at=AT - 30)
    data = view(site)
    problem = only(data["problems"])
    assert problem["status"] == "auto_retry" and problem["stage"] == "fetch"
    assert problem["summary"] == "连接超时" and problem["failures"] == 1
    assert problem["next_attempt_at"] > AT - 30
    row = only(data["sources"])
    assert row["schedule"]["label"] == "正常" and row["fetch"]["tone"] == "fail"
    assert row["parse"]["label"] == row["latest"]["label"] == "无新输入"

    site.ingest(9001, 9002, at=AT - 10)
    data = view(site)
    row = only(data["sources"])
    assert data["problems"] == [] and row["fetch"]["tone"] == "ok"
    assert row["latest"]["detail"].startswith("新帖 1")


def test_parse_failure_keeps_fetch_normal(site):
    site.ingest(9001, at=AT - 300)
    site.ingestion.record_failure("nodeseek-rss", "not_rss", at=AT - 30)
    row = only(view(site)["sources"])
    assert row["fetch"]["tone"] == "ok" and row["parse"]["tone"] == "fail"
    assert row["latest"]["label"] == "无新输入"


def test_untouched_site_is_not_reported_normal(site):
    row = only(view(site)["sources"])
    assert row["schedule"]["label"] == "待首次采集"
    assert {row[key]["label"] for key in ("fetch", "parse", "latest")} == {"尚无记录"}


def test_paused_site_fault_leaves_current_problems_but_stays_in_history(site):
    site.ingestion.record_failure("nodeseek-rss", "timeout", at=AT - 300)
    with write_session(site.engine) as session:
        session.get(Website, "nodeseek").enabled = False
    data = view(site)
    assert data["problems"] == []
    assert only(data["sources"])["schedule"]["label"] == "已暂停"
    row = only(problem_history(site.engine, at=AT)["items"])
    assert row["status"] == "paused" and row["ended_at"] is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [("smtp_rejected", "action"), ("target_credentials_invalid", "action")],
)
def test_permanent_delivery_fault_needs_action(core, code, expected):
    fault(core, "delivery:" + core.target, code)
    assert only(view(core)["problems"])["status"] == expected


def test_retrying_delivery_reports_next_attempt(core):
    attempt(core, code="smtp_retry", status_value="retry")
    fault(core, "delivery:" + core.target, "smtp_retry")
    problem = only(view(core)["problems"])
    assert problem["status"] == "auto_retry" and problem["next_attempt_at"] == AT + 60


def test_transient_delivery_without_queue_waits_for_next_send(core):
    attempt(core, code="smtp_retry")
    fault(core, "delivery:" + core.target, "smtp_retry")
    problem = only(view(core)["problems"])
    assert problem["status"] == "verifying" and "已没有待重试" in problem["hint"]


def test_fixed_target_waits_for_real_send_after_config_change(core):
    attempt(core)
    fault(core, "delivery:" + core.target, "smtp_rejected")
    with write_session(core.engine) as session:
        session.get(NotificationTarget, core.target).revision += 1
    problem = only(view(core)["problems"])
    assert problem["status"] == "verifying" and "配置已在故障后修改" in problem["hint"]


def test_passed_target_test_waits_for_real_send(core):
    fault(core, "delivery:" + core.target, "smtp_rejected")
    with write_session(core.engine) as session:
        session.add(
            TargetTestAttempt(
                id="test-1",
                target_id=core.target,
                target_snapshot={},
                started_at=AT - 20,
                finished_at=AT - 19,
                result="success",
            )
        )
    problem = only(view(core)["problems"])
    assert problem["status"] == "verifying" and "目标测试已通过" in problem["hint"]


def test_test_before_the_fault_does_not_count(core):
    with write_session(core.engine) as session:
        session.add(
            TargetTestAttempt(
                id="test-1",
                target_id=core.target,
                target_snapshot={},
                started_at=AT - 500,
                finished_at=AT - 499,
                result="success",
            )
        )
    fault(core, "delivery:" + core.target, "smtp_rejected")
    assert only(view(core)["problems"])["status"] == "action"


def test_paused_target_fault_is_not_current(core):
    fault(core, "delivery:" + core.target, "smtp_rejected")
    with write_session(core.engine) as session:
        session.get(NotificationTarget, core.target).enabled = False
    assert view(core)["problems"] == []


def test_stopped_runtime_is_the_single_root_cause(site):
    site.ingestion.record_failure("nodeseek-rss", "timeout", at=AT - 300)
    fault(site, "runtime:collection", "collection_stopped", at=AT - 30, label="采集服务")
    observed = running(active=False, status="failed", code="collection_stopped")
    observed["actors"]["collection"]["alive"] = False
    observed["actors"]["delivery"]["alive"] = False
    data = view(site, observed)
    problem = only(data["problems"])
    assert problem["key"] == "runtime:collection" and problem["since"] == AT - 30
    assert problem["status"] == "action" and problem["event_id"]
    row = only(data["sources"])
    assert row["schedule"]["label"] == "后台已停止" and row["next_attempt_at"] is None
    assert row["fetch"]["label"] == "—"
    services = {row["id"]: row for row in data["services"]}
    assert services["collection"]["state"] == "failed"
    assert services["delivery"]["state"] == "stopped_with"
    assert services["delivery"]["stopped_with"] == "采集"
    assert services["alerts"]["state"] == "running"


def test_stalled_loop_states_the_fact(core):
    observed = running()
    observed["actors"]["delivery"]["last_loop_at"] = AT - LOOP_STALL_SECONDS - 1
    data = view(core, observed)
    problem = only(data["problems"])
    assert problem["kind"] == "stall" and problem["event_id"] is None
    assert problem["since"] == AT - LOOP_STALL_SECONDS - 1 and problem["guide"]["known"]
    assert {row["id"]: row["state"] for row in data["services"]}["delivery"] == "stalled"


def test_target_row_separates_queue_lease_and_uncertain(core):
    attempt(core, code="send_timeout", status_value="retry")
    with write_session(core.engine) as session:
        target = session.get(NotificationTarget, core.target)
        target.kind, target.config_ciphertext = "bark", "synthetic"
        event = session.get(Outbox, "event-retry")
        event.uncertain = True
        for suffix, lease in (("a", AT + 30), ("b", AT - 30)):
            session.add(SeenPost(website_id="nodeseek", external_post_id=suffix, first_seen_at=AT))
            session.flush()
            session.add(
                Outbox(
                    id="lease-" + suffix,
                    website_id="nodeseek",
                    external_post_id=suffix,
                    target_id=core.target,
                    target_snapshot={},
                    payload={},
                    status="leased",
                    available_at=AT,
                    lease_token=suffix,
                    lease_until=lease,
                    created_at=AT,
                )
            )
    row = only(view(core)["targets"])
    assert row["status"] == "enabled"
    assert row["queue"] == {"pending": 0, "retry": 1, "earliest_at": AT + 60}
    assert row["sending"] == row["expired_leases"] == row["uncertain"] == 1
    assert row["last"] == {"result": "permanent_error", "code": "send_timeout", "at": AT - 60}


def test_mock_targets_are_not_listed(core):
    assert view(core)["targets"] == []


def source_plan():
    return HOTLIST_SOURCES["linuxdo"]


def memory(**fields):
    return {
        "next_attempt_at": 0,
        "failures": 0,
        "error_code": None,
        "deferred": False,
        "refreshing": False,
        **fields,
    }


@pytest.mark.parametrize(
    ("state", "fetched", "viewing", "expected", "tone"),
    [
        (None, AT, True, "本次启动后尚无记录", "none"),
        (memory(), AT - 5, True, "正常", "ok"),
        (memory(), AT - 5, False, "未在预热", "none"),
        (memory(refreshing=True), AT - 5, True, "刷新中", "ok"),
        (memory(error_code="collection_priority", deferred=True), AT, True, "采集优先", "wait"),
        (memory(error_code="source_cooldown", deferred=True), AT, True, "共享退避", "wait"),
        (memory(failures=2, error_code="http_429"), AT, True, "刷新失败，旧数据仍可看", "warn"),
        (memory(failures=2, error_code="http_429"), None, True, "刷新失败，暂无数据", "fail"),
    ],
)
def test_hotlist_node_keeps_failure_apart_from_old_data(state, fetched, viewing, expected, tone):
    result = _hotlist_node("hot", state, fetched, 600, viewing, source_plan(), AT)
    assert result["label"] == expected and result["tone"] == tone


def test_overdue_staggered_list_is_normal_not_a_fault():
    result = _hotlist_node("weekly", memory(), AT - 5000, 600, True, source_plan(), AT)
    assert result["label"] == "正常错开" and result["tone"] == "wait"


def test_problem_history_pairs_recovery_and_hides_short_problems(core):
    fault(core, SOURCE, "timeout", at=AT - 1000)
    recover(core, SOURCE, at=AT - 990)
    fault(core, SOURCE, "http_429", at=AT - 900)
    recover(core, SOURCE, at=AT - 300)
    fault(core, "runtime:delivery", "delivery_stopped", at=AT - 200)

    rows = problem_history(core.engine, at=AT)
    assert rows["total"] == 2
    assert [row["code"] for row in rows["items"]] == ["delivery_stopped", "http_429"]
    assert rows["items"][0]["status"] == "ongoing" and rows["items"][0]["ended_at"] is None
    assert rows["items"][1]["status"] == "recovered"
    assert rows["items"][1]["ended_at"] == AT - 300
    assert problem_history(core.engine, at=AT, show_short=True)["total"] == 3
    only_runtime = problem_history(core.engine, at=AT, kind="runtime")
    assert [row["kind"] for row in only_runtime["items"]] == ["runtime"]
    second = problem_history(core.engine, at=AT, page=2, page_size=1)
    assert second["total"] == 2 and [row["code"] for row in second["items"]] == ["http_429"]


def test_problem_history_respects_window_and_ignores_orphan_recovery(core):
    fault(core, SOURCE, "timeout", at=AT - 8 * 86400)
    recover(core, SOURCE, at=AT - 10)
    assert problem_history(core.engine, at=AT)["total"] == 0
    assert problem_history(core.engine, at=AT, days=30)["total"] == 1

    with write_session(core.engine) as session:
        session.query(SystemEvent).filter(SystemEvent.phase == "fault").delete()
    assert problem_history(core.engine, at=AT, days=30)["total"] == 0


def test_problem_detail_counts_failures_and_shows_both_alert_phases(site):
    site.ingestion.record_failure("nodeseek-rss", "timeout", at=AT - 300)
    site.ingestion.record_failure("nodeseek-rss", "timeout", at=AT - 200)
    site.ingest(9001, at=AT - 100)
    key = only(problem_history(site.engine, at=AT)["items"])["id"]
    with write_session(site.engine) as session:
        recovery = session.query(SystemEvent).filter(SystemEvent.phase == "recovery").one()
        for name, event, result in (("故障", key, "success"), ("恢复", recovery.id, "unknown")):
            session.add(
                AlertDelivery(
                    id="alert-" + name,
                    event_id=event,
                    target_id=site.target,
                    target_snapshot={"name": name, "kind": "bark"},
                    result=result,
                    finished_at=AT - 90,
                )
            )

    data = problem_detail(site.engine, key, [], at=AT)
    assert data["status"] == "recovered" and data["failures"] == 2
    assert data["ended_at"] == AT - 100 and data["guide"]["summary"] == "连接超时"
    assert data["verify"] == {"kind": "rss_test", "website_id": "nodeseek"}
    assert [row["phase"] for row in data["alerts"]] == ["fault", "recovery"]
    assert [row["label"] for row in data["recent"]] == ["成功", "失败", "失败"]
    assert data["handling"] is None


def test_problem_detail_of_a_crash_finds_its_record(core):
    fault(core, "runtime:collection", "collection_stopped", at=AT - 30)
    key = only(problem_history(core.engine, at=AT)["items"])["id"]
    crash = {"actor": "collection", "at": AT - 31, "exception": "ValueError", "location": None}
    other = {"actor": "collection", "at": AT - 5000, "exception": "KeyError", "location": None}
    data = problem_detail(core.engine, key, [other, crash], at=AT)
    assert data["crash"] == crash and data["verify"] == {"kind": "restart"}


def test_problem_detail_rejects_recovery_and_missing_events(core):
    fault(core, SOURCE, "timeout", at=AT - 900)
    recovery = recover(core, SOURCE, at=AT - 300)
    for key in (recovery, "missing"):
        with pytest.raises(LookupError):
            problem_detail(core.engine, key, [], at=AT)


def boom():
    raise ValueError("synthetic-private-value")


def caught(action):
    try:
        action()
    except BaseException as error:
        return error
    raise AssertionError("expected failure")


def test_crash_record_keeps_type_and_location_but_never_text(tmp_path):
    records = CrashRecords(tmp_path / "crashes.json")
    records.add("delivery", caught(boom), at=AT)
    text = (tmp_path / "crashes.json").read_text(encoding="utf-8")
    assert "synthetic-private" not in text
    row = only(records.read())
    assert row["exception"] == "ValueError" and row["actor"] == "delivery"
    # Test frames are outside the package, so no location is claimed for them.
    assert row["location"] is None


def test_crash_record_points_at_package_code_inside_a_task_group(tmp_path):
    records = CrashRecords(tmp_path / "crashes.json")

    async def scenario():
        async with asyncio.TaskGroup() as group:
            group.create_task(asyncio.to_thread(source_guide_failure))

    error = caught(lambda: asyncio.run(scenario()))
    assert isinstance(error, ExceptionGroup)
    row = records.add("collection", error, at=AT)
    assert row["exception"] == "KeyError"
    assert row["location"]["file"] == "seekbell/services/fault_guide.py"
    assert row["location"]["function"] == "guide_for"


def source_guide_failure():
    from seekbell.services.fault_guide import guide_for

    guide_for("not-a-kind", None)


def test_crash_records_stay_bounded_and_survive_a_corrupt_file(tmp_path):
    path = tmp_path / "crashes.json"
    records = CrashRecords(path)
    for index in range(LIMIT + 5):
        records.add("alerts", None, at=index)
    rows = records.read()
    assert len(rows) == LIMIT and rows[0]["at"] == LIMIT + 4
    assert rows[0]["exception"] is None and list(tmp_path.glob("*.tmp")) == []
    path.write_text("{", encoding="utf-8")
    assert records.read() == []
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    assert records.read() == []


def literal_codes(pattern):
    root = Path(seekbell.__file__).parent
    found = set()
    for path in root.rglob("*.py"):
        found.update(re.findall(pattern, path.read_text(encoding="utf-8")))
    return found


def test_every_source_failure_code_has_a_guide():
    codes = literal_codes(r'SourceFailure\(\s*"([a-z0-9_]+)"')
    assert "timeout" in codes and len(codes) >= 12
    assert {code for code in codes if not source_guide(code).known} == set()


def test_every_delivery_code_has_a_guide():
    codes = literal_codes(r'SendResult\([^)]*?code="([a-z0-9_]+)"')
    codes |= literal_codes(r'code="(smtp_[a-z_]+)"')
    codes |= literal_codes(r'error_code = "(lease_expired)"')
    codes = {code for code in codes if not code.endswith("_accepted")} - {"mock_unavailable"}
    assert "send_timeout" in codes and "lease_expired" in codes
    assert {code for code in codes if not delivery_guide(code).known} == set()
    for prefix in DELIVERY_PREFIXES:
        for outcome in DELIVERY_OUTCOMES:
            assert delivery_guide(f"{prefix}_{outcome}").known


@pytest.mark.parametrize(
    ("code", "handling"),
    [("http_503", "auto_retry"), ("http_404", "action"), ("http_429", "auto_retry")],
)
def test_http_status_rules(code, handling):
    assert source_guide(code).known and source_guide(code).handling == handling


def test_unknown_codes_fall_back_without_claiming_a_cause():
    for guide in (source_guide("mystery"), delivery_guide("mystery"), runtime_guide("mystery")):
        assert not guide.known and guide.handling == "action"
    assert not delivery_guide("other_retry").known


def test_uncertain_delivery_never_reads_as_failure():
    assert "结果不确定" in delivery_guide("send_timeout").summary
    assert "结果不确定" in delivery_guide("telegram_timeout").summary


def test_status_routes_do_not_touch_hotlist_network_or_warming(tmp_path):
    hotlists = synthetic_hotlists()
    app = create_app(Settings(data_dir=tmp_path), hotlist_factory=lambda: hotlists)
    with TestClient(app) as client:
        authenticate(client)
        first = client.get("/api/manage/operations/status")
        assert first.status_code == 200
        assert client.get("/api/manage/operations/problems").json()["total"] == 0
        assert client.get("/api/manage/operations/problems/absent").status_code == 404
        assert hotlists.viewed_at is None and hotlists.pending == {} and hotlists.warmer is None
        assert first.json()["services"][0]["state"] == "unknown"


def test_status_route_requires_login(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/manage/operations/status").status_code == 401


def test_actor_crash_reason_survives_restart(tmp_path):
    scenario = SyntheticScenario()

    def crashing(engine, notifiers):
        runtime = scenario.factory(engine, notifiers)

        async def fail(stop):
            boom()

        runtime.worker.run = fail
        return runtime

    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings, runtime_factory=scenario.factory)) as client:
        authenticate(client)

    app = create_app(settings, runtime_factory=crashing)
    with TestClient(app) as client:
        until(lambda: client.get("/health/ready").status_code == 503)
        authenticate(client, setup=False)
        data = client.get("/api/manage/operations/status").json()
        problem = only(data["problems"])
        assert problem["key"] == "runtime:delivery" and problem["hint"] == "重启容器后恢复"
        assert {row["id"]: row["state"] for row in data["services"]}["delivery"] == "failed"
        event_id = problem["event_id"]

    restarted = create_app(settings, runtime_factory=scenario.factory)
    with TestClient(restarted) as client:
        until(lambda: client.get("/health/ready").status_code == 200)
        authenticate(client, setup=False)
        data = client.get("/api/manage/operations/status").json()
        assert data["problems"] == []
        assert all(row["state"] == "running" for row in data["services"])
        detail = client.get("/api/manage/operations/problems/" + event_id).json()
        assert detail["status"] == "recovered"
        assert detail["crash"]["exception"] == "ValueError"
        assert "synthetic-private" not in json.dumps(detail)
