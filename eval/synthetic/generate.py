"""Generate synthetic case01: Cellebrite-style Excel reports, the expected canonical database,
the mock affidavit and the DRAFT answer key. SYNTHETIC data only; deterministic for a seed.

Usage: python -m eval.synthetic.generate [--out eval/synthetic/case01] [--db <path>]

Outputs in --out:
  item1.xlsx, item2.xlsx   one Cellebrite-style report per phone (what the importer reads)
  case.json                metadata, devices, source hashes, planted traps, ground truth
  affidavit_draft.md       mock government affidavit, numbered paragraphs, for Arsh's review
  draft_gold.jsonl         DRAFT answer key in GoldClaim format, not gold until Arsh signs off
  ANSWER_KEY_DRAFT.md      the same key with reasoning and the cited rows, for line-by-line review

--db writes the canonical rows a correct importer should produce from the two reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.contracts import GoldClaim
from core.db import apply_schema, connect
from eval.synthetic import case01_key as key
from eval.synthetic import case01_story as story
from eval.synthetic.filler import make_filler
from eval.synthetic.xlsx import write_xlsx

GENERATOR_VERSION = "case01-gen 0.1.0"
TOOL_NAME = "baker-synth (Cellebrite-style layout)"
SEED = 20260306
DEFAULT_OUT = Path("eval/synthetic/case01")
IMPORTED_AT = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)  # fixed so the expected DB is stable
DRAFT_LABELED_AT = datetime(2026, 10, 6, tzinfo=UTC)
TITLE_ROWS = 2  # row 1 = sheet title, row 2 = column headers; data starts on row 3

# Layout agreed with the Cellebrite report import thread (header names, not positions, matter).
CHAT_COLUMNS = [
    "#",
    "Chat #",
    "Name",
    "Source",
    "Identifier",
    "Participants",
    "From",
    "To",
    "Body",
    "Timestamp",
    "Direction",
    "Deleted",
    "Attachment #1",
    "Tag",
]
CALL_COLUMNS = ["#", "Source", "Type", "Timestamp", "Duration", "From", "To", "Deleted"]
CONTACT_COLUMNS = ["#", "Name", "Entries", "Source", "Deleted"]
ACCOUNT_COLUMNS = ["#", "Source", "Username", "Name"]

# Filler rows the report marks deleted (a few SMS with Ilya on item1, none in WhatsApp).
DELETED_FILLER = {"f:item1:ilya_sms:0007", "f:item1:ilya_sms:0042", "f:item1:ilya_sms:0113"}


# ---------------------------------------------------------------- formatting


def fmt_ts(utc: datetime, offset_min: int) -> str:
    """Cellebrite-style display time, e.g. '3/14/2026 9:50:20 PM(UTC-4)'."""
    local = utc + timedelta(minutes=offset_min)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    h, m = divmod(abs(offset_min), 60)
    sign = "+" if offset_min >= 0 else "-"
    tz = f"UTC{sign}{h}" + (f":{m:02d}" if m else "")
    return (
        f"{local.month}/{local.day}/{local.year} {hour}:{local.minute:02d}:"
        f"{local.second:02d} {ampm}({tz})"
    )


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_duration(s: int) -> str:
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def phone_of(identifier: str) -> str | None:
    if identifier.startswith("+"):
        return identifier
    if identifier.endswith("@s.whatsapp.net"):
        return "+" + identifier.split("@")[0]
    return None


# ---------------------------------------------------------------- rendering


@dataclass
class Rendered:
    """Everything derived for one device: report sheets plus canonical rows."""

    device: story.Device
    sheets: list[tuple[str, list[list[str | int | None]]]] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)
    threads: list[dict] = field(default_factory=list)
    accounts: dict[tuple[str, str], dict] = field(default_factory=dict)
    attachments: list[dict] = field(default_factory=list)
    device_row: int = 0
    keys: dict[str, list[str]] = field(default_factory=dict)  # story key -> record ids


def _offset(dev: story.Device, utc: datetime) -> int:
    return 0 if dev.report_tz == "utc" else story.eastern_offset_min(utc)


def _contact_name(dev: story.Device, identifier: str) -> str | None:
    phone = phone_of(identifier)
    for name, entries in dev.contacts:
        for _, value in entries:
            if value == identifier or (phone and value == phone):
                return name
    return None


def _name(dev: story.Device, acct: story.Acct, at: datetime) -> str | None:
    if acct.app == "Telegram":
        return acct.name_at(at)
    return _contact_name(dev, acct.identifier)


def _display(dev: story.Device, acct: story.Acct, at: datetime) -> str:
    if acct.key in dev.owner_accounts:
        return f"{acct.identifier} (owner)"
    name = _name(dev, acct, at)
    return f"{acct.identifier} {name}" if name else acct.identifier


def _account(
    r: Rendered, app: str, acct: story.Acct, locator: str, at: datetime, display: str | None = None
) -> str:
    """First sighting wins: locator and display name come from the first row naming the account."""
    k = (app, acct.identifier)
    if k not in r.accounts:
        if display is None and acct.key not in r.device.owner_accounts:
            display = _name(r.device, acct, at)
        r.accounts[k] = {
            "id": f"acct:{r.device.key}:{app}:{acct.identifier}",
            "locator": locator,
            "app": app,
            "identifier": acct.identifier,
            "display_name": display,
            "owned": acct.key in r.device.owner_accounts,
        }
    return r.accounts[k]["id"]


def render_device(dev: story.Device, msgs: list[story.Msg], calls: list[story.Call]) -> Rendered:
    r = Rendered(dev)
    acc = story.ACCOUNTS
    src = dev.key
    owned = set(dev.owner_accounts)

    # ---- Summary: key in column A, value in column B
    info: list[list[str | int | None]] = [
        ["Summary (SYNTHETIC: all data fictional, generated by eval/synthetic)"],
        ["Case number", "SYN-2026-0001"],
        ["Evidence number", dev.evidence_no],
        ["Device", dev.model],
        ["OS version", dev.os_version],
        ["Extraction type", dev.extraction_label],
        ["Extraction start date/time", fmt_ts(dev.extracted_at, _offset(dev, dev.extracted_at))],
        # The report's display setting. Not the phone's zone (trap: timezone).
        ["Time zone", "UTC+0" if dev.report_tz == "utc" else "Device local (offset shown per row)"],
        ["Device time zone", story.DEVICE_TZ],
        ["Report version", f"baker-synth {GENERATOR_VERSION} (Cellebrite-style layout)"],
        ["Tool", TOOL_NAME],
        ["Tool version", GENERATOR_VERSION],
    ]
    r.device_row = 4
    r.sheets.append(("Summary", info))

    # ---- User Accounts: the phone's own accounts
    acct_rows: list[list[str | int | None]] = [["User Accounts"], ACCOUNT_COLUMNS]
    for i, k in enumerate(dev.owner_accounts, start=1):
        a = acc[k]
        name = a.name_at(dev.extracted_at) if a.app == "Telegram" else None
        acct_rows.append([i, a.app, a.identifier, name or ""])
        _account(r, a.app, a, f"User Accounts!{TITLE_ROWS + i}", dev.extracted_at, name)
    r.sheets.append(("User Accounts", acct_rows))

    # ---- Contacts
    contact_rows: list[list[str | int | None]] = [["Contacts"], CONTACT_COLUMNS]
    for i, (name, entries) in enumerate(dev.contacts, start=1):
        row = TITLE_ROWS + i
        entry_text = "\n".join(f"{label}: {value}" for label, value in entries)
        source = "Telegram" if all(lbl.endswith("Telegram") for lbl, _ in entries) else "Phone"
        contact_rows.append([i, name, entry_text, source, "Intact"])
        ids = []
        for j, (_, value) in enumerate(entries, start=1):
            cid = f"contact:{src}:Contacts!{row}#{j}"
            r.contacts.append(
                {"id": cid, "locator": f"Contacts!{row}", "name": name, "identifier": value}
            )
            ids.append(cid)
        r.keys[f"contact:{name}"] = ids
    r.sheets.append(("Contacts", contact_rows))

    # ---- Chats: group by thread (app + other party), threads ordered by first message
    mine = [m for m in msgs if m.sender in owned or m.to in owned]
    threads: dict[tuple[str, str], list[story.Msg]] = {}
    for m in mine:
        other = m.to if m.sender in owned else m.sender
        threads.setdefault((acc[m.sender].app, other), []).append(m)
    ordered = sorted(threads.items(), key=lambda kv: (min(x.at for x in kv[1]), kv[0]))

    chat_rows: list[list[str | int | None]] = [["Chats"], CHAT_COLUMNS]
    n = 0
    for chat_no, ((app, other_key), tmsgs) in enumerate(ordered, start=1):
        other = acc[other_key]
        owner_key = next(x.sender if x.sender in owned else x.to for x in tmsgs)
        owner = acc[owner_key]
        participants = (
            f"{_display(dev, owner, dev.extracted_at)}\n{_display(dev, other, dev.extracted_at)}"
        )
        chat_name = _name(dev, other, dev.extracted_at) or other.identifier
        first_row = TITLE_ROWS + n + 1
        thread_id = f"thr:{src}:{app}:{chat_no}"
        r.threads.append(
            {"id": thread_id, "locator": f"Chats!{first_row}", "app": app, "title": chat_name}
        )
        for m in sorted(tmsgs, key=lambda x: (x.at, x.key)):
            n += 1
            row = TITLE_ROWS + n
            loc = f"Chats!{row}"
            offset = _offset(dev, m.at)
            raw = fmt_ts(m.at, offset)
            outgoing = m.sender in owned
            deleted = m.key in DELETED_FILLER
            sender, to = acc[m.sender], acc[m.to]
            from_cell, to_cell = _display(dev, sender, m.at), _display(dev, to, m.at)
            chat_rows.append(
                [
                    n,
                    chat_no,
                    chat_name,
                    app,
                    other.identifier,
                    participants,
                    from_cell,
                    to_cell,
                    m.body,
                    raw,
                    "Outgoing" if outgoing else "Incoming",
                    "Deleted" if deleted else "Intact",
                    m.attachment or "",
                    m.tag or "",
                ]
            )
            mid = f"msg:{src}:{loc}"
            r.messages.append(
                {
                    "id": mid,
                    "locator": loc,
                    "thread_id": thread_id,
                    "sender_account_id": _account(r, app, sender, loc, m.at),
                    "recipient_account_id": _account(r, app, to, loc, m.at),
                    "from_cell": from_cell,
                    "to_cell": to_cell,
                    "direction": "outgoing" if outgoing else "incoming",
                    "ts_utc": iso(m.at),
                    "ts_offset_min": offset,
                    "ts_raw": raw,
                    "body": m.body,
                    "lang": m.lang,  # truth for tests; the importer stores NULL
                    "deleted_flag": int(deleted),
                    "tag": m.tag,  # examiner tag shown in the report
                    "app": app,
                    "key": m.key,
                }
            )
            if m.attachment:
                r.attachments.append(
                    {
                        "id": f"att:{src}:{loc}:1",
                        "locator": loc,
                        "message_id": mid,
                        "file_name": m.attachment,
                        "mime_type": None,  # not in the report
                        "sha256": None,
                    }
                )
            r.keys.setdefault(m.key, []).append(mid)
            if m.attachment:
                r.keys[f"att:{m.key}"] = [f"att:{src}:{loc}:1"]
    r.sheets.append(("Chats", chat_rows))

    # ---- Call Log
    call_rows: list[list[str | int | None]] = [["Call Log"], CALL_COLUMNS]
    mine_calls = sorted(
        (c for c in calls if c.caller in owned or c.callee in owned), key=lambda c: (c.at, c.key)
    )
    for i, c in enumerate(mine_calls, start=1):
        row = TITLE_ROWS + i
        loc = f"Call Log!{row}"
        offset = _offset(dev, c.at)
        raw = fmt_ts(c.at, offset)
        if c.caller in owned:
            direction = "outgoing"
        else:
            direction = "incoming" if c.answered else "missed"
        caller, callee = acc[c.caller], acc[c.callee]
        from_cell, to_cell = _display(dev, caller, c.at), _display(dev, callee, c.at)
        call_rows.append(
            [
                i,
                "Phone",
                direction.capitalize(),
                raw,
                fmt_duration(c.duration_s),
                from_cell,
                to_cell,
                "Intact",
            ]
        )
        cid = f"call:{src}:{loc}"
        r.calls.append(
            {
                "id": cid,
                "locator": loc,
                "app": "Phone",
                "from_account_id": _account(r, "Phone", caller, loc, c.at),
                "to_account_id": _account(r, "Phone", callee, loc, c.at),
                "from_cell": from_cell,
                "to_cell": to_cell,
                "direction": direction,
                "ts_utc": iso(c.at),
                "ts_offset_min": offset,
                "ts_raw": raw,
                "duration_s": c.duration_s,
                "deleted_flag": 0,
                "key": c.key,
            }
        )
        r.keys.setdefault(c.key, []).append(cid)
    r.sheets.append(("Call Log", call_rows))
    return r


def build(seed: int = SEED) -> list[Rendered]:
    apps = {k: a.app for k, a in story.ACCOUNTS.items()}
    filler_msgs, filler_calls = make_filler(seed, apps)
    msgs = list(story.SCRIPTED_MESSAGES) + filler_msgs
    calls = list(story.SCRIPTED_CALLS) + filler_calls
    return [render_device(d, msgs, calls) for d in story.DEVICES]


# ---------------------------------------------------------------- canonical database


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_db(conn: sqlite3.Connection, rendered: list[Rendered], out: Path) -> None:
    """Write the rows a correct importer should produce from the two reports."""
    apply_schema(conn)
    for r in rendered:
        d, src = r.device, r.device.key
        conn.execute(
            "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                src,
                "cellebrite_excel",
                "curated_report",  # examiner-built report; cannot support absence claims
                d.extraction_type,
                f"{src}.xlsx",
                sha256_file(out / f"{src}.xlsx"),
                TOOL_NAME,
                GENERATOR_VERSION,
                iso(d.extracted_at),
                iso(IMPORTED_AT),
            ),
        )
        conn.execute(
            "INSERT INTO devices VALUES (?,?,?,?,?,?,?)",
            (
                f"dev:{src}",
                src,
                f"Summary!{r.device_row}",
                d.model,  # the report's Device field; who it was seized from is not in the report
                d.model,
                d.os_version,
                story.DEVICE_TZ,
            ),
        )
        dev_id = f"dev:{src}"
        for a in r.accounts.values():
            conn.execute(
                "INSERT INTO accounts VALUES (?,?,?,?,?,?,?)",
                (
                    a["id"],
                    src,
                    a["locator"],
                    dev_id if a["owned"] else None,  # only the phone's own accounts
                    a["app"],
                    a["identifier"],
                    a["display_name"],
                ),
            )
        for t in r.threads:
            conn.execute(
                "INSERT INTO threads VALUES (?,?,?,?,?,?)",
                (t["id"], src, t["locator"], dev_id, t["app"], t["title"]),
            )
        for m in r.messages:
            conn.execute(
                "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
                " direction, ts_utc, ts_offset_min, ts_raw, body, lang, deleted_flag, bookmarked)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    m["id"],
                    src,
                    m["locator"],
                    m["thread_id"],
                    m["sender_account_id"],
                    m["direction"],
                    m["ts_utc"],
                    m["ts_offset_min"],
                    m["ts_raw"],
                    m["body"],
                    None,  # lang: the report does not say
                    m["deleted_flag"],
                    1 if m["tag"] else None,  # bookmarked: a Tag cell; blank = not stated
                ),
            )
            conn.execute(
                "INSERT INTO message_recipients (message_id, account_id) VALUES (?,?)",
                (m["id"], m["recipient_account_id"]),
            )
        for a in r.attachments:
            conn.execute(
                "INSERT INTO attachments VALUES (?,?,?,?,?,?,?)",
                (
                    a["id"],
                    src,
                    a["locator"],
                    a["message_id"],
                    a["file_name"],
                    a["mime_type"],
                    a["sha256"],
                ),
            )
        for c in r.calls:
            conn.execute(
                "INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    c["id"],
                    src,
                    c["locator"],
                    dev_id,
                    c["app"],
                    c["from_account_id"],
                    c["to_account_id"],
                    c["direction"],
                    c["ts_utc"],
                    c["ts_offset_min"],
                    c["ts_raw"],
                    c["duration_s"],
                    c["deleted_flag"],
                ),
            )
        for c in r.contacts:
            conn.execute(
                "INSERT INTO contacts VALUES (?,?,?,?,?,?)",
                (c["id"], src, c["locator"], dev_id, c["name"], c["identifier"]),
            )
    conn.commit()


# ---------------------------------------------------------------- affidavit and draft key


def affidavit_paragraphs() -> list[tuple[int, int, str]]:
    claims = {c.claim_id: c.text for c in key.CLAIMS}
    return [
        (page, no, " ".join(claims.get(p, p) for p in parts))
        for no, (page, parts) in enumerate(key.AFFIDAVIT, start=1)
    ]


def claim_location() -> dict[str, tuple[int, int]]:
    loc = {}
    for no, (page, parts) in enumerate(key.AFFIDAVIT, start=1):
        for p in parts:
            if p.startswith("C") and p[1:].isdigit():
                loc[p] = (page, no)
    return loc


def render_affidavit() -> str:
    lines = [
        "# Mock affidavit (SYNTHETIC DRAFT): case01",
        "",
        "Every name, number, agency and event in this document is fictional. Generated from",
        "`eval/synthetic/case01_key.py`; edit there, not here. Draft for Arsh's review.",
        "",
    ]
    page = 0
    for p, no, text in affidavit_paragraphs():
        if p != page:
            page = p
            lines += [f"## Page {page}", ""]
        lines += [f"{no}. {text}", ""]
    return "\n".join(lines)


def resolve(rendered: list[Rendered], refs: tuple[tuple[str, str], ...]) -> list[str]:
    by_dev = {r.device.key: r for r in rendered}
    ids: list[str] = []
    for dev, k in refs:
        found = by_dev[dev].keys.get(k)
        if not found:
            raise KeyError(f"evidence {dev}:{k} not found in generated data")
        ids += found
    return ids


def draft_gold(rendered: list[Rendered]) -> list[GoldClaim]:
    loc = claim_location()
    return [
        GoldClaim(
            claim_id=c.claim_id,
            page=loc[c.claim_id][0],
            para_no=loc[c.claim_id][1],
            text=c.text,
            claim_type=c.claim_type,
            cross_device=c.cross_device,
            gold_verdict=c.verdict,
            core_assumptions=c.core_assumptions,
            key_evidence=tuple(resolve(rendered, c.evidence)),
            trap=c.trap,
            rationale=c.rationale,
            labeled_by=key.DRAFT_LABEL,
            labeled_at=DRAFT_LABELED_AT,
        )
        for c in key.CLAIMS
    ]


def _row_index(rendered: list[Rendered]) -> dict[str, dict]:
    idx: dict[str, dict] = {}
    for r in rendered:
        for m in r.messages:
            idx[m["id"]] = {"kind": "message", **m}
        for c in r.calls:
            idx[c["id"]] = {"kind": "call", **c}
        for c in r.contacts:
            idx[c["id"]] = {"kind": "contact", **c}
        for a in r.attachments:
            idx[a["id"]] = {"kind": "attachment", **a}
    return idx


def render_answer_key(rendered: list[Rendered], gold: list[GoldClaim]) -> str:
    idx = _row_index(rendered)
    counts: dict[str, int] = {}
    for g in gold:
        counts[g.gold_verdict.value] = counts.get(g.gold_verdict.value, 0) + 1
    out = [
        "# case01 answer key: DRAFT for Arsh's line-by-line review",
        "",
        "**Not gold.** The generating agent proposed every verdict below. Arsh decides each one.",
        "Approved lines get copied into `eval/gold/case01/gold.jsonl` by a human, with",
        "`labeled_by` set to the approver.",
        "",
        f"Draft split: {counts.get('supported', 0)} supported, "
        f"{counts.get('contradicted', 0)} contradicted, {counts.get('unproven', 0)} unproven; "
        f"{sum(g.cross_device for g in gold)} claims need both phones.",
        "",
        f"Shared assumption: {key.DEVICE_ATTRIBUTION}",
        "",
        "Labeling rules:",
        "",
        *[f"{i}. {rule}" for i, rule in enumerate(key.LABELING_RULES, start=1)],
        "",
        "Paragraph numbers (¶) are the numbers printed in the affidavit, not document order.",
        "",
        "Times below are as printed in each report. Item 1 prints UTC+0; Item 2 prints device "
        "local time. Both phones are set to America/New_York.",
        "",
        "| Claim | Para | Type | Draft verdict | Trap | Cross-device | Approve? |",
        "|---|---|---|---|---|---|---|",
    ]
    for g in gold:
        out.append(
            f"| {g.claim_id} | p{g.page} ¶{g.para_no} | {g.claim_type.value} | "
            f"**{g.gold_verdict.value}** | {g.trap or ''} | "
            f"{'yes' if g.cross_device else ''} | [ ] |"
        )
    out.append("")
    for g in gold:
        out += [
            f"## {g.claim_id}: draft **{g.gold_verdict.value}**",
            "",
            f"> {g.text}",
            "",
            f"- Type: {g.claim_type.value}. Page {g.page}, paragraph {g.para_no}."
            + (f" Trap: {g.trap}." if g.trap else "")
            + (" Needs both phones." if g.cross_device else ""),
            "- Core assumptions: " + "; ".join(g.core_assumptions),
            f"- Reasoning: {g.rationale}",
            "- Evidence:",
            "",
            "| Record id | Printed time | From | To | Text |",
            "|---|---|---|---|---|",
        ]
        for rid in g.key_evidence:
            row = idx[rid]
            if row["kind"] == "message":
                text = row["body"] or "(attachment only)"
                out.append(
                    f"| `{rid}` | {row['ts_raw']} | {row['app']} {row['from_cell']} | "
                    f"{row['to_cell']} | {text} |"
                )
            elif row["kind"] == "call":
                out.append(
                    f"| `{rid}` | {row['ts_raw']} | {row['app']} {row['from_cell']} | "
                    f"{row['to_cell']} | {row['direction']} call, "
                    f"{fmt_duration(row['duration_s'])} |"
                )
            elif row["kind"] == "attachment":
                out.append(f"| `{rid}` |  | attachment | | {row['file_name']} |")
            else:
                out.append(f"| `{rid}` |  | contact | | {row['name']}: {row['identifier']} |")
        out += ["", "Arsh's decision: [ ] agree  [ ] change to ______  Note:", ""]
    return "\n".join(out)


def case_json(rendered: list[Rendered], out: Path) -> dict:
    return {
        "case_id": "case01",
        "description": "Synthetic case. Two phones, mixed English and Russian, hand-placed traps.",
        "synthetic": True,
        "generator": GENERATOR_VERSION,
        "seed": SEED,
        "devices": [
            {
                "source_id": r.device.key,
                "label": r.device.label,
                "model": r.device.model,
                "timezone": story.DEVICE_TZ,
                "report_time": r.device.report_tz,
                "extraction_type": r.device.extraction_type,
                "owner": story.PEOPLE[r.device.owner],
                "messages": len(r.messages),
                "calls": len(r.calls),
                "contacts": len(r.contacts),
            }
            for r in rendered
        ],
        "sources": [
            {
                "source_id": r.device.key,
                "file": f"{r.device.key}.xlsx",
                "kind": "cellebrite_excel",
                "fidelity": "curated_report",
                "sha256": sha256_file(out / f"{r.device.key}.xlsx"),
            }
            for r in rendered
        ],
        "traps": {
            "handle_change": "Telegram user 5551234 shows as @alex92, then @northstar from "
            f"{iso(story.RENAME_AT)}. Same user id throughout.",
            "shared_account": "Instagram dp_garage on item1 is also used by Ilya Morozov "
            "(ig03, il01).",
            "timezone": "item1 prints UTC+0, item2 prints local time (EST, then EDT from "
            "2026-03-08). pr03 and ns_move/c_luis read wrong if printed times are "
            "taken as local.",
            "gap": f"No WhatsApp rows on either phone from {iso(story.WA_GAP_START)} to "
            f"{iso(story.WA_GAP_END)}; SMS, Telegram and calls continue.",
            "decoy_thread": "'tickets' in the item1 SMS thread with Alex Turner are concert "
            "tickets (at03-at09).",
            "second_alex": "item1 'Alex' (+12125550182) is Alex Turner. @northstar is linked "
            "to +12125550147 in item2 contacts ('Sasha N').",
            "meeting_place": "REYES proposed the Mar 9 meeting place (pr05); PETROV agreed (pr06).",
        },
        "ground_truth_people": story.PEOPLE,
    }


# ---------------------------------------------------------------- main


def generate(out: Path, db: Path | None = None, seed: int = SEED) -> list[Rendered]:
    out.mkdir(parents=True, exist_ok=True)
    rendered = build(seed)
    for r in rendered:
        write_xlsx(out / f"{r.device.key}.xlsx", r.sheets)
    gold = draft_gold(rendered)
    (out / "case.json").write_text(
        json.dumps(case_json(rendered, out), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out / "affidavit_draft.md").write_text(render_affidavit(), encoding="utf-8")
    (out / "draft_gold.jsonl").write_text(
        "".join(g.model_dump_json() + "\n" for g in gold), encoding="utf-8"
    )
    (out / "ANSWER_KEY_DRAFT.md").write_text(render_answer_key(rendered, gold), encoding="utf-8")
    if db is not None:
        db.parent.mkdir(parents=True, exist_ok=True)
        db.unlink(missing_ok=True)
        conn = connect(db)
        try:
            load_db(conn, rendered, out)
        finally:
            conn.close()
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    rendered = generate(args.out, args.db)
    total = sum(len(r.messages) for r in rendered)
    print(f"case01: {total} messages across {len(rendered)} devices -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
