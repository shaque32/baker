"""Selection audit on synthetic case01: what the document quotes, exhibits and examiner tags pick,
and the messages exchanged around those picks that were not picked.

Where a test needs a situation case01 does not have (two messages holding the same words, a copy
that differs between phones, an untimed message), it edits its own copy of the synthetic case.
All data is synthetic.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import encryption
from core.audit.context import context_ids
from core.audit.invariants import check_report_text
from core.contracts import ExcerptSplit
from core.db import connect
from core.report.html import render_report
from core.report.selection import Links, Totals, claim_note, selection_html, totals
from core.restore.store import add_exhibit
from core.review.status import claim_states
from core.selection import audit as selection_module
from core.selection.audit import (
    EXCHANGE_GAP,
    Passage,
    Quiet,
    SelectionAudit,
    Unit,
    _Thread,
    gap_text,
    lookup_note,
    quiet,
    selection_audit,
    summary,
)
from core.selection.picks import paragraph_quotes, skip_reason
from core.timeline.gaps import find_gaps
from core.timeline.records import CaseRecords
from core.timeline.settings import Settings
from eval import run_pipeline
from ui.app import App, Request

EXPERT = "expert:Test Expert"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
HOST = {"host": "127.0.0.1:8765"}
EXHIBIT = """Telegram chat, Item 1
3/12/2026 4:15 PM PETROV: "need 2 more by friday"
3/12/2026 8:11 PM @northstar: "The package will be at Marcs."
3/5/2026 2:31 AM PETROV: its done
PETROV: got the money ... get it
REYES: we never talked about this
"""


def M(n: int, item: int = 1) -> str:  # noqa: N802 - reads like the record ids it builds
    return f"msg:item{item}:Chats!{n}"


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("selection") / "case01.db"
    run_pipeline.build_case("case01", path).close()
    return path


@pytest.fixture
def db(built, tmp_path) -> Path:
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    return copy


@pytest.fixture
def conn(db) -> sqlite3.Connection:
    c = connect(db)
    yield c
    c.close()


def _unit(audit: SelectionAudit, label: str) -> Unit:
    return next(u for u in audit.units if u.label == label)


def _only(unit: Unit) -> Passage:
    assert len(unit.primary) == 1, [p.picked_ids for p in unit.primary]
    return unit.primary[0]


def _roles(p: Passage) -> list[tuple[str, str | None]]:
    return [(r.role, r.line.record_id if r.line else None) for r in p.rows]


def _reword(conn: sqlite3.Connection, label: str, old: str, new: str) -> None:
    """Change words of one paragraph of the synthetic affidavit."""
    with conn:
        text = conn.execute(
            "SELECT text FROM govdoc_paragraphs WHERE label = ?", (label,)
        ).fetchone()[0]
        assert old in text
        conn.execute(
            "UPDATE govdoc_paragraphs SET text = ? WHERE label = ?", (text.replace(old, new), label)
        )


def _copy_message(conn: sqlite3.Connection, src: str, new_id: str, **changes: object) -> None:
    """A synthetic message made from another one, for situations case01 does not have."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    row = dict(
        zip(
            cols,
            conn.execute("SELECT * FROM messages WHERE id = ?", (src,)).fetchone(),
            strict=True,
        )
    )
    row.update(id=new_id, locator=new_id.split(":", 2)[2], bookmarked=0, **changes)
    with conn:
        conn.execute(
            f"INSERT INTO messages ({','.join(row)}) VALUES ({','.join('?' * len(row))})",  # noqa: S608
            list(row.values()),
        )


# ---------------------------------------------------------------- the document's quotes


def test_quotes_are_read_from_quotation_marks_with_line_breaks_as_spaces() -> None:
    text = 'He wrote "need 2\nmore by friday" and “the package”.'
    assert [w for _, _, w in paragraph_quotes(text)] == ["need 2 more by friday", "the package"]
    names = {"marc garage", "alex"}
    assert skip_reason("Marc  Garage", names) == "a name in the case, not a quoted message"
    assert skip_reason("@Alex", names) == "a name in the case, not a quoted message"
    assert skip_reason("tickets", names) == "a single word, too short to place a message"
    assert skip_reason("got the tickets", names) is None


