"""The small synthetic phone every layout variant renders. Everything here is invented.

Each variant writes these same records in a different report layout. What an importer must get
back is fixed here, so a variant either reproduces these records exactly or the coverage record
says what it could not read.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta

DEVICE_OFFSET = -240  # the phone shows UTC-4 in the report


@dataclass(frozen=True)
class Who:
    ident: str
    name: str | None = None
    owner: bool = False

    def cell(self) -> str:
        """Party cell as a report prints it: '<identifier> <name>' or '... (owner)'."""
        if self.owner:
            return f"{self.ident} (owner)"
        return f"{self.ident} {self.name}" if self.name else self.ident


OWNER = Who("+15550100001", "Riley", owner=True)
OWNER_TG = Who("@riley_k", "Riley", owner=True)
JO = Who("+15550100002", "Jo")
SAM = Who("+15550100003", "Sam")
KAI = Who("@kai_m", "Kai")
PAT = Who("+15550100009", "Pat")


@dataclass(frozen=True)
class Chat:
    key: str  # Chat # in the report
    name: str | None
    app: str
    members: tuple[Who, ...]


@dataclass(frozen=True)
class Msg:
    key: str
    chat: str | None  # Chat key; None for SMS
    sender: Who
    to: tuple[Who, ...]
    body: str
    utc: datetime
    attachments: tuple[str, ...] = ()

    @property
    def outgoing(self) -> bool:
        return self.sender.owner


@dataclass(frozen=True)
class Call:
    key: str
    app: str
    direction: str  # Incoming, Outgoing, Missed
    party: Who
    utc: datetime
    duration_s: int


@dataclass(frozen=True)
class Contact:
    name: str
    entries: tuple[str, ...]


def t(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, second, tzinfo=UTC)


CHATS: tuple[Chat, ...] = (
    Chat("g1", "Weekend plan", "WhatsApp", (OWNER, JO, SAM)),
    Chat("t1", None, "Telegram", (OWNER_TG, KAI)),
)

MESSAGES: tuple[Msg, ...] = (
    Msg("m01", "g1", JO, (OWNER, SAM), "Are we still on for Saturday?", t(13, 22, 5)),
    Msg("m02", "g1", OWNER, (JO, SAM), "Yes, meet at the north gate at 10.", t(13, 22, 7, 30)),
    Msg("m03", "g1", SAM, (OWNER, JO), "I can bring the cooler.", t(14, 1, 15)),
    Msg("m04", "g1", JO, (OWNER, SAM), "Photo of the trail map", t(14, 13, 40), ("map.jpg",)),
    Msg("m05", "t1", KAI, (OWNER_TG,), "Did the package arrive?", t(15, 9, 0)),
    Msg("m06", "t1", OWNER_TG, (KAI,), "Not yet. Tracking says Monday.", t(15, 9, 3)),
    Msg("m07", "t1", KAI, (OWNER_TG,), "ok thanks", t(16, 23, 59, 59)),
    Msg("m08", None, PAT, (OWNER,), "Running ten minutes late", t(16, 14, 2)),
    Msg("m09", None, OWNER, (PAT,), "No problem, see you soon", t(16, 14, 4)),
)

CALLS: tuple[Call, ...] = (
    Call("c1", "Phone", "Outgoing", JO, t(13, 21, 50), 125),
    Call("c2", "Phone", "Incoming", SAM, t(14, 2, 0), 42),
    Call("c3", "WhatsApp", "Missed", JO, t(15, 18, 30), 0),
    Call("c4", "Phone", "Incoming", PAT, t(16, 13, 58), 61),
)

CONTACTS: tuple[Contact, ...] = (
    Contact("Jo", ("Phone-Mobile: +15550100002",)),
    Contact("Sam Work", ("Phone-Work: +15550100003", "Email: sam@example.invalid")),
    Contact("Pat", ("Phone-Mobile: +15550100009",)),
)

ACCOUNTS: tuple[tuple[str, str, str], ...] = (
    ("WhatsApp", "+15550100001", "Riley"),
    ("Telegram", "@riley_k", "Riley"),
)


@dataclass(frozen=True)
class Phone:
    """One synthetic phone: the records a report of it holds."""

    chats: tuple[Chat, ...] = CHATS
    messages: tuple[Msg, ...] = MESSAGES
    calls: tuple[Call, ...] = CALLS
    contacts: tuple[Contact, ...] = CONTACTS
    accounts: tuple[tuple[str, str, str], ...] = ACCOUNTS
    extra: dict[str, object] = field(default_factory=dict)

    def chat(self, key: str | None) -> Chat | None:
        return next((c for c in self.chats if c.key == key), None)

    def shifted(self, delta: timedelta) -> Phone:
        """The same phone with every time moved by `delta` (to change which dates appear)."""
        return replace(
            self,
            messages=tuple(replace(m, utc=m.utc + delta) for m in self.messages),
            calls=tuple(replace(c, utc=c.utc + delta) for c in self.calls),
        )


PHONE = Phone()


# ---------------------------------------------------------------- time formats


def local(utc: datetime, offset_min: int) -> datetime:
    return (utc + timedelta(minutes=offset_min)).replace(tzinfo=None)


def utc_suffix(offset_min: int, style: str = "short") -> str:
    """'(UTC-4)' (short), '(UTC-04:00)' (long), 'GMT-4' (gmt), '-0400' (bare), 'Z' (z)."""
    sign = "-" if offset_min < 0 else "+"
    h, m = divmod(abs(offset_min), 60)
    if style == "short":
        return f"(UTC{sign}{h}" + (f":{m:02d}" if m else "") + ")"
    if style == "long":
        return f"(UTC{sign}{h:02d}:{m:02d})"
    if style == "gmt":
        return f"GMT{sign}{h}" + (f":{m:02d}" if m else "")
    if style == "bare":
        return f"{sign}{h:02d}{m:02d}"
    if style == "z":
        assert offset_min == 0  # noqa: S101 - synthetic data only
        return "Z"
    raise ValueError(style)


def us12(utc: datetime, offset_min: int, suffix: str | None = "short") -> str:
    """'3/13/2026 6:05:00 PM(UTC-4)', the layout of the case01 reports."""
    d = local(utc, offset_min)
    h12 = d.hour % 12 or 12
    ampm = "AM" if d.hour < 12 else "PM"
    s = f"{d.month}/{d.day}/{d.year} {h12}:{d.minute:02d}:{d.second:02d} {ampm}"
    return s + (utc_suffix(offset_min, suffix) if suffix else "")


def dmy24(utc: datetime, offset_min: int, suffix: str | None = "long", sep: str = "/") -> str:
    """'13/03/2026 18:05:00(UTC-04:00)'."""
    d = local(utc, offset_min)
    s = f"{d.day:02d}{sep}{d.month:02d}{sep}{d.year} {d.hour:02d}:{d.minute:02d}:{d.second:02d}"
    return s + (utc_suffix(offset_min, suffix) if suffix else "")


def iso(utc: datetime, offset_min: int) -> str:
    d = local(utc, offset_min)
    sign = "-" if offset_min < 0 else "+"
    h, m = divmod(abs(offset_min), 60)
    return d.isoformat() + (f"{sign}{h:02d}:{m:02d}" if offset_min else "Z")


def month_name(utc: datetime, offset_min: int) -> str:
    """'13-Mar-2026 18:05:00 GMT-4'."""
    d = local(utc, offset_min)
    return d.strftime("%d-%b-%Y %H:%M:%S") + " " + utc_suffix(offset_min, "gmt")


def long_month(utc: datetime, offset_min: int) -> str:
    """'Fri, Mar 13, 2026 6:05:00 PM (UTC-04:00)'."""
    d = local(utc, offset_min)
    h12 = d.hour % 12 or 12
    ampm = "AM" if d.hour < 12 else "PM"
    return (
        f"{d.strftime('%a')}, {d.strftime('%b')} {d.day}, {d.year} "
        f"{h12}:{d.minute:02d}:{d.second:02d} {ampm} {utc_suffix(offset_min, 'long')}"
    )


def hms(seconds: int) -> str:
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def many(n: int, body_words: int = 6) -> Phone:
    """A phone whose WhatsApp group holds `n` messages, seven minutes apart from 13 March.
    For page-break and size variants."""
    words = ("north", "gate", "cooler", "trail", "map", "ten", "Saturday", "bring", "late", "ok")
    msgs = []
    for i in range(n):
        sender = (JO, OWNER, SAM)[i % 3]
        to = tuple(w for w in (OWNER, JO, SAM) if w != sender)
        body = " ".join(words[(i + k) % len(words)] for k in range(body_words)) + f" #{i + 1}"
        msgs.append(
            Msg(f"n{i + 1:06d}", "g1", sender, to, body, t(13, 0, 0) + timedelta(minutes=7 * i))
        )
    return replace(PHONE, messages=tuple(msgs))
