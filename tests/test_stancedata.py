"""Shared stance-data pieces: families vs the guide, item checks, overlap check, scorer, go bar."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from core.contracts import AssumptionKind as K
from core.contracts import ClaimType, GoldClaim, Prediction, SupportedBasis, Verdict
from core.llm.runtime import GenerationParams, ModelOutput
from eval import run_eval
from eval.probe import prompts, run_probe
from eval.probe.from_draft import convert
from eval.stancedata import bakerform as bf
from eval.stancedata import contamination, gobar, review_sheet, score
from eval.stancedata.chat import (
    Account,
    Msg,
    NonexistentLocalTime,
    at_local,
    build_item,
    local_str,
    read_jsonl,
    write_jsonl,
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
    assert len(BY_ID) == len(FAMILIES) == 66


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
    assert sum(s.startswith("probe(signed)") and s.endswith("assumption") for s in sources) == 105
    drafts = len(read_jsonl(ROOT / "eval" / "probe_draft" / "probe_draft.jsonl"))
    assert sum(s.startswith("probe(draft)") and s.endswith("assumption") for s in sources) == drafts
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
    frames = [
        "On May 2, 2026, the contact saved as Tess told the owner that the dryer was fixed.",
        # The name Jules is in the probe set too; the frame still is not a copy.
        "The contact saved as Jules told the owner that all 60 tiles came.",
    ]
    for frame in frames:
        res = contamination.compare("t", [contamination.Text("frame", frame)], reference_index)
        assert res.flags == [], frame
    vikram = "The first message between the owner and the contact saved as Vikram was sent on "
    held = contamination._index([contamination.Text("h", vikram + "March 6, 2025.")])
    other = vikram.replace("Vikram", "Imani") + "December 1, 2025"
    assert contamination.compare("t", [contamination.Text("q", other)], held).flags == []
    same = contamination.Text("q", vikram + "March 6, 2025")
    assert [f.kind for f in contamination.compare("t", [same], held).flags] == ["exact"]


def test_overlap_check_flags_a_near_copy_of_a_probe_record(reference_index) -> None:
    near = contamination.Text("ru", "слушай, я там больше не работаю)")  # signed P079 plus noise
    kinds = {f.kind for f in contamination.compare("t", [near], reference_index).flags}
    assert kinds == {"jaccard"}


def test_overlap_check_reads_the_claim_a_baker_item_shows(reference_index) -> None:
    """The claim is model-visible text a generator writes, so a claim that copies test data
    is flagged like a copied record."""
    copied = {r["probe_id"]: r for r in read_jsonl(PROBE)}["P049"]["target"]["text"]
    row = {
        "probe_id": "T000001",
        "baker_template": "meaning",
        "baker_params": {},
        "baker_claim": copied,
        "target": {"text": "the drywall guy wants cash before he starts on the hallway"},
        "rationale": "The record says nothing about it.",
        "context": [],
    }
    texts = list(contamination.item_text_list([row], "train"))
    res = contamination.compare("t", texts, reference_index)
    assert {f.query.source: f.kind for f in res.flags} == {"train T000001 claim": "exact"}


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
                "contradicts_shown_as_supports", "moved_traps_shown_as_supports",
                "expert_load_supports_shown", "expert_load_precision", "stance_valid_output",
                "confusion", "bars"):  # fmt: skip
        assert got[key] == expected[key], key
    assert expected["moved_traps_shown_as_supports"] > 0  # the cycle labels some moved traps
    assert (ours.correct, ours.quote_verified) == (st.correct, st.quote_verified)


def test_moved_traps_are_the_families_guide_v0_3_made_complicates() -> None:
    moved = {f.trap: set() for f in FAMILIES if f.trap in run_probe.MOVED_TRAPS}
    for f in FAMILIES:
        if f.trap in moved:
            moved[f.trap].add(f.stance.value)
    # The four trap families v0.3 moved, and two probe-only traps (2026-10-15) that the
    # generators never write: undated denials and told frames (guide rules 12 and 23).
    assert set(moved) == set(TRAP_ORDER[:4])
    assert run_probe.MOVED_TRAPS == set(TRAP_ORDER)
    assert all(stances == {"complicates"} for stances in moved.values()), moved
    probe = [it for it in read_jsonl(PROBE) if it["trap"] in run_probe.MOVED_TRAPS]
    assert {it["probe_id"] for it in probe} == {
        *(f"P0{n}" for n in (*range(38, 45), 49, *range(66, 70), 71, 92, 93, 94))
    }
    assert {it["gold_stance"] for it in probe} == {"complicates"}
    one = probe[0]  # P038, a signed later correction
    pred = {"stance": "supports", "quote": one["proposed_quote"]}
    shown = score.score([one], {one["probe_id"]: pred})
    assert shown["gated"]["moved_traps_shown_as_supports"] == 1
    assert shown["gated"]["contradicts_shown_as_supports"] == 0


class _Capture(_Replay):
    """A fake LocalModel that keeps every prompt and answers irrelevant."""

    def __init__(self) -> None:
        super().__init__([])
        self.prompts: list[str] = []

    def generate_json(self, prompt, schema, params=None) -> ModelOutput:
        self.prompts.append(prompt)
        parsed = {"stance": "irrelevant", "quote": "", "rationale": "r"}
        return ModelOutput(raw_text="{}", parsed=parsed, error=None)


def test_probe_runner_shows_a_baker_item_as_baker_does(tmp_path: Path) -> None:
    """run_probe --probe-set reads an item in Baker's own wording as Baker shows a case: senders
    without Baker's internal account ids, a chat record's context opening with its members
    line, and the claim, in a stance prompt that has a {claim} slot."""
    tz = "America/Chicago"
    at = datetime(2026, 5, 3, 2, 10, 44, tzinfo=UTC)
    owner = bf.sender_line("Telegram", "5550147", owner=True, persons=[bf.owner_person(1)])
    lines = [
        bf.message_line(1, "Telegram", "5550163", at, tz, "bring the blue one tonight",
                        recipients=[owner]),
        bf.message_line(1, "Telegram", "5550147", at + timedelta(minutes=1), tz, "ok",
                        owner=True, persons=[bf.owner_person(1)]),
    ]  # fmt: skip
    item = bf.build_baker_item(
        probe_id="H999999",
        family_id="bk_meaning_said",
        source="heldout_gen",
        generator="eval.heldout test",
        lang="en",
        template_id="meaning",
        params={"quoted_text": "the blue one"},
        lines=lines,
        target=0,
        quote="the blue one",
        rationale="The record uses the words; the claim gives their meaning.",
        device="dev:item1",
        claim="Daniel Petrov asked for the gun.",
        names={bf.owner_person(1): "Daniel Petrov"},
    )
    write_jsonl([item], tmp_path / "items.jsonl")
    reviewer, stance = convert(read_jsonl(tmp_path / "items.jsonl")[0])
    assert stance["context"].splitlines() == [
        "Members seen in this chat's records: Telegram 5550147 (owner) [Daniel Petrov (the user"
        " of item1)]; Telegram 5550163",
        "[2026-05-02 21:10:44 CDT] Telegram 5550163: bring the blue one tonight",
        "[2026-05-02 21:11:44 CDT] Telegram 5550147 (owner) [Daniel Petrov (the user of item1)]:"
        " ok",
    ]
    assert stance["record"] == stance["context"].splitlines()[1]
    assert reviewer["context"] == stance["context"] and "acct:" not in json.dumps(stance)
    assert stance["claim"] == "Daniel Petrov asked for the gun." and "claim" not in reviewer

    start = prompts.PROMPT_START
    signed = tmp_path / "v1_0.md"
    signed.write_text(f"{start}\nA={{assumption}} R={{record}} C={{context}}\n", encoding="utf-8")
    slotted = tmp_path / "v1_1.md"
    slotted.write_text(f"{start}\nK={{claim}} A={{assumption}} R={{record}} C={{context}}\n",
                       encoding="utf-8")  # fmt: skip
    plain = {**stance, "id": "H999998"}
    plain.pop("claim")
    for path, shown in ((signed, None), (slotted, "Daniel Petrov asked for the gun.")):
        model = _Capture()
        run_probe.score_stance(model, [stance, plain], GenerationParams(), 1, stance_path=path)
        if shown is None:
            assert "K=" not in model.prompts[0] and "{claim}" not in model.prompts[0]
        else:
            assert model.prompts[0].startswith(f"K={shown} A=")
            assert model.prompts[1].startswith(f"K={prompts.NO_CLAIM} A=")


def _perfect(name: str) -> dict:
    n = gobar.MIN_GATED[name]
    gated = {"n": n, "gold_contradicts": gobar.MIN_GOLD_CONTRADICTS[name],
             "stance_valid_output": 1.0, "supports_recall": 0.95,
             "contradicts_precision": 0.93, "contradicts_shown_as_supports": 0,
             "moved_traps_shown_as_supports": 0}  # fmt: skip
    return {"gated": gated}


CASE02_OK = {"false_supported": 0, "false_contradicted": 0, "verdict_accuracy": 0.85}


def test_go_bar_decision() -> None:
    ok = gobar.decide(probe=_perfect("probe"), heldout=_perfect("heldout"), case02=CASE02_OK,
                      seconds_per_call=4.5, contamination_passed=True)  # fmt: skip
    assert ok.go and ok.reasons == []
    bad_heldout = _perfect("heldout")
    bad_heldout["gated"]["contradicts_shown_as_supports"] = 1
    moved_probe = _perfect("probe")
    moved_probe["gated"]["moved_traps_shown_as_supports"] = 1
    unscored = _perfect("heldout")  # a result from before the moved-trap count existed
    del unscored["gated"]["moved_traps_shown_as_supports"]
    few_contradicts = _perfect("probe")
    few_contradicts["gated"]["gold_contradicts"] = gobar.MIN_GOLD_CONTRADICTS["probe"] - 1
    small = {"gated": {"n": 0}}  # held-out sample not signed yet: nothing gated
    for kw, needle in [
        ({"heldout": bad_heldout}, "contradicts_shown_as_supports"),
        ({"probe": moved_probe}, "probe: moved_traps_shown_as_supports is 1"),
        ({"heldout": unscored}, "heldout: moved_traps_shown_as_supports is None"),
        ({"probe": few_contradicts}, "fewer than 11 gold contradicts"),
        ({"heldout": small}, "gated items"),
        ({"seconds_per_call": 4.6}, "speed"),
        ({"contamination_passed": False}, "overlap"),
        ({"probe": None}, "probe: no result"),
        ({"case02": None}, "case02: no result"),
        ({"case02": {**CASE02_OK, "false_supported": 1}}, "case02: false_supported is 1"),
        ({"case02": {**CASE02_OK, "false_contradicted": 1}}, "case02: false_contradicted is 1"),
        ({"case02": {**CASE02_OK, "verdict_accuracy": 0.79}}, "case02: verdict accuracy"),
        ({"case02": {"false_supported": 0, "false_contradicted": 0}}, "verdict accuracy is None"),
        ({"case02": {"verdict_accuracy": 0.9}}, "case02: false_supported is None"),
    ]:
        args = dict(probe=_perfect("probe"), heldout=_perfect("heldout"), case02=CASE02_OK,
                    seconds_per_call=4.0, contamination_passed=True)  # fmt: skip
        args.update(kw)
        d = gobar.decide(**args)
        assert not d.go and any(needle in r for r in d.reasons), (kw, d.reasons)
    edge = {**CASE02_OK, "verdict_accuracy": gobar.CASE02_MIN_VERDICT_ACCURACY}
    assert gobar.decide(probe=_perfect("probe"), heldout=_perfect("heldout"), case02=edge,
                        seconds_per_call=4.0, contamination_passed=True).go  # fmt: skip
    no_contradicts = _perfect("probe")
    no_contradicts["gated"]["contradicts_precision"] = None
    assert not gobar.decide(probe=no_contradicts, heldout=_perfect("heldout"), case02=CASE02_OK,
                            seconds_per_call=1.0, contamination_passed=True).go  # fmt: skip


def test_go_bar_scorer_fails_a_moved_trap_shown_as_supports() -> None:
    # GO_BAR.md bars 2 and 3 hold moved traps at zero, so the go bar's scorer cannot report a
    # pass with one shown as supports; run_probe's four Expert-confirms bars do not count it.
    items = read_jsonl(PROBE)
    preds = {it["probe_id"]: {"stance": it["gold_stance"], "quote": it["proposed_quote"]}
             for it in items}  # fmt: skip
    assert score.score(items, preds)["gated"]["passes_all"] is True
    preds["P038"] = {"stance": "supports", "quote": preds["P038"]["quote"]}  # a moved trap
    gated = score.score(items, preds)["gated"]
    assert gated["moved_traps_shown_as_supports"] == 1
    assert {bar for bar, ok in gated["bars"].items() if not ok} == {
        "no_moved_traps_shown_as_supports"
    }
    assert gated["passes_all"] is False
    st = score.StanceScore()
    for it in items:
        if run_probe.is_gated(it):
            score.add_prediction(st, it, preds[it["probe_id"]])
    assert run_probe.expert_confirms(st)["passes_all"] is True


def test_go_bar_scorer_needs_one_contradicts_so_precision_exists() -> None:
    # GO_BAR.md bar 2: a model that never says "contradicts" has no precision, and gobar.decide()
    # rejects that, so the go bar's scorer cannot report a pass for it either.
    items = read_jsonl(PROBE)
    preds = {it["probe_id"]: {"stance": it["gold_stance"], "quote": it["proposed_quote"]}
             for it in items}  # fmt: skip
    for pid, pred in preds.items():
        if pred["stance"] == "contradicts":
            preds[pid] = {"stance": "complicates", "quote": pred["quote"]}
    gated = score.score(items, preds)["gated"]
    assert gated["contradicts_precision"] is None
    assert {bar for bar, ok in gated["bars"].items() if not ok} == {
        "contradicts_said_at_least_once"
    }
    assert gated["passes_all"] is False
    d = gobar.decide(probe={"gated": gated}, heldout=_perfect("heldout"),
                     case02=CASE02_OK, seconds_per_call=1.0, contamination_passed=True)  # fmt: skip
    assert not d.go and "probe: contradicts_precision is None, needs >= 0.9" in d.reasons


def _claim(cid: str, gold: Verdict) -> GoldClaim:
    return GoldClaim(claim_id=cid, page=1, para_no=1, text="t", claim_type=ClaimType.EVENT,
                     cross_device=False, gold_verdict=gold, core_assumptions=(),
                     key_evidence=(), trap=None, rationale="r", labeled_by="test",
                     labeled_at=datetime(2026, 10, 14, tzinfo=UTC))  # fmt: skip


def _pred(cid: str, got: Verdict) -> Prediction:
    basis = SupportedBasis.CONFIRMED if got == Verdict.SUPPORTED else None
    return Prediction(claim_id=cid, verdict=got, supported_basis=basis)


def test_go_bar_reads_case02_from_the_merge_gate_score() -> None:
    # Condition 5 takes run_eval's own score, as an object or as the JSON it prints; run_eval
    # has no false-contradicted count, so the go bar reads it from the confusion table.
    s, c, u = Verdict.SUPPORTED, Verdict.CONTRADICTED, Verdict.UNPROVEN
    pairs = [(s, s), (u, u), (c, c), (u, c), (s, s)]  # one unproven claim decided contradicted
    gold = [_claim(f"C{n}", g) for n, (g, _) in enumerate(pairs)]
    scores = run_eval.score(gold, [_pred(f"C{n}", p) for n, (_, p) in enumerate(pairs)])
    printed = json.loads(json.dumps(scores.__dict__))
    want = {"false_supported": 0, "false_contradicted": 1, "verdict_accuracy": 0.8}
    assert gobar.case02_numbers(scores) == gobar.case02_numbers(printed) == want
    assert gobar.case02_numbers(want) == want
    args = dict(probe=_perfect("probe"), heldout=_perfect("heldout"), seconds_per_call=4.0,
                contamination_passed=True)  # fmt: skip
    for form in (scores, printed, want):
        d = gobar.decide(case02=form, **args)
        assert d.reasons == ["case02: false_contradicted is 1, needs <= 0"], d.reasons
    clean = run_eval.score(gold, [_pred(f"C{n}", g) for n, (g, _) in enumerate(pairs)])
    assert gobar.decide(case02=clean, **args).go


def test_go_bar_file_states_the_coded_numbers() -> None:
    text = GO_BAR.read_text(encoding="utf-8")
    assert f"{gobar.MAX_SECONDS_PER_CALL:.2f} seconds" in text
    assert f"{gobar.BASELINE_SECONDS_PER_CALL} seconds" in text
    assert f"{gobar.MIN_GATED['heldout']:,} items" in text
    assert f"{gobar.MIN_GOLD_CONTRADICTS['heldout']} gold contradicts" in text
    assert f"{gobar.MIN_GATED['probe']} items, {gobar.MIN_GOLD_CONTRADICTS['probe']}" in text
    assert "at least 90%" in text and "valid output 100%" in text
    flat = " ".join(text.split())
    assert "(" + ", ".join(sorted(run_probe.MOVED_TRAPS, key=TRAP_ORDER.index)) + ")" in flat
    assert 'shown as "supports"' in flat and "The moved-trap bar applies here too" in flat
    assert "It must have 0 false supported, 0 false contradicted" in flat
    assert gobar.CASE02_AT_MOST == {"false_supported": 0, "false_contradicted": 0}
    assert f"verdict accuracy of at least {gobar.CASE02_MIN_VERDICT_ACCURACY:.2f}" in flat


TRAP_ORDER = ["time_mismatch", "sender_mismatch", "speaker_mismatch", "later_correction",
              "undated_denial", "told_frame"]  # fmt: skip


def test_review_sample_is_fixed_and_spread_over_families() -> None:
    rows = [{"probe_id": f"T{n:06d}", "family": f"f{n % 7}"} for n in range(700)]
    a = review_sheet.sample(rows, 70, seed=1)
    assert a == review_sheet.sample(rows, 70, seed=1)
    counts = {f: sum(r["family"] == f for r in a) for f in {r["family"] for r in rows}}
    assert set(counts.values()) == {10}
