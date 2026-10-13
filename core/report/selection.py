"""The selection audit in HTML, shared by the report and the review screen.

Each picked message is shown in its own conversation, as the phone showed it: the messages
exchanged with it that were not picked are marked, and so is anything another part of the
selection picked. Everything quoted (paragraph text, message text, senders, exhibit labels, file
names) goes through q(), so the forbidden-word check can tell it from the tool's own words.

Tiers: messages are observed; the phone's local time is derived from UTC and the phone's zone;
placements, exchanges and counts are derived by code. No model is involved, and nothing here sets
or changes a verdict.
"""

from __future__ import annotations

import html
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from core.report.letter import letter_body
from core.report.restore import METHOD_WORDS, context_table, highlighted, q
from core.restore.store import FIDELITY_WORDS
from core.review.status import ClaimState, claim_states
from core.selection.audit import (
    EXCHANGE_GAP,
    Mark,
    Passage,
    Row,
    SelectionAudit,
    Unit,
    gap_text,
    left_out_heading,
    lookup_note,
    selection_audit,
    summary,
)
from core.selection.picks import Lookup

CSS = """
.sel-unit { margin: 28px 0 36px; }
.sel-unit > h3 { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px;
  font-size: 18px; margin: 0 0 8px; }
.sel-unit > h3 .muted { font: 400 12px var(--mono); }
.sel-n { display: inline-flex; align-items: center; height: 20px; padding: 0 8px;
  border-radius: 999px; font: 500 11px var(--sans); white-space: nowrap;
  color: var(--con); background: var(--con-bg); border: 1px solid var(--con-line); }
.sel-n.none { color: var(--muted); background: var(--panel); border-color: var(--line); }
ul.sel-quotes { list-style: none; padding: 0; margin: 8px 0 12px; }
ul.sel-quotes li { margin: 0 0 8px; font-size: 13.5px; line-height: 1.5; }
.sel-claims { font-size: 13px; margin: 6px 0 10px; display: flex; flex-wrap: wrap; gap: 6px;
  align-items: center; }
.sel-claims .verdict { font-size: 12px; text-decoration: none; }
.sel-passage { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  margin: 14px 0; overflow: hidden; }
.sel-passage > .in { padding: 12px 16px; }
.sel-passage .where { font: 400 11px var(--mono); color: var(--muted); overflow-wrap: anywhere; }
.sel-passage ul.sum { margin: 6px 0 0; padding-left: 18px; font-size: 13.5px; }
.sel-passage ul.sum li { margin: 2px 0; }
.sel-passage > .foot { border-top: 1px solid var(--line); font-size: 13px; }
.sel-passage .sel-passage { margin: 10px 0 0; }
.sel-convo { display: flex; flex-direction: column; gap: 8px; padding: 14px 16px;
  background: #faf8f4; border-top: 1px solid var(--line); }
.bub { max-width: 76%; border: 1px solid var(--line); border-radius: 14px; padding: 7px 12px;
  background: #fff; align-self: flex-start; overflow-wrap: anywhere; }
.bub.out { align-self: flex-end; background: #e9eef5; border-color: #d3dceb; }
.bub.pick { border: 1.5px solid #c9a24a; background: #fbf1cf;
  box-shadow: 0 0 0 3px rgb(201 162 74 / 0.18); }
.bub.left { border: 1.5px dashed var(--con); }
.bub.dim { opacity: 0.62; }
.bub .who2 { font-size: 11.5px; color: var(--muted); }
.bub .body { font-size: 14.5px; }
.bub .att { font-size: 12px; color: var(--muted); }
.bub .t { font: 400 10.5px var(--mono); color: var(--muted); margin-top: 3px; display: flex;
  flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 4px 6px; }
.tag { font: 600 9.5px var(--mono); letter-spacing: 0.08em; text-transform: uppercase;
  border-radius: 3px; padding: 1px 5px; }
.tag.pick { color: #6b4d0c; background: #f0dca3; }
.tag.left { color: var(--con); background: var(--con-bg); }
.tag.else { color: var(--accent); background: rgb(29 53 87 / 0.08); }
.tag.maybe { color: var(--unp); background: var(--unp-bg); }
.divider { align-self: center; font: 400 10.5px var(--mono); color: var(--muted);
  border: 1px dashed var(--line-strong); border-radius: 999px; padding: 1px 10px;
  text-align: center; }
@media (max-width: 600px) { .bub { max-width: 92%; } .sel-convo { padding: 12px 10px; } }
@media print { .sel-passage { break-inside: avoid; } }
"""


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


