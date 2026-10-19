"""The 14B-vs-Opus test's own scoring (eval/bench/fair_steps.py): the split-aware claim matcher,
the replay of a first audit's fills and the cloud retry. No model is called."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.contracts import ClaimType, GoldClaim, Verdict
from core.db import apply_schema, connect
from core.llm.cloud import CloudError
from eval.bench.fair_steps import (
    Proposal,
    ReplayModel,
    Retried,
    canonical_people,
    compare,
    main,
    pick_entry,
    revision,
    sheet_coverage,
    split_match,
    summary,
)


def gold(cid: str, para: int, text: str) -> GoldClaim:
    return GoldClaim(
        claim_id=cid, page=1, para_no=para, text=text, claim_type=ClaimType.COMMUNICATION,
        cross_device=False, gold_verdict=Verdict.SUPPORTED, core_assumptions=(),
        key_evidence=(), trap=None, rationale="test", labeled_by="test",
        labeled_at=datetime(2026, 10, 16, tzinfo=UTC),
    )  # fmt: skip


G1 = gold("C01", 4, "PETROV sent 3 Telegram messages to REYES on March 6, 2026")
G2 = gold("C02", 4, "REYES replied the next morning asking about the tickets")


def found(rows: list[dict]) -> dict[str, bool]:
    return {r["claim_id"]: r["found"] for r in rows}


def test_a_claim_split_into_several_proposals_is_found() -> None:
    props = [
        Proposal("p1", "4", "PETROV sent 3 Telegram messages to REYES."),
        Proposal("p2", "4", "PETROV's messages to REYES were sent on March 6, 2026."),
    ]
    rows = split_match([G1], props)
    assert found(rows) == {"C01": True}
    assert rows[0]["proposals"] == ["p1", "p2"]


def test_one_proposal_counts_toward_one_gold_claim_only() -> None:
    whole = Proposal("p1", "4", f"{G1.text}. {G2.text}.")
    assert sum(found(split_match([G1, G2], [whole])).values()) == 1


def test_every_number_must_be_kept_and_the_paragraph_must_match() -> None:
    no_date = Proposal("p1", "4", "PETROV sent 3 Telegram messages to REYES on March")
    assert found(split_match([G1], [no_date])) == {"C01": False}
    elsewhere = Proposal("p1", "5", G1.text)
    assert found(split_match([G1], [elsewhere])) == {"C01": False}


def test_strict_matching_stops_unrelated_fragments_pooling_their_words() -> None:
    bits = [
        Proposal("p1", "4", "PETROV owns a garage in Queens"),
        Proposal("p2", "4", "Telegram was installed on 3 phones"),
        Proposal("p3", "4", "REYES moved house in March 2026 and 6 cats came"),
    ]
    assert found(split_match([G1], bits)) == {"C01": True}  # the registered matcher
    assert found(split_match([G1], bits, strict=True)) == {"C01": False}
    real = [
        Proposal("p1", "4", "PETROV sent 3 Telegram messages to REYES."),
        Proposal("p2", "4", "PETROV's messages to REYES were sent on March 6, 2026."),
    ]
    assert found(split_match([G1], real, strict=True)) == {"C01": True}


def test_fills_cover_a_claim_only_with_every_signed_core_template() -> None:
    sheet = [
        {"claim_id": "C01", "template_id": "contact_entry", "is_core": True},
        {"claim_id": "C02", "template_id": "same_account", "is_core": True},
        {"claim_id": "C02", "template_id": "record_time", "is_core": True},
        {"claim_id": "C02", "template_id": "record_time", "is_core": True},
        {"claim_id": "C02", "template_id": "meaning", "is_core": False},
    ]
    fills = [
        ("C01", "contact_entry", {}),
        ("C01", "event", {}),
        ("C02", "event", {}),
        ("C02", "record_time", {}),
    ]
    res = sheet_coverage(sheet, fills)
    assert (res["covered"], res["claims"]) == (1, 2)
    c02 = res["rows"][1]
    assert (c02["missing"], c02["extra"]) == (["record_time", "same_account"], ["event"])
    assert res["rows"][0]["extra"] == ["event"]  # listed, not held against the claim


WINDOW = {"start_utc": "2026-03-10T04:00:00Z", "end_utc": "2026-04-01T03:59:59.999999Z"}
SIGNED = {"handles": ["@northstar"], "expected_count": 13, "count_op": "eq", "window": WINDOW}


def test_a_fill_with_the_right_template_and_a_wrong_value_does_not_match_the_sheet() -> None:
    sheet = [{"claim_id": "C03", "template_id": "message_count", "is_core": True,
              "params": SIGNED}]  # fmt: skip
    right = {**SIGNED, "window": {**WINDOW, "raw": "March 10-31", "tz": "America/New_York"},
             "channels": ["Telegram"], "quoted_text": None}  # fmt: skip
    res = sheet_coverage(sheet, [("C03", "message_count", right)])
    assert (res["covered"], res["params_covered"]) == (1, 1)
    for wrong in ({"expected_count": 12}, {"handles": ["@northstar", "@alex92"]},
                  {"window": {**WINDOW, "end_utc": "2026-03-31T03:59:59Z"}}):  # fmt: skip
        res = sheet_coverage(sheet, [("C03", "message_count", {**right, **wrong})])
        assert (res["covered"], res["params_covered"]) == (1, 0)
        assert res["rows"][0]["params_missed"] == ["message_count"]


def test_two_signed_rows_need_two_fills() -> None:
    a = {"quoted_text": "hey its sasha"}
    b = {"quoted_text": "not now"}
    row = {"claim_id": "C02", "template_id": "record_time", "is_core": True}
    sheet = [{**row, "params": a}, {**row, "params": b}]
    one = sheet_coverage(sheet, [("C02", "record_time", {"quoted_text": "Hey  its Sasha"})])
    assert one["rows"][0]["params_missed"] == ["record_time"]
    both = [("C02", "record_time", {"quoted_text": "Hey  its Sasha"}),
            ("C02", "record_time", b)]  # fmt: skip
    assert sheet_coverage(sheet, both)["params_covered"] == 1


def test_strict_matching_needs_fragments_that_state_something() -> None:
    keywords = [Proposal(f"p{i}", "4", w) for i, w in
                enumerate(["PETROV", "Telegram 3", "REYES", "March 6, 2026"])]  # fmt: skip
    assert found(split_match([G1], keywords)) == {"C01": True}  # the registered matcher
    assert found(split_match([G1], keywords, strict=True)) == {"C01": False}


def arm(split: int, strict: int, fills: float, sheet: int, commit: str = "abc") -> dict:
    return {
        "revision": {"commit": commit, "dirty": False},
        "claims": {"split_found": ["C"] * split, "split_found_strict": ["C"] * strict},
        "audit": {"n_false_supported": 0},
        "fills_only": {"verdict_accuracy": fills, "n_false_supported": 0},
        "sheet": {"claims": 20, "params_covered": sheet},
    }


def decide(local: dict, opus: dict) -> str:
    """compare() on two arms built by arm(), each marked with its own arm and a model hash."""
    return compare({"arm": "local", "model_sha256": "14b", **local},
                   {"arm": "opus", "model_sha256": "opus", **opus})  # fmt: skip


def test_the_decision_needs_a_win_on_both_measures_of_a_step() -> None:
    out = decide(arm(17, 17, 0.60, 5), arm(19, 19, 0.75, 6))
    assert "- Claim proposal: moves toward Opus" in out
    assert "- Assumption filling: stays local" in out  # 4b won by 1 only
    assert "CHECK" not in out
    assert "- Claim proposal: stays local" in decide(arm(17, 18, 0.6, 5), arm(19, 19, 0.6, 5))


def test_the_decision_flags_runs_that_are_not_comparable() -> None:
    opus = arm(19, 19, 0.75, 9, commit="def")
    opus["revision"]["dirty"] = True
    out = decide(arm(17, 17, 0.6, 5), opus)
    assert "CHECK: opus arm ran with uncommitted changes" in out
    assert "CHECK: the arms ran at different commits" in out
    assert out.count("not decided: runs not comparable") == 2


def test_an_invalid_arm_or_another_commit_decides_nothing() -> None:
    invalid = arm(20, 20, 1.0, 20)
    invalid["invalid"] = "a cloud call failed after its retries"
    for opus in (invalid, arm(20, 20, 1.0, 20, commit="def")):
        out = decide(arm(10, 10, 0.5, 2), opus)
        assert out.count("not decided: runs not comparable") == 2
        assert "moves toward Opus" not in out and "stays local" not in out
    no_commit = arm(20, 20, 1.0, 20)
    no_commit["revision"] = {}
    out = decide(arm(10, 10, 0.5, 2), no_commit)  # listed, as the plan says, but decides
    assert "CHECK: opus arm recorded no commit" in out
    assert out.count("moves toward Opus") == 2
    bad = arm(17, 17, 0.6, 5)
    bad["fills_only"]["n_false_supported"] = 1
    assert "moves toward Opus" not in decide(bad, arm(20, 20, 1.0, 20))


def _db_with_call(path: Path, prompt: str, raw: str, outcome: str = "ok") -> None:
    conn = connect(path)
    apply_schema(conn)
    conn.execute(
        "INSERT INTO model_runs (id, purpose, model_name, model_sha256, prompt_version,"
        " params_json, started_at_utc) VALUES ('mr:1', 'assumptions', 'm', 'abc', 'v', '{}',"
        " '2026-10-16T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO model_calls (id, model_run_id, seq, subject_json, prompt, raw_output,"
        " outcome, at_utc) VALUES ('mc:mr:1#1', 'mr:1', 1, '[]', ?, ?, ?,"
        " '2026-10-16T00:00:01Z')",
        (prompt, raw, outcome),
    )
    conn.commit()
    conn.close()


def test_the_replay_answers_only_prompts_the_first_audit_sent(tmp_path: Path) -> None:
    db = tmp_path / "case01.db"
    _db_with_call(db, "fill C01", '{"assumptions": []}')
    replay = ReplayModel(db, "assumptions")
    assert replay.sha256 == "abc"
    assert replay.generate_json("fill C01", {}).raw_text == '{"assumptions": []}'
    with pytest.raises(LookupError):
        replay.generate_json("fill C02", {})


def test_the_replay_skips_failed_calls(tmp_path: Path) -> None:
    db = tmp_path / "case01.db"
    _db_with_call(db, "fill C01", "", outcome="error")
    with pytest.raises(LookupError):
        ReplayModel(db, "assumptions").generate_json("fill C01", {})
    with pytest.raises(LookupError):
        ReplayModel(db, "stance")
    assert sqlite3.connect(db).execute("SELECT count(*) FROM model_calls").fetchone() == (1,)


def test_the_local_arm_and_the_mac_probe_pick_the_same_one_model() -> None:
    two = [{"name": "qwen3-8b-q4_k_m"}, {"name": "qwen3-14b-q4_k_m"}]
    assert pick_entry(two, None)["name"] == "qwen3-14b-q4_k_m"
    assert pick_entry(two, "qwen3-8b-q4_k_m")["name"] == "qwen3-8b-q4_k_m"
    assert pick_entry([{"name": "other"}], None)["name"] == "other"
    with pytest.raises(SystemExit):
        pick_entry([{"name": "a"}, {"name": "b"}], None)
    with pytest.raises(SystemExit):
        pick_entry(two, "missing")


def test_an_unknown_effort_is_refused_before_any_call() -> None:
    with pytest.raises(SystemExit):
        main(["--arm", "opus", "--effort", "medum"])


class Flaky:
    """A stand-in cloud model that raises the given failures, then answers."""

    name, sha256, params, where = "claude-opus-5-5", "x", None, "cloud"

    def __init__(self, *failures: CloudError) -> None:
        self.failures, self.sent = list(failures), 0

    def generate_json(self, prompt: str, schema: object, params: object = None) -> str:
        self.sent += 1
        if self.failures:
            raise self.failures.pop(0)
        return "ok"

    def usage(self) -> dict[str, int]:
        return {"calls": self.sent}


def timeout() -> CloudError:
    return CloudError("APITimeoutError", sticky=True, retryable=True)


def test_a_retryable_failure_is_sent_again_as_the_product_does() -> None:
    m = Retried(Flaky(timeout(), timeout()), sleep=lambda _s: None)
    assert m.generate_json("p", {}) == "ok"
    assert (m.failure, m.usage()) == (None, {"calls": 3})


def test_a_failure_left_after_the_retries_makes_the_run_invalid() -> None:
    inner = Flaky(timeout(), timeout(), timeout())
    m = Retried(inner, sleep=lambda _s: None)
    with pytest.raises(CloudError):
        m.generate_json("p", {})
    assert m.failure == "APITimeoutError"
    with pytest.raises(CloudError):  # later calls are not sent at all
        m.generate_json("q", {})
    assert inner.sent == 3
    res = {"arm": "opus", "model": m.name, "invalid": "a cloud call failed"}
    assert "INVALID, do not score" in summary(res)


def test_a_refusal_is_the_models_own_dropped_label_not_an_invalid_run() -> None:
    m = Retried(Flaky(CloudError("declined", sticky=False)), sleep=lambda _s: None)
    with pytest.raises(CloudError):
        m.generate_json("p", {})
    assert m.failure is None
    assert m.generate_json("q", {}) == "ok"


def test_the_files_must_be_given_local_then_opus_with_a_14b_hash() -> None:
    lo, op = arm(10, 10, 0.5, 2), arm(20, 20, 1.0, 20)
    out = compare(
        {"arm": "opus", "model_sha256": "x", **op}, {"arm": "local", "model_sha256": "y", **lo}
    )
    assert "CHECK: the local file is the 'opus' arm" in out
    assert out.count("not decided: runs not comparable") == 2
    out = compare({"arm": "local", **lo}, {"arm": "opus", **op})
    assert "CHECK: local arm recorded no model hash" in out
    assert out.count("not decided: runs not comparable") == 2


def test_the_sheet_names_people_the_way_the_case_does_before_comparing() -> None:
    sheet = [{"claim_id": "C09", "template_id": "record_time", "is_core": True,
              "params": {"person_ids": ["person:petrov"], "quoted_text": "ok"}}]  # fmt: skip
    mapped = canonical_people(sheet, {"person:petrov": "person:dev:item1:owner"})
    assert mapped[0]["params"]["person_ids"] == ["person:dev:item1:owner"]
    assert sheet[0]["params"]["person_ids"] == ["person:petrov"]  # the signed rows are not changed
    fill = ("C09", "record_time", {"person_ids": ["person:dev:item1:owner"], "quoted_text": "ok"})
    assert sheet_coverage(mapped, [fill])["params_covered"] == 1
    third = canonical_people(
        [{**sheet[0], "params": {"person_ids": ["person:sokolov"]}}], {"person:petrov": "x"}
    )
    assert third[0]["params"]["person_ids"] == ["person:sokolov"]  # no owner: unchanged


def test_each_result_records_the_commit_it_ran_at() -> None:
    rev = revision()
    assert set(rev) == {"commit", "dirty"}
    assert rev["commit"] is None or len(rev["commit"]) == 40
