"""Person aliases (schema 0.6.0, signed by Arsh 2026-10-30): the other names an expert gives a
person, as the government document writes them ("SUBJECT-1", "HAL").

case04's go/no-go (Arsh's Mac run, 2026-10-30, NO-GO): 11 of the 32 claims the testability step
did not convert named a person by an affidavit designation that no person's one name matched.
Only an expert enters an alias. It is matched whole, never by its last word, and an alias that
could reach two persons is refused, or matches neither if it ever does.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit import testability
from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import LocalAssumptionFiller
from core.audit.invariants import check_report_text
from core.contracts import Claim, ClaimStatus, ClaimType
from core.db import apply_schema, connect
from core.identity import aliases
from core.identity import links as L
from core.report.html import render_report
from core.review import actions
from core.review.actions import ReviewError
from eval import run_pipeline
from tests.fake_model import FakeModel
from ui.app import App, Request

EXPERT = "expert:Test Expert"
WHEN = datetime(2026, 10, 30, 23, 30, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]
FILLER_DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))
PETROV = "person:dev:item1:owner"  # case01's Item 1 owner, Daniel Petrov
HOST = {"host": "127.0.0.1:8765"}


def _clock() -> datetime:
    return WHEN


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    return conn


@pytest.fixture
def two(db) -> tuple[str, str]:
    hal = actions.add_person(db, "Owen Halloran", EXPERT, _clock)
    dez = actions.add_person(db, "Desmond Okafor", EXPERT, _clock)
    return hal, dez


def _log(conn: sqlite3.Connection, action: str) -> list[dict]:
    return [
        json.loads(p)
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq", (action,)
        )
    ]


# ---------------------------------------------------------------- entering them


def test_an_expert_records_a_persons_other_names_and_each_is_logged(db, two):
    hal, _ = two
    kept = actions.set_aliases(db, hal, ["SUBJECT-1", "  HAL ", "subject 1"], EXPERT, _clock)
    assert kept == ["HAL", "SUBJECT-1"]  # "subject 1" is SUBJECT-1 again, matched alike
    assert [p["alias"] for p in _log(db, aliases.ADD_ACTION)] == ["SUBJECT-1", "HAL"]
    assert aliases.person_names(db)[hal] == ("Owen Halloran", ["HAL", "SUBJECT-1"])
    row = db.execute("SELECT created_by, created_at_utc FROM person_aliases LIMIT 1").fetchone()
    assert row == (EXPERT, "2026-10-30T23:30:00Z")


def test_the_list_replaces_the_old_one_and_an_empty_list_clears_it(db, two):
    hal, _ = two
    actions.set_aliases(db, hal, ["SUBJECT-1", "HAL"], EXPERT, _clock)
    assert actions.set_aliases(db, hal, ["SUBJECT-1"], EXPERT, _clock) == ["SUBJECT-1"]
    assert [p["alias"] for p in _log(db, aliases.REMOVE_ACTION)] == ["HAL"]
    assert actions.set_aliases(db, hal, [], EXPERT, _clock) == []
    assert aliases.person_names(db)[hal] == ("Owen Halloran", [])
    assert len(_log(db, aliases.ADD_ACTION)) == 2  # saving SUBJECT-1 again logged nothing


@pytest.mark.parametrize(
    ("alias", "why"),
    [
        ("Desmond Okafor", "would also match Desmond Okafor"),  # another person's whole name
        ("OKAFOR", "would also match Desmond Okafor"),  # another person's surname
        ("dez", "would also match Desmond Okafor"),  # another person's alias, any case
        ("Halloran", "already how the audit matches Owen Halloran"),
        ("--", "no letter or digit"),
        ("x" * 121, "up to 120 characters"),
    ],
)
def test_an_alias_the_audit_could_not_place_on_one_person_is_refused(db, two, alias, why):
    hal, dez = two
    actions.set_aliases(db, dez, ["DEZ"], EXPERT, _clock)
    with pytest.raises(ReviewError, match=why):
        actions.set_aliases(db, hal, ["SUBJECT-1", alias], EXPERT, _clock)
    assert aliases.person_names(db)[hal] == ("Owen Halloran", [])  # nothing half-saved


def test_only_an_expert_enters_an_alias_and_only_for_a_person_in_the_case(db, two):
    hal, _ = two
    with pytest.raises(ReviewError):
        actions.set_aliases(db, hal, ["SUBJECT-1"], "model:qwen3-14b", _clock)
    with pytest.raises(ReviewError, match="no person"):
        actions.set_aliases(db, "person:nobody", ["SUBJECT-1"], EXPERT, _clock)
    with pytest.raises(sqlite3.IntegrityError):  # the schema holds the line too
        db.execute(
            "INSERT INTO person_aliases VALUES (?, 'SUBJECT-1', 'model:qwen3-14b', 't')", (hal,)
        )
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO person_aliases VALUES ('person:nobody', 'X1', ?, 't')", (EXPERT,))


def test_a_new_person_may_not_take_a_name_another_person_is_called(db, two):
    hal, _ = two
    actions.set_aliases(db, hal, ["SUBJECT-1", "BOSS"], EXPERT, _clock)
    with pytest.raises(ReviewError, match="whom the document also calls SUBJECT-1"):
        actions.add_person(db, "SUBJECT-1", EXPERT, _clock)
    with pytest.raises(ReviewError, match="also calls BOSS"):
        actions.add_person(db, "Tony Boss", EXPERT, _clock)  # its surname is the alias
    actions.add_person(db, "Big Boss Man", EXPERT, _clock)  # neither its name nor its surname


def test_removing_a_person_removes_their_aliases_and_says_so(db, two):
    hal, _ = two
    actions.set_aliases(db, hal, ["SUBJECT-1"], EXPERT, _clock)
    actions.remove_person(db, hal, EXPERT, _clock)
    assert aliases.stored(db) == []
    assert _log(db, "person.remove")[-1]["aliases_removed"] == ["SUBJECT-1"]


# ---------------------------------------------------------------- reading them


def test_a_shared_alias_matches_neither_person(db, two):
    hal, dez = two
    # Entry refuses this; a database can still hold it (a phone owner renamed later, or rows
    # written outside the actions), so the reader drops it for both.
    for pid, alias in ((hal, "THE BOSS"), (dez, "the boss"), (dez, "HALLORAN")):
        db.execute(
            "INSERT INTO person_aliases VALUES (?, ?, ?, '2026-10-30T23:30:00Z')",
            (pid, alias, EXPERT),
        )
    names = aliases.person_names(db)
    assert names[hal] == ("Owen Halloran", [])
    assert names[dez] == ("Desmond Okafor", [])  # HALLORAN is Owen Halloran's surname
    assert len(aliases.stored(db)) == 3  # the report and the form still show every row


def test_an_alias_is_matched_whole_never_by_its_last_word(db, two):
    hal, _ = two
    actions.set_aliases(db, hal, ["Big Owen", "SUBJECT-1"], EXPERT, _clock)
    persons = L.load(db).persons
    assert L.resolves(persons, "big owen") == [hal]
    assert L.resolves(persons, "SUBJECT-1") == [hal]
    assert L.resolves(persons, "HALLORAN") == [hal]  # the name keeps the surname rule
    assert L.resolves(persons, "Owen") == []  # "Big Owen"'s last word is no name
    assert L.resolves(persons, "SUBJECT-12") == []


def test_an_alias_another_persons_last_name_word_matches_is_refused(db):
    """The Identities page reads "John Brown-Smith"'s last name word as "Smith", so "Smith"
    would reach him there: it may not be another person's alias (Codex on #181)."""
    john = actions.add_person(db, "John Brown-Smith", EXPERT, _clock)
    amy = actions.add_person(db, "Amy Jones", EXPERT, _clock)
    assert L.resolves(L.load(db).persons, "Smith") == [john]
    with pytest.raises(ReviewError, match="would also match John Brown-Smith"):
        actions.set_aliases(db, amy, ["Smith"], EXPERT, _clock)
    db.execute(
        "INSERT INTO person_aliases VALUES (?, 'SMITH', ?, '2026-10-30T23:30:00Z')", (amy, EXPERT)
    )
    assert aliases.person_names(db)[amy] == ("Amy Jones", [])  # written outside the action
    assert L.resolves(L.load(db).persons, "Smith") == [john]


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("SUBJECT-1 drove.", "SUBJECT-1"),
        ("Subject 1 drove.", "Subject 1"),  # spacing and punctuation do not count (Codex)
        ("SUBJECT-1's phone", "SUBJECT-1"),
        ("SUBJECT-12 drove.", None),
        ("Subject-1A drove.", None),
        ("SUBJECT1 drove.", None),  # no break between its words, so another name
        ("He wrote to @subject-1.", None),  # a handle, not the designation
    ],
)
def test_an_alias_is_found_whole_as_its_key_compares_it(text, found):
    assert aliases.written("SUBJECT-1", text) == found