def test_paragraph_6_left_out_the_two_replies_between_its_quotes(conn) -> None:
    unit = _unit(selection_audit(conn), "¶6")
    assert [lk.places[0].record_id for lk in unit.lookups] == [M(948), M(951)]
    p = _only(unit)
    assert p.picked_ids == (M(948), M(951))
    assert (p.exchange, p.before, p.between, p.after) == (4, 0, 2, 0)
    assert set(p.between_ids) == {M(949), M(950)} == set(p.left_out_ids)
    roles = _roles(p)
    assert roles[3:7] == [("picked", M(948)), ("between", M(949)), ("between", M(950)),
                          ("picked", M(951))]  # fmt: skip
    assert [r for r, _ in roles[:3]] == ["earlier"] * 3  # the exchange opens with a quote
    later = [r for r in p.rows if r.role == "later"]
    assert later[0].line.record_id == M(952) and later[0].elsewhere  # ¶9 quotes it
    lines = summary(unit, p)
    assert lines[0].startswith("¶6 quotes 2 of the 4 messages in this exchange (2026-03-12 20:03")
    assert "Not quoted anywhere in the document: 2 between the quoted messages." in lines
    assert "The previous message in this thread is 2 days 8 h earlier." in lines
    assert "The next message in this thread is 2 days 1 h later." in lines


def test_paragraph_15_quotes_part_of_a_message_and_leaves_out_the_rest_of_the_exchange(
    conn,
) -> None:
    unit = _unit(selection_audit(conn), "¶15")
    assert (
        lookup_note(unit.lookups[0]) == "Not looked up: a name in the case, not a quoted message."
    )
    p = _only(unit)
    assert p.picked_ids == (M(670),)
    assert (p.exchange, p.before, p.between, p.after) == (6, 1, 0, 4)
    assert p.partial == 1 and p.other_senders == 3
    picked = next(r for r in p.rows if r.role == "picked")
    assert picked.line.body[slice(*picked.spans[0])] == "got the tickets"
    attach = next(r for r in p.rows if r.line and r.line.record_id == M(672))
    assert attach.attachments and attach.left_out
    lines = summary(unit, p)
    assert "Not quoted anywhere in the document: 1 just before, 4 just after." in lines
    assert (
        "3 of the 5 not quoted are from someone other than the sender of the quoted message."
        in lines
    )
    assert any(s.startswith("¶15 quotes only part of 1 message") for s in lines)


def test_the_same_message_on_both_phones_is_folded_into_one_passage(conn) -> None:
    audit = selection_audit(conn)
    for label in ("¶8", "¶10", "¶12"):
        unit = _unit(audit, label)
        assert len(unit.lookups[0].places) == 2, label  # item1 and item2
        assert "read as copies of one message" in lookup_note(unit.lookups[0])
        first, copy = unit.passages
        assert first.thread.source_id == "item1" and copy.thread.source_id == "item2"
        assert copy.copy_of == first.id and copy.same_as_copy, label
    p12 = _unit(audit, "¶12").primary[0]
    earlier = [r.line.body for r in p12.rows if r.role == "earlier"]
    assert any("its ilya btw" in b for b in earlier)  # shown although 4 h 34 min earlier
    assert "The previous message in this thread is 4 h 34 min earlier." in summary(
        _unit(audit, "¶12"), p12
    )
    assert totals(audit.of("document"), audit.same).picked == 7  # copies are not counted twice


def test_a_copy_whose_exchange_differs_is_shown_with_the_difference(conn) -> None:
    _copy_message(conn, M(904, 2), M(9001, 2), body="on my way", ts_utc="2026-03-05T02:32:00Z")
    unit = _unit(selection_audit(conn), "¶8")
    first, copy = unit.passages
    assert copy.copy_of == first.id and not copy.same_as_copy
    assert (copy.only_here, copy.only_there) == (1, 0)
    page = selection_html(selection_audit(conn))
    assert "this exchange is not the same there" in page


def test_names_and_redactions_are_not_looked_up(conn) -> None:
    audit = selection_audit(conn)
    for label in ("¶4", "¶7", "¶13", "¶14"):
        unit = _unit(audit, label)
        assert not unit.passages and all(lk.skipped for lk in unit.lookups), label
    assert _unit(audit, "¶13").lookups[0].skipped == "no letters or digits to look up"


