"""The local-model filler for the assumption templates (core/audit/assumptions.py).

The model reads one claim and its paragraph and proposes which templates the claim rests on,
with each value written exactly as the document writes it: names ("PETROV"), phones ("Item 1"),
numbers and handles ("+1 (212) 555-0122", "@northstar"), apps, quoted words, a count and a time
range in the document's own words. It never writes an id, a time zone or a UTC time.

Code then turns those words into typed AssumptionParams, and drops anything it cannot tie to
the document or the case data. It fails closed at every step:

- Every value must appear verbatim in the claim or its paragraph. Anything else is dropped.
- Names resolve to persons the expert created (exact name or surname, one match only).
  Phones resolve to devices by id, label or a name the expert gave the device ("TARGET PHONE",
  one match only). Numbers and user ids resolve to accounts by app
  and identifier, the way the checks match accounts. A handle stays a handle where the
  template takes one, and the checks resolve it from the data; a template that takes no
  handles drops the proposal. A handle the model wrote as an account ("@northstar") is kept as
  a handle the same way. Zero or several matches for any other value drop it too.
  When the words are not an account's identifier, three more lookups are tried, each with
  one answer only. A number written another way ("(919) 888-7386" for "+19198887386",
  `phone_digits`) finds its account. A person the expert created, written as an account
  ("SUBJECT-1" on Signal), is that person, whose accounts the checks take from confirmed
  stipulations and links; if an account not confirmed as theirs carries the same name, the
  proposal is refused. The display name of exactly one account finds that account. A
  number or a display name finds an account only on a phone app or on an app the claim
  names, so the words alone never pick the app. Accounts are never merged.
- A channel must be named in the claim ("Telegram", or "texted" for SMS, "call" for calls).
  A model never narrows a search to a channel the document did not name. An export's own
  name for an app ("Wickr Pro", "Kik Messenger", "Native Messages") is named by the word a
  document uses for it ("Wickr", "Kik", "iMessage"; `APP_ALIASES`) only when no other app in
  the case goes by that word. A capitalized word counts only as written or in capitals
  ("Teams", never "the teams met"). No count or absence is read from an app that holds more
  than the word names (iOS "Native Messages" holds iMessage and SMS together).
- A call's stated length ("about two minutes") is turned into seconds by code.
- A count's number must appear in the claim, and its comparison ("at least", "at most",
  exactly) is read from the claim's words by code, not taken from the model.
- A time range must match the dates and times the document states (see `check_window`).
  The zone is the phone's zone from the case data; UTC only if the document says UTC. A
  zone the document writes beside the time ("11:11 a.m. EDT") is read by code, never taken
  from the model, and the phone's zone must have its offset then, or the range is refused.
  Code reads the claim's own plain dates and times (`stated_windows`: "On March 12, 2026",
  "between March 20 and March 23, 2026", "At about 7:58 p.m. on March 9, 2026", "On April
  30, 2023, at approximately 11:11 a.m. EDT") and builds those ranges itself, the way the
  signed case01 sheet writes them. A time of day it cannot read is never widened to the
  whole day. When the model's range
  is refused or missing, the range the claim states on the same day (or its only one) is used
  instead, and still goes through `check_window`. A quoted message the claim dates gets its
  time assumption from code when the model gave none: the sender's parties and words with the
  claim's one stated range. The model's arithmetic is never needed for a plain stated date.
- A sender assumption the model left without a party gets the person the claim names as the
  writer of the quoted words ("PETROV wrote", "PETROV texted REYES"), read by code
  (`stated_sender`) from the verb nearest before the quote, when that name matches exactly one
  person the expert created. Otherwise it stays without a party and
  is refused as before.
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
from core.audit.checks._common import Account, CaseData, key, namespace, person_party
from core.contracts import Claim, ClaimType, ModelRun
from core.review.device_names import logged_names, name_key
from core.zones import resolve_zone

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
# Words a document uses for an app that real exports name another way (a UFDR says "Wickr
# Pro", "Kik Messenger", "Native Messages"). Such a word names the export's app only when no
# other app in the case goes by it too. A word with a capital letter counts only as written
# here or in capitals ("Teams" or "TEAMS", never "the teams met"); a lowercase one in any case.
APP_ALIASES: dict[str, tuple[str, ...]] = {
    "wickr pro": ("Wickr",),
    "wickr me": ("Wickr",),
    "kik messenger": ("Kik",),
    "microsoft teams": ("Teams",),
    "native messages": ("iMessage", "iMessages", "MMS", *CHANNEL_WORDS["sms"]),
}
# Apps that hold more than the word that names them: iOS "Native Messages" holds iMessage and
# SMS together.
WIDER_APPS = frozenset({"native messages"})
# Checks whose answer depends on every record on the app they search. On a wider app a count
# would count, and an absence would fail on, messages the claim does not name.
WHOLE_APP_TEMPLATES = frozenset({"message_count", "no_contact"})


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


def _has_alias(text: str, alias: str) -> bool:
    """An APP_ALIASES word in the text: any case when it is lowercase, else as written or in
    capitals."""
    if alias.islower():
        return _has_word(text, alias)
    return any(
        re.search(rf"(?<![A-Za-z0-9]){re.escape(a)}(?![A-Za-z0-9])", text)
        for a in (alias, alias.upper())
    )


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
_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WD_RE = "|".join(_WEEKDAYS)
_NUM_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_YEAR_RE = re.compile(r"\b(19\d\d|20\d\d)\b")
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?![a-z])", re.IGNORECASE)
_TIME24_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b(?!\s*(?:a\.?m|p\.?m))", re.IGNORECASE)
# "between 9 and 11 p.m.": the bare first hour takes the second time's a.m. or p.m.
_BARE_HOUR_RE = re.compile(
    r"\b(?:between|from)\s+(\d{1,2})(?::(\d{2}))?\s*(?:and|to|until|till|through|thru|-|–)\s*$",
    re.IGNORECASE,
)

OPEN_START = ("before", "prior to", "until", "up to")
OPEN_END = ("after", "since", "onward", "onwards", "later")

# Zones a document writes beside a time ("11:11 a.m. EDT"). An abbreviation is its fixed UTC
# offset. A generic name ("ET", "Eastern Time") is the zone whose offset on that day it means.
# The phone's zone must have that offset at the time (`LocalAssumptionFiller._read_zone`).
_H = timedelta(hours=1)
WRITTEN_ZONES: dict[str, timedelta | str] = {
    "utc": timedelta(0),
    "gmt": timedelta(0),
    "est": -5 * _H,
    "edt": -4 * _H,
    "cst": -6 * _H,
    "cdt": -5 * _H,
    "mst": -7 * _H,
    "mdt": -6 * _H,
    "pst": -8 * _H,
    "pdt": -7 * _H,
    "akst": -9 * _H,
    "akdt": -8 * _H,
    "hst": -10 * _H,
    "eastern standard time": -5 * _H,
    "eastern daylight time": -4 * _H,
    "central standard time": -6 * _H,
    "central daylight time": -5 * _H,
    "mountain standard time": -7 * _H,
    "mountain daylight time": -6 * _H,
    "pacific standard time": -8 * _H,
    "pacific daylight time": -7 * _H,
    "et": "America/New_York",
    "ct": "America/Chicago",
    "mt": "America/Denver",
    "pt": "America/Los_Angeles",
    "eastern time": "America/New_York",
    "central time": "America/Chicago",
    "mountain time": "America/Denver",
    "pacific time": "America/Los_Angeles",
}
# Abbreviations only in capitals ("est" is not a zone); spelled-out names in any case.
_ZONE = (
    r"(?:(?-i:UTC|GMT|AKST|AKDT|[ECMP][SD]T|HST|[ECMP]T)"
    r"|(?:eastern|central|mountain|pacific)(?:\s+(?:standard|daylight))?\s+time)\b"
)
_CLOCK_END = r"(?:\b[ap]\.?m\.?|\bnoon|\b\d{1,2}:\d{2})"
_TIMED_ZONE_RE = re.compile(rf"{_CLOCK_END}\s*\(?(?P<z>{_ZONE})", re.IGNORECASE)
_ENDS_TIMED_RE = re.compile(rf"{_CLOCK_END}\s*$", re.IGNORECASE)
_ENDS_DATE_RE = re.compile(r"\b(?:19|20)\d\d\s*$")


def _zone_opt(name: str) -> str:
    """An optional zone right after a time: "11:11 a.m. EDT", "11:11 a.m. (EDT)"."""
    return rf"(?:\s*\(?(?P<{name}>{_ZONE})\)?)?"


def _hm(off: timedelta | None) -> str:
    """'-04:00' for an offset of minus four hours."""
    if off is None:
        return "?"
    mins = int(off.total_seconds() // 60)
    return f"{'-' if mins < 0 else '+'}{abs(mins) // 60:02d}:{abs(mins) % 60:02d}"


def zone_offset(zone: str, at: datetime) -> timedelta:
    """The UTC offset a zone the document writes means at this wall-clock time."""
    z = WRITTEN_ZONES[" ".join(zone.split()).casefold()]
    if isinstance(z, timedelta):
        return z
    return at.replace(tzinfo=ZoneInfo(z)).utcoffset() or timedelta(0)


def written_zone(as_written: str, claim: str = "") -> str | None:
    """The zone the range's own words give its times in, or None when they give none. Only a
    zone right after a time ("11:11 a.m. EDT", "noon (ET)") or a date ("March 3, 2026 (UTC)")
    counts, and so does one the claim writes right after the range's words ("... 11:11 a.m."
    then " EDT" in the claim). Raises Reject when they give more than one."""
    plain = _unquoted(as_written)
    found = [m.group("z") for m in _TIMED_ZONE_RE.finditer(plain)]
    for d in _DATE_RE.finditer(plain):
        zm = _DATE_ZONE_RE.match(plain[d.end() :])
        if zm is not None:
            found.append(zm.group("z") or zm.group("z2"))
    text, words = _nfc(claim), _nfc(as_written.strip())
    if not found and words:
        timed = _ENDS_TIMED_RE.search(words)
        dated = _ENDS_DATE_RE.search(words)
        i = text.find(words) if timed or dated else -1
        while i >= 0:
            rest = text[i + len(words) :]
            zm = (
                re.match(rf"\s*\(?(?P<z>{_ZONE})", rest, re.IGNORECASE)
                if timed
                else _DATE_ZONE_RE.match(rest)
            )
            if zm is not None:
                found.append(zm.group("z") or (zm.groupdict().get("z2") or ""))
            i = text.find(words, i + 1)
    if len({str(WRITTEN_ZONES[" ".join(z.split()).casefold()]) for z in found}) > 1:
        raise Reject("the range names more than one time zone")
    return found[0] if found else None


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
        t = _clock(m.group(1), m.group(2), m.group(3))
        if t is None:
            continue
        bare = _BARE_HOUR_RE.search(text[max(0, m.start() - 16) : m.start()])
        if bare is not None:
            first = _clock(bare.group(1), bare.group(2), m.group(3))
            if first is not None and first < t:
                out.append(first)
        out.append(t)
    for m in _TIME24_RE.finditer(text):
        out.append(time(int(m.group(1)), int(m.group(2))))
    if _has_word(text, "midnight"):
        out.append(time(0, 0))
    if _has_word(text, "noon"):
        out.append(time(12, 0))
    return out


def _clock(h: str | None, mi: str | None, ap: str | None, word: str | None = None) -> time | None:
    """A time of day as written, or None when it is not one plain time. "midnight" is None:
    it may be the start or the end of the day."""
    if word is not None:
        return time(12, 0) if word.lower() == "noon" else None
    if h is None or ap is None:
        return None
    hour, minute = int(h), int(mi or 0)
    if not 1 <= hour <= 12 or minute > 59:
        return None
    return time((hour % 12) + (12 if ap.lower().startswith("p") else 0), minute)


def _clock_re(p: str, ap_optional: bool = False) -> str:
    q = "?" if ap_optional else ""
    return (
        rf"(?:(?P<{p}h>\d{{1,2}})(?::(?P<{p}m>\d{{2}}))?\s*(?P<{p}ap>a\.?m\.?|p\.?m\.?){q}(?![a-z])"
        rf"|(?P<{p}w>noon|midnight)\b)"
    )


# "between 9 and 11 p.m.", "from 9 p.m. to 11 p.m.", "between noon and 2 p.m."
_RANGE_TIME = (
    rf"\b(?:between|from)\s+{_clock_re('a', ap_optional=True)}\s*"
    rf"(?:and|to|until|till|through|thru|-|–)\s*{_clock_re('b')}"
)
_RANGE_TIME_RE = re.compile(_RANGE_TIME, re.IGNORECASE)


def _time_range(m: re.Match[str]) -> tuple[time, time] | None:
    """The two times of a _RANGE_TIME match, or None when they are not a plain range on one
    day: midnight, an end not after the start (it may cross midnight), or a bare first hour
    that cannot take the end's a.m. or p.m. ("between 11 and noon")."""
    end = _clock(m.group("bh"), m.group("bm"), m.group("bap"), m.group("bw"))
    if end is None:
        return None
    if m.group("aw") is not None:
        start = _clock(None, None, None, m.group("aw"))
    else:
        start = _clock(m.group("ah"), m.group("am"), m.group("aap") or m.group("bap"))
    if start is None or start >= end:
        return None
    return start, end


