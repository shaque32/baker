"""Replaying recorded stance calls (eval/probe/replay.py): today's code rebuilds a recorded
audit's prompts byte for byte, a variant changes only the prompt order or the context size, and
labels are compared the way the product stores them. A stand-in model, synthetic case01 only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core import pipeline
from core.db import connect
from core.llm.runtime import FakeModel
from eval import run_pipeline as rp
from eval.loss_report import open_readonly
from eval.probe import replay, time_case

CLAIMS = ["C02", "C05", "C12"]


def _record_text(prompt: str) -> str:
    return prompt.split("[RECORD START]\n", 1)[1].split("\n[RECORD END]", 1)[0]


def supports_everything(prompt: str) -> str:
    """Says "supports" and quotes the whole record, so every label passes the quote check."""
    return json.dumps(
        {"stance": "supports", "quote": _record_text(prompt), "rationale": "stand-in"}
    )


@pytest.fixture(scope="module")
def recorded_db(tmp_path_factory) -> Path:  # noqa: ANN001
    """A case01 audit of three claims, labelled by the stand-in through the product's wiring."""
    path = tmp_path_factory.mktemp("recorded") / "case01.db"
    conn = rp.build_case("case01", path)
    comps = time_case._components(  # noqa: SLF001 - the speed test's product wiring
        conn, FakeModel(respond=supports_everything), time_case.default_spec(), False
    )
    pipeline.run_audit(conn, comps, clock=rp._clock, claim_ids=CLAIMS)  # noqa: SLF001
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def conn(recorded_db, tmp_path):  # noqa: ANN001, ANN201
    copy = tmp_path / "case01.db"
    shutil.copy(recorded_db, copy)
    db = open_readonly(copy)
    yield db
    db.close()


def test_every_recorded_prompt_rebuilds_exactly_and_v14_reads_less(conn) -> None:  # noqa: ANN001
    rec = replay.recorded(conn)
    assert rec.calls and rec.model_sha256 == FakeModel.sha256
    out = replay.check(conn, rec.calls)
    assert out["rebuilt_exactly"] == out["recorded_calls"] == len(rec.calls)
    v = out["variants"]
    assert v["signed_w20"]["prompt_chars"] == out["recorded_prompt_chars"]
    assert v["v14_w20"]["prompt_chars"] == v["signed_w20"]["prompt_chars"]  # same words
    assert v["v14_w20"]["new_chars"] < v["signed_w20"]["new_chars"]
    assert v["signed_w5"]["prompt_chars"] <= v["signed_w8"]["prompt_chars"]
    assert v["signed_w8"]["prompt_chars"] <= v["signed_w20"]["prompt_chars"]


def test_the_recorded_variant_replays_the_same_answers(conn, tmp_path) -> None:  # noqa: ANN001
    rec = replay.recorded(conn)
    model = FakeModel(respond=supports_everything)
    meta = replay.run(conn, model, rec.calls, "signed", 20, tmp_path / "base", rec.model_sha256)
    assert meta["not_rebuilt"] == 0
    rows = replay.read_rows(tmp_path / "base")
    assert len(rows) == len(rec.calls)
    assert all(r["same_raw"] and r["recorded"] == r["replayed"] for r in rows)
    assert {r["recorded"] for r in rows} <= {"supports", "complicates", "dropped"}
    assert model.calls == [c.prompt for c in rec.calls]  # the recorded prompts, in order
    text = replay.report(tmp_path)
    assert "the recorded model file" in text and "new supports 0" in text


def test_a_variant_sends_the_same_words_in_its_own_order(conn, tmp_path) -> None:  # noqa: ANN001
    rec = replay.recorded(conn)
    model = FakeModel(respond=supports_everything)
    replay.run(conn, model, rec.calls[:5], "v14", 20, tmp_path / "v14", rec.model_sha256)
    for sent, call in zip(model.calls, rec.calls[:5], strict=True):
        assert sent != call.prompt
        assert sorted(sent.splitlines()) == sorted(call.prompt.splitlines())
    rows = replay.read_rows(tmp_path / "v14")
    assert all(r["replayed"] == r["recorded"] for r in rows)  # same answers, same labels