def test_a_message_that_is_just_a_quoted_single_word_is_never_counted_as_left_out(conn) -> None:
    p12 = _unit(selection_audit(conn), "¶12").primary[0]
    assert (p12.after, p12.maybe) == (1, 0)  # 'tmrw', the reply
    with conn:
        conn.execute(
            "UPDATE govdoc_paragraphs SET text = text || ' REYES answered \"tmrw\".'"
            " WHERE label = '12'"
        )
    unit = _unit(selection_audit(conn), "¶12")
    word = unit.lookups[-1]
    assert word.skipped == "a single word, too short to place a message" and not word.places
    assert len(word.hits) == 2  # the reply on both phones
    assert lookup_note(word).endswith("2 messages are just these words, so they are marked as "
                                      "may be quoted.")  # fmt: skip
    p12 = unit.primary[0]
    assert (p12.after, p12.maybe) == (0, 1)


def test_words_in_two_different_messages_are_not_placed_and_not_counted_as_left_out(conn) -> None:
    alex = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (M(670),)).fetchone()[0]
    _copy_message(conn, M(948), M(9002), thread_id=alex, ts_utc="2026-03-26T12:00:00Z")
    unit = _unit(selection_audit(conn), "¶6")
    first = unit.lookups[0]
    assert first.found == 2 and not first.places
    assert lookup_note(first).startswith("Found in 2 messages. Code cannot confirm")
    p = _only(unit)
    assert p.picked_ids == (M(951),)
    assert (p.before, p.between, p.after, p.maybe) == (2, 0, 0, 1)
    assert next(r for r in p.rows if r.line and r.line.record_id == M(948)).maybe
    assert any(
        s.startswith("1 more message in this exchange may be quoted") for s in summary(unit, p)
    )


def test_a_quote_found_nowhere_says_what_that_does_not_show(conn) -> None:
    with conn:
        conn.execute(
            "UPDATE govdoc_paragraphs SET text = text || ' He also wrote \"see you at the pier\".'"
            " WHERE label = '9'"
        )
    unit = _unit(selection_audit(conn), "¶9")
    note = lookup_note(unit.lookups[-1])
    assert note == (
        "Not found in the messages searched. This does not show that the message was never sent "
        "or received."
    )


def test_a_quote_is_looked_for_with_every_method_before_it_is_placed(conn) -> None:
    """As printed, the quote is in no message. Without its comma it is one message character for
    character, and ¶6's message with letter case aside. Stopping at the first method that finds
    something would place it on the wrong one and count ¶6's message as not quoted."""
    _reword(conn, "6", '"need 2 more by friday"', '"Need 2 more by friday,"')
    alex = conn.execute("SELECT thread_id FROM messages WHERE id = ?", (M(670),)).fetchone()[0]
    _copy_message(
        conn, M(948), M(9004), thread_id=alex, body="Need 2 more by friday",
        ts_utc="2026-03-26T12:00:00Z",
    )  # fmt: skip
    unit = _unit(selection_audit(conn), "¶6")
    first = unit.lookups[0]
    assert (first.found, first.loose, first.places) == (2, 0, ())
    assert first.hits == tuple(sorted((M(948), M(9004))))
    assert lookup_note(first).startswith("Found in 2 messages. Code cannot confirm")
    p = _only(unit)
    assert p.picked_ids == (M(951),)
    assert (p.before, p.maybe) == (2, 1)  # 949 and 950; 948 may be quoted
    assert next(r for r in p.rows if r.line and r.line.record_id == M(948)).maybe


def test_the_same_words_with_other_punctuation_are_never_counted_as_left_out(conn) -> None:
    _reword(conn, "6", '"need 2 more by friday"', '"need 2 more, by friday"')
    unit = _unit(selection_audit(conn), "¶6")
    first = unit.lookups[0]
    assert (first.found, first.loose, first.places, first.hits) == (0, 1, (), (M(948),))
    assert lookup_note(first) == (
        "Not found as printed. The same words with different punctuation are in 1 message, so it "
        "is not placed and it is marked as may be quoted."
    )
    p = _only(unit)
    assert p.picked_ids == (M(951),) and (p.before, p.maybe) == (2, 1)
    # Found as printed in one message, and with other punctuation in another: not placed.
    _reword(conn, "6", '"need 2 more, by friday"', '"need 2 more by friday"')
    _copy_message(
        conn, M(948), M(9005), body="need 2 more... by friday!", ts_utc="2026-03-26T12:00:00Z"
    )
    unit = _unit(selection_audit(conn), "¶6")
    first = unit.lookups[0]
    assert (first.found, first.loose, first.places) == (1, 1, ())
    assert lookup_note(first) == (
        "Found in 1 message, and the same words with different punctuation in 1 more message. "
        "Code does not decide which one is meant. Not placed."
    )
    assert _only(unit).maybe == 1
    for lk in unit.lookups:
        check_report_text(lookup_note(lk))


