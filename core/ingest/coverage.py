"""Read an import's coverage record and say, in plain words, what was read and what was not.

Every Cellebrite import writes one `source_coverage` row (core/schema.sql, `SourceCoverage` in
core/contracts.py). Its payload is described in docs/ingest/coverage.md. This module turns it
into a short summary for the case screen, the CLI and the report's limitations.

Each item is a list of segments. A segment marked quoted is text taken from the report itself
(a sheet or column name, a raw value); everything else is Mabillon's own words. Renderers pass
quoted segments through their quote helper, so the forbidden-word check can tell them apart.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from core.contracts import SourceCoverage

Level = Literal["attention", "info"]
Segment = tuple[str, bool]  # (text, quoted from the report)

KIND_WORDS = {
    "chats": "chat messages",
    "sms": "SMS and MMS messages",
    "calls": "calls",
    "contacts": "contacts",
    "accounts": "the phone's own accounts",
}
_RECORD_WORDS = {
    "chats": "messages",
    "sms": "messages",
    "calls": "calls",
    "contacts": "contacts",
    "accounts": "accounts",
}
_KEY_FIELD_WORDS = {
    "time": "time column, so its records have no time",
    "body": "message text column, so its messages have no text to cite",
    "from": "sender column, so senders are known only where direction says so",
    "name": "name column",
}
# Each phrase follows a count; {be}, {have}, {s0} and {them} agree with it.
_SKIP_REASON_WORDS = {
    "no_values_in_known_columns": (
        "had values only in columns Mabillon does not read (for example a footer or a sub-heading)"
    ),
    "header_like_row": "held only column names (a second header row Mabillon could not join)",
    "account_without_identifier": "had no username or identifier",
    "same_id_as_an_earlier_record": (
        "repeated the record id of an earlier record (the same record listed twice); the "
        "earlier one was imported"
    ),
}
_TIME_PROBLEM_WORDS = {
    "ambiguous_day_month": (
        "could be read day first or month first, and nothing in the report decides which, "
        "so no time was set. Re-import with the report's date order stated (month first or "
        "day first) to read {them}"
    ),
    "unparsed": "{be} not a date and time Mabillon recognises; kept as written, with no time",
    "date_only": "{be} a date with no time of day; kept as written, with no time",
    "two_digit_year": "{have} a two-digit year, which Mabillon does not guess; kept as written",
    "named_zone": (
        "name{s0} a time zone instead of a UTC offset; Mabillon does not apply zone names, so no "
        "UTC time was set"
    ),
    "numeric": "{be} a bare number, not a date; kept as written, with no time",
    "date_column_disagrees": (
        "{have} a date in the Date column that is not the date in the Time column (or is not a "
        "date), so Mabillon cannot tell which is right; kept as written, with no time"
    ),
    "no_offset": (
        "{have} no UTC offset in the value, the column name or the report settings; kept as "
        "written, with no UTC time"
    ),
}


def _fill(template: str, count: int, **extra: str) -> str:
    one = count == 1
    return template.format(
        **extra,
        be="is" if one else "are",
        have="has" if one else "have",
        s0="s" if one else "",
        them="it" if one else "them",
    )


# A second column for one of these fields may hold a different value (a read time, a second
# text), so the expert must see that it was not read.
_KEY_DUPLICATE_FIELDS = {"ts", "ts_date", "ts_time", "body", "from", "to", "parties", "duration"}
# Counters whose rows lost information; each is something the expert must see.
_ATTENTION_COUNTERS = {
    "tagged_file_ids_repeated": (
        "File ids listed more than once in taggedFiles with different paths; attachments naming "
        "them were not linked to any file, so those files were not hashed"
    ),
    "calls_with_extra_parties_dropped": (
        "Calls listing more than one caller or callee, where only the first of each was kept"
    ),
    "messages_with_multiple_senders_first_kept": (
        "Messages listing more than one sender, where only the first was kept"
    ),
    "calls_party_unattributed": (
        "Calls naming a party without saying whether it called or was called (the party is "
        "recorded, but not as caller or callee)"
    ),
    "values_contradicting_field_date_format": (
        "Time values that can only be read the other way round from the date format their "
        "field name states (each was read as written; compare with the tool that made the report)"
    ),
    "values_contradicting_stated_date_order": (
        "Time values that can only be read the other way round from the date order stated at "
        "import (each was read as written; check the stated order)"
    ),
    "attachments_without_file_reference": (
        "Attachments the package names without pointing to a file inside it (no file hash)"
    ),
}
_INFO_COUNTERS = {
    "embedded_messages_imported": (
        "Forwarded or quoted messages carried inside other messages, imported as records of their "
        "own (not in the extraction's own message count)"
    ),
    "related_copies": (
        "Messages, calls, contacts and accounts the package holds a second time under another "
        "record's RelatedModels (Cellebrite's related items), not imported again"
    ),
    "related_copies_matching_a_record": (
        "Of those, copies that say what the record holding them says (text or duration, time, "
        "parties, record state and attachments; a copied chat's messages one to one)"
    ),
    "embedded_messages_already_imported": (
        "Forwarded or quoted messages carried inside other messages that the extraction also "
        "lists as records of their own (same model id), so imported once"
    ),
    "picture_entries_not_identifiers": (
        "Picture entries (profile pictures, contact photos) in accounts and contacts, not used "
        "as identifiers"
    ),
    "times_offset_from_report_settings": (
        "Times read with the report's fixed time zone setting, having no offset of their own"
    ),
    "times_offset_from_column_header": (
        "Times read with the offset in their column name, having no offset of their own"
    ),
    "direction_unknown": "Messages with no stated or derivable direction",
    "parties_name_only": "Parties shown by name only, with no number or handle",
    "pdf_tables_kind_from_columns": "Tables under no heading, classified by their columns",
    "pdf_tables_continued_from_previous_page": (
        "Tables continued from the previous page and joined to it"
    ),
    "pdf_text_lines_outside_tables_in_data_sections": (
        "Lines of text outside tables in message or call sections, not read"
    ),
    "extraction_time_unread": "Extraction times in the summary that could not be read",
    "pdf_subheadings_in_sections": "Sub-headings inside sections (kept in their section)",
    "attachment_files_hashed": "Attachment files found in the package and SHA-256 hashed",
    "attachment_files_encrypted_not_hashed": (
        "Attachment files encrypted in the package, so not hashed"
    ),
    "chats_without_messages": "Chats with no messages in the package",
    "cells_with_excel_escapes_decoded": (
        "Cells holding characters Excel stores escaped (such as _x000D_ for the carriage "
        "return of a line break), read as the characters they stand for"
    ),
}


# Shown first for every import made with the AXIOM reader, until a real AXIOM export has been
# checked against the tool that made it. Attention level: the expert must see it. A UFDR import
# has no such item: since #117 its reader has been run on public Reader 7.48 packages, and the
# format notice (core/ingest/tested.py) says whether its version is in the tested set.
FORMAT_UNVERIFIED_AXIOM = (
    "Mabillon's Magnet AXIOM reader is not yet verified. It was built from public descriptions of "
    "AXIOM's XML and Excel report exports and tested only on synthetic exports, never on a real "
    "one. Before relying on a record, open the same record in AXIOM Examine (or the examiner's "
    "portable case) and compare (each record's locator gives its artifact and hit, or its sheet "
    "and row)."
)
# Per importer: the unverified notice ("" for none), the tool to compare records in, and what
# the file is.
READERS: dict[str, tuple[str, str, str]] = {
    "ufdr": ("", "Cellebrite Reader", "package"),
    "axiom": (FORMAT_UNVERIFIED_AXIOM, "AXIOM Examine", "report"),
}


def reader_words(importer: str) -> tuple[str, str, str]:
    return READERS.get(importer, READERS["ufdr"])


# Record flags a UFDR import lists by locator: (level, words). {n} is the count with its noun;
# {be}, {have}, {s0} and {them} agree with it.
_FLAG_WORDS: dict[str, tuple[Level, str]] = {
    "numbered_as_copy": (
        "attention",
        "{n} {be} numbered by the tool that made the report as a further copy of another row "
        "(such as '3(1)' after '3'), often the same database read at a second path. Each was "
        "imported as a record of its own, so a count of these messages may include one message "
        "twice; compare each with the row it copies before counting.",
    ),
    "carved": (
        "attention",
        "{n} {be} marked as recovered by carving (rebuilt from raw or unallocated data), so "
        "{them} may be incomplete or wrong in text, time or parties. They were imported; check "
        "each one in {tool} before relying on it.",
    ),
    "decoding_confidence_not_high": (
        "attention",
        "{n} {have} a decoding confidence other than high in the package; check {them} in "
        "{tool} before relying on {them}.",
    ),
    "attachment_file_not_in_package": (
        "attention",
        "{n} name{s0} an attachment file that is not in the package, so the file was not hashed.",
    ),
    "attachment_hash_differs": (
        "attention",
        "{n} {have} an attachment whose SHA-256 in the package differs from the hash stated for "
        "it in report.xml.",
    ),
    "attachment_without_name": (
        "attention",
        "{n} {have} an attachment with neither a file name nor a file, so it was not recorded.",
    ),
    "forwarded": (
        "attention",
        "{n} {be} marked as forwarded. Mabillon shows {them} as sent by whoever forwarded {them} "
        "and has not verified who first wrote {them}, so {them} cannot support or contradict a "
        "claim; check each one in {tool} before saying who wrote {them}.",
    ),
    "embedded_message_imported_separately": (
        "attention",
        "{n} {have} a forwarded or quoted message inside {them}; Mabillon imported each such "
        "message as a record of its own (at the locator plus /Embedded[n]), but who wrote which "
        "words is not verified, so {them} cannot support or contradict a claim; see {them} in "
        "{tool}.",
    ),
    "embedded_original_imported": (
        "attention",
        "{n} {be} a forwarded or quoted message carried inside another message, imported "
        "separately and marked forwarded. The sender shown is the one the extraction "
        "names for the embedded message, not verified, so {them} cannot support or contradict a "
        "claim. These records are not in the extraction's own message count.",
    ),
    "embedded_message_not_imported": (
        "attention",
        "{n} {have} a forwarded or quoted message nested inside {them} (a second level) whose "
        "text and attachments Mabillon did not import, so {them} cannot support or contradict a "
        "claim; see {them} in {tool}.",
    ),
    "attachment_file_ambiguous": (
        "attention",
        "{n} {have} an attachment whose file id taggedFiles lists more than once with different "
        "paths, so it was not linked to a file or hashed.",
    ),
    "related_copy_unmatched": (
        "attention",
        "{n} {be} held only as a related copy (under another record's RelatedModels) that "
        "does not say what the record holding it says (app, text or duration, time, "
        "direction, parties, record state and attachments; a copied chat's messages one to "
        "one), so Mabillon did not "
        "import {them}; open each one in {tool}.",
    ),
    "duration_unread": ("attention", "{n} {have} a call duration Mabillon could not read."),
    "no_time": ("attention", "{n} {have} no time in the {container}, so no time was set."),
}


@dataclass(frozen=True)
class CoverageItem:
    level: Level
    code: str
    parts: tuple[Segment, ...]
    locators: tuple[str, ...] = ()  # where to look, capped (see MAX_LISTED in the importer)

    @property
    def plain(self) -> str:
        return "".join(t for t, _q in self.parts)


@dataclass(frozen=True)
class CoverageSummary:
    source_id: str
    file_name: str
    importer: str
    importer_version: str
    status: Literal["complete", "needs_review"]
    headline: str
    items: tuple[CoverageItem, ...] = field(default=())

    @property
    def format_unverified(self) -> bool:
        """The import was made with a reader not yet checked against a real file."""
        return any(i.code == "format_unverified" for i in self.items)

    @property
    def attention(self) -> list[CoverageItem]:
        return [i for i in self.items if i.level == "attention"]

    @property
    def info(self) -> list[CoverageItem]:
        return [i for i in self.items if i.level == "info"]


# ---------------------------------------------------------------- loading


def load(conn: sqlite3.Connection, source_id: str) -> SourceCoverage | None:
    """The coverage record for one source. Imports from before importer 0.2.0 wrote it to the
    audit log only, so that is read when the table has no row."""
    row = conn.execute(
        "SELECT source_id, importer, importer_version, payload_json FROM source_coverage"
        " WHERE source_id = ?",
        (source_id,),
    ).fetchone()
    if row is not None:
        return SourceCoverage(
            source_id=row[0], importer=row[1], importer_version=row[2], payload=json.loads(row[3])
        )
    for (payload_json,) in conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = 'import' ORDER BY seq DESC"
    ):
        p = json.loads(payload_json)
        if p.get("source_id") == source_id:
            return SourceCoverage(
                source_id=source_id,
                importer=str(p.get("importer", "")),
                importer_version=str(p.get("importer_version", "")),
                payload=p,
            )
    return None


def load_all(conn: sqlite3.Connection) -> list[SourceCoverage]:
    ids = [r[0] for r in conn.execute("SELECT id FROM sources WHERE kind != 'govdoc' ORDER BY id")]
    return [c for c in (load(conn, i) for i in ids) if c is not None]


def summary(conn: sqlite3.Connection, source_id: str) -> CoverageSummary | None:
    """The summary for one source, or None when it has no coverage record (a govdoc)."""
    c = load(conn, source_id)
    return summarize(c) if c is not None else None


def summaries(conn: sqlite3.Connection) -> list[CoverageSummary]:
    """One summary per imported evidence source, in source id order."""
    return [summarize(c) for c in load_all(conn)]


# ---------------------------------------------------------------- summarising


def _n(count: int, word: str) -> str:
    return f"{count:,} {word}" if count != 1 else f"1 {word.removesuffix('s')}"


def _q(text: object) -> Segment:
    return (str(text), True)


def _t(text: str) -> Segment:
    return (text, False)


def _names(values: list[str]) -> list[Segment]:
    out: list[Segment] = []
    for i, v in enumerate(values):
        if i:
            out.append(_t(", "))
        out.append(_q(v))
    return out


def _table_items(t: dict, xml: bool = False, importer: str = "ufdr") -> list[CoverageItem]:
    """Items for one table (a sheet or PDF table), or one record type of a UFDR (`xml`)."""
    items: list[CoverageItem] = []
    name = str(t.get("name"))
    kind = str(t.get("kind") or "")
    records = _RECORD_WORDS.get(kind, "records")
    where = [_t("In "), _q(name), _t(", ")]
    for f in t.get("missing_key_fields", []) or []:
        items.append(
            CoverageItem(
                "attention",
                f"missing_{f}",
                (*where, _t(f"there is no {_KEY_FIELD_WORDS.get(f, f + ' column')}.")),
            )
        )
    for reason, count in sorted((t.get("rows_skipped") or {}).items()):
        if reason in ("empty", "repeated_header"):
            continue
        items.append(
            CoverageItem(
                "attention",
                f"rows_skipped_{reason}",
                (
                    *where,
                    _t(
                        f"{_n(count, 'records' if xml else 'rows')} "
                        f"{'was' if count == 1 else 'were'} not imported: "
                        f"{'it' if count == 1 else 'they'} "
                        f"{_SKIP_REASON_WORDS.get(reason, reason.replace('_', ' '))}."
                    ),
                ),
                tuple((t.get("skipped_locators") or {}).get(reason, [])),
            )
        )
    for problem, count in sorted((t.get("time_problems") or {}).items()):
        items.append(
            CoverageItem(
                "attention",
                f"times_{problem}",
                (
                    *where,
                    _t(
                        f"{_n(count, 'time values')} "
                        + _fill(_TIME_PROBLEM_WORDS.get(problem, problem.replace("_", " ")), count)
                        + "."
                    ),
                ),
                tuple((t.get("time_problem_locators") or {}).get(problem, [])),
            )
        )
    for d in t.get("duplicate_columns") or []:
        if not isinstance(d, dict):
            continue
        key = d.get("field") in _KEY_DUPLICATE_FIELDS
        items.append(
            CoverageItem(
                "attention" if key else "info",
                "duplicate_column",
                (
                    *where,
                    _t("column "),
                    _q(d.get("column")),
                    _t(" was not read: an earlier column, "),
                    _q(d.get("used")),
                    _t(", holds the same field."),
                ),
            )  # fmt: skip
        )
    not_filled = t.get("merged_columns_not_filled") or []
    if not_filled:
        items.append(
            CoverageItem(
                "attention",
                "merged_cells_not_filled",
                (
                    *where,
                    _t(
                        "merged cells span several rows in columns whose value Mabillon does not "
                        "copy to every row (text, times, attachments, flags); only the first "
                        "row of each merge has the value. Columns: "
                    ),
                    *_names(not_filled),
                    _t("."),
                ),
            )
        )
    _notice, tool, container = reader_words(importer)
    for loc_reason, locs in sorted((t.get("flagged_locators") or {}).items()):
        if loc_reason in _FLAG_WORDS:
            level, words = _FLAG_WORDS[loc_reason]
            n = int((t.get("flag_counts") or {}).get(loc_reason, len(locs)))
            items.append(
                CoverageItem(
                    level,
                    loc_reason,
                    (
                        *where,
                        _t(_fill(words, n, n=_n(n, "records"), tool=tool, container=container)),
                    ),
                    tuple(locs),
                )
            )
        elif loc_reason == "body_at_excel_cell_limit":
            items.append(
                CoverageItem(
                    "attention",
                    "body_at_excel_cell_limit",
                    (
                        *where,
                        _t(
                            f"{_n(len(locs), 'message texts')} may be cut off at "
                            "Excel's 32,767-character cell limit."
                        ),
                    ),  # fmt: skip
                    tuple(locs),
                )
            )
    unknown = t.get("unknown_columns") or []
    if unknown:
        items.append(
            CoverageItem(
                "info",
                "unknown_columns",
                (
                    *where,
                    _t(f"{'fields' if xml else 'columns'} Mabillon does not read: "),
                    *_names(unknown),
                    _t("."),
                ),
            )
        )
    for col, off in sorted((t.get("header_offsets") or {}).items()):
        items.append(
            CoverageItem(
                "info",
                "header_offset",
                (
                    *where,
                    _t("times in "),
                    _q(col),
                    _t(f" were read at UTC{_fmt_off(off)}, from the column name."),
                ),  # fmt: skip
            )
        )
    for col, zone in sorted((t.get("header_zone_names") or {}).items()):
        items.append(
            CoverageItem(
                "info",
                "header_zone_name",
                (
                    *where,
                    _t("column "),
                    _q(col),
                    _t(" names the zone "),
                    _q(zone),
                    _t(", which is not a UTC offset, so it was not applied."),
                ),
            )  # fmt: skip
        )
    filled = int(t.get("merged_cells_filled") or 0)
    if filled:
        items.append(
            CoverageItem(
                "info",
                "merged_cells_filled",
                (
                    *where,
                    _t(
                        f"{_n(filled, 'cells')} of merged chat, party or app columns "
                        "took the merged value."
                    ),
                ),  # fmt: skip
            )
        )
    for note in t.get("header_notes") or []:
        items.append(CoverageItem("info", "header_note", (*where, _q(note))))
    if t.get("app_from_title"):
        items.append(
            CoverageItem(
                "info",
                "app_from_title",
                (
                    *where,
                    _t("the app was taken from the title: "),
                    _q(t["app_from_title"]),
                    _t("."),
                ),
            )  # fmt: skip
        )
    no_body = (t.get("flagged_locators") or {}).get("no_body_or_attachment")
    if no_body:
        items.append(
            CoverageItem(
                "info",
                "no_body_or_attachment",
                (*where, _t(f"some {records} have neither text nor an attachment.")),
                tuple(no_body),
            )
        )
    return items


def _ufdr_items(u: dict) -> list[CoverageItem]:
    """What a UFDR package held beyond its records: extractions, files, record states."""
    items: list[CoverageItem] = []
    partial = u.get("partial_extractions") or []
    if partial:
        items.append(
            CoverageItem(
                "attention",
                "partial_extraction",
                (
                    _t("The package marks these extractions as holding partial data: "),
                    *_names([str(x) for x in partial]),
                    _t(". Records missing from them may be on the phone."),
                ),
            )
        )
    exts = u.get("extractions") or []
    if len(exts) > 1:
        items.append(
            CoverageItem(
                "info",
                "several_extractions",
                (
                    _t(f"The package holds {len(exts)} extractions of one device, read together: "),
                    *_names([str(e.get("name") or e.get("type") or "?") for e in exts]),
                    _t(". A record that appears in more than one may be imported more than once."),
                ),
            )  # fmt: skip
        )
    if u.get("namespace") and not u.get("namespace_known"):
        items.append(
            CoverageItem(
                "info",
                "unknown_namespace",
                (
                    _t("report.xml uses the XML namespace "),
                    _q(u["namespace"]),
                    _t(", which Mabillon has not seen documented; it was read the same way."),
                ),
            )
        )
    files = int(u.get("package_files") or 0)
    hashed = int(u.get("package_files_hashed") or 0)
    if files:
        items.append(
            CoverageItem(
                "info",
                "package_files",
                (
                    _t(
                        f"The package holds {_n(files, 'other files')} (pictures, databases and "
                        f"other extracted files). Mabillon read report.xml and hashed "
                        f"{_n(hashed, 'files')} attached to messages; it did not read the rest."
                    ),
                ),
            )
        )
    tagged = int(u.get("tagged_files") or 0)
    if tagged:
        items.append(
            CoverageItem(
                "info",
                "tagged_files",
                (
                    _t(
                        f"report.xml lists {_n(tagged, 'files')}; "
                        "Mabillon does not import that list."
                    ),
                ),
            )
        )
    states = u.get("deleted_state_values") or {}
    if states:
        parts: list[Segment] = [_t("Record states as the package gives them: ")]
        for i, (k, v) in enumerate(sorted(states.items())):
            parts += [*([_t(", ")] if i else []), _q(k), _t(f" ({v:,})")]
        parts.append(_t(". Mabillon stores only what the package states."))
        items.append(CoverageItem("info", "record_states", tuple(parts)))
    return items


def _fmt_off(off: int) -> str:
    sign = "-" if off < 0 else "+"
    h, m = divmod(abs(off), 60)
    return f"{sign}{h}" + (f":{m:02d}" if m else "")


def summarize(c: SourceCoverage) -> CoverageSummary:
    p = c.payload
    items: list[CoverageItem] = []
    xml = p.get("layout") == "xml"  # a UFDR: record types, not sheets or tables
    notice = reader_words(str(p.get("importer", "")))[0]
    if p.get("format_support") == "unverified" and notice:
        items.append(CoverageItem("attention", "format_unverified", (_t(notice),)))
    tables = [t for t in p.get("tables", []) if isinstance(t, dict)]
    for entry in p.get("not_imported", []) or []:
        reason = str(entry.get("reason", ""))
        deliberate = reason == "category not imported" or reason.startswith("section '")
        rows, lines = entry.get("rows"), entry.get("lines")
        records = entry.get("records")
        parts: list[Segment] = [_q(entry.get("name")), _t(" was not imported")]
        if isinstance(records, int):
            parts.append(_t(f" ({_n(records, 'records')})"))
        elif isinstance(rows, int):
            parts.append(_t(f" ({_n(rows, 'rows')}, any header included)"))
        elif isinstance(lines, int):
            parts.append(_t(f" ({_n(lines, 'lines')} of text)"))
        parts.append(_t(": " + _reason_words(reason)))
        if entry.get("section"):
            parts += [_t(" (section "), _q(entry["section"]), _t(")")]
        parts.append(_t("."))
        cols = entry.get("columns") or []
        if cols:
            parts += [_t(" Its first row: "), *_names(cols), _t(".")]
        items.append(
            CoverageItem(
                "info" if deliberate else "attention",
                "category_not_imported" if deliberate else "not_imported",
                tuple(parts),
            )
        )
    for t in tables:
        items += _table_items(t, xml, str(p.get("importer", "")))
    borrowed: dict[tuple[str, str], list[str]] = {}
    for t in tables:
        basis, order = t.get("date_order_basis"), t.get("date_order")
        if basis in ("other tables in the report", "stated at import", "field name") and order in (
            "dmy",
            "mdy",
        ):
            borrowed.setdefault((basis, order), []).append(str(t.get("name")))
    for (basis, order), names in borrowed.items():
        words = "day first" if order == "dmy" else "month first"
        why = {
            "other tables in the report": (
                "because other tables in the same report decide the order"
            ),
            "field name": "as the date format in the time field's name states",
        }.get(basis, "as stated at import")
        items.append(
            CoverageItem(
                "info",
                "date_order",
                (_t("Dates in "), *_names(names), _t(f" were read {words}, {why}.")),
            )
        )
    counts = p.get("counts", {}) or {}
    for key, words in _ATTENTION_COUNTERS.items():
        if counts.get(key):
            items.append(CoverageItem("attention", key, (_t(f"{words}: {counts[key]:,}."),)))
    for key, words in _INFO_COUNTERS.items():
        if counts.get(key):
            items.append(CoverageItem("info", key, (_t(f"{words}: {counts[key]:,}."),)))
    unmapped = p.get("unmapped_direction_values") or {}
    if unmapped:
        items.append(
            CoverageItem(
                "info",
                "unmapped_direction_values",
                (
                    _t("Direction values Mabillon does not read: "),
                    *_names(sorted(unmapped)),
                    _t("."),
                ),
            )
        )
    missing = p.get("categories_not_found")
    if missing:
        names = [KIND_WORDS.get(k, k) for k in missing]
        items.append(
            CoverageItem(
                "info",
                "categories_not_found",
                (
                    _t(
                        f"The {'package' if xml else 'report'} has no "
                        f"{'records' if xml else 'section'} Mabillon reads for "
                        + ", ".join(names)
                        + f". That means only that the {'package' if xml else 'report'} does "
                        "not include them, not that the phone had none."
                    ),
                ),
            )
        )
    if p.get("summary_found") is False:
        items.append(
            CoverageItem(
                "info",
                "no_summary",
                (
                    _t(
                        "The package has no device metadata Mabillon recognises, so the "
                        "extraction time and device were not read from it."
                        if xml
                        else "The report has no summary Mabillon recognises, so the extraction "
                        "time, device and report time zone were not read from it."
                    ),
                ),
            )
        )
    stated = p.get("date_order_stated_at_import")
    if stated:
        words = "day first" if stated == "dmy" else "month first"
        items.append(
            CoverageItem(
                "info", "date_order_stated", (_t(f"Date order stated at import: {words}."),)
            )
        )
    tz_raw = p.get("report_time_zone_raw")
    if tz_raw is not None and p.get("report_offset_min_applied") is None:
        items.append(
            CoverageItem(
                "info",
                "report_time_zone_not_fixed",
                (
                    _t("The report's time zone setting "),
                    _q(tz_raw),
                    _t(" is not a fixed UTC offset, so it was not applied to times without one."),
                ),
            )  # fmt: skip
        )
    hidden = p.get("hidden_sheets") or []
    if hidden:
        items.append(
            CoverageItem(
                "info",
                "hidden_sheets",
                (_t("Hidden sheets, read like the others: "), *_names(hidden), _t(".")),
            )
        )
    multi = p.get("accounts_with_multiple_display_names") or []
    if multi:
        items.append(
            CoverageItem(
                "info",
                "accounts_with_multiple_display_names",
                (
                    _t("Accounts shown with more than one display name (the first is stored): "),
                    *_names(multi),
                    _t("."),
                ),
            )  # fmt: skip
        )
    if isinstance(p.get("ufdr"), dict):
        items += _ufdr_items(p["ufdr"])
    for note in p.get("notes", []) or []:
        # Notes with report text in them are rendered above from structured fields; only
        # Mabillon's own fixed notes are shown as they are.
        if note.startswith(_OWN_NOTES):
            items.append(CoverageItem("info", "note", (_t(note),)))

    imported = sum(int(t.get("rows_imported") or 0) for t in tables)
    read = sum(int(t.get("rows_read") or 0) for t in tables)
    n_not = len(p.get("not_imported", []) or [])
    attention = [i for i in items if i.level == "attention"]
    rw, tw = ("records", "record types") if xml else ("rows", "tables")
    head = (
        f"Imported all {_n(read, rw)} read" if imported == read and read != 1
        else f"Imported {_n(imported, rw)} of {_n(read, rw)} read"
    )  # fmt: skip
    headline = (
        ("Unverified format. " if any(i.code == "format_unverified" for i in items) else "")
        + f"{head} from {_n(len(tables), tw)}"
        + (f"; {_n(n_not, 'parts')} of the report not imported" if n_not else "")
        + (
            f". {_n(len(attention), 'items')} to review."
            if attention
            else ". Nothing needs review."
        )
    )
    return CoverageSummary(
        source_id=c.source_id,
        file_name=str(p.get("file_name", "")),
        importer=c.importer,
        importer_version=c.importer_version,
        status="needs_review" if attention else "complete",
        headline=headline,
        items=tuple(items),
    )


_OWN_NOTES = ("Text comes from PDF layout", "Pages with no ruled table")


def _reason_words(reason: str) -> str:
    if reason == "category not imported" or reason.startswith("section '"):
        return "Mabillon does not import this category"
    if reason == "model type not recognised":
        return "Mabillon does not know this record type, so its records were not read"
    return reason


def where(item: CoverageItem, limit: int = 5) -> str:
    """'see Chats!3, Chats!7, ...': the first rows or tables to open, or '' when none."""
    if not item.locators:
        return ""
    more = ", ..." if len(item.locators) > limit else ""
    return f"see {', '.join(item.locators[:limit])}{more}"


def render(item: CoverageItem, quote: Callable[[str], str], escape: Callable[[str], str]) -> str:
    """One item as markup: text from the report through `quote` (the screen's and the
    report's q()), Mabillon's own words through `escape`, then where to look."""
    body = "".join(quote(t) if quoted else escape(t) for t, quoted in item.parts)
    loc = where(item)
    return body + (f" ({escape(loc)})" if loc else "")


def format_text(s: CoverageSummary, limit: int = 8) -> str:
    """Plain-text summary for the command line: the headline, then every item to review,
    then up to `limit` informational items."""
    lines = [f"Import coverage for {s.file_name} ({s.source_id}): {s.headline}"]
    for i in s.attention:
        loc = where(i)
        lines.append(f"  ! {i.plain}" + (f" [{loc}]" if loc else ""))
    for i in s.info[:limit]:
        lines.append(f"  - {i.plain}")
    if len(s.info) > limit:
        lines.append(f"  - and {len(s.info) - limit} more notes in the case's coverage record")
    return "\n".join(lines)
