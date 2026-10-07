"""Generate HIDDEN synthetic case02: Cellebrite-style Excel reports, the expected canonical
database, the mock affidavit (Markdown, and a PDF next to --db) and the DRAFT answer key.
SYNTHETIC data only; deterministic for a seed. Builder threads must not read this file.

Usage: python -m eval.synthetic.case02_generate [--out eval/synthetic/case02] [--db <path>]

Outputs in --out:
  item1.xlsx, item2.xlsx   one Cellebrite-style report per phone (same layout as case01)
  case.json                metadata, devices, source hashes, planted traps, ground truth
  affidavit_draft.md       mock government affidavit, printed paragraph numbers from 21
  draft_gold.jsonl         DRAFT answer key in GoldClaim format, not gold until Arsh signs off
  ANSWER_KEY_DRAFT.md      the same key with reasoning and the cited rows, for line-by-line review

--db writes the canonical rows a correct importer should produce from the two reports, and
affidavit.pdf in the same directory (the PDF the govdoc ingester reads; not committed).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core.contracts import GoldClaim
from core.db import apply_schema, connect
from eval.synthetic import case02_key as key
from eval.synthetic import case02_story as story
from eval.synthetic import govdocs
from eval.synthetic.case02_filler import make_filler
from eval.synthetic.generate import (
    ACCOUNT_COLUMNS,
    CALL_COLUMNS,
    CHAT_COLUMNS,
    CONTACT_COLUMNS,
    TITLE_ROWS,
    fmt_duration,
    fmt_ts,
    iso,
    phone_of,
    sha256_file,
)
from eval.synthetic.xlsx import write_xlsx

GENERATOR_VERSION = "case02-gen 0.1.0"
TOOL_NAME = "baker-synth (Cellebrite-style layout)"
CASE_NUMBER = "SYN-2026-0002"
SEED = 20260318
DEFAULT_OUT = Path("eval/synthetic/case02")
IMPORTED_AT = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)  # fixed so the expected DB is stable
DRAFT_LABELED_AT = datetime(2026, 10, 7, tzinfo=UTC)
HIDDEN_NOTE = (
    "Hidden eval case. Builder threads must not read eval/synthetic/case02*, "
    "tests/test_synthetic_case02.py or eval/out/case02/."
)

Row = list[str | int | None]


# ---------------------------------------------------------------- rendering


@dataclass
class Rendered:
    """Everything derived for one device: report sheets plus canonical rows."""

    device: story.Device
    sheets: list[tuple[str, list[Row]]] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)
    threads: list[dict] = field(default_factory=list)
    accounts: dict[tuple[str, str], dict] = field(default_factory=dict)
    attachments: list[dict] = field(default_factory=list)
    device_row: int = 0
    keys: dict[str, list[str]] = field(default_factory=dict)  # story key -> record ids


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
        if app == acct.app:
            r.keys.setdefault(f"acct:{acct.key}", [r.accounts[k]["id"]])
    return r.accounts[k]["id"]


def _on_device(dev: story.Device, m: story.Msg) -> bool:
    if m.only is not None and m.only != dev.key:
        return False
    owned = set(dev.owner_accounts)
    group = story.GROUPS.get(m.to)
    if group is not None:
        return group.key not in dev.omitted_groups and any(a in owned for a in group.members)
    return m.sender in owned or m.to in owned


def _summary(dev: story.Device) -> list[Row]:
    return [
        ["Summary (SYNTHETIC: all data fictional, generated by eval/synthetic)"],
        ["Case number", CASE_NUMBER],
        ["Evidence number", dev.evidence_no],
        ["Device", dev.model],
        ["OS version", dev.os_version],
        ["Extraction type", dev.extraction_label],
        [
            "Extraction start date/time",
            fmt_ts(dev.extracted_at, dev.printed_offset(dev.extracted_at)),
        ],
        # The report's display setting. Not the phone's zone.
        ["Time zone", "UTC+0" if dev.report_tz == "utc" else "Device local (offset shown per row)"],
        ["Device time zone", story.DEVICE_TZ],
        ["Report version", f"baker-synth {GENERATOR_VERSION} (Cellebrite-style layout)"],
        ["Tool", TOOL_NAME],
        ["Tool version", GENERATOR_VERSION],
    ]


def render_device(dev: story.Device, msgs: list[story.Msg], calls: list[story.Call]) -> Rendered:
    r = Rendered(dev)
    acc = story.ACCOUNTS
    src = dev.key
    owned = set(dev.owner_accounts)

    r.device_row = 4
    r.sheets.append(("Summary", _summary(dev)))

    # ---- User Accounts: the phone's own accounts
    acct_rows: list[Row] = [["User Accounts"], ACCOUNT_COLUMNS]
    for i, k in enumerate(dev.owner_accounts, start=1):
        a = acc[k]
        name = a.name_at(dev.extracted_at) if a.app == "Telegram" else None
        acct_rows.append([i, a.app, a.identifier, name or ""])
        _account(r, a.app, a, f"User Accounts!{TITLE_ROWS + i}", dev.extracted_at, name)
    r.sheets.append(("User Accounts", acct_rows))

    # ---- Contacts
    contact_rows: list[Row] = [["Contacts"], CONTACT_COLUMNS]
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

    # ---- Chats: group by thread (app + other party, or the group), ordered by first message
    threads: dict[tuple[str, str], list[story.Msg]] = {}
    for m in msgs:
        if not _on_device(dev, m):
            continue
        if m.to in story.GROUPS:
            tkey = (story.GROUPS[m.to].app, m.to)
        else:
            other = m.to if m.sender in owned else m.sender
            tkey = (acc[m.sender].app, other)
        threads.setdefault(tkey, []).append(m)
    ordered = sorted(threads.items(), key=lambda kv: (min(x.at for x in kv[1]), kv[0]))

    chat_rows: list[Row] = [["Chats"], CHAT_COLUMNS]
    n = 0
    for chat_no, ((app, other_key), tmsgs) in enumerate(ordered, start=1):
        group = story.GROUPS.get(other_key)
        if group is not None:
            members = [acc[k] for k in group.members]
            owner = next(a for a in members if a.key in owned)
            people = [owner] + [a for a in members if a.key != owner.key]
            chat_name = group.name
            identifier = group.identifier
        else:
            other = acc[other_key]
            owner_key = next(x.sender if x.sender in owned else x.to for x in tmsgs)
            people = [acc[owner_key], other]
            chat_name = _name(dev, other, dev.extracted_at) or other.identifier
            identifier = other.identifier
        participants = "\n".join(_display(dev, a, dev.extracted_at) for a in people)
        first_row = TITLE_ROWS + n + 1
        thread_id = f"thr:{src}:{app}:{chat_no}"
        r.threads.append(
            {"id": thread_id, "locator": f"Chats!{first_row}", "app": app, "title": chat_name}
        )
        for m in sorted(tmsgs, key=lambda x: (x.at, x.key)):
            n += 1
            row = TITLE_ROWS + n
            loc = f"Chats!{row}"
            offset = dev.printed_offset(m.at)
            raw = fmt_ts(m.at, offset)
            outgoing = m.sender in owned
            deleted = m.key in dev.deleted
            sender = acc[m.sender]
            if group is not None:
                recipients = [a for a in people if a.key != m.sender]
            else:
                recipients = [acc[m.to]]
            from_cell = _display(dev, sender, m.at)
            to_cell = "\n".join(_display(dev, a, m.at) for a in recipients)
            chat_rows.append(
                [
                    n,
                    chat_no,
                    chat_name,
                    app,
                    identifier,
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
            sender_id = _account(r, app, sender, loc, m.at)
            recipient_ids = [_account(r, app, a, loc, m.at) for a in recipients]
            r.messages.append(
                {
                    "id": mid,
                    "locator": loc,
                    "thread_id": thread_id,
                    "sender_account_id": sender_id,
                    "recipient_account_ids": recipient_ids,
                    "from_cell": from_cell,
                    "to_cell": to_cell,
                    "direction": "outgoing" if outgoing else "incoming",
                    "ts_utc": iso(m.at),
                    "ts_offset_min": offset,
                    "ts_raw": raw,
                    "body": m.body,
                    "lang": m.lang,  # truth for tests; the importer stores NULL
                    "deleted_flag": int(deleted),
                    "tag": m.tag,
                    "app": app,
                    "key": m.key,
                    "group": group.key if group else None,
                }
            )
            if m.attachment:
                aid = f"att:{src}:{loc}:1"
                r.attachments.append(
                    {
                        "id": aid,
                        "locator": loc,
                        "message_id": mid,
                        "file_name": m.attachment,
                        "mime_type": None,  # not in the report
                        "sha256": None,
                    }
                )
                r.keys[f"att:{m.key}"] = [aid]
            r.keys.setdefault(m.key, []).append(mid)
    r.sheets.append(("Chats", chat_rows))

    # ---- Call Log
    call_rows: list[Row] = [["Call Log"], CALL_COLUMNS]
    mine_calls = sorted(
        (c for c in calls if c.caller in owned or c.callee in owned), key=lambda c: (c.at, c.key)
    )
    for i, c in enumerate(mine_calls, start=1):
        row = TITLE_ROWS + i
        loc = f"Call Log!{row}"
        offset = dev.printed_offset(c.at)
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
    filler_msgs, filler_calls = make_filler(seed)
    msgs = list(story.SCRIPTED_MESSAGES) + filler_msgs
    calls = list(story.SCRIPTED_CALLS) + filler_calls
    return [render_device(d, msgs, calls) for d in story.DEVICES]


# ---------------------------------------------------------------- canonical database


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
        dev_id = f"dev:{src}"
        conn.execute(
            "INSERT INTO devices VALUES (?,?,?,?,?,?,?)",
            (
                dev_id,
                src,
                f"Summary!{r.device_row}",
                d.model,
                d.model,
                d.os_version,
                story.DEVICE_TZ,
            ),
        )
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
            for rid in dict.fromkeys(m["recipient_account_ids"]):
                conn.execute(
                    "INSERT INTO message_recipients (message_id, account_id) VALUES (?,?)",
                    (m["id"], rid),
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


AFFIDAVIT_TITLE = "AFFIDAVIT IN SUPPORT OF A CRIMINAL COMPLAINT (EXCERPT)"
PDF_HEADER = f"SYNTHETIC TEST DOCUMENT - Case No. {CASE_NUMBER} - NOT A REAL CASE"


def affidavit_paragraphs() -> list[tuple[int, int, str]]:
    """(page, printed paragraph number, text)."""
    claims = {c.claim_id: c.text for c in key.CLAIMS}
    return [
        (page, no, " ".join(claims.get(p, p) for p in parts))
        for no, (page, parts) in enumerate(key.AFFIDAVIT, start=key.FIRST_PARA)
    ]


def claim_location() -> dict[str, tuple[int, int]]:
    loc = {}
    for no, (page, parts) in enumerate(key.AFFIDAVIT, start=key.FIRST_PARA):
        for p in parts:
            if p.startswith("C") and p[1:].isdigit():
                loc[p] = (page, no)
    return loc


def render_affidavit() -> str:
    lines = [
        "# Mock affidavit (SYNTHETIC DRAFT): case02",
        "",
        "Hidden eval case. Every name, number, agency and event in this document is fictional.",
        "Generated from `eval/synthetic/case02_key.py`; edit there, not here. Draft for Arsh's",
        "review. This is an excerpt: printed paragraph numbers start at 21.",
        "",
        f"**{AFFIDAVIT_TITLE}**",
        "",
    ]
    page = 0
    for p, no, text in affidavit_paragraphs():
        if p != page:
            page = p
            lines += [f"## Page {page}", ""]
        lines += [f"{no}. {text}", ""]
    return "\n".join(lines)


def write_affidavit_pdf(path: Path) -> Path:
    """Deterministic PDF of the affidavit; each paragraph lands on the page the key states."""
    by_page: dict[int, list[govdocs.Para]] = {}
    for page, no, text in affidavit_paragraphs():
        by_page.setdefault(page, []).append(govdocs.Para(text, no))
    by_page[1].insert(0, govdocs.Para(AFFIDAVIT_TITLE, heading=True))
    pages: list[list[tuple[float, float, str]]] = []
    for page in sorted(by_page):
        lines: list[tuple[float, float, str]] = []
        y = govdocs.TOP
        for para in by_page[page]:
            for x, text in govdocs._lines(para):  # noqa: SLF001 - shared synthetic helper
                if y > govdocs.BOTTOM:
                    raise ValueError(f"affidavit page {page} overflows; move a paragraph")
                lines.append((x, y, text))
                y += govdocs.LEADING
            y += govdocs.PARA_GAP
        pages.append(lines)
    c = govdocs._canvas(str(path), AFFIDAVIT_TITLE, "baker synthetic")  # noqa: SLF001
    for n, lines in enumerate(pages, start=1):
        c.setFont(govdocs.FONT, 8)
        c.drawString(govdocs.LEFT, govdocs.PAGE_H - 48, PDF_HEADER)
        c.drawString(govdocs.PAGE_W / 2 - 24, govdocs.PAGE_H - 760, f"Page {n} of {len(pages)}")
        govdocs._draw_lines(c, lines)  # noqa: SLF001
        c.showPage()
    c.save()
    return path


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


def row_index(rendered: list[Rendered]) -> dict[str, dict]:
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
        for a in r.accounts.values():
            idx[a["id"]] = {"kind": "account", **a}
    return idx


def _cell(text: str) -> str:
    return text.replace("\n", "; ").replace("|", "\\|")


def render_answer_key(rendered: list[Rendered], gold: list[GoldClaim]) -> str:
    idx = row_index(rendered)
    counts: dict[str, int] = {}
    for g in gold:
        counts[g.gold_verdict.value] = counts.get(g.gold_verdict.value, 0) + 1
    out = [
        "# case02 answer key: DRAFT for Arsh's line-by-line review",
        "",
        f"**{HIDDEN_NOTE}**",
        "",
        "**Not gold.** The generating agent proposed every verdict below. Arsh decides each one.",
        "Approved lines get copied into `eval/gold/case02/gold.jsonl` by a human, with",
        "`labeled_by` set to the approver.",
        "",
        f"Draft split: {counts.get('supported', 0)} supported, "
        f"{counts.get('contradicted', 0)} contradicted, {counts.get('unproven', 0)} unproven; "
        f"{sum(g.cross_device for g in gold)} claims need both phones.",
        "",
        f"Shared assumption: {key.DEVICE_ATTRIBUTION}",
        "",
        "Labeling rules (1 to 4 are case01's; rules marked NEW need Arsh's approval):",
        "",
        *[f"{i}. {rule}" for i, rule in enumerate(key.LABELING_RULES, start=1)],
        "",
        "Paragraph numbers (¶) are the numbers printed in the affidavit, not document order. "
        "The affidavit is an excerpt that starts at ¶21.",
        "",
        "Times below are as printed in each report. Item 1 prints UTC+0. Item 2 prints device "
        "local time: CST (UTC-6) until the DST change on 2026-03-08, CDT (UTC-5) after it, and "
        "PDT (UTC-7) from Mar 18 to Mar 23 while QUINTERO was in Los Angeles. Both phones are set "
        "to America/Chicago. The affidavit states its times in Central (¶23). Group-message "
        "recipients are separated by ';'.",
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
                deleted = " [report: Deleted]" if row["deleted_flag"] else ""
                out.append(
                    f"| `{rid}` | {row['ts_raw']} | {row['app']} {_cell(row['from_cell'])} | "
                    f"{_cell(row['to_cell'])} | {_cell(text)}{deleted} |"
                )
            elif row["kind"] == "call":
                out.append(
                    f"| `{rid}` | {row['ts_raw']} | {row['app']} {row['from_cell']} | "
                    f"{row['to_cell']} | {row['direction']} call, "
                    f"{fmt_duration(row['duration_s'])} |"
                )
            elif row["kind"] == "attachment":
                out.append(f"| `{rid}` |  | attachment | | {row['file_name']} |")
            elif row["kind"] == "account":
                where = (
                    "the phone's own account, User Accounts" if row["owned"] else "seen in chats"
                )
                out.append(
                    f"| `{rid}` |  | account | | {row['app']} {row['identifier']} ({where}) |"
                )
            else:
                out.append(f"| `{rid}` |  | contact | | {row['name']}: {row['identifier']} |")
        out += ["", "Arsh's decision: [ ] agree  [ ] change to ______  Note:", ""]
    return "\n".join(out)


TRAPS = {
    "travel_tz": "QUINTERO's phone (item2, device-local report) prints rows from "
    f"{iso(story.TRAVEL_START)} to {iso(story.TRAVEL_END)} as (UTC-7) because he was in Los "
    "Angeles; the Summary still says America/Chicago. The affidavit states Central time. qh03 "
    "is 12:30 AM CDT Mar 20 but prints 3/19 10:30 PM (UTC-7); s07 prints 3/20 11:41 PM (UTC-7) "
    "but is 1:41 AM CDT Mar 21.",
    "dst": "US DST starts 2026-03-08. s03 prints 3/10 1:15 AM (UTC+0) on item1; CDT gives "
    "8:15 PM Mar 9, CST would give 7:15 PM.",
    "group_sender": "WhatsApp group 'Westside Flips' (item1): g05 'drop is at the storage on "
    "4th...' was sent by HALE (+13125550131), not BRANDT.",
    "quoted_speech": "s05: BRANDT reports Wade's words ('wade said \"bring the cash friday\"').",
    "negation": "km02: BRANDT denies ('i never sold chino anything') in reply to MERCER.",
    "call_count": "Five BRANDT-QUINTERO call records Mar 10-14 (Central): two connected "
    "(00:04:31, 00:01:02), two Missed, one outgoing 00:00:00. Two print outside the window's "
    "dates in UTC on item1.",
    "deleted_flag": "item2 marks six Telegram rows with BRANDT (tq03-tq07, tq12) Deleted; item1 "
    "has them Intact. item2 also marks three filler SMS with Dani Deleted; item1 two with Gary. "
    "The flag carries no time or actor.",
    "absence_curated": "The item2 report omits the 'Westside Flips' group although QUINTERO's "
    "account posts in it; item1's copy shows QUINTERO and HALE exchanging messages on Mar 24 "
    "(g07, g08). No row on either phone involves +13125550143 after Mar 14.",
    "sarcasm": "g02 'yeah im the kingpin lol' answers a joke about having more drills than the "
    "hardware store.",
    "name_collision": "item1 'Chino' is +13125550143 (Hector Salas); item2 'Chino' is "
    "+13125550158 (Victor Aguilar, QUINTERO's cousin).",
    "attachment_only": "ch03 is an empty-bodied WhatsApp message with attachment IMG_4471.jpg; "
    "the report has no image content, hash or MIME type.",
    "translation": "Spanish: mq01 (going to Los Angeles on Wednesday) and mf01 (slang 'la cosa "
    "está caliente', no mention of police or a storage unit).",
    "handle_reuse": "Telegram name 'Vic Tools' is shown by two user ids on item1: 8200417 "
    "(Feb 24 to Mar 10) and 8200952 (Mar 17 to Mar 25). Inverse of case01's handle_change.",
}


def case_json(rendered: list[Rendered], out: Path) -> dict:
    return {
        "hidden": True,
        "note": HIDDEN_NOTE,
        "case_id": "case02",
        "description": "Synthetic case. Two phones, English and Spanish, a resale ring for "
        "stolen tools; hand-placed traps that differ from case01.",
        "synthetic": True,
        "generator": GENERATOR_VERSION,
        "seed": SEED,
        "affidavit": {
            "markdown": "affidavit_draft.md",
            "pdf": "written next to --db as affidavit.pdf (not committed)",
            "first_printed_paragraph": key.FIRST_PARA,
            "time_zone_statement": "paragraph 23: Central Time (America/Chicago)",
        },
        "devices": [
            {
                "source_id": r.device.key,
                "label": r.device.label,
                "model": r.device.model,
                "timezone": story.DEVICE_TZ,
                "report_time": r.device.report_tz,
                "travel": [
                    {"start_utc": iso(s), "end_utc": iso(e), "offset_min": off}
                    for s, e, off in r.device.travel
                ],
                "omitted_from_report": [story.GROUPS[g].name for g in r.device.omitted_groups],
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
        "traps": TRAPS,
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
        write_affidavit_pdf(db.parent / "affidavit.pdf")
    return rendered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args(argv)
    rendered = generate(args.out, args.db)
    total = sum(len(r.messages) for r in rendered)
    print(f"case02: {total} messages across {len(rendered)} devices -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