def test_an_everyday_alias_matches_in_any_case_as_the_experts_statement(db, two):
    """An alias is the expert's statement that the document's words mean this person, so it
    applies wherever a claim writes them, capitals or not. The Limitations line says so; an
    expert gives the document's defined term, not a common word (Baker Eval on #181)."""
    _, dez = two
    actions.set_aliases(db, dez, ["the DRIVER"], EXPERT, _clock)
    assert aliases.written("the DRIVER", "the DRIVER's phone") == "the DRIVER"
    assert aliases.written("the DRIVER", "the driver of the van") == "the driver"
    assert aliases.written("the DRIVER", "a driver for the courier") is None


def test_an_alias_in_another_script_is_kept_and_matched(db, two):
    hal, _ = two
    assert actions.set_aliases(db, hal, ["Дима", "José"], EXPERT, _clock) == ["José", "Дима"]
    assert aliases.written("Дима", "ДИМА wrote first.") == "ДИМА"
    assert aliases.key("José") != aliases.key("Jose")
    assert L.resolves(L.load(db).persons, "дима") == [hal]


def test_a_case_database_without_the_table_reads_as_having_no_aliases(db, two):
    hal, _ = two
    db.execute("DROP TABLE person_aliases")
    assert aliases.person_names(db)[hal] == ("Owen Halloran", [])
    assert aliases.stored(db) == []


