"""Mechanics shared by the training and held-out generators: accounts, local times, item assembly.

Only mechanics live here: how a sender is printed, how a UTC instant becomes the phone's local
time, how an item is assembled and checked, and how a file is written. Wording (messages,
assumptions, names, places, scenarios) belongs to each generator, so the held-out set shares no
phrasing with the training data.

Conventions match the signed probe set: a sender prints as '<App> <identifier> <label>', the
phone's own account as '<App> <identifier> (owner)'; times print as the phone's local time with
its zone abbreviation, e.g. '2026-03-12 20:03:27 EDT'.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from core.contracts import AssumptionKind
from eval.probe_draft.model import ProbeLine
from eval.stancedata.families import family
from eval.stancedata.model import GenItem, generated_label

APPS = ("SMS", "WhatsApp", "Telegram", "Signal", "Instagram")
DEFAULT_TZ = "America/New_York"


@dataclass(frozen=True)
class Account:
    """One account as the phone report shows it."""

    app: str  # one of APPS
    identifier: str  # phone number (+1...), Telegram user id, or Instagram username
    label: str | None = None  # saved contact name or display handle; never set for the owner
    owner: bool = False  # the phone's own account
    device: str = "gen"

    def __post_init__(self) -> None:
        if self.app not in APPS:
            raise ValueError(f"unknown app {self.app!r}")
        if self.owner and self.label:
            raise ValueError("the owner's account prints as (owner), without a label")
        if not self.identifier or " " in self.identifier:
            raise ValueError(f"bad identifier {self.identifier!r}")

    @property
    def sender(self) -> str:
        if self.owner:
            return f"{self.app} {self.identifier} (owner)"
        return (
            f"{self.app} {self.identifier} {self.label}"
            if self.label
            else f"{self.app} {self.identifier}"
        )

    @property
    def account_id(self) -> str:
        return f"acct:{self.device}:{self.app}:{self.identifier}"


@dataclass(frozen=True)
class Msg:
    account: Account
    utc: datetime  # timezone-aware
    text: str

    def __post_init__(self) -> None:
        if self.utc.tzinfo is None:
            raise ValueError("message time must be timezone-aware")
        if not self.text.strip() or "\n" in self.text or "\r" in self.text:
            raise ValueError(f"message text must be one non-empty line: {self.text!r}")


class NonexistentLocalTime(ValueError):
    """A local clock time skipped by a DST change (for example 2:30 a.m. on the spring change)."""


def at_local(
    day: date, hh: int, mm: int, ss: int = 0, tz: str = DEFAULT_TZ, fold: int = 0
) -> datetime:
    """The UTC instant at which the phone's clock in `tz` read this local time.

    Raises NonexistentLocalTime for a time the clock skipped. For a repeated hour (the fall
    change) `fold=0` is the first pass and `fold=1` the second.
    """
    zone = ZoneInfo(tz)
    local = datetime.combine(day, time(hh, mm, ss), tzinfo=zone).replace(fold=fold)
    utc = local.astimezone(UTC)
    back = utc.astimezone(zone)
    if (back.hour, back.minute, back.second, back.date()) != (hh, mm, ss, day):
        raise NonexistentLocalTime(f"{day} {hh:02d}:{mm:02d}:{ss:02d} does not exist in {tz}")
    return utc


def local_dt(utc: datetime, tz: str = DEFAULT_TZ) -> datetime:
    return utc.astimezone(ZoneInfo(tz))


def local_str(utc: datetime, tz: str = DEFAULT_TZ) -> str:
    """'2026-03-12 20:03:27 EDT': the phone's local clock reading and zone abbreviation."""
    loc = local_dt(utc, tz)
    return loc.strftime("%Y-%m-%d %H:%M:%S ") + (loc.tzname() or tz)


def long_date(day: date) -> str:
    """'March 12, 2026', the date form assumptions use."""
    return f"{day.strftime('%B')} {day.day}, {day.year}"


