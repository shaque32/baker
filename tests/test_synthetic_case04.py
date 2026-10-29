"""Synthetic case04, the testability step's held-out set: the generator is deterministic and the
committed drafts match a fresh build, the real importer reads all three reports, the key and the
sheet are well formed and keep the case's design (six claims per type, three plain and three
affidavit wordings per type, a wrong reading planted for most claims), every check finds what the
sheet expects, and a model-free run on the draft sheet gives the drafted verdicts.
Synthetic data only.

case04 is not part of `make eval`, any gate or any go/no-go list; these tests hold the case
itself, not a measurement made on it.
"""

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit.assumptions import (
    TEMPLATES,
    TEMPLATES_VERSION,
    instantiate,
    parse_params,
    templates_for,
)
from core.audit.checks import CHECKS
from core.audit.rules import _REQUIRED_KIND
from core.contracts import ClaimType, GoldClaim
from core.db import apply_schema, connect
from core.ingest.cellebrite_excel import CellebriteExcelImporter
from core.ingest.govdoc import PdfGovDocIngester
from eval.run_eval import load_jsonl
from eval.synthetic import case04_key as key
from eval.synthetic import case04_story as story
from eval.synthetic.case04_generate import (
    DEFAULT_OUT,
    SEED,
    affidavit_paragraphs,
    generate,
    write_affidavit_pdf,
)
from tests.checks.helpers import stipulate

ROOT = Path(__file__).resolve().parents[1]
COMMITTED = ROOT / DEFAULT_OUT
COMMITTED_FILES = (
    "case.json",  # pins the SHA-256 of item1.xlsx, item2.xlsx and item3.xlsx
    "affidavit_draft.md",
    "draft_gold.jsonl",
    "draft_assumptions.jsonl",
    "ANSWER_KEY_DRAFT.md",
    "SIGNING_SHEET.md",
)
IMPORTED_AT = datetime(2026, 10, 29, tzinfo=UTC)
# The one claim whose quote is in no record by design: the words in the data are similar, not
# the same (its hazard), so the claim stays unproven.
ABSENT_QUOTE = "C06"
# Names and numbers from case01 and case03 that case04 must not reuse.
EARLIER_CASES = ("case01_story.py", "case03_story.py")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("case04")
    generate(out)
    return out


@pytest.fixture(scope="module")
def gold(built) -> list[GoldClaim]:
    return load_jsonl(built / "draft_gold.jsonl", GoldClaim)