def test_a_quote_with_no_letters_keeps_the_messages_that_are_just_those_marks(conn) -> None:
    _reword(conn, "9", '"move it\ntonight".', '"move it\ntonight". REYES answered "?" and "👍".')
    _copy_message(conn, M(949), M(9006), body=" ? ", ts_utc="2026-03-13T00:05:00Z")
    _copy_message(conn, M(950), M(9007), body="👍🏽", ts_utc="2026-03-13T00:10:30Z")
    audit = selection_audit(conn)
    marks, thumb = _unit(audit, "¶9").lookups[-2:]
    assert (marks.text, thumb.text) == ("?", "👍")
    for lk, rid in ((marks, M(9006)), (thumb, M(9007))):
        assert lk.skipped == "no letters or digits to look up" and not lk.places
        assert rid in lk.hits
        assert "just these characters" in lookup_note(lk)
        check_report_text(lookup_note(lk))
    p = _only(_unit(audit, "¶6"))
    assert (p.between, p.maybe) == (2, 2)  # 949 and 950 not quoted; the two replies may be


# ---------------------------------------------------------------- paragraphs, documents, copies


def test_a_paragraph_printed_across_a_page_break_is_one_paragraph(db, conn) -> None:
    """The importer stores such a paragraph once per page. Its parts are read as one text, so a
    quote running across the break is still found, and a claim on either part finds them."""
    pid, page, para_no, start, text = conn.execute(
        "SELECT id, page, para_no, char_start, text FROM govdoc_paragraphs WHERE label = '6'"
    ).fetchone()
    k = text.index("be at marcs")
    second = pid.rsplit(":", 2)[0] + f":{page + 1}:{para_no}"
    with conn:
        conn.execute(
            "UPDATE govdoc_paragraphs SET text = ?, char_end = ? WHERE id = ?",
            (text[:k].rstrip(), start + k, pid),
        )
        conn.execute(
            "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
            " char_end, text, ocr) SELECT ?, govdoc_id, page + 1, para_no, label, 0, ?, ?, ocr"
            " FROM govdoc_paragraphs WHERE id = ?",
            (second, len(text) - k, text[k:], pid),
        )
        cid = conn.execute(
            "SELECT id FROM claims WHERE paragraph_id = ? ORDER BY id", (pid,)
        ).fetchone()[0]
        conn.execute("UPDATE claims SET paragraph_id = ? WHERE id = ?", (second, cid))
    audit = selection_audit(conn)
    unit = _unit(audit, "¶6")
    assert unit.ids == (pid, second) and (unit.page, unit.last_page) == (page, page + 1)
    assert [lk.text for lk in unit.lookups] == [
        "need 2 more by friday",
        "the package will be at marcs",
    ]
    assert [lk.places[0].record_id for lk in unit.lookups] == [M(948), M(951)]
    assert _only(unit).between == 2
    html = selection_html(audit, claims=claim_states(conn))
    assert f"pages {page}–{page + 1}" in html
    assert f"href='#{cid}'" in html  # the claim on the second part is listed with the paragraph
    assert [u.label for u in selection_audit(conn, paragraph_id=second).units] == ["¶6"]
    claim = _app(db).handle(Request("GET", "/claim", {"id": cid}, dict(HOST)))
    assert "Selection audit: ¶6 quotes 2 messages from 1 exchange" in claim.text


def test_two_quotes_sharing_words_mark_the_message_once(conn) -> None:
    _reword(conn, "12", 'come get it".', 'come get it". By "come get it" he meant the bag.')
    audit = selection_audit(conn)
    unit = _unit(audit, "¶12")
    assert [len(lk.places) for lk in unit.lookups] == [2, 2]  # on both phones
    picked = next(r for r in unit.primary[0].rows if r.role == "picked")
    assert picked.spans == ((0, len(picked.line.body)),)
    assert "</mark><mark>" not in selection_html(audit)  # no words shown twice


