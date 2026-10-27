"""The challenge step (core/audit/challenge.py): code's counter-searches on claims close to
SUPPORTED, storing only doubt, each search logged and re-run by verify-bundle without a model.
Synthetic case01 only; case02 is the held-out case and is never used here."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core import pipeline
from core.audit import challenge, invariants
from core.bundle import export
from core.bundle import verify as verify_mod
from core.bundle.verify import FAIL, NOTE, PASS, failed, verify_bundle
from core.contracts import (
    Assumption,
    AssumptionKind,
    AssumptionParams,
    CheckOutcome,
    CheckResult,
    EvidenceItem,
    EvidenceStatus,
    GoldClaim,
    ProvenanceTier,
    SourceRef,
    Stance,
)
from core.hypotheses import explain
from core.review import audit_log
from eval import run_pipeline as rp
from eval.run_eval import load_jsonl
from eval.simulated_expert import (
    RUBBER_STAMP,
    GoldDirectionLabeler,
    GoldKey,
    rubber_stamp_review,
)

EXPERT = "expert:Dana Reyes"
AT = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _case(folder: Path, challenge_on: bool = True, labeler=None):  # noqa: ANN001, ANN202
    conn = rp.build_case("case01", folder / "case01.db")
    gold = GoldKey(load_jsonl(rp.gold_path("case01"), GoldClaim))
    comps = rp.model_free_components(conn, rp.assumption_sheet("case01"), gold)
    if labeler is not None:
        comps.labeler = labeler(comps.labeler)
    comps.challenge = challenge_on
    return conn, comps


def _entries(conn) -> list[dict]:  # noqa: ANN001
    return [
        json.loads(p)
        for (p,) in conn.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq",
            (challenge.QUERY_ACTION,),
        )
    ]


class _Doubting:
    """The model-free labeler, with the stance given for the records named."""

    model_runs = GoldDirectionLabeler.model_runs

    def __init__(self, inner, stances: dict[str, Stance]) -> None:  # noqa: ANN001
        self.inner = inner
        self.stances = stances

    def label(self, assumption, candidate):  # noqa: ANN001, ANN201
        out = self.inner.label(assumption, candidate)
        stance = self.stances.get(candidate.record_id)
        return out if stance is None else out.model_copy(update={"stance": stance})


@pytest.fixture(scope="module")
def challenged(tmp_path_factory):  # noqa: ANN201
    """case01, model-free, with the challenge step on and its real searches."""
    folder = tmp_path_factory.mktemp("challenged")
    conn, comps = _case(folder)
    result = pipeline.run_audit(conn, comps)
    yield conn, result, folder
    conn.close()


# ---------------------------------------------------------------- which claims, what is kept


def _a(aid: str, core: bool = True) -> Assumption:
    return Assumption(
        id=aid,
        claim_id="C01",
        kind=AssumptionKind.IDENTITY,
        template_id="sender",
        template_version="0",
        params=AssumptionParams(),
        text="t",
        is_core=core,
        tier=ProvenanceTier.INFERRED,
    )


def _check(aid: str, outcome: CheckOutcome) -> CheckResult:
    return CheckResult(
        id=f"ck:{aid}",
        assumption_id=aid,
        check_name="sender",
        check_version="0",
        outcome=outcome,
        searched="s",
        detail="d",
    )


def _item(aid: str, stance: Stance) -> EvidenceItem:
    return EvidenceItem(
        id=f"ev:{aid}:{stance.value}",
        assumption_id=aid,
        record_id="msg:x",
        ref=SourceRef(source_id="item1", locator="Chats!1"),
        stance=stance,
        quote="q",
        quote_verified=True,
        rationale="",
        tier=ProvenanceTier.OBSERVED,
        status=EvidenceStatus.OPEN,
        model_run_id="mr:x",
    )


def test_a_claim_is_close_to_supported_only_when_every_core_assumption_is_covered():
    a1, a2, side = _a("a1"), _a("a2"), _a("a3", core=False)
    passed = [_check("a1", CheckOutcome.PASS)]
    supports = [_item("a2", Stance.SUPPORTS)]
    assert challenge.near_supported([a1, a2, side], passed, supports)
    assert not challenge.near_supported([a1, a2], passed, [])
    assert not challenge.near_supported(
        [a1, a2], [_check("a1", CheckOutcome.INCONCLUSIVE)], supports
    )
    assert not challenge.near_supported([a1, a2], passed, [_item("a2", Stance.COMPLICATES)])
    assert not challenge.near_supported([side], [], [])  # no core assumption: nothing to undercut


def test_only_contradicts_and_complicates_are_kept():
    assert {s for s in Stance if challenge.keep(_item("a", s))} == {
        Stance.CONTRADICTS,
        Stance.COMPLICATES,
    }


def test_the_invariant_fails_on_any_other_item():
    invariants.check_challenge([_item("a", Stance.CONTRADICTS), _item("a", Stance.COMPLICATES)])
    for stance in (Stance.SUPPORTS, Stance.IRRELEVANT):
        with pytest.raises(invariants.InvariantViolation, match="stores only"):
            invariants.check_challenge([_item("a", stance)])


# ---------------------------------------------------------------- off by default


def test_the_step_is_off_by_default(tmp_path):
    assert pipeline.Components.__dataclass_fields__["challenge"].default is False
    conn, comps = _case(tmp_path, challenge_on=False)
    result = pipeline.run_audit(conn, comps)
    assert result.challenge == {} and _entries(conn) == []
    assert "challenge" not in pipeline.view_run(conn)["config"]
    conn.close()


# ---------------------------------------------------------------- the searches


def test_each_challenged_claim_logs_every_search_even_one_that_found_nothing(challenged):
    conn, result, _ = challenged
    entries = _entries(conn)
    assert result.challenge and len(entries) == sum(len(v) for v in result.challenge.values())
    run = pipeline.view_run(conn)
    assert run["config"]["challenge"] == challenge.VERSION
    for p in entries:
        assert p["run_id"] == result.run_id and p["claim_id"] in result.challenge
        assert (p["challenge"], p["explain"]) == (challenge.VERSION, explain.VERSION)
        assert p["searched"]  # what was searched, even when nothing was found
        assert set(p) >= {"kind", "assumption_ids", "record_ids", "total", "stored"}
    # Only claims close to supported are challenged, and each says something was asked.
    for claim_id, es in result.challenge.items():
        items = run["manifest"][claim_id]
        assumptions = pipeline.load_assumptions(conn, items["assumptions"])
        assert challenge.near_supported(
            assumptions,
            pipeline.load_checks(conn, items["checks"]),
            pipeline.load_evidence(conn, items["evidence"]),
        )
        assert es
    settled = {d.claim_id for d in result.decisions if d.verdict.value == "contradicted"}
    assert not settled & set(result.challenge)


def test_a_search_that_finds_nothing_is_kept_only_when_asked(challenged):
    conn, result, _ = challenged
    case = explain.load(conn)
    run = pipeline.view_run(conn)
    for claim_id in result.challenge:
        assumptions = pipeline.load_assumptions(conn, run["manifest"][claim_id]["assumptions"])
        shown = explain.alternatives(case, assumptions)
        every = explain.alternatives(case, assumptions, keep_empty=True)
        assert all(alt.total for alt in shown)  # the report's leads: only what a record fits
        assert [a.kind for a in shown] == [a.kind for a in every if a.total]
        for alt in every:
            assert alt.searched and alt.assumption_ids


class _EmptyCase:
    pass


@pytest.fixture
def no_alternatives(monkeypatch):  # noqa: ANN201
    monkeypatch.setattr(explain, "alternatives", lambda case, assumptions, keep_empty=False: [])


def test_a_claim_no_search_applies_to_still_logs_that_nothing_was_searched(no_alternatives):
    (q,) = challenge.queries(_EmptyCase(), [_a("a1"), _a("a2", core=False)])
    assert (q.kind, q.record_ids, q.total, q.assumption_ids) == ("none", (), 0, ("a1",))
    assert q.searched == challenge.NO_SEARCH


# ---------------------------------------------------------------- what is stored


def _two_records(conn, claim_id: str) -> list[str]:  # noqa: ANN001
    """Two messages with text that the claim's retrieval did not send to the labeler."""
    run = pipeline.view_run(conn)
    seen = {
        e.record_id for e in pipeline.load_evidence(conn, run["manifest"][claim_id]["evidence"])
    }
    rows = conn.execute(
        "SELECT id FROM messages WHERE body GLOB '*[A-Za-z]*' ORDER BY id"
    ).fetchall()
    return [r for (r,) in rows if r not in seen][:2]


