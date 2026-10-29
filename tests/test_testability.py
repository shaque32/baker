"""The testability step (core/audit/testability.py): a second try at a claim the assumption
filler left untested, checked by the filler's own code and then against the signed sheet, used
only once an examiner accepts it, each try logged and re-run by verify-bundle without a model.
Synthetic case01 only, with scripted fake models; case02 is the held-out case and is never used.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import pipeline
from core.audit import assumption_filler, testability
from core.audit._llm_json import prompt_body, required_placeholders
from core.audit.assumption_filler import LocalAssumptionFiller
from core.audit.assumptions import TemplateAssumptionBuilder, is_code_made
from core.audit.invariants import InvariantViolation
from core.bundle import export
from core.bundle import verify as verify_mod
from core.bundle.verify import FAIL, NOTE, PASS, failed, verify_bundle
from core.contracts import Claim, ClaimStatus, ClaimType, GoldClaim
from core.llm.runtime import FakeModel as RuntimeFake
from core.report.html import render_report
from core.review.actions import set_claim_status
from eval import run_pipeline as rp
from eval.run_eval import load_jsonl
from eval.synthetic.generate import generate
from tests.checks.helpers import stipulate
from tests.fake_model import FakeModel

ROOT = Path(__file__).parents[1]
FILLER_DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))
DRAFT = prompt_body((ROOT / "docs/prompts/agent_testability.md").read_text("utf-8"))
SHEET = [
    json.loads(line)
    for line in (ROOT / "eval/gold/case01/assumptions.jsonl").read_text("utf-8").splitlines()
    if line
]
GOLD = {
    d["claim_id"]: d
    for d in map(json.loads, (ROOT / "eval/gold/case01/gold.jsonl").read_text("utf-8").splitlines())
}
PETROV, REYES = "person:petrov", "person:reyes"
EXAMINER = "expert:Dana Reyes"


def P(template_id: str, **kw) -> dict:  # noqa: N802
    base = dict(
        people=[],
        accounts=[],
        handles=[],
        phones=[],
        channels=[],
        quoted_text="",
        count=None,
        duration=None,
        window=None,
    )
    return {"template_id": template_id, **base, **kw}


MARC = {"as_written": "+1 (212) 555-0122", "app": "Phone"}
# C01's first try writes the phone as an account, as run 2's refusals did (kinds only): refused.
ITEM1_AS_ACCOUNT = {"as_written": "Item 1", "app": "Phone"}
BAD_C01 = {
    "assumptions": [
        P("contact_entry", quoted_text="Marc Garage", accounts=[ITEM1_AS_ACCOUNT, MARC])
    ]
}
GOOD_C01 = {
    "assumptions": [
        P("contact_entry", phones=["Item 1"], quoted_text="Marc Garage", accounts=[MARC])
    ]
}


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    db = out / "case01.db"
    generate(out, db)
    c = sqlite3.connect(db)
    stipulate(c, PETROV, "Daniel Petrov", "dev:item1")
    stipulate(c, REYES, "Marcus Reyes", "dev:item2")
    c.execute("PRAGMA foreign_keys = OFF")
    affidavit = (ROOT / "eval/synthetic/case01/affidavit_draft.md").read_text("utf-8")
    for label, text in re.findall(r"^(\d+)\. (.+)$", affidavit, re.M):
        c.execute(
            "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
            " char_end, text) VALUES (?, 'gd', 1, ?, ?, 0, ?, ?)",
            (f"para:{label}", int(label), label, len(text), text),
        )
    for cid, g in GOLD.items():
        c.execute(
            "INSERT OR IGNORE INTO claims (id, paragraph_id, text, claim_type, status)"
            " VALUES (?, ?, ?, ?, 'accepted')",
            (cid, f"para:{g['para_no']}", g["text"], g["claim_type"]),
        )
    yield c
    c.close()


def claim(cid: str) -> Claim:
    g = GOLD[cid]
    return Claim(
        id=cid,
        paragraph_id=f"para:{g['para_no']}",
        text=g["text"],
        claim_type=ClaimType(g["claim_type"]),
        status=ClaimStatus.ACCEPTED,
    )


def first_pass(conn, cid: str, answer: dict):  # noqa: ANN001, ANN202
    filler = LocalAssumptionFiller(FakeModel(answer), conn, template=FILLER_DRAFT)
    builder = TemplateAssumptionBuilder(filler)
    built = builder.build(claim(cid))
    return filler, built, builder.refused(cid)


def step(conn, filler, *answers, sheet=None, cap=1, examiner=lambda c, a: EXAMINER):  # noqa: ANN001, ANN202
    model = FakeModel(*answers)
    s = testability.Testability(
        model,
        filler,
        testability.sheet_named(SHEET) if sheet is None else sheet,
        cap,
        template=DRAFT,
        examiner=examiner,
    )
    return s, model


# ---------------------------------------------------------------- the draft prompt


def test_the_draft_prompt_and_any_signed_copy_have_every_placeholder():
    assert required_placeholders(DRAFT) >= testability.PLACEHOLDERS
    signed = ROOT / "core/audit/prompts" / testability.PROMPT_FILE
    if signed.exists():  # once Arsh signs it (PROPOSED_CHANGES.md)
        assert required_placeholders(prompt_body(signed.read_text("utf-8"))) >= (
            testability.PLACEHOLDERS
        )


def test_the_answer_has_no_field_for_the_claim():
    fields = set(assumption_filler._ProposalOut.model_fields)
    assert not fields & {"claim", "text", "claim_text", "claim_id"}


# ---------------------------------------------------------------- lookups and the sheet


def test_lookups_name_the_phone_and_the_number_the_claim_writes(conn):
    filler = LocalAssumptionFiller(FakeModel({}), conn, template=FILLER_DRAFT)
    found = testability.lookups(filler, claim("C01"), filler.paragraph_text(claim("C01")))
    by_kind = {(x.kind, x.written) for x in found}
    assert ("phone", "Item 1") in by_kind
    assert ("account", "+1 (212) 555-0122") in by_kind
    assert all(x.written in claim("C01").text + filler.paragraph_text(claim("C01")) for x in found)
    people = testability.lookups(filler, claim("C05"), "")
    assert ("person", "PETROV") in {(x.kind, x.written) for x in people}


def test_a_phone_label_is_not_found_inside_a_longer_one():
    assert testability._written("Item 1", ["Item 12 holds it"]) is None
    assert testability._written("Item 1", ["seen on item 1."]) == "item 1"


def test_the_sheet_check_rejects_whatever_the_sheet_does_not_name():
    sheet = testability.Named(people=frozenset({PETROV}), phones=frozenset({"dev:item1"}))
    ok = testability.Named(people=frozenset({PETROV}))
    assert testability.mismatch(ok, sheet) == []
    other = testability.Named(people=frozenset({REYES}), phones=frozenset({"dev:item2"}))
    wrong = testability.mismatch(other, sheet)
    assert len(wrong) == 2 and all("signed sheet does not name" in w for w in wrong)


def test_sheet_windows_compare_by_their_utc_ends():
    rows = [r for r in SHEET if r["claim_id"] == "C05"]
    facts = testability.sheet_named(rows)["C05"]
    assert facts.people == {PETROV}
    assert facts.windows == {("2026-03-12T04:00:00+00:00", "2026-03-13T03:59:59.999999+00:00")}


# ---------------------------------------------------------------- the claim-only check

# C09's call, with the party the claim writes and the length it states.
WIN_C09 = {
    "as_written": "At about 7:58 p.m. on March 9, 2026",
    "start": "2026-03-09T19:50",
    "end": "2026-03-09T20:05",
    "zone": "phone",
}
CALL_C09 = P(
    "record_time",
    phones=["Item 1"],
    channels=["call"],
    accounts=[{"as_written": "+1 (212) 555-0122", "app": "Phone"}],
    duration={"as_written": "about two minutes"},
    window=WIN_C09,
)


def test_the_claim_only_check_counts_only_what_the_claims_own_words_name(conn):
    filler = LocalAssumptionFiller(FakeModel({}), conn, template=FILLER_DRAFT)
    N = testability.Named  # noqa: N806
    c08 = claim("C08")  # "PETROV chose the location ...": its paragraph names REYES too
    assert testability.outside_claim(filler, c08, N(people=frozenset({PETROV}))) == []
    (why,) = testability.outside_claim(filler, c08, N(people=frozenset({REYES})))
    assert "claim's own words do not name" in why
    c05 = claim("C05")  # PETROV and @northstar; no phone
    assert testability.outside_claim(filler, c05, N(handles=frozenset({"@northstar"}))) == []
    wrong = N(phones=frozenset({"dev:item2"}), handles=frozenset({"@alex92"}))
    assert len(testability.outside_claim(filler, c05, wrong)) == 2
    c01 = claim("C01")  # the number +1 (212) 555-0122
    ok = N(accounts=frozenset({"acct:item1:Phone:+12125550122"}), phones=frozenset({"dev:item1"}))
    assert testability.outside_claim(filler, c01, ok) == []
    other = N(accounts=frozenset({"acct:item1:SMS:+12125550182"}))
    assert testability.outside_claim(filler, c01, other)


def test_a_repair_naming_a_person_only_its_paragraph_names_is_outside_the_claim(conn):
    """The filler takes names from the claim or its paragraph; the agent's repair only from the
    claim. C09's paragraph names PETROV, its claim does not: rejected before the sheet, which
    names PETROV, is read."""
    filler = LocalAssumptionFiller(FakeModel({}), conn, template=FILLER_DRAFT)
    sheet = testability.sheet_named(SHEET)["C09"]
    assert PETROV in sheet.people
    with_petrov = {**CALL_C09, "people": ["PETROV"]}
    for check in (testability.CLAIM_CHECK, testability.SHEET_CHECK):
        outcome, reasons, got, kept = testability.check_answer(
            filler, claim("C09"), [with_petrov], sheet, check
        )
        assert (outcome, kept) == ("outside", []) and PETROV in got.people
        assert reasons == [f"names the person {PETROV!r}, which the claim's own words do not name"]
    outcome, reasons, _, kept = testability.check_answer(
        filler, claim("C09"), [CALL_C09], None, testability.CLAIM_CHECK
    )
    assert (outcome, reasons) == ("proposed", []) and [a.template_id for a in kept] == [
        "record_time"
    ]


def test_without_a_sheet_the_step_proposes_on_the_claim_only_check(conn):
    filler, _, why = first_pass(conn, "C01", BAD_C01)
    s = testability.Testability(FakeModel(GOOD_C01), filler, None, 1, template=DRAFT)
    rep = s.repair(claim("C01"), why)
    (only,) = rep.attempts
    assert only.outcome == "proposed" and rep.check == testability.CLAIM_CHECK
    assert only.proposed and all(set(x) == {"id", "template_id", "text"} for x in only.proposed)
    assert [x["id"] for x in only.proposed] == only.assumption_ids
    assert rep.assumptions == [] and rep.accepted_by is None  # no examiner: not used
    assert rep.entries()[0]["check"] == testability.CLAIM_CHECK


# ---------------------------------------------------------------- one claim


def test_a_refused_claim_is_repaired_checked_and_used_once_the_examiner_accepts(conn):
    filler, built, why = first_pass(conn, "C01", BAD_C01)
    assert built == [] and why
    s, model = step(conn, filler, GOOD_C01)
    rep = s.repair(claim("C01"), why)
    assert [a.outcome for a in rep.attempts] == ["proposed"]
    assert rep.accepted_by == EXAMINER
    assert [a.template_id for a in rep.assumptions] == ["contact_entry"]
    assert rep.assumptions[0].params.device_ids == ("dev:item1",)
    prompt = model.prompts[0]
    assert all(r in prompt for r in why)  # the try is told code's reasons
    assert '"Item 1": a phone (Apple iPhone 13 (A2482)), not an account' in prompt
    assert claim("C01").text in prompt


def test_a_repair_nobody_accepts_is_logged_and_never_used(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    s, _ = step(conn, filler, GOOD_C01, examiner=None)
    rep = s.repair(claim("C01"), why)
    assert rep.attempts[-1].outcome == "proposed" and rep.assumptions == []
    assert rep.accept_entry() is None
    s, _ = step(conn, filler, GOOD_C01, examiner=lambda c, a: "system")
    assert s.repair(claim("C01"), why).assumptions == []  # only an expert accepts


def test_a_repair_naming_another_phone_than_the_sheet_is_rejected_and_is_a_no_go(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    facts = testability.sheet_named(SHEET)
    sheet = {**facts, "C01": testability.Named(accounts=facts["C01"].accounts)}  # no phone
    s, _ = step(conn, filler, GOOD_C01, sheet=sheet)
    rep = s.repair(claim("C01"), why)
    att = rep.attempts[-1]
    assert att.outcome == "mismatch" and att.no_go and rep.assumptions == []
    assert any("phone 'dev:item1'" in r for r in att.reasons)


def test_an_account_the_sheet_does_not_name_is_rejected_but_is_not_the_no_go_kind(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    facts = testability.sheet_named(SHEET)
    sheet = {**facts, "C01": testability.Named(phones=facts["C01"].phones)}
    s, _ = step(conn, filler, GOOD_C01, sheet=sheet)
    att = s.repair(claim("C01"), why).attempts[-1]
    assert att.outcome == "mismatch" and not att.no_go


@pytest.mark.parametrize(
    "drop, said",
    [
        ("templates", "template 'contact_entry'"),
        ("quotes", "quoted words 'marc garage'"),
    ],
)
def test_the_same_entities_on_another_template_or_quote_are_rejected(conn, drop, said):
    """The sheet check compares what the assumptions test, not only who and when."""
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    facts = testability.sheet_named(SHEET)
    sheet = {**facts, "C01": dataclasses.replace(facts["C01"], **{drop: frozenset({"other"})})}
    s, _ = step(conn, filler, GOOD_C01, sheet=sheet)
    att = s.repair(claim("C01"), why).attempts[-1]
    assert att.outcome == "mismatch" and not att.no_go
    assert any(said in r for r in att.reasons), att.reasons


def test_an_app_the_sheet_does_not_name_is_rejected():
    rows = [r for r in SHEET if r["claim_id"] == "C05"]
    sheet = testability.sheet_named(rows)["C05"]
    got = testability.named(
        [("sender", {"person_ids": [PETROV], "quoted_text": "need 2 more by  Friday",
                     "channels": ["Telegram"]})]
    )  # fmt: skip
    assert testability.mismatch(got, sheet) == [
        "names the app 'telegram', which the signed sheet does not name"
    ]  # quoted words compare with case and spacing folded


def test_a_claim_the_sheet_leaves_untested_is_never_repaired(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    facts = {k: v for k, v in testability.sheet_named(SHEET).items() if k != "C01"}
    s, _ = step(conn, filler, GOOD_C01, sheet=facts)
    rep = s.repair(claim("C01"), why)
    assert rep.sheet is None and rep.assumptions == []
    assert rep.attempts[-1].reasons == ["the signed sheet has no core assumption for this claim"]


def test_the_cap_bounds_the_calls_and_each_try_is_told_the_last_ones_reasons(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    s, model = step(conn, filler, BAD_C01, cap=3)
    rep = s.repair(claim("C01"), why)
    assert len(model.prompts) == 3 and [a.n for a in rep.attempts] == [1, 2, 3]
    assert all(a.outcome == "refused" for a in rep.attempts)
    assert rep.attempts[1].refused_before == rep.attempts[0].reasons
    assert all(r in model.prompts[1] for r in rep.attempts[0].reasons)
    s, model = step(conn, filler, BAD_C01, GOOD_C01, cap=3)
    assert [a.outcome for a in s.repair(claim("C01"), why).attempts] == ["refused", "proposed"]
    assert len(model.prompts) == 2  # stops at the first try that passes


def test_an_unusable_answer_is_counted_invalid(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    s, _ = step(conn, filler, "not json at all")
    att = s.repair(claim("C01"), why).attempts[-1]
    assert att.outcome == "invalid" and att.assumption_ids == []


def test_a_try_gets_the_fillers_own_fills_in_its_order(conn):
    """check_answer runs the filler's steps after its items in the filler's own order (#160,
    #164): an answer naming no assumption for C05 gets code's sender and time range from the
    claim's words, exactly as the first pass does with the same answer."""
    filler, built, _why = first_pass(conn, "C05", {"assumptions": []})
    assert {a.template_id for a in built} >= {"sender", "record_time"}
    same = testability.named((a.template_id, a.params.model_dump()) for a in built if a.is_core)
    outcome, reasons, _got, assumptions = testability.check_answer(filler, claim("C05"), [], same)
    assert (outcome, reasons) == ("proposed", [])
    assert sorted(a.id for a in assumptions) == sorted(a.id for a in built)
    # Code's fills keep their note on the repair path too (Codex on #169).
    assert any(is_code_made(a.text) for a in built)
    assert sorted(a.text for a in assumptions) == sorted(a.text for a in built)


def test_a_try_runs_every_code_fill_the_first_pass_runs(conn, monkeypatch):
    """The repair runs the filler's own code_fills, the call count included (Codex on #169)."""
    filler, _built, _why = first_pass(conn, "C05", {"assumptions": []})
    seen: list[str] = []
    real = filler._add_call_count

    def counting(claim, out, allowed):
        seen.append(claim.id)
        return real(claim, out, allowed)

    monkeypatch.setattr(filler, "_add_call_count", counting)
    testability.check_answer(filler, claim("C05"), [], testability.named([]))
    assert seen == ["C05"]


def test_the_repair_leaves_the_first_pass_refusals_as_they_were(conn):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    before = list(filler.drops)
    s, _ = step(conn, filler, BAD_C01, GOOD_C01, cap=2)
    s.repair(claim("C01"), why)
    assert filler.drops == before


def test_a_repair_that_changes_the_claim_fails_the_run(conn, monkeypatch):
    filler, _built, why = first_pass(conn, "C01", BAD_C01)
    s, _ = step(conn, filler, GOOD_C01)
    real = testability.check_answer

    def editing(*a, **kw):  # noqa: ANN002, ANN003, ANN202
        conn.execute("UPDATE claims SET text = text || ' (edited)' WHERE id = 'C01'")
        return real(*a, **kw)

    monkeypatch.setattr(testability, "check_answer", editing)
    try:
        with pytest.raises(InvariantViolation, match="changed the claim"):
            s.repair(claim("C01"), why)
    finally:
        conn.execute("UPDATE claims SET text = ? WHERE id = 'C01'", (GOLD["C01"]["text"],))


def test_the_step_needs_a_cap_and_a_sheet(conn):
    filler = LocalAssumptionFiller(FakeModel({}), conn, template=FILLER_DRAFT)
    with pytest.raises(ValueError, match="cap"):
        testability.Testability(FakeModel({}), filler, testability.sheet_named(SHEET), 0,
                                template=DRAFT)  # fmt: skip
    with pytest.raises(ValueError, match="signed sheet"):
        testability.Testability(FakeModel({}), filler, {}, 1, template=DRAFT)


# ---------------------------------------------------------------- in the audit


def _answers(prompt: str) -> str:
    """The filler's answer for C01 (refused), and the step's (passes)."""
    if "[REFUSED START]" in prompt:
        return json.dumps(GOOD_C01)
    return json.dumps(BAD_C01)


def _audit(folder: Path, on: bool = True, examiner: str | None = EXAMINER, signed: bool = True):  # noqa: ANN202
    conn = rp.build_case("case01", folder / "case01.db")
    result = pipeline.run_audit(conn, _components(conn, on, examiner, signed), claim_ids=["C01"])
    return conn, result


def _components(conn, on: bool = True, examiner: str | None = EXAMINER, signed: bool = True):  # noqa: ANN001, ANN202
    """case01's components with the scripted filler; the step checks against the signed sheet,
    or (signed False) against the claim's own words only, as a case without a sheet."""
    from eval.pipeline_fakes import FakeReviewer
    from eval.simulated_expert import GoldDirectionLabeler, GoldKey

    gold = GoldKey(load_jsonl(rp.gold_path("case01"), GoldClaim))
    model = RuntimeFake(respond=_answers)
    filler = assumption_filler.create(conn, model=model)
    comps = pipeline.real_components(
        conn,
        replace={"labeler": GoldDirectionLabeler(conn, gold), "reviewer": FakeReviewer(False)},
        filler=filler,
    )
    comps.reviewable = lambda item: False
    comps.model_runs = (*comps.model_runs, *GoldDirectionLabeler.model_runs)
    if on:
        s = testability.create(
            conn,
            filler,
            testability.sheet_named(SHEET, rp.sheet_people(conn)) if signed else None,
            1,
            model=model,
            template=DRAFT,
            examiner=(lambda c, a: examiner),
        )
        comps.testability = s
        comps.recorders = (*comps.recorders, s)
        comps.model_runs = (*comps.model_runs, *s.model_runs)
    return comps


def _log(conn, action: str) -> list[tuple[str, dict]]:  # noqa: ANN001
    return [
        (a, json.loads(p))
        for a, p in conn.execute(
            "SELECT actor, payload_json FROM audit_log WHERE action = ? ORDER BY seq", (action,)
        )
    ]


@pytest.fixture(scope="module")
def audited(tmp_path_factory):
    conn, result = _audit(tmp_path_factory.mktemp("audited"))
    yield conn, result
    conn.close()


def test_the_step_is_off_by_default(tmp_path):
    conn, result = _audit(tmp_path, on=False)
    try:
        assert result.testability == {} and "C01" in result.not_tested
        assert _log(conn, testability.REPAIR_ACTION) == []
        assert "testability" not in pipeline.last_run(conn)["config"]
    finally:
        conn.close()


def test_a_claim_the_filler_tests_never_reaches_the_step(tmp_path, monkeypatch):
    """The step never adds to a claim that already has a core assumption."""
    monkeypatch.setitem(globals(), "BAD_C01", GOOD_C01)  # the first pass now passes
    conn, result = _audit(tmp_path)
    try:
        assert result.testability == {} and "C01" not in result.not_tested
        assert _log(conn, testability.REPAIR_ACTION) == []
    finally:
        conn.close()


def test_the_audit_logs_each_try_and_the_examiners_acceptance(audited):
    conn, result = audited
    assert "C01" not in result.not_tested
    (entry,) = [p for _a, p in _log(conn, testability.REPAIR_ACTION)]
    assert entry["claim_id"] == "C01" and entry["outcome"] == "proposed"
    assert entry["run_id"] == result.run_id and entry["testability"] == testability.VERSION
    (accepted,) = _log(conn, testability.ACCEPT_ACTION)
    assert accepted[0] == EXAMINER
    assert accepted[1]["assumption_ids"] == entry["assumption_ids"]
    kept = result.manifest["C01"]["assumptions"]
    assert kept == entry["assumption_ids"]
    assert pipeline.last_run(conn)["config"]["testability"] == testability.VERSION
    calls = conn.execute(
        "SELECT COUNT(*) FROM model_calls mc JOIN model_runs mr ON mr.id = mc.model_run_id"
        " WHERE mr.purpose = 'testability'"
    ).fetchone()[0]
    assert calls == 1


def test_a_proposal_without_an_examiner_leaves_the_claim_untested(tmp_path):
    conn, result = _audit(tmp_path, examiner=None)
    try:
        assert "C01" in result.not_tested
        assert result.manifest["C01"]["assumptions"] == []
        assert _log(conn, testability.ACCEPT_ACTION) == []
        assert [p["outcome"] for _a, p in _log(conn, testability.REPAIR_ACTION)] == ["proposed"]
    finally:
        conn.close()


def test_the_report_says_proposed_by_agent_accepted_by_examiner(audited):
    conn, _ = audited
    html = render_report(conn)
    assert html.count("Proposed by agent, accepted by examiner (Dana Reyes)") >= 1


# ---------------------------------------------------------------- the examiner's card


def _proposal(conn):  # noqa: ANN001, ANN202
    (x,) = testability.proposals(conn, pipeline.last_run(conn)).values()
    return x


def test_without_a_sheet_a_proposal_waits_for_the_examiner_and_the_next_audit_uses_it(
    tmp_path,
):
    from core.review.actions import ReviewError, decide_repair
    from core.review.status import claim_state

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        (entry,) = [p for _a, p in _log(conn, testability.REPAIR_ACTION)]
        assert (entry["check"], entry["outcome"]) == (testability.CLAIM_CHECK, "proposed")
        assert "C01" in first.not_tested and _log(conn, testability.ACCEPT_ACTION) == []
        x = _proposal(conn)
        assert x.decided is None and x.assumption_ids == sorted(entry["assumption_ids"])
        assert claim_state(conn, "C01").agent_waiting
        for actor, attempt, reason, why in (
            ("system", 1, "Read it.", "expert"),
            (EXAMINER, 1, " ", "say why"),
            (EXAMINER, 2, "Read it.", "no agent proposal"),
        ):
            with pytest.raises(ReviewError, match=why):
                decide_repair(conn, "C01", first.run_id, attempt, True, actor, reason)
        decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Item 1 is the phone.")
        assert _proposal(conn).decided == (testability.ACCEPT_ACTION, EXAMINER)
        assert not claim_state(conn, "C01").agent_waiting
        # Nothing is used until the next audit.
        assert pipeline.last_run(conn)["manifest"]["C01"]["assumptions"] == []
        second = pipeline.run_audit(
            conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"]
        )
        assert "C01" not in second.not_tested
        assert second.manifest["C01"]["assumptions"] == entry["assumption_ids"]
        (accepted,) = _log(conn, testability.ACCEPT_ACTION)  # the card's, not a new one
        assert accepted[0] == EXAMINER and accepted[1]["via"] == "claim page"
        assert "Proposed by agent, accepted by examiner (Dana Reyes)" in render_report(conn)
        assert not failed(_check(conn))
    finally:
        conn.close()


def test_a_rejected_proposal_is_never_used_and_the_latest_decision_stands(tmp_path):
    from core.review.actions import decide_repair

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Looks right.")
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "The number is not theirs.")
        assert _proposal(conn).decided == (testability.REJECT_ACTION, EXAMINER)
        second = pipeline.run_audit(
            conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"]
        )
        assert "C01" in second.not_tested and second.manifest["C01"]["assumptions"] == []
        assert not any(MARK in x for x in _shown(tmp_path, conn))
    finally:
        conn.close()