def test_each_government_document_is_counted_on_its_own(conn) -> None:
    """A message counts as quoted only when a paragraph of the same document quotes it, so a
    second document gets its own counts, named by its title."""
    affidavit = conn.execute("SELECT id FROM govdocs").fetchone()[0]
    alone = selection_audit(conn)
    before = totals(alone.of("document"), alone.same)
    text = '1. REYES answered "friday hard. saturday".'
    with conn:
        conn.execute(
            "INSERT INTO govdocs (id, source_id, title, doc_kind) SELECT 'govdoc:test2',"
            " source_id, 'POLICE REPORT (SYNTHETIC)', 'police_report' FROM govdocs"
        )
        conn.execute(
            "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
            " char_end, text) VALUES ('para:test2:1:1', 'govdoc:test2', 1, 1, '1', 0, ?, ?)",
            (len(text), text),
        )
    audit = selection_audit(conn)
    titles = ["AFFIDAVIT (SYNTHETIC CASE01)", "POLICE REPORT (SYNTHETIC)"]
    assert [t for _, t in audit.docs] == titles
    ours = [u for u in audit.of("document") if u.doc == affidavit]
    assert totals(ours, audit.same) == before  # the other document's quote changes nothing here
    assert _only(_unit(audit, "¶6")).between == 2
    other = next(u for u in audit.of("document") if u.doc == "govdoc:test2")
    p = _only(other)
    assert p.picked_ids == (M(949),) and (p.before, p.after) == (1, 2)
    html = selection_html(audit)
    check_report_text(html)
    report = '<span class="q">POLICE REPORT (SYNTHETIC)</span>'
    assert (
        f"The document {report} puts 1 set of words in quotation marks, in 1 paragraph. 1 is "
        "placed on a message." in html
    )
    assert (
        "In the 1 exchange those quotes come from, 3 messages are not quoted anywhere in that "
        "document." in html
    )
    assert f"Quoted in ¶1 of {report}" in html  # 949, in ¶6's passage


def test_an_exchange_on_two_phones_counts_once_when_one_lacks_a_quoted_message(conn) -> None:
    """¶12's exchange is on both phones. A second quoted message is only on the first, so the
    two passages are not folded into one; the totals still count each message and the exchange
    once."""
    _copy_message(conn, M(1028), M(9008), body="ok on my way", ts_utc="2026-03-18T21:45:00Z")
    _copy_message(conn, M(920, 2), M(9009, 2), body="ok on my way", ts_utc="2026-03-18T21:45:00Z")
    _copy_message(conn, M(1028), M(9010), body="bring the bag", ts_utc="2026-03-18T21:50:00Z")
    _reword(conn, "12", 'come get it".', 'come get it". He then wrote "bring the bag".')
    audit = selection_audit(conn)
    unit = _unit(audit, "¶12")
    assert [p.picked_ids for p in unit.primary] == [(M(1028), M(9010)), (M(920, 2),)]
    assert totals([unit]) == Totals(picked=3, exchanges=2, left_out=4, between=1)  # per phone
    assert totals([unit], audit.same) == Totals(picked=2, exchanges=1, left_out=2, between=1)
    note = claim_note(unit, "/x", audit.same)
    assert note is not None and "¶12 quotes 2 messages from 1 exchange; 2 other messages" in note


# ---------------------------------------------------------------- exchanges


def test_thread_order_matches_core_audit_context(conn) -> None:
    for (tid,) in conn.execute("SELECT id FROM threads"):
        th = _Thread(conn, tid)
        if not th.msgs:
            continue
        assert [m.id for m in th.msgs] == list(
            context_ids(conn, th.msgs[0].id, 10**9, include_target=True)
        ), tid


def test_a_pause_longer_than_an_hour_starts_a_new_exchange(conn) -> None:
    with conn:  # 'did u get them?' exactly one hour before the quoted message: same exchange
        conn.execute("UPDATE messages SET ts_utc = '2026-03-25T15:42:09Z' WHERE id = ?", (M(669),))
    p = _only(_unit(selection_audit(conn), "¶15"))
    assert p.before == 1
    with conn:  # one second more: a new exchange, shown with the pause
        conn.execute("UPDATE messages SET ts_utc = '2026-03-25T15:42:08Z' WHERE id = ?", (M(669),))
    unit = _unit(selection_audit(conn), "¶15")
    p = _only(unit)
    assert p.before == 0 and p.lead == 0
    assert ("earlier", M(669)) in _roles(p)
    assert "The previous message in this thread is 1 h earlier." in summary(unit, p)
    assert gap_text(EXCHANGE_GAP.total_seconds() + 1) == "1 h"


