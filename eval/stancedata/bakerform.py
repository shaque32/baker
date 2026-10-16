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

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from core.audit.assumptions import TEMPLATES, local_window, parse_params
from core.audit.quotes import verify_quote
from core.contracts import TimeWindow
from eval.probe_draft.model import ProbeLine
from eval.stancedata.chat import local_str
from eval.stancedata.families import family
from eval.stancedata.model import GenItem, generated_label
from eval.stancedata.names import bracketed, case_names, readable_sender

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
    brackets: 'Telegram 5550147 (owner) [person:dev:item1:owner]'. build_baker_item prints
    them by name, as core.audit.readable does: '[Daniel Petrov (the user of item1)]'."""
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


# ---------------------------------------------------------------- lines and items


@dataclass(frozen=True)
class Line:
    """One excerpt line as the small model's adapter builds it from Baker's database."""

    sender: str
    account_id: str  # the account behind the line; a contact row's number as a Phone account
    local_time: str
    text: str
    utc: datetime | None = None  # None only for a contact row, which has no time
    kind: str = "message"  # a message or an attachment; "call" or "contact" for those rows
    recipients: tuple[str, ...] = ()  # a message's listed recipients, printed as senders are


def message_line(
    item: int,
    app: str,
    identifier: str,
    utc: datetime,
    tz: str,
    text: str,
    *,
    owner: bool = False,
    persons: Iterable[str] = (),
    recipients: Iterable[str] = (),
) -> Line:
    """A message (or an attachment's file name, as its text) on phone item<n>. recipients are
    the accounts the source lists as its recipients, each as sender_line prints it."""
    return Line(
        sender_line(app, identifier, owner=owner, persons=persons),
        account_id(item, app, identifier),
        local_str(utc, tz),
        text,
        utc,
        recipients=tuple(recipients),
    )


def call_line(
    item: int,
    utc: datetime,
    tz: str,
    direction: str,
    frm: str,
    to: str,
    duration_s: int,
    *,
    owner: bool = False,
    persons: Iterable[str] = (),
    report_offset_min: int = 0,
) -> Line:
    """A call on phone item<n>: its line shows the calling number's account, as Baker's context
    does, and its text is the record text with the time as the report printed it."""
    if direction not in ("incoming", "outgoing", "missed"):
        raise ValueError(f"bad call direction {direction!r}")
    return Line(
        sender_line("Phone", frm, owner=owner, persons=persons),
        account_id(item, "Phone", frm),
        local_str(utc, tz),
        call_text(direction, frm, to, report_time(utc, report_offset_min), duration_s),
        utc,
        "call",
    )


def contact_line(item: int, name: str | None, number: str) -> Line:
    """A contact row on phone item<n>. It is shown alone: Baker gives it no context."""
    return Line(CONTACT_SENDER, account_id(item, "Phone", number), CONTACT_TIME,
                contact_text(name, number), kind="contact")  # fmt: skip


def build_baker_item(
    *,
    probe_id: str,
    family_id: str,
    source: str,
    generator: str,
    lang: str,
    template_id: str,
    params: dict[str, Any],
    lines: Sequence[Line],
    target: int,
    quote: str,
    rationale: str,
    device: str,
    group: str | None = None,
    disputed: str | None = None,
    labeled_by: str | None = None,
    claim: str | None = None,
    names: Mapping[str, str] | None = None,
    captioned: bool = False,
) -> GenItem:
    """Assemble and check one item in Baker's own wording. The assumption is the product's
    rendering of (template_id, params); the label comes from the family, as for plain items.

    lines are the excerpt in time order with the record at `target`; device is the phone the
    record came from ('dev:item3'); claim is the claim's text, shown only with the meaning, role
    and event templates. names gives a name to every person the parameters or a line's
    brackets name ('person:dev:item1:owner' -> 'Daniel Petrov'): the assumption and the sender
    lines then read as core.audit.readable prints them for a case where an expert stipulated
    each phone owner and the document named everyone else.

    captioned says the record is an attachment whose message has a caption: the line before it
    is that message, with the same sender and time and the caption as its text, as the small
    model's adapter shows it (eval/stancemodel/time_case01.case_item).

    A message or attachment record's excerpt is its own chat, as Baker's context is, and the
    item carries the chat's members for the line the context opens with
    (core.audit.readable.members_line): every account that sent a line or that a line lists as
    a recipient, as Baker takes the chat's senders and listed recipients. A call or a contact
    row has no chat and carries none.
    """
    if not 0 <= target < len(lines):
        raise ValueError(f"{probe_id}: target {target} outside {len(lines)} lines")
    timed = [ln.utc for ln in lines if ln.utc is not None]
    if len(timed) != len(lines) and len(lines) != 1:
        raise ValueError(f"{probe_id}: a line without a time (a contact row) stands alone")
    tie = -1  # the one pair of lines that may share a time: a caption and its attachment
    if captioned:
        cap, rec = lines[target - 1] if target else None, lines[target]
        if cap is None or rec.kind != "message" or not cap.text.strip() or (
            (cap.sender, cap.account_id, cap.utc, cap.kind) != (rec.sender, rec.account_id,
                                                                rec.utc, rec.kind)
        ):  # fmt: skip
            raise ValueError(f"{probe_id}: a caption is its attachment's message, just before it")
        tie = target - 1
    if any(b <= a and i != tie for i, (a, b) in enumerate(zip(timed, timed[1:], strict=False))):
        raise ValueError(f"{probe_id}: lines must be in strictly increasing UTC order")
    if quote.strip() != quote or not verify_quote(quote, lines[target].text):
        raise ValueError(f"{probe_id}: quote is not a word-aligned verbatim part of the record")
    chat = lines[target].kind == "message"
    if chat and any(ln.kind != "message" for ln in lines):
        raise ValueError(f"{probe_id}: a message's excerpt holds only its own chat's messages")
    parsed = parse_params(template_id, params)
    template = TEMPLATES[template_id]
    f = family(family_id)
    shown = {ln.sender for ln in lines}  # every account the item prints
    if chat:  # with the accounts the chat's messages list as recipients, for its members line
        shown |= {r for ln in lines for r in ln.recipients}
    readable = None
    kept: dict[str, str] | None = None
    if names is not None:
        involved = {*parsed.person_ids, *(pid for s in shown for pid in bracketed(s))}
        missing = sorted(pid for pid in involved if not names.get(pid, "").strip())
        if missing:
            raise ValueError(f"{probe_id}: no name for {', '.join(missing)}")
        kept = {pid: names[pid] for pid in sorted(involved)}
        readable = case_names(kept, parsed.account_ids)
    printed = {x: x if readable is None else readable_sender(x, readable) for x in shown}
    probe_lines = [
        ProbeLine(
            sender=printed[ln.sender],
            account_id=ln.account_id,
            local_time=ln.local_time,
            text=ln.text,
        )
        for ln in lines
    ]
    members = tuple(sorted(set(printed.values()))) if chat else None
    return GenItem(
        probe_id=probe_id,
        category=f.category,
        trap=f.trap,
        lang=lang,
        assumption_kind=template.kind,
        assumption=template.render(parsed, readable),
        target=probe_lines[target],
        context=tuple(x for i, x in enumerate(probe_lines) if i != target),
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
        device_id=device,
        baker_template=template_id,
        baker_params=parsed.model_dump(mode="json", exclude_defaults=True),
        baker_claim=claim,
        baker_names=kept,
        baker_members=members,
    )