# Quoted words: "...", “...”, ‘...’ and '...' (an apostrophe inside a word opens or closes
# no quote).
_QUOTE_SPAN_RE = re.compile(
    r"\"[^\"\n]*\"|“[^”\n]*”"
    r"|‘(?:[^’\n]|(?<=\w)’(?=\w))*’"  # 'I’ll': an apostrophe inside a word closes nothing
    r"|(?<!\w)'(?:[^'\n]|(?<=\w)'(?=\w))*'(?!\w)"
)


def _unquoted(text: str) -> str:
    """The text with quoted words blanked out, same length, so a time in a quoted message
    ("meet me at noon") is not read as when something happened."""
    return _QUOTE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _date_stated(d: date, mentions: list[_DateMention], years: set[int]) -> bool:
    for m in mentions:
        if (m.month, m.day) != (d.month, d.day):
            continue
        if (m.year == d.year) if m.year is not None else (d.year in years):
            return True
    return False


_WD_BEFORE_RE = re.compile(rf"\b({_WD_RE}),?\s+$", re.IGNORECASE)
# "two days after", "shortly after": the range is offset from the date by words code does
# not read
_OFFSET_AFTER_RE = re.compile(
    r"\b(?:minutes?|hours?|days?|nights?|weeks?|months?|years?|shortly|soon|"
    r"right|just|immediately|sometime|long)\s+after\s+$",
    re.IGNORECASE,
)


