import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.contracts import ClaimType, GoldClaim, Prediction, Verdict
from eval.validation.card import (
    RunVerdict,
    build_card,
    check_name,
    claims_for_upper_bound,
    load_checks,
    load_run,
    main,
    render_markdown,
    wilson,
)

SCHEMA = Path(__file__).resolve().parents[1] / "core" / "schema.sql"


def gold(claim_id: str, verdict: Verdict, ctype: ClaimType = ClaimType.COMMUNICATION, by="test"):
    return GoldClaim(
        claim_id=claim_id,
        page=1,
        para_no=1,
        text="t",
        claim_type=ctype,
        cross_device=False,
        gold_verdict=verdict,
        core_assumptions=(),
        key_evidence=(),
        trap=None,
        rationale="r",
        labeled_by=by,
        labeled_at=datetime(2026, 10, 21, tzinfo=UTC),
    )


def pred(claim_id: str, verdict: Verdict) -> Prediction:
    basis = "confirmed" if verdict is Verdict.SUPPORTED else None
    return Prediction(claim_id=claim_id, verdict=verdict, supported_basis=basis)


def test_wilson_gives_the_upper_bound_a_clean_run_still_allows():
    lo, hi = wilson(0, 12)
    assert lo == 0.0
    assert hi == pytest.approx(0.2425, abs=1e-4)
    assert wilson(0, 0) is None
    lo, hi = wilson(5, 10)
    assert lo < 0.5 < hi


def test_claims_needed_for_a_zero_error_upper_bound():
    assert claims_for_upper_bound(0.05) == 73
    assert wilson(0, 73)[1] <= 0.05 < wilson(0, 72)[1]
    assert claims_for_upper_bound(0.02) == 189


def test_check_name_reads_the_check_id():
    assert check_name("chk:asm:C04:no_contact:4c1b|absence@1.0.1") == "absence"


def test_false_supported_and_false_contradicted_use_their_own_denominators():
    g = [
        gold("C1", Verdict.SUPPORTED),
        gold("C2", Verdict.UNPROVEN, ClaimType.TIMING),
        gold("C3", Verdict.CONTRADICTED),
        gold("C4", Verdict.UNPROVEN),
        gold("C5", Verdict.SUPPORTED),
    ]
    p = [
        pred("C1", Verdict.SUPPORTED),
        pred("C2", Verdict.SUPPORTED),  # false supported
        pred("C3", Verdict.UNPROVEN),  # missed contradiction
        pred("C4", Verdict.CONTRADICTED),  # false contradicted
        # C5 has no prediction: wrong, but neither false supported nor false contradicted
    ]
    run = {
        "C4": RunVerdict("C4", "contradicted", ("timing",), 0, False),
    }
    card = build_card(g, p, run)
    assert card["accuracy"]["k"] == 1 and card["accuracy"]["n"] == 5
    assert (card["false_supported"]["k"], card["false_supported"]["n"]) == (1, 3)
    assert card["false_supported"]["by_basis"] == {"confirmed": 1}
    assert (card["false_contradicted"]["k"], card["false_contradicted"]["n"]) == (1, 4)
    assert card["false_contradicted"]["by_basis"] == {"failed check: timing": 1}
    assert (card["missed_contradicted"]["k"], card["missed_contradicted"]["n"]) == (1, 1)
    assert (card["missed_supported"]["k"], card["missed_supported"]["n"]) == (1, 2)
    timing = card["by_claim_type"]["timing"]
    assert timing["false_supported"]["k"] == 1 and timing["n"] == 1
    assert card["checks"] is None
    assert card["predicted"] == 4 and card["not_predicted"] == ["C5"]
    md = render_markdown(card)
    assert "| Claims predicted | predicted 4 of 5 |" in md
    assert (
        "| No prediction (counted wrong; never false supported or false contradicted) | 1: C5 |"
        in md
    )


def test_a_card_with_every_claim_predicted_has_no_missing_row():
    card = build_card([gold("C1", Verdict.SUPPORTED)], [pred("C1", Verdict.SUPPORTED)])
    md = render_markdown(card)
    assert card["not_predicted"] == [] and "predicted 1 of 1" in md
    assert "No prediction" not in md


def test_false_contradicted_by_accepted_evidence_and_override():
    g = [gold("C1", Verdict.UNPROVEN), gold("C2", Verdict.SUPPORTED)]
    p = [pred("C1", Verdict.CONTRADICTED), pred("C2", Verdict.CONTRADICTED)]
    run = {
        "C1": RunVerdict("C1", "contradicted", (), 2, False),
        "C2": RunVerdict("C2", "contradicted", ("sender",), 0, True),
    }
    basis = build_card(g, p, run)["false_contradicted"]["by_basis"]
    assert basis == {"expert-accepted evidence": 1, "expert override": 1}


