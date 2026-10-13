"""The timeline settings of one case, kept in its settings file (core/casework/cases.py).

tolerance_min: how far, in minutes, a phone record may sit from a time the government document
    states before the Timeline check shows the difference. The one-shot demo used 5.
gap_hours: the shortest stretch with no messages or calls the Gaps view lists.

A change is the expert's, and the audit log records it with their name.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from core.casework import cases
from core.review.actions import ReviewError, _expert

DEFAULT_TOLERANCE_MIN = 5
DEFAULT_GAP_HOURS = 72
TOLERANCE_RANGE = (0, 24 * 60)
GAP_RANGE = (1, 90 * 24)
TOLERANCE_KEY = "timeline_tolerance_min"
GAP_KEY = "gap_min_hours"


@dataclass(frozen=True)
class Settings:
    tolerance_min: int = DEFAULT_TOLERANCE_MIN
    gap_hours: int = DEFAULT_GAP_HOURS


def _int_in(value: object, lo: int, hi: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        n = int(str(value).strip())
    except ValueError:
        return None
    return n if lo <= n <= hi else None


def from_case(settings: dict) -> Settings:
    """The saved settings; a missing or unreadable value falls back to the default."""
    tol = _int_in(settings.get(TOLERANCE_KEY), *TOLERANCE_RANGE)
    gap = _int_in(settings.get(GAP_KEY), *GAP_RANGE)
    return Settings(
        DEFAULT_TOLERANCE_MIN if tol is None else tol,
        DEFAULT_GAP_HOURS if gap is None else gap,
    )


def save(
    case: cases.Case,
    conn: sqlite3.Connection,
    actor: str,
    tolerance_min: str,
    gap_hours: str,
    clock: cases.Clock | None = None,
) -> Settings:
    _expert(actor)
    tol = _int_in(tolerance_min, *TOLERANCE_RANGE)
    gap = _int_in(gap_hours, *GAP_RANGE)
    if tol is None:
        raise ReviewError(
            f"time tolerance is whole minutes from {TOLERANCE_RANGE[0]} to {TOLERANCE_RANGE[1]}"
        )
    if gap is None:
        raise ReviewError(f"shortest stretch is whole hours from {GAP_RANGE[0]} to {GAP_RANGE[1]}")
    old = from_case(case.settings)
    new = Settings(tol, gap)
    if new == old:
        return new
    now = (clock or (lambda: datetime.now(UTC)))()
    cases._logged(
        conn,
        now,
        actor,
        "timeline.settings",
        {
            "tolerance_min": [old.tolerance_min, new.tolerance_min],
            "gap_hours": [old.gap_hours, new.gap_hours],
        },
    )
    case.save_settings(**{TOLERANCE_KEY: tol, GAP_KEY: gap})
    return new
