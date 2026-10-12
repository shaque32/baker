"""Context Restore on synthetic case01: stored exhibits, context, the report and the screen.

The exhibits are written here from the synthetic affidavit's own quotes. All data is synthetic.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit.invariants import check_report_text
from core.contracts import ExcerptSplit
from core.db import connect
from core.report.html import render_report
from core.report.letter import request_letter
from core.restore.match import verify
from core.restore.store import (
    ExhibitError,
    add_exhibit,
    load_excerpts,
    load_exhibits,
    load_matches,
    match_exhibits,
    remove_exhibit,
    stale_reason,
)
from core.restore.view import identifier_key, match_view, related_threads
from core.review import audit_log
from eval import run_pipeline
from ui.app import App, Request

EXPERT = "expert:Test Expert"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
EXHIBIT = """Telegram chat, Item 1
3/12/2026 4:15 PM PETROV: "need 2 more by friday"
3/12/2026 8:11 PM @northstar: "The package will be at Marcs."
3/5/2026 2:31 AM PETROV: its done
PETROV: got the money ... get it
REYES: we never talked about this
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("restore") / "case01.db"
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


def _add(conn: sqlite3.Connection, text: str = EXHIBIT, label: str = "Government Exhibit 4"):
    return add_exhibit(conn, label, text, ExcerptSplit.LINE, EXPERT, clock=lambda: NOW)


def _results(conn: sqlite3.Connection, ex_id: str) -> dict[str, list[str]]:
    return {
        x.text: [m.record_id for m in load_matches(conn, x.id)] for x in load_excerpts(conn, ex_id)
    }


# ---------------------------------------------------------------- store


def test_add_stores_verbatim_and_finds_each_quote(conn) -> None:
    ex = _add(conn)
    (stored,) = load_exhibits(conn)
    assert stored.text == EXHIBIT and stored.sha256 == ex.sha256
    got = _results(conn, ex.id)
    assert got["Telegram chat, Item 1"] == []
    assert got['3/12/2026 4:15 PM PETROV: "need 2 more by friday"'] == ["msg:item1:Chats!948"]
    assert got['3/12/2026 8:11 PM @northstar: "The package will be at Marcs."'] == [
        "msg:item1:Chats!951"
    ]
    # the same text on both phones is found on both
    assert set(got["3/5/2026 2:31 AM PETROV: its done"]) == {
        "msg:item1:Chats!1011",
        "msg:item2:Chats!903",
    }
    assert len(got["PETROV: got the money ... get it"]) == 2
    assert got["REYES: we never talked about this"] == []


def test_every_stored_match_verifies_against_the_stored_body(conn) -> None:
    ex = _add(conn)
    from core.restore.match import Found

    n = 0
    for x in load_excerpts(conn, ex.id):
        assert x.text == ex.text[x.char_start : x.char_end]
        for m in load_matches(conn, x.id):
            body = conn.execute("SELECT body FROM messages WHERE id = ?", (m.record_id,)).fetchone()
            f = Found(m.record_id, m.ref, m.method, m.spans, m.excerpt_spans)
            assert verify(x.text, body[0], f)
            n += 1
    assert n >= 6


def test_add_and_remove_are_expert_actions_in_the_audit_log(conn) -> None:
    with pytest.raises(ExhibitError):
        add_exhibit(conn, "Exhibit", "its done", ExcerptSplit.LINE, "system")
    with pytest.raises(ExhibitError):
        _add(conn, text="   \n  ")
    ex = _add(conn)
    with pytest.raises(ExhibitError):
        _add(conn)  # the same exhibit twice
    remove_exhibit(conn, ex.id, EXPERT, clock=lambda: NOW)
    assert load_exhibits(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM exhibit_matches").fetchone()[0] == 0
    actions = [
        (a, json.loads(p))
        for a, p in conn.execute(
            "SELECT action, payload_json FROM audit_log WHERE action LIKE 'exhibit%' ORDER BY seq"
        )
    ]
    assert [a for a, _ in actions] == ["exhibit_add", "exhibit_match", "exhibit_remove"]
    assert actions[1][1]["excerpts_found"] == 4 and actions[1][1]["excerpts_not_found"] == 2
    assert actions[1][1]["matches_failed_verification"] == 0
    assert audit_log.verify_chain(conn)


def test_new_messages_make_matches_stale_until_searched_again(conn) -> None:
    ex = _add(conn)
    assert stale_reason(conn, ex.id) is None
    with conn:
        conn.execute(
            "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
            " imported_at_utc) VALUES ('item9', 'synthetic', 'full_extraction', 'file_system',"
            " 'item9.zip', ?, '2026-10-12T00:00:00Z')",
            ("0" * 64,),
        )
        conn.execute(
            "INSERT INTO threads (id, source_id, locator, app) VALUES"
            " ('thr:item9:SMS:1', 'item9', 't1', 'SMS')"
        )
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, direction, ts_utc, body)"
            " VALUES ('msg:item9:1', 'item9', 'm1', 'thr:item9:SMS:1', 'incoming',"
            " '2026-03-20T12:00:00Z', 'we never talked about this')"
        )
    assert "imported" in stale_reason(conn, ex.id)
    match_exhibits(conn, clock=lambda: NOW)
    assert stale_reason(conn, ex.id) is None
    assert _results(conn, ex.id)["REYES: we never talked about this"] == ["msg:item9:1"]


