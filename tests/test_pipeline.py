"""Pipeline skeleton on the synthetic case01, with eval stand-ins and test-only verdict rules."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core import pipeline
from core.audit import quotes
from core.audit.invariants import (
    InvariantViolation,
    check_evidence,
    check_report_text,
    record_text,
    record_text_before_76,
)
from core.contracts import (
    EvidenceCandidate,
    EvidenceStatus,
    Prediction,
    ProvenanceTier,
    SourceRef,
    Stance,
    StanceLabel,
    SupportedBasis,
    Verdict,
    VerdictDecision,
    verdict_id,
)
from core.db import connect
from core.enrich.records import get_record
from core.report.html import SUPPORTED_AI, SUPPORTED_EXPERT, render_report, write_report
from core.review import actions, audit_log
from eval import run_pipeline
from eval.pipeline_fakes import (
    InconclusiveCheck,
    PhraseLabeler,
    QuotedPhraseRetriever,
    exact_substring,
    fake_components,
)

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)
EXPERT = "expert:test"


def _clock() -> datetime:
    return NOW


@pytest.fixture(scope="module")
def built_case(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("case") / "case01.db"
    run_pipeline.build_case("case01", path).close()  # type: ignore[attr-defined]
    return path


@pytest.fixture
def conn(built_case, tmp_path) -> sqlite3.Connection:
    copy = tmp_path / "case.db"
    shutil.copy(built_case, copy)
    c = connect(copy)
    yield c
    c.close()


def supporting_rule(lie_about_basis: bool = False):
    """Test-only rule: SUPPORTED when any supporting item is accepted, citing those items."""

    def rule(claim, assumptions, evidence, checks, stipulations, pipeline_run_id):
        ok = [
            e
            for e in evidence
            if e.stance == Stance.SUPPORTS
            and e.status in (EvidenceStatus.AI_ACCEPTED, EvidenceStatus.ACCEPTED)
        ]
        if not ok:
            verdict, basis = Verdict.UNPROVEN, None
        else:
            verdict = Verdict.SUPPORTED
            expert = all(e.status == EvidenceStatus.ACCEPTED for e in ok)
            basis = (
                SupportedBasis.CONFIRMED
                if expert or lie_about_basis
                else SupportedBasis.AI_REVIEWED
            )
        return VerdictDecision(
            id=verdict_id(claim.id, pipeline_run_id),
            claim_id=claim.id,
            pipeline_run_id=pipeline_run_id,
            verdict=verdict,
            supported_basis=basis,
            rule_version="test",
            reasons=("test rule",),
            cited_evidence_ids=tuple(e.id for e in ok),
            decided_at_utc=NOW,
        )

    return rule


def comps(**kw):
    c = fake_components(accept=kw.pop("accept", True))
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def items(conn, claim_id="C01"):
    run = pipeline.last_run(conn)
    return pipeline.load_evidence(conn, run["manifest"][claim_id]["evidence"])


def test_fake_run_covers_every_gold_claim(conn):
    c = comps()
    result = pipeline.run_audit(conn, c, clock=_clock)
    assert result.fake
    assert len(result.decisions) == 20
    if c.rules_pending():
        assert {d.verdict for d in result.decisions} == {Verdict.UNPROVEN}
        assert all(pipeline.RULES_PENDING_REASON in d.reasons for d in result.decisions)
    preds = pipeline.predictions(conn)
    assert [p.claim_id for p in preds] == [f"C{i:02d}" for i in range(1, 21)]
    assert conn.execute("SELECT status FROM pipeline_runs").fetchone()[0] == "completed"
    assert audit_log.verify_chain(conn)


def test_ai_reviewed_support_is_never_shown_as_confirmed(conn):
    pipeline.run_audit(conn, comps(rule=supporting_rule()), clock=_clock, claim_ids=["C01"])
    v = pipeline.load_verdict(conn, "C01", pipeline.last_run(conn)["run_id"])
    assert v.verdict == Verdict.SUPPORTED and v.supported_basis == SupportedBasis.AI_REVIEWED
    html = render_report(conn)
    assert SUPPORTED_AI in html and f'"verdict v-sup">{SUPPORTED_EXPERT}' not in html
    assert "ai_reviewed" in html


def test_rule_that_claims_confirmed_for_ai_reviewed_support_stops_the_run(conn):
    with pytest.raises(InvariantViolation, match="AI-reviewed never shows as confirmed"):
        pipeline.run_audit(
            conn, comps(rule=supporting_rule(lie_about_basis=True)), clock=_clock, claim_ids=["C01"]
        )
    status, note = conn.execute("SELECT status, note FROM pipeline_runs").fetchone()
    assert status == "failed" and "supported_basis" in note
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM evidence_items").fetchone()[0] == 0


def test_expert_acceptance_makes_it_expert_confirmed(conn):
    pipeline.run_audit(conn, comps(rule=supporting_rule()), clock=_clock, claim_ids=["C01"])
    (item,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    actions.decide_evidence(conn, item.id, EvidenceStatus.ACCEPTED, EXPERT, "Seen in the sheet.")
    pipeline.run_audit(conn, comps(rule=supporting_rule()), clock=_clock, claim_ids=["C01"])
    v = pipeline.load_verdict(conn, "C01", pipeline.last_run(conn)["run_id"])
    assert v.supported_basis == SupportedBasis.CONFIRMED
    assert SUPPORTED_EXPERT in render_report(conn)


def test_expert_dismissal_overrides_the_ai_on_every_rerun(conn):
    pipeline.run_audit(conn, comps(rule=supporting_rule()), clock=_clock, claim_ids=["C01"])
    (item,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    assert item.status == EvidenceStatus.AI_ACCEPTED
    actions.decide_evidence(conn, item.id, EvidenceStatus.DISMISSED, EXPERT, "Wrong contact.")
    pipeline.run_audit(conn, comps(rule=supporting_rule()), clock=_clock, claim_ids=["C01"])
    (again,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    assert again.id == item.id and again.status == EvidenceStatus.DISMISSED
    kinds = [r[0] for r in conn.execute("SELECT reviewer_kind FROM evidence_reviews ORDER BY seq")]
    assert kinds == ["ai", "expert"]
    v = pipeline.load_verdict(conn, "C01", pipeline.last_run(conn)["run_id"])
    assert v.verdict == Verdict.UNPROVEN


def test_unverified_quote_is_dropped_and_never_stored(conn):
    class Paraphraser(PhraseLabeler):
        def label(self, assumption, candidate):
            real = super().label(assumption, candidate)
            return real.model_copy(update={"quote": real.quote + " (paraphrased)"})

    result = pipeline.run_audit(conn, comps(labeler=Paraphraser()), clock=_clock, claim_ids=["C01"])
    assert result.dropped_labels >= 1 and result.stored_items == 0
    assert conn.execute("SELECT COUNT(*) FROM evidence_items").fetchone()[0] == 0
    halted = conn.execute("SELECT COUNT(*) FROM audit_log WHERE payload_json LIKE '%paraphrased%'")
    assert halted.fetchone()[0] == 0


def test_label_for_another_record_is_dropped(conn):
    class Wrong(PhraseLabeler):
        def label(self, assumption, candidate) -> StanceLabel:
            return super().label(assumption, candidate).model_copy(update={"record_id": "msg:x"})

    result = pipeline.run_audit(conn, comps(labeler=Wrong()), clock=_clock, claim_ids=["C01"])
    assert result.stored_items == 0 and result.dropped_labels >= 1


def test_a_quote_copied_from_the_contact_as_shown_is_kept(conn):
    # Regression (scoring audit, 2026-10-15): retrieval shows the labeler a contact as
    # "Marc Garage: +12125550122", but the quote check read it as "Marc Garage +12125550122",
    # so a model that copied what it saw had its right answer dropped.
    class CopiesWhatItSaw(PhraseLabeler):
        def label(self, assumption, candidate):
            real = super().label(assumption, candidate)
            if not candidate.record_id.startswith("contact:"):
                return real
            shown = get_record(conn, candidate.record_id).text
            return real.model_copy(update={"stance": Stance.SUPPORTS, "quote": shown})

    pipeline.run_audit(conn, comps(labeler=CopiesWhatItSaw()), clock=_clock, claim_ids=["C01"])
    (kept,) = [e for e in items(conn) if e.record_id.startswith("contact:")]
    assert kept.quote == "Marc Garage: +12125550122" and kept.stance == Stance.SUPPORTS
    assert record_text(conn, kept.record_id) == get_record(conn, kept.record_id).text


def test_every_record_reads_the_same_for_the_labeler_and_the_quote_check(conn):
    for table in ("messages", "calls", "contacts", "attachments"):
        for (rid,) in conn.execute(f"SELECT id FROM {table}"):  # noqa: S608
            assert record_text(conn, rid) == get_record(conn, rid).text, rid


@pytest.mark.parametrize("other", ["contact:item1:Contacts!4#1", "call:item1:Call Log!10"])
def test_a_record_that_contradicts_quoted_as_shown_keeps_the_claim_from_supported(conn, other):
    # Regression (#69): the quote check drops a label before its stance is used. While it read
    # contacts and calls differently from what the labeler saw, a "contradicts" copied from one
    # was dropped, and a claim with other expert-accepted support could go SUPPORTED.
    table = {"contact": "contacts", "call": "calls"}[other.split(":", 1)[0]]
    source_id, locator = conn.execute(
        f"SELECT source_id, locator FROM {table} WHERE id = ?",  # noqa: S608
        (other,),
    ).fetchone()

    class PlusContact(QuotedPhraseRetriever):
        def retrieve(self, assumption, conn, k):
            extra = EvidenceCandidate(
                record_id=other,
                ref=SourceRef(source_id=source_id, locator=locator),
                text=get_record(conn, other).text,
                tier=ProvenanceTier.OBSERVED,
                retrieval_score=0.5,
            )
            return [*super().retrieve(assumption, conn, k), extra]

    class Contrarian(PhraseLabeler):
        def label(self, assumption, candidate):
            if candidate.record_id != other:
                return super().label(assumption, candidate)
            return StanceLabel(
                assumption_id=assumption.id,
                record_id=other,
                stance=Stance.CONTRADICTS,
                quote=get_record(conn, other).text,
                rationale="test",
                model_run_id="mr:fake-stance",
            )

    def run():
        c = comps(retriever=PlusContact(), labeler=Contrarian())
        return pipeline.run_audit(conn, c, clock=_clock, claim_ids=["C01"])

    run()
    (support,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    actions.decide_evidence(conn, support.id, EvidenceStatus.ACCEPTED, EXPERT, "Seen in the sheet.")
    result = run()
    (against,) = [e for e in items(conn) if e.stance == Stance.CONTRADICTS]
    assert against.record_id == other and result.dropped_labels == 0
    assert result.decisions[0].verdict == Verdict.CONTRADICTED
    # The record is all that stands between this claim and SUPPORTED: only an expert removes it.
    actions.decide_evidence(conn, against.id, EvidenceStatus.DISMISSED, EXPERT, "Another person.")
    assert run().decisions[0].verdict == Verdict.SUPPORTED


def test_evidence_stored_before_the_fix_still_passes_the_stored_quote_check(conn):
    # Codex on #76: a case audited before #76 holds contact and call quotes in the check's old
    # text. Re-deciding it (core.review.redecide) re-checks them and must not stop on them.
    pipeline.run_audit(conn, comps(), clock=_clock, claim_ids=["C01"])
    (item,) = [e for e in items(conn) if e.record_id.startswith("contact:")]
    call = "call:item1:Call Log!10"
    old_call = (
        "incoming call from +12125550133 to +12125550111 at 3/10/2026 8:30:17 PM(UTC+0), 434s"
    )
    check_evidence(
        conn,
        [
            item.model_copy(update={"quote": "Marc Garage +12125550122"}),
            item.model_copy(update={"record_id": call, "quote": old_call}),
        ],
    )
    # Held to the check of its day (Codex): only Baker's words, but a substring of the old text.
    check_evidence(conn, [item.model_copy(update={"record_id": call, "quote": "call from"})])
    for rid, quote in ((item.record_id, "Marc Garage +1 212"), (call, "outgoing call from")):
        with pytest.raises(InvariantViolation, match="not verbatim"):
            check_evidence(conn, [item.model_copy(update={"record_id": rid, "quote": quote})])


NAMELESS = "contact:item1:Contacts!4#1"
CALL = "call:item1:Call Log!10"


@pytest.mark.parametrize(
    ("other", "quote", "kept"),
    [
        (NAMELESS, "(no name)", False),
        (NAMELESS, "no name", False),
        (NAMELESS, "(no name): ", False),
        (NAMELESS, "SHOWN", True),
        (NAMELESS, "IDENTIFIER", True),
        (CALL, "call from", False),
        (CALL, ", duration", False),
        (CALL, "SHOWN", True),
        (CALL, "DIRECTION", True),
    ],
)
def test_a_quote_of_only_bakers_words_or_a_placeholder_is_dropped(conn, other, quote, kept):
    # Grok review on #80, item 3: once the check reads a record as the labeler sees it, a quote
    # of "(no name)" or of a call line's own words ("call from") is a verbatim substring of
    # nothing the record holds. It must not verify; a quote that reaches the record's fields does.
    with conn:
        conn.execute("UPDATE contacts SET name = NULL WHERE id = ?", (NAMELESS,))
    table = {"contact": "contacts", "call": "calls"}[other.split(":", 1)[0]]
    source_id, locator = conn.execute(
        f"SELECT source_id, locator FROM {table} WHERE id = ?",  # noqa: S608
        (other,),
    ).fetchone()
    shown = get_record(conn, other).text
    quote = {"SHOWN": shown, "IDENTIFIER": shown.split(": ", 1)[-1]}.get(quote, quote)
    quote = shown.split(" ", 1)[0] if quote == "DIRECTION" else quote
    assert quote in shown

    class PlusOther(QuotedPhraseRetriever):
        def retrieve(self, assumption, conn, k):
            extra = EvidenceCandidate(
                record_id=other,
                ref=SourceRef(source_id=source_id, locator=locator),
                text=shown,
                tier=ProvenanceTier.OBSERVED,
                retrieval_score=0.5,
            )
            return [*super().retrieve(assumption, conn, k), extra]

    class Contrarian(PhraseLabeler):
        def label(self, assumption, candidate):
            if candidate.record_id != other:
                return super().label(assumption, candidate)
            return StanceLabel(
                assumption_id=assumption.id,
                record_id=other,
                stance=Stance.CONTRADICTS,
                quote=quote,
                rationale="test",
                model_run_id="mr:fake-stance",
            )

    c = comps(retriever=PlusOther(), labeler=Contrarian())
    result = pipeline.run_audit(conn, c, clock=_clock, claim_ids=["C01"])
    stored = [e for e in items(conn) if e.record_id == other]
    assert result.dropped_labels == (0 if kept else 1)
    assert [e.quote for e in stored] == ([quote] if kept else [])
    # The stored re-check holds the same line, except that evidence stored before #76 keeps the
    # check of its day (Codex): "call from" was a substring of the old call text.
    (item,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    stored = item.model_copy(update={"record_id": other, "quote": quote})
    if kept or quote in record_text_before_76(conn, other):
        check_evidence(conn, [stored])
    else:
        with pytest.raises(InvariantViolation, match="not verbatim"):
            check_evidence(conn, [stored])


@pytest.mark.parametrize(
    ("verifier", "recorded"),
    [
        (quotes.verify_quote, "1.2.0"),
        (exact_substring, "1.2.0 and eval.pipeline_fakes.exact_substring"),
    ],
)
def test_every_run_records_the_quote_check_that_ran(conn, verifier, recorded):
    # Codex on #76: a caller's config must not overwrite the check that ran, and a run with
    # another verifier must not claim the product's alone.
    c = comps(verify_quote=verifier)
    pipeline.run_audit(conn, c, clock=_clock, claim_ids=["C01"], config={"quote_check": "9.9.9"})
    assert quotes.VERSION == "1.2.0"
    assert pipeline.last_run(conn)["config"]["quote_check"] == recorded
    assert f"quote check {recorded}" in render_report(conn)


def test_another_verifier_cannot_pass_a_quote_the_product_refuses(conn):
    # The eval's stand-in matches inside words; the product's own rule still runs beside it.
    shown = get_record(conn, CALL).text
    cut = shown[1:9]  # starts and ends inside a word
    assert exact_substring(cut, shown) and not quotes.verify_quote(cut, shown)
    rec = get_record(conn, CALL)
    assert not quotes.cites_record(cut, rec.text, rec.own)


def test_reviewer_failure_is_a_dismissal_and_reviewer_never_sees_the_rationale(conn):
    seen: list[str] = []

    class Broken:
        model_run_id = "mr:fake-review"

        def review(self, assumption, item, context):
            seen.append(item.rationale)
            raise RuntimeError("model crashed")

    result = pipeline.run_audit(
        conn, comps(reviewer=Broken(), rule=supporting_rule()), clock=_clock, claim_ids=["C01"]
    )
    assert seen == [""]
    assert result.reviewer_failures == 1
    (item,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    assert item.status == EvidenceStatus.DISMISSED
    assert result.decisions[0].verdict == Verdict.UNPROVEN


def test_unreviewable_items_stay_open_for_the_expert(conn):
    pipeline.run_audit(
        conn,
        comps(reviewable=lambda item: False, rule=supporting_rule()),
        clock=_clock,
        claim_ids=["C01"],
    )
    (item,) = [e for e in items(conn) if e.stance == Stance.SUPPORTS]
    assert item.status == EvidenceStatus.OPEN
    assert conn.execute("SELECT COUNT(*) FROM evidence_reviews").fetchone()[0] == 0


def test_supported_with_open_contradiction_stops_the_run(conn):
    class PlusOne(QuotedPhraseRetriever):
        def retrieve(self, assumption, conn, k):
            extra = EvidenceCandidate(
                record_id="msg:item1:Chats!3",
                ref=SourceRef(source_id="item1", locator="Chats!3"),
                text=record_text(conn, "msg:item1:Chats!3"),
                tier=ProvenanceTier.OBSERVED,
                retrieval_score=0.5,
            )
            return [*super().retrieve(assumption, conn, k), extra]

    class Contrarian(PhraseLabeler):
        def label(self, assumption, candidate):
            if candidate.record_id.startswith("contact:"):
                return super().label(assumption, candidate)
            return StanceLabel(
                assumption_id=assumption.id,
                record_id=candidate.record_id,
                stance=Stance.CONTRADICTS,
                quote=candidate.text,  # the whole record: the product's quote rule runs too
                rationale="test",
                model_run_id="mr:fake-stance",
            )

    # supporting_rule is deliberately wrong here: it ignores the open contradiction.
    with pytest.raises(InvariantViolation, match="contradicting or complicating"):
        pipeline.run_audit(
            conn,
            comps(retriever=PlusOne(), labeler=Contrarian(), rule=supporting_rule()),
            clock=_clock,
            claim_ids=["C01"],
        )


def test_report_lists_stipulations_and_avoids_forbidden_words(conn, tmp_path):
    pipeline.run_audit(conn, comps(), clock=_clock)
    html = write_report(conn, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Device ownership is a stipulation, not a finding." in html
    assert "Daniel Petrov used" in html and "Marcus Reyes used" in html
    assert "Test run with stand-in components." in html
    assert "<script" not in html and "http" not in html.replace("http-equiv", "")


def test_forbidden_words_outside_quotes_are_caught():
    check_report_text('<p>cited: <span class="q">he deleted it</span></p>')
    with pytest.raises(InvariantViolation):
        check_report_text("<p>The messages were deleted.</p>")


def test_an_experts_own_words_are_exempt_and_nothing_else_is():
    check_report_text(
        '<p>Dismissed by expert:A: <span class="said">not deleted, only hidden</span></p>'
    )
    with pytest.raises(InvariantViolation):
        check_report_text('<p><span class="said">their reason</span>, so it was deleted.</p>')
    with pytest.raises(InvariantViolation):
        check_report_text('<p><span class="said" title="x">deleted</span></p>')


def test_cli_audit_review_and_report(conn, tmp_path):
    db = Path(conn.execute("PRAGMA database_list").fetchone()[2])
    assert cli_main(["audit", "--db", str(db)]) == 2  # real components not built yet
    assert cli_main(["audit", "--db", str(db), "--fake"]) == 0
    out = tmp_path / "report.html"
    assert cli_main(["report", "--db", str(db), "--out", str(out)]) == 0
    assert "Baker claims report" in out.read_text(encoding="utf-8")
    assert (
        cli_main(["verdict", "--db", str(db), "--claim", "C01", "--confirm", "--by", EXPERT]) == 0
    )
    assert cli_main(["verdict", "--db", str(db), "--claim", "C01", "--confirm", "--by", "x"]) == 2
    assert cli_main(["verify-log", "--db", str(db)]) == 0


def test_repeat_runs_on_fresh_databases_give_identical_predictions(tmp_path):
    a = run_pipeline.run_once("case01", "fake", "accept", tmp_path / "a")
    b = run_pipeline.run_once("case01", "fake", "accept", tmp_path / "b")
    assert a == b and len(a) == 20


def test_checks_run_only_where_they_apply(conn):
    class Picky(InconclusiveCheck):
        name = "picky"

        def applies_to(self, assumption):
            return False

    pipeline.run_audit(conn, comps(checks=(Picky(),)), clock=_clock, claim_ids=["C01"])
    assert conn.execute("SELECT COUNT(*) FROM check_results").fetchone()[0] == 0


def test_hostile_gate_fails_only_on_structural_claims(monkeypatch):
    import sys
    import types

    blocks = types.ModuleType("eval.adversarial.structural_blocks")
    blocks.STRUCTURAL, blocks.MODEL_ONLY = ("C04",), ("C06",)
    monkeypatch.setitem(sys.modules, "eval.adversarial", types.ModuleType("eval.adversarial"))
    monkeypatch.setitem(sys.modules, "eval.adversarial.structural_blocks", blocks)
    sup = SupportedBasis.AI_REVIEWED
    model_only = [Prediction(claim_id="C06", verdict=Verdict.SUPPORTED, supported_basis=sup)]
    assert run_pipeline.hostile_gate(model_only) == 0
    breach = [Prediction(claim_id="C04", verdict=Verdict.SUPPORTED, supported_basis=sup)]
    assert run_pipeline.hostile_gate(breach) == 1


def _one_message_case(conn, contradict_named: bool):
    """C05 with a real "sender" assumption: the named message plus one other message, both
    labeled contradicts unless contradict_named is False (then the named one supports)."""
    from core.audit.assumptions import instantiate

    (named,) = conn.execute(
        "SELECT id FROM messages WHERE body = 'need 2 more by friday'"
    ).fetchall()[0:1]
    other = "msg:item1:Chats!3"
    sender = instantiate(
        "C05",
        "sender",
        {"quoted_text": "need 2 more by friday", "person_ids": ["person:petrov"]},
        True,
    )

    class Builder:
        def build(self, claim):
            return [sender]

    class Two:
        def retrieve(self, assumption, conn, k):
            return [
                EvidenceCandidate(
                    record_id=rid,
                    ref=SourceRef(source_id=rid.split(":")[1], locator=rid.split(":", 2)[2]),
                    text=record_text(conn, rid),
                    tier=ProvenanceTier.OBSERVED,
                    retrieval_score=1.0,
                )
                for rid in (named[0], other)
            ]

    class Contrarian(PhraseLabeler):
        def label(self, assumption, candidate):
            is_named = candidate.record_id == named[0]
            return StanceLabel(
                assumption_id=assumption.id,
                record_id=candidate.record_id,
                stance=Stance.CONTRADICTS if contradict_named or not is_named else Stance.SUPPORTS,
                quote=candidate.text.split()[0],
                rationale="a different sender",
                model_run_id="mr:fake-stance",
            )

    result = pipeline.run_audit(
        conn,
        comps(assumptions=Builder(), retriever=Two(), labeler=Contrarian(), reviewer=None),
        clock=_clock,
        claim_ids=["C05"],
    )
    by_record = {e.record_id: e for e in items(conn, "C05")}
    return result.decisions[0], by_record[named[0]], by_record[other]


def test_another_message_never_contradicts_a_one_message_assumption(conn):
    decision, named, other = _one_message_case(conn, contradict_named=False)
    assert named.stance == Stance.SUPPORTS
    assert other.stance == Stance.COMPLICATES  # kept for the expert, not a contradiction
    assert other.rationale.startswith("Recorded as complicates, not contradicts")
    assert other.rationale.endswith("a different sender")
    assert decision.verdict == Verdict.UNPROVEN
    (raw,) = conn.execute(
        "SELECT stance FROM evidence_items WHERE record_id = ?", (other.record_id,)
    ).fetchone()
    assert raw == Stance.COMPLICATES.value


def test_the_named_message_itself_still_contradicts(conn):
    decision, named, other = _one_message_case(conn, contradict_named=True)
    assert named.stance == Stance.CONTRADICTS
    assert other.stance == Stance.COMPLICATES
    assert decision.verdict == Verdict.CONTRADICTED