def test_only_doubt_from_the_searches_is_stored(tmp_path, challenged, monkeypatch):
    base_conn, base, _ = challenged
    claim_id = sorted(base.challenge)[0]
    doubt, support = _two_records(base_conn, claim_id)

    def queries(case, assumptions):  # noqa: ANN001, ANN202
        core = tuple(a.id for a in assumptions if a.is_core)
        return [challenge.Query("other_app", core[:1], "test search", (doubt, support), 2)]

    monkeypatch.setattr(challenge, "queries", queries)
    stances = {doubt: Stance.COMPLICATES, support: Stance.SUPPORTS}
    conn, comps = _case(tmp_path, labeler=lambda inner: _Doubting(inner, stances))
    result = pipeline.run_audit(conn, comps)
    (entry, *_) = result.challenge[claim_id]
    assert (len(entry["stored"]), entry["discarded"], entry["dropped"]) == (1, 1, 0)
    (eid,) = entry["stored"]
    (stance, record) = conn.execute(
        "SELECT stance, record_id FROM evidence_items WHERE id = ?", (eid,)
    ).fetchone()
    assert (stance, record) == ("complicates", doubt)
    assert not conn.execute(
        "SELECT 1 FROM evidence_items WHERE record_id = ? AND stance = 'supports'"
        " AND assumption_id = ?",
        (support, entry["assumption_ids"][0]),
    ).fetchone()
    # The stored doubt is one of the claim's items: an open complicating item blocks SUPPORTED.
    assert eid in pipeline.view_run(conn)["manifest"][claim_id]["evidence"]
    (logged, *_) = [p for p in _entries(conn) if p["claim_id"] == claim_id]
    assert logged["stored"] == [eid] and logged["record_ids"] == [doubt, support]
    conn.close()