GAP_WORDS = (
    "an hour"
    if EXCHANGE_GAP.total_seconds() == 3600
    else gap_text(EXCHANGE_GAP.total_seconds()).replace(" h", " hours")
)
_EXHIBIT_RE = re.compile(r"\bex(hibit)?\b|\bgx\b", re.IGNORECASE)


def exhibit_name(label: str, start: bool = False) -> str:
    """An exhibit's label as pasted (cited), with the word exhibit when the label lacks it."""
    if _EXHIBIT_RE.search(label):
        return q(label)
    return f"{'Exhibit' if start else 'exhibit'} {q(label)}"


@dataclass(frozen=True)
class Links:
    """Where the review screen links. The report has no server, so it links within the page."""

    context: Callable[[str], str] | None = None  # message id -> its whole conversation
    claim: Callable[[str], str] | None = None  # claim id -> the claim page


def anchor(unit_id: str) -> str:
    """The page anchor of one unit (a paragraph, an exhibit, or the tags)."""
    return f"sel-{unit_id}"


# ---------------------------------------------------------------- totals


@dataclass(frozen=True)
class Totals:
    picked: int  # messages picked, copies on other sources not counted again
    exchanges: int
    left_out: int  # distinct messages left out across those exchanges
    between: int  # of them, between two picked messages


def totals(units: list[Unit]) -> Totals:
    passages = [p for u in units for p in u.primary]
    picked = {r for p in passages for r in p.picked_ids}
    left = {r for p in passages for r in p.left_out_ids}
    between = {r for p in passages for r in p.between_ids}
    return Totals(len(picked), len(passages), len(left), len(between))


def _n(n: int, word: str, plural: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else plural or word + 's'}"


def _glance(audit: SelectionAudit) -> list[str]:
    """The opening list: what was checked and what was found, in the tool's own words."""
    out: list[str] = []
    docs = audit.of("document")
    lks = [lk for u in docs for lk in u.lookups]
    if not audit.paragraphs:
        out.append("No government document is imported, so there are no quotes to place.")
    elif not docs:
        out.append(
            "The government document puts no words in quotation marks, so no quote is placed."
        )
    else:
        placed = sum(1 for lk in lks if lk.places)
        skipped = sum(1 for lk in lks if lk.skipped)
        missing = sum(1 for lk in lks if not lk.skipped and not lk.found)
        unplaced = len(lks) - placed - skipped - missing
        line = (
            f"The government document puts {_n(len(lks), 'set')} of words in quotation marks, "
            f"in {_n(len(docs), 'paragraph')}. {placed:,} {'is' if placed == 1 else 'are'} "
            "placed on a message"
        )
        rest = [f"{missing:,} not found"] if missing else []
        rest += [f"{unplaced:,} found but not placed"] if unplaced else []
        rest += [f"{skipped:,} not looked up (names, single words, redactions)"] if skipped else []
        out.append(line + (f"; {', '.join(rest)}." if rest else "."))
        t = totals(docs)
        if t.exchanges:
            out.append(
                f"<strong>In the {_n(t.exchanges, 'exchange')} those quotes come from, "
                f"{_n(t.left_out, 'message')} {'is' if t.left_out == 1 else 'are'} not quoted "
                "anywhere in the document"
                + (f", {t.between:,} of them between two quoted messages" if t.between else "")
                + ".</strong>"
            )
    for u in audit.of("exhibit"):
        t = totals([u])
        out.append(
            f"{exhibit_name(u.label, True)}: {u.placed:,} of "
            f"{_n(len(u.lookups), 'quoted message')} "
            "placed"
            + (
                f"; {_n(t.left_out, 'message')} in their exchanges "
                f"{'is' if t.left_out == 1 else 'are'} not in the exhibit."
                if t.exchanges
                else "."
            )
        )
    for label in audit.unsearched:
        out.append(
            f"{exhibit_name(label, True)} has not been searched on the Exhibits screen yet, so it "
            "is not checked here."
        )
    tagged = len(audit.tagged_ids)
    if tagged:
        per = ", ".join(f"{q(s.file_name)} {s.tagged:,}" for s in audit.sources if s.tagged)
        line = (
            f"The examiner tagged {_n(tagged, 'message')} ({per}); "
            f"{audit.tagged_quoted:,} of them {'is' if audit.tagged_quoted == 1 else 'are'} quoted "
            "in the document."
        )
        tags = next(iter(audit.of("tags")), None)
        if tags and tags.passages:
            line += " Tagged messages the document does not quote are shown below."
        out.append(line)
    else:
        out.append("No message in the sources carries an examiner tag.")
    return out


