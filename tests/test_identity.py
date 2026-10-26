"""The identity audit on synthetic case01: proposed links, the expert's decisions, and what a
link may and may not change.

case01's identity traps: the affidavit says "@northstar is ALEXANDER SOKOLOV" (C18, gold
unproven: nothing names a surname), and that @northstar is the "Alex" saved at 0182 on Item 1
(C19, gold contradicted: that Alex calls himself "alex turner"). Code may propose links from
names in the data; it must show what speaks against them and must never confirm one.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit.checks._common import CaseData, person_party
from core.audit.invariants import check_report_text
from core.audit.retrieval import query_for
from core.contracts import (
    Assumption,
    AssumptionKind,
    AssumptionParams,
    IdentityLinkStatus,
    ProvenanceTier,
)
from core.db import connect
from core.identity import links as L
from core.report.html import render_report
from core.review import actions, audit_log
from core.review.actions import ReviewError
from eval import run_pipeline
from ui.app import App, Request

EXPERT = "expert:Test Expert"
SOKOLOV = "ALEXANDER SOKOLOV"
TELEGRAM = "acct:item1:Telegram:5551234"
ALEX_0182 = "acct:item1:SMS:+12125550182"
WHEN = datetime(2026, 10, 13, tzinfo=UTC)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("identity") / "case01.db"
    run_pipeline.build_case("case01", path).close()
    return path


@pytest.fixture
def conn(built, tmp_path) -> sqlite3.Connection:
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    c = connect(copy)
    yield c
    c.close()


def _add_sokolov(conn: sqlite3.Connection) -> str:
    pid = actions.add_person(conn, SOKOLOV, EXPERT, clock=lambda: WHEN)
    L.propose_links(conn, clock=lambda: WHEN)
    return pid


def _links(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    return {
        lid: (status, tier)
        for lid, status, tier in conn.execute("SELECT id, status, tier FROM identity_links")
    }


def _candidate(conn: sqlite3.Connection, pid: str, account: str) -> L.Candidate:
    case = L.load(conn)
    person = next(p for p in case.persons if p.id == pid)
    return next(c for c in L.candidates(case, person) if account in c.group.account_ids)


# ---------------------------------------------------------------- proposals


def test_a_name_in_the_document_is_listed_until_the_expert_adds_it(conn):
    case = L.load(conn)
    names = {u.name: u for u in L.unplaced_names(conn, case.persons)}
    assert SOKOLOV in names and names[SOKOLOV].matches == 0
    assert "C18" in names[SOKOLOV].claim_ids
    assert "PETROV" not in names and "REYES" not in names  # each resolves to its phone owner
    _add_sokolov(conn)
    assert SOKOLOV not in {u.name for u in L.unplaced_names(conn, L.load(conn).persons)}


def test_code_proposes_links_only_from_names_in_the_data_and_confirms_none(conn):
    pid = _add_sokolov(conn)
    got = _links(conn)
    assert set(got) == {L.link_id(TELEGRAM, pid), L.link_id(ALEX_0182, pid)}
    assert set(got.values()) == {("proposed", "inferred")}
    (actor,) = [
        r[0]
        for r in conn.execute("SELECT actor FROM audit_log WHERE action = ?", (L.PROPOSE_ACTION,))
    ]
    assert actor == "system"
    assert audit_log.verify_chain(conn)


def test_each_link_shows_what_speaks_against_it(conn):
    pid = _add_sokolov(conn)
    tele = _candidate(conn, pid, TELEGRAM)
    assert [s.quote for s in tele.support] == ["@alex92", "@alex92"]  # a short form of Alexander
    against = {s.record_id: s for s in tele.against}
    assert "contact:item2:Contacts!4#2" in against  # Item 2 saves 5551234 as "Sasha N"
    assert "msg:item1:Chats!938" in against  # "hey its sasha"
    assert "msg:item2:Chats!836" in {s.record_id for s in tele.mentions}  # "ok sasha"
    alex = _candidate(conn, pid, ALEX_0182)
    turner = next(s for s in alex.against if s.record_id == "msg:item1:Chats!666")
    assert "different surname" in L.plain(turner.note)
    # C18 states the Telegram link itself; confirming it must not read as deciding C18
    assert L.claims_stating(L.load(conn), tele) == ["C18"]
    assert L.claims_stating(L.load(conn), alex) == []


def test_owner_accounts_are_not_proposed_for_their_own_owner(conn):
    case = L.load(conn)
    for person in case.persons:
        for c in L.candidates(case, person):
            assert not set(c.group.owner_devices) & set(person.devices)


def test_a_person_with_no_named_account_says_what_was_searched(conn):
    actions.add_person(conn, "VIKTOR ORLOV", EXPERT)
    L.propose_links(conn)
    case = L.load(conn)
    person = next(p for p in case.persons if p.name == "VIKTOR ORLOV")
    assert L.candidates(case, person) == []
    note = L.plain(L.searched_note(case))
    assert "item1" in note and "curated report" in note


def test_proposing_again_never_touches_an_expert_decision(conn):
    pid = _add_sokolov(conn)
    lid = L.link_id(TELEGRAM, pid)
    actions.decide_identity_link(conn, lid, IdentityLinkStatus.REJECTED, EXPERT, "Sasha N.")
    assert L.propose_links(conn).added == []
    assert _links(conn)[lid] == ("rejected", "inferred")


# ---------------------------------------------------------------- what a link changes


def test_only_a_confirmed_link_counts_in_a_check(conn):
    pid = _add_sokolov(conn)
    assert person_party(CaseData(conn), pid).keys == set()  # proposed: not used
    lid = L.link_id(TELEGRAM, pid)
    actions.decide_identity_link(conn, lid, IdentityLinkStatus.UNRESOLVED, EXPERT)
    assert person_party(CaseData(conn), pid).keys == set()
    actions.decide_identity_link(conn, lid, IdentityLinkStatus.CONFIRMED, EXPERT, "Test only.")
    assert _links(conn)[lid] == ("confirmed", "confirmed")
    assert person_party(CaseData(conn), pid).keys == {("telegram", "5551234")}
    actions.decide_identity_link(conn, lid, IdentityLinkStatus.REJECTED, EXPERT, "Changed mind.")
    assert _links(conn)[lid] == ("rejected", "inferred")  # never left showing as confirmed
    assert person_party(CaseData(conn), pid).keys == set()


def test_a_rejected_link_is_not_searched_but_the_claims_handle_still_is(conn):
    pid = _add_sokolov(conn)
    for account in (TELEGRAM, ALEX_0182):
        actions.decide_identity_link(
            conn, L.link_id(account, pid), IdentityLinkStatus.REJECTED, EXPERT, "Test."
        )
    a = Assumption(
        id="asm:C18:person_identity:x",
        claim_id="C18",
        kind=AssumptionKind.IDENTITY,
        template_id="person_identity",
        template_version="1.0.0",
        params=AssumptionParams(person_ids=(pid,), handles=("@northstar",)),
        text="@northstar belongs to ALEXANDER SOKOLOV",
        is_core=True,
        tier=ProvenanceTier.INFERRED,
    )
    q = query_for(a, conn)
    assert ALEX_0182 not in q.account_ids
    assert q.thread_ids  # @northstar's own conversations
    assert pid in q.unresolved  # the person has no account to search by


def test_only_an_expert_decides_with_a_reason(conn):
    pid = _add_sokolov(conn)
    lid = L.link_id(TELEGRAM, pid)
    with pytest.raises(ReviewError):
        actions.decide_identity_link(conn, lid, IdentityLinkStatus.CONFIRMED, "ai:qwen", "x")
    with pytest.raises(ReviewError):
        actions.decide_identity_link(conn, lid, IdentityLinkStatus.CONFIRMED, EXPERT, " ")
    with pytest.raises(ReviewError):
        actions.decide_identity_link(conn, lid, IdentityLinkStatus.PROPOSED, EXPERT, "x")
    assert _links(conn)[lid] == ("proposed", "inferred")


def test_a_name_that_would_be_ambiguous_is_refused(conn):
    with pytest.raises(ReviewError, match="tell them apart"):
        actions.add_person(conn, "PETROV", EXPERT)  # Daniel Petrov owns Item 1


def test_numbered_designations_are_different_people(conn):
    """Affidavits name people SUBJECT-1, SUBJECT-2; the number is part of the name."""
    one = actions.add_person(conn, "SUBJECT-1", EXPERT)
    two = actions.add_person(conn, "SUBJECT-2", EXPERT)
    assert (one, two) == ("person:subject-1", "person:subject-2")
    with pytest.raises(ReviewError, match="tell them apart"):
        actions.add_person(conn, "subject-2", EXPERT)
    assert L.resolves(L.load(conn).persons, "SUBJECT-2") == [two]
    for pid in (one, two):
        actions.remove_person(conn, pid, EXPERT)


def test_removing_a_person_keeps_what_an_expert_confirmed(conn):
    pid = _add_sokolov(conn)
    lid = actions.link_account(conn, ALEX_0182, pid, EXPERT, "Test only.")
    assert _links(conn)[lid] == ("confirmed", "confirmed")
    with pytest.raises(ReviewError, match="confirmed"):
        actions.remove_person(conn, pid, EXPERT)
    actions.decide_identity_link(conn, lid, IdentityLinkStatus.REJECTED, EXPERT, "Undo.")
    actions.remove_person(conn, pid, EXPERT)
    assert _links(conn) == {}
    with pytest.raises(ReviewError, match="phone owner"):
        actions.remove_person(conn, "person:dev:item1:owner", EXPERT)


def test_the_report_lists_a_confirmed_link_as_a_limitation(conn):
    pid = _add_sokolov(conn)
    assert "Who uses an account is an expert decision" not in render_report(conn)
    actions.decide_identity_link(
        conn, L.link_id(TELEGRAM, pid), IdentityLinkStatus.CONFIRMED, EXPERT, "Test only."
    )
    html = render_report(conn)
    assert "Who uses an account is an expert decision, not a finding." in html
    assert "Telegram 5551234" in html and SOKOLOV in html
    check_report_text(html)


# ---------------------------------------------------------------- the screen

HOST = {"host": "127.0.0.1:8765"}


def _get(app: App, path: str):  # noqa: ANN202
    return app.handle(Request("GET", path, {}, dict(HOST)))


def _post(app: App, path: str, **form: str):  # noqa: ANN202
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def test_the_identities_page_flow(conn):
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    app = App(db, expert="Test Expert", port=8765)
    page = _get(app, "/identities")
    assert page.status == 200 and SOKOLOV in page.text and "Add as a person" in page.text
    assert _post(app, "/person/add", name=SOKOLOV, next="/identities").status == 303
    assert app.flash and not app.flash[1] and "2 link(s)" in app.flash[0]
    page = _get(app, "/identities").text
    assert page.count("<article class='card idlink") == 2
    assert "The document states this link itself" in page
    assert "class='badge b-conf'" not in page  # nothing confirmed by code
    lid = L.link_id(TELEGRAM, "person:alexander-sokolov")
    _post(app, "/identity/decide", id=lid, status="confirmed", note="", next="/identities")
    assert app.flash and app.flash[1]  # refused: no reason
    _post(app, "/identity/decide", id=lid, status="rejected", note="Saved as Sasha N.")
    assert app.flash and not app.flash[1]
    page = _get(app, "/identities").text
    assert "Rejected by expert:Test Expert" in page
    assert "identity change(s) since the last audit" not in page  # no audit has run here
    check_report_text(page)
    assert "Open Identities" in _get(app, "/setup").text


def test_identity_styles_do_not_reach_the_claim_page_sidebar():
    # The claim page's ledger is <aside class='side'>. A bare .side rule from the Identities
    # page once made it a flex row and squashed it into a thin column.
    import re

    from ui.theme import THEME_CSS

    for selector in re.findall(r"([^{}]+)\{", THEME_CSS):
        for part in selector.split(","):
            if re.match(r"\.side\b", part.strip()):
                raise AssertionError(f"unscoped .side rule: {part.strip()!r}")
