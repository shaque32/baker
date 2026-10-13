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

from core.audit.context import context_ids
from core.audit.invariants import check_report_text
from core.contracts import ExcerptSplit
from core.db import connect
from core.report.html import render_report
from core.report.selection import Links, claim_note, selection_html, totals
from core.restore.store import add_exhibit
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
    assert totals(audit.of("document")).picked == 7  # copies are not counted twice


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
        "exchanged with it. The messages beside it in the source's order are shown."
    ]


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
