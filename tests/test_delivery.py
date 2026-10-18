import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from seekbell.db.models import DeliveredPost, DeliveryAttempt, Outbox
from seekbell.domain.delivery import DeliveryPolicy, SendResult
from seekbell.domain.rules import Rule
from seekbell.services.delivery import DeliveryWorker
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.core_helpers import RecordingNotifier


def worker_for(core, **policy):
    return DeliveryWorker(core.engine, {}, policy=DeliveryPolicy(**policy))


def test_multiple_task_hits_merge_per_target_and_target_failure_is_independent(core):
    other_target = core.config.create_target("Second target")
    core.config.create_task("Second rule", Rule(), [core.target, other_target], at=2)
    report = core.queued()
    assert (report.hits, report.queued) == (2, 2)
    worker = worker_for(core)
    claims = [worker.claim(at=30), worker.claim(at=30)]
    assert {c.target_snapshot["id"] for c in claims} == {core.target, other_target}
    by_target = {c.target_snapshot["id"]: c for c in claims}
    assert len(by_target[core.target].payload["matched_tasks"]) == 2
    assert len(by_target[other_target].payload["matched_tasks"]) == 1
    worker.finish(by_target[core.target], SendResult(status="success"), at=31)
    worker.finish(
        by_target[other_target],
        SendResult(status="permanent_error", code="mock_rejected"),
        at=31,
    )
    with Session(core.engine) as session:
        assert session.get(Outbox, by_target[core.target].event_id).status == "sent"
        assert session.get(Outbox, by_target[other_target].event_id).status == "failed"
    assert core.count(DeliveredPost) == 1 and worker.claim(at=1000) is None


def test_claim_is_atomic_with_concurrent_workers(core):
    core.queued()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: worker_for(core).claim(at=30), range(2)))
    assert sum(claim is not None for claim in claims) == 1
    assert core.count(DeliveryAttempt) == 1
    assert core.one(Outbox).status == "leased"


def test_expired_lease_recovers_after_restart_with_same_event_id(core):
    core.queued()
    old_worker = worker_for(core, lease_seconds=10)
    first = old_worker.claim(at=30)
    assert worker_for(core).claim(at=39) is None
    recovered = worker_for(core).claim(at=40)
    assert recovered.event_id == first.event_id
    assert recovered.token != first.token and recovered.sequence == 2
    assert recovered.payload["event_id"] == first.payload["event_id"]
    with Session(core.engine) as session:
        attempts = session.scalars(select(DeliveryAttempt).order_by(DeliveryAttempt.sequence)).all()
        assert (attempts[0].result, attempts[0].error_code) == ("unknown", "lease_expired")
    worker_for(core).finish(recovered, SendResult(status="success"), at=41)
    assert core.one(Outbox).status == "sent" and core.one(Outbox).uncertain


def test_late_old_success_is_audited_and_cannot_overwrite_new_lease(core):
    core.queued()
    worker = worker_for(core, lease_seconds=10)
    first = worker.claim(at=30)
    second = worker.claim(at=40)
    assert not worker.finish(first, SendResult(status="success"), at=41)
    event = core.one(Outbox)
    assert event.status == "leased" and event.lease_token == second.token
    assert core.count(DeliveredPost) == 1
    # A known late success also prevents retrying the event after the current attempt fails.
    assert worker.finish(second, SendResult(status="unknown", code="mock_timeout"), at=42)
    assert core.one(Outbox).status == "sent"
    with Session(core.engine) as session:
        old = session.scalar(
            select(DeliveryAttempt).where(DeliveryAttempt.lease_token == first.token)
        )
        assert old.result == "unknown" and old.late_result == "success"


def test_stale_failure_cannot_replace_new_success(core):
    core.queued()
    worker = worker_for(core, lease_seconds=10)
    old = worker.claim(at=30)
    new = worker.claim(at=40)
    worker.finish(new, SendResult(status="success"), at=41)
    assert not worker.finish(old, SendResult(status="permanent_error", code="late_failure"), at=42)
    assert core.one(Outbox).status == "sent" and core.count(DeliveredPost) == 1


def test_retry_after_bounded_attempts_and_unknown_are_persistent(core):
    core.queued()
    worker = worker_for(core, max_attempts=3, base_backoff=5, max_backoff=20)
    first = worker.claim(at=30)
    worker.finish(
        first,
        SendResult(status="transient_error", code="rate_limited", retry_after=60),
        at=31,
    )
    assert worker.claim(at=90) is None
    second = worker.claim(at=91)
    worker.finish(second, SendResult(status="unknown", code="mock_timeout"), at=92)
    assert core.one(Outbox).available_at == 102
    third = worker.claim(at=102)
    worker.finish(third, SendResult(status="transient_error", code="service_unavailable"), at=103)
    assert core.one(Outbox).status == "failed"
    assert core.one(Outbox).uncertain and core.one(Outbox).attempt_count == 3
    assert worker.claim(at=10000) is None and core.count(DeliveredPost) == 0


