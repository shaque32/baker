"""Stance v1.4 (eval/probe/stance_v1_4_draft.md, eval/probe/v14/PREREGISTERED.md): the signed
v1.1 lines in a new order, fixed instructions first, so model calls share a long prompt start;
and the scorer applies the written criteria. No model runs here; a stand-in answers.

SYNTHETIC. Fake model only.
"""

from __future__ import annotations

import json
import os
import shutil
from collections import Counter
from pathlib import Path

import pytest

from core.audit._llm_json import fill_prompt, prompt_body
from core.db import apply_schema, connect
from core.llm.runtime import FakeModel, GenerationParams, ModelOutput
from eval import run_pipeline as rp
from eval.probe import prompts, run_probe, time_case
from eval.probe.v13.score import prompt_text
from eval.probe.v14 import score

ROOT = Path(__file__).resolve().parents[1]
SIGNED = ROOT / "core/audit/prompts/stance.md"
DRAFT = score.PROMPTS["v14"]
FIXED = (
    "How names read:",
    "Choose exactly one stance:",
    'If you are unsure between "supports"',
    "Rules for the quote:",
    "Rules for the rationale:",
)
DATA_STARTS = "The claim this assumption belongs to"


def _bodies() -> tuple[str, str]:
    """The signed v1.1 body and the draft's."""
    return (
        prompt_body(SIGNED.read_text(encoding="utf-8")),
        prompt_body(DRAFT.read_text(encoding="utf-8")),
    )


def test_the_draft_is_the_signed_v1_1_lines_in_a_new_order():
    signed, draft = _bodies()
    assert draft != signed
    assert Counter(signed.splitlines()) == Counter(draft.splitlines())
    assert prompts._body(score.PROMPTS["base"]) == signed  # noqa: SLF001 - the bench copy


def test_every_fixed_instruction_comes_before_the_case_data():
    _, draft = _bodies()
    data = draft.index(DATA_STARTS)
    for heading in FIXED:
        assert draft.index(heading) < data, heading
    assert data < draft.index("{claim}") < draft.index("{assumption}")
    assert draft.index("{assumption}") < draft.index("{record}") < draft.index("{context}")
    assert draft.rstrip().endswith('"rationale": "<one or two sentences>"}')


def _fill(template: str, claim: str, record: str) -> str:
    return fill_prompt(
        template, {"claim": claim, "assumption": "A", "record": record, "context": "ctx"}
    )


def test_calls_share_the_fixed_text_and_one_assumption_shares_up_to_the_record():
    signed, draft = _bodies()

    def shared(template: str, a: tuple[str, str], b: tuple[str, str]) -> int:
        return len(os.path.commonprefix([_fill(template, *a), _fill(template, *b)]))

    one = _fill(draft, "first claim", "first record")
    assert shared(draft, ("first claim", "first record"), ("first claim", "next")) == one.index(
        "first record"
    )
    # Two claims: v1.4 still shares every fixed instruction; v1.1 only its opening lines.
    other = (("first claim", "r"), ("second claim", "r"))
    fixed = draft[: draft.index(DATA_STARTS)]
    assert shared(draft, *other) >= len(fixed) > 2000
    assert shared(signed, *other) < len(fixed) / 3


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "case01.db"
    rp.build_case("case01", db_path).close()  # type: ignore[attr-defined]
    db = connect(db_path)
    yield db
    db.close()