def weekday_mismatch(text: str, years: set[int]) -> bool:
    """True when the text gives a weekday beside a date ("Tuesday, March 3, 2025") that is
    not that date's weekday. A date whose year is not plain is not judged."""
    for m in _DATE_RE.finditer(text):
        wd = _WD_BEFORE_RE.search(text[max(0, m.start() - 12) : m.start()])
        if wd is None:
            continue
        y = int(m.group(3) or m.group(6) or 0) or (next(iter(years)) if len(years) == 1 else 0)
        if not y:
            continue
        try:
            d = date(y, _MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            return True
        if _WEEKDAYS.index(wd.group(1).lower()) != d.weekday():
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
      "before X" may leave the start open and end at X; "after X" may leave the end open and
      starts at midnight the day after X ("on or after X" and "since X" start on X).
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

    for rm in _RANGE_TIME_RE.finditer(as_written):
        # "between 9 and 11 p.m.": the start is near 9 p.m. and the end near 11 p.m., not
        # both near either one
        rng = _time_range(rm)
        if rng is None:
            raise Reject("the stated time range is not a plain range on one day")
        if not open_start and not _near(start, [rng[0]]):
            raise Reject("window start is not near the start of the stated time range")
        if not open_end and not _near(end, [rng[1]]):
            raise Reject("window end is not near the end of the stated time range")
    # "after March 3" leaves March 3 out: the range starts at midnight on March 4. "on or
    # after" and "since" keep the day itself.
    if weekday_mismatch(as_written, years) or weekday_mismatch(claim, years):
        raise Reject("a weekday the document gives is not that date's weekday")
    after = []
    for m in _DATE_RE.finditer(as_written):
        head = as_written[: m.start()]
        wd = _WD_BEFORE_RE.search(head)
        if wd is not None:
            head = head[: wd.start()]  # "after Monday, March 3"
        if not re.search(r"\bafter\s+$", head, re.IGNORECASE):
            continue
        if _OFFSET_AFTER_RE.search(head):
            raise Reject("a range offset from a date ('two days after') is not read")
        if re.search(r"\bon\s+or\s+after\s+$", head, re.IGNORECASE):
            continue
        y = int(m.group(3) or m.group(6) or 0) or None
        after.append(_DateMention(_MONTHS[m.group(1).lower()], int(m.group(2)), y))
    if after and not times:
        if start.time() != time(0, 0) or not _date_stated(
            start.date() - timedelta(days=1), after, years
        ):
            raise Reject("a range 'after' a date starts at midnight the day after it")
    elif not open_start:
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


ABOUT_MINUTES = 8  # "at about 7:58 p.m." is 7:50 to 8:05 (the signed case01 sheet, C09)
# the time is tied to the date right after it: "9 p.m. on March 3", "9 p.m. on Monday, March 3"
_TIED = rf"\s*,?\s*(?:on\s+)?(?:(?P<wd>{_WD_RE}),?\s+)?$"
_AT_TIME_RE = re.compile(
    rf"\b(?:at\s+)?(?P<about>about\s+|approximately\s+|around\s+)?{_clock_re('t')}"
    rf"{_zone_opt('z')}{_TIED}",
    re.IGNORECASE,
)
_AT_RANGE_RE = re.compile(_RANGE_TIME + _zone_opt("z") + _TIED, re.IGNORECASE)
# the date first, then its time: "On April 30, 2023, at approximately 11:11 a.m. EDT"
_THEN = r"^\s*,?\s*"
_THEN_TIME_RE = re.compile(
    rf"{_THEN}(?P<at>at\s+)?(?P<about>(?:about|approximately|around)\s+)?{_clock_re('t')}"
    rf"{_zone_opt('z')}",
    re.IGNORECASE,
)
_THEN_RANGE_RE = re.compile(_THEN + _RANGE_TIME + _zone_opt("z"), re.IGNORECASE)
# a time with no a.m. or p.m. right after the date ("On May 2, 2026, between 9 and 11, ..."),
# not a count ("between 10 and 12 messages")
_THEN_LOOSE_RE = re.compile(
    rf"{_THEN}(?:at|between|from)\s+(?:about\s+|approximately\s+|around\s+)?\d{{1,2}}"
    r"(?:\s*(?:and|to|until|till|through|thru|-|–)\s*\d{1,2})?"
    r"(?:\s*(?:hours|hrs|o'clock))?\s*(?:[,.;]|$)",
    re.IGNORECASE,
)
# every time of day the text writes, so one that no range read is never widened to a day
_ANY_TIME_RE = re.compile(
    rf"{_TIME_RE.pattern}|{_TIME24_RE.pattern}|\b(?:noon|midnight)\b", re.IGNORECASE
)
# a time just before the one read, joined to it: a range code did not read as one
_JOINED_RE = re.compile(r"(?:and|to|until|till|through|thru|-|–)\s*$", re.IGNORECASE)
# a time with no a.m. or p.m. tied to the date ("between 9 and 11 on", "at 21:00 on")
_LOOSE_TIME_RE = re.compile(
    r"\b(?:at|about|around|approximately|between|from|and|to|until|till|through|thru)\s+"
    r"\d{1,2}(?::\d{2})?(?:\s*(?:hours|hrs))?" + _TIED,
    re.IGNORECASE,
)
_LEAD_RE = re.compile(r"\b(?:on|between|from)\s+$", re.IGNORECASE)
# after a plain date, a zone in brackets, or an abbreviation that is never initials ("ET" or
# "PT" after a date may be a person)
_DATE_ZONE_RE = re.compile(
    rf"\s*(?:\((?P<z>{_ZONE})\)|,?\s*(?P<z2>(?-i:UTC|GMT|AKST|AKDT|[ECMP][SD]T|HST))\b)",
    re.IGNORECASE,
)
_FROM_RE = re.compile(r"\b(?:between|from)\s+$", re.IGNORECASE)
# a word right before the range read that leaves one end open or names a second end: "after 9
# p.m. on", "from 9 p.m. on", "starting on", "as of"
_OPEN_LEAD_RE = re.compile(
    r"\b(?:after|before|since|until|till|by|from|between|starting|beginning|commencing|"
    r"as\s+of|prior\s+to|up\s+to|no\s+(?:later|earlier)\s+than)\s+$",
    re.IGNORECASE,
)
# words right after the range read that leave its end open: "at 9 p.m. onward", "or later"
_OPEN_TAIL_RE = re.compile(
    r"\s*,?\s*(?:(?:and|or)\s+(?:later|after|afterwards?|thereafter|onwards?|beyond|since|"
    r"before|earlier|prior)|onwards?|forward|thereafter|afterwards?|later)\b",
    re.IGNORECASE,
)
_JOIN_AHEAD_RE = re.compile(r"\s*(?:(?:and|to|until|till|through|thru)\b|[-–])", re.IGNORECASE)


@dataclass(frozen=True)
class StatedWindow:
    """A plain range the claim states in its own words: wall clock, end exclusive. `zone` is
    the zone the words give the time in ("EDT"), or None when they give none."""

    raw: str
    start: datetime
    end: datetime
    zone: str | None = None


def stated_windows(text: str, context: str = "") -> list[StatedWindow] | None:
    """Every date the text states, as the range it plainly means, or None when any date is
    not plain: an open range ("before", "after", "since", "until", "from 9 p.m. on", "at 9
    p.m. onward", "or later"), a date with no year in the text or its context, or a time code
    cannot pin to one date.

    - "March 12, 2026": the whole day.
    - "March 20 and March 23, 2026" or "March 10 through March 31, 2026": first day to the
      end of the last.
    - "2:31 a.m. on March 5, 2026" or "On March 5, 2026, at 2:31 a.m.": that minute.
      "about 7:58 p.m." (or "approximately", "around") is 8 minutes either side. "noon" is
      12:00. "midnight" is not read: it may be the start or the end of the day.
    - "Between 9 and 11 p.m. on May 2, 2026", "From 9 p.m. to 11 p.m. ..." or "On May 2, 2026,
      between 9 and 11 p.m.": 9:00 p.m. through the 11:00 p.m. minute. A bare first hour takes
      the end's a.m. or p.m.; a range that would cross midnight, or carries "about", is not
      read.
    - A zone written right after the time ("11:11 a.m. EDT", "(ET)", "Eastern Time") is kept
      in `zone`, for the filler to check against the phone's zone.
    - Any time of day the text writes outside quoted words that no range above read (a
      second time, "beginning at", "after 10 a.m.") makes the whole answer None: a time is
      never widened to the whole day.
    """
    years = {int(y) for y in _YEAR_RE.findall(text + " " + context)}
    out: list[StatedWindow] = []
    read: list[tuple[int, int]] = []  # the spans of `plain` the ranges were read from
    plain = _unquoted(text)  # a date or time in quoted words is the message's, not the claim's
    if weekday_mismatch(plain, years):
        return None  # a weekday that is not the date's: never pick one
    for m in _DATE_RE.finditer(plain):
        before = plain[max(0, m.start() - 64) : m.start()]
        if any(_has_word(before[-12:], w) for w in (*OPEN_START, *OPEN_END)):
            return None
        y_end = int(m.group(6)) if m.group(6) else None
        y1 = int(m.group(3)) if m.group(3) else y_end
        if y1 is None:
            if len(years) != 1:
                return None
            (y1,) = years
        try:
            d1 = date(y1, _MONTHS[m.group(1).lower()], int(m.group(2)))
            if m.group(5):
                mon2 = _MONTHS[m.group(4).lower()] if m.group(4) else d1.month
                d2 = date(y_end or y1, mon2, int(m.group(5)))
            else:
                d2 = d1
        except ValueError:
            return None
        if d2 < d1:
            return None
        start_i, end_i = m.start(), m.end()
        after = plain[m.end() : m.end() + 96]
        rng = _AT_RANGE_RE.search(before)
        at = _AT_TIME_RE.search(before) if rng is None else None
        then: re.Match[str] | None = None
        if rng is None and at is None:
            rng = then = _THEN_RANGE_RE.match(after)
            if rng is None:
                at = then = _THEN_TIME_RE.match(after)
                if at is not None and not (at.group("at") or at.group("about")):
                    at = then = None  # "On May 2, 2026, 9 p.m." ties nothing
        if (rng is not None or at is not None) and m.group(5):
            return None  # a time of day on a range of dates: leave it to the model
        tied = rng or at
        if tied is not None and then is None and tied.group("wd"):
            if _WEEKDAYS.index(tied.group("wd").lower()) != d1.weekday():
                return None  # the weekday does not match the date: never pick one
        if then is not None:
            end_i = m.end() + then.end()
            if (
                _JOINED_RE.search(before)
                or _FROM_RE.search(before)
                or _JOIN_AHEAD_RE.match(plain[end_i:])
            ):
                return None  # "between March 20 at 9 p.m. and March 21 at 1 a.m.": not read
            lead = _LEAD_RE.search(before)
            if lead is not None:
                start_i = m.start() - len(before) + lead.start()
        elif tied is not None:
            start_i = m.start() - len(before) + tied.start()
        if rng is not None:
            times = _time_range(rng)
            if times is None:
                return None
            start = datetime.combine(d1, times[0])
            end = datetime.combine(d1, times[1]) + timedelta(minutes=1)  # through the end minute
        elif at is not None:
            if then is None and _JOINED_RE.search(before[: at.start()]):
                return None  # "about 9 p.m. and 11 p.m. on ...": a range not read as one
            tt = _clock(at.group("th"), at.group("tm"), at.group("tap"), at.group("tw"))
            if tt is None:
                return None
            t = datetime.combine(d1, tt)
            if at.group("about"):
                start, end = (
                    t - timedelta(minutes=ABOUT_MINUTES),
                    t + timedelta(minutes=ABOUT_MINUTES),
                )
            else:
                start, end = t, t + timedelta(minutes=1)
        else:
            if _LOOSE_TIME_RE.search(before) or _THEN_LOOSE_RE.match(after):
                return None  # a time code cannot read: never widen it to the whole day
            lead = _LEAD_RE.search(before)
            if lead is not None:
                start_i = m.start() - len(before) + lead.start()
            start = datetime.combine(d1, time(0, 0))
            end = datetime.combine(d2 + timedelta(days=1), time(0, 0))
        zone = tied.group("z") if tied is not None else None
        if zone is None and then is None:  # right after the date: "on March 3, 2026 (UTC)"
            zm = _DATE_ZONE_RE.match(plain[end_i:])
            if zm is not None:
                zone, end_i = zm.group("z") or zm.group("z2"), end_i + zm.end()
        if _OPEN_LEAD_RE.search(plain[:start_i]) or _OPEN_TAIL_RE.match(plain[end_i:]):
            return None  # "after 9 p.m. on ...", "at 9 p.m. onward": an open range, not read
        if rng is None and not m.group(5) and _FROM_RE.search(before):
            return None  # "from January 9, 2026" with no end: not read
        read.append((start_i, end_i))
        out.append(StatedWindow(text[start_i:end_i].strip(), start, end, zone))
    if _NUM_DATE_RE.search(text):
        return None  # numeric dates (3/12/2026) may be either order; never guess
    for t in _ANY_TIME_RE.finditer(plain):
        if not any(a <= t.start() and t.end() <= b for a, b in read):
            return None  # a time no range was read from: never widen it to the whole day
    return out


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


# The writer of a quoted message, as the claim names it: 'PETROV wrote', 'Daniel Petrov texted
# REYES'. One to three capitalised words right before a verb of writing.
_WRITER_VERBS = r"wrote|texted|messaged|sent|told|replied|emailed"
_WRITER_RE = re.compile(
    r"(?<![\w@])([A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,2})\s+"
    rf"(?i:(?:{_WRITER_VERBS}))\b"
)
# Any verb that can introduce a quote. The one nearest before the quote governs it: in
# 'PETROV wrote a report quoting REYES: "ok"' it is "quoting", so PETROV is not the writer.
_QUOTING_RE = re.compile(
    rf"(?<!@)\b(?:{_WRITER_VERBS}|said|says|asked|posted|quoted|quoting|quotes|forwarded|forwarding|"
    r"stated|states|stating|saying|according|reads|read|answered|answers|answering|responded|"
    r"responds|responding|replies|replying|writes|writing|texts|texting|sends|sending|tells|"
    r"telling|typed|types|typing)\b",
    re.IGNORECASE,
)
QUOTE_REACH = 80  # characters from the writer's verb to the quote
_JOINS_WORDS = (
    r"(?:and|but|or|then|as|while|when|whereas|although|though|because|since|until|after|"
    r"before|so)"
)
# "two texts", "the answers": a quote word that can be a noun is no verb when it is the direct
# object of the verb before it (below), and only when nothing but punctuation follows it up to
# the quote. Only such words: "the
# quoted statement" still governs the quote, and so does a noun phrase that says whose words
# they are ("two quotes attributed to REYES: 'ok'"). A possessive ("her replies") may name
# someone else's words, so the noun then stays and names no writer.
_NOUN_FORMS = frozenset({"texts", "replies", "answers", "types", "quotes", "reads"})
# What may stand between the verb before a noun or participle and that word for the verb to
# keep the quote: only the recipient, named ("REYES", "REYES and SMITH", "Dr. Reyes", "@x").
# Anything else ("a report listing the replies", "about all the replies", "REYES while SMITH,
# replying") may make the words someone else's, so the word governs and names no writer.
_RECIPIENT = r"(?:@[\w.-]+|[A-Z][\w'.-]*)(?:\s+(?:and\s+)?(?:@[\w.-]+|[A-Z][\w'.-]*)){0,3}"
_DETERMINERS = (
    r"(?:a|an|the|these|those|some|several|two|three|four|five|six|seven|eight|nine|ten|\d+)"
)
_DIRECT_OBJECT = re.compile(
    rf"^\s+(?:(?-i:{_RECIPIENT})\s+)?(?:{_DETERMINERS}\s+){{1,2}}$", re.IGNORECASE
)
_SAME_CLAUSE = re.compile(rf"^\s+(?-i:{_RECIPIENT})\s*(?:,|\s(?:and|then))\s*$", re.IGNORECASE)
# 'PETROV texted REYES, writing "ok"': a participle right after the recipient and a comma (or
# "and", "then") has the same subject as the verb before it, so it does not govern the quote.
# Not when a new subject follows the quote ("..., replying 'ok', SMITH left"): that subject may
# be the one replying.
_SAME_SUBJECT_FORMS = frozenset(
    {
        "writing",
        "texting",
        "sending",
        "typing",
        "telling",
        "saying",
        "stating",
        "replying",
        "answering",
        "responding",
    }
)
# The participle's quote must end the sentence: in "saying 'ok' was what SMITH had written"
# the quote is the subject of what follows, and in "replying 'ok', an annoyed SMITH left" the
# one replying may be SMITH, so the words may be someone else's.
_QUOTE_ENDS_CLAUSE = re.compile(r"^[^\w]*$|^[^\w]*?[.!?](?:\s|$)")
_SUBJECT_AFTER = re.compile(
    r"^[^\w,]*,\s*(?:(?:he|she|they|it|we|i|you)\b|(?-i:[A-Z])|@)", re.IGNORECASE
)
# Words that carry a quote: a possessive hands the quote on only before one of these
# ("REYES's message", "JONES' reply") or right before the quote, not in "from his brother's
# phone".
_QUOTE_NOUNS = (
    r"(?:texts?|messages?|repl(?:y|ies)|answers?|responses?|quotes?|words|statements?|remarks?|"
    r"posts?|emails?|notes?|comments?|tweets?|captions?|lines?|chats?|dms?|voicemails?)"
)
_POSSESSIVE_OF_QUOTE = (
    r"(?:\b(?!(?:it|that|he|she|what|there|here|where|how|this|let)['’]s\b)\w+['’]s\b|\w+s['’](?=\s))"
    rf"(?=(?:\s+[\w-]+){{0,2}}?\s+{_QUOTE_NOUNS}\b|[\s,:\"'“‘”’-]*$)"
)
# A stop after a title ("Dr. Reyes") is no sentence break. Only titles that stand before a
# name: "St.", "Jr.", "No." can end a sentence ("from Main St. REYES shot back"), so they
# break. A single letter is not excused: "Exhibit A. REYES shot back" is a break, so
# "J. Reyes" fails closed.
_NOT_A_TITLE = "".join(
    rf"(?<!\b{t})"
    for t in (
        "Dr",
        "Mr",
        "Mrs",
        "Ms",
        "Sgt",
        "Det",
        "Lt",
        "Ofc",
        "Cpl",
        "Capt",
        "Prof",
        "Gen",
        "Col",
        "Insp",
        "Agt",
    )
)
# Words that can start a new clause with its own subject: "and REYES shot back", "as REYES
# shot back", "while he typed".
_JOINS = _JOINS_WORDS
# Between the writer's verb and the quote, anything that can hand the quote to someone else
# names no writer: a sentence break ('PETROV messaged REYES. REYES: "ok"'; a stop before a
# capital, so "2:31 p.m.:" and "Dr. Reyes" are no break), a relative or a joined clause
# ('PETROV texted REYES, who responded "ok"', '..., where REYES shot back', '..., and REYES
# shot back ...', '..., and @northstar shot back'), a possessive of the quoted words
# ('PETROV replied to REYES's message "ok"', "... JONES' reply ...", "..., and her reply
# was"), or
# words said to come from someone else ('PETROV wrote a report with the quotes from REYES,
# "ok"'). "and" joins a clause only before a pronoun or a name with words of its own:
# 'PETROV texted REYES and SMITH: "ok"' is one writer, two recipients (an all-caps claim is
# checked by _CAPS_CLAUSE_RE). Time words ("before midnight") hand nothing on, nor does a
# contraction ("that it's").
_HANDED_ON_RE = re.compile(
    rf"[;!?]|{_NOT_A_TITLE}\.(?=\s+[(\[\"'“‘]*[A-Z@])|{_POSSESSIVE_OF_QUOTE}"
    r"|\b(?:who|whom|whose|which|where)\b"
    rf"|\b{_QUOTE_NOUNS}\s+(?:from|of|by)\b"
    rf"|\b(?:his|her|their|its|my|our|your)\s+(?:[\w-]+\s+){{0,2}}?{_QUOTE_NOUNS}\b"
    rf"|\b{_JOINS}\s+(?:(?:he|she|they|it|we|i|you)\b"
    r"|(?-i:(?:(?:[A-Z][\w'.-]*|@[\w.-]+)\s+){1,3}[a-z]))",
    re.IGNORECASE,
)
# The same joined clause in an all-caps claim: "AND REYES SHOT BACK", not "AND SMITH:".
_CAPS_CLAUSE_RE = re.compile(rf"\b(?i:{_JOINS})\s+(?:(?:[A-Z][A-Z'.-]*|@[\w.-]+)\s+){{1,3}}[A-Z]")
# Besides the checks above, every word between the writer's verb and the quote must be one
# that cannot hand the quote on: a person the expert created, an "@" handle, a title, a
# number, a capitalised word in a claim that is not all caps (a name; in an all-caps claim
# only a person the expert created counts), or one of these words (recipients, times, "two
# texts", a same-subject participle).
# Any other word ("annoyed", "REPORT", "shot") names no writer: the guard above lists
# phrasings that hand a quote on, and this one keeps a phrasing it does not know from
# naming the wrong person.
_BETWEEN_WORDS = frozenset(
    {
        *_SAME_SUBJECT_FORMS,
        *_NOUN_FORMS,
        "to", "and", "that", "it", "back", "at", "on", "before", "after", "around",
        "a", "an", "the", "these", "those", "some", "several", "two", "three", "four",
        "five", "six", "seven", "eight", "nine", "ten",
        "a.m", "p.m", "am", "pm", "midnight", "noon", "morning", "afternoon", "evening",
        "night", "today", "yesterday", "monday", "tuesday", "wednesday", "thursday",
        "friday", "saturday", "sunday", "january", "february", "march", "april", "may",
        "june", "july", "august", "september", "october", "november", "december",
    }
)  # fmt: skip
_TITLES = frozenset(
    t.casefold()
    for t in ("Dr", "Mr", "Mrs", "Ms", "Sgt", "Det", "Lt", "Ofc", "Cpl", "Capt", "Prof",
              "Gen", "Col", "Insp", "Agt", "Agent", "Officer", "Detective")
)  # fmt: skip
# A name right after one of these is not the one who wrote: 'a friend of PETROV texted ...',
# 'someone posing as PETROV texted ...'. A plain "As PETROV texted ..." still names him.
_POSSESSIVE_BEFORE = re.compile(r"['’]s\s*$", re.IGNORECASE)
_NOT_THE_WRITER_BEFORE = re.compile(
    r"(?:\b(?:of|for|to|with|by|from|via|behind|about|like|than|posing\s+as|"
    r"pretending\s+to\s+be|impersonating))\s*$",
    re.IGNORECASE,
)


def _last_end(pattern: re.Pattern[str], text: str) -> int:
    """Where the last match of the pattern in the text ends, or 0 when there is none."""
    return max((m.end() for m in pattern.finditer(text)), default=0)


def coverage_gap(claim: Claim, proposals: list[Proposal]) -> str | None:
    """What the kept proposals leave untested that the claim states, or None.

    A claim must not be judged on its easy parts: its key template must be there, a stated
    date must be tested by some time range, a stated time of day (outside quoted words) by a
    range that states one,
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
    if time_mentions(_unquoted(claim.text)) and not any(time_mentions(r) for r in raws):
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

        out = self._add_record_time(claim, para, out, allowed_ids)
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
        elif tpl.id == "sender" and not (p.handles or p.accounts):
            # A phone scopes the search but is no party, so it does not stop this.
            writer = self.stated_sender(claim, p.quoted_text)
            if writer is not None:
                params["person_ids"] = [writer]

        channels = self._channels(claim.text, p.channels, tpl.id)
        if channels:
            params["channels"] = channels

        account_ids: set[str] = set()
        handles = [h.strip() for h in p.handles]
        named: set[str] = set()  # people the model wrote as accounts
        for acc in p.accounts:
            try:
                account_ids |= self._accounts(acc, device_ids, claim.text)
            except Reject:
                # Words the case holds no account identifier under may still name a party:
                # - a person the expert created ("SUBJECT-1" on Signal): the claim names the
                #   person, whose accounts the checks take from confirmed stipulations and
                #   links, never from the words;
                # - "@northstar", a handle, where the template takes handles: the checks
                #   resolve it from the data (exactly one account, or the party is left
                #   unresolved);
                # - the display name of exactly one account on that app ("ThisIs DfirTwo" on
                #   Skype). A name several accounts carry is refused: they are never merged.
                # Anything else fails.
                written = acc.as_written.strip()
                person = self._person_named(written) if "person_ids" in tpl.allowed else None
                by_name = self._accounts_named(acc, device_ids, claim.text)
                if person is not None:
                    theirs = person_party(self.data, person).keys
                    if any(self.data.accounts[a].key not in theirs for a in by_name):
                        raise Reject(
                            f"{written!r} names a person and a {acc.app} account that is not"
                            " confirmed as theirs"
                        ) from None
                    named.add(person)
                    continue
                if "handles" in tpl.allowed and (written.startswith("@") or written in handles):
                    if written not in handles:
                        handles.append(written)
                    continue
                if not by_name:
                    raise
                account_ids |= by_name
        if named:
            params["person_ids"] = sorted(set(params.get("person_ids", [])) | named)
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

        if p.window is not None and "window" not in tpl.allowed:
            pass  # a sender is picked by its words and party; the time is record_time's job
        elif p.window is not None:
            try:
                params["window"] = self._window(claim.text, para, p.window, device_ids, tpl.id)
            except Reject as refused:
                # The model's range is refused; use the range the claim states that day.
                try:
                    params["window"] = self._stated(claim, para, device_ids, tpl.id, p.window.start)
                except Reject as e:
                    raise Reject(f"{refused}, and {e}") from None
        elif "window" in tpl.required:
            params["window"] = self._stated(claim, para, device_ids, tpl.id, None)

        return Proposal(p.template_id, params, is_core=True)

    def _stated(
        self, claim: Claim, para: str, device_ids: list[str], template_id: str, near: str | None
    ) -> Any:
        """The claim's own stated range: the one on the model's start day, or its only one.
        Raises Reject when there is none, or more than one could be meant."""
        if template_id == "no_contact" and any(
            _has_word(claim.text, w) for w in ("first", "last", "earliest", "latest")
        ):
            # "first made contact on March 12" means none before it, not none that day.
            raise Reject("the claim's range for no contact is not a plain stated range")
        stated = stated_windows(claim.text, para) or []
        if near is not None and len(stated) > 1:
            try:
                day = datetime.fromisoformat(near).date()
            except ValueError:
                day = None
            stated = [w for w in stated if w.start.date() == day]
        if len(stated) != 1:
            raise Reject("the time range is not one the claim plainly states")
        (w,) = stated
        check_window(w.start, w.end, w.raw, claim.text, para, template_id)
        tz = self._read_zone(w.zone, w.start, w.end, device_ids)
        try:
            return local_window(w.start, w.end, tz, w.raw)
        except ValueError as e:
            raise Reject(str(e)) from None

    def _add_record_time(
        self, claim: Claim, para: str, out: list[Proposal], allowed_ids: set[str]
    ) -> list[Proposal]:
        """A claim that dates a quoted message ("On March 12, 2026, PETROV wrote ...") and got
        a sender assumption but no time range gets the record_time assumption from code: the
        sender's parties and words, in the one range the claim states."""
        if "record_time" not in allowed_ids or not date_mentions(claim.text):
            return out
        if any(isinstance(p.params, dict) and p.params.get("window") for p in out):
            return out
        senders = [p for p in out if p.template_id == "sender" and isinstance(p.params, dict)]
        if len(senders) != 1:
            return out
        sender = dict(senders[0].params)
        try:
            window = self._stated(claim, para, sender.get("device_ids", []), "record_time", None)
        except Reject as e:
            self._drop(claim, None, f"record_time from the claim's date: {e}", None)
            return out
        allowed = TEMPLATES["record_time"].allowed
        params = {k: v for k, v in sender.items() if k in allowed} | {"window": window}
        return [*out, Proposal("record_time", params, is_core=True)]

    @staticmethod
    def _passes_quote_on(before: str, verb: re.Match[str], after: str) -> bool:
        """True when this quote word is a noun or a same-subject participle, so the verb
        before it still governs the quote. `after` is the claim's text after the quote."""
        word, ahead = verb.group(0).casefold(), before[: verb.start()]
        span = ahead[_last_end(_QUOTING_RE, ahead) :] if _QUOTING_RE.search(ahead) else ""
        if word in _NOUN_FORMS and _DIRECT_OBJECT.match(span):
            return not re.search(r"\w", before[verb.end() :])
        return (
            word in _SAME_SUBJECT_FORMS
            and bool(_SAME_CLAUSE.match(span))
            and not _SUBJECT_AFTER.search(after)
            and bool(_QUOTE_ENDS_CLAUSE.match(after))
        )

    def stated_sender(self, claim: Claim, quoted: str | None) -> str | None:
        """The person the claim names as the writer of the quoted words, or None.

        The verb nearest before the quote must be a verb of writing with a name right before
        it ("PETROV wrote to @northstar: ..."), at most QUOTE_REACH characters from the quote,
        and the name must match exactly one person the expert created. Nothing between the
        verb and the quote may hand the quote on (a sentence break, "who", "and", a
        possessive), and the name must not follow "of", "for", "posing as" and the like.
        Anything else (no quote, "quoting", "said", "answered", a name that is no person)
        names no writer."""
        if not quoted or not quoted.strip():
            return None
        at = _nfc(claim.text).find(_nfc(quoted.strip()))
        if at < 0:
            return None
        before = _nfc(claim.text)[:at]
        after = _nfc(claim.text)[at + len(_nfc(quoted.strip())) :]
        verbs = [
            v for v in _QUOTING_RE.finditer(before) if not self._passes_quote_on(before, v, after)
        ]
        if not verbs or at - verbs[-1].end() > QUOTE_REACH:
            return None
        last = verbs[-1]
        match = next((m for m in _WRITER_RE.finditer(before) if m.end() == last.end()), None)
        if match is None:
            return None
        between = before[last.end() :]
        if _HANDED_ON_RE.search(between) or (_CAPS_CLAUSE_RE.search(between)):
            return None  # the quote may be someone else's: fail closed, as for no writer
        if not self._plain_between(between):
            return None
        words = match.group(1).split()
        for i in range(len(words)):
            # What comes before this form of the name, capitalised words included ("A FRIEND
            # OF PETROV TEXTED"), must not make it someone else's. After a possessive a later
            # form may still name the writer ("PETROV'S ASSISTANT REYES TEXTED": REYES).
            prefix = " ".join([before[: match.start()], *words[:i]])
            if _NOT_THE_WRITER_BEFORE.search(prefix):
                return None
            if _POSSESSIVE_BEFORE.search(prefix):
                continue
            try:
                return self._person(" ".join(words[i:]))  # the longest form that names a person
            except Reject:
                continue
        return None

    def _plain_between(self, between: str) -> bool:
        """True when every word between the writer's verb and the quote is on the list that
        cannot hand the quote on (see _BETWEEN_WORDS)."""
        names = {
            part
            for (full,) in self.conn.execute("SELECT name FROM persons")
            for part in _nfc(full).casefold().split()
        }
        if "\n" in between or "\r" in between:
            return False  # a new line can carry a new label ("REYES\nSMITH: 'ok'")
        mixed_case = bool(re.search(r"[a-z]", re.sub(r"@[\w.-]+", "", between)))
        last_end, last_capital = 0, False  # the word before: where it ends, and its kind
        last_digit = False
        for m in re.finditer(r"@[\w.-]+|\w[\w'’.-]*", between):
            word = m.group(0)
            w = re.sub(r"['’]s$", "", word.casefold()).strip(".'’-")
            # Between words only spaces and commas ("2:31" aside): a dash, a bracket or a
            # colon can set a new label on the quote ("REYES — @northstar: 'ok'").
            gap = between[last_end : m.start()]
            if not (re.fullmatch(r"[\s,]*", gap) or (gap == ":" and last_digit and w.isdigit())):
                return False
            known = (
                word.startswith("@")
                or w.isdigit()
                or w in _BETWEEN_WORDS
                or w in _TITLES
                or (w in names and word[0].isupper())  # "Will", not the word "will"
            )
            # A capitalised word that is no created person may be a name, but not right after
            # another capitalised word: "REYES SHOT BACK" is a clause of its own.
            right_after = last_capital and not between[last_end : m.start()].strip()
            if not known and not (mixed_case and word[0].isupper() and not right_after):
                return False
            last_end = m.end()
            last_capital = (word[0].isupper() and w not in _TITLES) or word.startswith("@")
            last_digit = w.isdigit()
        # After the last word only a comma or a colon, then the quote's opening mark. A colon
        # after a list ("REYES, then REYES: 'ok'") may label the quote, so not both.
        tail = between[last_end:]
        if not re.fullmatch(r"\s*[,:]?\s*[\"'“‘]*\s*", tail):
            return False
        return not (":" in tail and "," in between[:last_end])

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
        """The device a phone name means: its id, source id or label, or a name the expert
        gave it (core/review/device_names.py)."""
        want = name_key(phone)
        named = logged_names(self.conn)
        hits = [
            did
            for did, sid, label in self.conn.execute(
                "SELECT id, source_id, label FROM devices ORDER BY id"
            )
            if want in {name_key(x) for x in (did, sid, label, *named.get(did, [])) if x}
        ]
        if len(hits) != 1:
            raise Reject(f"phone {phone!r} matches {len(hits)} devices")
        return hits[0]

    def _channels(self, claim_text: str, names: list[str], template_id: str = "") -> list[str]:
        vocab = {c.casefold(): c for c in self.channels()}
        out = []
        for name in names:
            canon = vocab.get(name.strip().casefold())
            if canon is None:
                raise Reject(f"channel {name!r} is not an app in this case")
            words = CHANNEL_WORDS.get(canon.casefold(), (canon.casefold(),))
            if not any(_has_word(claim_text, w) for w in words):
                self._alias(claim_text, canon, vocab, template_id)
            out.append(canon)
        return sorted(set(out), key=str.lower)

    @staticmethod
    def _alias(claim_text: str, canon: str, vocab: dict[str, str], template_id: str) -> None:
        """Raises Reject unless the claim names this app by a word APP_ALIASES gives it, and
        no other app in the case goes by that word."""
        said = [w for w in APP_ALIASES.get(canon.casefold(), ()) if _has_alias(claim_text, w)]
        if not said:
            raise Reject(f"the claim does not name the channel {canon!r}")
        for w in said:
            others = sorted(
                c
                for k, c in vocab.items()
                if c != canon
                and (
                    k == w.casefold()
                    or w in APP_ALIASES.get(k, ())
                    or w.casefold() in CHANNEL_WORDS.get(k, ())
                )
            )
            if others:
                raise Reject(
                    f"the claim's {w!r} could be {canon!r} or {', '.join(map(repr, others))}"
                )
        if canon.casefold() in WIDER_APPS and template_id in WHOLE_APP_TEMPLATES:
            raise Reject(
                f"{canon!r} holds more than the claim's {said[0]!r} names, so no count or"
                " absence is read on it"
            )

    def _accounts(self, acc: _Account, device_ids: list[str], claim_text: str = "") -> set[str]:
        """The accounts on the model's app with this identifier. A number written another way
        ("(919) 888-7386" for "+19198887386") finds its account too, on a phone app or on an
        app the claim names: a number alone never picks the app."""
        app = acc.app.strip().casefold()
        ident = re.sub(r"(?i)^(user\s*id|id|number|no\.)\s*", "", acc.as_written.strip())
        want = key(acc.app, ident)
        sources = set(self.data.sources_for(device_ids)) if device_ids else None
        mine = [
            a
            for a in self.data.accounts.values()
            if a.app.casefold() == app and (sources is None or a.source_id in sources)
        ]
        hits = {a.id for a in mine if a.key == want}
        number = phone_digits(ident)
        if not hits and number is not None and self._app_named(claim_text, acc.app):
            hits = {a.id for a in mine if _same_number(number, a)}
        if not hits:
            raise Reject(f"{acc.as_written!r} on {acc.app} matches no account in the case")
        return hits

    def _app_named(self, claim_text: str, app: str) -> bool:
        """A phone app, or an app the claim names the way `_channels` requires."""
        if namespace(app) == "tel":
            return True
        try:
            self._channels(claim_text, [app])
        except Reject:
            return False
        return True

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
        # The zone comes from the document's words, never the model's: "11:11 a.m. EDT" is
        # read in EDT even when the model says UTC, and check_window then holds the model's
        # times to the times written.
        zone = written_zone(w.as_written, claim_text)
        if zone is None and w.zone == "UTC":
            raise Reject("the range does not say UTC")
        check_window(start, end, w.as_written, claim_text, para, template_id)
        tz = self._read_zone(zone, start, end, device_ids)
        try:
            return local_window(start, end, tz, w.as_written.strip())
        except ValueError as e:
            raise Reject(str(e)) from None

    def _person_named(self, words: str) -> str | None:
        """The one person the expert created whom these words name, or None."""
        try:
            return self._person(words)
        except Reject:
            return None

    def _accounts_named(self, acc: _Account, device_ids: list[str], claim_text: str) -> set[str]:
        """The accounts on the model's app whose display name is exactly these words, when
        they are one account and the app is a phone app or one the claim names. Raises Reject
        when the name is on several accounts."""
        if not self._app_named(claim_text, acc.app):
            return set()
        app, written = acc.app.strip().casefold(), _nfc(acc.as_written.strip())
        sources = set(self.data.sources_for(device_ids)) if device_ids else None
        hits = [
            a
            for a in self.data.accounts.values()
            if a.app.casefold() == app
            and (sources is None or a.source_id in sources)
            and a.display_name is not None
            and _nfc(a.display_name.strip()) == written
        ]
        if len({a.key for a in hits}) > 1:
            raise Reject(
                f"{acc.as_written!r} is the name of {len({a.key for a in hits})} {acc.app}"
                " accounts; which one the claim means is not known"
            )
        return {a.id for a in hits}

    def _read_zone(
        self, zone: str | None, start: datetime, end: datetime, device_ids: list[str]
    ) -> str:
        """The zone a range's wall-clock times are read in. UTC when the document writes UTC
        or GMT beside the time. Otherwise the phone's zone, which must have the offset any
        zone the document writes means ("EDT" is UTC-04:00) at both ends of the range: a
        claim that says EST on a day New York was on EDT is refused, never read either way."""
        if zone is not None and zone.strip().upper() in ("UTC", "GMT"):
            return "UTC"
        tz = self._phone_zone(device_ids)
        if zone is None:
            return tz
        for t in (start, end - timedelta(minutes=1)):
            want = zone_offset(zone, t)
            got = t.replace(tzinfo=ZoneInfo(tz)).utcoffset()
            if got != want:
                raise Reject(
                    f"the claim gives the time in {zone} (UTC{_hm(want)}), but the phone's zone"
                    f" {tz} is at UTC{_hm(got)} then"
                )
        return tz

    def _phone_zone(self, device_ids: list[str]) -> str:
        rows = self.conn.execute("SELECT id, timezone FROM devices ORDER BY id").fetchall()
        zones = {resolve_zone(tz) for did, tz in rows if not device_ids or did in device_ids}
        if len(zones) != 1 or None in zones:
            raise Reject("the phones do not share one known time zone; name the phone")
        (tz,) = zones
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError):
            raise Reject(f"unknown phone time zone {tz!r}") from None
        return tz


