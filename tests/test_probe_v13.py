"""The stance v1.3 re-probe of the local 14B (eval/probe/v13/PREREGISTERED.md): the candidates
are v1.1 plus their blocks only, the item sets are the ones the plan names, and the scorer
applies the written criteria. No model runs here; a stand-in answers."""

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from core.audit.quotes import verify_quote
from core.llm.runtime import GenerationParams, ModelOutput
from eval.probe import prompts, run_probe
from eval.probe.v13 import score

ROOT = Path(__file__).resolve().parents[1]
CHECKS_START = 'Before you answer "contradicts", make two checks.'
EXAMPLES_START = "Examples, invented and not from this case:"
UNSURE = 'If you are unsure between "supports" and anything else, do not choose "supports".'


def _block(body: str, start: str) -> str:
    """The block that starts with `start` and ends at the next blank line, with that line."""
    i = body.index(start)
    return body[i : body.index("\n\n", i) + 2]


def test_each_candidate_is_v1_1_word_for_word_plus_its_blocks():
    v11 = prompts._body(ROOT / "core/audit/prompts/stance.md")  # noqa: SLF001
    a = prompts._body(score.PROMPTS["a"])  # noqa: SLF001
    b = prompts._body(score.PROMPTS["b"])  # noqa: SLF001
    checks = _block(a, CHECKS_START)
    assert a.replace(checks, "") == v11
    assert a.index(checks) + len(checks) == a.index(UNSURE)
    examples = _block(b, EXAMPLES_START)
    assert b.replace(examples, "") == a
    assert b.index(examples) + len(examples) == b.index(UNSURE)
    # The bench copy the baseline ran is the product's v1.1 text.
    assert prompts._body(score.PROMPTS["base"]) == v11  # noqa: SLF001


def test_the_examples_balance_complicates_and_contradicts():
    examples = _block(prompts._body(score.PROMPTS["b"]), EXAMPLES_START)  # noqa: SLF001
    answers = re.findall(r'Answer "(\w+)"', examples)
    assert sorted(answers) == ["complicates", "complicates", "contradicts", "contradicts"]


def test_the_2026_10_15_sets_are_the_files_that_were_scored_then():
    for name, sha in (("tf24", "db1adc759d17658f"), ("r26", "d7daa9ea5ab9cb49")):
        assert hashlib.sha256(score.SETS[name].read_bytes()).hexdigest()[:16] == sha
    assert len(score.scored("tf24")) == 22 and len(score.scored("r26")) == 26


def test_the_fresh_set_is_well_formed_synthetic_data():
    rows = run_probe.load_items(score.SETS["fresh"])
    ids = [r["probe_id"] for r in rows]
    assert ids == [f"H{n:03d}" for n in range(1, len(rows) + 1)] and len(rows) >= 30
    for r in rows:
        lines = list(r["context"])
        lines.insert(r["target_index"], r["target"])
        times = [x["local_time"] for x in lines]
        assert times == sorted(times), r["probe_id"]
        quote = r["proposed_quote"]
        assert (quote == "") == (r["gold_stance"] == "irrelevant"), r["probe_id"]
        assert not quote or verify_quote(quote, r["target"]["text"]), r["probe_id"]
        for x in lines:
            for number in re.findall(r"\+1\d{10}", x["sender"]):
                assert 100 <= int(number[-4:]) <= 199 and number[-7:-4] == "555", number
        assert r["labeled_by"].startswith("DRAFT")
    groups = {g: [r for r in rows if r["trap"] == g] for g in score.TARGET_TRAPS}
    assert all(groups.values())
    out = json.loads(score.LEFT_OUT_FILE.read_text(encoding="utf-8"))["left_out"]
    assert set(out) <= set(ids)


def test_the_baseline_file_is_the_2026_10_19_v1_1_run_and_still_renders_the_same():
    rows = [json.loads(x) for x in score.BASELINE.read_text(encoding="utf-8").splitlines()]
    labels = {r["item_id"]: r["first"] for r in rows}
    m = score.signed_metrics(labels)
    assert m["contradicts_precision"] == (11, 19) and m["supports_recall"] == (33, 33)
    assert m["traps_shown_as_supports"] == 23
    assert m["wrong_contradicts"] == [
        "P049",
        "P066",
        "P067",
        "P068",
        "P069",
        "P092",
        "P093",
        "P094",
    ]
    for it in score.items("signed"):
        text = score.prompt_text(it, score.PROMPTS["base"])
        assert (
            hashlib.sha256(text.encode()).hexdigest()
            == rows[[r["item_id"] for r in rows].index(it["id"])]["prompt_sha256"]
        )
    assert {r["model_sha256"] for r in rows} == {
        "500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0"
    }