def test_the_product_wiring_takes_the_draft(conn):
    spec = Path("eval/probe_draft/case01_assumptions.jsonl")
    model = FakeModel(respond=lambda p: '{"stance": "irrelevant", "quote": "", "rationale": "n"}')
    comps = time_case._components(conn, model, spec, False, DRAFT)
    assert comps.labeler.template == prompt_body(DRAFT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the scorer


class StandIn:
    """Answers every item with its gold label and quote, except the ones `wrong` names."""

    name = "stand-in"
    sha256 = "5" * 64

    def __init__(self, path: Path, set_name: str, wrong: dict[str, str] | None = None) -> None:
        self.by_prompt = {prompt_text(it, path): it for it in score.items(set_name)}
        self.rows = {r["probe_id"]: r for r in run_probe.load_items(score.SETS[set_name])}
        self.wrong = wrong or {}

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
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
    # What run_probe's main adds to each result.
    res |= {"params": GenerationParams(n_ctx=8192).as_record(), "runtime": "flash",
            "peak_rss_gb": 12.5}  # fmt: skip
    (folder / "summary.json").write_text(json.dumps([res]), encoding="utf-8")


def _timed(
    out: Path,
    prompt: str,
    mean_s: float,
    sha: str = StandIn.sha256,
    recorded: bool = True,
    outcomes: dict[str, int] | None = None,
) -> None:
    """A timed audit's summary; recorded=False is a folder from before per-call seconds, call
    outcomes, settings and peak memory were written."""
    folder = out / f"time_{prompt}"
    folder.mkdir(exist_ok=True)
    stance: dict[str, object] = {
        "calls": 60,
        "mean_seconds_per_call": mean_s,
        "tokens_per_second": 9.5,
    }
    if recorded:  # the same 60 calls, a little spread around the mean, all answered
        stance["call_seconds"] = [mean_s + (i % 5) - 2 for i in range(60)]
        stance["outcomes"] = outcomes or {"ok": 60}
    cold = {
        "passes": {"stance": stance},
        "wall_seconds": round(60 * mean_s, 1),
        "verdicts": {"unproven": 3},
        "stored_items": 5,
    }
    model = {"model": StandIn.name, "sha256": sha, "cold": cold}
    if recorded:
        model |= {"params": {"seed": 1234}, "n_ctx": 8192, "runtime": "flash", "peak_rss_gb": 13.1}
    summary = {"case": "case01", "models": [model]}
    (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")


def _audit_db(out: Path, prompt: str, cold: dict[str, int]) -> None:
    """A timed audit's own case database, as time_case leaves it: a cold stance run whose calls
    ended as `cold` says, then the warm run, all answered."""
    path = out / f"time_{prompt}" / StandIn.name / "case01.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = connect(path)
    apply_schema(db)
    for hour, (run, ended) in enumerate((("mr:stance:cold", cold), ("mr:stance:warm", {"ok": 3}))):
        at = f"2026-10-31T0{hour}:00:00+00:00"
        db.execute(
            "INSERT INTO model_runs (id, purpose, model_name, model_sha256, prompt_version,"
            " params_json, started_at_utc) VALUES (?, 'stance', ?, ?, 'v1.1', '{}', ?)",
            (run, StandIn.name, StandIn.sha256, at),
        )
        outcomes = [o for o, n in ended.items() for _ in range(n)]
        for seq, outcome in enumerate(outcomes, 1):
            db.execute(
                "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
                " outcome, at_utc) VALUES (?, ?, ?, '[]', 'p', '', ?, ?)",
                (f"mc:{run}#{seq}", run, seq, outcome, at),
            )
    db.commit()
    db.close()


def _gold(set_name: str, gold: str) -> list[str]:
    return [i["id"] for i in score.scored(set_name) if i["expected"] == gold]


def _failed(out: Path) -> list[str]:
    return [text for _, text, ok in score.criteria(out) if not ok]


def _only_fails(out: Path, start: str) -> None:
    failed = _failed(out)
    assert len(failed) == 1 and failed[0].startswith(start), failed


@pytest.fixture
def out(tmp_path):
    for s in score.SETS:
        _run(tmp_path, "base", s)
    _timed(tmp_path, "base", 40.0)
    return tmp_path


def test_same_labels_and_a_faster_call_recommend_signing(out):
    for s in score.SETS:
        _run(out, "v14", s)
    _timed(out, "v14", 30.0)
    assert score.passes(out), score.criteria(out)
    text = score.report(out)
    assert "Recommendation: sign v1.4." in text
    assert f"Model SHA-256: {StandIn.sha256}" in text
    assert score.NOT_FRESH in text
    # the speed with its spread, call by call, and never as a product runtime
    assert "one cold run of C02,C05,C12 on case01: a go/no-go for criterion 6" in text
    assert "- v1.4, timed audit stance calls: 60 calls, mean 30.0 s (SD 1.4), median 30.0 s" in text
    assert "v1.4 faster on 60 of 60 calls" in text
    # the run record: seed, context, runtime, tokens per second and peak memory of every step
    assert "| v1.4 on signed | 1234 | 8192 | flash |" in text
    assert "| v1.1 timed audit | 1234 | 8192 | flash | 9.5 | 13.1 |" in text
    # every item, not only those whose answer differs
    rows = [r for r in text.splitlines() if r.startswith("| signed | P")]
    assert len(rows) == len(score.items("signed"))


def test_one_more_trap_shown_as_supports_fails_with_no_slack(out):
    trap = _gold("fresh", "complicates")[0]
    for s in score.SETS:
        _run(out, "v14", s, {trap: "supports"} if s == "fresh" else None)
    _timed(out, "v14", 30.0)
    _only_fails(out, "4. gold complicates or irrelevant shown as supports <= v1.1's 0 (v1.4: 1)")
    text = score.report(out)
    assert "Recommendation: no prompt change." in text
    assert f"| fresh | {trap} | complicates | complicates | supports |" in text


def test_a_trap_on_one_set_cannot_hide_behind_a_drop_on_another(tmp_path):
    # v1.1 shows a told-frame trap as supports; v1.4 gets it right but shows a signed-set trap
    # as supports. Pooled over the sets they tie; on the signed set v1.4 is worse, so it fails.
    signed_trap, tf24_trap = _gold("signed", "complicates")[0], _gold("tf24", "complicates")[0]
    for s in score.SETS:
        _run(tmp_path, "base", s, {tf24_trap: "supports"} if s == "tf24" else None)
        _run(tmp_path, "v14", s, {signed_trap: "supports"} if s == "signed" else None)
    _timed(tmp_path, "base", 40.0)
    _timed(tmp_path, "v14", 30.0)
    failed = [(scope, text) for scope, text, ok in score.criteria(tmp_path) if not ok]
    base_signed = score.traps(score.ran(tmp_path, "base", "signed").labels, "signed")
    assert failed == [
        (
            "signed",
            "4. gold complicates or irrelevant shown as supports <= v1.1's"
            f" {base_signed} (v1.4: {base_signed + 1})",
        )
    ]


def test_a_folder_from_before_the_run_record_still_scores(out):
    for s in score.SETS:
        _run(out, "v14", s)
    _timed(out, "v14", 30.0, recorded=False)
    _audit_db(out, "v14", {"ok": 60})  # the call outcomes come from the audit's own database
    assert score.passes(out), score.criteria(out)
    text = score.report(out)
    assert "60 calls, mean 30.0 s; per-call times not recorded" in text
    assert "| v1.4 timed audit | not recorded | not recorded | not recorded | 9.5 |" in text
    assert "stored items 5, call outcomes ok 60" in text


def test_failed_calls_never_count_as_a_speedup(out):
    # Two calls that failed at once and one unusable answer pull v1.4's mean well below v1.1's.
    for s in score.SETS:
        _run(out, "v14", s)
    _timed(out, "v14", 20.0, outcomes={"ok": 57, "error": 2, "invalid_output": 1})
    assert _failed(out) == [
        "6. every stance call of both timed audits answered, no runtime error or invalid output"
        " (v1.1: 0 failed, v1.4: 3 failed)",
        "6. mean s per stance call at least 15% below v1.1's (v1.1 40.0 s, v1.4 20.0 s;"
        " not counted)",
    ]
    text = score.report(out)
    assert "Recommendation: no prompt change." in text
    assert "call outcomes error 2, invalid_output 1, ok 57" in text
    # A quote the product discards is a real answer: reported, not a failed call.
    _timed(out, "v14", 30.0, outcomes={"ok": 59, "quote_failed": 1})
    assert score.passes(out)
    # The same holds for v1.1's audit, and for an old folder read from its database.
    _timed(out, "base", 40.0, recorded=False)
    _audit_db(out, "base", {"ok": 59, "error": 1})
    assert [t.split(" (")[1] for t in _failed(out)] == [
        "v1.1: 1 failed, v1.4: 0 failed)",
        "v1.1 40.0 s, v1.4 30.0 s; not counted)",
    ]


def test_call_outcomes_that_were_never_recorded_fail_the_speed_criterion(out):
    for s in score.SETS:
        _run(out, "v14", s)
    _timed(out, "v14", 30.0, recorded=False)  # an old folder whose database is gone
    assert _failed(out) == [
        "6. every stance call of both timed audits answered, no runtime error or invalid output"
        " (v1.1: 0 failed, v1.4: not recorded)",
        "6. mean s per stance call at least 15% below v1.1's (v1.1 40.0 s, v1.4 30.0 s;"
        " not counted: call outcomes not recorded)",
    ]


def test_spread_and_the_call_by_call_ratio():
    assert score.spread([]) == "per-call times not recorded"
    assert score.spread([10.0, 20.0, 30.0, 40.0]) == (
        "4 calls, mean 25.0 s (SD 12.9), median 25.0 s, middle half 12.5 to 37.5 s"
    )
    assert score.paired([10.0, 20.0], [5.0]) is None  # different calls cannot be paired
    assert score.paired([10.0, 20.0, 40.0], [5.0, 10.0, 40.0]) == (
        "call by call, v1.4's time over v1.1's: median 0.50, middle half 0.50 to 1.00;"
        " v1.4 faster on 2 of 3 calls"
    )


def test_recall_may_lose_one_item_but_not_two(out):
    lost = _gold("signed", "supports")[:2]
    for s in score.SETS:
        _run(out, "v14", s, dict.fromkeys(lost[:1], "complicates") if s == "signed" else None)
    _timed(out, "v14", 30.0)
    assert score.passes(out)
    shutil.rmtree(out / "v14_signed")
    _run(out, "v14", "signed", dict.fromkeys(lost, "complicates"))
    _only_fails(out, "5. supports recall >= v1.1's")


def test_a_bar_v1_1_misses_only_needs_v1_4_to_be_no_worse(tmp_path):
    wrong = dict.fromkeys(_gold("signed", "complicates")[:3], "contradicts")  # precision < 90%
    for s in score.SETS:
        _run(tmp_path, "base", s, wrong if s == "signed" else None)
        _run(tmp_path, "v14", s, wrong if s == "signed" else None)
    _timed(tmp_path, "base", 40.0)
    _timed(tmp_path, "v14", 30.0)
    res = {text.split(":")[0]: ok for _, text, ok in score.criteria(tmp_path)}
    assert res["3. contradicts precision >= 90%"] is True
    assert score.passes(tmp_path)
    shutil.rmtree(tmp_path / "v14_signed")
    more = {**wrong, _gold("signed", "complicates")[3]: "contradicts"}
    _run(tmp_path, "v14", "signed", more)
    _only_fails(tmp_path, "3. contradicts precision >= 90%: v1.1 misses it")


def test_too_little_speedup_fails(out):
    for s in score.SETS:
        _run(out, "v14", s)
    _timed(out, "v14", 36.0)  # 10% below v1.1's 40 s, short of 15%
    _only_fails(out, "6. mean s per stance call at least 15% below v1.1's")


def test_nothing_is_recommended_until_everything_ran_on_one_model_file(out):
    for s in score.SETS:
        _run(out, "v14", s)
    _only_fails(out, "1. everything ran (missing: timed audit with v1.4)")
    _timed(out, "v14", 30.0, sha="6" * 64)
    _only_fails(out, "1. every run from one model file (found 2)")
