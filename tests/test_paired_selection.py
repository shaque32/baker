"""Paired selection audit: a curated report against a larger source of the same phone.

Two synthetic pairs (eval/synthetic/paired.py): case01's own curated item1 report against a
UFDR of item1 that holds planted records, and a small new pair on item2's device. All data is
synthetic. Where a test needs a situation the pairs do not have (an untimed record, a report
record listed twice, a pair that does not line up), it edits its own copy of the case.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit.invariants import check_report_text
from core.db import apply_schema, connect
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.ufdr import UfdrImporter
from core.report.html import render_report
from core.report.paired import claim_line, paired_html
from core.review.status import claim_states
from core.selection.audit import selection_audit
from core.selection.paired import Pair, near_claim, paired_check, pairs
from eval import run_pipeline
from eval.synthetic import paired as planted
from eval.synthetic.case01_story import eastern_offset_min
from ui.app import App, Request

HOST = {"host": "127.0.0.1:8765"}
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def files(tmp_path_factory) -> dict[str, Path]:
    return planted.write(tmp_path_factory.mktemp("paired"))


@pytest.fixture(scope="module")
def built(files, tmp_path_factory) -> Path:
    """case01 as the eval builds it, plus the UFDR of item1 with the planted records."""
    path = tmp_path_factory.mktemp("case01p") / "case.db"
    conn = run_pipeline.build_case("case01", path)
    UfdrImporter(source_id="item1full", now=NOW).import_source(files["item1-full.ufdr"], conn)
    conn.close()
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


@pytest.fixture
def small(files, tmp_path) -> sqlite3.Connection:
    """The small pair alone: its curated report and its UFDR."""
    c = connect(tmp_path / "small.db")
    apply_schema(c)
    CellebriteExcelImporter(source_id="pair02", now=NOW).import_source(files["pair02.xlsx"], c)
    UfdrImporter(source_id="pair02full", now=NOW).import_source(files["pair02-full.ufdr"], c)
    yield c
    c.close()


def _the_pair(conn: sqlite3.Connection) -> Pair:
    ps, _, _ = pairs(conn)
    assert len(ps) == 1
    return ps[0]


def _full_id(p: Pair, body: str, at: datetime, kind: str = "message") -> str:
    found = [
        r.id
        for r in p.full_records.values()
        if r.kind == kind and r.ts == at and (kind != "message" or r.text == body)
    ]
    assert len(found) == 1, (body, at, found)
    return found[0]


def _report_id(p: Pair, body: str, at: datetime) -> str:
    found = [m.record.id for m in p.matches if m.record.text == body and m.record.ts == at]
    assert len(found) == 1, (body, at)
    return found[0]


# ---------------------------------------------------------------- the synthetic pairs


def test_the_curated_report_is_case01_item1_unchanged(files) -> None:
    case = json.loads(Path("eval/synthetic/case01/case.json").read_text(encoding="utf-8"))
    sha = next(s["sha256"] for s in case["sources"] if s["source_id"] == "item1")
    assert hashlib.sha256(files["item1.xlsx"].read_bytes()).hexdigest() == sha


def test_the_pairs_are_deterministic(files, tmp_path) -> None:
    again = planted.write(tmp_path / "again")
    for name, path in files.items():
        assert path.read_bytes() == again[name].read_bytes(), name


# ---------------------------------------------------------------- every report record


def test_every_report_record_is_matched_ambiguous_or_unmatched(conn) -> None:
    p = _the_pair(conn)
    assert (p.report.id, p.full.id) == ("item1", "item1full")
    assert "Telegram 7001001" in p.basis
    sql = "SELECT COUNT(*) FROM {} WHERE source_id = 'item1'"
    n = {
        k: conn.execute(sql.format(t)).fetchone()[0]
        for k, t in (("message", "messages"), ("call", "calls"), ("contact", "contacts"))
    }
    for kind, total in n.items():
        assert p.total(kind) == total
        assert sum(p.count(kind, s) for s in ("matched", "ambiguous", "unmatched")) == total
    assert {m.record.id for m in p.matches} >= {f"msg:item1:Chats!{i}" for i in (948, 949, 950)}
    odd = {m.record.id: m.state for m in p.matches if m.state != "matched"}
    assert odd == {"msg:item1:Chats!949": "unmatched", "msg:item1:Chats!950": "ambiguous"}
    assert p.listed


def test_planted_records_are_found_as_planted(conn) -> None:
    p = _the_pair(conn)
    for pl in planted.PLANTED:
        fid = _full_id(p, pl.msg.body, pl.msg.at)
        assert p.full_state[fid] == pl.state, (pl.msg.key, pl.why)
    for call, _ in planted.PLANTED_CALLS:
        assert p.full_state[_full_id(p, "", call.at, "call")] == "not_in_report"
    # the report's "fine" could be either "fine": both may be in the report
    pp05 = next(pl for pl in planted.PLANTED if pl.msg.key == "pp05")
    amb = next(m for m in p.matches if m.state == "ambiguous")
    assert _full_id(p, "fine", pp05.msg.at) in amb.candidates and len(amb.candidates) == 2
    # the edited message: the report's copy is not found, the larger source's may be it
    edited = _full_id(p, planted.EDITED[1], datetime(2026, 3, 13, 0, 9, 2, tzinfo=UTC))
    assert p.full_state[edited] == "may_be" and p.may_be_why[edited] == "near_unmatched"
    left = {r.id for r in p.left_out("message")}
    assert left == {
        _full_id(p, pl.msg.body, pl.msg.at) for pl in planted.PLANTED if pl.state == "not_in_report"
    }
    assert [r.text for r in p.left_out("contact")] == ["Kevin S"]
    whole = [t for t in p.missing_threads() if t[4]]
    assert [t[1] for t in whole] == ["Kevin S"]  # the only conversation not in the report at all


def test_omissions_near_each_claim_match_the_planted_key_in_order(conn) -> None:
    p = _the_pair(conn)
    chk = paired_check(conn, claim_states(conn), selection_audit(conn))
    expected: dict[str, list[str]] = {}
    for pl in planted.PLANTED:
        for cid in pl.near:
            expected.setdefault(cid, []).append(_full_id(p, pl.msg.body, pl.msg.at))
    for call, near in planted.PLANTED_CALLS:
        for cid in near:
            expected.setdefault(cid, []).append(_full_id(p, "", call.at, "call"))
    got = {c.claim_id: [n.record.id for n in c.ordered()] for c in chk.claims if c.total}
    assert {k: set(v) for k, v in got.items()} == {k: set(v) for k, v in expected.items()}
    by = {c.claim_id: c for c in chk.claims}
    c05 = by["C05"]
    # the claim's own conversation first, by time distance; then the other thread; calls last
    assert [g.title for g in c05.groups] == ["@northstar", "Ilya", None]
    assert [n.record.text for n in c05.ordered()][:3] == [
        "or sunday works too",
        "call me when ur close",
        "cant tonight, tmrw?",
    ]
    assert [round(n.distance_s) for n in c05.ordered()] == [183, 804, 507, 1104]
    c20 = by["C20"]
    assert [(g.title, g.has_anchor, g.whole) for g in c20.groups] == [
        ("Alex", True, False),
        ("Kevin S", False, True),
    ]
    # claims whose records are on the pair but have nothing near them say so, with no list
    for cid in ("C10", "C11", "C12", "C16"):
        assert by[cid].anchors and not by[cid].total, cid
    assert ("C01", "C01") in chk.no_records


def test_small_pair_lists_by_thread_then_time_distance(small) -> None:
    p = _the_pair(small)
    assert p.basis and p.listed
    by_key = {pl.msg.key: pl for pl in planted.PAIR02_EXTRA}
    q02 = next(m for m in planted.PAIR02_REPORT if m.key == "q02")
    amb = [m for m in p.matches if m.state == "ambiguous"]
    assert [m.record.id for m in amb] == [_report_id(p, "yeah", q02.at)]
    assert p.full_state[_full_id(p, "yeah", by_key["q03"].msg.at)] == "may_be"
    assert sum(1 for m in p.matches if m.state == "unmatched") == 0
    anchor = next(m for m in planted.PAIR02_REPORT if m.key == planted.PAIR02_ANCHOR)
    rid = _report_id(p, anchor.body, anchor.at)
    cn = near_claim(p, "X", "X", [rid], {m.record.id: m for m in p.matches})
    assert cn is not None
    keys = {_full_id(p, pl.msg.body, pl.msg.at): k for k, pl in by_key.items()}
    keys |= {_full_id(p, "", c.at, "call"): c.key for c in planted.PAIR02_EXTRA_CALLS}
    assert tuple(keys[n.record.id] for n in cn.ordered()) == planted.PAIR02_ORDER
    q07 = _full_id(p, "done", by_key["q07"].msg.at)
    assert p.full_state[q07] == "not_in_report"  # counted, but more than an hour away


# ---------------------------------------------------------------- failing closed


def test_two_report_records_that_could_be_one_record_are_both_ambiguous(small) -> None:
    p = _the_pair(small)
    anchor = next(m for m in planted.PAIR02_REPORT if m.key == "q04")
    rid = _report_id(p, anchor.body, anchor.at)
    cols = [r[1] for r in small.execute("PRAGMA table_info(messages)")]
    row = dict(zip(cols, small.execute("SELECT * FROM messages WHERE id = ?", (rid,)).fetchone(),
                   strict=True))  # fmt: skip
    row.update(id=rid + "-copy", locator=row["locator"] + "-copy")
    with small:
        small.execute(
            f"INSERT INTO messages ({','.join(row)}) VALUES ({','.join('?' * len(row))})",  # noqa: S608
            list(row.values()),
        )
    p = _the_pair(small)
    states = {m.record.id: m.state for m in p.matches}
    assert states[rid] == states[rid + "-copy"] == "ambiguous"
    assert p.full_state[_full_id(p, anchor.body, anchor.at)] == "may_be"


def test_an_untimed_report_record_not_found_holds_back_its_app_and_direction(small) -> None:
    p = _the_pair(small)
    q09 = next(m for m in planted.PAIR02_REPORT if m.key == "q09")
    rid = _report_id(p, "ok", q09.at)
    with small:
        small.execute("UPDATE messages SET body = 'okay', ts_utc = NULL WHERE id = ?", (rid,))
    p = _the_pair(small)
    fid = _full_id(p, "ok", q09.at)
    assert p.full_state[fid] == "may_be" and p.may_be_why[fid] == "near_unmatched"
    assert fid not in {r.id for r in p.left_out("message")}


def test_a_pair_that_does_not_line_up_lists_nothing(conn) -> None:
    with conn:  # one report message in ten no longer found in the larger source
        conn.execute(
            "UPDATE messages SET body = body || ' (x)' WHERE source_id = 'item1'"
            " AND CAST(substr(locator, 7) AS INTEGER) % 10 = 0"
        )
    p = _the_pair(conn)
    assert not p.listed and "may not be the same phone" in (p.not_listed_why or "")
    assert p.left_out("message") == [] and p.missing_threads() == []
    chk = paired_check(conn, claim_states(conn), selection_audit(conn))
    assert all(c.total == 0 for c in chk.claims)
    html = paired_html(chk)
    assert "nothing is listed for this pair" in html and "data-rec=" not in html


def test_no_shared_account_means_no_pair(small) -> None:
    with small:
        small.execute("UPDATE accounts SET device_id = NULL WHERE source_id = 'pair02full'")
    ps, unpaired, larger = pairs(small)
    assert ps == [] and [s.id for s in unpaired] == ["pair02"] and len(larger) == 1
    html = paired_html(paired_check(small, [], selection_audit(small)))
    assert "is not compared" in html


def test_a_case_with_only_curated_reports_says_what_is_missing(tmp_path) -> None:
    c = run_pipeline.build_case("case01", tmp_path / "plain.db")
    try:
        chk = paired_check(c, claim_states(c), selection_audit(c))
        assert chk.pairs == () and len(chk.unpaired) == 2
        assert "no larger source" in paired_html(chk)
    finally:
        c.close()


# ---------------------------------------------------------------- never a verdict


def test_the_check_reads_only_and_never_changes_a_verdict(db, conn) -> None:
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    conn.execute("PRAGMA query_only = ON")
    states = claim_states(conn)
    verdicts = [(s.claim.id, s.decision) for s in states]
    paired_check(conn, states, selection_audit(conn))
    render_report(conn)
    assert [(s.claim.id, s.decision) for s in claim_states(conn)] == verdicts
    conn.execute("PRAGMA query_only = OFF")
    conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


# ---------------------------------------------------------------- screen and report agree

_ATTRS = re.compile(r"data-(pair|claim|rec|odd)='([^']*)'")


def _paired_part(html: str) -> list[tuple[str, str]]:
    start = html.index("<h3 id='paired-audit'>")
    end = html.index("<h3 id='full-extraction-request'>") if "full-extraction-request" in html[
        start:
    ] else len(html)  # fmt: skip
    return _ATTRS.findall(html[start:end])


def test_screen_and_report_list_the_same_records_in_the_same_order(db, conn) -> None:
    report = render_report(conn)
    check_report_text(report)
    app = App(db, expert="Test Expert", port=8765)
    page = app.handle(Request("GET", "/selection", {}, dict(HOST)))
    assert page.status == 200
    check_report_text(page.text)
    shown, printed = _paired_part(page.text), _paired_part(report)
    assert shown == printed
    assert ("pair", "item1|item1full") in shown
    assert sum(1 for k, _ in shown if k == "rec") == 10  # C05 and C06: 4 each; C20: 2
    assert [v for k, v in shown if k == "claim"] == [
        "C05", "C06", "C10", "C11", "C12", "C13", "C16", "C20"
    ]  # fmt: skip


def test_claim_page_says_what_the_larger_source_holds_near_it(db, conn) -> None:
    chk = paired_check(conn, claim_states(conn), selection_audit(conn))
    assert "holds 4 records within an hour" in claim_line(chk, "C05", "/x")
    assert "holds nothing within an hour" in claim_line(chk, "C10", "/x")
    assert claim_line(chk, "C01", "/x") == ""
    page = App(db, expert="Test Expert", port=8765).handle(
        Request("GET", "/claim", {"id": "C05"}, dict(HOST))
    )
    assert page.status == 200
    assert "Curated report check:" in page.text and "/selection#paired-C05" in page.text


def test_times_show_on_the_phone_clock(conn) -> None:
    html = paired_html(paired_check(conn, claim_states(conn), selection_audit(conn)))
    pp01 = next(pl for pl in planted.PLANTED if pl.msg.key == "pp01")
    assert eastern_offset_min(pp01.msg.at) == -240
    assert "2026-03-12 20:06:30 EDT" in html


# ---------------------------------------------------------------- review findings (#78)


def test_records_after_the_reports_extraction_are_never_counted_left_out(conn) -> None:
    with conn:  # the report was made before ¶15's day; the larger source later
        conn.execute(
            "UPDATE sources SET extracted_at_utc = '2026-03-20T00:00:00Z' WHERE id = 'item1'"
        )
    p = _the_pair(conn)
    late = {pl.msg.key: pl for pl in planted.PLANTED}
    for key in ("pp06", "pp07"):  # 2026-03-25
        fid = _full_id(p, late[key].msg.body, late[key].msg.at)
        assert p.full_state[fid] == "not_compared" and p.may_be_why[fid] == "after_report"
    pp01 = _full_id(p, late["pp01"].msg.body, late["pp01"].msg.at)
    assert p.full_state[pp01] == "not_in_report"  # 2026-03-12, before it
    chk = paired_check(conn, claim_states(conn), selection_audit(conn))
    by = {c.claim_id: c for c in chk.claims}
    assert by["C20"].total == 0 and by["C05"].total == 4
    assert "dated after the report's extraction" in paired_html(chk)


def test_a_report_with_no_extraction_time_lists_nothing(conn) -> None:
    with conn:
        conn.execute("UPDATE sources SET extracted_at_utc = NULL WHERE id = 'item1'")
    p = _the_pair(conn)
    assert not p.listed and "extraction time is not known" in (p.not_listed_why or "")
    assert p.left_out("message") == []


def test_a_shared_account_on_another_device_model_is_not_a_pair(conn) -> None:
    with conn:  # the same accounts signed in on another phone
        conn.execute("UPDATE devices SET model = 'Apple iPad Air' WHERE source_id = 'item1full'")
    ps, unpaired, _ = pairs(conn)
    assert ps == [] and "item1" in [s.id for s in unpaired]
    assert "states the same device model" in paired_html(
        paired_check(conn, claim_states(conn), selection_audit(conn))
    )


def test_claim_line_names_a_pair_that_lists_nothing_beside_one_that_does(conn) -> None:
    chk = paired_check(conn, claim_states(conn), selection_audit(conn))
    c10 = next(c for c in chk.claims if c.claim_id == "C10")
    other = replace(
        c10.pair, listed=False, not_listed_why="x", full=replace(c10.pair.full, file_name="b.ufdr")
    )
    line = claim_line(replace(chk, claims=(c10, replace(c10, pair=other))), "C10", "/x")
    assert "holds nothing within an hour" in line
    assert 'nothing is listed for <span class="q">b.ufdr</span>' in line


def test_claim_ids_are_escaped_in_the_list_anchor(conn) -> None:
    chk = paired_check(conn, claim_states(conn), selection_audit(conn))
    c05 = next(c for c in chk.claims if c.claim_id == "C05")
    odd = replace(c05, claim_id="C'5\" onclick=x", claim_name="C'5")
    html = paired_html(replace(chk, claims=(odd,)))
    assert "id='paired-C&#x27;5&quot; onclick=x'" in html and "onclick=x'" not in html.replace(
        "&quot; onclick=x'", ""
    )


def test_a_removed_claim_page_has_no_link_to_a_missing_list(db, conn) -> None:
    with conn:
        conn.execute("UPDATE claims SET status = 'removed' WHERE id = 'C05'")
    page = App(db, expert="Test Expert", port=8765).handle(
        Request("GET", "/claim", {"id": "C05"}, dict(HOST))
    )
    assert page.status == 200 and "Curated report check:" not in page.text
