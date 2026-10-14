"""Baker's own wording for generated stance items. SYNTHETIC; mechanics only, like chat.py.

Baker's stance step reads `Assumption.text`, rendered by the product's fixed templates
(core/audit/assumptions.py), and each record as its database stores it: a message body, a call
or contact row rendered by core/audit/invariants.record_text, or an attachment's file name. The
small model reads them through eval/stancemodel's adapter, which turns core/audit/context lines
into item lines. These helpers write the same strings, so a generated item in Baker's wording
matches what the adapter builds from a real case database; tests/test_bakerform.py checks each
format against core on a database built from core/schema.sql.

Ids follow the product: phone `dev:item1` (source `item1`), account `acct:item1:Telegram:5550147`
(the same app and identifier on another phone is the same account), the stipulated owner of a
phone `person:dev:item1:owner`, and a person the document names `person:<surname>`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from core.audit.assumptions import TEMPLATES, local_window, parse_params
from core.contracts import TimeWindow

# Apps as Cellebrite reports spell them; calls and contact rows use "Phone".
APPS = ("SMS", "WhatsApp", "Telegram", "Signal", "Instagram", "Phone")

CONTACT_SENDER = "contact list"
CONTACT_TIME = "no time in source"

# Zone abbreviations a line can carry, and the zone each one reads in. America/Phoenix is left
# out on purpose: its MST is also Denver's winter abbreviation.
ZONE_OF = {
    "EST": "America/New_York",
    "EDT": "America/New_York",
    "CST": "America/Chicago",
    "CDT": "America/Chicago",
    "MST": "America/Denver",
    "MDT": "America/Denver",
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
}
ZONES = tuple(dict.fromkeys(ZONE_OF.values()))


def source_id(item: int) -> str:
    return f"item{item}"


def device_id(item: int) -> str:
    return f"dev:item{item}"


def account_id(item: int, app: str, identifier: str) -> str:
    if app not in APPS:
        raise ValueError(f"unknown app {app!r}")
    if not identifier or " " in identifier:
        raise ValueError(f"bad identifier {identifier!r}")
    return f"acct:item{item}:{app}:{identifier}"


def owner_person(item: int) -> str:
    """The person an expert stipulated as phone item<n>'s owner, as Baker names them."""
    return f"person:dev:item{item}:owner"


def named_person(slug: str) -> str:
    """A person the document names and no expert has tied to an account, e.g. person:vance."""
    if not slug.replace("_", "").isalnum() or slug != slug.lower():
        raise ValueError(f"bad person slug {slug!r}")
    return f"person:{slug}"


def window(start: datetime, end_exclusive: datetime, tz: str, raw: str) -> TimeWindow:
    """The template window for local wall-clock [start, end_exclusive) in tz; raw is the
    document's own words, which is all the assumption text shows of it."""
    return local_window(start, end_exclusive, tz, raw)


def assumption_text(template_id: str, **params: Any) -> str:
    """The product's own rendering. Parameters a template does not accept raise ValueError,
    exactly as the product's builder refuses them."""
    return TEMPLATES[template_id].render(parse_params(template_id, params))


def sender_line(
    app: str,
    identifier: str,
    *,
    owner: bool = False,
    persons: Iterable[str] = (),
    shown_as: str | None = None,
) -> str:
    """'<App> <identifier>', the source's sender text if it kept one, '(owner)' for the record's
    own phone's account, then the person ids Baker holds as confirmed for the account in
    brackets: 'Telegram 5550147 (owner) [person:dev:item1:owner]'."""
    if app not in APPS:
        raise ValueError(f"unknown app {app!r}")
    out = f"{app} {identifier}"
    if shown_as:
        out += f" {shown_as}"
    if owner:
        out += " (owner)"
    ids = sorted(set(persons))
    if ids:
        out += f" [{', '.join(ids)}]"
    return out


def contact_text(name: str | None, identifier: str) -> str:
    """A contact row as core.audit.invariants.record_text cites it: '<name> <identifier>'."""
    return f"{name or ''} {identifier}".strip()


def call_text(
    direction: str, frm: str | None, to: str | None, ts_raw: str | None, duration_s: int | None
) -> str:
    """A call as core.audit.invariants.record_text cites it."""
    return f"{direction} call from {frm or '?'} to {to or '?'} at {ts_raw or '?'}, {duration_s}s"


def report_time(utc: datetime, offset_min: int = 0) -> str:
    """The time as a Cellebrite report prints it: '3/9/2026 11:58:02 PM(UTC+0)' for a report in
    UTC, '3/9/2026 7:58:02 PM(UTC-4)' for one in the phone's local offset."""
    local = utc.astimezone(UTC) + timedelta(minutes=offset_min)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    h, m = divmod(abs(offset_min), 60)
    sign = "+" if offset_min >= 0 else "-"
    zone = f"UTC{sign}{h}" + (f":{m:02d}" if m else "")
    return (
        f"{local.month}/{local.day}/{local.year} {hour}:{local.minute:02d}:"
        f"{local.second:02d} {ampm}({zone})"
    )
