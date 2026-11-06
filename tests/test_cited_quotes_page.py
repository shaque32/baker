"""A claim that quotes a word the tool never says still gets its report and claim page.

Validation run 3 on a public test phone: a claim quoting "Done. It's been deleted." came back
inside Mabillon's own sentences (its assumption's text, the check's search line, the verdict
reason) without the cited mark, so the forbidden-word check withheld the whole report. The
claim page runs the same check. All data is synthetic case01, with one claim's quote changed.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from core import pipeline
from core.audit.invariants import check_report_text
from core.db import connect
from core.report.html import render_report
from eval import run_pipeline
from eval.pipeline_fakes import fake_components
from ui.app import App, Request

QUOTE = "ok. it was deleted"


@pytest.fixture
def quoting(tmp_path) -> tuple[sqlite3.Connection, str]:
    path = tmp_path / "case.db"
    run_pipeline.build_case("case01", path).close()  # type: ignore[attr-defined]
    conn = connect(path)
    pipeline.run_audit(conn, fake_components(accept=True))
    conn.commit()
    claim_id, old = next(
        (cid, json.loads(pj)["quoted_text"])
        for cid, pj in conn.execute(
            "SELECT claim_id, params_json FROM assumptions ORDER BY claim_id"
        )
        if json.loads(pj).get("quoted_text")
        and json.loads(pj)["quoted_text"]
        in conn.execute("SELECT text FROM claims WHERE id = ?", (cid,)).fetchone()[0]
    )
    # the claim, and every line that carries its quote, now quote a forbidden word
    conn.execute(
        "UPDATE claims SET text = replace(text, ?, ?) WHERE id = ?", (old, QUOTE, claim_id)
    )
    conn.execute(
        "UPDATE assumptions SET text = replace(text, ?, ?) WHERE claim_id = ?",
        (old, QUOTE, claim_id),
    )
    # the lines Mabillon writes around it: the assumption's own text and a check's search line
    conn.execute(
        "UPDATE assumptions SET text = ? WHERE id = (SELECT min(id) FROM assumptions "
        "WHERE claim_id = ?)",
        (f'A message with the words "{QUOTE}" is in the extraction.', claim_id),
    )
    conn.execute(
        "UPDATE check_results SET searched = ? WHERE assumption_id IN "
        "(SELECT id FROM assumptions WHERE claim_id = ?)",
        (f'Searched every message for the words "{QUOTE}".', claim_id),
    )
    # a reason as the rules write it for a meaning assumption on that quote (rules.py, rule 2)
    reason = f"Rule 2: 'The words \"{QUOTE}\" mean what the claim says they mean' is not covered."
    conn.execute(
        "UPDATE verdicts SET reasons_json = json_insert(reasons_json, '$[#]', ?) "
        "WHERE claim_id = ?",
        (reason, claim_id),
    )
    conn.commit()
    yield conn, claim_id
    conn.close()


def test_the_report_and_claim_page_cite_a_claims_quoted_forbidden_word(quoting, tmp_path):
    conn, claim_id = quoting
    report = render_report(conn)
    check_report_text(report)
    app = App(tmp_path / "case.db", expert="Test Expert", port=8765)
    response = app.handle(Request("GET", "/claim", {"id": claim_id}, {"host": "127.0.0.1:8765"}))
    assert response.status == 200, response.text[:300]
    assert "page withheld" not in response.text
    page = response.text
    assert page.count(f'<span class="q">{QUOTE}</span>') >= 3  # reason, assumption, search