MARK = "Proposed by agent, accepted by examiner (Dana Reyes)"


def _shown(tmp_path: Path, conn) -> tuple[str, str]:  # noqa: ANN001
    """C01's claim page and the report, as the examiner sees them."""
    from ui.app import App, Request

    app = App(tmp_path / "case01.db", "Dana Reyes", 8765, model_check=None)
    host = {"host": "127.0.0.1:8765"}
    page = app.handle(Request("GET", "/claim", {"id": "C01"}, host)).body.decode()
    return page, render_report(conn)


def test_the_agent_mark_follows_the_decision_the_shown_audit_used(tmp_path):
    """One reading for the claim page and the report, for the audit shown: the acceptance that
    audit used, and a later rejection said beside it (Grok Product on #163)."""
    from core.review.actions import decide_repair

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Looks right.")
        assert not any(MARK in x for x in _shown(tmp_path, conn))  # nothing used yet
        pipeline.run_audit(conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"])
        page, report = _shown(tmp_path, conn)
        assert MARK in page and MARK in report
        assert "next audit does not use it" not in page + report
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "Not this number.")
        lapsed = MARK + "; later rejected by Dana Reyes, so the next audit does not use it"
        assert all(lapsed in x for x in _shown(tmp_path, conn))  # still true of the audit shown
        pipeline.run_audit(conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"])
        assert not any(MARK in x for x in _shown(tmp_path, conn))
        assert testability.used_repairs(conn, pipeline.last_run(conn)) == {}
        pipeline.run_audit(conn, _components(conn, on=False), claim_ids=["C01"])
        assert testability.used_repairs(conn, pipeline.last_run(conn)) == {}  # no step, no mark
    finally:
        conn.close()


def test_an_acceptance_does_not_carry_over_to_an_edited_claim(tmp_path):
    from core.review.actions import decide_repair

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Looks right.")
        pipeline.run_audit(conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"])
        (text,) = conn.execute("SELECT text FROM claims WHERE id = 'C01'").fetchone()
        set_claim_status(conn, "C01", ClaimStatus.EDITED, EXAMINER, text=text + " (as edited)")
        lapsed = (
            MARK + "; the claim was edited or removed after the acceptance, so the next audit "
            "does not use it"
        )
        assert all(lapsed in x for x in _shown(tmp_path, conn))
        third = pipeline.run_audit(
            conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"]
        )
        assert "C01" in third.not_tested and third.manifest["C01"]["assumptions"] == []
        page, report = _shown(tmp_path, conn)
        assert MARK not in page and MARK not in report and "Waiting for you" in page
    finally:
        conn.close()


def test_verify_bundle_fails_a_kept_proposal_whose_latest_decision_was_a_rejection(
    tmp_path, monkeypatch
):
    """An acceptance does not outlive a later rejection in verify-bundle either: a step that
    used the stale acceptance is caught (Codex on #163)."""
    from core.review.actions import decide_repair

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Looks right.")
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "Not this number.")
        with monkeypatch.context() as m:  # a step that reads only the first acceptance
            m.setattr(
                testability, "decision", lambda *a, **k: (testability.ACCEPT_ACTION, EXAMINER)
            )
            second = pipeline.run_audit(
                conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"]
            )
        assert second.manifest["C01"]["assumptions"]
        details = [f.detail for f in _check(conn) if f.level == FAIL]
        assert any("latest decision on them before the audit used them was a rejection" in d
                   for d in details)  # fmt: skip
    finally:
        conn.close()


def test_a_rejection_after_the_audit_used_a_proposal_does_not_fail_that_audit(tmp_path):
    from core.review.actions import decide_repair

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Looks right.")
        second = pipeline.run_audit(
            conn, _components(conn, examiner=None, signed=False), claim_ids=["C01"]
        )
        assert second.manifest["C01"]["assumptions"]
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "Not this number.")
        assert not failed(_check(conn))  # it was in force then; the next audit drops it
    finally:
        conn.close()


