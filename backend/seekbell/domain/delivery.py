import math
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SendResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["success", "transient_error", "permanent_error", "unknown"]
    code: str | None = Field(default=None, pattern=r"^[a-z0-9_]{1,80}$")
    retry_after: float | None = Field(default=None, ge=0, allow_inf_nan=False)


@dataclass(frozen=True)
class DeliveryPolicy:
    max_attempts: int = 5
    base_backoff: float = 5
    max_backoff: float = 300
    lease_seconds: float = 30
    send_timeout_seconds: float = 10

    def __post_init__(self):
        if not 1 <= self.max_attempts <= 20:
            raise ValueError("max_attempts must be between 1 and 20")
        if not all(
            math.isfinite(value)
            for value in (
                self.base_backoff,
                self.max_backoff,
                self.lease_seconds,
                self.send_timeout_seconds,
            )
        ):
            raise ValueError("Delivery time limits must be finite")
        if self.base_backoff <= 0 or self.max_backoff < self.base_backoff:
            raise ValueError("Invalid delivery backoff")
        if not 0 < self.send_timeout_seconds <= self.lease_seconds:
            raise ValueError("Send timeout must be positive and no longer than lease")

    def retry_delay(self, attempt: int, retry_after: float | None) -> float:
        normal = min(self.max_backoff, self.base_backoff * 2 ** max(0, attempt - 1))
        return max(normal, retry_after or 0)


@dataclass(frozen=True)
class SourcePolicy:
    base_backoff: float = 10
    max_backoff: float = 300

    def retry_delay(self, failures: int, retry_after: float | None) -> float:
        normal = min(self.max_backoff, self.base_backoff * 2 ** min(20, max(0, failures - 1)))
        return max(normal, retry_after or 0)
