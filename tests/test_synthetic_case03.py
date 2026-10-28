"""Synthetic case03, the challenge-step case: the generator is deterministic, the committed
drafts match a fresh build, the real importer reads both reports, and every record the draft
key cites exists in the imported case. Synthetic data only.

These tests never run the retrieval or explain.py: case03 exists to measure them, so it must
not gate them. eval/synthetic/case03_reach.py reports where each plant sits.
"""

import json
import re
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
from eval.synthetic import case03_key as key
from eval.synthetic import case03_story as story
from eval.synthetic.case03_generate import (
    DEFAULT_OUT,
    SEED,
    affidavit_paragraphs,
    generate,
    write_affidavit_pdf,
)
from tests.checks.helpers import stipulate

COMMITTED = Path(__file__).resolve().parents[1] / DEFAULT_OUT
COMMITTED_FILES = (
    "case.json",  # pins the SHA-256 of item1.xlsx and item2.xlsx
    "affidavit_draft.md",
    "draft_gold.jsonl",
    "draft_assumptions.jsonl",
    "ANSWER_KEY_DRAFT.md",
    "SIGNING_SHEET.md",
)
IMPORTED_AT = datetime(2026, 10, 27, tzinfo=UTC)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("case03")
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
    """Both reports through the real importer, with the case's device-owner stipulations."""
    conn = connect(built / "case03.db")
    apply_schema(conn)
    for s in meta["sources"]:
        importer = CellebriteExcelImporter(source_id=s["source_id"], now=IMPORTED_AT)
        src = importer.import_source(built / s["file"], conn)
        assert src.sha256 == s["sha256"], s["file"]
    stipulate(conn, key.ORLOV, "Pavel Orlov", key.ITEM1)
    stipulate(conn, key.DIAZ, "Ruben Diaz", key.ITEM2)
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
    out = []
    for rid in ids:
        row = conn.execute(
            "SELECT body FROM messages WHERE id = ?"
            " UNION ALL SELECT name FROM contacts WHERE id = ?",
            (rid, rid),
        ).fetchone()
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
    assert {"item1.xlsx", "item2.xlsx", *COMMITTED_FILES} <= set(names)
    for name in names:
        assert (a / name).read_bytes() == (b / name).read_bytes(), name


@pytest.mark.parametrize("name", COMMITTED_FILES)
def test_committed_outputs_match_a_fresh_generation(built, name):
    assert (built / name).read_bytes() == (COMMITTED / name).read_bytes(), (
        f"{name} is stale: run `python -m eval.synthetic.case03_generate` and commit the result"
    )


# ---------------------------------------------------------------- the draft key


def test_every_cited_record_exists_in_the_imported_case(imported, gold, meta):
    for g in gold:
        assert g.key_evidence, g.claim_id
        for rid in g.key_evidence:
            assert _record_exists(imported, rid), f"{g.claim_id}: {rid} missing"
    for cid, plant in meta["plants"].items():
        for rid in plant["counter_records"] + plant["decoy_records"]:
            assert _record_exists(imported, rid), f"{cid}: {rid} missing"


def test_the_key_and_the_sheet_are_drafts(gold, sheet):
    assert key.DRAFT_LABEL.startswith("DRAFT")
    assert all(g.labeled_by == key.DRAFT_LABEL for g in gold)
    assert all(row["labeled_by"] == key.DRAFT_LABEL for row in sheet)


def test_the_four_groups_and_the_draft_split(gold):
    sizes = {n: sum(c.group == n for c in key.CLAIMS) for n in key.GROUPS}
    assert sizes == {1: 6, 2: 3, 3: 5, 4: 3}
    verdicts = [g.gold_verdict.value for g in gold]
    assert (verdicts.count("supported"), verdicts.count("contradicted")) == (6, 2)
    assert list(key.SUMMARY) == [c.claim_id for c in key.CLAIMS]
    for c in key.CLAIMS:
        assert set(c.counter) <= set(c.evidence), c.claim_id
        assert not set(c.decoys) & set(c.evidence), c.claim_id
        if c.group in (1, 2):
            assert c.counter and c.reach and c.verdict != "supported", c.claim_id
        if c.group == 1:
            assert c.direction, c.claim_id
        if c.group == 3:
            assert c.verdict == "supported" and c.decoys and not c.counter, c.claim_id


def test_claims_are_verbatim_in_their_affidavit_paragraph(built, gold):
    paras = {(p, n): text for p, n, text in affidavit_paragraphs()}
    md = (built / "affidavit_draft.md").read_text(encoding="utf-8")
    for g in gold:
        assert g.text in paras[(g.page, g.para_no)], g.claim_id
        assert f"{g.para_no}. {paras[(g.page, g.para_no)]}" in md


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
            assert any(quote in c for c in cited), f"{g.claim_id}: {quote!r} not cited"
    for row in sheet:
        quote = row["params"].get("quoted_text")
        if quote:
            cited = _cited_texts(imported, by_claim[row["claim_id"]].key_evidence)
            assert any(quote in c for c in cited), f"{row['claim_id']}: {quote!r} not cited"


# ---------------------------------------------------------------- the draft assumption sheet


def test_every_claim_has_a_core_assumption(gold, sheet):
    assert [s.claim_id for s in key.SHEET] == [g.claim_id for g in gold]
    for g in gold:
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
        assert row["template_version"] == TEMPLATES_VERSION
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
    assert checked >= 30


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


def test_item1_whatsapp_is_quiet_everywhere_while_other_apps_go_on(imported):
    start, end = (
        t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in (story.WA_QUIET_START, story.WA_QUIET_END)
    )

    def count(source: str, app: str) -> int:
        return imported.execute(
            "SELECT count(*) FROM messages m JOIN threads t ON t.id = m.thread_id"
            " WHERE m.source_id = ? AND t.app = ? AND m.ts_utc >= ? AND m.ts_utc < ?",
            (source, app, start, end),
        ).fetchone()[0]

    assert count("item1", "WhatsApp") == 0
    assert count("item1", "SMS") > 0 and count("item1", "Telegram") > 0
    assert count("item2", "WhatsApp") > 0