def test_a_proposal_for_a_claim_whose_text_changed_cannot_be_accepted(tmp_path):
    from core.review.actions import ReviewError, decide_repair

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    try:
        with conn:
            conn.execute("UPDATE claims SET text = text || ' (edited)' WHERE id = 'C01'")
        with pytest.raises(ReviewError, match="changed after the agent proposed"):
            decide_repair(conn, "C01", first.run_id, 1, True, EXAMINER, "Read it.")
    finally:
        conn.close()


def test_the_claim_page_shows_one_card_and_takes_one_decision(tmp_path):
    from ui.app import App, Request

    conn, first = _audit(tmp_path, examiner=None, signed=False)
    conn.close()
    app = App(tmp_path / "case01.db", "Dana Reyes", 8765, model_check=None)
    host = {"host": "127.0.0.1:8765"}
    page = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(host))).body.decode()
    card = page.split("<section class='agent' id='agent'>", 1)[1].split("</section>", 1)[0]
    assert testability.PROPOSED_MARK in card and "Waiting for you" in card
    assert card.count("value='accept'") == 1 and card.count("value='reject'") == 1
    assert "accept all" not in page.lower()
    form = {
        "token": app.token,
        "claim": "C01",
        "run": first.run_id,
        "attempt": "1",
        "decision": "accept",
        "reason": "Item 1 is the phone, as the claim says.",
        "next": "/claim?id=C01",
    }
    app.handle(Request("POST", "/testability/decide", {}, dict(host), form))
    page = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(host))).body.decode()
    assert "Accepted by Dana Reyes" in page and "Waiting for you" not in page
    c = sqlite3.connect(tmp_path / "case01.db")
    try:
        (accepted,) = _log(c, testability.ACCEPT_ACTION)
        assert accepted[0] == "expert:Dana Reyes"
        assert accepted[1]["reason"] == "Item 1 is the phone, as the claim says."
    finally:
        c.close()