@pytest.fixture(scope="module")
def sheet(built) -> list[dict]:
    text = (built / "draft_assumptions.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


@pytest.fixture(scope="module")
def meta(built) -> dict:
    return json.loads((built / "case.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def imported(built, meta):
    """All three reports through the real importer, with the case's device-owner stipulations
    under the sheet's person ids."""
    conn = connect(built / "case04.db")
    apply_schema(conn)
    for s in meta["sources"]:
        importer = CellebriteExcelImporter(source_id=s["source_id"], now=IMPORTED_AT)
        src = importer.import_source(built / s["file"], conn)
        assert src.sha256 == s["sha256"], s["file"]
    stipulate(conn, key.HAL, "Owen Halloran", key.ITEM1)
    stipulate(conn, key.FER, "Nadia Ferro", key.ITEM2)
    stipulate(conn, key.OKA, "Desmond Okafor", key.ITEM3)
    conn.commit()
    yield conn
    conn.close()


def _record_exists(conn, rid: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM messages WHERE id = ? UNION ALL SELECT 1 FROM calls WHERE id = ? "
            "UNION ALL SELECT 1 FROM contacts WHERE id = ?",
            (rid, rid, rid),
        ).fetchone()
        is not None
    )


def _cited_texts(conn, ids) -> list[str]:
    """What a quote may come from: a message body, a saved contact's name or number, and the
    names the report shows for a cited message's sender and thread."""
    out: list[str] = []
    for rid in ids:
        for sql in (
            "SELECT body FROM messages WHERE id = ?",
            "SELECT name FROM contacts WHERE id = ?",
            "SELECT identifier FROM contacts WHERE id = ?",
            "SELECT a.display_name FROM messages m JOIN accounts a"
            " ON a.id = m.sender_account_id WHERE m.id = ?",
            "SELECT a.identifier FROM messages m JOIN accounts a"
            " ON a.id = m.sender_account_id WHERE m.id = ?",
            "SELECT t.title FROM messages m JOIN threads t ON t.id = m.thread_id WHERE m.id = ?",
        ):
            row = conn.execute(sql, (rid,)).fetchone()
            if row and row[0]:
                out.append(row[0])
    return out


# ---------------------------------------------------------------- determinism


def test_the_generator_gives_the_same_bytes_twice(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    generate(a)
    generate(b)
    names = sorted(p.name for p in a.iterdir())
    assert names == sorted(p.name for p in b.iterdir())
    assert {"item1.xlsx", "item2.xlsx", "item3.xlsx", *COMMITTED_FILES} <= set(names)
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


@pytest.mark.parametrize("name", COMMITTED_FILES)
def test_committed_outputs_match_a_fresh_generation(built, name):
    assert (built / name).read_bytes() == (COMMITTED / name).read_bytes(), (
        f"{name} is stale: run `python -m eval.synthetic.case04_generate` and commit the result"
    )


def test_case_json_pins_the_reports_and_is_not_hidden(built, meta):
    assert meta["case_id"] == "case04" and meta["synthetic"] is True
    assert "hidden" not in meta
    assert [d["report_time"] for d in meta["devices"]] == ["utc", "local", "fixed-360"]
    assert len({d["owner"].split()[-1] for d in meta["devices"]}) == 3  # sheet_people needs it
    from eval.synthetic.generate import sha256_file

    for s in meta["sources"]:
        assert sha256_file(built / s["file"]) == s["sha256"], s["file"]


def test_the_world_is_new(built):
    """No person, number or handle from case01 or case03 appears in case04."""
    earlier = "\n".join(
        (ROOT / "eval/synthetic" / name).read_text(encoding="utf-8") for name in EARLIER_CASES
    )
    for acct in story.ACCOUNTS.values():
        ident = acct.identifier.split("@")[0]
        assert ident not in earlier, acct.key
        assert ident[-7:] not in earlier, acct.key
    for name in story.PEOPLE.values():
        surname = name.split(" (")[0].split()[-1]
        if surname[0].isupper() and surname not in ("CW-1", "Metals", "Instagram"):
            assert surname not in earlier, surname


# ---------------------------------------------------------------- the draft key


def test_every_cited_record_exists_in_the_imported_case(imported, gold, meta):
    for g in gold:
        assert g.key_evidence, g.claim_id
        for rid in g.key_evidence:
            assert _record_exists(imported, rid), f"{g.claim_id}: {rid} missing"
    for cid, plant in meta["plants"].items():
        for rid in plant["wrong_records"]:
            assert _record_exists(imported, rid), f"{cid}: {rid} missing"


def test_the_key_and_the_sheet_are_drafts(gold, sheet):
    assert key.DRAFT_LABEL == "DRAFT (case04 builder, not signed by Arsh)"
    assert all(g.labeled_by == key.DRAFT_LABEL for g in gold)
    assert all(row["labeled_by"] == key.DRAFT_LABEL for row in sheet)


def test_every_claim_records_type_verdict_wording_and_hazard(gold, meta):
    assert [c.claim_id for c in key.CLAIMS] == [f"C{i:02d}" for i in range(1, 49)]
    assert list(key.SUMMARY) == [c.claim_id for c in key.CLAIMS]
    by_id = {g.claim_id: g for g in gold}
    for c in key.CLAIMS:
        assert c.claim_type in key.CLAIM_TYPES, c.claim_id
        assert c.wording in ("plain", "affidavit"), c.claim_id
        assert c.verdict in ("supported", "contradicted", "unproven"), c.claim_id
        assert c.hazard in key.HAZARDS, c.claim_id
        assert by_id[c.claim_id].gold_verdict.value == c.verdict
        assert by_id[c.claim_id].claim_type.value == c.claim_type
        assert by_id[c.claim_id].trap == c.hazard
        plant = meta["plants"][c.claim_id]
        assert (plant["claim_type"], plant["wording"], plant["verdict"], plant["hazard"]) == (
            c.claim_type,
            c.wording,
            c.verdict,
            c.hazard,
        )
        if c.hazard != "none":
            assert c.wrong and c.hazard_detail, f"{c.claim_id}: a hazard needs its wrong records"
        if c.wording == "affidavit":
            assert c.style, f"{c.claim_id}: say which affidavit devices the wording uses"


def test_the_design_counts(gold):
    types = Counter(c.claim_type for c in key.CLAIMS)
    assert types == {t: 6 for t in key.CLAIM_TYPES}
    for t in key.CLAIM_TYPES:
        wordings = Counter(c.wording for c in key.CLAIMS if c.claim_type == t)
        assert wordings == {"plain": 3, "affidavit": 3}, t
    verdicts = Counter(g.gold_verdict.value for g in gold)
    assert verdicts == {"supported": 24, "contradicted": 12, "unproven": 12}
    assert sum(c.hazard != "none" for c in key.CLAIMS) >= 24
    # no absence claim can be supported on a curated report
    assert not [c for c in key.CLAIMS if c.claim_type == "absence" and c.verdict == "supported"]


def test_claims_are_verbatim_in_their_affidavit_paragraph(built, gold):
    paras = {(p, n): text for p, n, text in affidavit_paragraphs()}
    md = (built / "affidavit_draft.md").read_text(encoding="utf-8")
    for g in gold:
        assert g.text in paras[(g.page, g.para_no)], g.claim_id
        assert f"{g.para_no}. {paras[(g.page, g.para_no)]}" in md
    words = md.casefold()
    for banned in ("guilty", "innocent", "leader", "deleted"):
        assert banned not in words, banned


def test_the_affidavit_pdf_reads_back_every_paragraph_as_written(tmp_path):
    pdf = write_affidavit_pdf(tmp_path / "affidavit.pdf")
    read = {" ".join(p.text.split()) for p in PdfGovDocIngester().parse(pdf).paragraphs}
    for _, no, text in affidavit_paragraphs():
        assert f"{no}. {' '.join(text.split())}" in read, no


def test_quoted_text_matches_cited_records_verbatim(imported, gold, sheet):
    by_claim = {g.claim_id: g for g in gold}
    for g in gold:
        cited = _cited_texts(imported, g.key_evidence)
        for quote in re.findall(r'"([^"]+)"', g.text):
            if g.claim_id == ABSENT_QUOTE:
                continue
            assert any(quote in c for c in cited), f"{g.claim_id}: {quote!r} not cited"
    for row in sheet:
        quote = row["params"].get("quoted_text")
        if quote and row["claim_id"] != ABSENT_QUOTE:
            cited = _cited_texts(imported, by_claim[row["claim_id"]].key_evidence)
            assert any(quote in c for c in cited), f"{row['claim_id']}: {quote!r} not cited"


def test_the_absent_quote_is_in_no_record(imported, gold):
    (g,) = [g for g in gold if g.claim_id == ABSENT_QUOTE]
    assert g.gold_verdict.value == "unproven"
    for quote in re.findall(r'"([^"]+)"', g.text):
        hit = imported.execute(
            "SELECT count(*) FROM messages WHERE instr(body, ?) > 0", (quote,)
        ).fetchone()[0]
        assert hit == 0, quote


# ---------------------------------------------------------------- the draft assumption sheet


def test_every_claim_has_a_sheet_with_a_core_row(gold, sheet):
    assert len(key.NO_SHEET) <= 4
    assert [s.claim_id for s in key.SHEET] == [
        g.claim_id for g in gold if g.claim_id not in key.NO_SHEET
    ]
    for g in gold:
        if g.claim_id in key.NO_SHEET:
            continue
        assert any(r["is_core"] for r in sheet if r["claim_id"] == g.claim_id), g.claim_id


def test_supported_claims_carry_the_kind_their_type_needs(gold, sheet):
    for g in gold:
        need = _REQUIRED_KIND.get(ClaimType(g.claim_type))
        if g.gold_verdict.value != "supported" or need is None:
            continue
        kinds = {
            TEMPLATES[r["template_id"]].kind
            for r in sheet
            if r["claim_id"] == g.claim_id and r["is_core"]
        }
        assert need in kinds, f"{g.claim_id} needs a core {need} assumption"


def test_every_row_fits_its_template(gold, sheet):
    types = {g.claim_id: ClaimType(g.claim_type) for g in gold}
    for row in sheet:
        assert row["template_version"] == TEMPLATES_VERSION == key.TEMPLATES_VERSION
        parse_params(row["template_id"], row["params"])
        allowed = {t.id for t in templates_for(types[row["claim_id"]])}
        assert row["template_id"] in allowed, row["claim_id"]


def test_every_check_finds_what_the_sheet_expects(imported, sheet):
    accounts = {r[0] for r in imported.execute("SELECT id FROM accounts")}
    checked = 0
    for row in sheet:
        assert set(row["params"].get("account_ids", [])) <= accounts, row["claim_id"]
        if not row["expected_check"]:
            assert not TEMPLATES[row["template_id"]].checks, row["claim_id"]
            continue
        a = instantiate(row["claim_id"], row["template_id"], row["params"], row["is_core"])
        (name,) = TEMPLATES[row["template_id"]].checks
        result = CHECKS[name].run(a, imported)
        assert result.outcome.value == row["expected_check"], (row["claim_id"], result.detail)
        checked += 1
    assert checked >= 60


def test_contradicted_claims_rest_on_a_failed_core_check(gold, sheet):
    """Every contradicted claim is settled by an observed record a check can test, never by a
    model's label alone; no other claim has a failing core row."""
    failing = {r["claim_id"] for r in sheet if r["is_core"] and r["expected_check"] == "fail"}
    contradicted = {g.claim_id for g in gold if g.gold_verdict.value == "contradicted"}
    assert failing == contradicted


# ---------------------------------------------------------------- the plants hold


def _reserved(text: str) -> list[str]:
    folded = text.casefold()
    return [w for w in story.RESERVED_WORDS if re.search(rf"(?<!\w){re.escape(w)}", folded)]


def test_background_chatter_never_uses_a_reserved_word():
    for pool in (*story.POOLS.values(), story.IG_CUSTOMER, story.IG_SHOP):
        for phrase in pool:
            assert not _reserved(phrase), phrase
    msgs, _ = story.make_filler(SEED)
    assert len(msgs) > 1000
    assert not [m.body for m in msgs if _reserved(m.body)]


def test_background_chatter_never_joins_two_subjects():
    subjects = {"halloran", "ferro", "okafor", "cw1", "kip"}
    msgs, calls = story.make_filler(SEED)
    acc = story.ACCOUNTS
    for m in msgs:
        assert not (acc[m.sender].person in subjects and acc[m.to].person in subjects), m.key
    for c in calls:
        assert not (acc[c.caller].person in subjects and acc[c.callee].person in subjects), c.key


def test_records_left_off_a_phone_are_on_the_other(imported):
    """The second_phone plants: a record one report does not hold is on the other phone."""
    for m in story.SCRIPTED_MESSAGES:
        for dev in m.skip:
            n = imported.execute(
                "SELECT count(*) FROM messages WHERE source_id = ? AND body = ? AND ts_utc = ?",
                (dev, m.body, m.at.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ).fetchone()[0]
            assert n == 0, (m.key, dev)
            others = imported.execute(
                "SELECT count(*) FROM messages WHERE source_id != ? AND body = ? AND ts_utc = ?",
                (dev, m.body, m.at.strftime("%Y-%m-%dT%H:%M:%SZ")),
            ).fetchone()[0]
            assert others >= 1, m.key


# ---------------------------------------------------------------- the model-free run


def test_a_model_free_run_on_the_draft_sheet_gives_the_drafted_verdicts(tmp_path, monkeypatch):
    from eval import run_pipeline

    monkeypatch.chdir(ROOT)
    spec = COMMITTED / "draft_assumptions.jsonl"
    preds = run_pipeline.run_once("case04", "model-free", "accept", tmp_path, spec, "simulated")
    got = {p.claim_id: p.verdict.value for p in preds}
    want = {c.claim_id: c.verdict for c in key.CLAIMS}
    assert got == want


def test_case04_is_the_held_out_go_no_go_case():
    """The testability go/no-go counts case04 only, and the step runs only on its signed sheet:
    on the draft it refuses."""
    from eval import run_pipeline

    assert run_pipeline.TESTABILITY_GO_NO_GO_CASES == frozenset({"case04"})
    sheet = run_pipeline.assumption_sheet("case04")
    assert sheet is not None
    if run_pipeline.sheet_status(sheet) != "signed":
        with pytest.raises(SystemExit, match="needs a signed assumption sheet"):
            run_pipeline.testability_step(None, "case04", None, 1, None, "rubber-stamp")
