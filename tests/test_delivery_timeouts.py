import asyncio

from seekbell.db.models import DeliveredPost, Outbox
from seekbell.domain.delivery import DeliveryPolicy, SendResult
from seekbell.services.delivery import DeliveryWorker


def test_hanging_transport_is_bounded_and_recorded_as_unknown(core):
    core.queued()

    class Hanging:
        async def send(self, target, payload):
            await asyncio.Event().wait()

    worker = DeliveryWorker(
        core.engine,
        {"mock": Hanging()},
        clock=lambda: 30,
        policy=DeliveryPolicy(send_timeout_seconds=0.01),
    )
    asyncio.run(worker.run_once())
    event = core.one(Outbox)
    assert event.status == "retry" and event.uncertain
    assert event.last_error_code == "send_timeout"


def test_late_success_after_final_lease_expiry_corrects_terminal_status(core):
    core.queued()
    worker = DeliveryWorker(
        core.engine,
        {},
        policy=DeliveryPolicy(max_attempts=1, lease_seconds=10),
    )
    claim = worker.claim(at=30)
    assert worker.claim(at=40) is None
    assert core.one(Outbox).status == "failed"
    assert not worker.finish(claim, SendResult(status="success"), at=41)
    assert core.one(Outbox).status == "sent" and core.one(Outbox).uncertain
    assert core.count(DeliveredPost) == 1
