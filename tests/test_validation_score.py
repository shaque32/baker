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
    empty = model(
        "Chat", field("Source", "WhatsApp"), field("Id", "2"), id="c-2", source_index="15"
    )
    alone = model(  # a standalone message makes a thread of its own, not a source chat
        "InstantMessage",
        field("Source", "Telegram"),
        one("From", party(*JO)),
        field("Body", "on my way"),
        ts_field("TimeStamp", T3),
        source_index="51",
        id="im-51",
    )
    sms = model(
        "SMS",
        many("Parties", [party("+15550100003", "Sam", role="From")]),
        field("Body", "sms in"),
        ts_field("TimeStamp", T1),
        source_index="41",
        id="sms-41",
    )
    call = model(
        "Call",
        field("Source", "Phone"),
        field("Type", "Outgoing", "CallType"),
        ts_field("TimeStamp", "2023-04-28T17:00:00.000+00:00"),
        field("Duration", "00:01:30.6000000", "TimeSpan"),
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
            [
                model("PhoneNumber", field("Category", "Mobile"), field("Value", "+12125550122")),
                model("PhoneNumber", field("Category", "Work"), field("Value", "+12125550199")),
            ],
            "ContactEntry",
        ),
        source_index="31",
        id="contact-31",
    )
    xml = report_xml(
        {
            "Contact": [contact],
            "Chat": [chat, empty],
            "InstantMessage": [alone],
            "SMS": [sms],
            "Call": [call],
        }
    )
    return write_package(path, xml)


def _gold(claim_id: str, para: int, text: str, verdict: str, keys: list[str]) -> dict:
    return {
        "claim_id": claim_id, "page": 1, "para_no": para, "text": text,
        "claim_type": "content", "cross_device": False, "gold_verdict": verdict,
        "core_assumptions": [], "key_evidence": [f"ufdr:source_index:{k}" for k in keys],
        "trap": None, "rationale": "synthetic", "labeled_by": "test",
        "labeled_at": "2026-10-24T00:00:00Z",
    }  # fmt: skip