def test_a_message_with_no_time_is_its_own_exchange(conn) -> None:
    with conn:
        conn.execute("UPDATE messages SET ts_utc = NULL WHERE id = ?", (M(670),))
    unit = _unit(selection_audit(conn), "¶15")
    p = _only(unit)
    assert p.untimed and p.exchange == 1 and p.left_out == 0
    assert summary(unit, p) == [
        "¶15 quotes a message with no usable time in the source, so code cannot tell what was "
        "exchanged with it. It is listed after the thread's messages that have a time, so the "
        "messages shown beside it are not necessarily the ones sent or received around it."
    ]
    last_timed = [m.id for m in _Thread(conn, p.thread.id).msgs if m.utc is not None][-3:]
    assert [r for r, _ in _roles(p)] == ["earlier"] * 3 + ["picked"]
    assert [rid for _, rid in _roles(p)][:3] == last_timed  # not 669 and 671, its neighbours


# ---------------------------------------------------------------- exhibits and tags


def test_exhibit_quotes_are_placed_and_their_exchanges_shown(conn) -> None:
    add_exhibit(conn, "Government Exhibit 4", EXHIBIT, ExcerptSplit.LINE, EXPERT, clock=lambda: NOW)
    audit = selection_audit(conn)
    unit = audit.of("exhibit")[0]
    assert unit.placed == 4 and len(unit.lookups) == 6
    assert [lk.found for lk in unit.lookups] == [0, 1, 1, 2, 2, 0]
    p = next(p for p in unit.primary if M(948) in p.picked_ids)
    assert p.picked_ids == (M(948), M(951)) and p.between == 2
    assert summary(unit, p)[1] == "Not in this exhibit: 2 between the quoted messages."
    marks = audit.marks()[M(948)]
    assert {(m.unit.kind, m.placed) for m in marks} == {
        ("document", True),
        ("exhibit", True),
        ("tags", True),
    }


def test_an_exhibit_not_searched_yet_is_named_not_checked(conn) -> None:
    from core.restore.store import _clear

    ex = add_exhibit(conn, "Ex 9", "PETROV: its done", ExcerptSplit.LINE, EXPERT, clock=lambda: NOW)
    with conn:
        _clear(conn, ex.id)
    audit = selection_audit(conn)
    assert audit.unsearched == ("Ex 9",) and not audit.of("exhibit")
    assert "has not been searched on the Exhibits screen yet" in selection_html(audit)


def test_tagged_messages_the_document_does_not_quote_are_shown(conn) -> None:
    audit = selection_audit(conn)
    assert len(audit.tagged_ids) == 10 and audit.tagged_quoted == 10
    assert not audit.of("tags")[0].passages  # every tagged message is quoted
    with conn:
        conn.execute("UPDATE messages SET bookmarked = 1 WHERE id = ?", (M(949),))
    tags = selection_audit(conn).of("tags")[0]
    p = next(p for p in tags.passages if M(949) in p.picked_ids)
    assert p.picked_ids == (M(948), M(949), M(951))
    assert summary(tags, p)[0].startswith("The examiner tagged 3 of the 4 messages")
    assert "Not tagged: 1 between the tagged messages." in summary(tags, p)


# ---------------------------------------------------------------- safety


def test_the_audit_reads_only_and_is_the_same_every_time(db) -> None:
    ro = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        first, second = selection_audit(ro), selection_audit(ro)
        with_gaps = selection_audit(ro, timeline=Settings())
    finally:
        ro.close()
    assert first == second
    assert any(p.quiet for u in with_gaps.units for p in u.passages)


def test_locking_a_case_drops_the_kept_index_of_its_messages(db, conn) -> None:
    """The matcher's index holds every message's text. It is kept in memory between views, and
    locking a case (or forgetting every key) drops it, so it never outlives a case's key."""

    def kept() -> list[Path]:
        return [Path(p).resolve() for p in selection_module._INDEXES]

    selection_audit(conn)
    assert db.resolve() in kept()
    encryption.lock(db)
    assert kept() == []
    selection_audit(conn)
    assert db.resolve() in kept()
    encryption.forget_all()
    assert kept() == []


