"""The local-model filler for the assumption templates (core/audit/assumptions.py).

The model reads one claim and its paragraph and proposes which templates the claim rests on,
with each value written exactly as the document writes it: names ("PETROV"), phones ("Item 1"),
numbers and handles ("+1 (212) 555-0122", "@northstar"), apps, quoted words, a count and a time
range in the document's own words. It never writes an id, a time zone or a UTC time.

Code then turns those words into typed AssumptionParams, and drops anything it cannot tie to
the document or the case data. It fails closed at every step:

- Every value must appear verbatim in the claim or its paragraph. Anything else is dropped.
  A message's quoted words (sender, record_time, meaning) must lie inside quotation marks in
  the claim: "call" in "placed a Telegram call" is the claim's own word, not a message anyone
  wrote. A quoted name the proposal also gives as a party ('the Teams user "ThisIs
  DfirTwo"') is not a message either.
- A sender is never a party the claim writes only as the one written to ("wrote to the
  Discord user X", "SUBJECT-1's iMessage to (919) 888-7386", "told REYES"): the sender check
  would test the wrong person, and a failed check contradicts the claim.
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
  proposal is refused. A phone written as an account ("the TARGET PHONE's Kik account") is
  that phone's own accounts on the app, as the phone recorded them, never its owner's links.
  The display name of exactly one account finds that account. A number or a display name
  finds an account only on a phone app or on an app the claim names, so the words alone
  never pick the app. Accounts are never merged.
- A channel must be named in the claim ("Telegram", or "texted" for SMS, "call" for calls).
  A model never narrows a search to a channel the document did not name. An export's own
  name for an app ("Wickr Pro", "Kik Messenger", "Native Messages") is named by the word a
  document uses for it ("Wickr", "Kik", "iMessage"; `APP_ALIASES`) only when no other app in
  the case goes by that word. A capitalized word counts only as written or in capitals
  ("Teams", never "the teams met"). No count or absence is read from an app that holds more
  than the word names (iOS "Native Messages" holds iMessage and SMS together).
- A call the model proposed without its parties gets them from the claim's words
  (`_call_parties`): each person the expert created whom the claim names, and each number,
  identifier or quoted display name it writes, on the one app the claim names for the call
  ("a Signal call"; `_call_app`). Each must be exactly one person or one account, and plainly
  a party: not someone's ("PETROV's phone"), not after "of", "for", "about" or "posing as",
  and not in a claim with a second clause ("after speaking with"). Both sides must be read,
  or one account and the phone; an unknown handle, address or number refuses. Else nothing is
  filled.
  The channels become "call" and that app, so the time check searches that app's
  calls only. A call on no named app (a native phone call) or on two is left as it was.
- A call's stated length ("about two minutes", "a minute and a half", "more than two
  minutes") is turned into seconds by code, with any bound the claim writes right before it
  (`duration_range`).
- A count's number must appear in the claim, in figures or words ("thirteen"), and its
  comparison ("at least", "at most", exactly) is read from the claim's words by code, not
  taken from the model. The count check
  counts messages between two parties in both directions, so a count of calls or "times",
  or of messages one side sent or received ("sent 10 messages to"), is refused.
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
  (`stated_sender`) from the verb nearest before the quote ("asked on TikTok:", "told REYES
  by iMessage:", "sent a Signal message to (919) 888-7386 reading", "wrote to the Discord user
  'X':"), when that name matches exactly one person the expert created. Otherwise it stays
  without a party and is refused as before. A claim that quotes a message and names its
  writer that way, with no sender assumption at all, gets one from code: the claim's one
  quoted message (`the_quote`) sent by that person, on the one app the claim names.
- A claim whose type needs a meaning assumption and got none gets it from code on the claim's
  one quoted message: the words a kept sender or time assumption already quotes, or else the
  one quote in the claim that is no name and follows a verb of saying or a colon. Two quotes,
  or any doubt, add nothing. Meaning has no check, so only the expert's acceptance covers it.
- Every proposed assumption is core. The model does not get to mark one optional.
- A claim must not be judged on its easy parts (`coverage_gap`): each claim type needs its
  key template (a meaning claim needs "meaning", a count needs "message_count", ...), a stated
  date needs a time range, a stated time of day a range that states it, and a quoted message
  in a claim of any type a sender assumption. Otherwise the claim gets no assumptions at
  all and stays unproven. It judges only proposals whose parameters fit their template: a
  sender naming two parties, which the builder drops, does not count as testing who sent it.

Proposals then go through TemplateAssumptionBuilder, which validates them again.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
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
from core.audit.assumptions import TEMPLATES, Proposal, Template, local_window, parse_params
from core.audit.checks._common import (
    CALL_CHANNEL,
    Account,
    CaseData,
    Key,
    key,
    namespace,
    person_party,
)
from core.contracts import Claim, ClaimType, ModelRun, TimeWindow
from core.review.device_names import logged_names, name_key
from core.zones import resolve_zone

PROMPT_FILE = "assumptions.md"
PLACEHOLDERS = frozenset({"claim", "paragraph", "templates", "channels"})
MAX_PROPOSALS = 8
# The filler's own version, recorded in each assumptions run (open_run's code_version). Bump it
# when a change alters which proposals are kept or what code adds, so two runs of the same
# model and prompt that test different claims can be told apart.
#   2: #160's guards, and code adds a meaning assumption and a stated writer's sender.
FILLER_VERSION = "2"
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
# Words for a phone's own messages, whether or not the case holds an app by that name.
_PHONE_MESSAGE_WORDS = (*CHANNEL_WORDS["sms"], "imessage", "imessages", "mms", "rcs")
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
# Apps that hold more than the word that names them, with what they hold: iOS "Native Messages"
# holds iMessage and SMS together. The report and the claim page say so on a claim that names
# or rests on one (core/report/html.py, mixed_app_note).
WIDER_APPS: dict[str, str] = {"native messages": "iMessages and SMS"}
# Checks whose answer depends on every record on the app they search. On a wider app a count
# would count, and an absence would fail on, messages the claim does not name.
WHOLE_APP_TEMPLATES = frozenset({"message_count", "no_contact"})
# The app an import gives a record with no source app: on a phone, its own call log. A call
# claim that names no app and writes the other party as a phone number is searched there
# (validation ruling R1).
NATIVE_CALL_APP = "unknown"
# Templates whose check reads exactly two sides.
TWO_SIDED_TEMPLATES = frozenset({"message_count", "no_contact"})
# The templates whose time range a check tests.
_TIMED = frozenset({"record_time", "message_count", "no_contact", "weekday_date"})
# Templates whose quoted_text is the words of a message (a contact entry's is a saved name, a
# weekday's the claim's own words).
MESSAGE_TEXT_TEMPLATES = frozenset({"sender", "record_time", "meaning"})


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


def _name_spans(text: str, name: str) -> list[tuple[int, int]]:
    """Where the text names this person the expert created: the whole name in any case
    ("SUBJECT-1", "Daniel Petrov"), or a last name of several as written or in capitals
    ("PETROV")."""
    words = _words(name).split()
    if not words:
        return []
    found = [r"(?<![a-z0-9])" + r"[^a-z0-9]+".join(map(re.escape, words)) + r"(?![a-z0-9])"]
    parts = name.split()
    if len(parts) > 1:
        found += [
            rf"(?-i:(?<![\w-]){re.escape(x)}(?![\w-]))" for x in (parts[-1], parts[-1].upper())
        ]
    return [m.span() for f in found for m in re.finditer(f, text, re.IGNORECASE)]


# An address or identifier with an app's name in it: "x@gmail.com", "live:.cid.5638", "zoom.us".
_ADDRESS_RE = re.compile(r"\S+@\S+|\S*:\S+|\S+\.(?:com|net|org|us|io)\b\S*", re.IGNORECASE)


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
# A zone that code does not read, so the range is never put in the phone's zone instead: an
# abbreviation not in capitals ("pdt", or "pt" all in lowercase, since "Pt." after a time may
# be a place), an offset ("UTC+3"), a zone outside the US and UTC
# ("BST", "CET", "bst"), or another zone's name ("Central European Time", "central european
# time"). A zone outside the US and UTC counts in capitals or all in lowercase, never in title
# case ("Sgt. Reyes"), and the lowercase ones that are English words ("west", "art") never
# count.
_OFFSET_ZONE = (
    r"(?:(?i:utc|gmt)\s*[+\-−]\s*\d"
    # or an offset with no name, "+0300", "-05:00" (Codex on #152). Never a range's other end:
    # "10:00-10:30 a.m." goes on to a.m. or p.m., and no offset passes 14 hours.
    r"|[+\-−](?:0\d|1[0-4]):?[0-5]\d(?![\d:])(?!\s*[ap]\.?\s?m\b))"
)
_OTHER_ABBRS = (
    "BST IST CET CEST EET EEST MSK GST PKT ICT WIB SGT HKT PHT JST KST AWST ACST ACDT AEST AEDT"
    " NZST NZDT AST ADT NST NDT BRT SAST SST"
).split()
_OTHER_ZONE = (
    rf"(?:{'|'.join(_OTHER_ABBRS)}|WET|WEST|ART|CAT|EAT|WAT|ChST"
    rf"|{'|'.join(a.lower() for a in _OTHER_ABBRS if a != 'SGT')}|chst)\b"
)
_ZONE_REGIONS = (
    r"european|british|greenwich|india|indian|china|japan|korea|singapore|hong\s+kong"
    r"|philippine|australian|new\s+zealand|atlantic|newfoundland|alaska|alaskan|hawaii|hawaiian"
    r"|aleutian|arabian|gulf|moscow|brasilia|brazil|argentina|africa|african|chamorro|samoa"
    r"|pakistan|indochina|indonesia|indonesian|israel|universal|mexico|mexican"
)
_ZONE_NAME = (
    r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+Time"
    rf"|(?i:(?:[a-z]+\s+){{0,2}}(?:{_ZONE_REGIONS})(?:\s+(?:standard|daylight|summer))?\s+time))\b"
)
_UNREAD_ZONE_RE = re.compile(
    rf"(?i:{_CLOCK_END})\s*\(?(?P<z>{_OFFSET_ZONE}"
    r"|(?i:utc|gmt|akst|akdt|[ecmp][sd]t|hst)\b|[ecmp]t\b"
    rf"|{_OTHER_ZONE}|{_ZONE_NAME})"
)
# After a date only an offset, or a zone in brackets, counts: a capitalized word after a date
# may be a person ("On January 9, 2026, AST called").
_UNREAD_DATE_ZONE_RE = re.compile(
    rf"\s*,?\s*(?:\(?(?P<z>{_OFFSET_ZONE})"
    r"|\(\s*(?P<z2>(?i:utc|gmt|akst|akdt|[ecmp][sd]t|hst|[ecmp]t)\b"
    rf"|{_OTHER_ZONE}|{_ZONE_NAME})\s*\))"
)


def unread_zone(text: str) -> str | None:
    """A zone written right after a time, or after a date, in the text (outside quoted words)
    that code does not read, or None."""
    plain = _unquoted(text)
    found = [m.group("z") for m in _UNREAD_ZONE_RE.finditer(plain)]
    for d in _DATE_RE.finditer(plain):
        m = _UNREAD_DATE_ZONE_RE.match(plain[d.end() :])
        if m is not None:
            found.append(m.group("z") or m.group("z2"))
    for z in found:
        if not re.fullmatch(_ZONE, z, re.IGNORECASE):
            return z
    return None


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


def _offsets(t: datetime, tz: str) -> dict[int, timedelta | None]:
    """The offsets a wall-clock time has in tz, by fold: two the night the clocks go back, and
    none for a time they skip when they go forward."""
    z = ZoneInfo(tz)
    return {
        f: t.replace(fold=f, tzinfo=z).utcoffset()
        for f in (0, 1)
        if t.replace(fold=f, tzinfo=z).astimezone(UTC).astimezone(z).replace(tzinfo=None) == t
    }


def _instant(t: datetime, tz: str, want: timedelta | None) -> datetime:
    """t with the fold that makes it one instant in tz: the one at the offset the document
    writes ("EDT"), or its only one. Raises Reject when a clock change makes it two instants or
    none and the document's words do not pick one."""
    offsets = _offsets(t, tz)
    if want is not None:
        fold = next((f for f, off in offsets.items() if off == want), None)
        if fold is None:
            raise Reject(f"{t:%Y-%m-%d %H:%M} is not at UTC{_hm(want)} in {tz}: the clocks change")
        return t.replace(fold=fold)
    if len(set(offsets.values())) != 1:
        n = "two times" if offsets else "no time"
        raise Reject(f"{t:%Y-%m-%d %H:%M} is {n} in {tz}: the clocks change then")
    return t.replace(fold=0)


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
    then " EDT" in the claim). Raises Reject when they give more than one, or a zone right after
    a time that code does not read ("pdt", "UTC+3", "BST"): the range is then never read in the
    phone's zone instead."""
    plain = _unquoted(as_written)
    unread = unread_zone(plain)
    if unread is not None:
        raise Reject(f"the range writes a time zone code does not read ({unread!r})")
    found = [m.group("z") for m in _TIMED_ZONE_RE.finditer(plain)]
    for d in _DATE_RE.finditer(plain):
        zm = _DATE_ZONE_RE.match(plain[d.end() :])
        if zm is not None:
            found.append(zm.group("z") or zm.group("z2"))
    text, words = _nfc(claim), _nfc(as_written.strip())
    timed = _ENDS_TIMED_RE.search(words)
    dated = _ENDS_DATE_RE.search(words)
    reads_on = not found and (timed or dated)
    i = text.find(words) if words else -1
    while i >= 0:
        rest = text[i + len(words) :]
        # Checked even when the model's words give a zone: they may stop inside one the claim
        # writes, "On January 9, 2026 UTC" in "On January 9, 2026 UTC+3" (Codex on #150).
        unread = unread_zone(words + rest[:40])
        if unread is not None:
            raise Reject(f"the claim writes a time zone code does not read ({unread!r})")
        zm = None
        if reads_on:
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