def _export(conn, path: Path, include: str | list[str] = "all") -> Path:  # noqa: ANN001
    at = datetime(2026, 10, 20, 12, tzinfo=UTC)
    return export.export_bundle(
        conn, path, EXAMINER, counsel_confirmed=True, clock=lambda: at, include=include
    ).path


def _check(conn) -> list:  # noqa: ANN001
    out = verify_mod._Out()
    verify_mod._testability(conn, pipeline.view_run(conn), {"scope": export.FULL}, out)
    return out.items


def _copy(conn, folder: Path) -> sqlite3.Connection:  # noqa: ANN001
    """A copy whose log can be edited, to show what verify-bundle does with a forged one."""
    copy = sqlite3.connect(folder / "copy.db")
    conn.backup(copy)
    for (name,) in copy.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'audit_log'"
    ).fetchall():
        copy.execute(f'DROP TRIGGER "{name}"')
    return copy


def test_verify_bundle_re_runs_each_try_without_a_model(audited, tmp_path):
    conn, _ = audited
    findings = verify_bundle(_export(conn, tmp_path / "b.zip"))
    assert not failed(findings), [f for f in findings if f.level == FAIL]
    (f,) = [f for f in findings if f.check == "testability"]
    assert f.level == PASS and "same lookups and outcomes again, with no model" in f.detail


