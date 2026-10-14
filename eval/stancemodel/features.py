"""What the small stance model reads: one probe-format item rendered as an (assumption, excerpt)
text pair, plus where the record's text sits in the excerpt.

SYNTHETIC data only. Pure Python, no torch, so the rendering is testable anywhere and the product
can later render a case's records the same way.

The excerpt is every line of the chat in time order, the record marked "RECORD:", or
"RECORD (item1):" when the item names the phone the record was extracted from (Baker-form items,
written the way Baker sends a case's records, eval/stancemodel/time_case01.case_item; the phone
reads as its source id, as core/audit/readable.py names it). Each line is
"<local time> | <sender> | <text>". The time is the phone's local clock reading, written the way
assumptions write it ("10:46 p.m. on February 15, 2025"), with the weekday and zone after it. In
plain items the sender's +1 numbers are written "+1 718-555-0122", as the plain assumptions write
them; a Baker-form sender is kept exactly as core/audit/readable.py printed it, because Baker's
assumptions print the same numbers that way ("SMS +12125550111"). Nothing is inferred: both are
the record's own fields in another spelling, and the text is untouched, so a quote cut from it is
verbatim in the record.

When a pair is too long for the model, context lines farthest from the record go first. The
record line itself is never dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# 1.1.0: the record mark names the phone; 1.2.0: the claim line (baker_claim); 1.3.0: the phone
# reads as its source id, and Baker-form senders keep Baker's spelling
VERSION = "1.3.0"

RECORD_MARK = "RECORD: "
CLAIM_MARK = "CLAIM: "
LINE_SEP = " || "
FIELD_SEP = " | "

_PHONE = re.compile(r"\+1(\d{3})(\d{3})(\d{4})(?!\d)")
_LOCAL_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (\S+)$")


def spoken_time(local_time: str) -> str:
    """'2025-02-15 22:46:56 EST' -> '10:46 p.m. on February 15, 2025 (Saturday, EST)'.

    Seconds are left out: assumptions state minutes at most. An unparseable value is kept as is.
    """
    m = _LOCAL_TIME.match(local_time.strip())
    if not m:
        return local_time
    dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    hour = dt.hour % 12 or 12
    half = "a.m." if dt.hour < 12 else "p.m."
    return (
        f"{hour}:{dt.minute:02d} {half} on {dt.strftime('%B')} {dt.day}, {dt.year} "
        f"({dt.strftime('%A')}, {m.group(2)})"
    )


def spoken_sender(sender: str) -> str:
    """'Signal +17185550122 Dante' -> 'Signal +1 718-555-0122 Dante'."""
    return _PHONE.sub(r"+1 \1-\2-\3", sender)


def phone_name(device_id: str) -> str:
    """'dev:item1' -> 'item1': Baker's phone ids are 'dev:' plus the source id."""
    return device_id.removeprefix("dev:")


def line_text(line: dict[str, Any], baker_form: bool = False) -> tuple[str, int]:
    """One rendered line and the offset of the message text inside it."""
    sender = line["sender"] if baker_form else spoken_sender(line["sender"])
    head = spoken_time(line["local_time"]) + FIELD_SEP + sender + FIELD_SEP
    return head + line["text"], len(head)


@dataclass(frozen=True)
class Rendered:
    assumption: str
    excerpt: str
    record_start: int  # where the record's text starts inside excerpt
    record_end: int
    lines_kept: int
    lines_total: int


def assumption_text(item: dict[str, Any]) -> str:
    """The first text of the pair: the assumption, after "CLAIM: <claim text> || " when the item
    carries the claim (Baker's meaning, role and event assumptions point at it). The claim sits
    on the assumption side, so a quote can never be cut from it."""
    claim = item.get("baker_claim")
    return f"{CLAIM_MARK}{claim}{LINE_SEP}{item['assumption']}" if claim else item["assumption"]


def record_mark(item: dict[str, Any]) -> str:
    """The record line's mark: "RECORD: ", or "RECORD (item1): " when the item names its
    phone."""
    device = item.get("device_id")
    return f"RECORD ({phone_name(device)}): " if device else RECORD_MARK


def ordered_lines(item: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    lines = list(item["context"])
    lines.insert(item["target_index"], item["target"])
    return lines, item["target_index"]


def render(item: dict[str, Any], keep: set[int] | None = None) -> Rendered:
    """Render an item; `keep` limits the context to those line indexes (the record always stays)."""
    lines, t = ordered_lines(item)
    mark = record_mark(item)
    baker_form = bool(item.get("device_id"))
    parts: list[str] = []
    record_start = record_end = -1
    pos = 0
    kept = 0
    for i, line in enumerate(lines):
        if i != t and keep is not None and i not in keep:
            continue
        text, text_off = line_text(line, baker_form)
        if i == t:
            text = mark + text
            text_off += len(mark)
        if parts:
            pos += len(LINE_SEP)
        if i == t:
            record_start = pos + text_off
            record_end = record_start + len(line["text"])
        parts.append(text)
        pos += len(text)
        kept += 1
    excerpt = LINE_SEP.join(parts)
    assert excerpt[record_start:record_end] == item["target"]["text"]  # noqa: S101 - invariant
    return Rendered(assumption_text(item), excerpt, record_start, record_end, kept, len(lines))


def drop_order(item: dict[str, Any]) -> list[int]:
    """Context line indexes, farthest from the record first (later lines first on a tie)."""
    lines, t = ordered_lines(item)
    others = [i for i in range(len(lines)) if i != t]
    return sorted(others, key=lambda i: (-abs(i - t), -i))
