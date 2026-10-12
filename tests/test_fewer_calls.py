"""Fewer stance calls, safely, and a run that stops part way keeps its finished claims.

- A claim a failed core check already decides (rule 1a) is not sent to the stance model. The
  first test holds the reason this is safe against the real rules: whatever evidence is added,
  in any stance, review status and tier, the verdict stays contradicted. If a rule change ever
  breaks that, it fails here, and settled_by_check must change with it.
- Each claim is committed when it finishes, so a run killed part way leaves the model outputs
  of its finished claims, and the next run reuses them instead of calling the model.

SYNTHETIC. Fake models only; no weights, no network.
"""

from __future__ import annotations

import itertools
import random
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core import contracts as c
from core import pipeline
from core.audit import rules, stance
from core.contracts import AssumptionKind as K
from core.contracts import CheckOutcome as O
from core.contracts import EvidenceStatus as S
from core.contracts import ProvenanceTier as T
from core.contracts import Stance, Verdict
from core.db import connect
from core.llm.runtime import FakeModel
from core.report.html import render_report
from core.review import status as review_status
from eval import run_pipeline

RUN = "run:test"
T0 = datetime(2026, 10, 9, tzinfo=UTC)
SHEET = Path("eval/probe_draft/case01_assumptions.jsonl")
IRRELEVANT = '{"stance": "irrelevant", "quote": "", "rationale": "n"}'


# ---------------------------------------------------------------- rule 1a holds


def _claim(claim_type: c.ClaimType) -> c.Claim:
    return c.Claim(
        id="C1",
        paragraph_id="p",
        text="claim",
        claim_type=claim_type,
        status=c.ClaimStatus.ACCEPTED,
    )


def _asm(n: int, kind: K, core: bool) -> c.Assumption:
    return c.Assumption(
        id=f"asm:C1:t{n}",
        claim_id="C1",
        kind=kind,
        template_id=f"t{n}",
        template_version="1",
        params=c.AssumptionParams(),
        text=f"assumption {n}",
        is_core=core,
        tier=T.INFERRED,
    )


def _chk(a: c.Assumption, outcome: O) -> c.CheckResult:
    return c.CheckResult(
        id=c.check_id(a.id, "check", "1"),
        assumption_id=a.id,
        check_name="check",
        check_version="1",
        outcome=outcome,
        searched="s",
        detail="d",
    )


def _pool(assumptions: list[c.Assumption]) -> list[c.EvidenceItem]:
    out = []
    combos = itertools.product(assumptions, Stance, S, (T.OBSERVED, T.DERIVED, T.INFERRED))
    for n, (a, st, status, tier) in enumerate(combos):
        rid = f"msg:item1:Chats!{n}"
        out.append(
            c.EvidenceItem(
                id=f"ev:{a.id}|{rid}|x",
                assumption_id=a.id,
                record_id=rid,
                ref=c.SourceRef(source_id="item1", locator=f"Chats!{n}"),
                stance=st,
                quote="q",
                quote_verified=True,
                rationale="r",
                tier=tier,
                status=status,
                model_run_id="m",
            )
        )
    return out


@pytest.mark.parametrize("claim_type", list(c.ClaimType))
@pytest.mark.parametrize("failed_kind", list(K))
def test_a_failed_core_check_decides_the_claim_whatever_the_evidence(claim_type, failed_kind):
    failed = _asm(1, failed_kind, core=True)
    other = _asm(2, K.IDENTITY, core=True)
    extra = _asm(3, K.MEANING, core=False)
    assumptions = [failed, other, extra]
    checks = [_chk(failed, O.FAIL), _chk(other, O.PASS)]
    assert pipeline.settled_by_check(assumptions, checks) is not None
    pool = _pool(assumptions)
    rng = random.Random(f"{claim_type}-{failed_kind}")  # noqa: S311 - a fixed test sample
    samples = [[], pool, *([e] for e in pool), *(rng.sample(pool, 12) for _ in range(40))]
    for evidence in samples:
        d = rules.decide_verdict(_claim(claim_type), assumptions, evidence, checks, [], RUN)
        assert d.verdict is Verdict.CONTRADICTED, (rules.RULE_VERSION, evidence, d.reasons)


def test_only_a_failed_core_check_settles_a_claim():
    core, side = _asm(1, K.EVENT, core=True), _asm(2, K.EVENT, core=False)
    assert pipeline.settled_by_check([core, side], [_chk(side, O.FAIL)]) is None
    assert pipeline.settled_by_check([core, side], [_chk(core, O.INCONCLUSIVE)]) is None
    assert pipeline.settled_by_check([core, side], [_chk(core, O.PASS)]) is None
    reason = pipeline.settled_by_check([core, side], [_chk(core, O.FAIL)])
    assert reason is not None and "rule 1a" in reason and "assumption 1" in reason


# ---------------------------------------------------------------- the pipeline on case01