def test_one_paragraph_alone_still_knows_what_the_others_quote(conn) -> None:
    alone = selection_audit(conn, paragraph_id=_unit(selection_audit(conn), "¶9").id)
    assert [u.label for u in alone.units] == ["¶9"]
    p = _only(alone.units[0])
    assert next(r for r in p.rows if r.line and r.line.record_id == M(951)).elsewhere


def test_cited_text_is_set_apart_from_the_tools_words(conn) -> None:
    add_exhibit(
        conn, "Deleted chats exhibit", EXHIBIT, ExcerptSplit.LINE, EXPERT, clock=lambda: NOW
    )
    _copy_message(
        conn, M(950), M(9003), body="i deleted it, leader said so", ts_utc="2026-03-12T20:10:30Z"
    )
    page = selection_html(selection_audit(conn), Links(context=lambda r: f"/x?{r}"))
    check_report_text(page)  # the label and the message are cited text, not the tool's words
    assert '<span class="q">i deleted it, leader said so</span>' in page


def test_a_sender_named_with_a_forbidden_word_is_cited_text(db, conn) -> None:
    """Some apps name a removed account 'Deleted Account'. That name is the source's, so it is
    cited, in the passage and in the table of other conversations nearby."""
    with conn:
        conn.execute(
            "INSERT INTO accounts (id, source_id, locator, app, identifier)"
            " VALUES ('acct:test:gone', 'item1', 'test', 'Telegram', 'Deleted Account')"
        )
        conn.execute(
            "UPDATE messages SET sender_account_id = 'acct:test:gone' WHERE id IN (?, ?)",
            (M(949), M(811)),
        )
    audit = selection_audit(conn)
    assert M(811) in [ln.record_id for ln in _only(_unit(audit, "¶6")).nearby]
    html = selection_html(audit)
    check_report_text(html)
    assert html.count('<span class="q">Telegram Deleted Account</span>') >= 2  # bubble, table
    app = _app(db)
    for path, query in (("/selection", {}), ("/selection/context", {"id": M(949)})):
        assert app.handle(Request("GET", path, query, dict(HOST))).status == 200, path


def test_tool_words_never_use_the_forbidden_words(conn) -> None:
    audit = selection_audit(conn)
    for u in audit.units:
        for p in u.passages:
            check_report_text("\n".join(summary(u, p)))
        for lk in u.lookups:
            check_report_text(lookup_note(lk))


# ---------------------------------------------------------------- quiet stretches (Gaps)


def test_a_quiet_stretch_in_a_pause_is_named_on_the_passage(conn) -> None:
    """¶15's exchange ends at 12:51 on March 25, and the Gaps check lists the phone's SMS going
    quiet from then until March 28. Without the case's timeline settings nothing is named."""
    assert not _only(_unit(selection_audit(conn), "¶15")).quiet
    unit = _unit(selection_audit(conn, timeline=Settings()), "¶15")
    p = _only(unit)
    assert p.quiet == (Quiet("after", "app", p.last_utc, p.quiet[0].end_utc),)
    assert p.last_utc < p.quiet[0].end_utc <= p.next_utc
    assert (
        "In the pause after this exchange, the Gaps check lists a quiet stretch: no messages in "
        "this app on this phone from 2026-03-25 12:51 EDT to 2026-03-28 14:15 EDT (3 days 1 h)."
        in summary(unit, p)
    )


def test_a_quiet_stretch_that_ends_where_the_pause_starts_is_not_named(conn) -> None:
    """The phone's Telegram goes quiet until message 946; ¶6's pause runs from 947 to 948."""
    p = _only(_unit(selection_audit(conn, timeline=Settings()), "¶6"))
    assert p.quiet == ()
    data = CaseRecords(conn)
    telegram = next(
        g
        for g in find_gaps(data, [], Settings())
        if g.series.scope == "app" and g.series.app == "Telegram" and g.after.id == M(946)
    )
    touching = replace(telegram, after=data.by_id[M(947)])
    assert touching.end == p.prev_utc
    assert quiet(p, [touching]) == ()
    inside = replace(telegram, before=data.by_id[M(947)], after=data.by_id[M(948)])
    assert quiet(p, [inside]) == (Quiet("before", "app", p.prev_utc, p.first_utc),)
    reaching = replace(telegram, after=data.by_id[M(948)])  # starts before the pause, at 946
    assert reaching.start < p.prev_utc < reaching.end == p.first_utc
    assert quiet(p, [reaching]) == ()
    other_phone = replace(inside, series=replace(inside.series, source_id="item2"))
    other_app = replace(inside, series=replace(inside.series, app="SMS"))
    assert quiet(p, [other_phone, other_app]) == ()


