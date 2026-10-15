"""The probe shows a signed item as the product shows a record, and scores it as the product
would (grading audit, 2026-10-14). No model, no network."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from core.audit.context import HEADER
from core.llm.runtime import GenerationParams, ModelOutput
from eval.bench import claude_bench as cb
from eval.probe import prompts, run_probe
from eval.probe.from_draft import PROBE_HEADER, convert, member

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "eval" / "gold" / "probe" / "probe.jsonl"
V1_1 = ROOT / "eval" / "probe" / "stance_v1_1_signed.md"


def _rows() -> list[dict]:
    return [json.loads(x) for x in PROBE.read_text(encoding="utf-8").splitlines() if x.strip()]


def _item(pid: str) -> dict:
    return next(r for r in _rows() if r["probe_id"] == pid)


def test_product_layout_sends_the_message_text_as_the_record():
    item = _item("P001")
    reviewer, stance = convert(item)
    assert stance["record"] == item["target"]["text"] == stance["record_text"]
    lines = stance["context"].splitlines()
    # Today's product context opens with its header; no members line until v1.1 is wired.
    assert lines[0] == PROBE_HEADER and "Times are the phone's local time" in PROBE_HEADER
    assert "Members seen" not in stance["context"]
    marked = [ln for ln in lines if ln.startswith(">>")]
    assert marked == [">> [2026-03-12 20:03:27 EDT] Telegram 7001001 (owner), outgoing: "
                      "need 2 more by friday"]  # fmt: skip
    assert "acct:" not in stance["context"] and reviewer["context"] == stance["context"]
    assert stance["kind"] == "event"


def test_product_members_layout_opens_with_the_members_line():
    _, plain = convert(_item("P001"))
    _, stance = convert(_item("P001"), "product_members")
    lines = stance["context"].splitlines()
    assert lines[0] == (
        "Members seen in this chat's records: Telegram 5551234; Telegram 7001001 (owner)"
    )
    assert "\n".join(lines[1:]) == plain["context"] and stance["record"] == plain["record"]


def test_every_signed_item_marks_exactly_its_record():
    for item in _rows():
        _, stance = convert(item, "product_members")
        marked = [ln for ln in stance["context"].splitlines() if ln.startswith(">>")]
        assert len(marked) == 1 and marked[0].endswith(item["target"]["text"]), item["probe_id"]
        assert stance["record"] == item["target"]["text"]


def test_header_differs_from_the_product_only_in_naming_the_owner():
    assert PROBE_HEADER == HEADER.replace("'(this phone)'", "'(owner)'") != HEADER


def test_members_line_drops_saved_names_so_one_account_is_one_member():
    assert member("SMS +12125550122 Marc Garage") == "SMS +12125550122"
    assert member("Telegram 5551234 @alex92") == member("Telegram 5551234 @northstar")
    assert member("WhatsApp +16465550104 (owner)") == "WhatsApp +16465550104 (owner)"


def test_legacy_layout_reproduces_the_runs_before_the_audit():
    _, stance = convert(_item("P001"), "legacy")
    assert stance["record"].startswith("[2026-03-12 20:03:27 EDT] Telegram 7001001 (owner)")
    with pytest.raises(ValueError):
        convert(_item("P001"), "other")


class _Answers:
    """A stand-in model: each item's answers come from a table, in order."""

    name, sha256 = "fake", "fake"

    def __init__(self, table: dict[str, list[dict]]):
        self.table = {k: list(v) for k, v in table.items()}
        self.prompts: list[str] = []

    def generate_json(self, prompt, schema, params=None):
        self.prompts.append(prompt)
        item = re.search(r"\[RECORD START\]\n(.*)\n\[RECORD END\]", prompt, re.S).group(1)
        parsed = self.table[item].pop(0)
        return ModelOutput(raw_text=json.dumps(parsed), parsed=parsed, error=None)


def _score(answers: dict[str, list[dict]], pids: list[str], repeat: int = 2):
    items = [convert(_item(p))[1] for p in pids]
    table = {it["record_text"]: answers[it["id"]] for it in items}
    model = _Answers(table)
    st = run_probe.score_stance(model, items, GenerationParams(), repeat=repeat)
    return model, run_probe.expert_confirms(st)


def test_quotes_are_checked_as_the_product_checks_them():
    # P012 is gold supports. A quote that copies the rendered header, or cuts a word, is dropped.
    header = {"stance": "supports", "rationale": "r",
              "quote": "[2026-02-14 11:47:03 EST] happy valentines lol"}  # fmt: skip
    cut = {"stance": "supports", "quote": "happy valentines lo", "rationale": "r"}
    good = {"stance": "supports", "quote": "happy valentines lol", "rationale": "r"}
    _, ec = _score({"P012": [header, good]}, ["P012"])
    assert ec["supports_recall"] == 0.0  # the first answer decides
    assert ec["reported"]["other_repeats"][0]["supports_recall"] == 1.0
    assert ec["reported"]["labels_identical_across_repeats"] == 0.0
    _, ec = _score({"P012": [cut, cut]}, ["P012"])
    assert ec["supports_recall"] == 0.0


def test_one_answer_per_item_reports_no_repeat_agreement():
    good = {"stance": "supports", "quote": "happy valentines lol", "rationale": "r"}
    _, ec = _score({"P012": [good]}, ["P012"], repeat=1)
    assert ec["reported"]["labels_identical_across_repeats"] is None
    assert ec["reported"]["other_repeats"] == []


