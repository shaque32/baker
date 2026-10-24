"""The validation-v1 run driver (eval/validation/hickman_run.py), on synthetic case01 as a UFDR
with stand-in components. The real run is on the public Hickman phone with the local model."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from eval.synthetic.generate import generate
from eval.synthetic.ufdr import write_case01
from eval.validation import hickman_run

CLAIMS = [
    {"claim_id": "C01", "page": 1, "para_no": 1, "claim_type": "communication",
     "text": "On April 28, 2023, the TARGET PHONE exchanged Signal messages with (919) 888-7386."},
    {"claim_id": "C02", "page": 1, "para_no": 2, "claim_type": "content",
     "text": 'SUBJECT-1 wrote "I\'m here!" on April 28, 2023.'},
    {"claim_id": "D01", "page": 2, "para_no": 3, "claim_type": "timing",
     "text": "On Tuesday, April 24, 2023, the TARGET PHONE's Discord account exchanged messages."},
]  # fmt: skip


@pytest.fixture(scope="module")
def ufdr(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("case01")
    generate(out)
    return write_case01(out)[0]


def _claims(tmp_path: Path, rows: list[dict] = CLAIMS) -> Path:
    path = tmp_path / "claims.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def test_the_run_builds_the_case_audits_it_and_zips_the_results(ufdr, tmp_path):
    claims, out = _claims(tmp_path), tmp_path / "out"
    sha = hickman_run.sha256_file(claims)
    report = hickman_run.report_xml_sha256(ufdr)
    args = ["--ufdr", str(ufdr), "--claims", str(claims), "--out", str(out), "--fake"]
    assert hickman_run.main([*args, "--claims-sha256", sha, "--report-sha256", report]) == 0

    conn = sqlite3.connect(out / "case.db")
    rows = conn.execute(
        "SELECT c.id, c.claim_type, c.text, p.label FROM claims c"
        " JOIN govdoc_paragraphs p ON p.id = c.paragraph_id ORDER BY c.id"
    ).fetchall()
    # Each claim sits on its own printed paragraph, verbatim; "content" reads as content_meaning.
    assert rows == [
        ("C01", "communication", CLAIMS[0]["text"], "1"),
        ("C02", "content_meaning", CLAIMS[1]["text"], "2"),
        ("D01", "timing", CLAIMS[2]["text"], "3"),
    ]
    owner = conn.execute(
        "SELECT s.subject_id, p.name FROM stipulations s JOIN persons p ON p.id = s.person_id"
    ).fetchall()
    assert owner == [("dev:ios15", "SUBJECT-1")]
    assert conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 3
    sources = conn.execute("SELECT id FROM sources ORDER BY id").fetchall()
    conn.close()

    run = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert run["claims"] == {"file": "claims.jsonl", "sha256": sha, "n": 3}
    assert run["report_xml_sha256"] == report
    assert run["audit"]["fake"] is True and sum(run["audit"]["verdicts"].values()) == 3
    with zipfile.ZipFile(out / "results.zip") as z:
        assert sorted(z.namelist()) == ["case.db", "progress.log", "report.html", "run.json"]

    # A second run resumes: the case is not rebuilt, and the audit runs again on it.
    assert hickman_run.main(args) == 0
    conn = sqlite3.connect(out / "case.db")
    assert conn.execute("SELECT id FROM sources ORDER BY id").fetchall() == sources
    assert conn.execute("SELECT COUNT(DISTINCT pipeline_run_id) FROM verdicts").fetchone()[0] == 2
    conn.close()


def test_a_claims_file_with_answers_is_refused(ufdr, tmp_path):
    rows = [{**CLAIMS[0], "label": "supported"}]
    with pytest.raises(SystemExit, match="claims only"):
        hickman_run.main(
            ["--ufdr", str(ufdr), "--claims", str(_claims(tmp_path, rows)), "--out",
             str(tmp_path / "out"), "--fake"]
        )  # fmt: skip


def test_the_wrong_claims_file_or_phone_is_refused_before_anything_is_built(ufdr, tmp_path):
    claims, out = _claims(tmp_path), tmp_path / "out"
    base = ["--ufdr", str(ufdr), "--claims", str(claims), "--out", str(out), "--fake"]
    with pytest.raises(SystemExit, match="expected"):
        hickman_run.main([*base, "--claims-sha256", "0" * 64])
    with pytest.raises(SystemExit, match="report.xml SHA-256"):
        hickman_run.main([*base, "--report-sha256", "0" * 64])
    assert not (out / "case.db").exists()


def test_paragraphs_must_run_in_order(tmp_path):
    rows = [CLAIMS[0], {**CLAIMS[1], "para_no": 5}]
    with pytest.raises(SystemExit, match="1..n"):
        hickman_run.load_claims(_claims(tmp_path, rows))


def test_a_resume_with_other_inputs_is_refused(ufdr, tmp_path):
    claims, out = _claims(tmp_path), tmp_path / "out"
    assert (
        hickman_run.main(
            ["--ufdr", str(ufdr), "--claims", str(claims), "--out", str(out), "--fake"]
        )
        == 0
    )
    run = (out / "run.json").read_text(encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    other_claims = _claims(other, CLAIMS[:2])
    with pytest.raises(SystemExit, match="was built from claims"):
        hickman_run.main(
            ["--ufdr", str(ufdr), "--claims", str(other_claims), "--out", str(out), "--fake"]
        )
    with pytest.raises(SystemExit, match="was built from report.xml"):
        hickman_run.main(
            ["--ufdr", str(ufdr), "--claims", str(claims), "--out", str(out), "--fake",
             "--report-sha256", "0" * 64]
        )  # fmt: skip
    assert (out / "run.json").read_text(
        encoding="utf-8"
    ) == run  # the record still names the case's inputs