def _coverage(audit: SelectionAudit) -> str:
    if not audit.sources:
        return "<p class='muted'>No evidence source is imported.</p>"
    partial = [s for s in audit.sources if s.fidelity != "full_extraction"]
    if not partial:
        return (
            "<p class='muted'>Every evidence source is recorded as a full extraction. Only "
            "messages are checked here, not calls, files or other records.</p>"
        )
    names = ", ".join(
        f"{q(s.file_name)} ({e(FIDELITY_WORDS.get(s.fidelity, s.fidelity))})" for s in partial
    )
    return (
        f"<div class='banner'><strong>What this can show.</strong> Not recorded as a full "
        f"extraction: {names}. A message such a source leaves out is not in the case, so it "
        "cannot be shown or counted here: the counts cover what was supplied. A draft request "
        "for the full extraction is below.</div>"
    )


# ---------------------------------------------------------------- one message


def _mark_text(m: Mark) -> tuple[str, str]:
    """(css class, html) for a mark from another part of the selection."""
    u = m.unit
    if u.kind == "tags":
        return "else", "Examiner tag"
    if u.kind == "document":
        return (
            ("else", f"Quoted in {e(u.label)}")
            if m.placed
            else ("maybe", f"May be quoted in {e(u.label)}")
        )
    return (
        ("else", f"In {exhibit_name(u.label)}")
        if m.placed
        else ("maybe", f"May be in {exhibit_name(u.label)}")
    )


def mark_html(m: Mark) -> str:
    """A mark as the chip the conversation view shows."""
    cls, text = _mark_text(m)
    return f"<span class='tag {cls}'>{text}</span>"


_PICK = {"document": "Quoted in {label}", "exhibit": "In this exhibit", "tags": "Tagged"}
_LEFT = {"document": "Not quoted", "exhibit": "Not in this exhibit", "tags": "Not tagged"}


def _bubble(unit: Unit, row: Row, marks: list[Mark]) -> str:
    ln = row.line
    assert ln is not None  # noqa: S101 - count rows are drawn as dividers
    tags: list[tuple[str, str]] = []
    cls = ["bub"]
    if ln.direction == "outgoing":
        cls.append("out")
    if row.role == "picked":
        cls.append("pick")
        tags.append(("pick", _PICK[unit.kind].format(label=e(unit.label))))
    elif row.left_out:
        cls.append("left")
        tags.append(("left", _LEFT[unit.kind]))
    elif row.role in ("earlier", "later"):
        cls.append("dim")
    for m in marks:
        if m.unit.id == unit.id and m.placed and row.role == "picked":
            continue  # the unit's own pick, tagged above
        tag = _mark_text(m)
        if tag not in tags:
            tags.append(tag)
    body = highlighted(ln.body, row.spans) if row.spans else q(ln.body)
    if not ln.body.strip():
        body = "<span class='muted'>(no text)</span>"
    shown = f" (shown as {q(ln.shown_as)})" if ln.shown_as else ""
    files = "".join(f"<div class='att'>Attachment: {q(a)}</div>" for a in row.attachments)
    chips = "".join(f"<span class='tag {c}'>{t}</span>" for c, t in tags)
    return (
        f"<div class='{' '.join(cls)}'>"
        f"<div class='who2'>{q(ln.sender)}{shown} · {e(ln.direction)} · observed</div>"
        f"<div class='body'>{body}</div>{files}"
        f"<div class='t'>{chips}<span>{e(ln.local)}</span>"
        f"<span>{e(ln.source_id)} {e(ln.locator)}</span></div></div>"
    )