def test_a_bundle_without_the_steps_model_answers_notes_the_tries_unchecked(audited, tmp_path):
    """Records but no prompts: the repair calls are left out, so the tries are noted, not
    re-run, and the bundle still verifies (Codex on #159)."""
    conn, _ = audited
    findings = verify_bundle(_export(conn, tmp_path / "b.zip", include=["records"]))
    assert not failed(findings), [f for f in findings if f.level == FAIL]
    (f,) = [f for f in findings if f.check == "testability" and f.level == NOTE]
    assert "were not re-run" in f.detail and "include records and prompts" in f.detail


def test_a_claim_removed_after_the_audit_still_verifies(audited, tmp_path):
    """The removed claim's row stays in the bundle, and its tries re-run (Codex on #159)."""
    conn, _ = audited
    copy = _copy(conn, tmp_path)
    set_claim_status(copy, "C01", ClaimStatus.REMOVED, EXAMINER)
    found = _check(copy)
    copy.close()
    assert [f.level for f in found] == [PASS], found


def test_a_claim_edited_after_the_audit_still_verifies_its_tries(audited, tmp_path):
    """The tries re-run on the claim as it stood, rebuilt from the edit's log entry, not on the
    edited text (Codex on #163)."""
    conn, _ = audited
    copy = _copy(conn, tmp_path)
    set_claim_status(copy, "C01", ClaimStatus.EDITED, EXAMINER, text="Edited by the examiner.")
    found = _check(copy)
    copy.close()
    assert [f.level for f in found] == [PASS], found


