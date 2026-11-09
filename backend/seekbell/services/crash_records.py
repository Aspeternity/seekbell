"""Keep recent background-actor crashes across the restart that recovers from them."""

import json
import os
import tempfile
import traceback
from importlib.metadata import version
from pathlib import Path

LIMIT = 20
PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def describe(error: BaseException | None) -> dict:
    """Exception type and innermost SeekBell frame; never message text or local values."""
    if error is None:
        return {"exception": None, "location": None}
    # The collection actor raises through a TaskGroup, whose group type says nothing.
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    location = None
    for frame in traceback.extract_tb(error.__traceback__):
        try:
            relative = Path(frame.filename).resolve().relative_to(PACKAGE_ROOT)
        except ValueError:
            continue
        location = {
            "file": "seekbell/" + relative.as_posix(),
            "function": frame.name,
            "line": frame.lineno,
        }
    return {"exception": type(error).__name__, "location": location}


class CrashRecords:
    """A small file, because a database failure may be the very thing being recorded."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> list[dict]:
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)][:LIMIT]

    def add(self, actor: str, error: BaseException | None, *, at: float) -> dict:
        record = {"actor": actor, "at": at, "version": version("seekbell"), **describe(error)}
        rows = [record, *self.read()][:LIMIT]
        descriptor, temporary = tempfile.mkstemp(
            dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                json.dump(rows, output)
            os.replace(temporary, self.path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
        return record