_MORE = {
    "before": "{n} more of this exchange before, not shown",
    "between": "{n} more in between, not shown",
    "after": "{n} more of this exchange after, not shown",
}


def _convo(unit: Unit, p: Passage, marks: dict[str, list[Mark]]) -> str:
    """The passage as a conversation. Dividers mark a pause longer than an exchange allows,
    where the exchange starts and ends, and runs of messages not shown."""
    out = ["<div class='sel-convo'>"]
    was_inside: bool | None = None
    for row in p.rows:
        inside = row.role not in ("earlier", "later")
        notes = []
        if row.line is not None and row.gap_s is not None:
            if row.gap_s > EXCHANGE_GAP.total_seconds():
                notes.append(f"{gap_text(row.gap_s)} later")
        if was_inside is None and not inside:
            notes.append("before this exchange")
        elif was_inside is not None and inside != was_inside:
            notes.append("this exchange starts" if inside else "after this exchange")
        if notes:
            out.append(f"<div class='divider'>{e(' · '.join(notes))}</div>")
        was_inside = inside
        if row.line is None:
            more = _MORE.get(row.role, "{n} not shown").format(n=_n(row.more, "message"))
            out.append(f"<div class='divider'>{more}</div>")
            continue
        out.append(_bubble(unit, row, marks.get(row.line.record_id, [])))
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------- a passage


def _where(p: Passage) -> str:
    t = p.thread
    return (
        f"{e(t.app)} conversation {q(t.title or '(untitled)')} · {q(t.device)} · "
        f"{q(t.file_name)} ({e(FIDELITY_WORDS.get(p.fidelity, p.fidelity))}) · tier derived"
    )


def _passage_html(
    unit: Unit,
    p: Passage,
    copies: list[Passage],
    by_id: dict[str, Passage],
    marks: dict[str, list[Mark]],
    links: Links,
) -> str:
    heading = left_out_heading(unit.kind)
    items = "".join(
        f"<li>{'<strong>' + e(s) + '</strong>' if s.startswith(heading) else e(s)}</li>"
        for s in summary(unit, p)
    )
    out = [f"<article class='sel-passage' id='{e(p.id)}'><div class='in'>"]
    if p.copy_of is not None:
        first = by_id[p.copy_of]
        out.append(
            f"<p>The quoted messages are also on {q(first.thread.file_name)}, but this exchange "
            f"is not the same there: it holds {_n(p.only_here, 'message')} that the exchange "
            f"there does not, and lacks {p.only_there:,} that it holds.</p>"
        )
    out.append(f"<div class='where'>{_where(p)}</div><ul class='sum'>{items}</ul></div>")
    out.append(_convo(unit, p, marks))
    foot: list[str] = []
    if p.nearby:
        total = len(p.nearby) + p.nearby_more
        count = f"{len(p.nearby)} of {total:,}" if p.nearby_more else f"{total:,}"
        foot.append(
            f"<details><summary>Other conversations in this source within {GAP_WORDS} of this "
            f"exchange: {count} "
            f"message{'' if total == 1 else 's'}</summary>{context_table(p.nearby)}</details>"
        )
    for c in copies:
        if c.same_as_copy:
            foot.append(
                f"<p class='muted'>The same exchange is also on {q(c.thread.file_name)} "
                f"({e(c.thread.app)} conversation {q(c.thread.title or '(untitled)')}): the same "
                f"{_n(c.exchange, 'message')}, so it is not shown again.</p>"
            )
        else:
            foot.append(_passage_html(unit, c, [], by_id, marks, links))
    if links.context is not None:
        foot.append(
            f"<p><a href='{e(links.context(p.picked_ids[0]))}'>Open in the conversation</a></p>"
        )
    if foot:
        out.append(f"<div class='in foot'>{''.join(foot)}</div>")
    out.append("</article>")
    return "".join(out)