def test_overreach_count_is_part_of_the_trap_count():
    # P049 is an overreach item whose gold is contradicts: a supports there is not a trap shown
    # as supports (contradicts_shown_as_supports counts it), so neither count moves.
    item = _item("P049")
    assert item["category"] == "overreach" and item["gold_stance"] == "contradicts"
    sup = {"stance": "supports", "quote": item["target"]["text"], "rationale": "r"}
    _, ec = _score({"P049": [sup, sup]}, ["P049"])
    assert ec["reported"]["traps_shown_as_supports"] == 0
    assert ec["reported"]["overreach_shown_as_supports"] == 0
    assert ec["contradicts_shown_as_supports"] == 1


def test_reported_metrics_never_change_the_bars():
    # P029 (overreach, complicates) shown as supports; P045 (meaning) and P081 (event) called
    # contradicts; P062 (time) rightly contradicts.
    sup = {"stance": "supports", "rationale": "r"}
    con = {"stance": "contradicts", "rationale": "r"}
    answers = {}
    for pid, ans in (("P029", sup), ("P045", con), ("P081", con), ("P062", con)):
        quote = _item(pid)["target"]["text"]
        answers[pid] = [{**ans, "quote": quote}] * 2
    _, ec = _score(answers, ["P029", "P045", "P081", "P062"])
    rep = ec["reported"]
    assert rep["traps_shown_as_supports"] == 1 and rep["overreach_shown_as_supports"] == 1
    assert ec["contradicts_precision"] == pytest.approx(1 / 3)  # the gated bar counts all kinds
    assert rep["verdict_capable_contradicts_precision"] == 0.5  # P045 is a meaning assumption
    assert rep["verdict_capable_wrong_contradicts"] == 1
    assert rep["contradicts_precision_95ci"][0] < 1 / 3 < rep["contradicts_precision_95ci"][1]
    assert not ec["bars"]["contradicts_precision_90"]


def _signed_v1_1_from_proposed_changes() -> str | None:
    text = (ROOT / "PROPOSED_CHANGES.md").read_text(encoding="utf-8")
    start = text.find("## 2026-10-13 claude/project-thread-czwpc8: stance prompt v1.1")
    if start < 0:
        return None
    section = text[start:].split("\n## ", 1)[0]
    body = prompts._body(ROOT / "core" / "audit" / "prompts" / "stance.md")
    one = section.split("Diff, part one:\n", 1)[1].split("Diff, part two", 1)[0]
    # Part one: runs of removed lines, each followed by the lines that replace them.
    pairs = [
        tuple("".join(ln[1:] + "\n" for ln in run.splitlines()) for run in pair)
        for pair in re.findall(r"((?:^-.*\n)+)((?:^\+.*\n)+)", one, re.M)
    ]
    two = section.split("Diff, part two", 1)[1].split("Diff, part three", 1)[0]
    two = "".join(ln[1:] + "\n" for ln in two.splitlines() if ln.startswith("+"))
    three = section.split("Diff, part three", 1)[1].split("and the header's version line", 1)[0]
    three = "".join(ln[1:] + "\n" for ln in three.splitlines() if ln.startswith("+"))
    if all(old not in body and new in body for old, new in pairs) and two in body and three in body:
        return body  # the pipeline wiring (#62) applied v1.1 to the product prompt
    for old, new in pairs:
        assert body.count(old) == 1
        body = body.replace(old, new)
    body = body.replace("\nAssumption:\n", "\n" + two + "Assumption:\n", 1)
    return body.replace("Choose exactly one stance:", three + "Choose exactly one stance:", 1)


def test_bench_copy_of_v1_1_is_the_signed_text():
    expected = _signed_v1_1_from_proposed_changes()
    if expected is None:
        pytest.skip("v1.1 applied; PROPOSED_CHANGES.md no longer holds its diff")
    assert prompts._body(V1_1) == expected
    assert prompts.has_placeholder(V1_1, "claim")
    assert "a different sender, a different time" not in prompts._body(V1_1)


def test_bench_dry_run_on_v1_1_stance_only(tmp_path):
    client = cb.DryRunClient()
    model = cb.ClaudeModel("claude-haiku-5-5", client=client)
    res = cb.run_probe(model, cb.SIGNED_PROBE, 1, tmp_path, V1_1, stance_only=True,
                       layout="product_members")  # fmt: skip
    assert len(client.requests) == len(_rows())  # stance calls only
    prompt = client.requests[0]["messages"][0]["content"]
    assert "[CLAIM START]\n(not needed for this assumption)\n[CLAIM END]" in prompt
    assert "Members seen in this chat's records:" in prompt
    assert res["stance_prompt"].startswith("stance_v1_1_signed.md@") and res["stance_only"]
    assert res["layout"] == "product_members" and "reported" in res["expert_confirms"]
    # No reviewer ran: its parts of the old bars are not measured, so they do not fail.
    assert res["bars"]["valid_output_100"] and res["reviewer_items"] == 0


def test_bench_sends_only_prompt_files_from_the_prompt_folders(tmp_path):
    outside = tmp_path / "stance.md"
    outside.write_text("<!-- prompt starts -->\n{assumption}{record}{context}\n")
    with pytest.raises(cb.DataSafetyError):
        cb.check_prompt_path(outside)
    with pytest.raises(cb.DataSafetyError):
        cb.check_prompt_path(ROOT / "eval" / "gold" / "probe" / "README.md")
    assert cb.check_prompt_path(V1_1) == V1_1.resolve()
    assert cb.check_prompt_path(ROOT / "core" / "audit" / "prompts" / "stance.md")
    client = cb.DryRunClient()
    model = cb.ClaudeModel("claude-haiku-5-5", client=client)
    with pytest.raises(cb.DataSafetyError):
        cb.run_probe(model, cb.SIGNED_PROBE, 1, tmp_path / "out", outside, stance_only=True)
    assert client.requests == []
