from typing import Protocol

from seekbell.domain.delivery import SendResult


class Notifier(Protocol):
    async def send(self, target_snapshot: dict, payload: dict) -> SendResult:
        """Return a classified result; retries and leases belong to delivery services."""
        ...