def _passages(unit: Unit, marks: dict[str, list[Mark]], links: Links) -> str:
    by_id = {p.id: p for p in unit.passages}
    copies: dict[str, list[Passage]] = {}
    for p in unit.passages:
        if p.copy_of is not None:
            copies.setdefault(p.copy_of, []).append(p)
    return "".join(
        _passage_html(unit, p, copies.get(p.id, []), by_id, marks, links) for p in unit.primary
    )


# ---------------------------------------------------------------- a unit


def _lookup_html(lk: Lookup) -> str:
    how = ""
    if lk.places and lk.places[0].method is not None:
        how = f" {e(METHOD_WORDS[lk.places[0].method])}."
    return f"<li><span class='piece'>{q(lk.text)}</span> {e(lookup_note(lk))}{how}</li>"


def _claims_html(states: list[ClaimState], links: Links) -> str:
    if not states:
        return ""
    pills = []
    for st in states:
        css = f"{st.css} v-nt" if st.untested else st.css
        href = links.claim(st.claim.id) if links.claim else f"#{st.claim.id}"
        pills.append(f"<a class='verdict {css}' href='{e(href)}'>{e(st.name)}: {e(st.label)}</a>")
    return (
        "<div class='sel-claims'><span class='muted'>Claims from this paragraph:</span>"
        + "".join(pills)
        + "</div>"
    )


def _badge(unit: Unit) -> str:
    t = totals([unit])
    if not t.exchanges:
        return ""
    word = {"document": "not quoted", "exhibit": "not in the exhibit", "tags": "not tagged"}
    return (
        f"<span class='sel-n{'' if t.left_out else ' none'}'>{t.left_out:,} "
        f"{word[unit.kind]}</span>"
    )


def _paragraph_html(
    unit: Unit, marks: dict[str, list[Mark]], links: Links, claims: list[ClaimState]
) -> str:
    where = f"page {unit.page}" + (f" of {q(unit.title)}" if unit.title else "")
    spans = tuple(lk.span for lk in unit.lookups if lk.span is not None)
    text = highlighted(unit.text or "", spans) if spans else q(unit.text or "")
    out = [
        f"<section class='sel-unit' id='{e(anchor(unit.id))}'>"
        f"<h3>{e(unit.label)} <span class='muted'>{where}</span>{_badge(unit)}</h3>",
        f"<blockquote>{text}</blockquote>",
    ]
    if unit.ocr:
        out.append(
            "<p class='muted'>This paragraph's text was read by OCR, so its quoted words may "
            "differ from the printed page.</p>"
        )
    out.append(_claims_html(claims, links))
    out.append("<ul class='sel-quotes'>" + "".join(map(_lookup_html, unit.lookups)) + "</ul>")
    out.append(_passages(unit, marks, links))
    out.append("</section>")
    return "".join(out)


def _exhibit_html(unit: Unit, marks: dict[str, list[Mark]], links: Links) -> str:
    out = [
        f"<section class='sel-unit' id='{e(anchor(unit.id))}'>"
        f"<h3>{exhibit_name(unit.label, True)}{_badge(unit)}</h3>"
        "<ul class='sel-quotes'>"
        + "".join(
            f"<li class='muted'>Quoted message {lk.seq}:</li>{_lookup_html(lk)}"
            for lk in unit.lookups
        )
        + "</ul>",
        _passages(unit, marks, links),
        "</section>",
    ]
    return "".join(out)


def _tags_html(unit: Unit, marks: dict[str, list[Mark]], links: Links) -> str:
    return (
        f"<section class='sel-unit' id='{e(anchor(unit.id))}'><h3>Examiner tags{_badge(unit)}</h3>"
        "<p class='muted'>Messages a report marks with an examiner tag that the document does "
        "not quote, each in its exchange.</p>" + _passages(unit, marks, links) + "</section>"
    )