C01_KEYS = ["11", CHAT_ID, "13", "999", "31"]
GOLD = [
    _gold("C01", 1, 'Jo wrote "meet at the dock".', "supported", C01_KEYS),
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
    assert m["keys"] == 6
    why = {u["key"].removeprefix("ufdr:source_index:"): u["why"] for u in m["unmapped"]}
    assert why == {
        CHAT_ID: "a chat, not a record Mabillon cites",
        "13": "2 records match",
        "999": "not in the dump",
    }
    # C01's message and contact and C02's message became Mabillon ids; the claim ids line up.
    assert {c: sorted(g) for c, g in m["groups"].items()} == {
        "C01": ["ufdr:source_index:11", "ufdr:source_index:31"],
        "C02": ["ufdr:source_index:12"],
        "C03": [],
    }
    assert len(m["groups"]["C01"]["ufdr:source_index:31"]) == 2  # one row per identifier
    per = s["r1"]["per_claim"]
    assert set(per) == {"C01", "C02", "C03"}


def test_recall_counts_key_records_not_contact_rows(scored):
    _, s = scored
    ke = s["key_evidence"]
    assert ke["key_evidence"] == 3  # message 11, contact 31 (two rows), message 12
    assert ke["per_claim"]["C01"]["key"] == 2
    assert ke["key_evidence_recall_retrieved"]["n"] == 3


def test_a_near_miss_is_never_a_match(scored):
    run, _ = scored
    conn = sqlite3.connect(run / "case.db")
    same_time = {"kind": "message", "time_utc": T1, "app": "WhatsApp", "chat_id": CHAT_ID}
    assert score_hickman.match_record(conn, {**same_time, "body": "meet at the dock"})[1] == ""
    for near in ({"body": "key text"}, {"body": "meet at the dock", "app": "Signal"}):
        assert score_hickman.match_record(conn, {**same_time, **near}) == ([], "no record matches")
    call = {"kind": "call", "time_utc": "2023-04-28T17:00:00.000+00:00", "app": "Phone"}
    assert score_hickman.match_record(conn, {**call, "duration": "00:00:30"}) == (
        [],
        "no record matches",
    )
    jo, sam = {"id": JO[0], "name": "Jo"}, {"id": "+15550100003", "name": "Sam"}
    call = {**call, "duration": "00:01:30"}
    assert score_hickman.match_record(conn, {**call, "parties": [jo]})[1] == ""
    # a call whose people sit in From or To rather than Parties: the dump keeps them
    assert score_hickman.match_record(conn, {**call, "parties": [], "to": [jo]})[1] == ""
    # the same time, app and duration with another person is another call
    assert score_hickman.match_record(conn, {**call, "parties": [sam]}) == ([], "no record matches")
    conn.close()


def test_the_dump_keeps_a_calls_explicit_from_and_to(tmp_path):
    call = model(
        "Call",
        field("Source", "Phone"),
        ts_field("TimeStamp", T1),
        one("To", party(*JO)),
        source_index="61",
        id="call-61",
    )
    xml = tmp_path / "report.xml"
    xml.write_text(report_xml({"Call": [call]}), encoding="utf-8")
    dump_ufdr.main([str(xml), str(tmp_path / "dump")])
    row = json.loads((tmp_path / "dump" / "calls.jsonl").read_text("utf-8"))
    assert row["parties"] == [] and [p["id"] for p in row["to"]] == [JO[0]]
    assert (
        "from" not in row
    )  # absent From adds no key, so dumps of Parties-only calls are unchanged


def test_a_standalone_sms_is_in_the_dump_and_matches(scored):
    run, _ = scored
    dump = run.parent / "dump"
    rows = [json.loads(x) for x in (dump / "messages.jsonl").read_text("utf-8").splitlines()]
    sms = next(r for r in rows if r["source_index"] == "41")
    assert sms["model"] == "SMS" and sms["body"] == "sms in"
    conn = sqlite3.connect(run / "case.db")
    ids, why = score_hickman.match_record(conn, sms)
    assert len(ids) == 1 and why == ""
    conn.close()


def test_calls_and_contacts_map_to_their_one_record(scored, tmp_path):
    run, _ = scored
    conn = sqlite3.connect(run / "case.db")
    call = {
        "kind": "call", "time_utc": "2023-04-28T17:00:00.000+00:00", "app": "Phone",
        "duration": "00:01:30.6000000", "parties": [{"id": JO[0], "name": "Jo"}],
    }  # fmt: skip
    ids, why = score_hickman.match_record(conn, call)  # the fraction dropped, as imported
    assert len(ids) == 1 and ids[0].startswith("call:") and why == ""
    contact = {"kind": "contact", "name": "Marc Garage", "entries": [{"value": "+12125550122"}]}
    ids, why = score_hickman.match_record(conn, contact)
    # one contact record, kept as one row per identifier: both rows, from one locator
    assert why == "" and len(ids) == 2 and len({i.split("#")[0] for i in ids}) == 1
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
    assert imported["messages"] == {"mabillon": 6, "dump": 6}
    assert imported["calls"] == {"mabillon": 1, "dump": 1}
    assert imported["contacts"] == {"mabillon": 1, "dump": 1}
    # The empty chat makes no thread, and the standalone messages' threads are not chats.
    assert imported["chats_with_messages"] == {"mabillon": 1, "dump": 1}


def test_coverage_counts_the_tested_claims_beside_the_measures(scored):
    run, s = scored
    c = s["coverage"]
    # Stand-in components give every claim a core assumption, so all three are tested.
    assert (c["claims"], c["tested"], c["untested"]) == (3, 3, 0)
    assert c["tested_claims"] == ["C01", "C02", "C03"] and c["refusal_kinds"] == {}
    assert c["minimum"] == score_hickman.MINIMUM_TESTED == 30
    assert c["result"] == score_hickman.INSUFFICIENT  # 3 tested is under the minimum
    # Over tested claims the bases are the same here, and the all-claims measures stay as they are.
    over = c["r1_over_tested"]["contradicted_without_expert"]
    assert over["n"] == s["r1"]["contradicted_without_expert"]["n"] == 2
    assert s["r2"]["card_over_tested"]["claims"] == 3
    assert s["scorer_version"] == score_hickman.SCORER_VERSION
    md = (run.parent / "score" / "score.md").read_text("utf-8")
    assert "**Tested: 3 of 3 claims.** Minimum 30: insufficient coverage" in md
    # Run 3's tiers split the tested claims, and its measure sits beside measures 1 to 3.
    # Stand-in components put each claim's core assumption to a check: all code-checked.
    assert c["tiers"] == {"code_checked": ["C01", "C02", "C03"], "expert_only": []}
    assert c["result_v3"] == score_hickman.INSUFFICIENT
    assert s["r1"]["contradicted_by_failed_check"]["n"] == 2
    assert "Run 3 (eval/validation/PREREGISTERED_v3.md): code-checked" in md
    assert "4. Contradicted by a failed check, gold not contradicted (run 3)" in md


def _claim(claim_id: str, para: int, verdict: str):  # noqa: ANN202
    from core.contracts import GoldClaim

    return GoldClaim.model_validate(
        {**_gold(claim_id, para, "x", verdict, []), "claim_type": "content_meaning"}
    )


def _per_claim(gold: str, r1: str | None) -> dict:
    return {
        "type": "content", "gold": gold, "r1": r1, "failed_checks": [],
        "verdict_failed_checks": [], "supports": 0, "contradicts": 0, "contradicts_on_key": 0,
    }  # fmt: skip


def test_untested_claims_are_listed_by_reason_and_left_out_of_every_base():
    from core.pipeline import not_tested_reason

    gold = [_claim(f"C{i:02}", i, "contradicted") for i in range(1, 7)]
    gap = "no usable message_count or call_duration assumption; the claim stays unproven"
    quote_gap = "the claim quotes a message but no assumption tests who sent it"
    run = {
        "not_tested": {
            "C01": not_tested_reason(["phone 'TARGET PHONE' matches 0 devices", gap]),
            "C02": not_tested_reason(
                [
                    "the phones do not share one known time zone; name the phone",
                    "'SUBJECT-2' matches no person the expert created",
                    "'@jo' on WhatsApp matches no account in the case",
                    "the claim's count is approximate or strict; it cannot be checked exactly",
                    "not valid JSON: Unterminated string",
                ]
            ),
            "C03": not_tested_reason(["something new the filler said"]),
            "C05": not_tested_reason(
                [
                    "phone 'TARGET PHONE' matches 0 devices",
                    "something new the filler said",
                    f"{quote_gap}; the claim stays unproven",
                ]
            ),
            "C06": not_tested_reason([gap]),
        }
    }
    per_claim = {g.claim_id: _per_claim("contradicted", "unproven") for g in gold}
    c = score_hickman.coverage(run, gold, {"per_claim": per_claim})

    assert (c["claims"], c["tested"], c["untested"]) == (6, 1, 5)
    assert c["tested_claims"] == ["C04"]
    assert list(c["untested_claims"]) == ["C01", "C02", "C03", "C05", "C06"]
    kinds = {k: v["ids"] for k, v in c["refusal_kinds"].items()}
    assert kinds == {
        # The closing summary names templates (call_duration), not a cause: C01 is phone only.
        "phone not matched to a device": ["C01", "C05"],
        "phone time zone not known": ["C02"],
        "person not set up by the expert": ["C02"],
        "account not found": ["C02"],
        "count or duration not readable": ["C02"],
        # Each refusal is read on its own: C05's unknown one is kept beside its phone refusal.
        score_hickman.UNCLASSIFIED: ["C03", "C05"],
        score_hickman.ONLY_SUMMARY: ["C06"],
    }
    # A refusal's own "; " stays inside it.
    assert score_hickman.refusals(run["not_tested"]["C02"])[:1] == [
        "the phones do not share one known time zone; name the phone"
    ]
    # The sentence shows four refusals and "(and 1 more)": the JSON one is not counted.
    assert c["sentences_cut_short"] == ["C02"]
    # Measures count only the tested claim; untested ones are never correct or wrong.
    assert c["r1_over_tested"]["false_claim_shown_only_as_support"]["n"] == 1
    assert c["r1_over_tested"]["contradiction_surfaced"]["n"] == 1
    assert c["result"] == score_hickman.INSUFFICIENT


def test_coverage_is_enough_at_the_minimum():
    n = score_hickman.MINIMUM_TESTED
    gold = [_claim(f"C{i:02}", i + 1, "unproven") for i in range(n)]
    per_claim = {g.claim_id: _per_claim("unproven", "unproven") for g in gold}
    c = score_hickman.coverage({"not_tested": {}}, gold, {"per_claim": per_claim})
    assert c["tested"] == n and c["result"] == "enough tested claims"
    c = score_hickman.coverage(
        {"not_tested": {"C00": "Not tested."}}, gold, {"per_claim": per_claim}
    )
    assert c["tested"] == n - 1 and c["result"] == score_hickman.INSUFFICIENT
    assert c["refusal_kinds"] == {score_hickman.ONLY_SUMMARY: {"claims": 1, "ids": ["C00"]}}


def test_run_3_counts_its_minimum_on_code_checked_claims_only():
    n = score_hickman.MINIMUM_CODE_CHECKED
    gold = [_claim(f"C{i:02}", i + 1, "unproven") for i in range(n + 2)]
    per_claim = {g.claim_id: {**_per_claim("unproven", "unproven"), "code_checked": True}
                 for g in gold}  # fmt: skip
    per_claim["C00"]["code_checked"] = False  # expert only: meaning or event alone
    per_claim["C01"].pop("code_checked")  # a row from before 1.3.0 counts as expert only
    c = score_hickman.coverage({"not_tested": {}}, gold, {"per_claim": per_claim})
    assert c["tested"] == n + 2 and c["result"] == "enough tested claims"
    assert c["tiers"]["expert_only"] == ["C00", "C01"]
    assert len(c["tiers"]["code_checked"]) == n and c["result_v3"] == "enough code-checked claims"
    per_claim["C02"]["code_checked"] = False
    c = score_hickman.coverage({"not_tested": {}}, gold, {"per_claim": per_claim})
    assert c["result_v3"] == score_hickman.INSUFFICIENT  # 31 tested, 29 code-checked


def test_a_wrong_contradicted_from_a_failed_check_is_counted():
    def failed(*ids: str, decided: bool = True) -> dict:
        return {"failed_checks": list(ids), "verdict_failed_checks": list(ids) if decided else []}

    rows = {
        "C01": {**_per_claim("supported", "contradicted"), **failed("chk:a")},
        "C02": {**_per_claim("unproven", "contradicted")},  # no failed check: measure 1 only
        "C03": {**_per_claim("contradicted", "contradicted"), **failed("chk:b")},
        # A stance contradiction decided C04; its failed check is on a non-core assumption.
        "C04": {**_per_claim("supported", "contradicted"), **failed("chk:c", decided=False)},
    }
    m = score_hickman._measures(rows)["contradicted_by_failed_check"]
    assert (m["k"], m["n"], m["claims"]) == (1, 3, ["C01"])


def test_a_claim_with_no_verdict_is_untested_and_never_scored():
    gold = [_claim(f"C{i:02}", i, "unproven") for i in range(1, 4)]
    per_claim = {g.claim_id: _per_claim("unproven", "unproven") for g in gold}
    per_claim["C02"]["r1"] = None  # neither decided nor marked "Not tested"
    c = score_hickman.coverage({"not_tested": {}}, gold, {"per_claim": per_claim})
    assert (c["claims"], c["tested"], c["untested"]) == (3, 2, 1)
    assert c["tested_claims"] == ["C01", "C03"]
    assert c["untested_claims"] == {"C02": "no verdict recorded."}
    assert c["refusal_kinds"] == {score_hickman.NO_VERDICT: {"claims": 1, "ids": ["C02"]}}
    # Measure 1's base (gold not contradicted) holds only the two decided claims.
    assert c["r1_over_tested"]["contradicted_without_expert"]["n"] == 2


def test_coverage_refuses_a_gold_claim_without_a_first_pass_row():
    gold = [_claim(f"C{i:02}", i, "unproven") for i in range(1, 3)]
    per_claim = {"C01": _per_claim("unproven", "unproven")}
    with pytest.raises(SystemExit):
        score_hickman.coverage({"not_tested": {}}, gold, {"per_claim": per_claim})


def test_bare_words_are_not_a_refusal_kind():
    from core.pipeline import not_tested_reason

    loose = not_tested_reason(["the record's window and range and duration looked odd"])
    assert score_hickman.refusal_kinds(loose) == [score_hickman.UNCLASSIFIED]
    exact = not_tested_reason(
        [
            "template 'record_time': the time range is not one the claim plainly states",
            "cannot read the duration 'a while'",
        ]
    )
    assert score_hickman.refusal_kinds(exact) == [
        "time range not plainly stated",
        "count or duration not readable",
    ]