@pytest.fixture(scope="module")
def built_case(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("case") / "case01.db"
    run_pipeline.build_case("case01", path).close()  # type: ignore[attr-defined]
    return path


@pytest.fixture
def conn(built_case, tmp_path):
    copy = tmp_path / "case.db"
    shutil.copy(built_case, copy)
    db = connect(copy)
    yield db
    db.close()


def _components(conn, model, label_settled: bool = False) -> pipeline.Components:
    lab = stance.create(conn, model=model)
    comps = pipeline.real_components(
        conn, replace={"labeler": lab}, filler=run_pipeline.spec_filler(SHEET, conn)
    )
    comps.label_settled = label_settled
    return comps


def _calls_per_claim(conn) -> dict[str, int]:
    out: dict[str, int] = {}
    for (aid,) in conn.execute("SELECT json_extract(subject_json, '$[0]') FROM model_calls"):
        claim_id = aid.split(":")[1]
        out[claim_id] = out.get(claim_id, 0) + 1
    return out


def test_a_claim_a_failed_check_decides_is_not_sent_to_the_model(conn):
    """C04's no-contact check fails on case01, so rule 1a contradicts it: no stance calls."""
    model = FakeModel(respond=lambda p: IRRELEVANT)
    result = pipeline.run_audit(conn, _components(conn, model), claim_ids=["C04", "C05"])
    calls = _calls_per_claim(conn)
    assert "C04" not in calls and calls["C05"] > 0
    assert set(result.unlabeled) == {"C04"}
    verdicts = {d.claim_id: d.verdict for d in result.decisions}
    assert verdicts["C04"] is Verdict.CONTRADICTED

    run = pipeline.last_run(conn)
    assert run["config"]["label_settled"] is False
    assert run["unlabeled"]["C04"].startswith("Evidence was not sent to the stance model")
    assert run["manifest"]["C04"]["evidence"] == [] and run["manifest"]["C04"]["checks"]
    st = review_status.claim_state(conn, "C04")
    assert st is not None and st.unlabeled == run["unlabeled"]["C04"]
    assert "Evidence was not sent to the stance model" in render_report(conn)


def test_label_all_still_labels_a_settled_claim(conn):
    model = FakeModel(respond=lambda p: IRRELEVANT)
    result = pipeline.run_audit(
        conn, _components(conn, model, label_settled=True), claim_ids=["C04"]
    )
    assert _calls_per_claim(conn)["C04"] > 0 and result.unlabeled == {}
    assert {d.verdict for d in result.decisions} == {Verdict.CONTRADICTED}


def test_redecide_keeps_the_reason(conn):
    from core.review.redecide import redecide

    model = FakeModel(respond=lambda p: IRRELEVANT)
    pipeline.run_audit(conn, _components(conn, model), claim_ids=["C04", "C05"])
    redecide(conn, "expert:test")
    run = pipeline.last_run(conn)
    assert run["mode"] == "rules_only" and set(run["unlabeled"]) == {"C04"}


# ---------------------------------------------------------------- stop and resume


class Killed(BaseException):
    """Stands for the process dying (a closed laptop, a kill): no except clause runs."""


def test_a_killed_run_keeps_its_finished_claims_and_the_next_run_resumes(
    conn, built_case, tmp_path
):
    # How many calls C02 takes, measured on a separate copy of the case.
    other = tmp_path / "measure.db"
    shutil.copy(built_case, other)
    measure = connect(other)
    probe = FakeModel(respond=lambda p: IRRELEVANT)
    pipeline.run_audit(measure, _components(measure, probe), claim_ids=["C02"])
    measure.close()
    c02_calls = len(probe.calls)
    assert c02_calls > 0

    # Die on the first call after C02 is done, inside C05.
    budget = iter(range(c02_calls))

    def respond(prompt: str) -> str:
        if next(budget, None) is None:
            raise Killed
        return IRRELEVANT

    with pytest.raises(Killed):
        pipeline.run_audit(
            conn, _components(conn, FakeModel(respond=respond)), claim_ids=["C02", "C05"]
        )
    statuses = [r[0] for r in conn.execute("SELECT status FROM pipeline_runs")]
    assert statuses == ["running"]  # never completed, so nothing reads its verdicts
    assert pipeline.last_run(conn) is None
    assert _calls_per_claim(conn) == {"C02": c02_calls}  # C02's outputs survived

    again = FakeModel(respond=lambda p: IRRELEVANT)
    result = pipeline.run_audit(conn, _components(conn, again), claim_ids=["C02", "C05"])
    assert result.model_outputs_reused == c02_calls
    assert not set(again.calls) & set(probe.calls)  # nothing for C02 reached the model
    assert len(again.calls) > 0  # C05 was labeled now
    assert set(pipeline.last_run(conn)["manifest"]) == {"C02", "C05"}


def test_progress_is_reported_after_each_claim_is_saved(conn):
    seen: list[tuple[int, int, str, int]] = []

    def progress(done: int, total: int, d: c.VerdictDecision) -> None:
        saved = conn.execute(
            "SELECT COUNT(*) FROM verdicts WHERE pipeline_run_id = ?", (d.pipeline_run_id,)
        ).fetchone()[0]
        seen.append((done, total, d.claim_id, saved))

    comps = _components(conn, FakeModel(respond=lambda p: IRRELEVANT))
    pipeline.run_audit(conn, comps, claim_ids=["C01", "C04", "C09"], progress=progress)
    assert seen == [(1, 3, "C01", 1), (2, 3, "C04", 2), (3, 3, "C09", 3)]
