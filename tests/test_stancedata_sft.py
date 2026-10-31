"""Chat training records (eval/stancedata/sft.py): each generated training item becomes the
prompt the probe sends for it and an answer the product's own checks accept. SYNTHETIC; no
model is trained or loaded here."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core.audit import stance
from core.llm.runtime import parse_json_output
from eval.probe import prompts
from eval.probe.from_draft import convert
from eval.probe.v13.score import prompt_text
from eval.stancedata import sft
from eval.stancedata.chat import write_jsonl
from eval.stancedata.contamination import Flag, Result, Text, payload
from eval.train.generate import generate

PROMPT = prompts.STANCE_PROMPT


@pytest.fixture(scope="module")
def items(tmp_path_factory) -> Path:  # noqa: ANN001
    path = tmp_path_factory.mktemp("sft") / "train.jsonl"
    write_jsonl(generate(40, 1, 20), path)  # plain items, then items in Baker's own wording
    return path


def _rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def test_each_item_is_the_prompt_the_probe_sends_and_an_answer_the_product_accepts(items):
    rows = _rows(items)
    out, left_out = sft.chats(rows, PROMPT)
    assert len(out) == len(rows) and not left_out
    assert {r["generator"].split()[0] for r in rows} == {"eval.train", "eval.train.baker"}
    for row, chat in zip(rows, out, strict=True):
        user, assistant = chat["messages"]
        assert (user["role"], assistant["role"]) == ("user", "assistant")
        assert user["content"] == prompt_text(convert(row, sft.LAYOUT)[1], PROMPT)
        parsed, error = parse_json_output(assistant["content"], stance.STANCE_SCHEMA)
        assert error is None
        got = stance.validate_stance_output(parsed)
        assert got.stance == chat["stance"] == row["gold_stance"]
        if got.stance != "irrelevant":
            assert got.quote == row["proposed_quote"] and got.quote in row["target"]["text"]


def test_an_answer_the_product_would_drop_is_left_out_and_counted(items):
    good = next(r for r in _rows(items) if r["gold_stance"] == "supports")
    bad_quote = {**good, "proposed_quote": good["proposed_quote"] + " (not in the record)"}
    banned = {**good, "rationale": "The message was deleted later."}
    no_quote = {**good, "proposed_quote": ""}
    out, left_out = sft.chats([good, bad_quote, banned, no_quote], PROMPT)
    assert [c["id"] for c in out] == [good["probe_id"]]
    assert left_out == {
        "quote not verbatim in the record": 1,
        "rationale uses a word the tool never says": 1,
        "not a valid stance answer": 1,
    }


def test_held_out_items_never_become_training_chats(items):
    row = _rows(items)[0]
    for held_out in ("D000001", "H000001"):
        with pytest.raises(SystemExit, match="only training items"):
            sft.chats([{**row, "probe_id": held_out}], PROMPT)


def test_the_same_items_give_the_same_file_and_a_manifest(items, tmp_path):
    first, second = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    for out in (first, second):
        assert sft.main(["--items", str(items), "--out", str(out)]) == 0
    assert first.read_bytes() == second.read_bytes()
    m = json.loads((tmp_path / "a.jsonl.manifest.json").read_text(encoding="utf-8"))
    assert m["chats"] == len(_rows(items)) and m["left_out"] == {}
    assert m["prompt_version"] == prompts.prompt_version(PROMPT)
    assert sum(m["by_stance"].values()) == m["chats"]
    assert m["overlap"] is None  # not checked, so not for training


def _overlap(tmp_path: Path, train: list[Path], held: list[Path], results: list[Result]) -> Path:
    path = tmp_path / f"report{len(list(tmp_path.glob('report*.json')))}.json"
    path.write_text(json.dumps(payload(results, train, held)), encoding="utf-8")
    return path


def test_only_an_overlap_check_that_passed_on_these_items_is_recorded(items, tmp_path):
    held = tmp_path / "heldout_test.jsonl"
    held.write_text("{}\n", encoding="utf-8")
    clean = [Result("train vs test data"), Result("held-out vs test data"),
             Result("train vs held-out")]  # fmt: skip
    report = _overlap(tmp_path, [items], [held], clean)
    out = tmp_path / "chats.jsonl"
    assert sft.main(["--items", str(items), "--out", str(out), "--overlap", str(report)]) == 0
    m = json.loads((tmp_path / "chats.jsonl.manifest.json").read_text(encoding="utf-8"))
    assert m["overlap"]["report"] == str(report)
    sha = hashlib.sha256(held.read_bytes()).hexdigest()
    assert m["overlap"]["heldout"] == [{"path": str(held), "sha256": sha}]
    other = tmp_path / "other.jsonl"
    other.write_text("{}\n", encoding="utf-8")
    flag = Flag("exact", 1.0, Text("train T1 record", "x"), Text("heldout H1 record", "x"))
    flagged = [*clean[:2], Result("train vs held-out", flags=[flag])]
    for report, why in (
        (_overlap(tmp_path, [other], [held], clean), "did not check this items file"),
        (_overlap(tmp_path, [items], [held], clean[:2]), "lacks train vs held-out"),
        (_overlap(tmp_path, [items], [], clean), "lacks held-out files"),
        (_overlap(tmp_path, [items], [held], flagged), "found overlap"),
    ):  # fmt: skip
        with pytest.raises(SystemExit, match=why):
            sft.main(["--items", str(items), "--out", str(out), "--overlap", str(report)])
    old = tmp_path / "old.json"  # the check's report from before it named its files
    old.write_text(json.dumps(payload(clean, [items], [held])["comparisons"]), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not name the files"):
        sft.main(["--items", str(items), "--out", str(out), "--overlap", str(old)])
