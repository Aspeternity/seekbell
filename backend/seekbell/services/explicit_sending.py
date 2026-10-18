"""Shared, bounded explicit sending; never automatically replay an interrupted action."""

import asyncio

from seekbell.domain.delivery import SendResult


class SendConflict(ValueError):
    pass


class SendNotFound(ValueError):
    pass


async def send_once(notifiers, snapshot: dict, payload: dict, *, timeout: float) -> SendResult:
    notifier = notifiers.get(snapshot["kind"])
    if notifier is None:
        return SendResult(status="permanent_error", code="unsupported_notifier")
    try:
        result = await asyncio.wait_for(notifier.send(snapshot, payload), timeout=timeout)
        if isinstance(result, SendResult):
            return result
        return SendResult(status="unknown", code="invalid_notifier_result")
    except TimeoutError:
        return SendResult(status="unknown", code="send_timeout")
    except Exception:
        return SendResult(status="unknown", code="send_exception")