# ---------------------------------------------------------------- on case01


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("aliases") / "case01.db"
    run_pipeline.build_case("case01", path).close()
    return path


@pytest.fixture
def conn(built, tmp_path) -> sqlite3.Connection:
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    c = connect(copy)
    yield c
    c.close()


def _claim(text: str) -> Claim:
    return Claim(
        id="C99",
        paragraph_id="para:x",
        text=text,
        claim_type=ClaimType.COMMUNICATION,
        status=ClaimStatus.ACCEPTED,
    )


def test_the_testability_step_looks_a_person_up_by_an_alias_the_claim_writes(conn):
    filler = LocalAssumptionFiller(FakeModel({}), conn, template=FILLER_DRAFT)
    text = "On March 12, 2026, SUBJECT-1 wrote to @northstar on Telegram."
    people = [x for x in testability.lookups(filler, _claim(text), "") if x.kind == "person"]
    assert people == []  # before the expert gives the alias
    actions.set_aliases(conn, PETROV, ["SUBJECT-1"], EXPERT, _clock)
    people = [x for x in testability.lookups(filler, _claim(text), "") if x.kind == "person"]
    assert [(x.written, x.means) for x in people] == [
        ("SUBJECT-1", "a person in the case (Daniel Petrov)")
    ]
    longer = _claim("On March 12, 2026, SUBJECT-12 wrote to @northstar on Telegram.")
    assert not [x for x in testability.lookups(filler, longer, "") if x.kind == "person"]
    # compared as the Identities page compares it: "Subject 1" is SUBJECT-1 (Codex on #181)
    spaced = _claim("On March 12, 2026, Subject 1 wrote to @northstar on Telegram.")
    people = [x for x in testability.lookups(filler, spaced, "") if x.kind == "person"]
    assert [x.written for x in people] == ["Subject 1"]


