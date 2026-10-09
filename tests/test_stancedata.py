"""Shared stance-data pieces: families vs the guide, item checks, overlap check, scorer, go bar."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from core.contracts import AssumptionKind as K
from core.llm.runtime import GenerationParams, ModelOutput
from eval.probe import run_probe
from eval.probe.from_draft import convert
from eval.stancedata import contamination, gobar, review_sheet, score
from eval.stancedata.chat import (
    Account,
    Msg,
    NonexistentLocalTime,
    at_local,
    build_item,
    local_str,
    read_jsonl,
)
from eval.stancedata.families import BY_ID, FAMILIES

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "eval" / "stancedata" / "LABELING_GUIDE.md"
GO_BAR = ROOT / "eval" / "stancedata" / "GO_BAR.md"
PROBE = ROOT / "eval" / "gold" / "probe" / "probe.jsonl"

OWNER = Account("SMS", "+19175550126", owner=True)
TESS = Account("SMS", "+13475550142", "Tess")


def _msgs(*texts: str) -> list[Msg]:
    return [Msg(TESS if i % 2 else OWNER, at_local(date(2026, 5, 2), 9, i), t)
            for i, t in enumerate(texts)]  # fmt: skip


def _item(family_id: str = "sup_plain", **kw):
    args = dict(
        probe_id="T000001", family_id=family_id, source="train_gen", generator="test 0",
        lang="en", kind=K.EVENT,
        assumption="The contact saved as Tess told the owner the van is fixed.",
        msgs=_msgs("is the van ready?", "van is fixed, come by"), target=1, quote="van is fixed",
        rationale="Tess says the van is fixed.",
    )  # fmt: skip
    args.update(kw)
    return build_item(**args)


def test_every_family_is_in_the_guide_with_the_same_answer() -> None:
    rows = re.findall(r"^\| `(\w+)` \| (\w+)", GUIDE.read_text(encoding="utf-8"), re.M)
    assert dict(rows) == {f.family_id: f.stance.value for f in FAMILIES}
    assert len(BY_ID) == len(FAMILIES) == 37


def test_label_comes_from_the_family() -> None:
    it = _item("ovr_plan", kind=K.EVENT)
    assert (it.gold_stance, it.category, it.trap, it.gold_review) == (
        "complicates", "overreach", "plan_not_event", "dismiss")  # fmt: skip
    assert it.labeled_by.startswith("DRAFT")
    assert it.group == "T000001"


def test_item_checks() -> None:
    with pytest.raises(ValueError, match="banned word"):
        _item(rationale="Nothing here says he is guilty.")
    with pytest.raises(ValueError, match="verbatim"):
        _item(quote="van is repaired")
    with pytest.raises(ValueError, match="word-aligned"):
        _item(quote="van is fixe")  # cut inside a word: the product would discard it
    with pytest.raises(ValueError, match="word-aligned"):
        _item(msgs=_msgs("ok", "??"), quote="??")  # no letter or digit
    with pytest.raises(ValueError, match="increasing UTC"):
        _item(msgs=list(reversed(_msgs("a b", "van is fixed"))))
    with pytest.raises(ValueError, match="kind"):
        _item(kind=K.IDENTITY)
    with pytest.raises(ValueError, match="id prefix"):
        _item(probe_id="H000001")
    with pytest.raises(ValueError, match="one non-empty line"):
        Msg(OWNER, at_local(date(2026, 5, 2), 9, 0), "two\nlines")


def test_disputed_family_is_disputed_in_heldout_only() -> None:
    kw = dict(kind=K.MEANING, lang="ru", msgs=_msgs("ну?", "он меня кинул"), quote="кинул",
              assumption="The contact saved as Tess said a man stole from her.")  # fmt: skip
    assert _item("ovr_translation", **kw).disputed is None
    held = _item("ovr_translation", probe_id="H000001", source="heldout_gen", **kw)
    assert held.disputed and "disputed" in held.disputed


def test_local_times_follow_the_phone_clock() -> None:
    assert local_str(at_local(date(2026, 3, 8), 1, 58)) == "2026-03-08 01:58:00 EST"
    assert local_str(at_local(date(2026, 3, 8), 3, 5)) == "2026-03-08 03:05:00 EDT"
    with pytest.raises(NonexistentLocalTime):
        at_local(date(2026, 3, 8), 2, 30)
    first = at_local(date(2026, 11, 1), 1, 20, fold=0)
    second = at_local(date(2026, 11, 1), 1, 20, fold=1)
    assert local_str(first).endswith("EDT") and local_str(second).endswith("EST")
    assert (second - first).total_seconds() == 3600
    assert local_str(at_local(date(2026, 1, 5), 12, 0, tz="Europe/Moscow"), "Europe/Moscow") == (
        "2026-01-05 12:00:00 MSK"
    )


@pytest.fixture(scope="module")
def reference_index() -> contamination.Index:
    return contamination._index(contamination.reference_texts())


def test_reference_data_covers_probe_case01_and_case02(reference_index) -> None:
    sources = [t.source for t in reference_index.texts]
    assert sum(s.startswith("probe(signed)") and s.endswith("assumption") for s in sources) == 88
    assert sum(s.startswith("probe(draft)") and s.endswith("assumption") for s in sources) == 97
    assert sum(s.startswith("case01 msg:") for s in sources) > 1500
    assert sum(s.startswith("case02 msg:") for s in sources) > 1000
    assert any(s.startswith("case01 gold C20") for s in sources)
    assert any(s.startswith("case02 key") for s in sources)


def test_overlap_check_flags_copies_and_light_edits(reference_index) -> None:
    probe = {r["probe_id"]: r for r in read_jsonl(PROBE)}
    copied = probe["P049"]["target"]["text"]
    renamed = probe["P066"]["assumption"].replace("Pam", "Tess")
    queries = [
        contamination.Text("copy", copied),
        contamination.Text("renamed", renamed),
        contamination.Text("fresh", "the drywall guy wants cash before he starts on the hallway"),
        contamination.Text("short", "ok thx"),
    ]
    res = contamination.compare("t", queries, reference_index)
    flagged = {f.query.source: f.kind for f in res.flags}
    assert flagged.get("copy") == "exact"
    assert flagged.get("renamed") in {"run", "jaccard"}
    assert "fresh" not in flagged and "short" not in flagged


def test_overlap_check_ignores_a_shared_sentence_frame(reference_index) -> None:
    frame = "On May 2, 2026, the contact saved as Tess told the owner that the dryer was fixed."
    res = contamination.compare("t", [contamination.Text("frame", frame)], reference_index)
    assert res.flags == []


class _Replay:
    """A fake LocalModel that returns prepared outputs in order."""

    name = "replay"
    sha256 = "0" * 64

    def __init__(self, outputs: list[ModelOutput]) -> None:
        self.outputs = list(outputs)

    def generate_json(self, prompt, schema, params=None) -> ModelOutput:
        return self.outputs.pop(0)


def test_scorer_matches_run_probe_exactly() -> None:
    items = read_jsonl(PROBE)
    preds, outputs = {}, []
    cycle = ["right", "supports", "bad_quote", "invalid", "irrelevant_no_quote", "contradicts"]
    for n, it in enumerate(items):
        kind = cycle[n % len(cycle)]
        quote = it["proposed_quote"]
        pred = {
            "right": {"stance": it["gold_stance"], "quote": quote},
            "supports": {"stance": "supports", "quote": quote},
            "bad_quote": {"stance": "supports", "quote": quote + " (paraphrased)"},
            "invalid": None,
            "irrelevant_no_quote": {"stance": "irrelevant", "quote": ""},
            "contradicts": {"stance": "contradicts", "quote": quote},
        }[kind]
        if pred is None:
            outputs.append(ModelOutput(raw_text="not json", parsed=None, error="parse"))
        else:
            preds[it["probe_id"]] = {"probe_id": it["probe_id"], **pred}
            outputs.append(
                ModelOutput(raw_text="{}", parsed={**pred, "rationale": "r"}, error=None)
            )
    stance_items = [convert(it)[1] for it in items]
    st = run_probe.score_stance(_Replay(outputs), stance_items, GenerationParams(), repeat=1)
    expected = run_probe.expert_confirms(st)
    ours = score.StanceScore()
    for it in items:
        score.add_prediction(ours, it, preds.get(it["probe_id"]))
    got = run_probe.expert_confirms(ours)
    for key in ("supports_recall", "contradicts_precision", "contradicts_recall",
                "contradicts_shown_as_supports", "expert_load_supports_shown",
                "expert_load_precision", "stance_valid_output", "confusion", "bars"):  # fmt: skip
        assert got[key] == expected[key], key
    assert (ours.correct, ours.quote_verified) == (st.correct, st.quote_verified)


def _perfect(name: str) -> dict:
    n = gobar.MIN_GATED[name]
    gated = {"n": n, "gold_contradicts": gobar.MIN_GOLD_CONTRADICTS[name],
             "stance_valid_output": 1.0, "supports_recall": 0.95,
             "contradicts_precision": 0.93, "contradicts_shown_as_supports": 0}  # fmt: skip
    return {"gated": gated}


def test_go_bar_decision() -> None:
    ok = gobar.decide(probe=_perfect("probe"), heldout=_perfect("heldout"),
                      seconds_per_call=4.5, contamination_passed=True)  # fmt: skip
    assert ok.go and ok.reasons == []
    bad_heldout = _perfect("heldout")
    bad_heldout["gated"]["contradicts_shown_as_supports"] = 1
    small = {"gated": {"n": 0}}  # held-out sample not signed yet: nothing gated
    for kw, needle in [
        ({"heldout": bad_heldout}, "contradicts_shown_as_supports"),
        ({"heldout": small}, "gated items"),
        ({"seconds_per_call": 4.6}, "speed"),
        ({"contamination_passed": False}, "overlap"),
        ({"probe": None}, "probe: no result"),
    ]:
        args = dict(probe=_perfect("probe"), heldout=_perfect("heldout"),
                    seconds_per_call=4.0, contamination_passed=True)  # fmt: skip
        args.update(kw)
        d = gobar.decide(**args)
        assert not d.go and any(needle in r for r in d.reasons), (kw, d.reasons)
    no_contradicts = _perfect("probe")
    no_contradicts["gated"]["contradicts_precision"] = None
    assert not gobar.decide(probe=no_contradicts, heldout=_perfect("heldout"),
                            seconds_per_call=1.0, contamination_passed=True).go  # fmt: skip


def test_go_bar_file_states_the_coded_numbers() -> None:
    text = GO_BAR.read_text(encoding="utf-8")
    assert f"{gobar.MAX_SECONDS_PER_CALL:.2f} seconds" in text
    assert f"{gobar.BASELINE_SECONDS_PER_CALL} seconds" in text
    assert f"{gobar.MIN_GATED['heldout']:,} items" in text
    assert f"{gobar.MIN_GOLD_CONTRADICTS['heldout']} gold contradicts" in text
    assert f"{gobar.MIN_GATED['probe']} items, {gobar.MIN_GOLD_CONTRADICTS['probe']}" in text
    assert "at least 90%" in text and "valid output 100%" in text


def test_review_sample_is_fixed_and_spread_over_families() -> None:
    rows = [{"probe_id": f"T{n:06d}", "family": f"f{n % 7}"} for n in range(700)]
    a = review_sheet.sample(rows, 70, seed=1)
    assert a == review_sheet.sample(rows, 70, seed=1)
    counts = {f: sum(r["family"] == f for r in a) for f in {r["family"] for r in rows}}
    assert set(counts.values()) == {10}