_PHONE_RE = re.compile(r"\+?[\d\s().\-]{7,24}")
# the North American form: "(919) 888-7386", "919-888-7386", "1-919-888-7386"
_NANP_RE = re.compile(r"(1[\s.\-]?)?(?:\((\d{3})\)\s?|(\d{3})[\s.\-])(\d{3})[\s.\-](\d{4})")


def phone_digits(words: str) -> str | None:
    """A phone number as its digits with the country code, or None when the words are not
    plainly one. "+1 919-888-7386" is 19198887386. A number written in the North American form
    ("(919) 888-7386", "919-888-7386") takes country code 1. Other numbers without a "+",
    digits run together among them, are not read: their country is not written."""
    w = words.strip()
    if not _PHONE_RE.fullmatch(w):
        return None
    d = re.sub(r"\D", "", w)
    if w.startswith("+"):
        return d if 8 <= len(d) <= 15 else None
    m = _NANP_RE.fullmatch(w)
    if m is None:
        return None
    area, exchange, line = m.group(2) or m.group(3), m.group(4), m.group(5)
    if area[0] not in "23456789" or exchange[0] not in "23456789":
        return None
    return "1" + area + exchange + line


def _same_number(number: str, acc: Account) -> bool:
    """The account's identifier is this phone number: written with its country code ("+"),
    a WhatsApp id ("12125550122@s.whatsapp.net"), or a phone account's own number. A user id
    that happens to be digits is never one."""
    ident = acc.identifier.strip()
    jid = re.fullmatch(r"(\d{8,15})@s\.whatsapp\.net", ident)  # a WhatsApp id is the number
    if jid is not None:
        return jid.group(1) == number
    if not (ident.startswith("+") or namespace(acc.app) == "tel"):
        return False
    return phone_digits(ident) == number


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