def test_a_claim_row_changed_outside_the_log_fails(audited, tmp_path):
    conn, _ = audited
    copy = _copy(conn, tmp_path)
    copy.execute("UPDATE claims SET text = 'Changed with no log entry.' WHERE id = 'C01'")
    found = _check(copy)
    copy.close()
    assert any(f.level == FAIL and "another claim row" in f.detail for f in found), found


def test_a_logged_try_that_no_longer_follows_fails(audited, monkeypatch):
    conn, _ = audited
    monkeypatch.setattr(testability, "MAX_LOOKUPS", 0)  # code's lookups now find nothing
    assert any(f.level == FAIL for f in _check(conn))


def test_a_repair_kept_without_an_expert_acceptance_fails(audited, tmp_path):
    conn, _ = audited
    copy = _copy(conn, tmp_path)
    copy.execute("UPDATE audit_log SET actor = 'system' WHERE action = ?",
                 (testability.ACCEPT_ACTION,))  # fmt: skip
    found = _check(copy)
    copy.close()
    details = [f.detail for f in found if f.level == FAIL]
    assert any("not by an expert" in d for d in details)
    assert any("no expert accepted them" in d for d in details)


def test_repairs_logged_for_a_run_without_the_step_fail(audited, tmp_path):
    conn, result = audited
    copy = _copy(conn, tmp_path)
    cfg = json.loads(copy.execute("SELECT config_json FROM pipeline_runs WHERE id = ?",
                                  (result.run_id,)).fetchone()[0])  # fmt: skip
    del cfg["testability"]
    copy.execute("UPDATE pipeline_runs SET config_json = ? WHERE id = ?",
                 (json.dumps(cfg), result.run_id))  # fmt: skip
    found = _check(copy)
    copy.close()
    assert [f.level for f in found] == [FAIL]
    assert "did not run the step" in found[0].detail