def test_changed_labels_are_counted_by_direction(conn, tmp_path) -> None:  # noqa: ANN001
    rec = replay.recorded(conn)
    model = FakeModel(respond=lambda p: '{"stance": "irrelevant", "quote": "", "rationale": "n"}')
    replay.run(conn, model, rec.calls, "signed", 8, tmp_path / "w8", rec.model_sha256)
    c = replay.compare(replay.read_rows(tmp_path / "w8"))
    supports = sum(r["recorded"] == "supports" for r in replay.read_rows(tmp_path / "w8"))
    assert c["lost_supports"] == supports > 0
    assert c["new_supports"] == 0
    assert c["same_label"] == c["calls"] - sum(
        r["recorded"] != "irrelevant" for r in replay.read_rows(tmp_path / "w8")
    )


def test_a_stopped_replay_resumes_without_asking_twice(conn, tmp_path) -> None:  # noqa: ANN001
    rec = replay.recorded(conn)
    first = FakeModel(respond=supports_everything)
    replay.run(conn, first, rec.calls[:3], "signed", 20, tmp_path / "r", rec.model_sha256)
    again = FakeModel(respond=supports_everything)
    replay.run(conn, again, rec.calls[:6], "signed", 20, tmp_path / "r", rec.model_sha256)
    assert len(again.calls) == 3
    assert [r["seq"] for r in replay.read_rows(tmp_path / "r")] == [c.seq for c in rec.calls[:6]]


def test_sample_keeps_whole_assumptions_in_order(conn) -> None:  # noqa: ANN001
    calls = replay.recorded(conn).calls
    kept = replay.sample(calls, 2)
    order = list(dict.fromkeys(c.assumption_id for c in calls))
    assert {c.assumption_id for c in kept} == set(order[::2])
    assert kept == [c for c in calls if c.assumption_id in set(order[::2])]


def test_the_hidden_case_is_refused(tmp_path) -> None:  # noqa: ANN001
    db = tmp_path / "case02" / "case.db"
    with pytest.raises(SystemExit, match="hidden"):
        replay.main(["check", "--db", str(db)])


def test_a_write_connection_is_never_needed(recorded_db, tmp_path) -> None:  # noqa: ANN001
    copy = tmp_path / "ro.db"
    shutil.copy(recorded_db, copy)
    assert replay.main(["check", "--db", str(copy)]) == 0
    db = connect(copy)  # still a well-formed case database after the check
    assert db.execute("SELECT count(*) FROM model_calls").fetchone()[0] > 0
    db.close()


