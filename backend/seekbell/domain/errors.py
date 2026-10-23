class SourceDeferred(Exception):
    """The shared origin is busy or cooling down; no HTTP attempt occurred."""

    def __init__(self, next_attempt_at, code="source_cooldown"):
        self.next_attempt_at, self.code = next_attempt_at, code
        super().__init__(code)


class SourceFailure(Exception):
    """A bounded, non-sensitive source error; never store raw exception text."""

    def __init__(self, code: str, *, retry_after: float | None = None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)