class StandIn:
    """Answers every item with its gold label and quote, except the ones `wrong` names."""

    name = "stand-in"
    # The 2026-10-19 file, so the reused signed-set baseline and the stand-in's runs agree.
    sha256 = "500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0"

    def __init__(self, path: Path, set_name: str, wrong: dict[str, str] | None = None) -> None:
        self.by_prompt = {score.prompt_text(it, path): it for it in score.items(set_name)}
        self.rows = {r["probe_id"]: r for r in run_probe.load_items(score.SETS[set_name])}
        self.wrong = wrong or {}

    def generate_json(self, prompt, schema, params=None):
        it = self.by_prompt[prompt]
        stance = self.wrong.get(it["id"], it["expected"])
        quote = "" if stance == "irrelevant" else self.rows[it["id"]]["proposed_quote"]
        raw = json.dumps({"stance": stance, "quote": quote, "rationale": "stand-in"})
        return ModelOutput(raw, json.loads(raw), None, 900, 40, 1.0)


def _run(out: Path, prompt: str, set_name: str, wrong: dict[str, str] | None = None) -> None:
    path = score.PROMPTS[prompt]
    folder = out / f"{prompt}_{set_name}"
    res = run_probe.run_model(
        StandIn(path, set_name, wrong),
        [],
        score.items(set_name),
        GenerationParams(n_ctx=8192),
        1,
        folder,
        path,
        stance_only=True,
    )
    (folder / "summary.json").write_text(json.dumps([res]), encoding="utf-8")


def _told(set_name: str) -> list[str]:
    return [i["id"] for i in score.scored(set_name) if i.get("trap") == "told_frame"]


@pytest.fixture
def out(tmp_path):
    for s in ("fresh", "tf24", "r26"):
        _run(tmp_path, "base", s)
    return tmp_path


def test_a_candidate_that_answers_like_the_labels_is_recommended(out):
    for s in score.SETS:
        _run(out, "a", s)
    assert score.passes(out, "a")
    ok, why = score.baseline_ok(out)
    assert ok, why
    text = score.report(out)
    assert "Recommendation: sign v1.3a." in text and "v1.3b: not run." in text
    assert "| fresh | H001 |" in text


def test_two_wrong_contradicts_on_told_frames_fail_a_new_set(out):
    two = dict.fromkeys(_told("tf24")[:2], "contradicts")
    for s in score.SETS:
        _run(out, "a", s, two if s == "tf24" else None)
    res = score.criteria(out, "a")
    failed = [(s, c) for s, c, ok in res if not ok]
    assert failed == [
        ("tf24", "at most 1 wrong contradicts on told-frame and undated-denial items")
    ]
    assert "Recommendation: no prompt change." in score.report(out)


def test_losing_true_contradicts_on_the_signed_set_fails(out):
    gone = [i["id"] for i in score.scored("signed") if i["expected"] == "contradicts"][:2]
    for s in score.SETS:
        _run(out, "a", s, dict.fromkeys(gone, "complicates") if s == "signed" else None)
    failed = [c for s, c, ok in score.criteria(out, "a") if not ok]
    assert failed == ["contradicts recall >= 10 of 11"]


def test_a_candidate_that_has_not_run_everywhere_is_not_recommended(out):
    _run(out, "a", "signed")
    assert not score.passes(out, "a")


def test_runs_from_two_model_files_give_no_decision(out, monkeypatch):
    for s in score.SETS:
        _run(out, "a", s)
    shutil.rmtree(out / "a_fresh")  # one step rerun with another model file at the same path
    monkeypatch.setattr(StandIn, "sha256", "1" * 64)
    _run(out, "a", "fresh")
    res = score.criteria(out, "a")
    assert res == [("all", "every run from one model file (found 2)", False)]
    assert not score.passes(out, "a")
