"""`baker claims propose`: proposals stored with their model run, never accepted by the tool."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from cli.main import main as cli_main
from core.audit._local_model import MODEL_CONFIG_ENV
from core.claims import extract
from core.claims.propose import PROPOSE_ACTION, load_paragraphs, propose_claims
from core.contracts import ClaimStatus, ClaimType
from core.db import apply_schema, connect
from core.llm.runtime import FakeModel
from core.review import actions, audit_log

NOW = datetime(2026, 10, 8, tzinfo=UTC)
P1 = 'On March 12, 2026, PETROV wrote to @northstar: "need 2 more by friday".'
P2 = "I believe there is probable cause."


def _db(tmp_path):
    conn = connect(tmp_path / "case.db")
    apply_schema(conn)
    conn.execute("PRAGMA foreign_keys = OFF")  # paragraphs without a full govdoc row
    for i, text in enumerate((P1, P2), start=1):
        conn.execute(
            "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
            " char_end, text, ocr) VALUES (?, 'gd1', 1, ?, ?, 0, ?, ?, 0)",
            (f"para:gd1:{i}", i, str(i), len(text), text),
        )
    conn.commit()
    return conn


def respond(prompt: str) -> str:
    if "need 2 more" in prompt:
        return json.dumps(
            {
                "claims": [
                    {
                        "text": 'On March 12, 2026, PETROV wrote "need 2 more by friday".',
                        "claim_type": "communication",
                        "span": "PETROV wrote to @northstar",
                    },
                    {  # a number the paragraph never says: dropped
                        "text": "PETROV wrote 3 messages.",
                        "claim_type": "count",
                        "span": "PETROV wrote",
                    },
                ]
            }
        )
    return json.dumps({"claims": []})


def test_proposals_are_stored_as_proposed_with_their_run(tmp_path):
    conn = _db(tmp_path)
    model = FakeModel(name="fake-14b", respond=respond)
    ex = extract.create(conn, model=model)
    r = propose_claims(conn, ex, load_paragraphs(conn), clock=lambda: NOW)

    assert [c.text for c in r.claims] == [
        'On March 12, 2026, PETROV wrote "need 2 more by friday".'
    ]
    assert len(r.drops) == 1 and "numbers not in paragraph" in r.drops[0].reason
    row = conn.execute("SELECT status, model_run_id FROM claims").fetchone()
    assert row == (ClaimStatus.PROPOSED.value, r.model_run_id)
    run = conn.execute("SELECT purpose, model_name FROM model_runs").fetchone()
    assert run == ("claims", "fake-14b")
    assert conn.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0] == 2  # both paragraphs
    (payload,) = conn.execute(
        "SELECT payload_json FROM audit_log WHERE action = ?", (PROPOSE_ACTION,)
    ).fetchone()
    assert json.loads(payload)["claims"] == [c.id for c in r.claims]
    assert audit_log.verify_chain(conn)


def test_paragraphs_with_claims_are_skipped(tmp_path):
    conn = _db(tmp_path)
    actions.add_claim(
        conn,
        "C01",
        "para:gd1:1",
        "PETROV wrote to @northstar.",
        ClaimType.COMMUNICATION,
        "expert:test",
    )
    model = FakeModel(respond=respond)
    r = propose_claims(conn, extract.create(conn, model=model), load_paragraphs(conn))
    assert r.skipped == ["para:gd1:1"] and r.claims == []
    assert len(model.calls) == 1  # only the paragraph without claims

    # Proposing again changes nothing: every paragraph with a proposal is skipped too.
    again = propose_claims(conn, extract.create(conn, model=model), load_paragraphs(conn))
    assert again.claims == [] and len(model.calls) == 1


def test_unknown_paragraph_is_refused(tmp_path):
    conn = _db(tmp_path)
    with pytest.raises(ValueError, match="no such paragraph"):
        load_paragraphs(conn, ["para:gd1:9"])
    assert [p.id for p in load_paragraphs(conn, ["para:gd1:2"])] == ["para:gd1:2"]


def test_cli_propose_without_a_model_config_says_so(tmp_path, monkeypatch, capsys):
    _db(tmp_path).close()
    monkeypatch.setenv(MODEL_CONFIG_ENV, str(tmp_path / "missing.json"))
    assert cli_main(["claims", "--db", str(tmp_path / "case.db"), "propose"]) == 2
    assert "no model config" in capsys.readouterr().err
