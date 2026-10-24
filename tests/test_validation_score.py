"""The validation-v1 scorer (eval/validation/score_hickman.py) on a small synthetic UFDR: the run
driver builds and audits it with stand-in components, the independent dump reads its report.xml,
and the scorer maps the keys by content, scores R1, and runs the simulated expert for R2."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from eval.synthetic.ufdr import field, many, model, one, party, report_xml, ts_field, write_package
from eval.validation import dump_ufdr, hickman_run, score_hickman

OWNER = ("+15550100001", None, True)
JO = ("+15550100002", "Jo", False)
T1 = "2023-04-28T15:39:15.000+00:00"
T2 = "2023-04-28T15:41:02.000+00:00"
T3 = "2023-04-28T16:00:00.000+00:00"
CHAT_ID = "c0ffee00-0000-4000-8000-000000000001"


def _msg(si: str, body: str, ts: str, frm=JO, to=(OWNER,)) -> str:  # noqa: ANN001
    return model(
        "InstantMessage",
        field("Source", "WhatsApp"),
        one("From", party(*frm)),
        many("To", [party(*p) for p in to]),
        field("Body", body),
        ts_field("TimeStamp", ts),
        source_index=si,
        id=f"m-{si}",
    )


def _package(path: Path) -> Path:
    chat = model(
        "Chat",
        field("Source", "WhatsApp"),
        field("Id", "1"),
        field("Name", "Jo"),
        many("Participants", [party(*OWNER), party(*JO)]),
        many(
            "Messages",
            [
                _msg("11", "meet at the dock", T1),
                _msg("12", "bring the car", T2, frm=OWNER, to=(JO,)),
                _msg("13", "ok", T3),  # two records alike in time, app and text: ambiguous
                _msg("14", "ok", T3),
            ],
            "InstantMessage",
        ),
        id=CHAT_ID,
        source_index="10",
    )
    call = model(
        "Call",
        field("Source", "Phone"),
        field("Type", "Outgoing", "CallType"),
        ts_field("TimeStamp", "2023-04-28T17:00:00.000+00:00"),
        field("Duration", "00:01:30", "TimeSpan"),
        many("Parties", [party(*JO, role="To")]),
        source_index="21",
        id="call-21",
    )
    contact = model(
        "Contact",
        field("Source", "Phone"),
        field("Name", "Marc Garage"),
        many(
            "Entries",
            [model("PhoneNumber", field("Category", "Mobile"), field("Value", "+12125550122"))],
            "ContactEntry",
        ),
        source_index="31",
        id="contact-31",
    )
    xml = report_xml({"Contact": [contact], "Chat": [chat], "Call": [call]})
    return write_package(path, xml)


def _gold(claim_id: str, para: int, text: str, verdict: str, keys: list[str]) -> dict:
    return {
        "claim_id": claim_id, "page": 1, "para_no": para, "text": text,
        "claim_type": "content", "cross_device": False, "gold_verdict": verdict,
        "core_assumptions": [], "key_evidence": [f"ufdr:source_index:{k}" for k in keys],
        "trap": None, "rationale": "synthetic", "labeled_by": "test",
        "labeled_at": "2026-10-24T00:00:00Z",
    }  # fmt: skip


GOLD = [
    _gold("C01", 1, 'Jo wrote "meet at the dock".', "supported", ["11", CHAT_ID, "13", "999"]),
    _gold("C02", 2, 'SUBJECT-1 wrote "bring the van".', "contradicted", ["12"]),
    _gold("C03", 3, 'Jo wrote "see you at noon".', "unproven", []),
]


@pytest.fixture(scope="module")
def scored(tmp_path_factory) -> tuple[Path, dict]:
    tmp = tmp_path_factory.mktemp("score")
    ufdr = _package(tmp / "phone.ufdr")
    claims = tmp / "claims.jsonl"
    keep = ("claim_id", "page", "para_no", "text", "claim_type")
    claims.write_text(
        "".join(json.dumps({k: g[k] for k in keep}) + "\n" for g in GOLD), encoding="utf-8"
    )
    run = tmp / "run"
    args = ["--ufdr", str(ufdr), "--claims", str(claims), "--out", str(run), "--fake"]
    assert hickman_run.main(args) == 0

    xml = tmp / "report.xml"
    with zipfile.ZipFile(ufdr) as z:
        xml.write_bytes(z.read("report.xml"))
    dump_ufdr.main([str(xml), str(tmp / "dump")])

    keys = tmp / "keys"
    keys.mkdir()
    (keys / "gold.jsonl").write_text("".join(json.dumps(g) + "\n" for g in GOLD), "utf-8")
    (keys / "gold_b2.jsonl").write_text("", "utf-8")
    (keys / "gold_b3.jsonl").write_text("", "utf-8")
    out = tmp / "score"
    args = ["--results", str(run / "results.zip"), "--keys", str(keys)]
    assert score_hickman.main([*args, "--dump", str(tmp / "dump"), "--out", str(out)]) == 0
    return run, json.loads((out / "score.json").read_text("utf-8"))


def test_keys_map_by_content_and_every_unmapped_key_is_listed(scored):
    _, s = scored
    m = s["key_mapping"]
    assert m["keys"] == 5
    why = {u["key"].removeprefix("ufdr:source_index:"): u["why"] for u in m["unmapped"]}
    assert why == {
        CHAT_ID: "a chat, not a record Mabillon cites",
        "13": "2 records match",
        "999": "not in the dump",
    }
    # C01's one mappable key and C02's key became Mabillon message ids; the claim ids line up.
    per = s["r1"]["per_claim"]
    assert set(per) == {"C01", "C02", "C03"}


def test_calls_and_contacts_map_to_one_record(scored, tmp_path):
    run, _ = scored
    conn = sqlite3.connect(run / "case.db")
    call = {"kind": "call", "time_utc": "2023-04-28T17:00:00.000+00:00", "duration": "00:01:30"}
    ids, why = score_hickman.match_record(conn, call)
    assert len(ids) == 1 and ids[0].startswith("call:") and why == ""
    contact = {"kind": "contact", "name": "Marc Garage", "entries": [{"value": "+12125550122"}]}
    ids, why = score_hickman.match_record(conn, contact)
    assert len(ids) == 1 and ids[0].startswith("contact:") and why == ""
    written = {"kind": "contact", "name": "Marc Garage", "entries": [{"value": "(212) 555-0122"}]}
    assert score_hickman.match_record(conn, written)[0] == ids
    stranger = {"kind": "contact", "name": "Marc Garage", "entries": [{"value": "+19995550000"}]}
    assert score_hickman.match_record(conn, stranger) == ([], "no contact matches")
    conn.close()


def test_r1_measures_count_against_the_right_denominators(scored):
    _, s = scored
    r1 = s["r1"]
    assert r1["contradicted_without_expert"]["n"] == 2  # gold not contradicted: C01, C03
    assert r1["false_claim_shown_only_as_support"]["n"] == 1  # gold contradicted: C02
    assert r1["contradiction_surfaced"]["n"] == 1
    assert r1["no_r1_verdict"] == []
    # Stand-in components contradict nothing, so nothing is contradicted without an expert.
    assert r1["contradicted_without_expert"]["k"] == 0


def test_r2_runs_the_simulated_expert_then_the_rules_on_a_copy(scored):
    run, s = scored
    card = s["r2"]["card"]
    assert card["claims"] == 3 and card["not_predicted"] == []
    # The expert accepted C01's key message in the gold direction, so the rules now support it;
    # C02's item was not key evidence the way gold points, and C03 is gold unproven.
    assert s["r2"]["simulated_expert"]["claims_with_an_acceptance"] == ["C01"]
    assert card["false_supported"]["k"] == 0 and card["missed_supported"]["k"] == 0
    assert s["r2"]["run_id"] != s["audit_run"]
    assert s["run_record"]["audit"]["run_id"] == s["audit_run"]  # the run's run.json, kept
    # The run's own case.db is untouched: no expert decision was written to it.
    conn = sqlite3.connect(run / "case.db")
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind = 'expert'"
        ).fetchone()[0]
        == 0
    )
    conn.close()
    imported = s["import_counts"]
    assert imported["messages"] == {"mabillon": 4, "dump": 4}
    assert imported["calls"] == {"mabillon": 1, "dump": 1}
    assert imported["contacts"] == {"mabillon": 1, "dump": 1}