# ---------------------------------------------------------------- the eval harness


def _eval_answers(prompt: str) -> str:
    if "Templates you may use for this claim" in prompt:
        return _answers(prompt)
    return '{"stance": "irrelevant", "quote": "", "rationale": "n"}'


def test_the_eval_reports_both_wrong_entity_rates_on_the_same_tries(capsys):
    """The claim-only check's rate leaves out "outside" tries. #159's rate counts them by what
    the sheet says of the names they gave, so the two can be compared until the go/no-go."""
    sheet = testability.Named(people=frozenset({"person:petrov", "person:reyes"}))
    other = testability.Named(people=frozenset({"person:someone-else"}))

    def tried(outcome: str, named: testability.Named) -> testability.Attempt:
        return testability.Attempt(1, None, [], [], outcome, [], named)

    rep = testability.Repair("C01", "sha", sheet, testability.SHEET_CHECK)
    rep.attempts = [
        tried("outside", testability.Named(people=frozenset({"person:reyes"}))),  # sheet agrees
        tried("outside", other),
        tried("outside", other),
        tried("mismatch", other),
        tried("proposed", sheet),
    ]
    step = SimpleNamespace(cap=5, seconds=0.0)
    t = rp.testability_summary(SimpleNamespace(testability={"C01": rep}), step, "case01", None)
    assert t["outside_the_claims_words"] == 3
    assert t["mismatch_person_phone_or_window"] == 2  # the two outside tries naming another
    assert t["wrong_entity_rate"] == 0.5  # 1 of the 2 tries the claim-only check let through
    assert t["wrong_entity_rate_without_the_claim_check"] == 0.6  # 3 of the 5
    rp.print_testability(t)
    printed = capsys.readouterr().out
    assert "the claim-only check, the sheet check rejected 50%" in printed
    assert "(#159's measure, the claim-only check aside), the sheet check rejects 60%" in printed


