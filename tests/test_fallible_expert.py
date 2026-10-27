"""The fallible simulated expert (eval/simulated_expert.py, fallible_review): the signed-key
simulated expert, wrong on each item at a set rate drawn per item from a seed. The rates here are
made up to test the mechanism; the real rate is Arsh's to set. Synthetic case01 only."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from core import pipeline
from core.contracts import EvidenceStatus, GoldClaim, Stance
from eval import run_pipeline as rp
from eval.run_eval import load_jsonl
from eval.simulated_expert import FALLIBLE, GoldKey, errs, fallible_review, review
from tests.test_challenge import _case

AT = datetime(2026, 10, 20, 12, tzinfo=UTC)


def _gold() -> GoldKey:
    return GoldKey(load_jsonl(rp.gold_path("case01"), GoldClaim))


def test_the_draw_is_fixed_by_seed_and_item_and_near_the_rate():
    ids = [f"ev:{i}" for i in range(20000)]
    first = [errs(7, i, 0.3) for i in ids]
    assert first == [errs(7, i, 0.3) for i in ids]
    assert first != [errs(8, i, 0.3) for i in ids]
    assert abs(sum(first) / len(ids) - 0.3) < 0.02
    assert not any(errs(7, i, 0.0) for i in ids) and all(errs(7, i, 1.0) for i in ids)


def _first_pass(tmp_path, name: str):  # noqa: ANN001, ANN202
    folder = tmp_path / name
    folder.mkdir()
    conn, comps = _case(folder, challenge_on=False)
    return conn, pipeline.run_audit(conn, comps)


def _decided(conn, manifest) -> dict[str, EvidenceStatus]:  # noqa: ANN001
    return {
        e.id: e.status
        for items in manifest.values()
        for e in pipeline.load_evidence(conn, items["evidence"])
        if e.stance is not Stance.IRRELEVANT
    }


def test_at_rate_zero_it_decides_as_the_signed_key_expert(tmp_path):
    a, ra = _first_pass(tmp_path, "a")
    b, rb = _first_pass(tmp_path, "b")
    gold = _gold()
    key = review(a, gold, ra.manifest, lambda: AT)
    fallible = fallible_review(b, gold, rb.manifest, lambda: AT, 0.0)
    assert _decided(a, ra.manifest) == _decided(b, rb.manifest)
    assert fallible.accepted == key.accepted and fallible.dismissed == key.dismissed
    assert fallible.wrong_accepts == fallible.wrong_dismissals == []
    a.close()
    b.close()


def test_each_wrong_decision_is_the_drawn_one_and_goes_through_the_expert_actions(tmp_path):
    conn, result = _first_pass(tmp_path, "c")
    gold = _gold()
    items = [
        (cid, e)
        for cid, m in result.manifest.items()
        for e in pipeline.load_evidence(conn, m["evidence"])
        if e.stance is not Stance.IRRELEVANT
    ]
    out = fallible_review(conn, gold, result.manifest, lambda: AT, 0.25, seed=3)
    drawn = {e.id for _c, e in items if errs(3, e.id, 0.25)}
    assert drawn and set(out.wrong_accepts) | set(out.wrong_dismissals) == drawn
    status = _decided(conn, result.manifest)
    for cid, e in items:
        right = gold.accepts(cid, e)
        assert (status[e.id] is EvidenceStatus.ACCEPTED) == (right != (e.id in drawn)), e.id
    by = dict(
        conn.execute(
            "SELECT evidence_id, reviewer FROM evidence_reviews WHERE reviewer_kind = 'expert'"
        ).fetchall()
    )
    assert {by[e.id] for _c, e in items} == {FALLIBLE}
    s = out.summary()
    assert s["error_rate"] == 0.25
    assert s["wrong_accepts"] + s["wrong_dismissals"] == len(drawn)
    assert s["dismissal_rate"] == round(s["dismissed"] / len(items), 4)
    assert s["accepted"] + s["dismissed"] == len(items)
    conn.close()


def test_the_other_experts_summaries_are_unchanged(tmp_path):
    conn, result = _first_pass(tmp_path, "d")
    gold = _gold()
    s = review(conn, gold, result.manifest, lambda: AT).summary()
    assert set(s) == {"actor", "accepted", "dismissed", "claims_with_an_acceptance"}
    conn.close()


def test_a_rate_outside_zero_to_one_is_refused(tmp_path):
    conn, result = _first_pass(tmp_path, "e")
    gold = _gold()
    with pytest.raises(ValueError, match="between 0 and 1"):
        fallible_review(conn, gold, result.manifest, lambda: AT, 1.5)
    conn.close()


@pytest.mark.parametrize(
    "args",
    [
        ["--expert", "fallible"],  # the rate has no default
        ["--error-rate", "0.1"],  # a rate needs the fallible expert
        ["--expert", "fallible", "--error-rate", "2"],
    ],
)
def test_the_eval_needs_a_rate_for_the_fallible_expert_and_only_for_it(args):
    with pytest.raises(SystemExit):
        rp.main(["--case", "case01", "--mode", "model-free", *args])


def test_the_eval_runs_the_fallible_expert(tmp_path):
    out = tmp_path / "out"
    assert rp.main(
        ["--case", "case01", "--mode", "model-free", "--expert", "fallible", "--error-rate",
         "0.2", "--expert-seed", "5", "--out", str(out)]
    ) == 0  # fmt: skip
    s = json.loads((out / "run.json").read_text(encoding="utf-8"))["simulated_expert"]
    assert s["actor"] == FALLIBLE and s["error_rate"] == 0.2
    assert s["wrong_accepts"] + s["wrong_dismissals"] > 0