def _unplaced_html(units: list[Unit]) -> str:
    rows = [
        f"<tr><td>{e(u.label)}</td><td>{q(lk.text)}</td><td>{e(lookup_note(lk))}</td></tr>"
        for u in units
        for lk in u.lookups
    ]
    if not rows:
        return ""
    return (
        "<h4>Quotes not placed on a message</h4><table><thead><tr><th>Paragraph</th>"
        "<th>Quoted words</th><th>Why</th></tr></thead>" + "".join(rows) + "</table>"
    )


# ---------------------------------------------------------------- the whole audit


INTRO = (
    "<p>What the government picked out of the phone evidence, each piece shown in its own "
    "conversation with the messages exchanged around it that were not picked: the words the "
    "document puts in quotation marks, the messages each exhibit quotes, and the messages the "
    "examiner tagged. Code places every quote and counts every message; no model is involved. "
    "Nothing here changes a claim's verdict. It is for the expert to weigh.</p>"
    "<p class='muted'>An exchange is a run of messages in one conversation with no pause longer "
    f"than {GAP_WORDS}. Quoted means put in quotation marks; a "
    "paragraph may still describe a message it does not quote. A quote is placed on a message "
    "only when code can tell which message it is. A message counts as not quoted when no quote "
    "of the document was found in it, so a quote too far from the message's words to be found "
    "leaves that message counted as not quoted: check the quotes listed as not found. Messages "
    "are observed, as the source recorded them. Times are the phone's local time, derived from "
    "UTC and the phone's time zone. Placements and counts are derived by code.</p>"
)


def selection_html(
    audit: SelectionAudit, links: Links | None = None, claims: list[ClaimState] | None = None
) -> str:
    """Everything under the section heading: what was checked, the totals, and each unit."""
    links = links or Links()
    marks = audit.marks()
    by_para: dict[str, list[ClaimState]] = {}
    for st in claims or []:
        by_para.setdefault(st.claim.paragraph_id, []).append(st)
    out = [INTRO, _coverage(audit)]
    out.append("<ul>" + "".join(f"<li>{s}</li>" for s in _glance(audit)) + "</ul>")
    docs = audit.of("document")
    shown = [u for u in docs if u.passages]
    if docs:
        out.append("<h3 class='eyebrow'>Government document</h3>")
        out += [_paragraph_html(u, marks, links, by_para.get(u.id, [])) for u in shown]
        out.append(_unplaced_html([u for u in docs if not u.passages]))
    exhibits = [u for u in audit.of("exhibit") if u.passages or u.lookups]
    if exhibits:
        out.append("<h3 class='eyebrow'>Exhibits</h3>")
        out += [_exhibit_html(u, marks, links) for u in exhibits]
    out += [_tags_html(u, marks, links) for u in audit.of("tags") if u.passages]
    return "".join(out)


def selection_section(conn: sqlite3.Connection, states: list[ClaimState] | None = None) -> str:
    """The report's Selection audit section, ending with the draft request."""
    audit = selection_audit(conn)
    states = claim_states(conn) if states is None else states
    return (
        "<h2 id='selection-audit'>Selection audit</h2>"
        + selection_html(audit, claims=states)
        + "<h3 id='full-extraction-request'>Request for the full extraction</h3>"
        + letter_body(conn)
    )


def claim_note(unit: Unit, href: str) -> str | None:
    """One line for a claim page: what the selection audit found around its paragraph's quotes."""
    t = totals([unit])
    if not t.exchanges:
        return None
    found = (
        f"{_n(t.left_out, 'other message')} in "
        f"{'that exchange' if t.exchanges == 1 else 'those exchanges'} "
        f"{'is' if t.left_out == 1 else 'are'} not quoted anywhere in the document"
        + (f", {t.between:,} of them between quoted messages" if t.between else "")
        if t.left_out
        else "every message in "
        + ("that exchange" if t.exchanges == 1 else "those exchanges")
        + " is quoted in the document"
    )
    return (
        f"<p class='caution'>Selection audit: {e(unit.label)} quotes "
        f"{_n(t.picked, 'message')} from {_n(t.exchanges, 'exchange')}; {found}. "
        f"<a href='{e(href)}'>See them in context</a>. This does not change the verdict.</p>"
    )