_QUOTE_MARKS = "\"“”‘’'"


def _flat(text: str) -> str:
    """The text with each line break or other whitespace character as one space, same length,
    so a quote a PDF wrapped over two lines is still one quoted span (Codex on #160)."""
    return re.sub(r"\s", " ", text)


def _in_quotes(value: str, text: str) -> bool:
    """True when the value lies inside one quoted span of the text: words the claim quotes,
    not words it uses itself ("call" in "placed a Telegram call")."""
    v = _flat(_nfc(value.strip())).strip(_QUOTE_MARKS).strip()
    spans = _QUOTE_SPAN_RE.finditer(_flat(_nfc(text)))
    return bool(v) and any(v in m.group(0)[1:-1] for m in spans)


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
        # "at approximately 12:01 a.m. on May 2" starts a few minutes before midnight on May 1:
        # a start near a stated time may fall on the day before the date it is near.
        near_midnight = bool(times) and _near(start, times)
        if not _date_stated(start.date(), mentions, years) and not (
            near_midnight and _date_stated((start + TIME_SLACK).date(), mentions, years)
        ):
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
# a weekday the document writes before the date: "on Friday, January 9"
_WD_LEAD = rf"(?:(?:{_WD_RE}),?\s+)?"
_LEAD_RE = re.compile(rf"\b(?:on|between|from)\s+{_WD_LEAD}$", re.IGNORECASE)
# after a plain date, a zone in brackets, or an abbreviation that is never initials ("ET" or
# "PT" after a date may be a person)
_DATE_ZONE_RE = re.compile(
    rf"\s*(?:\((?P<z>{_ZONE})\)|,?\s*(?P<z2>(?-i:UTC|GMT|AKST|AKDT|[ECMP][SD]T|HST))\b)",
    re.IGNORECASE,
)
_FROM_RE = re.compile(rf"\b(?:between|from)\s+{_WD_LEAD}$", re.IGNORECASE)
# a word right before the range read that leaves one end open or names a second end: "after 9
# p.m. on", "from 9 p.m. on", "starting on", "as of", "starting on Friday,"
_OPEN_LEAD_RE = re.compile(
    r"\b(?:after|before|since|until|till|by|from|between|starting|beginning|commencing|"
    r"as\s+of|prior\s+to|up\s+to|no\s+(?:later|earlier)\s+than)\s+"
    rf"(?:on\s+)?{_WD_LEAD}$",
    re.IGNORECASE,
)
# words right after the range read that leave its end open: "at 9 p.m. onward", "or later"
_OPEN_TAIL_RE = re.compile(
    # the phone's-zone words first do not hide the open end: "at 9 p.m. local time onward"
    # (Codex on #150)
    r"(?:\s*,?\s*\(?(?:local(?:\s+time)?|(?:phone|device)(?:'s)?\s+time)\)?)?"
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
    if unread_zone(plain) is not None:
        return None  # "9 p.m. pdt", "9 p.m. BST": never read in the phone's zone instead
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


# Words that leave a range for no contact open to the extraction's edge (validation R5).
_OPEN_RANGE_RE = re.compile(r"\b(?:never|before|prior\s+to|until|after|since)\b", re.IGNORECASE)
# An open range's edges come from the data, so the source spans it by construction; the
# words say what that leaves unseen.
_EDGE_NOTE = "; the edges are the extraction's own, so contact outside its records is not seen"
_HANDLE_RE = re.compile(r"@[\w.-]*\w|\S+@\S*\w")
# Someone the message went to: "REYES received a Telegram message reading ...", "a message
# to REYES" (Codex on #169).
_RECEIVED_AFTER_RE = re.compile(
    r"\s+(?:(?:had|has|have|was|were)\s+)?(?:received|receives|got|gets|was\s+sent)\b",
    re.IGNORECASE,
)
_TO_BEFORE_RE = re.compile(r"\b(?:to|for|toward|towards)\s+$", re.IGNORECASE)
# Any other word for when, outside an open range's one date: a year, a month, a weekday, a
# part of a day or a span ("During 2025 ... never", "never on Mondays"; Codex on #169).
_OTHER_TIME_RE = re.compile(
    rf"\b(?:{_MONTH_RE}|{_WD_RE})s?\b|\b(?:during|within|throughout|"
    r"while|when|whenever|once|again|anymore|weekends?|weekdays?|weeks?|months?|years?|days?|"
    r"nights?|mornings?|afternoons?|evenings?|tonight|today|yesterday|tomorrow|period|"
    r"summer|winter|spring|autumn|holidays?|hours?|minutes?)\b",
    re.IGNORECASE,
)
# One call among those counted: "including a call at 9:00 p.m.", "the last one at" (Codex on
# #169). "Between 1:55 and 2:01 p.m. ... five calls" dates the count itself.
_ONE_CALL_RE = re.compile(
    r"\b(?:including|included|includes|among|of\s+which|one\s+of)\b|"
    r"\b(?:first|last|final|second|third|latest|earliest)\s+of\b|\b(?:a|an|one|the|first|"
    r"last|final|second|third|each|another|latest|earliest)\s+(?:[\w-]+\s+){0,2}(?:call|one)\b",
    re.IGNORECASE,
)
# The words a no-contact claim code fills its sides for may use, beside the phone, the party,
# the range's date and the case's app names (Codex on #169).
_PLAIN_CONTACT_WORDS = frozenset(
    "there was were is has have had did does do not no never any ever at all contact contacts "
    "communication communications communicated communicate communicating between and with the "
    "a an on by via over using through telephone phone number before after since until prior "
    "to or of from app".split()
)
# One way only: "never sent anything to REYES", "never received anything from" (Codex on #169).
_ONE_DIRECTION_RE = re.compile(
    r"\b(?:sent|sends|sending|send|received|receives|receiving|receive|got|gets|heard|"
    r"contacted|contacts|contacting|reached|incoming|outgoing|inbound|outbound|forwarded)\b",
    re.IGNORECASE,
)
# Another act on a quoted message, which the stated date may date instead of its sending:
# "On March 16, REYES deleted the Telegram message ..." (Codex on #169).
_OTHER_ACT_RE = re.compile(
    r"\b(?:deleted|deletes|deleting|forwarded|forwards|forwarding|read|viewed|opened|saved|"
    r"edited|copied|shared|archived|starred|pinned|screenshotted|replied|responded|reacted|"
    r"recovered|found|located|retrieved|extracted|reviewed|discovered)\b",
    re.IGNORECASE,
)
# The word right before an open range's one date: "before May 1", "on or after", "since".
_OPEN_EDGE_BEFORE_RE = re.compile(r"\b(?:before|prior\s+to|until|after|since)\s+$", re.IGNORECASE)
_CALL_WORD_RE = re.compile(
    r"\b(?:calls?|called|calling|phoned|phoning|rang|dialed|dialled|voicemails?)\b", re.IGNORECASE
)
# "never texted X" or "never spoke with X": one kind of contact. The absence check reads
# messages and calls alike, so the words keep code from filling either scope (Codex on #169).
_MESSAGE_WORD_RE = re.compile(
    r"\b(?:texts?|texted|texting|messages?|messaged|messaging|wrote|writes?|written|writing|"
    r"chats?|chatted|chatting|dms?|dm'?d|e-?mails?|e-?mailed|e-?mailing|replied|replies|"
    r"spoke|speak|speaks|speaking|spoken|talked|talks?|talking)\b",
    re.IGNORECASE,
)
_OFFSET_EDGE_RE = re.compile(
    r"\b(?:minutes?|hours?|days?|nights?|weeks?|months?|years?|shortly|soon|right|just|"
    r"immediately|sometime|long|well)\s+(?:before|after|prior\s+to|since|until)\b",
    re.IGNORECASE,
)


# Apps that place calls of their own, which a phone's call log does not stand in for. Names
# that are also plain words count only as capitalised here or in capitals.
_OTHER_CALL_APPS_RE = re.compile(
    r"\b(?:whats\s?app|telegram|viber|face\s?time|skype|zoom|snapchat|instagram|facebook|kik|"
    r"wickr|threema|discord|wechat|textnow|hangouts|google\s+voice|video)\b",
    re.IGNORECASE,
)
_OTHER_CALL_APPS_CAP_RE = re.compile(
    r"\b(?:Signal|SIGNAL|Line|LINE|Wire|WIRE|Teams|TEAMS|Session|SESSION|Element|ELEMENT|"
    r"Messenger|MESSENGER|Duo|DUO|Meet|MEET)\b"
)


def _names_an_app_off_the_case(bare: str) -> bool:
    """True when the words name a calling app, whether or not the case holds it."""
    return bool(_OTHER_CALL_APPS_RE.search(bare) or _OTHER_CALL_APPS_CAP_RE.search(bare))


def _open_range_wording(bare: str) -> bool:
    """True when a no-contact claim's range is open ("never", "before May 1, 2023") and code
    runs it to the extraction's edge (R5). A range with both ends stated ("from March 10
    until March 12"), a time of day, a written time zone or "first" or "last" contact keeps
    the model's range, read as before (Codex on #169)."""
    if not _OPEN_RANGE_RE.search(bare) or time_mentions(bare) or _NUM_DATE_RE.search(bare):
        return False
    if any(_has_word(bare, w) for w in ("first", "last", "earliest", "latest")):
        return False
    if _OFFSET_EDGE_RE.search(bare):
        return False  # "two days after March 12": an offset code does not read
    dates = list(_DATE_RE.finditer(bare))
    if len(dates) > 1 or (dates and dates[0].group(5)):
        return False
    if dates and not _OPEN_EDGE_BEFORE_RE.search(bare[: dates[0].start()]):
        return False  # "On March 12, 2026, ... never": a stated day, not an open end
    rest = bare[: dates[0].start()] + " " + bare[dates[0].end() :] if dates else bare
    if _YEAR_RE.search(rest) or _OTHER_TIME_RE.search(rest):
        return False  # "During 2025", "in March", "on Mondays": a range code does not keep
    if unread_zone(bare) is not None:
        return False
    return not (dates and _DATE_ZONE_RE.match(bare[dates[0].end() :]))


_PART_DAY_RE = re.compile(
    rf"\b(?P<dir>after|before)\s+{_clock_re('t')}{_zone_opt('z')}", re.IGNORECASE
)


def stated_part_day(text: str, context: str = "") -> StatedWindow | None:
    """The part of one stated day an open time leaves, or None (PAST-30 fill c).

    "On May 7, 2023, there was no Wickr contact ... after 10:00 a.m. EDT" is 10:00 a.m. to
    midnight on May 7; "before 9 a.m." is midnight to 9:00 a.m. Only when the text, outside
    quoted words, states exactly one date (one day, with its year in the text or context) and
    exactly one time of day, written right after "after" or "before"; no "about", no numeric
    date, no weekday that is not the date's, no zone code cannot read. Anything else is None."""
    plain = _unquoted(text)
    years = {int(y) for y in _YEAR_RE.findall(text + " " + context)}
    if weekday_mismatch(plain, years) or unread_zone(plain) is not None:
        return None
    if _NUM_DATE_RE.search(text):
        return None
    dates = list(_DATE_RE.finditer(plain))
    times = list(_ANY_TIME_RE.finditer(plain))
    parts = list(_PART_DAY_RE.finditer(plain))
    if len(dates) != 1 or len(times) != 1 or len(parts) != 1:
        return None
    (m,), (t,), (p,) = dates, times, parts
    if not (p.start("th") <= t.start() < p.end()) or m.group(5):
        return None
    if _DATE_ZONE_RE.match(plain[m.end() :]) or _UNREAD_DATE_ZONE_RE.match(plain[m.end() :]):
        return None  # "On May 7, 2023 UTC, ... after 10:00 a.m.": the day's zone (Codex on #169)
    if _OFFSET_EDGE_RE.search(plain):
        return None  # "two hours after 10:00 a.m.": an offset code does not read
    before = plain[max(0, m.start() - 12) : m.start()]
    if any(_has_word(before, w) for w in (*OPEN_START, *OPEN_END)):
        return None
    if re.search(r"\b(?:about|approximately|around|roughly)\s*$", plain[: p.start()], re.I):
        return None
    y = int(m.group(3) or m.group(6) or 0) or (next(iter(years)) if len(years) == 1 else None)
    if y is None:
        return None
    try:
        day = date(y, _MONTHS[m.group(1).lower()], int(m.group(2)))
    except ValueError:
        return None
    tt = _clock(p.group("th"), p.group("tm"), p.group("tap"), p.group("tw"))
    if tt is None or p.group("tw"):
        return None  # "after midnight", "before noon": not read
    at = datetime.combine(day, tt)
    midnight = datetime.combine(day, time(0, 0))
    if p.group("dir").lower() == "after":
        start, end = at, midnight + timedelta(days=1)
    else:
        start, end = midnight, at
    raw = f"{plain[m.start() : m.end()].strip(' ,')}, {p.group(0).strip()}"
    return StatedWindow(raw, start, end, p.group("z"))


_COUNT_NOUNS = r"(?:messages?|texts?|calls?|times|emails?|chats?)"
_APPROX = ("about", "approximately", "around", "roughly", "nearly", "almost", "some", "over",
           "more than", "fewer than", "less than", "under")  # fmt: skip


# A count one side made: "sent 10 messages", "13 messages were sent by PETROV", "13 messages
# that PETROV sent", "13 messages went from PETROV to @northstar", "10 messages to X". The count
# check counts both directions between the two parties (checks/count.py), so it would count the
# replies too and fail a true "exactly". Any such word anywhere in the claim refuses the count,
# even one about something else ("After PETROV sent the photo, they exchanged 13 messages"):
# that costs coverage, never a wrong verdict.
_ONE_WAY_RE = re.compile(
    r"\b(?:sent|sends|sending|received|receives|receiving|wrote|writes|written|texted|"
    r"messaged|forwarded|got|went|came|incoming|outgoing|inbound|outbound)\b",
    re.IGNORECASE,
)
# Calls of a length: "two calls, each lasting more than ten minutes" (Codex on #169).
_CALL_LENGTH_RE = re.compile(
    r"\b(?:lasting|lasted|lasts|long|longer|shorter|duration|minutes?|mins?|seconds?|secs?|"
    r"hours?|hrs?)\b",
    re.IGNORECASE,
)
# A kind of call the call log does not record: "video calls", "audio calls" (Codex on #169).
_CALL_KIND_RE = re.compile(r"\b(?:video|videos|audio|voice)\b", re.I)
# A call one side placed: "two outgoing calls", "made four calls", "called X" (Codex on #169).
_ONE_WAY_CALL_RE = re.compile(
    r"\b(?:placed|placing|made|making|dialed|dialled|dialing|dialling|answered|missed|"
    r"returned|called|calling|rang)\b",
    re.IGNORECASE,
)
# "sent and received 13 messages": both directions together, as the check counts (Codex on #160).
_BOTH_WAYS_RE = re.compile(
    r"\b(?:sent|received|incoming|outgoing|inbound|outbound)\s+(?:and|or|and/or)\s+"
    r"(?:received|sent|incoming|outgoing|inbound|outbound)\b",
    re.IGNORECASE,
)
# "13 messages to X" or "from X", but not "to and from X" or a range of dates or times ("from
# March 10 to March 31", "from 9 a.m. to noon").
_ONE_WAY_AFTER_RE = re.compile(
    rf"^\s+(?:to|from)\b(?!\s+and\b)(?!\s+(?:(?:{_MONTH_RE})\b|\d|noon\b|midnight\b))",
    re.IGNORECASE,
)


# What a count's number counts: up to two words, then the noun ("13 Signal messages").
_COUNTED_RE = re.compile(rf"\s+(?:[\w-]+\s+){{0,2}}(?P<noun>{_COUNT_NOUNS})\b", re.IGNORECASE)


def stated_call_count(claim: str) -> int | None:
    """The one number of calls the claim states ("had four calls with X", "five Viber calls"),
    or None: no such number, two of them, or one `count_op` would refuse."""
    found = {
        v
        for n in re.finditer(r"(?<![\d.,])\b(?:\d+|[a-z]+(?:-[a-z]+)?)\b(?![.,]\d)", claim, re.I)
        if n.group(0).lower() not in ("a", "an")
        and (v := _number(n.group(0))) is not None
        and counts_calls(claim, v)
    }
    if len(found) != 1:
        return None
    (value,) = found
    try:
        count_op(claim, value)
    except Reject:
        return None
    return value


def counts_calls(claim: str, value: int) -> bool:
    """True when the claim's count of `value` counts calls ("had four calls with X")."""
    try:
        _, m = _count_match(claim, value)
    except Reject:
        return False
    return bool(re.fullmatch(r"calls?", m.group("noun"), re.I))


def _count_match(claim: str, value: int) -> tuple[int, re.Match[str]]:
    # The number in figures or in words ("13 messages", "thirteen messages"), never "a", and
    # never one part of a longer number: "twenty one", "one hundred" and "1,000" are read as
    # no count, not as 20, 1 or 1 (Codex on #164).
    at, m = 0, None
    for n in re.finditer(r"(?<![\d.,])\b(?:\d+|[a-z]+(?:-[a-z]+)?)\b(?![.,]\d)", claim, re.I):
        if n.group(0).lower() in ("a", "an") or _number(n.group(0)) != value:
            continue
        if _NEXT_TO_A_NUMBER_RE.search(claim[: n.start()]) or _NUMBER_GOES_ON_RE.match(
            claim, n.end()
        ):
            continue
        m = _COUNTED_RE.match(claim, n.end())
        if m is not None:
            at = n.start()
            break
    if m is None:
        raise Reject(f"{value} is not written in the claim as a number of messages or calls")
    return at, m


def count_op(claim: str, value: int) -> Literal["eq", "ge", "le"]:
    """How the claim compares its count, read from its words. Raises Reject when the number
    is not a count of records in the claim, the claim's comparison cannot be stated exactly
    ("about 13", "more than 13"), or the count is one the count check cannot make: "times",
    or records one side sent or received (it counts both directions). Calls are counted
    (validation fill f); the caller puts 'call' among the channels (`counts_calls`)."""
    at, m = _count_match(claim, value)
    if re.fullmatch(r"times", m.group("noun"), re.I):
        raise Reject("the claim counts times; the count check counts messages or calls")
    words = _BOTH_WAYS_RE.sub(" ", _unquoted(_flat(claim)))
    if re.fullmatch(r"calls?", m.group("noun"), re.I) and _ONE_WAY_CALL_RE.search(words):
        raise Reject("the claim counts calls one side made; the count check counts both directions")
    if re.fullmatch(r"calls?", m.group("noun"), re.I) and _CALL_LENGTH_RE.search(words):
        raise Reject("the claim counts calls of a length; the count check counts every call")
    if re.fullmatch(r"calls?", m.group("noun"), re.I) and _CALL_KIND_RE.search(words):
        # "two Telegram video calls": a call log keeps no video or audio kind (Codex on #169)
        raise Reject("the claim counts one kind of call; the count check counts every call")
    if _ONE_WAY_RE.search(words) or _ONE_WAY_AFTER_RE.match(claim[m.end() :]):
        raise Reject(
            "the claim counts messages one side sent or received; the count check counts both"
            " directions"
        )
    before = claim[max(0, at - 24) : at].lower()
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
} | {"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_UNITS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_ABOUT = ("about", "approximately", "around", "roughly", "nearly", "almost", "some")
# What a word before a stated call length makes of it. A bound reads as an open range, up to
# LONGEST_CALL_S above or from 1 second below (a call that lasted 0 seconds never connected).
_LENGTH_LEADS = {
    **dict.fromkeys(_ABOUT, "about"),
    **dict.fromkeys(("more than", "over", "longer than", "just over", "a little over",
                     "a little more than", "slightly more than", "well over"), "over"),
    **dict.fromkeys(("at least", "no less than", "no shorter than"), "at least"),
    **dict.fromkeys(("less than", "under", "shorter than", "just under", "a little under",
                     "a little less than", "slightly less than", "well under"), "under"),
    **dict.fromkeys(("at most", "no more than", "no longer than", "up to"), "at most"),
}  # fmt: skip
LONGEST_CALL_S = 86_400  # the open end of "more than" and "at least": one day
_LEAD_ALT = "|".join(w.replace(" ", r"\s+") for w in sorted(_LENGTH_LEADS, key=len, reverse=True))
_LENGTH_LEAD_RE = re.compile(rf"^(?P<lead>{_LEAD_ALT})\s+(?P<rest>.+)$", re.IGNORECASE)
_LEAD_BEFORE_RE = re.compile(rf"\b(?P<lead>{_LEAD_ALT})\s+$", re.IGNORECASE)
# a word that turns a bound round: "not more than", "never lasted over", "wasn't under",
# "cannot have lasted over" (apostrophes are made plain first)
_NEGATED_RE = re.compile(r"(?:\b(?:not|never|cannot)|n't)(?:\s+[\w'-]+){0,3}\s+$", re.IGNORECASE)
# a bound written after the length: "two minutes or less", "or more", "or so", "plus"
_BOUND_AFTER_RE = re.compile(
    r"^\s*,?\s*(?:(?:or|and)\s+(?:less|more|longer|shorter|under|over|fewer|greater|above|"
    r"below|up|so|thereabouts)\b|plus\b|\+)",
    re.IGNORECASE,
)
_UNIT = r"(?:second|sec|minute|min|hour|hr)s?\.?"
_NUM = r"\d+|an?|[a-z]+(?:[-\s][a-z]+)?"
# The claim's length goes on past the model's words, or starts before them: "more than a
# minute" of "more than a minute and a half", "30 seconds" of "two minutes and 30 seconds".
# Read alone, the part would be another length (Codex on #153).
_NUMBER_WORD = "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
_LENGTH_GOES_ON_RE = re.compile(
    rf"^\s*,?\s*(?:and\s+)?(?:a\s+half\b|(?:\d+|(?:{_NUMBER_WORD})(?:[-\s](?:{_NUMBER_WORD}))?)"
    rf"\s+{_UNIT}(?!\w))",
    re.IGNORECASE,
)
_LENGTH_GOES_BEFORE_RE = re.compile(rf"(?<!\w){_UNIT}\s*,?\s*(?:and\s+)?$", re.IGNORECASE)
# A number word right before or after a count's number: the number goes on ("twenty one").
_MORE_NUMBER = r"hundred|thousand|million|dozen|score"
_NEXT_TO_A_NUMBER_RE = re.compile(
    rf"(?<![\w-])(?:\d+|{_NUMBER_WORD}|{_MORE_NUMBER})[\s-]+(?:and\s+)?$", re.IGNORECASE
)
_NUMBER_GOES_ON_RE = re.compile(
    rf"[\s-]+(?:and\s+)?(?:\d+|{_NUMBER_WORD}|{_MORE_NUMBER})(?![\w-])", re.IGNORECASE
)
# One part of a length, with the precision its words state: "two minutes" to the minute,
# "a minute and a half" or "half an hour" to the half.
_HALF_PARTS = (
    re.compile(rf"(?P<n>{_NUM})\s+and\s+a\s+half\s+(?P<u>{_UNIT})", re.IGNORECASE),
    re.compile(rf"(?P<n>{_NUM})\s+(?P<u>{_UNIT})\s+and\s+a\s+half", re.IGNORECASE),
    re.compile(rf"(?:a\s+)?half(?:\s+an?)?[\s-]+(?P<u>{_UNIT})", re.IGNORECASE),
)
_PART_RE = re.compile(rf"(?P<n>{_NUM})\s+(?P<u>{_UNIT})", re.IGNORECASE)
# two parts: "two minutes and 30 seconds", "1 minute, 30 seconds"
_TWO_PARTS_RE = re.compile(rf"(?P<a>.+?{_UNIT})\s*,?\s*(?:and\s+)?(?P<b>.+)", re.IGNORECASE)


def _number(words: str) -> int | None:
    w = words.lower()
    if w.isdigit():
        return int(w)
    if w in ("a", "an"):
        return 1
    if w in _NUMBER_WORDS:
        return _NUMBER_WORDS[w]
    tens, _, ones = w.replace("-", " ").partition(" ")  # "forty-five", "twenty two"
    if tens in _NUMBER_WORDS and _NUMBER_WORDS[tens] >= 20 and _NUMBER_WORDS[tens] % 10 == 0:
        if ones in _NUMBER_WORDS and 1 <= _NUMBER_WORDS[ones] <= 9:
            return _NUMBER_WORDS[tens] + _NUMBER_WORDS[ones]
    return None


def _unit(words: str) -> int:
    return _UNITS[words.lower().rstrip(".").removesuffix("s")]


def _length(words: str) -> tuple[int, int]:
    """Seconds a plain stated length is, and the precision its words state it to. Raises
    Reject when the words are not one."""
    for i, half in enumerate(_HALF_PARTS):
        m = half.fullmatch(words)
        if m is not None:
            unit = _unit(m.group("u"))
            if unit == 1:  # "ten and a half seconds": records count whole seconds (Codex on #153)
                raise Reject(f"the duration {words!r} is in half seconds")
            n = 0 if i == 2 else _number(m.group("n"))
            if n is None:
                raise Reject(f"cannot read the number in {words!r}")
            return n * unit + unit // 2, unit // 2
    m = _PART_RE.fullmatch(words)
    if m is not None:
        n = _number(m.group("n"))
        if n is None:
            raise Reject(f"cannot read the number in {words!r}")
        unit = _unit(m.group("u"))
        return n * unit, unit
    m = _TWO_PARTS_RE.fullmatch(words)
    if m is not None:
        a, b = _PART_RE.fullmatch(m.group("a")), _PART_RE.fullmatch(m.group("b"))
        if a is not None and b is not None:
            na, nb = _number(a.group("n")), _number(b.group("n"))
            ua, ub = _unit(a.group("u")), _unit(b.group("u"))
            if na is not None and nb is not None and ub < ua and nb * ub < ua:
                return na * ua + nb * ub, ub
    raise Reject(f"cannot read the duration {words!r}")


def _plain_apostrophes(words: str) -> str:
    return words.replace("\u2019", "'").replace("\u2018", "'").replace("\u02bc", "'")


def duration_range(as_written: str, claim: str = "") -> tuple[int, int]:
    """Seconds a stated call length allows, read from its words by code.

    - "two minutes" is 120 to 179, to the precision the words state; "a minute and a half" is
      90 to 119; "two minutes and 30 seconds" is 150.
    - "about two minutes" (or "approximately", "around", ...) is 90 to 150 (25% either side).
    - A bound is an open range: "more than a minute and a half" is 91 seconds to a day,
      "at least two minutes" 120 to a day, "under two minutes" 1 to 119, "at most two minutes"
      1 to 120.
    - The claim's own words before the length count, whole: in "lasting more than two
      minutes", the words "two minutes" are read as "more than two minutes", and in "no more
      than two minutes" the words "more than two minutes" are read as "no more than".
    - Refused: a bound the claim turns round ("not more than", "never over", "wasn't under";
      "no more than" is read as "at most"), a bound written after the length ("two minutes
      or less", "or more", "or so", "plus"), in the model's words or the claim's, and words
      that are only part of the claim's length ("a minute" of "a minute and a half").
    """
    words = " ".join(_plain_apostrophes(as_written).split())
    m = _LENGTH_LEAD_RE.match(words)
    lead, rest = (m.group("lead"), m.group("rest")) if m else (None, words)
    if claim:
        text, leads = " ".join(_plain_apostrophes(claim).split()), set()
        i = text.lower().find(words.lower())
        while i >= 0:
            # the claim's whole lead before the length, which holds the model's lead if any
            head = text[: i + len(words) - len(rest)]
            if _LENGTH_GOES_ON_RE.match(text[i + len(words) :]) or _LENGTH_GOES_BEFORE_RE.search(
                head
            ):
                raise Reject(f"the claim's length goes on past the words {as_written!r}")
            before = _LEAD_BEFORE_RE.search(head)
            if before is not None:
                head = head[: before.start()]
            if _NEGATED_RE.search(head):
                raise Reject(
                    f"the claim writes 'not' or 'never' before the duration {as_written!r}"
                )
            if _BOUND_AFTER_RE.match(text[i + len(words) :]):
                raise Reject(f"the claim writes a bound after the duration {as_written!r}")
            leads.add(" ".join(before.group("lead").lower().split()) if before else None)
            i = text.lower().find(words.lower(), i + 1)
        if len(leads) > 1:
            raise Reject(
                f"the claim writes {as_written!r} more than once, with other words before it"
            )
        if leads:
            lead = leads.pop()
    v, step = _length(rest)
    kind = _LENGTH_LEADS[" ".join(lead.lower().split())] if lead else None
    if v < 1 or v > LONGEST_CALL_S:
        raise Reject(f"the duration {as_written!r} is not a call length")
    if kind == "about":
        return round(v * 0.75), round(v * 1.25)
    if kind == "over":
        return v + 1, LONGEST_CALL_S
    if kind == "at least":
        return v, LONGEST_CALL_S
    if kind == "under":
        if v < 2:
            raise Reject(f"the duration {as_written!r} is not a call length")
        return 1, v - 1
    if kind == "at most":
        return 1, v
    return v, v + step - 1


# A message quoted after a verb of saying: 'PETROV texted REYES: "its done"'. A quoted contact
# name ('saved as "Marc Garage"') is not a message.
_QUOTED_MESSAGE = re.compile(
    r"\b(?:wrote|texted|told|sent|said|messaged|replied|asked|posted)\b[^\"“]{0,60}[\"“]",
    re.IGNORECASE,
)

# A party written as the one a message went to: "wrote to the Discord user 'X'", "iMessage to
# (919) 888-7386", "told REYES", "texted REYES". Up to three words may stand between the word
# and the party ("to the Discord user"), but none of _NOT_BETWEEN ("to the group from PETROV":
# PETROV sent it), and an opening quote may lead a quoted name. "According to X" is a source.
# Words that end the recipient's phrase: "from" or "by" name the sender, and a joining word or
# a verb starts a new clause ("REYES texted back after PETROV wrote": PETROV is the writer).
_NOT_BETWEEN = (
    r"from|by|after|before|when|while|once|and|or|then|but|as|because|since|until|who|which|"
    r"that|back|wrote|writes|texted|texts|sent|sends|messaged|told|replied|said|asked|posted"
)
# "PETROV texted REYES, who replied 'ok'": a relative clause right after the party makes it the
# writer after all (Codex on #160).
_WHO_WROTE_RE = re.compile(
    r"^[\"”’']?\s*,?\s*who\s+(?:[\w-]+\s+)?(?:replied|wrote|texted|answered|responded|said|"
    r"sent|messaged|asked|posted|typed|emailed)\b",
    re.IGNORECASE,
)
_ADDRESSED_RE = re.compile(
    r"(?<!according )\b(?:to|with|told|texted|messaged|emailed|called)\s+"
    rf"(?:(?!(?:{_NOT_BETWEEN})\b)[\w-]+\s+){{0,3}}?[\"“‘']?$",
    re.IGNORECASE,
)


def only_addressed(value: str, text: str, quoted: str | None) -> bool:
    """True when every place the claim writes this party is as the one written to, so it
    cannot be the sender of the quoted message. Words inside the quoted message itself are
    words, not a party, and are skipped; a quoted name ('the user "DFIR Two"') is read from
    what leads its opening quote. A party the claim does not write is not judged here."""
    v, t = _flat(_nfc(value.strip())), _flat(_nfc(text))
    if not v:
        return False
    q = _flat(_nfc(quoted.strip())) if quoted else ""
    spans = [(m.start(), m.end()) for m in _QUOTE_SPAN_RE.finditer(t)]
    places: list[int] = []
    at = t.find(v)
    while at >= 0:
        span = next(((s, e) for s, e in spans if s <= at < e), None)
        if span is None:
            places.append(at)
        elif not (q and q in t[span[0] : span[1]]):
            places.append(span[0])
        at = t.find(v, at + 1)
    return bool(places) and all(
        _ADDRESSED_RE.search(t[:p]) and not _WHO_WROTE_RE.match(t[p + len(v) :]) for p in places
    )


# The writer of a quoted message, as the claim names it: 'PETROV wrote', 'Daniel Petrov texted
# REYES'. One to three capitalised words right before a verb of writing.
_WRITER_VERBS = r"wrote|texted|messaged|sent|told|replied|emailed|asked|posted"
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
        "message",  # "PETROV sent the Telegram message 'ok'"
        # "told REYES by iMessage", "wrote to the Discord user X", "told X in a Zoom chat"
        "by", "via", "in", "user", "account", "chat",
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


# What leads a quote that is a message, right before its opening mark: a verb of saying or
# writing, alone or with the one it went to ('PETROV texted REYES "ok"', 'a message reading
# "ok"'), a word for a message ('the Telegram message "ok"'), or a colon. Not a name's lead-in
# ('the contact saved as "Marc"', 'the LINE user "DFIR Two"').
_SAYING = (
    r"wrote|writes|writing|texted|texts|texting|told|tells|sent|sends|sending|said|says|saying|"
    r"messaged|replied|replies|replying|asked|asks|posted|posts|stated|states|stating|answered|"
    r"responded|typed|read|reads|reading"
)
# Words that may name who sent a quoted message, anywhere outside quotes ("which @northstar
# sent", "after receiving it from X", "writing"): with any of them, no record_time is made
# without a sender, so a writer the claim names is never left untested (PAST-30 fill a). "a
# message reading" names no one.
_NAMES_A_WRITER_RE = re.compile(
    rf"\b(?:(?!read\b|reads\b|reading\b)(?:{_SAYING})|from|by|via)\b", re.IGNORECASE
)
# A word for a message dated right before its quote is a cue too: 'the Wickr message of May 7,
# 2023, "..."' (PAST-30 fill a).
_MESSAGE_CUE_RE = re.compile(
    rf"(?:\b(?:{_SAYING})(?:\s+(?-i:{_RECIPIENT}))?|\b{_QUOTE_NOUNS}"
    rf"(?:\s+of\s+(?:{_DATE_RE.pattern}))?|:)\s*,?\s*$",
    re.IGNORECASE,
)


# A message's own words: "a Signal message (to X) reading". ("that read" leaves "read" as the
# nearest verb, which names no writer.)
_READING_RE = re.compile(
    r"\b((?:message|text|imessage|dm)(?:\s+to\s+Party)?)\s+reading\b", re.IGNORECASE
)


# A call's party is named plainly: not someone's ("PETROV's lawyer", "PETROV's phone"), and
# not someone acted for or spoken of ("on behalf of PETROV", "about REYES", "posing as X").
_NOT_A_PARTY_AFTER = re.compile(r"\s*['’]s\b", re.IGNORECASE)
_NOT_A_PARTY_BEFORE = re.compile(
    r"\b(?:of|for|about|like|than|posing\s+as|pretending\s+to\s+be|impersonating)\s*$",
    re.IGNORECASE,
)
# A word that joins another clause ("after speaking with PETROV", "while REYES waited"): a
# name there may belong to another event, so code reads no call party from such a claim.
_CLAUSE_JOINER_RE = re.compile(
    r"\b(?:but|then|while|when|whereas|although|though|because|since|until|unless|after|"
    r"before|so|who|whom|whose|which|where)\b",
    re.IGNORECASE,
)
# What may be a call's party whatever the case knows: a handle, an address, or a run of five
# or more digits.
_UNREAD_PARTY_RE = re.compile(r"@[\w.-]*\w|\S+@\S*\w|(?<![\w-])\+?\d[\d\s().-]{3,}\d(?![\w-])")
# Words that hand on what another wrote: 'REYES forwarded what PETROV posted: "ok"'.
_PASSED_ON_RE = re.compile(
    r"\b(?:forward\w*|quot(?:e|ed|es|ing)|relay\w*|repost\w*|shared|screenshot\w*)\b",
    re.IGNORECASE,
)
# 'SUBJECT-2 instructed SUBJECT-1 by Signal to destroy evidence, writing "..."': the one who
# instructed is the subject of "writing" (PAST-30 fill b). Between them only the recipient,
# the app, and a short errand in lower-case words (checked against _ERRAND_STOP).
_ERRAND_RE = re.compile(
    rf"(?<![\w@])(?P<name>[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){{0,2}})\s+"
    r"(?i:instructed|told|asked|directed|ordered|urged)\s+"
    rf"(?P<to>{_RECIPIENT})"
    r"(?:\s+(?i:by|via|on|over)\s+(?P<app>[\w]+(?:\s+[\w]+){0,2}?))?"
    r"\s+to\s+(?P<errand>[a-z]+(?:\s+[a-z]+){0,5})\s*,\s*writing\s*:?\s*[\"“‘']?\s*$"
)
# Errand words that may bring in someone else's words or another clause.
_ERRAND_STOP = frozenset(
    {
        "and", "but", "or", "then", "who", "whom", "whose", "which", "where", "when", "while",
        "he", "she", "they", "it", "we", "i", "you", "him", "her", "them", "his", "their",
        "its", "my", "our", "your", "message", "messages", "text", "texts", "reply", "words",
        "post", "email", "note", "chat", "what", "that",
    }
)  # fmt: skip
# The wordings fill b reads a sender from, for the cheap test before them.
_SENDER_WORDS_RE = re.compile(r"\bwriting\b|\breceiving\s+it\s+from\b", re.IGNORECASE)
# '... the Kik message "..." after receiving it from thisisdfirtwo_dm7@talk.kik.com.': the one
# it came from sent it (PAST-30 fill b). Only that wording, right after the quote, ending the
# claim.
_RECEIVED_FROM_RE = re.compile(
    r"^[\"”’']?\s*,?\s*(?:after|upon|on)\s+receiving\s+it\s+from\s+(?P<who>\S+?)\s*[.;]?\s*$",
    re.IGNORECASE,
)


def _last_end(pattern: re.Pattern[str], text: str) -> int:
    """Where the last match of the pattern in the text ends, or 0 when there is none."""
    return max((m.end() for m in pattern.finditer(text)), default=0)


def coverage_gap(
    claim: Claim, proposals: list[Proposal], names: frozenset[str] = frozenset()
) -> str | None:
    """What the kept proposals leave untested that the claim states, or None.

    A claim must not be judged on its easy parts: its key template must be there, a stated
    date must be tested by some time range, a stated time of day (outside quoted words) by a
    range that states one,
    and a quoted message, in a claim of any type, by a sender assumption: a meaning claim
    ("SUBJECT-2 told SUBJECT-1: \"...\"") is not tested with its writer unchecked. Outside a
    communication claim, a claim whose every quote is one of `names` (casefolded; a person's
    or an account's name: 'sent 13 messages to the Telegram user "Marcus R"') quotes no
    message.
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
    if _QUOTED_MESSAGE.search(claim.text) and "sender" not in kept:
        quotes = [m.group(0)[1:-1].strip() for m in _QUOTE_SPAN_RE.finditer(_flat(claim.text))]
        if claim.claim_type is ClaimType.COMMUNICATION or any(
            _nfc(q).casefold() not in names for q in quotes
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

        out = self.code_fills(claim, para, self._shaped(claim, out, call.id), allowed_ids, call.id)
        gap = coverage_gap(claim, out, frozenset(self._names()))
        if gap:
            self._drop(claim, None, f"{gap}; the claim stays unproven", call.id)
            return []
        return out

    def _shaped(self, claim: Claim, out: list[Proposal], call_id: str | None) -> list[Proposal]:
        """The proposals whose parameters fit their template, as the builder will check them.
        The rest are dropped here, before coverage_gap and before a sender's parties are
        copied into a time range, so a sender naming two parties never counts as testing who
        sent the message."""
        kept: list[Proposal] = []
        for p in out:
            try:
                parse_params(p.template_id, p.params)
            except ValueError as e:  # pydantic's ValidationError is a ValueError
                self._drop(claim, None, f"template {p.template_id!r}: {e}", call_id)
                continue
            kept.append(p)
        return kept

    def _drop(self, claim: Claim, index: int | None, reason: str, call_id: str | None) -> None:
        self.drops.append(FillerDrop(claim_id=claim.id, index=index, reason=reason,
                                     model_call_id=call_id))  # fmt: skip

    # -- words to typed parameters

    def _resolve(self, claim: Claim, para: str, p: _ProposalOut) -> Proposal:
        tpl = TEMPLATES[p.template_id]
        texts = (claim.text, para)
        params: dict[str, Any] = {}
        code_made = False  # code filled a parameter the model left out or got wrong

        for value in [*p.people, *p.handles, *p.phones, *(a.as_written for a in p.accounts)]:
            if not _verbatim(value, *texts):
                raise Reject(f"{value!r} is not written in the claim or its paragraph")
        if p.quoted_text:
            if not _verbatim(p.quoted_text, claim.text):
                raise Reject("quoted_text is not written in the claim")
            if tpl.id in MESSAGE_TEXT_TEMPLATES:
                if not _in_quotes(p.quoted_text, claim.text):
                    raise Reject(
                        f"{p.quoted_text.strip()!r} is not inside quotation marks in the claim"
                    )
                names = [*p.people, *p.handles, *(a.as_written for a in p.accounts)]
                if any(_nfc(n.strip()) == _nfc(p.quoted_text.strip()) for n in names):
                    # 'the Teams user "ThisIs DfirTwo"': a quoted name is a party, not words.
                    raise Reject(f"{p.quoted_text.strip()!r} is a party's name, not a message")
            params["quoted_text"] = p.quoted_text.strip()
        if tpl.id == "sender":
            for value in [*p.people, *p.handles, *(a.as_written for a in p.accounts)]:
                if only_addressed(value, claim.text, p.quoted_text):
                    raise Reject(
                        f"the claim writes {value.strip()!r} as the one the message went to,"
                        " not its sender"
                    )

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
                code_made = True

        channels = self._channels(claim.text, p.channels, tpl.id)
        if channels:
            params["channels"] = channels

        account_ids: set[str] = set()
        handles = [h.strip() for h in p.handles]
        named: set[str] = set()  # people the model wrote as accounts
        named_on: set[str] = set()  # the apps it wrote them on
        own_ids: set[str] = set()  # a phone's own accounts, the phone written as an account
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
                own = self._own_accounts(written, acc.app, claim.text)
                if own:
                    # "the TARGET PHONE's Kik account": the phone's own accounts on that app,
                    # as the phone recorded them, never its owner's wider links.
                    account_ids |= own
                    own_ids |= own
                    continue
                person = self._person_named(written) if "person_ids" in tpl.allowed else None
                if person is not None:
                    theirs = person_party(self.data, person).keys
                    same = self._accounts_named(acc, device_ids, claim.text, one=False)
                    if any(self.data.accounts[a].key not in theirs for a in same):
                        raise Reject(
                            f"{written!r} names a person and a {acc.app} account that is not"
                            " confirmed as theirs"
                        ) from None
                    # The app the model wrote the person on scopes their accounts, as the
                    # channel it is, which the claim must name; without it a message on any of
                    # their apps would do (Codex on #152).
                    (on,) = self._channels(claim.text, [acc.app], tpl.id)
                    if channels and on not in channels:
                        raise Reject(
                            f"{written!r} is written on {on}, which the proposal's channels"
                            " leave out"
                        ) from None
                    named.add(person)
                    named_on.add(on)
                    continue
                if "handles" in tpl.allowed and (written.startswith("@") or written in handles):
                    if written not in handles:
                        handles.append(written)
                    continue
                by_name = self._accounts_named(acc, device_ids, claim.text)
                if not by_name:
                    raise
                account_ids |= by_name
        if own_ids and account_ids - own_ids and tpl.id in TWO_SIDED_TEMPLATES:
            # The checks read every account id as one party, so the phone's side and the other
            # cannot both be accounts: 'no Wickr contact between the TARGET PHONE and X'. The
            # phone's side is its owner by confirmed stipulation, only when that person is
            # exactly the phone's own accounts (PAST-30: the phone as an account).
            owner = self._exact_owner(own_ids)
            if owner is None:
                raise Reject(
                    "the phone and another party are both written as accounts, and no person"
                    " is exactly the phone's own accounts"
                )
            account_ids -= own_ids
            code_made = True
            named.add(owner)
            named_on |= {self.data.accounts[a].app for a in own_ids}
        if named:
            params["person_ids"] = sorted(set(params.get("person_ids", [])) | named)
            if not channels:
                params["channels"] = sorted(named_on, key=str.lower)
        if handles:
            if "handles" not in tpl.allowed:
                raise Reject(f"template {tpl.id!r} does not take handles")
            params["handles"] = handles  # the checks resolve them from the data
        if account_ids:
            params["account_ids"] = sorted(account_ids)
        if tpl.id in WHOLE_APP_TEMPLATES:
            # However an account was found, on an app that holds more than the claim's word
            # names a count would count, and an absence fail on, messages it does not name.
            for app in sorted({self.data.accounts[a].app for a in account_ids}, key=str.lower):
                said = [w for w in APP_ALIASES.get(app.casefold(), ()) if _has_alias(claim.text, w)]
                if app.casefold() in WIDER_APPS and said:
                    raise Reject(
                        f"{app!r} holds more than the claim's {said[0]!r} names, so no count or"
                        " absence is read on its accounts"
                    )

        if (
            tpl.id == "record_time"
            and not p.quoted_text
            and not (params.get("person_ids") or account_ids or handles)
            and any(_has_word(_unquoted(claim.text), w) for w in CHANNEL_WORDS["call"])
        ):
            # A call the model named without its parties: code reads them from the claim.
            app = self._call_app(claim.text, params.get("channels", []))
            people, accounts, phone = self._call_parties(claim, device_ids, app)
            code_made = True
            params["channels"] = sorted({CALL_CHANNEL, app}, key=str.lower)
            if phone and not device_ids:
                # The phone the claim writes scopes the search, and gives the window its zone.
                device_ids = phone
                params["device_ids"] = phone
            if people:
                params["person_ids"] = people
            if accounts:
                params["account_ids"] = accounts

        if (
            p.count is not None
            and tpl.id == "record_time"
            and counts_calls(claim.text, p.count.value)
        ):
            pass  # a time range takes no count; code adds the count of calls (_add_call_count)
        elif p.count is not None:
            params["count_op"] = count_op(claim.text, p.count.value)
            params["expected_count"] = p.count.value
            if tpl.id == "message_count" and counts_calls(claim.text, p.count.value):
                self._count_calls(claim, params)
                # The phone it may read from the claim gives the window its zone (Codex on #169).
                device_ids = list(params.get("device_ids", device_ids))
                code_made = True

        if p.duration is not None:
            if not _verbatim(p.duration.as_written, claim.text):
                raise Reject("the duration's words are not written in the claim")
            params["duration_s"] = duration_range(p.duration.as_written, claim.text)

        if tpl.id == "no_contact" and not (params.get("person_ids") or account_ids or handles):
            # "The TARGET PHONE never communicated with (919) 555-0142": the model named the
            # phone but no party; code reads both from the claim (validation ruling R5).
            device_ids = self._absence_parties(claim, params, device_ids)
            code_made = True
        open_range = tpl.id == "no_contact" and _open_range_wording(_unquoted(_nfc(claim.text)))
        if open_range and not device_ids:
            # "On dev:item1, there was no contact between PETROV and REYES before ...": the
            # phone the claim writes scopes the range (Codex on #169).
            written = sorted(self._written_phones(_unquoted(_nfc(claim.text))))
            if len(written) == 1:
                device_ids = params["device_ids"] = written
        if open_range and len(device_ids) == 1:
            # "before May 1, 2023", "never": the range runs to the extraction's own edge, which
            # code reads from the records, never the model (validation ruling R5).
            params["window"] = self._open_range(claim, device_ids, para)
            code_made = True
        elif p.window is not None and "window" not in tpl.allowed:
            pass  # a sender is picked by its words and party; the time is record_time's job
        elif p.window is not None:
            try:
                params["window"] = self._window(claim.text, para, p.window, device_ids, tpl.id)
            except Reject as refused:
                # The model's range is refused; use the range the claim states that day.
                try:
                    params["window"] = self._stated(claim, para, device_ids, tpl.id, p.window.start)
                    code_made = True
                except Reject as e:
                    raise Reject(f"{refused}, and {e}") from None
        elif "window" in tpl.required:
            params["window"] = self._stated(claim, para, device_ids, tpl.id, None)
            code_made = True

        return Proposal(p.template_id, params, is_core=True, code_made=code_made)

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
        stated = stated_windows(claim.text, para)
        if stated is None:
            part = stated_part_day(claim.text, para)
            stated = [part] if part is not None else []
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
        return self._zoned_window(w.zone, w.start, w.end, device_ids, w.raw)

    def the_quote(self, claim: Claim, out: list[Proposal]) -> str | None:
        """The one message the claim quotes, word for word, or None.

        The quoted words a kept proposal already uses (verified verbatim and inside quotation
        marks) are that message when all such proposals use the same words and those words
        lie in a quote that is a message. With none, the claim must hold exactly one quoted
        span that is not a name (a person the expert created, or an account's identifier or
        display name: 'the Teams user "ThisIs DfirTwo"'), led by what leads a message
        (_MESSAGE_CUE_RE: "PETROV wrote: ...", "a message reading ...", not "saved as ..."),
        on one line. Two such quotes, or any doubt, give None: code never picks one."""
        text, names = _nfc(claim.text), self._names()
        spans = [
            m.span()
            for m in _QUOTE_SPAN_RE.finditer(_flat(text))
            if m.group(0)[1:-1].strip() and m.group(0)[1:-1].strip().casefold() not in names
        ]
        messages = [(s, e) for s, e in spans if _MESSAGE_CUE_RE.search(text[:s])]
        used = {
            str(p.params["quoted_text"])
            for p in out
            if p.template_id in MESSAGE_TEXT_TEMPLATES
            and isinstance(p.params, dict)
            and p.params.get("quoted_text")
        }
        if used:
            # The model's words, when they lie in a quote that is a message.
            (words,) = used if len(used) == 1 else (None,)
            inside = words is not None and any(
                _flat(_nfc(words)) in _flat(text)[s + 1 : e - 1] for s, e in messages
            )
            return words if inside else None
        if len(spans) != 1 or len(messages) != 1:
            return None
        start, end = messages[0]
        words = text[start + 1 : end - 1].strip()
        return None if "\n" in words or "\r" in words else words

    def _names(self) -> set[str]:
        """Every name a quote must not be read as a message for: persons the expert created
        (whole and last name) and accounts' identifiers and display names, casefolded."""
        names: set[str] = set()
        for (full,) in self.conn.execute("SELECT name FROM persons"):
            parts = _nfc(full.strip()).casefold().split()
            names |= {" ".join(parts), *parts[-1:]}
        for a in self.data.accounts.values():
            names |= {_nfc(x.strip()).casefold() for x in (a.identifier, a.display_name) if x}
        return names

    def _add_sender(
        self, claim: Claim, out: list[Proposal], allowed_ids: set[str]
    ) -> list[Proposal]:
        """A claim that quotes a message and names its writer ("PETROV wrote to REYES: ...")
        but got no sender assumption gets it from code: the claim's one quoted message
        (`the_quote`) sent by the person `stated_sender` reads, or by the party
        `received_from` reads, on the one app the claim names if it names one. Otherwise the
        claim keeps no sender, and coverage_gap refuses it."""
        if "sender" not in allowed_ids or any(p.template_id == "sender" for p in out):
            return out
        if not (_QUOTED_MESSAGE.search(claim.text) or _SENDER_WORDS_RE.search(claim.text)):
            return out
        quote = self.the_quote(claim, out)
        writer = self.stated_sender(claim, quote) if quote else None
        party = {"person_ids": [writer]} if writer else self.received_from(claim, quote)
        if quote is None or party is None:
            return out
        params: dict[str, Any] = {"quoted_text": quote, **party}
        apps = self._message_apps(claim.text)
        if apps is None:
            return out  # a phone's messages, in a case that holds none
        if apps:  # the search stays on the apps named
            params["channels"] = apps
        phones = self._written_phones(_unquoted(_nfc(claim.text)))
        if len(phones) > 1:
            return out  # two phones: code never picks the one the message is on
        if phones:  # "On Item 1, PETROV wrote ...": the search stays on that phone (Codex)
            params["device_ids"] = sorted(phones)
        return [*out, Proposal("sender", params, code_made=True)]

    def _message_apps(self, claim_text: str) -> list[str] | None:
        """The apps a code-made sender searches: the apps the claim names other than a phone's
        ("told REYES on Telegram"), or, when it names only a phone's ("texted", "by iMessage"),
        every app in the case that holds a phone's messages, since "texted" may be SMS or
        iMessage (Codex on #164); None when the case holds no such app. Empty when the claim
        names no app."""
        if named := self._named_apps(claim_text):
            return named
        words = _ADDRESS_RE.sub(" ", _unquoted(claim_text))
        phone = [  # with an app that holds a phone's messages (iOS "Native Messages")
            app
            for app in self.channels()
            if app != CALL_CHANNEL
            and (namespace(app) == "tel" or app.strip().casefold() in WIDER_APPS)
        ]
        said = any(_has_word(words, w) for w in _PHONE_MESSAGE_WORDS) or any(
            _has_word(words, w) or _has_alias(words, w)
            for app in phone
            for w in (
                *CHANNEL_WORDS.get(app.casefold(), (app.casefold(),)),
                *APP_ALIASES.get(app.casefold(), ()),
            )
        )
        if not said:
            return []
        return phone or None

    def code_fills(
        self,
        claim: Claim,
        para: str,
        out: list[Proposal],
        allowed_ids: set[str],
        call_id: str | None,
    ) -> list[Proposal]:
        """Code's own fills after the model's items, in order: sender, time, call count and
        meaning. The first pass and the testability step's repair both run exactly these
        (Codex on #169)."""
        out = self._shaped(claim, self._add_sender(claim, out, allowed_ids), call_id)
        out = self._shaped(claim, self._add_record_time(claim, para, out, allowed_ids), call_id)
        out = self._shaped(claim, self._add_call_count(claim, out, allowed_ids), call_id)
        return self._add_meaning(claim, out, allowed_ids, call_id)

    def _add_call_count(
        self, claim: Claim, out: list[Proposal], allowed_ids: set[str]
    ) -> list[Proposal]:
        """A claim that counts calls ("had five calls with (828) 520-5789") whose model answer
        gave one call's time range but no count gets the count from code: the same parties,
        phone and window, 'call' on the same app, and the one number of calls it states
        (validation fill f). The phone's side is its exact owner (`_count_calls`)."""
        if "message_count" not in allowed_ids or any(p.template_id == "message_count" for p in out):
            return out
        value = stated_call_count(claim.text)
        bare = _unquoted(_nfc(claim.text))
        if time_mentions(bare) and _ONE_CALL_RE.search(bare):
            # "two calls ..., including a call at about 9:00 p.m.": the time range dates one
            # call, not the count's own span (Codex on #169).
            return out
        times = [
            p
            for p in out
            if p.template_id == "record_time"
            and isinstance(p.params, dict)
            and CALL_CHANNEL in p.params.get("channels", [])
            and not p.params.get("quoted_text")
        ]
        if value is None or len(times) != 1:
            return out
        allowed = TEMPLATES["message_count"].allowed
        params = {k: v for k, v in dict(times[0].params).items() if k in allowed}
        params |= {"count_op": count_op(claim.text, value), "expected_count": value}
        try:
            self._count_calls(claim, params)
        except Reject:
            return out  # the call's time stays tested; its count does not
        return [*out, Proposal("message_count", params, is_core=True, code_made=True)]

    def _add_meaning(
        self, claim: Claim, out: list[Proposal], allowed_ids: set[str], call_id: str | None
    ) -> list[Proposal]:
        """A claim whose type needs a meaning assumption (REQUIRED_TEMPLATES) and got none
        gets it from code on the claim's one quoted message (`the_quote`). Meaning has no
        check, so only the expert's acceptance can cover it: this keeps the claim's reading
        in front of the expert, and never makes Supported easier."""
        needed = REQUIRED_TEMPLATES.get(claim.claim_type, frozenset())
        if "meaning" not in needed or "meaning" not in allowed_ids:
            return out
        if any(p.template_id == "meaning" for p in out):
            return out
        quote = self.the_quote(claim, out)
        if quote is None:
            self._drop(claim, None, "meaning from the claim: no one quoted message", call_id)
            return out
        return [*out, Proposal("meaning", {"quoted_text": quote}, is_core=True, code_made=True)]

    def _add_record_time(
        self, claim: Claim, para: str, out: list[Proposal], allowed_ids: set[str]
    ) -> list[Proposal]:
        """A claim that dates a quoted message ("On March 12, 2026, PETROV wrote ...") and got
        a sender assumption but no time range gets the record_time assumption from code: the
        sender's parties and words, in the one range the claim states. With no sender at all,
        the claim's one quoted message (`the_quote`) on the apps it names (`_message_apps`)
        and the one phone it writes, if any, with no party: "The Wickr message of May 7,
        2023, \"...\"", "received a Kik message reading \"...\"" (PAST-30 fill a). Whoever
        sent it stays untested, and coverage_gap still asks for a sender where the claim
        names a writer."""
        if "record_time" not in allowed_ids or not date_mentions(claim.text):
            return out
        if _OTHER_ACT_RE.search(_unquoted(_nfc(claim.text))):
            # "On March 16, REYES deleted the message ... after receiving it from PETROV": the
            # date may be that act's, not the sending's, sender or no (Codex on #169)
            return out
        # A range only a model-read event or role holds is no check's: it does not stop this.
        if any(
            isinstance(p.params, dict) and p.params.get("window") and p.template_id in _TIMED
            for p in out
        ):
            return out
        senders = [p for p in out if p.template_id == "sender" and isinstance(p.params, dict)]
        if (
            not senders
            and not any(p.template_id == "sender" for p in out)
            and not _NAMES_A_WRITER_RE.search(_unquoted(_nfc(claim.text)))
            # "PETROV's Telegram message of March 12" names its writer too (Codex on #169).
            and not _NOT_A_PARTY_AFTER.search(_unquoted(_nfc(claim.text)))
        ):
            quote = self.the_quote(claim, out)
            apps = self._message_apps(claim.text) if quote else None
            phones = self._written_phones(_unquoted(_nfc(claim.text)))
            if quote is None or apps is None or len(phones) > 1:
                return out
            if not apps and _names_an_app_off_the_case(_unquoted(_nfc(claim.text))):
                return out  # "the Signal message" on a case with no Signal (Codex on #169)
            if self._names_a_recipient(_unquoted(_nfc(claim.text))):
                # "REYES received a Telegram message reading ...": a time on anyone's
                # message would not keep the party the claim names (Codex on #169)
                return out
            senders = [Proposal("sender", {"quoted_text": quote}
                                | ({"channels": apps} if apps else {})
                                | ({"device_ids": sorted(phones)} if phones else {}))]  # fmt: skip
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
        return [*out, Proposal("record_time", params, is_core=True, code_made=True)]

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
        Between them a phone number or a quoted name the case knows reads as one name, an
        app's name may stand ("by iMessage"), and "a message reading" leaves the verb before
        it governing (`_parties_as_names`). "by" or "via" must name an app. Anything else (no
        quote, words before it that forward, quote or share a message, "said", "answered", a
        name that is no person) names no writer."""
        if not quoted or not quoted.strip():
            return None
        at = _nfc(claim.text).find(_nfc(quoted.strip()))
        if at < 0:
            return None
        before = _nfc(claim.text)[:at]
        after = _nfc(claim.text)[at + len(_nfc(quoted.strip())) :]
        if _PASSED_ON_RE.search(before):
            return None  # the words may be another's, handed on
        if errand := _ERRAND_RE.search(before):
            return self._errand_writer(claim.text, before, errand, after)
        verbs = [
            v for v in _QUOTING_RE.finditer(before) if not self._passes_quote_on(before, v, after)
        ]
        if not verbs or at - verbs[-1].end() > QUOTE_REACH:
            return None
        last = verbs[-1]
        match = next((m for m in _WRITER_RE.finditer(before) if m.end() == last.end()), None)
        if match is None:
            return None
        between = self._parties_as_names(before[last.end() :])
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

    def _errand_writer(
        self, claim_text: str, before: str, m: re.Match[str], after: str
    ) -> str | None:
        """The person who instructed, when 'X instructed Y [by App] to <errand>, writing'
        leads the quote: X must be exactly one person the expert created and not Y, the app
        one the claim names, the errand plain lower-case words, and the quote must end the
        sentence with no new subject after it. Anything else names no writer."""
        errand = m.group("errand").split()
        if any(w in _ERRAND_STOP for w in errand):
            return None
        app = m.group("app")
        if app is not None and app.casefold() not in {
            a.casefold() for a in self._named_apps(claim_text)
        } | {
            w.casefold()
            for a in self._named_apps(claim_text)
            for w in (*CHANNEL_WORDS.get(a.casefold(), ()), *APP_ALIASES.get(a.casefold(), ()))
        }:
            return None
        if _SUBJECT_AFTER.search(after) or not _QUOTE_ENDS_CLAUSE.match(after):
            return None
        prefix = before[: m.start("name")]
        if _NOT_THE_WRITER_BEFORE.search(prefix) or _POSSESSIVE_BEFORE.search(prefix):
            return None
        writer = self._person_named(m.group("name"))
        to = self._person_named(m.group("to"))
        if writer is None or writer == to:
            return None
        return writer

    def received_from(self, claim: Claim, quoted: str | None) -> dict[str, list[str]] | None:
        """The party a quoted message came from when the claim says so right after the quote
        ('... "ok" after receiving it from X.'), as sender parameters, or None. X must be one
        person the expert created, or one account on the one app the claim names, found by
        its exact identifier. Words before the quote that hand it on or name a writer refuse."""
        if not quoted or not quoted.strip():
            return None
        text = _nfc(claim.text)
        at = text.find(_nfc(quoted.strip()))
        if at < 0:
            return None
        before, after = text[:at], text[at + len(_nfc(quoted.strip())) :]
        m = _RECEIVED_FROM_RE.match(after)
        if m is None or _PASSED_ON_RE.search(before) or _QUOTING_RE.search(before):
            return None
        who = m.group("who").strip()
        person = self._person_named(who)
        if person is not None:
            return {"person_ids": [person]}
        apps = self._named_apps(claim.text)
        if len(apps) != 1:
            return None
        try:
            ids = self._accounts(_Account(as_written=who, app=apps[0]), [], claim.text)
        except Reject:
            return None
        if len({self.data.accounts[a].key for a in ids}) != 1:
            return None
        return {"account_ids": sorted(ids)}

    def _parties_as_names(self, between: str) -> str:
        """The words between the writer's verb and the quote, with each party written as
        something other than a name read as one name ("Party"): a phone number ("to (919)
        888-7386"), and a quoted name of a person or an account ('the Discord user "josh
        #3283"'). "reading" right after a message ('a Signal message to (919) 888-7386
        reading "..."') is the message's words, so it is dropped: the verb before still
        governs. Any other quote between stays and refuses the writer."""
        names = self._names()

        def quoted(m: re.Match[str]) -> str:
            return " Party " if m.group(0)[1:-1].strip().casefold() in names else m.group(0)

        def number(m: re.Match[str]) -> str:
            # Only the number becomes "Party": a sentence's full stop after it stays, so a
            # new sentence still hands the quote on ("to (919) 888-7386. REYES: ..."; Codex).
            raw = m.group(0)
            words = raw.strip(" .,-")
            if phone_digits(words) is None:
                return raw
            at = raw.find(words)
            return raw[:at] + " Party " + raw[at + len(words) :]

        out = _QUOTE_SPAN_RE.sub(quoted, _nfc(between))
        out = _PHONE_RE.sub(number, out)
        return _READING_RE.sub(r"\1", out)

    def _plain_between(self, between: str) -> bool:
        """True when every word between the writer's verb and the quote is on the list that
        cannot hand the quote on (see _BETWEEN_WORDS)."""
        names = {
            part
            for (full,) in self.conn.execute("SELECT name FROM persons")
            for part in _nfc(full).casefold().split()
        }
        apps = {c.casefold() for c in self.channels()} | {
            w.casefold() for words in APP_ALIASES.values() for w in words if " " not in w
        }
        if "\n" in between or "\r" in between:
            return False  # a new line can carry a new label ("REYES\nSMITH: 'ok'")
        mixed_case = bool(re.search(r"[a-z]", re.sub(r"@[\w.-]+", "", between)))
        last_end, last_capital = 0, False  # the word before: where it ends, and its kind
        last_digit = by_app = False  # by_app: "by" or "via" must name an app ("by iMessage")
        for m in re.finditer(r"@[\w.-]+|\w[\w'’.-]*", between):
            word = m.group(0)
            w = re.sub(r"['’]s$", "", word.casefold()).strip(".'’-")
            # Between words only spaces and commas ("2:31" aside): a dash, a bracket or a
            # colon can set a new label on the quote ("REYES — @northstar: 'ok'").
            gap = between[last_end : m.start()]
            if not (re.fullmatch(r"[\s,]*", gap) or (gap == ":" and last_digit and w.isdigit())):
                return False
            if by_app and w not in apps:
                return False  # "a message by PETROV": PETROV may be the writer
            by_app = w in ("by", "via")
            known = (
                word.startswith("@")
                or w.isdigit()
                or w in _BETWEEN_WORDS
                or w in _TITLES
                or (w in names and word[0].isupper())  # "Will", not the word "will"
                or w in apps  # "by iMessage": an app's name, in any case
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
        if by_app or not re.fullmatch(r"\s*[,:]?\s*[\"'“‘]*\s*", tail):
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

    def _written_phones(self, text: str) -> set[str]:
        """The devices the text writes by id, source id, label or a name the expert gave them
        ("the TARGET PHONE", "Item 1"), compared as `_device` compares: case and spacing do
        not count."""
        named = logged_names(self.conn)
        return {
            did
            for did, sid, label in self.conn.execute("SELECT id, source_id, label FROM devices")
            for x in (did, sid, label, *named.get(did, []))
            if x
            and name_key(x)
            and re.search(
                r"(?<!\w)" + r"\s*".join(map(re.escape, name_key(x))) + r"(?!\w)", text, re.I
            )
        }

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
        # The claim may write another export's full name for that word, "Wickr Me" for a case
        # that holds only Wickr Pro: it means that app, not this one (Codex on #150).
        for k, words in APP_ALIASES.items():
            if k != canon.casefold() and set(words) & set(said) and _has_word(claim_text, k):
                raise Reject(f"the claim names {k.title()!r}, not {canon!r}")
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
        """The accounts on the model's app with this identifier. A number finds every account
        on that app whose identifier is the same number, however it is written ("(919)
        888-7386", "+19198887386", "19198887386@s.whatsapp.net"), on a phone app, the phone's
        call log, or an app the claim names: a number alone never picks the app. They are one
        party: the same digits, only the formatting differs (ruling R6)."""
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
        named = app == NATIVE_CALL_APP or self._app_named(claim_text, acc.app)
        if number is not None and named:
            # One number written two ways on one app ("+19195677484" and "9195677484", from two
            # databases) is one party: the same digits, only the formatting differs (ruling
            # R6). Display names, addresses and user ids are never read as numbers.
            hits |= {a.id for a in mine if _same_number(number, a)}
        if not hits:
            raise Reject(f"{acc.as_written!r} on {acc.app} matches no account in the case")
        return hits

    def _named_apps(self, claim_text: str) -> list[str]:
        """The apps the claim names the way `_channels` requires, phone apps aside (a phone
        app is never picked by the words). An app's name inside an address names no app
        ("thisisdfirtwo@gmail.com"), and neither does one inside a quoted message ('texted
        "use Telegram"'; Codex on #164)."""
        words = _ADDRESS_RE.sub(" ", _unquoted(claim_text))
        named = []
        for app in self.channels():
            if app == CALL_CHANNEL or namespace(app) == "tel":
                continue
            try:
                self._channels(words, [app])
            except Reject:
                continue
            named.append(app)
        return named

    def _call_app(self, claim_text: str, channels: list[str]) -> str:
        """The one app the claim names for a call ("a Signal call"), which any app the
        proposal names must be. A call on no named app, or on two, is refused: the words
        alone never pick the app."""
        if _CALL_KIND_RE.search(_unquoted(_nfc(claim_text))):
            # "a Telegram video call": the call log keeps no kind, so any call would match
            raise Reject("the claim names a kind of call the call log does not record")
        named = self._named_apps(claim_text)
        if (
            not named
            and NATIVE_CALL_APP in self.channels()
            and _writes_a_number(claim_text)
            # "a Signal call" on a case with no Signal is no call-log call (Codex on #169)
            and not _names_an_app_off_the_case(_unquoted(_nfc(claim_text)))
        ):
            # "placed an outgoing telephone call to (919) 567-7484": the phone's call log (R1).
            # _call_parties then takes only numbers as the other party.
            named = [NATIVE_CALL_APP]
        if len(named) != 1:
            raise Reject(f"the claim names {len(named)} apps for the call, not one")
        (app,) = named
        if any(c not in (CALL_CHANNEL, app) for c in channels):
            raise Reject(f"the proposal's channels are not the claim's {app!r} call")
        return app

    def _call_parties(
        self, claim: Claim, device_ids: list[str], app: str
    ) -> tuple[list[str], list[str], list[str]]:
        """The parties of a call the claim describes, read from its own words: each person
        the expert created whom it names, and each number, identifier or quoted display name
        it writes, on the claim's one app. Each must be exactly one person or one account,
        and plainly a party (no possessive, role word or second clause: Baker Eval on #164);
        if any is not, or the claim names none, nothing is filled. The phone the call was on
        ("the TARGET PHONE") is no party: it scopes the search, and the third list is that
        phone's device when the claim writes exactly one and the model gave none."""
        text = _nfc(claim.text)
        bare = _unquoted(text)
        joiner = _CLAUSE_JOINER_RE.search(bare)
        if joiner:
            raise Reject(f"the claim joins another clause ({joiner.group(0)!r}) to the call")
        spans: list[tuple[int, int]] = []  # where each party is written
        people: set[str] = set()
        for pid, name in self.conn.execute("SELECT id, name FROM persons ORDER BY id"):
            if found := _name_spans(bare, _nfc(name.strip())):
                people.add(pid)
                spans += found
        written: list[str] = []
        numbers: list[str] = []
        for m in _PHONE_RE.finditer(bare):
            if phone_digits(m.group(0).strip(" .,-")) is not None:
                written.append(m.group(0).strip(" .,-"))
                numbers.append(m.group(0).strip(" .,-"))
                spans.append(m.span())
        for m in _QUOTE_SPAN_RE.finditer(_flat(text)):
            if m.group(0)[1:-1].strip():
                written.append(m.group(0)[1:-1].strip())
                spans.append(m.span())
        ids = {
            a.identifier.strip()
            for a in self.data.accounts.values()
            if a.app == app
            and len(a.identifier.strip()) >= 6
            and not re.search(r"\s", a.identifier)
        }
        for i in sorted(ids):
            for m in re.finditer(rf"(?<![\w.:@-]){re.escape(i)}(?![\w@-])", bare):
                written.append(i)
                spans.append(m.span())
        for start, end in spans:
            if _NOT_A_PARTY_AFTER.match(bare, end) or _NOT_A_PARTY_BEFORE.search(bare[:start]):
                raise Reject(f"{text[start:end]!r} may not be a party to the call")
        # A handle, address or long number the case does not know is a party code cannot
        # read, so nothing is filled: "a Telegram call to @unknownuser" (Codex on #164).
        for m in _UNREAD_PARTY_RE.finditer(bare):
            if not any(s <= m.start() and m.end() <= e for s, e in spans):
                raise Reject(f"{m.group(0)!r} is not one account the call could be with")
        if app == NATIVE_CALL_APP and (people or any(phone_digits(w) is None for w in written)):
            # The call log by number only: a name or a display name with no app is refused (R1).
            raise Reject("a call on no named app is read only with a phone number as its party")
        accounts: set[str] = set()
        groups: list[set[Key]] = []  # the accounts each party is, merged where they share one
        for words in dict.fromkeys(written):
            person = self._person_named(words)
            acc = _Account(as_written=words, app=app)
            if person is not None:
                # A name an account on the app also carries may be that account, which no one
                # has linked to the person: 'the Telegram user "Marcus Reyes"' (Codex on #164).
                try:
                    shared = self._accounts_named(acc, device_ids, claim.text, one=False)
                except Reject:
                    shared = {""}
                if shared:
                    raise Reject(f"{words!r} names a person and an account on {app}")
                people.add(person)
                continue
            try:
                found = self._accounts(acc, device_ids, claim.text)
            except Reject:
                found = self._accounts_named(acc, device_ids, claim.text)
            keys = {self.data.accounts[a].key for a in found}
            number = phone_digits(words)
            one_number = number is not None and all(
                _same_number(number, self.data.accounts[a]) for a in found
            )
            if not keys or (len(keys) != 1 and not one_number):
                raise Reject(f"{words!r} on {app} is not one account the call could be with")
            accounts |= found
            groups = [g for g in groups if not g & keys] + [
                keys.union(*(g for g in groups if g & keys))
            ]
        if len(groups) > 1:
            # The checks read every account id as one party, either of them (Codex on #164).
            raise Reject("the claim writes two parties as accounts; a check reads them as one")
        if not people and not accounts:
            raise Reject("the claim names no party for the call")
        # Both sides, or the phone and one account ("(919) 888-7386 called the TARGET PHONE"):
        # a person alone may be the phone's own side, with the other side a name code cannot
        # read ("On the TARGET PHONE, PETROV called Jonathan"; Codex on #164).
        written = self._written_phones(bare)
        phone = sorted(written) if not device_ids and len(written) == 1 else []
        sides = len(people) + bool(accounts) + bool((device_ids or phone) and not people)
        if sides < 2:
            raise Reject("the claim names one side of the call; code reads both or none")
        return sorted(people), sorted(accounts), phone

    def _absence_parties(
        self, claim: Claim, params: dict[str, Any], device_ids: list[str]
    ) -> list[str]:
        """The two sides of "no contact" read from the claim when the model named none: the
        one phone it writes, as its owner by confirmed stipulation when that person is exactly
        the phone's own accounts, and one other party, a person the expert created or a phone
        number (every account on the phone's sources whose identifier is that number, on the
        apps the proposal names, or on any app when it names none). Returns the device ids.
        Raises Reject when either side is not exactly one."""
        bare = _unquoted(_nfc(claim.text))
        phones = sorted(set(device_ids) or self._written_phones(bare))
        if len(phones) != 1:
            raise Reject("no contact: the claim writes no one phone for its side")
        own = {a.id for a in self.data.accounts.values() if a.device_id == phones[0]}
        owner = self._exact_owner(own) if own else None
        if owner is None:
            raise Reject("no contact: the phone's side is no one person code can name")
        people: set[str] = set()
        spans: list[tuple[int, int]] = []
        for pid, name in self.conn.execute("SELECT id, name FROM persons ORDER BY id"):
            if pid != owner and (found := _name_spans(bare, _nfc(name.strip()))):
                people.add(pid)
                spans += found
        numbers: set[str] = set()
        for m in _PHONE_RE.finditer(bare):
            if (d := phone_digits(m.group(0).strip(" .,-"))) is not None:
                numbers.add(d)
                spans.append(m.span())
        if joiner := self._absence_joiner(bare):
            # "never communicated with SMITH while REYES was abroad" (Codex on #169)
            raise Reject(f"no contact: the claim joins another clause ({joiner!r})")
        for start, end in spans:
            # "REYES's assistant" or "a friend of REYES" is not REYES (Codex on #169).
            if _NOT_A_PARTY_AFTER.match(bare, end) or _NOT_A_PARTY_BEFORE.search(bare[:start]):
                raise Reject(f"no contact: {bare[start:end]!r} may not be the other party")
        if len(people) + len(numbers) != 1 or _UNREAD_PARTY_RE.search(
            _PHONE_RE.sub(" ", bare) if numbers else bare
        ):
            raise Reject("no contact: the claim does not write exactly one other party")
        # "never called X" says nothing of messages, whatever channels the model gave: the
        # absence check would search both, so a call-only claim is not filled (Codex on #169).
        if _CALL_WORD_RE.search(bare):
            raise Reject("no contact by call: code reads no call-only scope")
        if _MESSAGE_WORD_RE.search(bare):
            raise Reject("no contact by message or by voice: code reads no one-kind scope")
        if _ONE_DIRECTION_RE.search(bare):
            # "never sent anything to REYES": the absence check reads both ways (Codex on #169)
            raise Reject("no contact one way: code reads no one-direction scope")
        named = self._named_apps(claim.text)
        if not named and _names_an_app_off_the_case(bare):
            # "never communicated by Signal" on a case with no Signal: the scope cannot be
            # kept, so code does not widen it to every app (Codex on #169).
            raise Reject("no contact: the claim names an app the case does not hold")
        if self._absence_leftover(bare, phones[0], spans):
            # "never communicated with REYES about narcotics": a topic, or any word beyond
            # plain contact, is a scope the absence check cannot keep (Codex on #169).
            raise Reject("no contact: the claim says more than plain contact code can check")
        if not params.get("channels"):
            # "never communicated by Signal with X" is no contact on Signal only: the scope
            # comes from the claim's own words (Codex on #169).
            if named:
                params["channels"] = named
            elif self._message_apps(claim.text) != []:
                # "texted" or "by SMS" may be SMS or iMessage, and a phone app may hold calls
                raise Reject("no contact by text: code reads no phone-message scope")
        params["device_ids"] = phones
        if people:
            params["person_ids"] = sorted({owner, *people})
            return phones
        (number,) = numbers
        sources = set(self.data.sources_for(phones))
        apps = {c.casefold() for c in params.get("channels", []) if c != CALL_CHANNEL}
        found = {
            a.id
            for a in self.data.accounts.values()
            if a.source_id in sources
            and (not apps or a.app.casefold() in apps)
            and _same_number(number, a)
        }
        if not found:
            raise Reject("no contact: the number is on no account on the phone")
        params["person_ids"] = [owner]
        params["account_ids"] = sorted(found)
        return phones

    def _names_a_recipient(self, bare: str) -> bool:
        """True when the words write a person the case knows, a phone number or a handle as
        the one the message went to: "REYES received ...", "a message to REYES". The phone
        itself ("the TARGET PHONE received") scopes the search and is no such party."""
        spans = [m.span() for m in _HANDLE_RE.finditer(bare)]
        spans += [
            m.span()
            for m in _PHONE_RE.finditer(bare)
            if phone_digits(m.group(0).strip(" .,-")) is not None
        ]
        for (name,) in self.conn.execute("SELECT name FROM persons"):
            if name and name.strip():
                spans += _name_spans(bare, _nfc(name.strip()))
        return any(
            _RECEIVED_AFTER_RE.match(bare, end) or _TO_BEFORE_RE.search(bare[:start])
            for start, end in spans
        )

    def _absence_leftover(self, bare: str, phone: str, spans: list[tuple[int, int]]) -> bool:
        """True when the claim writes any word beyond plain no-contact wording, once the
        phone's name, the party, the range's date and the case's app names are taken out."""
        cut = [*spans, *(m.span() for m in _DATE_RE.finditer(bare))]
        named = logged_names(self.conn)
        for did, sid, label in self.conn.execute(
            "SELECT id, source_id, label FROM devices WHERE id = ?", (phone,)
        ):
            for x in (did, sid, label, *named.get(did, [])):
                if x and name_key(x):
                    pat = r"(?<!\w)" + r"\s*".join(map(re.escape, name_key(x))) + r"(?!\w)"
                    cut += [m.span() for m in re.finditer(pat, bare, re.I)]
        kept = list(bare)
        for start, end in cut:
            kept[start:end] = " " * (end - start)
        apps = {w for app in self.channels() for w in re.findall(r"[a-z0-9]+", app.casefold())}
        words = re.findall(r"[^\W_]+", "".join(kept).casefold())
        return any(w not in _PLAIN_CONTACT_WORDS and w not in apps for w in words)

    @staticmethod
    def _absence_joiner(bare: str) -> str | None:
        """A word joining another clause to a no-contact claim, a name in which may not be
        the other party. "before", "after", "since", "until" and "prior to" right before the
        range's date are the range's own words, not a clause."""
        if ";" in bare:
            return ";"
        for m in _CLAUSE_JOINER_RE.finditer(bare):
            word = m.group(0).casefold()
            if word in ("before", "after", "since", "until") and _DATE_RE.match(
                bare[m.end() :].lstrip()
            ):
                continue
            return m.group(0)
        return None

    def _open_range(self, claim: Claim, device_ids: list[str], para: str = "") -> Any:
        """The range of "no contact before May 1, 2023", "after", "since" or "never", run to
        the extraction's own edge: its first or last dated message or call on the phone
        (validation ruling R5). The range's words say so. Only a claim with no time of day and
        at most one plain date; "first" or "last" contact is refused."""
        text = _unquoted(_nfc(claim.text))
        if any(_has_word(text, w) for w in ("first", "last", "earliest", "latest")):
            raise Reject("the claim's range for no contact is not a plain stated range")
        if len(device_ids) != 1 or time_mentions(text) or _NUM_DATE_RE.search(text):
            raise Reject("an open range needs one phone and no time of day")
        dates = list(_DATE_RE.finditer(text))
        sources = self.data.sources_for(device_ids)
        times = [
            t
            for (t,) in self.conn.execute(
                "SELECT ts_utc FROM messages WHERE source_id IN (SELECT value FROM json_each(?))"
                " AND ts_utc IS NOT NULL UNION ALL SELECT ts_utc FROM calls WHERE source_id IN"
                " (SELECT value FROM json_each(?)) AND ts_utc IS NOT NULL",
                (json.dumps(sources), json.dumps(sources)),
            )
        ]
        if not times:
            raise Reject("the phone holds no dated record to run an open range to")
        tz = self._phone_zone(device_ids)
        zone = ZoneInfo(tz)

        def instant(ts: str) -> datetime:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return t if t.tzinfo else t.replace(tzinfo=UTC)

        # From the first record to the last one, inclusive, so a full extraction spans it.
        # The edges stay instants: a wall time in a repeated hour would shift them by the
        # clock change (Codex on #169).
        first_utc = min(instant(t) for t in times).astimezone(UTC)
        last_utc = max(instant(t) for t in times).astimezone(UTC)
        first, last = first_utc.astimezone(zone), last_utc.astimezone(zone)
        span = f"the extraction's first dated record ({first:%B} {first.day}, {first.year})"
        end_span = f"its last dated record ({last:%B} {last.day}, {last.year})"

        def window(start: datetime | None, end: datetime | None, raw: str) -> TimeWindow:
            """A range from a local midnight (start) or to one (end, exclusive); a missing
            end is the extraction's own."""
            lo = start.replace(tzinfo=zone).astimezone(UTC) if start else first_utc
            hi = (
                end.replace(tzinfo=zone).astimezone(UTC) - timedelta(microseconds=1)
                if end
                else last_utc
            )
            if hi < lo:
                raise Reject("the extraction holds no record on the open side of the date")
            return TimeWindow(start_utc=lo, end_utc=hi, tz=tz, raw=raw + _EDGE_NOTE)

        if not dates:
            if not _has_word(text, "never"):
                raise Reject("an open range needs 'never' or one stated date")
            return window(None, None, f"never: from {span} to {end_span}")
        if len(dates) != 1 or dates[0].group(5):
            raise Reject("an open range reads one stated day")
        m = dates[0]
        # A date with no year takes the one year the claim and its paragraph state, as
        # check_window reads it (Codex on #169).
        years = {int(y) for y in _YEAR_RE.findall(claim.text + " " + para)}
        y = int(m.group(3) or m.group(6) or 0) or (next(iter(years)) if len(years) == 1 else 0)
        try:
            day = datetime.combine(date(y, _MONTHS[m.group(1).lower()], int(m.group(2))), time())
        except ValueError:
            raise Reject("the open range's date is not a date") from None
        head = text[max(0, m.start() - 16) : m.start()]
        said = text[m.start() : m.end()].strip(" ,")
        if re.search(r"\bon\s+or\s+before\s+$", head, re.IGNORECASE):
            # "on or before March 12" takes in all of March 12 (Codex on #169)
            return window(None, day + timedelta(days=1), f"on or before {said}: from {span}")
        if re.search(r"\b(?:before|prior\s+to|until)\s+$", head, re.IGNORECASE):
            return window(None, day, f"before {said}: from {span}")
        if re.search(r"\bon\s+or\s+after\s+$|\bsince\s+$", head, re.IGNORECASE):
            return window(day, None, f"since {said}: to {end_span}")
        if re.search(r"\bafter\s+$", head, re.IGNORECASE):
            return window(day + timedelta(days=1), None, f"after {said}: to {end_span}")
        raise Reject("the claim's date is not the open end of a range")

    def _count_calls(self, claim: Claim, params: dict[str, Any]) -> None:
        """Make a count of calls ("the TARGET PHONE had four Viber calls with (919) 888-7386")
        countable (validation fill f): 'call' and the claim's one app go in the channels, and
        when the model named no party code reads them as for a call's time (`_call_parties`).
        The phone the claim writes is the other side through its owner by confirmed
        stipulation, only when that person is exactly the phone's own accounts. Raises Reject
        otherwise."""
        channels = [c for c in params.get("channels", []) if c != CALL_CHANNEL]
        app = self._call_app(claim.text, channels)
        params["channels"] = sorted({CALL_CHANNEL, app}, key=str.lower)
        device_ids = list(params.get("device_ids", []))
        if not (params.get("person_ids") or params.get("account_ids") or params.get("handles")):
            people, accounts, phone = self._call_parties(claim, device_ids, app)
            if phone and not device_ids:
                device_ids = phone
                params["device_ids"] = phone
            if people:
                params["person_ids"] = people
            if accounts:
                params["account_ids"] = accounts
        sides = len(params.get("person_ids", [])) + bool(
            params.get("account_ids") or params.get("handles")
        )
        if sides == 1 and len(device_ids) == 1:
            own = {a.id for a in self.data.accounts.values() if a.device_id == device_ids[0]}
            owner = self._exact_owner(own) if own else None
            if owner is None or owner in params.get("person_ids", []):
                raise Reject("the phone's side of the calls is no one person code can name")
            params["person_ids"] = sorted({*params.get("person_ids", []), owner})

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
        return self._zoned_window(zone, start, end, device_ids, w.as_written.strip())

    def _zoned_window(
        self, zone: str | None, start: datetime, end: datetime, device_ids: list[str], raw: str
    ) -> Any:
        """The range in the zone `_read_zone` gives, with each end read as the one instant it
        is there. On the night the clocks go back, "1:59 a.m. EDT" in New York ends at 2:00
        a.m., which is EST: read as is, the minute would be 61 minutes (Codex on #150)."""
        tz = self._read_zone(zone, start, end, device_ids)
        fixed = WRITTEN_ZONES[" ".join(zone.split()).casefold()] if zone else None
        want = fixed if isinstance(fixed, timedelta) else None
        try:
            return local_window(_instant(start, tz, want), _instant(end, tz, want), tz, raw)
        except ValueError as e:
            raise Reject(str(e)) from None

    def _own_accounts(self, words: str, app: str, claim_text: str) -> set[str]:
        """The phone's own accounts on the app when the words name exactly one phone ("TARGET
        PHONE" written as a Kik account) and the claim names the app; else none. Accounts
        the phone records as its own are observed, not an identity link."""
        try:
            device = self._device(words)
        except Reject:
            return set()
        if namespace(app) == "tel" or not self._app_named(claim_text, app):
            return set()
        want = app.strip().casefold()
        return {
            a.id
            for a in self.data.accounts.values()
            if a.device_id == device and a.app.casefold() == want
        }

    def _exact_owner(self, own_ids: set[str]) -> str | None:
        """The one person a confirmed stipulation makes owner of the phone these accounts are
        on, when that person's accounts are exactly the phone's own (no other phone, no link
        to an account elsewhere); else None."""
        devices = {self.data.accounts[a].device_id for a in own_ids}
        if len(devices) != 1 or None in devices:
            return None
        (device,) = devices
        owners = {
            pid
            for _, did, pid, status in self.data.stipulations
            if did == device and status == "confirmed"
        }
        if len(owners) != 1:
            return None
        (owner,) = owners
        phone = {a.key for a in self.data.accounts.values() if a.device_id == device}
        return owner if person_party(self.data, owner).keys == phone else None

    def _person_named(self, words: str) -> str | None:
        """The one person the expert created whom these words name, or None."""
        try:
            return self._person(words)
        except Reject:
            return None

    def _accounts_named(
        self, acc: _Account, device_ids: list[str], claim_text: str, *, one: bool = True
    ) -> set[str]:
        """The accounts on the model's app whose display name is exactly these words, when
        the app is a phone app or one the claim names. With `one`, they must be one account:
        a name on several accounts raises Reject."""
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
        if one and len({a.key for a in hits}) > 1:
            # The claim may write which one, in brackets right after the name: 'to "ThisIs
            # DfirTwo" (live:.cid.5638f9306b7b8594)' (PAST-30 fill d). Only an exact identifier
            # of one of the named accounts picks it.
            flat = _nfc(claim_text)
            picked = [
                a
                for a in hits
                if re.search(
                    rf"{re.escape(written)}[\"”]?\s*\(\s*{re.escape(a.identifier.strip())}\s*\)",
                    flat,
                )
            ]
            if len({a.key for a in picked}) == 1:  # one account, on any phone (Codex on #169)
                return {a.id for a in picked}
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
            if want not in _offsets(t, tz).values():  # "1:30 a.m. EST" the night they go back
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


def _writes_a_number(text: str) -> bool:
    """True when the text, outside quoted words, writes a phone number `phone_digits` reads."""
    return any(
        phone_digits(m.group(0).strip(" .,-")) is not None
        for m in _PHONE_RE.finditer(_unquoted(_nfc(text)))
    )


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
    """The account's identifier is this phone number: written with its country code ("+") or
    in the North American form, a WhatsApp id ("12125550122@s.whatsapp.net"), or bare digits
    on a phone app or the phone's call log. A user id that happens to be digits is never one.
    Accounts on one app whose identifiers are the same number are one party (ruling R6)."""
    ident = acc.identifier.strip()
    jid = re.fullmatch(r"(\d{8,15})@s\.whatsapp\.net", ident)  # a WhatsApp id is the number
    if jid is not None:
        return jid.group(1) == number
    bare = re.fullmatch(r"1?(\d{10})", ident)
    if bare is not None and (namespace(acc.app) == "tel" or acc.app == NATIVE_CALL_APP):
        # A phone's call log may store the number bare ("9195677484", "18285205789"); a user id
        # on another app that happens to be ten digits is never one.
        return number == "1" + bare.group(1)
    # "+1 919-888-7386", or the North American form "(919) 888-7386": `phone_digits` reads
    # nothing else, so a run of digits with no "+" (a user id) is never a number here.
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
    opened = open_run(
        conn,
        "assumptions",
        template,
        model=model,
        schema=fill_schema((), ()),
        code_version=FILLER_VERSION,
    )
    filler = LocalAssumptionFiller(opened.port, conn, template=template, recorder=opened.recorder)
    filler.model_runs = (opened.run,)
    return filler