def _add_claim(conn: sqlite3.Connection, text: str) -> None:
    para = conn.execute("SELECT id FROM govdoc_paragraphs ORDER BY id LIMIT 1").fetchone()[0]
    actions.add_claim(conn, "C99", para, text, ClaimType.COMMUNICATION, EXPERT, _clock)


def test_a_designation_with_an_alias_is_placed_and_its_claims_are_named(conn):
    _add_claim(conn, "On March 12, 2026, SUBJECT-1 wrote to @northstar on Telegram.")
    before = {u.name: u.matches for u in L.unplaced_names(conn, L.load(conn).persons)}
    assert before.get("SUBJECT-1") == 0  # offered whole, number and all
    actions.set_aliases(conn, PETROV, ["SUBJECT-1"], EXPERT, _clock)
    case = L.load(conn)
    assert "SUBJECT-1" not in {u.name for u in L.unplaced_names(conn, case.persons)}
    petrov = next(p for p in case.persons if p.id == PETROV)
    assert petrov.aliases == ("SUBJECT-1",)
    assert "C99" in {cid for cid, _ in L.claims_naming(conn, petrov)}


def test_other_designations_stay_names_of_their_own_on_the_identities_page(conn):
    """An alias places SUBJECT-1 only: CW-1 and SUBJECT-12 are still offered (Baker Eval on
    #181)."""
    _add_claim(conn, "On March 12, 2026, SUBJECT-1 met CW-1 and SUBJECT-12 on Telegram.")
    actions.set_aliases(conn, PETROV, ["SUBJECT-1"], EXPERT, _clock)
    unplaced = {u.name: u.matches for u in L.unplaced_names(conn, L.load(conn).persons)}
    assert unplaced.get("CW-1") == 0 and unplaced.get("SUBJECT-12") == 0
    assert "SUBJECT-1" not in unplaced


def test_the_report_lists_each_alias_as_an_expert_statement(conn):
    actions.set_aliases(conn, PETROV, ["SUBJECT-1", "DP"], EXPERT, _clock)
    html = render_report(conn)
    assert "Whom the document means by another name is an expert statement" in html
    assert (
        'said on 2026-10-30T23:30:00Z that the document\'s <span class="q">DP</span>, '
        '<span class="q">SUBJECT-1</span> is <span class="q">Daniel Petrov</span>.'
    ) in html
    check_report_text(html)


def _get(app: App, path: str):  # noqa: ANN202
    return app.handle(Request("GET", path, {}, dict(HOST)))


def _post(app: App, path: str, **form: str):  # noqa: ANN202
    form.setdefault("token", app.token)
    return app.handle(Request("POST", path, {}, dict(HOST), form))


def test_the_identities_page_saves_and_offers_aliases(conn):
    _add_claim(conn, "On March 12, 2026, SUBJECT-1 wrote to @northstar on Telegram.")
    conn.commit()
    db_path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    app = App(db_path, expert="Test Expert", port=8765)
    page = _get(app, "/identities").text
    assert "Also called in the document" in page and "Add as another name" in page
    assert _post(app, "/person/alias/add", id=PETROV, alias="SUBJECT-1").status == 303
    assert app.flash and not app.flash[1] and "SUBJECT-1" in app.flash[0]
    _post(app, "/person/aliases", id=PETROV, aliases="SUBJECT-1, DP", next="/identities")
    assert app.flash and not app.flash[1]
    _post(app, "/person/aliases", id=PETROV, aliases="REYES")  # Marcus Reyes's surname
    assert app.flash and app.flash[1]
    page = _get(app, "/identities").text
    assert "value='SUBJECT-1, DP'" not in page  # stored order is by alias
    assert "value='DP, SUBJECT-1'" in page
    check_report_text(page)