def test_a_stored_support_fails_the_run(tmp_path, challenged, monkeypatch):
    base_conn, base, _ = challenged
    claim_id = sorted(base.challenge)[0]
    _, support = _two_records(base_conn, claim_id)

    def queries(case, assumptions):  # noqa: ANN001, ANN202
        core = tuple(a.id for a in assumptions if a.is_core)
        return [challenge.Query("other_app", core[:1], "test search", (support,), 1)]

    monkeypatch.setattr(challenge, "queries", queries)
    monkeypatch.setattr(challenge, "keep", lambda item: True)  # a bug that keeps support
    stances = {support: Stance.SUPPORTS}
    conn, comps = _case(tmp_path, labeler=lambda inner: _Doubting(inner, stances))
    with pytest.raises(invariants.InvariantViolation, match="stores only"):
        pipeline.run_audit(conn, comps)
    conn.close()


# ---------------------------------------------------------------- verify-bundle re-runs them


def _export(conn, path: Path, include: str | None = "all") -> Path:  # noqa: ANN001
    return export.export_bundle(
        conn, path, EXPERT, counsel_confirmed=True, clock=lambda: AT, include=include
    ).path


def _challenge_findings(findings) -> list:  # noqa: ANN001
    return [f for f in findings if f.check == "challenge"]


def test_verify_bundle_re_runs_every_search_without_a_model(challenged, tmp_path):
    conn, _, _ = challenged
    findings = verify_bundle(_export(conn, tmp_path / "full.zip"))
    assert not failed(findings), [f for f in findings if f.level == FAIL]
    (f,) = _challenge_findings(findings)
    assert f.level == PASS and "give the same records again, with no model" in f.detail


def test_a_scoped_bundle_says_the_searches_were_not_re_run(challenged, tmp_path):
    conn, _, _ = challenged
    findings = verify_bundle(_export(conn, tmp_path / "scoped.zip", include=None))
    levels = [f.level for f in _challenge_findings(findings)]
    assert NOTE in levels and FAIL not in levels
    note = next(f for f in _challenge_findings(findings) if f.level == NOTE)
    assert "not re-run" in note.detail and "include records" in note.detail


def _check_challenge(conn) -> list:  # noqa: ANN001
    out = verify_mod._Out()
    verify_mod._challenge(conn, pipeline.view_run(conn), {"scope": export.FULL}, out)
    return out.items