def test_the_eval_reports_the_measures_and_gives_no_go_no_go_until_arsh_sets_them(tmp_path, capsys):
    model = RuntimeFake(respond=_eval_answers)
    rp.run_once(
        "case01",
        "real",
        "accept",
        tmp_path,
        None,
        "simulated",
        labeler_model=model,
        claim_ids=["C01"],
        filler_model=model,
        testability_cap=1,
        testability_prompt=ROOT / "docs/prompts/agent_testability.md",
        testability_model=model,
    )
    t = json.loads((tmp_path / "run.json").read_text("utf-8"))["testability"]
    assert t["prompt"] == "DRAFT, not signed by Arsh" and t["cap"] == 1
    assert t["claims_the_filler_left_untested"] == 1
    assert t["of_them_the_sheet_makes_testable"] == 1 and t["converted_and_accepted"] == 1
    assert t["mismatch_person_phone_or_window"] == 0 and t["invalid_outputs"] == 0
    assert t["wrong_entity_rate"] == 0.0 and t["mismatch_other_only"] == 0
    assert t["wrong_entity_rate_without_the_claim_check"] == 0.0
    assert t["x_percent"] == 40.0 and t["y_budget"] == {"calls": 2, "seconds": 120}
    assert t["cap_set"] == 2 and t["min_testable"] == 15 and not t["go_no_go_case"]
    assert "an upper bound: the signed sheet filters every try" in capsys.readouterr().out
    r = rp.testability_go_no_go(
        t, expert="simulated", false_supported=0, repeat=None, gold="signed"
    )
    assert r["decision"] == "none given"
    assert r["why"] == [
        "the prompt is a draft",
        "this is not a held-out go/no-go case",
        "the run's cap is 1, not Arsh's 2",
        "the false-supported bar needs --expert rubber-stamp",
        "the byte-identical repeat needs --repeat",
    ]
    db = sqlite3.connect(tmp_path / "case01.db")
    try:  # the replay pass asked no model and reused the examiner's acceptance
        assert len(_log(db, testability.ACCEPT_ACTION)) == 1
        assert len(_log(db, testability.REPAIR_ACTION)) == 2  # one try, once per pass
    finally:
        db.close()


def test_with_no_expert_the_eval_never_accepts_a_repair(tmp_path):
    """--expert none: the repair is logged and never used (Codex on #159)."""
    model = RuntimeFake(respond=_eval_answers)
    rp.run_once("case01", "real", "accept", tmp_path, None, "none", labeler_model=model,
                claim_ids=["C01"], filler_model=model, testability_cap=1,
                testability_prompt=ROOT / "docs/prompts/agent_testability.md",
                testability_model=model)  # fmt: skip
    db = sqlite3.connect(tmp_path / "case01.db")
    try:
        assert _log(db, testability.ACCEPT_ACTION) == []
        assert [p["outcome"] for _a, p in _log(db, testability.REPAIR_ACTION)] == ["proposed"]
        kept = db.execute("SELECT COUNT(*) FROM assumptions WHERE claim_id = 'C01'").fetchone()
        assert kept[0] == 0
    finally:
        db.close()


def test_the_eval_never_runs_the_step_on_a_hidden_case(monkeypatch, capsys):
    """Held-out scores never hold gold-filtered repairs: refused before anything is read."""
    with pytest.raises(SystemExit, match="hidden case"):
        rp.testability_step(None, "case02", None, 1, None, "simulated")
    monkeypatch.setattr(rp, "is_hidden", lambda case: case == "case99")
    with pytest.raises(SystemExit, match="hidden case"):
        rp.testability_step(None, "case99", None, 1, None, "simulated")
    # The command line refuses before it builds the case or loads a model.
    with pytest.raises(SystemExit):
        rp.main(["--mode", "real", "--case", "case02", "--testability", "1"])
    assert "never runs on a hidden case" in capsys.readouterr().err


def test_the_eval_refuses_the_step_without_a_cap_or_outside_real_mode():
    with pytest.raises(SystemExit):
        rp.main(["--mode", "model-free", "--testability", "1"])
    with pytest.raises(SystemExit):
        rp.main(["--mode", "real", "--testability-prompt", "x.md"])