def fictional_phone(rng: random.Random, area_codes: Sequence[str]) -> str:
    """A North American number in the 555-0100 to 555-0199 block reserved for fiction."""
    return f"+1{rng.choice(list(area_codes))}55501{rng.randrange(100):02d}"


def pretty_phone(number: str) -> str:
    """'+12125550122' -> '+1 212-555-0122', the form assumptions use."""
    if not (number.startswith("+1") and len(number) == 12 and number[1:].isdigit()):
        raise ValueError(f"not a +1 number: {number!r}")
    return f"+1 {number[2:5]}-{number[5:8]}-{number[8:]}"


def item_rng(generator: str, seed: int, index: int) -> random.Random:
    """A per-item random stream: item i is the same whatever else the run generates."""
    digest = hashlib.sha256(f"{generator}|{seed}|{index}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))  # noqa: S311 - synthetic data, not security


def _line(m: Msg, tz: str) -> ProbeLine:
    return ProbeLine(
        sender=m.account.sender,
        account_id=m.account.account_id,
        local_time=local_str(m.utc, tz),
        text=m.text,
    )


def build_item(
    *,
    probe_id: str,
    family_id: str,
    source: str,
    generator: str,
    lang: str,
    kind: AssumptionKind,
    assumption: str,
    msgs: Sequence[Msg],
    target: int,
    quote: str,
    rationale: str,
    group: str | None = None,
    tz: str = DEFAULT_TZ,
    disputed: str | None = None,
    labeled_by: str | None = None,
) -> GenItem:
    """Assemble and check one item. The gold stance, category and trap come from the family.

    msgs are every line of the chat excerpt in UTC order (the order the phone recorded them;
    around a DST change the local clock can run backwards); target indexes the labeled record.
    group names the chat scenario the item was built from (default: the item's own id); sibling
    items that share a record and differ only in the assumption share a group.
    """
    if not 0 <= target < len(msgs):
        raise ValueError(f"{probe_id}: target {target} outside {len(msgs)} messages")
    if any(b.utc <= a.utc for a, b in zip(msgs, msgs[1:], strict=False)):
        raise ValueError(f"{probe_id}: messages must be in strictly increasing UTC order")
    if quote.strip() != quote or not quote:
        raise ValueError(f"{probe_id}: quote must be non-empty with no outer whitespace")
    f = family(family_id)
    if f.disputed and source == "heldout_gen" and disputed is None:
        disputed = (
            f"The signed probe items of this kind ({f.trap}) are marked disputed, so this item "
            "is scored apart from the bars."
        )
    lines = [_line(m, tz) for m in msgs]
    return GenItem(
        probe_id=probe_id,
        category=f.category,
        trap=f.trap,
        lang=lang,
        assumption_kind=kind,
        assumption=assumption,
        target=lines[target],
        context=tuple(x for i, x in enumerate(lines) if i != target),
        target_index=target,
        proposed_quote=quote,
        gold_stance=f.stance,
        gold_review="accept" if f.stance == "supports" else "dismiss",
        rationale=rationale,
        source=source,
        labeled_by=labeled_by or generated_label(generator),
        disputed=disputed,
        family=family_id,
        generator=generator,
        group=group or probe_id,
    )


def item_texts(item: GenItem | dict) -> list[str]:
    """Every free text an item carries: assumption, record, context lines and rationale."""
    d = item if isinstance(item, dict) else item.model_dump(mode="json")
    texts = [d["assumption"], d["target"]["text"], d.get("rationale", "")]
    texts += [line["text"] for line in d["context"]]
    return [t for t in texts if t]


def write_jsonl(items: Iterable[GenItem], path: Path) -> str:
    """Write one item per line (LF, UTF-8) and return the file's SHA-256."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for it in items:
            fh.write(it.model_dump_json() + "\n")
    return sha256_file(path)


def read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(x) for x in lines if x.strip()]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