def test_a_search_that_now_gives_other_records_fails(challenged, monkeypatch):
    conn, _, _ = challenged
    real = challenge.queries

    def other(case, assumptions):  # noqa: ANN001, ANN202
        return [
            challenge.Query(q.kind, q.assumption_ids, q.searched, (*q.record_ids, "msg:x"), q.total)
            for q in real(case, assumptions)
        ]

    monkeypatch.setattr(challenge, "queries", other)
    findings = _check_challenge(conn)
    assert any(f.level == FAIL and "do not give the records" in f.detail for f in findings)


def test_a_change_after_the_run_to_what_the_searches_read_is_noted(tmp_path):
    conn, comps = _case(tmp_path)
    pipeline.run_audit(conn, comps)
    later = datetime.now(UTC) + timedelta(days=1)
    audit_log.append(conn, later, EXPERT, "person.add", {"person_id": "person:x", "name": "X"})
    findings = _check_challenge(conn)
    assert FAIL not in {f.level for f in findings}
    (note,) = [f for f in findings if f.level == NOTE]
    assert "not re-run" in note.detail and "person.add after the run" in note.detail
    conn.close()


def test_entries_for_a_run_without_the_step_fail(tmp_path):
    conn, comps = _case(tmp_path, challenge_on=False)
    result = pipeline.run_audit(conn, comps)
    audit_log.append(
        conn,
        datetime.now(UTC),
        "system",
        challenge.QUERY_ACTION,
        {"run_id": result.run_id, "claim_id": "C01", "stored": []},
    )
    (f,) = _check_challenge(conn)
    assert f.level == FAIL and "did not run them" in f.detail
    conn.close()


def test_a_stored_item_that_is_not_doubt_fails(challenged, tmp_path, monkeypatch):
    conn, _, _ = challenged
    run = pipeline.view_run(conn)
    claim_id = sorted(run["manifest"])[0]
    support = next(
        e.id
        for e in pipeline.load_evidence(conn, run["manifest"][claim_id]["evidence"])
        if e.stance is Stance.SUPPORTS
    )
    log = verify_mod._log(conn)
    fake = [
        *log,
        (
            10**9,
            log[-1][1],
            "system",
            challenge.QUERY_ACTION,
            {"run_id": run["run_id"], "claim_id": claim_id, "stored": [support]},
        ),
    ]
    monkeypatch.setattr(verify_mod, "_log", lambda c: fake)
    findings = _check_challenge(conn)
    assert any(f.level == FAIL and support in f.detail for f in findings)


# ---------------------------------------------------------------- the rubber-stamp expert


def test_the_rubber_stamp_expert_accepts_every_labeled_item(tmp_path):
    conn, comps = _case(tmp_path, challenge_on=False)
    result = pipeline.run_audit(conn, comps)
    review = rubber_stamp_review(conn, result.manifest, lambda: AT)
    labeled = [
        e
        for items in result.manifest.values()
        for e in pipeline.load_evidence(conn, items["evidence"])
        if e.stance is not Stance.IRRELEVANT
    ]
    assert labeled and review.summary()["accepted"] == len(labeled)
    assert review.summary()["actor"] == RUBBER_STAMP
    by = dict(
        conn.execute(
            "SELECT evidence_id, reviewer FROM evidence_reviews WHERE reviewer_kind = 'expert'"
        ).fetchall()
    )
    assert {by[e.id] for e in labeled} == {RUBBER_STAMP}
    status = {
        e.id: e.status
        for items in result.manifest.values()
        for e in pipeline.load_evidence(conn, items["evidence"])
    }
    assert {status[e.id] for e in labeled} == {EvidenceStatus.ACCEPTED}
    conn.close()


def test_the_eval_runs_the_step_under_the_rubber_stamp_expert(tmp_path):
    out = tmp_path / "out"
    assert rp.main(
        ["--case", "case01", "--mode", "model-free", "--expert", "rubber-stamp", "--challenge",
         "--out", str(out)]
    ) == 0  # fmt: skip
    summary = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert summary["simulated_expert"]["actor"] == RUBBER_STAMP
    assert summary["challenge"]["searches"] >= len(summary["challenge"]["claims_challenged"])
    assert summary["challenge"]["stored"] == 0 or summary["challenge"]["claims_challenged"]
