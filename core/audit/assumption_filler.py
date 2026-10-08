"""The local-model filler for the assumption templates (core/audit/assumptions.py).

The model reads one claim and its paragraph and proposes which templates the claim rests on,
with each value written exactly as the document writes it: names ("PETROV"), phones ("Item 1"),
numbers and handles ("+1 (212) 555-0122", "@northstar"), apps, quoted words, a count and a time
range in the document's own words. It never writes an id, a time zone or a UTC time.

Code then turns those words into typed AssumptionParams, and drops anything it cannot tie to
the document or the case data. It fails closed at every step:

- Every value must appear verbatim in the claim or its paragraph. Anything else is dropped.
- Names resolve to persons the expert created (exact name or surname, one match only).
  Phones resolve to devices by their label. Numbers and user ids resolve to accounts by app
  and identifier, the way the checks match accounts. A handle stays a handle where the
  template takes one, and the checks resolve it from the data; a template that takes no
  handles drops the proposal. Zero or several matches for any other value drop it too.
- A channel must be named in the claim ("Telegram", or "texted" for SMS, "call" for calls).
  A model never narrows a search to a channel the document did not name.
- A call's stated length ("about two minutes") is turned into seconds by code.
- A count's number must appear in the claim, and its comparison ("at least", "at most",
  exactly) is read from the claim's words by code, not taken from the model.
- A time range must match the dates and times the document states (see `check_window`).
  The zone is the phone's zone from the case data; UTC only if the document says UTC.
- Every proposed assumption is core. The model does not get to mark one optional.
- A claim must not be judged on its easy parts (`coverage_gap`): each claim type needs its
  key template (a meaning claim needs "meaning", a count needs "message_count", ...), a stated
  date needs a time range, a stated time of day a range that states it, and a quoted message
  in a communication claim a sender assumption. Otherwise the claim gets no assumptions at
  all and stays unproven.

Proposals then go through TemplateAssumptionBuilder, which validates them again.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from core.audit._llm_json import (
    PROMPTS_DIR,
    BadModelOutput,
    CallRecorder,
    JsonModel,
    fill_prompt,
    load_prompt,
    model_run_id,
    prompt_version,
    required_placeholders,
    run_json_call,
)
from core.audit._local_model import LocalModel, open_run
from core.audit.assumptions import TEMPLATES, Proposal, Template, local_window
from core.audit.checks._common import CaseData, key
from core.contracts import Claim, ClaimType, ModelRun

PROMPT_FILE = "assumptions.md"
PLACEHOLDERS = frozenset({"claim", "paragraph", "templates", "channels"})
MAX_PROPOSALS = 8
MAX_WINDOW_DAYS = 400
TIME_SLACK = timedelta(minutes=15)

# What each template means, for the prompt. Every template in TEMPLATES must have one.
TEMPLATE_HELP: dict[str, str] = {
    "sender": "the quoted message was sent by one party. Needs quoted_text; one party.",
    "record_time": (
        "the quoted message (or a call between the parties) happened in a time range. "
        "Needs window, and quoted_text or channel 'call' with parties. For a call, a stated "
        "length goes in duration."
    ),
    "message_count": (
        "one phone holds a number of messages between two parties in a time range. "
        "Needs count, window, exactly one phone and two parties."
    ),
    "no_contact": "two parties had no contact in a time range. Needs window and two parties.",
    "same_account": "two or more handles are one account on one app. Needs handles and one app.",
    "contact_entry": (
        "a phone has a saved contact (quoted_text = the saved name) with a number. "
        "Needs one phone, quoted_text and the number as an account."
    ),
    "weekday_date": (
        "a weekday named in the quoted message ('monday') means the date the claim gives. "
        "Needs quoted_text and the window of that date."
    ),
    "meaning": "the quoted words mean what the claim says they mean. Needs quoted_text.",
    "authorship": "a person personally wrote what an account sent. Needs people and accounts.",
    "person_identity": "an account or handle belongs to a person. Needs people.",
    "role": "a person played the role the claim states (directed, chose, led). Needs people.",
    "event": "an event the claim states happened (a seizure, a meeting, a delivery).",
}

# The template a claim of each type must keep, or the claim gets no assumptions.
REQUIRED_TEMPLATES: dict[ClaimType, frozenset[str]] = {
    ClaimType.CONTENT_MEANING: frozenset({"meaning"}),
    ClaimType.ROLE: frozenset({"role"}),
    ClaimType.COUNT: frozenset({"message_count"}),
    ClaimType.ABSENCE: frozenset({"no_contact"}),
    ClaimType.TIMING: frozenset({"record_time", "no_contact"}),
    ClaimType.COMMUNICATION: frozenset({"sender", "record_time", "message_count"}),
    ClaimType.IDENTITY: frozenset(
        {"same_account", "contact_entry", "person_identity", "authorship"}
    ),
    ClaimType.EVENT: frozenset({"event", "role"}),
}

# Words in a claim that name a channel. App names count as themselves.
CHANNEL_WORDS: dict[str, tuple[str, ...]] = {
    "sms": ("sms", "text message", "texted", "texts", "text"),
    "call": ("call", "called", "calls", "phoned"),
}


class FillerDrop(BaseModel):
    """One thing the filler refused, for the run log and the CLI."""

    model_config = ConfigDict(frozen=True)

    claim_id: str
    index: int | None  # position in the model's list; None for the whole claim
    reason: str
    model_call_id: str | None


# ---------------------------------------------------------------- model output


class _Window(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_written: StrictStr = Field(min_length=1, max_length=300)
    start: StrictStr  # local wall clock, 'YYYY-MM-DDTHH:MM'
    end: StrictStr  # local wall clock, exclusive
    zone: Literal["phone", "UTC"]


class _Count(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: int = Field(ge=0)


class _Account(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_written: StrictStr = Field(min_length=1, max_length=200)
    app: StrictStr = Field(min_length=1, max_length=60)


class _Duration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    as_written: StrictStr = Field(min_length=1, max_length=100)


class _ProposalOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: StrictStr
    people: list[StrictStr] = Field(default_factory=list, max_length=4)
    accounts: list[_Account] = Field(default_factory=list, max_length=4)
    handles: list[StrictStr] = Field(default_factory=list, max_length=4)
    phones: list[StrictStr] = Field(default_factory=list, max_length=2)
    channels: list[StrictStr] = Field(default_factory=list, max_length=4)
    quoted_text: StrictStr = Field(default="", max_length=500)
    count: _Count | None = None
    duration: _Duration | None = None
    window: _Window | None = None


class _FillOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumptions: list[dict[str, Any]] = Field(max_length=MAX_PROPOSALS)


def fill_schema(template_ids: Iterable[str], channels: Iterable[str]) -> dict[str, object]:
    s = {"type": "string"}
    strs = {"type": "array", "items": s, "maxItems": 4}
    return {
        "type": "object",
        "properties": {
            "assumptions": {
                "type": "array",
                "maxItems": MAX_PROPOSALS,
                "items": {
                    "type": "object",
                    "properties": {
                        "template_id": {"type": "string", "enum": sorted(template_ids)},
                        "people": strs,
                        "accounts": {
                            "type": "array",
                            "maxItems": 4,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "as_written": s,
                                    "app": {"type": "string", "enum": sorted(channels)},
                                },
                                "required": ["as_written", "app"],
                                "additionalProperties": False,
                            },
                        },
                        "handles": strs,
                        "phones": {"type": "array", "items": s, "maxItems": 2},
                        "channels": {
                            "type": "array",
                            "items": {"type": "string", "enum": sorted(channels)},
                            "maxItems": 4,
                        },
                        "quoted_text": s,
                        "count": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {"value": {"type": "integer", "minimum": 0}},
                                    "required": ["value"],
                                    "additionalProperties": False,
                                },
                            ]
                        },
                        "duration": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {"as_written": s},
                                    "required": ["as_written"],
                                    "additionalProperties": False,
                                },
                            ]
                        },
                        "window": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "as_written": s,
                                        "start": s,
                                        "end": s,
                                        "zone": {"type": "string", "enum": ["phone", "UTC"]},
                                    },
                                    "required": ["as_written", "start", "end", "zone"],
                                    "additionalProperties": False,
                                },
                            ]
                        },
                    },
                    "required": [
                        "template_id",
                        "people",
                        "accounts",
                        "handles",
                        "phones",
                        "channels",
                        "quoted_text",
                        "count",
                        "duration",
                        "window",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["assumptions"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------- text helpers


class Reject(ValueError):
    """One proposal (or one value in it) cannot be used."""


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def _verbatim(value: str, *texts: str) -> bool:
    v = _nfc(value.strip())
    return bool(v) and any(v in _nfc(t) for t in texts)


def _words(text: str) -> str:
    return " " + re.sub(r"[^a-z0-9]+", " ", text.lower()) + " "


def _has_word(text: str, phrase: str) -> bool:
    return f" {phrase} " in _words(text)


_MONTHS = {
    m: i + 1
    for i, names in enumerate(
        [
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ]
    )
    for m in names
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_DATE_RE = re.compile(
    rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?!:)(?:,?\s+(\d{{4}}))?"
    rf"(?:\s*(?:to|through|thru|and|until|-|–)\s*(?:({_MONTH_RE})\.?\s+)?(\d{{1,2}})\b(?!:)"
    rf"(?:,?\s+(\d{{4}}))?)?",
    re.IGNORECASE,
)
_NUM_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", re.IGNORECASE)
_TIME24_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*(?:a\.?m|p\.?m))", re.IGNORECASE)

OPEN_START = ("before", "prior to", "until", "up to")
OPEN_END = ("after", "since", "onward", "onwards", "later")


@dataclass(frozen=True)
class _DateMention:
    month: int
    day: int
    year: int | None


def date_mentions(text: str) -> list[_DateMention]:
    out: list[_DateMention] = []
    for m in _DATE_RE.finditer(text):
        mon1 = _MONTHS[m.group(1).lower()]
        y_end = int(m.group(6)) if m.group(6) else None
        y1 = int(m.group(3)) if m.group(3) else y_end
        out.append(_DateMention(mon1, int(m.group(2)), y1))
        if m.group(5):
            mon2 = _MONTHS[m.group(4).lower()] if m.group(4) else mon1
            out.append(_DateMention(mon2, int(m.group(5)), y_end or y1))
    for m in _NUM_DATE_RE.finditer(text):
        out.append(_DateMention(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return out


def time_mentions(text: str) -> list[time]:
    out: list[time] = []
    for m in _TIME_RE.finditer(text):
        h, mi = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= h <= 12 or mi > 59:
            continue
        pm = m.group(3).lower().startswith("p")
        out.append(time((h % 12) + (12 if pm else 0), mi))
    for m in _TIME24_RE.finditer(text):
        out.append(time(int(m.group(1)), int(m.group(2))))
    if _has_word(text, "midnight"):
        out.append(time(0, 0))
    if _has_word(text, "noon"):
        out.append(time(12, 0))
    return out


def _date_stated(d: date, mentions: list[_DateMention], years: set[int]) -> bool:
    for m in mentions:
        if (m.month, m.day) != (d.month, d.day):
            continue
        if (m.year == d.year) if m.year is not None else (d.year in years):
            return True
    return False


def _near(t: datetime, times: list[time]) -> bool:
    for x in times:
        cand = t.replace(hour=x.hour, minute=x.minute, second=0, microsecond=0)
        for c in (cand - timedelta(days=1), cand, cand + timedelta(days=1)):
            if abs(t - c) <= TIME_SLACK:
                return True
    return False


def check_window(
    start: datetime,
    end: datetime,
    as_written: str,
    claim: str,
    para: str,
    template_id: str = "",
) -> None:
    """The time range must say what the document says. Raises Reject otherwise.

    - Its dates must be dates the claim states (with a year the claim or paragraph states).
      "before X" may leave the start open and end at X; "after X" may leave the end open.
      For no_contact, "first ... on X" leaves the start open too.
    - With a time of day in the range's own words, each closed end is within 15 minutes of a
      stated time. Without one, the range is whole days (midnight to midnight).
    """
    if end <= start:
        raise Reject("window ends before it starts")
    if end - start > timedelta(days=MAX_WINDOW_DAYS):
        raise Reject(f"window longer than {MAX_WINDOW_DAYS} days")
    mentions = date_mentions(as_written) + date_mentions(claim)
    years = {int(y) for y in _YEAR_RE.findall(as_written + " " + claim + " " + para)}
    if not years:
        raise Reject("the document states no year for this range")
    times = time_mentions(as_written)
    low = as_written.lower()
    open_start = any(_has_word(low, w) for w in OPEN_START) or (
        # "first made contact on March 12" says nothing came before it: only for no_contact
        template_id == "no_contact" and _has_word(low, "first")
    )
    open_end = any(_has_word(low, w) for w in OPEN_END)
    last = end - timedelta(microseconds=1)

    if not open_start:
        if not _date_stated(start.date(), mentions, years):
            raise Reject(f"window start {start.date()} is not a date the claim states")
        if times and not _near(start, times):
            raise Reject("window start is not near a time the range states")
    if not times and start.time() != time(0, 0):
        raise Reject("a range with no time of day must start at midnight")

    if open_end:
        return
    if times:
        if not _near(end, times):
            raise Reject("window end is not near a time the range states")
        if not (
            _date_stated(last.date(), mentions, years)
            or _date_stated(start.date(), mentions, years)
        ):
            raise Reject("window end is not on a date the claim states")
        return
    if end.time() != time(0, 0):
        raise Reject("a range with no time of day must end at midnight")
    if _date_stated(last.date(), mentions, years):
        return
    if open_start and _date_stated(end.date(), mentions, years):
        return  # "before March 12": ends at the start of March 12
    raise Reject(f"window end {last.date()} is not a date the claim states")


_COUNT_NOUNS = r"(?:messages?|texts?|calls?|times|emails?|chats?)"
_APPROX = ("about", "approximately", "around", "roughly", "nearly", "almost", "some", "over",
           "more than", "fewer than", "less than", "under")  # fmt: skip


def count_op(claim: str, value: int) -> Literal["eq", "ge", "le"]:
    """How the claim compares its count, read from its words. Raises Reject when the number
    is not a count of records in the claim, or the claim's comparison cannot be stated exactly
    ("about 13", "more than 13")."""
    m = re.search(rf"(.{{0,24}})\b{value}\s+(?:[\w-]+\s+){{0,2}}{_COUNT_NOUNS}\b", claim, re.I)
    if m is None:
        raise Reject(f"{value} is not written in the claim as a number of messages or calls")
    before = m.group(1).lower()
    after = claim[m.end() : m.end() + 16].lower()
    if any(_has_word(before, w) for w in _APPROX):
        raise Reject("the claim's count is approximate or strict; it cannot be checked exactly")
    if _has_word(before, "at least") or _has_word(after, "or more"):
        return "ge"
    if any(_has_word(before, w) for w in ("at most", "no more than")) or _has_word(
        after, "or fewer"
    ):
        return "le"
    return "eq"


_NUMBER_WORDS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
} | {"thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50, "sixty": 60, "ninety": 90}
_UNITS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_ABOUT = ("about", "approximately", "around", "roughly", "nearly", "almost", "some")
_DURATION_RE = re.compile(
    r"^(?:(?P<about>[a-z]+)\s+)?(?:(?P<a>an?)|(?P<n>\d+|[a-z-]+))\s+"
    r"(?P<unit>second|sec|minute|min|hour|hr)s?\.?$",
    re.IGNORECASE,
)


def duration_range(as_written: str) -> tuple[int, int]:
    """Seconds a stated call length allows: "about two minutes" is 90 to 150 (25% either
    side); "two minutes" is 120 to 179. Bounds like "under" or "more than" are refused."""
    m = _DURATION_RE.match(as_written.strip())
    if m is None:
        raise Reject(f"cannot read the duration {as_written!r}")
    lead = (m.group("about") or "").lower()
    if lead and lead not in _ABOUT:
        raise Reject(f"the duration {as_written!r} is a bound, not a length")
    if m.group("a"):
        n = 1
    elif m.group("n").isdigit():
        n = int(m.group("n"))
    elif m.group("n").lower() in _NUMBER_WORDS:
        n = _NUMBER_WORDS[m.group("n").lower()]
    else:
        raise Reject(f"cannot read the number in {as_written!r}")
    unit = _UNITS[m.group("unit").lower()]
    v = n * unit
    if lead:
        return round(v * 0.75), round(v * 1.25)
    return v, v + unit - 1


# A message quoted after a verb of saying: 'PETROV texted REYES: "its done"'. A quoted contact
# name ('saved as "Marc Garage"') is not a message.
_QUOTED_MESSAGE = re.compile(
    r"\b(?:wrote|texted|told|sent|said|messaged|replied|asked|posted)\b[^\"“]{0,60}[\"“]",
    re.IGNORECASE,
)


def coverage_gap(claim: Claim, proposals: list[Proposal]) -> str | None:
    """What the kept proposals leave untested that the claim states, or None.

    A claim must not be judged on its easy parts: its key template must be there, a stated
    date must be tested by some time range, a stated time of day by a range that states one,
    and a quoted message in a communication claim by a sender assumption.
    """
    kept = {p.template_id for p in proposals}
    needed = REQUIRED_TEMPLATES.get(claim.claim_type, frozenset())
    if needed and not (kept & needed):
        return f"no usable {' or '.join(sorted(needed))} assumption"
    windows = [p.params.get("window") for p in proposals if isinstance(p.params, dict)]
    raws = [w.raw for w in windows if w is not None]
    if date_mentions(claim.text) and not raws:
        return "the claim states a date but no assumption tests a time range"
    if time_mentions(claim.text) and not any(time_mentions(r) for r in raws):
        return "the claim states a time of day but no time range states one"
    if (
        claim.claim_type is ClaimType.COMMUNICATION
        and _QUOTED_MESSAGE.search(claim.text)
        and "sender" not in kept
    ):
        return "the claim quotes a message but no assumption tests who sent it"
    return None


# ---------------------------------------------------------------- the filler


class LocalAssumptionFiller:
    """A Filler for TemplateAssumptionBuilder, backed by a local JsonModel."""

    def __init__(
        self,
        model: JsonModel,
        conn: sqlite3.Connection,
        *,
        template: str | None = None,
        prompts_dir: Path = PROMPTS_DIR,
        recorder: CallRecorder | None = None,
    ) -> None:
        self.model = model
        self.conn = conn
        self.template = template if template is not None else load_prompt(PROMPT_FILE, prompts_dir)
        missing = PLACEHOLDERS - required_placeholders(self.template)
        if missing:
            raise ValueError(f"assumptions prompt lacks placeholders: {sorted(missing)}")
        self.prompt_version = prompt_version(self.template)
        self.recorder = recorder if recorder is not None else CallRecorder()
        self.model_runs: tuple[ModelRun, ...] = ()
        self.drops: list[FillerDrop] = []
        self._data: CaseData | None = None

    # -- case vocabulary, read once

    @property
    def data(self) -> CaseData:
        if self._data is None:
            self._data = CaseData(self.conn)
        return self._data

    def channels(self) -> list[str]:
        apps = {a.app for a in self.data.accounts.values()}
        apps |= {r[0] for r in self.conn.execute("SELECT DISTINCT app FROM threads")}
        return sorted(apps | {"call"}, key=str.lower)

    def paragraph_text(self, claim: Claim) -> str:
        row = self.conn.execute(
            "SELECT text FROM govdoc_paragraphs WHERE id = ?", (claim.paragraph_id,)
        ).fetchone()
        return row[0] if row else ""

    # -- Filler

    def __call__(self, claim: Claim, allowed: list[Template]) -> list[Proposal]:
        allowed_ids = {t.id for t in allowed}
        run_id = model_run_id(self.model)
        if run_id is None:
            self._drop(claim, None, "model has no run id", None)
            return []
        para = self.paragraph_text(claim)
        channels = self.channels()
        prompt = fill_prompt(
            self.template,
            {
                "claim": claim.text,
                "paragraph": para or "(paragraph not available)",
                "templates": "\n".join(
                    f"- {t.id}: {TEMPLATE_HELP.get(t.id, t.id)}"
                    for t in sorted(allowed, key=lambda t: t.id)
                ),
                "channels": ", ".join(channels),
            },
        )
        schema = fill_schema(allowed_ids, channels)
        try:
            items, call = run_json_call(
                self.model, self.recorder, run_id, (claim.id,), prompt, schema, _validate_list
            )
        except BadModelOutput as e:
            self._drop(claim, None, e.reason, e.call.id if e.call else None)
            return []

        out: list[Proposal] = []
        for i, item in enumerate(items):
            try:
                p = _ProposalOut.model_validate(item)
                if p.template_id not in allowed_ids:
                    raise Reject(f"template {p.template_id!r} is not allowed for this claim")
                out.append(self._resolve(claim, para, p))
            except ValidationError as e:
                self._drop(claim, i, f"wrong shape: {e.error_count()} errors", call.id)
            except Reject as e:
                self._drop(claim, i, str(e), call.id)

        gap = coverage_gap(claim, out)
        if gap:
            self._drop(claim, None, f"{gap}; the claim stays unproven", call.id)
            return []
        return out

    def _drop(self, claim: Claim, index: int | None, reason: str, call_id: str | None) -> None:
        self.drops.append(FillerDrop(claim_id=claim.id, index=index, reason=reason,
                                     model_call_id=call_id))  # fmt: skip

    # -- words to typed parameters

    def _resolve(self, claim: Claim, para: str, p: _ProposalOut) -> Proposal:
        tpl = TEMPLATES[p.template_id]
        texts = (claim.text, para)
        params: dict[str, Any] = {}

        for value in [*p.people, *p.handles, *p.phones, *(a.as_written for a in p.accounts)]:
            if not _verbatim(value, *texts):
                raise Reject(f"{value!r} is not written in the claim or its paragraph")
        if p.quoted_text:
            if not _verbatim(p.quoted_text, claim.text):
                raise Reject("quoted_text is not written in the claim")
            params["quoted_text"] = p.quoted_text.strip()

        device_ids = [self._device(ph) for ph in p.phones]
        if device_ids:
            params["device_ids"] = sorted(set(device_ids))
        if p.people:
            params["person_ids"] = sorted({self._person(n) for n in p.people})

        channels = self._channels(claim.text, p.channels)
        if channels:
            params["channels"] = channels

        account_ids: set[str] = set()
        for acc in p.accounts:
            account_ids |= self._accounts(acc, device_ids)
        handles = [h.strip() for h in p.handles]
        if handles:
            if "handles" not in tpl.allowed:
                raise Reject(f"template {tpl.id!r} does not take handles")
            params["handles"] = handles  # the checks resolve them from the data
        if account_ids:
            params["account_ids"] = sorted(account_ids)

        if p.count is not None:
            params["count_op"] = count_op(claim.text, p.count.value)
            params["expected_count"] = p.count.value

        if p.duration is not None:
            if not _verbatim(p.duration.as_written, claim.text):
                raise Reject("the duration's words are not written in the claim")
            params["duration_s"] = duration_range(p.duration.as_written)

        if p.window is not None:
            params["window"] = self._window(claim.text, para, p.window, device_ids, tpl.id)

        return Proposal(p.template_id, params, is_core=True)

    def _person(self, name: str) -> str:
        n = _nfc(name.strip()).casefold()
        hits = []
        for pid, full in self.conn.execute("SELECT id, name FROM persons ORDER BY id"):
            parts = _nfc(full.strip()).casefold().split()
            if n == " ".join(parts) or (parts and n == parts[-1]):
                hits.append(pid)
        if len(hits) != 1:
            found = "no person" if not hits else f"{len(hits)} persons"
            raise Reject(f"{name!r} matches {found} the expert created")
        return hits[0]

    def _device(self, phone: str) -> str:
        want = re.sub(r"\s+", "", phone.casefold())
        hits = [
            did
            for did, sid, label in self.conn.execute(
                "SELECT id, source_id, label FROM devices ORDER BY id"
            )
            if want in {re.sub(r"\s+", "", x.casefold()) for x in (did, sid, label) if x}
        ]
        if len(hits) != 1:
            raise Reject(f"phone {phone!r} matches {len(hits)} devices")
        return hits[0]

    def _channels(self, claim_text: str, names: list[str]) -> list[str]:
        vocab = {c.casefold(): c for c in self.channels()}
        out = []
        for name in names:
            canon = vocab.get(name.strip().casefold())
            if canon is None:
                raise Reject(f"channel {name!r} is not an app in this case")
            words = CHANNEL_WORDS.get(canon.casefold(), (canon.casefold(),))
            if not any(_has_word(claim_text, w) for w in words):
                raise Reject(f"the claim does not name the channel {canon!r}")
            out.append(canon)
        return sorted(set(out), key=str.lower)

    def _accounts(self, acc: _Account, device_ids: list[str]) -> set[str]:
        app = acc.app.strip().casefold()
        ident = re.sub(r"(?i)^(user\s*id|id|number|no\.)\s*", "", acc.as_written.strip())
        want = key(acc.app, ident)
        sources = set(self.data.sources_for(device_ids)) if device_ids else None
        hits = {
            a.id
            for a in self.data.accounts.values()
            if a.key == want
            and a.app.casefold() == app
            and (sources is None or a.source_id in sources)
        }
        if not hits:
            raise Reject(f"{acc.as_written!r} on {acc.app} matches no account in the case")
        return hits

    def _window(
        self, claim_text: str, para: str, w: _Window, device_ids: list[str], template_id: str
    ) -> Any:
        if not _verbatim(w.as_written, claim_text):
            raise Reject("the window's words are not written in the claim")
        try:
            start = datetime.fromisoformat(w.start)
            end = datetime.fromisoformat(w.end)
        except ValueError:
            raise Reject("window start or end is not 'YYYY-MM-DDTHH:MM'") from None
        if start.tzinfo is not None or end.tzinfo is not None:
            raise Reject("window times must be wall-clock, without an offset")
        if w.zone == "UTC":
            if not re.search(r"\b(UTC|GMT)\b", w.as_written):
                raise Reject("the range does not say UTC")
            tz = "UTC"
        else:
            tz = self._phone_zone(device_ids)
        check_window(start, end, w.as_written, claim_text, para, template_id)
        try:
            return local_window(start, end, tz, w.as_written.strip())
        except ValueError as e:
            raise Reject(str(e)) from None

    def _phone_zone(self, device_ids: list[str]) -> str:
        rows = self.conn.execute("SELECT id, timezone FROM devices ORDER BY id").fetchall()
        zones = {tz for did, tz in rows if not device_ids or did in device_ids}
        if len(zones) != 1 or None in zones:
            raise Reject("the phones do not share one known time zone; name the phone")
        (tz,) = zones
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise Reject(f"unknown phone time zone {tz!r}") from None
        return tz


def _validate_list(obj: dict[str, object]) -> list[dict[str, Any]]:
    try:
        return _FillOut.model_validate(obj).assumptions
    except ValidationError as e:
        raise BadModelOutput(f"wrong shape: {e.errors(include_url=False)}", None) from None


def create(
    conn: sqlite3.Connection, *, model: LocalModel | None = None
) -> Callable[[Claim, list[Template]], list[Proposal]]:
    """The filler for core.audit.assumptions.create(conn, filler=...). Raises if the signed
    prompt or the model config is missing."""
    template = load_prompt(PROMPT_FILE)
    # The per-call schema is fixed by the templates and channels the prompt lists, so the
    # empty schema records its shape for stored-output reuse.
    opened = open_run(conn, "assumptions", template, model=model, schema=fill_schema((), ()))
    filler = LocalAssumptionFiller(opened.port, conn, template=template, recorder=opened.recorder)
    filler.model_runs = (opened.run,)
    return filler
