"""Pure HTTP date parsing, shared by collectors and notification transports."""

import math
from datetime import UTC
from email.utils import parsedate_to_datetime


def retry_after_seconds(value: str | None, now: float) -> float | None:
    if not value:
        return None
    try:
        result = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            result = (
                date.replace(tzinfo=UTC).timestamp() - now
                if date.tzinfo is None
                else (date.timestamp() - now)
            )
        except (TypeError, ValueError, OverflowError):
            return None
    if not math.isfinite(result):
        return None
    return max(0, result)