def test_quiet_stretches_named_lie_in_the_pause_on_the_passages_own_phone(conn) -> None:
    settings = Settings(gap_hours=24)  # a short setting, so case01 has many stretches
    stretches = find_gaps(CaseRecords(conn), [], settings)

    def listed(qs: Quiet, p: Passage) -> bool:
        return any(
            (g.start, g.end, g.series.scope) == (qs.start_utc, qs.end_utc, qs.scope)
            and g.series.source_id == p.thread.source_id
            and (qs.scope == "phone" or g.series.app == p.thread.app)
            and (qs.scope != "thread" or g.series.thread_id == p.thread.id)
            for g in stretches
        )

    named = 0
    for u in selection_audit(conn, timeline=settings).units:
        for p in u.passages:
            for qs in p.quiet:
                named += 1
                before = qs.side == "before"
                a, b = (p.prev_utc, p.first_utc) if before else (p.last_utc, p.next_utc)
                assert a <= qs.start_utc < qs.end_utc <= b
                assert listed(qs, p)
            check_report_text("\n".join(summary(u, p)))
    assert named >= 5
    p = _only(_unit(selection_audit(conn, timeline=settings), "¶15"))
    lines = [s for s in summary(_unit(selection_audit(conn), "¶15"), p) if "quiet" in s]
    assert lines == [
        "In the pause before this exchange, the Gaps check lists 3 quiet stretches. The longest: "
        "no messages in this app on this phone from 2026-03-14 22:15 EDT to 2026-03-16 09:58 EDT "
        "(35 h 43 min).",
        "In the pause after this exchange, the Gaps check lists 4 quiet stretches. The longest: "
        "no messages in this app on this phone from 2026-03-25 12:51 EDT to 2026-03-28 14:15 EDT "
        "(3 days 1 h).",
    ]


# ---------------------------------------------------------------- report and screen


def test_report_has_the_selection_audit_and_the_request(conn) -> None:
    html = render_report(conn)
    check_report_text(html)
    assert html.count("<h2 id='selection-audit'>Selection audit</h2>") == 1
    assert "<h3 id='full-extraction-request'>Request for the full extraction</h3>" in html
    assert "Not quoted anywhere in the document: 2 between the quoted messages." in html
    assert "A message such a source leaves out is not in the case" in html
    assert "the Gaps check lists a quiet stretch: no messages in this app on this phone" in html
    assert "href='/gaps'" not in html  # the report has no server to link to


def _app(db: Path) -> App:
    return App(db, expert="Test Expert", port=8765)


def test_screen_selection_tab_and_conversation_page(db) -> None:
    app = _app(db)
    page = app.handle(Request("GET", "/selection", {}, dict(HOST)))
    assert page.status == 200
    assert "<a href='/selection' class=on>Selection</a>" in page.text
    assert "Not quoted anywhere in the document" in page.text
    assert "/selection/context?id=msg%3Aitem1%3AChats%21948" in page.text
    assert "<a href='/gaps'>See it on the Gaps tab</a>" in page.text
    ctx = app.handle(Request("GET", "/selection/context", {"id": M(948)}, dict(HOST)))
    assert ctx.status == 200 and "Quoted in ¶6" in ctx.text
    assert "<a href='/selection' class=on>Selection</a>" in ctx.text
    missing = app.handle(Request("GET", "/selection/context", {"id": "msg:nope"}, dict(HOST)))
    assert missing.status == 404


def test_claim_page_points_to_its_paragraphs_selection(db, conn) -> None:
    unit = _unit(selection_audit(conn), "¶6")
    note = claim_note(unit, "/selection#x")
    assert note is not None and "2 other messages in that exchange are not quoted" in note
    cid = conn.execute("SELECT id FROM claims WHERE paragraph_id = ?", (unit.id,)).fetchone()[0]
    page = _app(db).handle(Request("GET", "/claim", {"id": cid}, dict(HOST)))
    assert page.status == 200
    assert "Selection audit: ¶6 quotes 2 messages from 1 exchange" in page.text
    assert f"/selection#sel-{unit.id}" in page.text