def test_check_table_flags_leads_against_the_claims_gold():
    g = [gold("C1", Verdict.SUPPORTED), gold("C2", Verdict.CONTRADICTED)]
    checks = [
        ("C1", "time", "fail"),
        ("C1", "time", "pass"),
        ("C2", "sender", "pass"),
        ("C2", "sender", "fail"),
        ("C9", "time", "fail"),  # not in gold: ignored
    ]
    card = build_card(g, [], None, checks)
    assert card["checks"]["time"] == {
        "fail": 1,
        "fail_on_claim_gold_not_contradicted": 1,
        "pass": 1,
    }
    assert card["checks"]["sender"]["pass_on_claim_gold_contradicted"] == 1
    md = render_markdown(card)
    assert "| time | 1 | 1 | 0 | 1 | 0 |" in md


def _db(path: Path) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA.read_text("utf-8"))
    conn.execute("PRAGMA foreign_keys = OFF")  # only the tables the card reads are filled
    for rid, at in (("run:a", "2026-10-21T00:00:00Z"), ("run:b", "2026-10-21T01:00:00Z")):
        conn.execute(
            "INSERT INTO pipeline_runs (id, started_at_utc, status, baker_version,"
            " contracts_version, rule_version, config_json) VALUES (?,?,?,?,?,?,?)",
            (rid, at, "completed", "0.1.0", "0.4.0", "0.3.0", "{}"),
        )
    rows = [
        ("C1", "run:a", "unproven", None, {"checks": [], "evidence": []}),
        ("C2", "run:a", "contradicted", None, {"checks": ["chk:x|absence@1"], "evidence": []}),
        ("C1", "run:b", "supported", "confirmed", {"checks": [], "evidence": ["ev:1"]}),
        ("C2", "run:b", "contradicted", None, {"checks": ["chk:x|absence@1"], "evidence": []}),
    ]
    for claim_id, rid, verdict, basis, cited in rows:
        conn.execute(
            "INSERT INTO verdicts (id, claim_id, pipeline_run_id, verdict, supported_basis,"
            " rule_version, reasons_json, coverage_json, cited_json, decided_at_utc)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                f"vd:{claim_id}@{rid}",
                claim_id,
                rid,
                verdict,
                basis,
                "0.3.0",
                "[]",
                "[]",
                json.dumps(cited),
                "2026-10-21T00:00:00Z",
            ),
        )
    conn.execute(
        "INSERT INTO assumptions (id, claim_id, kind, template_id, template_version,"
        " params_json, text, is_core, tier) VALUES ('asm:C2', 'C2', 'event', 't', '1', '{}',"
        " 'x', 1, 'observed'), ('asm:C2b', 'C2', 'event', 't', '1', '{}', 'x', 0, 'observed')"
    )
    conn.execute(
        "INSERT INTO check_results (id, assumption_id, check_name, check_version, outcome,"
        " searched, detail) VALUES ('chk:x|absence@1', 'asm:C2', 'absence', '1', 'fail', 's',"
        " 'd'), ('chk:y|time@1', 'asm:C2b', 'time', '1', 'fail', 's', 'd')"
    )
    conn.commit()
    conn.close()
    return path


def test_load_run_matches_the_predictions_to_their_run(tmp_path):
    db = _db(tmp_path / "case.db")
    unreviewed = [pred("C1", Verdict.UNPROVEN), pred("C2", Verdict.CONTRADICTED)]
    rid, run = load_run(db, unreviewed, None)
    assert rid == "run:a"
    assert run["C2"].checks == ("absence",)
    rid, _ = load_run(db, [pred("C1", Verdict.SUPPORTED)], None)
    assert rid == "run:b"
    with pytest.raises(SystemExit):
        load_run(db, [pred("C1", Verdict.CONTRADICTED)], None)
    assert load_run(db, [], "run:a")[0] == "run:a"


def test_load_checks_reads_core_assumptions_only(tmp_path):
    db = _db(tmp_path / "case.db")
    assert load_checks(db, ["C2"]) == [("C2", "absence", "fail")]
    assert load_checks(db, []) == []


def test_main_writes_the_card_and_says_a_draft_key_is_unsigned(tmp_path):
    g = tmp_path / "gold.jsonl"
    g.write_text(
        "\n".join(
            x.model_dump_json()
            for x in (gold("C1", Verdict.UNPROVEN, by="DRAFT"), gold("C2", Verdict.CONTRADICTED))
        ),
        encoding="utf-8",
    )
    p = tmp_path / "predictions.jsonl"
    p.write_text(
        "\n".join(
            x.model_dump_json()
            for x in (pred("C1", Verdict.UNPROVEN), pred("C2", Verdict.CONTRADICTED))
        ),
        encoding="utf-8",
    )
    out = tmp_path / "card"
    db = _db(tmp_path / "case.db")
    assert (
        main(["--gold", str(g), "--predictions", str(p), "--db", str(db), "--out", str(out)]) == 0
    )
    card = json.loads((out / "card.json").read_text("utf-8"))
    assert card["inputs"]["gold_status"] == "DRAFT (1 of 2 unsigned)"
    assert card["inputs"]["run"] == "run:a"
    assert "| Verdict accuracy | 2 of 2 (100%)" in (out / "card.md").read_text("utf-8")
