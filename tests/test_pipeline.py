"""Pipeline skeleton on the synthetic case01, with eval stand-ins and test-only verdict rules."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.main import main as cli_main
from core import pipeline
from core.audit.invariants import InvariantViolation, check_report_text, record_text
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
from core.report.html import SUPPORTED_AI, SUPPORTED_EXPERT, render_report, write_report
from core.review import actions, audit_log
from eval import run_pipeline
from eval.pipeline_fakes import (
    InconclusiveCheck,
    PhraseLabeler,
    QuotedPhraseRetriever,
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
                quote=candidate.text[:5],
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
