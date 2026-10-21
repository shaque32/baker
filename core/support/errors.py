"""Recent unexpected errors in this Baker session, kept in memory for the bug report.

Baker writes no log file. When the review screen or a background job hits an unexpected error,
this keeps what a developer needs and nothing from the case: the time, where it happened (a
fixed label), the exception's type names, and the file and line of each frame in Baker's own
code. The error message is never kept, because it can quote a file name, a path or case text.
Frames outside Baker (the standard library, installed packages) collapse to one marker, since
their paths name the user's folders.
"""

from __future__ import annotations

import threading
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("core", "ui", "cli", "eval")
KEEP = 50  # newest errors kept
WHERES = frozenset({"screen", "upload", "audit", "propose", "model_check", "cli"})


@dataclass(frozen=True)
class ErrorEvent:
    at_utc: str
    where: str  # one of WHERES
    types: tuple[str, ...]  # the exception's type, then each cause or context, outermost first
    frames: tuple[str, ...]  # "core/pipeline.py:123 in run_audit", or "(outside Baker)"

    def record(self) -> dict[str, object]:
        return {
            "at_utc": self.at_utc,
            "where": self.where,
            "types": list(self.types),
            "frames": list(self.frames),
        }


_recent: deque[ErrorEvent] = deque(maxlen=KEEP)
_lock = threading.Lock()


def _type_name(exc: BaseException) -> str:
    t = type(exc)
    mod = t.__module__
    if mod == "builtins":
        return t.__qualname__
    return f"{mod}.{t.__qualname__}"


def _baker_path(filename: str) -> str | None:
    try:
        rel = Path(filename).resolve().relative_to(ROOT)
    except (ValueError, OSError):
        return None
    if not rel.parts or rel.parts[0] not in PACKAGES:
        return None
    return rel.as_posix()


def _frames_one(exc: BaseException) -> list[str]:
    out: list[str] = []
    for fs in traceback.extract_tb(exc.__traceback__):
        rel = _baker_path(fs.filename)
        line = "(outside Baker)" if rel is None else f"{rel}:{fs.lineno} in {fs.name}"
        if not out or out[-1] != line:  # one marker for a run of outside frames
            out.append(line)
    return out


def _chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen and len(out) < 5:
        seen.add(id(cur))
        out.append(cur)
        cur = cur.__cause__ or cur.__context__
    return out


def frames_of(exc: BaseException) -> tuple[str, ...]:
    """Frames of the error, then of each error it came from, each block headed by its type."""
    out: list[str] = []
    for i, e in enumerate(_chain(exc)):
        if i:
            out.append(f"(from {_type_name(e)})")
        out.extend(_frames_one(e))
    return tuple(out)


def types_of(exc: BaseException) -> tuple[str, ...]:
    return tuple(_type_name(e) for e in _chain(exc))


def note(where: str, exc: BaseException, at: datetime | None = None) -> ErrorEvent:
    """Keep one error. `where` must be one of WHERES (a fixed label, never free text)."""
    if where not in WHERES:
        raise ValueError(f"unknown error label {where!r}")
    when = (at or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    event = ErrorEvent(when, where, types_of(exc), frames_of(exc))
    with _lock:
        _recent.append(event)
    return event


def recent() -> list[ErrorEvent]:
    with _lock:
        return list(_recent)


def clear() -> None:
    with _lock:
        _recent.clear()