def test_last_attempt_crash_exhausts_lease_without_unbounded_sends(core):
    core.queued()
    worker = worker_for(core, max_attempts=1, lease_seconds=10)
    assert worker.claim(at=30) is not None
    assert worker.claim(at=40) is None
    assert core.one(Outbox).status == "failed" and core.one(Outbox).uncertain
    assert core.count(DeliveryAttempt) == 1


@pytest.mark.parametrize("action", ["pause", "delete"])
def test_task_removal_cancels_only_its_pending_contribution(core, action):
    second = core.config.create_task("Keep this rule", Rule(), [core.target], at=2)
    core.queued()
    if action == "pause":
        core.config.set_task_enabled(core.task, False)
    else:
        core.config.delete_task(core.task, at=21)
    worker = worker_for(core)
    claim = worker.claim(at=30)
    assert [task["id"] for task in claim.payload["matched_tasks"]] == [second]
    worker.finish(claim, SendResult(status="success"), at=31)
    assert core.one(Outbox).status == "sent"


def test_reenable_task_or_target_does_not_restore_cancelled_messages(core):
    core.queued()
    core.config.set_task_enabled(core.task, False)
    core.config.set_task_enabled(core.task, True)
    assert worker_for(core).claim(at=30) is None
    assert core.one(Outbox).status == "cancelled"
    core.ingest(9002, 9003, at=40)
    core.config.set_target_enabled(core.target, False)
    core.config.set_target_enabled(core.target, True)
    assert worker_for(core).claim(at=50) is None
    with Session(core.engine) as session:
        assert set(session.scalars(select(Outbox.status))) == {"cancelled"}


def test_inflight_cancellation_preserves_actual_success_evidence(core):
    core.queued()
    worker = worker_for(core)
    claim = worker.claim(at=30)
    core.config.set_task_enabled(core.task, False)
    assert core.one(Outbox).cancel_requested and core.one(Outbox).status == "leased"
    worker.finish(claim, SendResult(status="success"), at=31)
    assert core.one(Outbox).status == "sent" and core.count(DeliveredPost) == 1


def test_inflight_cancellation_does_not_retry_uncertain_result(core):
    core.queued()
    worker = worker_for(core)
    claim = worker.claim(at=30)
    core.config.set_target_enabled(core.target, False)
    worker.finish(claim, SendResult(status="unknown", code="mock_timeout"), at=31)
    assert core.one(Outbox).status == "cancelled" and core.one(Outbox).uncertain


def test_updated_rule_keeps_pending_original_version_and_name(core):
    core.queued()
    core.config.update_task(core.task, "Changed name", Rule(), [core.target], at=21)
    claim = worker_for(core).claim(at=30)
    assert claim.payload["matched_tasks"] == [
        {
            "id": core.task,
            "version": 1,
            "name": "Synthetic rule",
        }
    ]


def test_async_dispatch_is_outside_database_transaction(core):
    core.queued()

    class ConfiguringNotifier:
        async def send(self, target, payload):
            # This independent write would lock/fail if send held BEGIN IMMEDIATE.
            await asyncio.to_thread(
                core.config.update_task, core.task, "New", Rule(), [core.target], at=30
            )
            return SendResult(status="success")

    worker = DeliveryWorker(core.engine, {"mock": ConfiguringNotifier()}, clock=lambda: 30)
    assert asyncio.run(worker.run_once()) is not None
    assert core.one(Outbox).status == "sent"


def test_notifier_exception_is_sanitized_and_retried(core):
    core.queued()

    class Broken:
        async def send(self, target, payload):
            raise OSError("SYNTHETIC_PRIVATE_PAYLOAD")

    worker = DeliveryWorker(core.engine, {"mock": Broken()}, clock=lambda: 30)
    asyncio.run(worker.run_once())
    assert core.one(Outbox).status == "retry"
    assert core.one(DeliveryAttempt).error_code == "send_exception"
    assert "SYNTHETIC_PRIVATE_PAYLOAD" not in core.one(Outbox).payload


def test_async_recording_notifier_gets_one_merged_payload(core):
    core.config.create_task("Second", Rule(), [core.target], at=2)
    core.queued()
    notifier = RecordingNotifier()
    worker = DeliveryWorker(core.engine, {"mock": notifier}, clock=lambda: 30)
    asyncio.run(worker.run_once())
    assert asyncio.run(worker.run_once()) is None
    assert len(notifier.calls) == 1
    assert len(notifier.calls[0][1]["matched_tasks"]) == 2