def _folder(out: Path, name: str, rows: list[dict], sha: str = "a" * 64) -> None:
    d = out / name
    d.mkdir(parents=True)
    meta = {"prompt": "signed", "window": 8, "model": "m", "model_sha256": sha,
            "recorded_model_sha256": "a" * 64}  # fmt: skip
    (d / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    (d / "calls.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _row(seq: int, label: str, seconds: float, record: str = "r", same: bool = True) -> dict:
    return {"seq": seq, "claim_id": "C01", "record_id": f"{record}{seq}", "template": "sender",
            "recorded": label, "replayed": label, "same_raw": same, "seconds": seconds,
            "prompt_chars": 100, "perf": None}  # fmt: skip


@pytest.fixture
def gold(tmp_path) -> Path:  # noqa: ANN001
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps({"claim_id": "C01", "key_evidence": ["k2"]}) + "\n", "utf-8")
    return path


def _window(tmp_path: Path, short: list[dict], base: list[dict] | None = None) -> Path:
    out = tmp_path / "out"
    labels = ["supports", "complicates", "irrelevant", "contradicts"]
    base = base or [_row(i, labels[i % 4], 40.0, "k" if i == 2 else "r") for i in range(8)]
    _folder(out, replay.BASE, base)
    _folder(out, replay.SHORT, short)
    return out


def _short(**changes: str) -> list[dict]:
    labels = ["supports", "complicates", "irrelevant", "contradicts"]
    rows = [_row(i, labels[i % 4], 30.0, "k" if i == 2 else "r") for i in range(8)]
    for seq, label in changes.items():
        rows[int(seq[1:])]["replayed"] = label
    return rows


def _not_met(out: Path, gold: Path) -> list[str]:
    return [text.split(" (")[0] for text, ok in replay.window_criteria(out, gold) if not ok]


def test_the_same_labels_and_a_faster_call_recommend_the_shorter_context(tmp_path, gold) -> None:  # noqa: ANN001
    out = _window(tmp_path, _short())
    assert _not_met(out, gold) == []
    text = replay.report(out, gold)
    assert "Recommendation: show 8 messages each side" in text
    # the spread, the call-by-call ratio and the run record are printed beside the decision
    assert "time per call: 8 calls, mean 30.0 s (SD 0.0)" in text
    assert "Call by call, signed_w8's time over signed_w20's: median 0.75" in text
    assert "faster on 8 of 8 calls" in text
    assert f"| signed_w8 | {'a' * 64} |" in text


def test_each_risky_change_fails_its_own_criterion(tmp_path, gold) -> None:  # noqa: ANN001
    # s2 is the key record (irrelevant -> supports); s1 leaves complicates.
    out = _window(tmp_path, _short(s2="supports", s1="irrelevant"))
    assert _not_met(out, gold) == [
        "3. no call newly labelled supports",
        "4. no call leaves complicates or contradicts",
        "5. no key record changes its label",
    ]
    assert "Recommendation: keep 20 messages" in replay.report(out, gold)


def test_a_baseline_that_does_not_repeat_the_recording_stops_the_decision(tmp_path, gold) -> None:  # noqa: ANN001
    labels = ["supports", "complicates", "irrelevant", "contradicts"]
    base = [_row(i, labels[i % 4], 40.0, same=i != 0) for i in range(8)]
    out = _window(tmp_path, _short(), base)
    assert _not_met(out, gold)[0].startswith("2. the 20-message replay repeats")


def test_failed_calls_never_count_as_a_speedup(tmp_path, gold) -> None:  # noqa: ANN001
    # A runtime error comes back empty at once: an irrelevant call that fails moves no risky
    # label, but its near-zero seconds would pull the mean down.
    short = _short(s6="invalid")
    short[6]["seconds"] = 0.1
    out = _window(tmp_path / "a", short)
    assert _not_met(out, gold) == [
        "6. every replayed call answered, no runtime error or invalid output",
        "6. mean s per call at least 10% below the 20-message replay's",
    ]
    text = replay.report(out, gold)
    assert "(0 failed with 20 messages, 1 with 8)" in text and "; not counted)" in text
    assert "failed calls 1;" in text
    labels = ["supports", "complicates", "irrelevant", "contradicts"]
    base = [_row(i, labels[i % 4], 40.0, "k" if i == 2 else "r") for i in range(8)]
    base[6]["replayed"] = "invalid"  # the same in the 20-message replay
    assert _not_met(_window(tmp_path / "b", _short(), base), gold)[0] == (
        "6. every replayed call answered, no runtime error or invalid output"
    )


def test_too_little_speedup_or_other_calls_fail(tmp_path, gold) -> None:  # noqa: ANN001
    slow = [dict(r, seconds=38.0) for r in _short()]
    assert _not_met(_window(tmp_path / "a", slow), gold) == [
        "6. mean s per call at least 10% below the 20-message replay's"
    ]
    fewer = _short()[:-1]
    assert _not_met(_window(tmp_path / "b", fewer), gold) == [
        "1. both ran the same calls on the recorded model file"
    ]
