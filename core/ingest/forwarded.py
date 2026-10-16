"""Messages the extraction marks as forwarded, or that carry a forwarded or quoted original.

The canonical tables cannot say a message was forwarded or who first wrote it (that needs a
schema change Arsh signs: PROPOSED_CHANGES.md). Until then each importer lists such messages,
in full, in its coverage payload under `forwarded_records`, and everything downstream reads them
from here and fails closed:

- the pipeline stores a model's "supports" or "contradicts" on one as "complicates", so it can
  neither make a claim supported nor contradicted, and keeps it in front of the expert;
- a check whose outcome rests on one is inconclusive, and the sender check never names the
  forwarder as the one who wrote the words;
- the claim page and the report put a warning on the claim and on the record.

Two reasons are kept: `forwarded` (the extraction marks the message forwarded) and `embedded`
(the message carries another message inside it, forwarded or quoted, which Baker did not import).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

PAYLOAD_KEY = "forwarded_records"
REASONS = ("forwarded", "embedded")
RULE_VERSION = "1"  # how forwarded records are handled; named in every note below

STANCE_NOTE = (
    "Recorded as complicates: the extraction marks this message as forwarded or as carrying a "
    "forwarded or quoted message, and Baker does not record who first wrote the words, so it "
    f"cannot support or contradict the claim (forwarded rule {RULE_VERSION}). Model's label: "
)
RECORD_NOTE = {
    "forwarded": "Forwarded: shown as sent by whoever forwarded it; who first wrote it is not "
    "recorded.",
    "embedded": "Carries a forwarded or quoted message that Baker did not import; who wrote "
    "which words is not recorded.",
}


def affected(conn: sqlite3.Connection) -> dict[str, str]:
    """Record id -> reason ('forwarded' wins over 'embedded') for every import in the case."""
    out: dict[str, str] = {}
    for (payload_json,) in conn.execute("SELECT payload_json FROM source_coverage"):
        try:
            listed = json.loads(payload_json).get(PAYLOAD_KEY) or {}
        except (ValueError, AttributeError):
            continue
        for reason in reversed(REASONS):
            for rid in listed.get(reason, []):
                out[rid] = reason
    return out


def among(found: dict[str, str], record_ids: Iterable[str]) -> list[str]:
    """The record ids that are affected, in order, each once."""
    return [r for r in dict.fromkeys(record_ids) if r in found]


def claim_warning(found: dict[str, str], record_ids: Iterable[str]) -> str | None:
    """One sentence for a claim whose evidence or checks rest on affected records."""
    hit = among(found, record_ids)
    if not hit:
        return None
    n = len(hit)
    these = "this message" if n == 1 else f"these {n} messages"
    return (
        f"{n} record{'s' if n != 1 else ''} this claim's evidence or checks rest on "
        f"{'is a message' if n == 1 else 'are messages'} the extraction marks as forwarded or "
        f"as carrying a forwarded or quoted message. Baker shows {these} as sent by whoever "
        "forwarded or quoted, and does not record who first wrote the words, so "
        f"{'it' if n == 1 else 'they'} cannot support or contradict this claim. Check "
        f"{'it' if n == 1 else 'each'} in the extraction tool."
    )


def check_note(found: dict[str, str], record_ids: Iterable[str]) -> str | None:
    """Why a check that rests on affected records is inconclusive, or None."""
    hit = among(found, record_ids)
    if not hit:
        return None
    return (
        f"Inconclusive (forwarded rule {RULE_VERSION}): the outcome rests on "
        f"{', '.join(hit)}, which the extraction marks as forwarded or as carrying a forwarded "
        "or quoted message; who first wrote those words is not recorded."
    )