def test_block_split_keeps_multi_line_messages_whole(conn) -> None:
    ex = add_exhibit(
        conn,
        "Exhibit 9",
        "PETROV:\nneed 2 more\nby friday\n\nmove it tonight",
        ExcerptSplit.BLOCK,
        EXPERT,
        clock=lambda: NOW,
    )
    got = _results(conn, ex.id)
    assert got == {
        "PETROV:\nneed 2 more\nby friday": ["msg:item1:Chats!948"],
        "move it tonight": ["msg:item1:Chats!952"],
    }


# ---------------------------------------------------------------- context


def test_context_window_times_and_tiers(conn) -> None:
    ex = _add(conn)
    x = next(x for x in load_excerpts(conn, ex.id) if "its done" in x.text)
    m = next(m for m in load_matches(conn, x.id) if m.ref.source_id == "item1")
    v = match_view(conn, m)
    target = [ln for ln in v.lines if ln.is_target]
    assert len(target) == 1 and target[0].body == "its done"
    # The exhibit prints 2:31 AM on March 5; the phone's own clock read 9:31 PM on March 4.
    assert target[0].utc == "2026-03-05 02:31:00 UTC"
    assert target[0].local.startswith("2026-03-04 21:31:00 EST")
    assert {ln.tier.value for ln in v.lines} == {"observed"}
    assert len(v.lines) <= 41
    assert v.before + len(v.lines) + v.after == v.thread.messages


def test_related_threads_cross_phones_but_not_through_the_owner_alone(conn) -> None:
    rel = {r.thread.id for r in related_threads(conn, "thr:item1:SMS:10", None, None)}
    assert "thr:item2:SMS:10" in rel  # the same two numbers on REYES's phone
    assert "thr:item1:WhatsApp:8" in rel  # same counterpart on another app, same phone
    assert not any(t.startswith("thr:item2:") and t not in {"thr:item2:SMS:10",
                   "thr:item2:WhatsApp:8"} for t in rel)  # fmt: skip


def test_identifier_key() -> None:
    assert identifier_key("+1 (212) 555-0122") == identifier_key("12125550122@s.whatsapp.net")
    assert identifier_key("@NorthStar") == identifier_key("northstar")
    assert identifier_key("5551234") != identifier_key("+12125551234")


# ---------------------------------------------------------------- report and letter


def test_report_has_context_restore_and_the_request_letter(conn) -> None:
    _add(conn)
    html = render_report(conn)
    check_report_text(html)
    assert "<h2 id='context-restore'>Context Restore</h2>" in html
    assert "4 of 6 quoted messages found" in html
    assert "Not found in the messages searched." in html
    assert "This does not show that the message was never sent or received." in html
    assert "examiner-curated report" in html
    assert "<h2 id='selection-audit'>Selection audit</h2>" in html
    assert "Request for complete phone extractions" in html


def test_letter_lists_each_report_and_the_missing_quotes(conn) -> None:
    _add(conn)
    text = request_letter(conn)
    assert text is not None
    for (sha,) in conn.execute("SELECT sha256 FROM sources WHERE kind != 'govdoc'"):
        assert sha in text
    assert "Government Exhibit 4: 2 of 6 quoted messages not located" in text
    assert "DRAFT FOR COUNSEL'S REVIEW" in text
    check_report_text(text)


def test_no_letter_when_every_source_is_a_full_extraction(conn) -> None:
    with conn:
        conn.execute("UPDATE sources SET fidelity = 'full_extraction' WHERE kind != 'govdoc'")
    assert request_letter(conn) is None
    assert "no request for one is drafted" in render_report(conn)


# ---------------------------------------------------------------- review screen

HOST = {"host": "127.0.0.1:8765"}


def _app(db: Path) -> App:
    return App(db, expert="Test Expert", port=8765)


def test_screen_add_view_and_remove(db) -> None:
    app = _app(db)
    page = app.handle(Request("GET", "/exhibits", {}, dict(HOST)))
    assert page.status == 200 and "Add an exhibit" in page.text
    resp = app.handle(
        Request(
            "POST",
            "/exhibit/add",
            {},
            dict(HOST),
            {
                "token": app.token,
                "label": "Gov Ex 4",
                "text": EXHIBIT,
                "split": "line",
                "next": "/exhibits",
            },
        )  # fmt: skip
    )
    assert resp.status == 303
    loc = resp.header("Location")
    assert loc.startswith("/exhibit?id=exh%3A")
    page = app.handle(Request("GET", "/exhibit", {"id": loc.split("=", 1)[1].replace("%3A", ":")},
                              dict(HOST)))  # fmt: skip
    assert page.status == 200
    assert "4 of 6 quoted messages found" in page.text and "Open in context" in page.text
    c = connect(db)
    (m,) = load_matches(c, load_excerpts(c, load_exhibits(c)[0].id)[1].id)
    ex_id = load_exhibits(c)[0].id
    c.close()
    page = app.handle(Request("GET", "/exhibit/match", {"id": m.id}, dict(HOST)))
    assert page.status == 200 and "need 2 more by friday" in page.text
    assert "Phone's local time" in page.text
    letter = app.handle(Request("GET", "/request-letter.txt", {}, dict(HOST)))
    assert letter.status == 200 and "attachment" in letter.header("Content-Disposition")
    resp = app.handle(
        Request("POST", "/exhibit/remove", {}, dict(HOST), {"token": app.token, "id": ex_id})
    )
    assert resp.status == 303
    c = connect(db)
    assert load_exhibits(c) == []
    c.close()


def test_screen_rejects_an_exhibit_post_without_the_token(db) -> None:
    app = _app(db)
    resp = app.handle(
        Request("POST", "/exhibit/add", {}, dict(HOST), {"token": "x", "label": "a", "text": "b"})
    )
    assert resp.status == 403
