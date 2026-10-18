class SourceFailure(Exception):
    """A bounded, non-sensitive source error; never store raw exception text."""

    def __init__(self, code: str, *, retry_after: float | None = None):
        self.code = code
        self.retry_after = retry_after
        super().__init__(code)
