"""The note on a claim that names or rests on an app holding more than one kind of message.

iOS exports put iMessages and SMS in one app, "Native Messages", and the records do not say
which kind a message is. The report and the claim page say so on every claim whose assumptions
name such an app or whose records come from one (core/report/html.py, mixed_app_note). All
data is synthetic case01.
"""

from __future__ import annotations

import dataclasses
import re
import sqlite3

import pytest

from core import pipeline
from core.audit.assumption_filler import APP_ALIASES, WIDER_APPS
from core.audit.invariants import check_report_text
from core.db import connect
from core.report.html import claim_record_ids, mixed_app_note, render_report
from core.review.status import claim_states
from eval import run_pipeline
from eval.pipeline_fakes import fake_components
from ui.app import App, Request

NOTE_RE = re.compile(r"<p class='warn mixed-app'>.*?</p>", re.S)


@pytest.fixture
def audited(tmp_path) -> sqlite3.Connection:
    path = tmp_path / "case.db"
    run_pipeline.build_case("case01", path).close()  # type: ignore[attr-defined]
    conn = connect(path)
    pipeline.run_audit(conn, fake_components(accept=True))
    conn.commit()
    yield conn
    conn.close()


def _thread_of_a_claims_message(conn: sqlite3.Connection) -> tuple[str, str]:
    """(claim id, thread id) for the first claim whose shown evidence or checks rest on a
    message."""
    for st in claim_states(conn):
        for rid in claim_record_ids(st):
            if rid.startswith("msg:"):
                (thread,) = conn.execute(
                    "SELECT thread_id FROM messages WHERE id = ?", (rid,)
                ).fetchone()
                return st.claim.id, thread
    raise AssertionError("case01 has a claim resting on a message")


def _block(report: str, claim_id: str) -> str:
    return report.split(f'<div class="claim" id="{claim_id}">', 1)[1].split('<div class="claim"')[0]


def test_every_wider_app_is_one_an_alias_names():
    assert WIDER_APPS == {"native messages": "iMessages and SMS"}
    assert set(WIDER_APPS) <= set(APP_ALIASES)


def test_case01_has_no_such_app_so_no_claim_gets_the_note(audited):
    assert not NOTE_RE.search(render_report(audited))


def test_a_claim_resting_on_native_messages_says_so_in_the_report_and_on_its_page(
    audited, tmp_path
):
    claim_id, thread = _thread_of_a_claims_message(audited)
    audited.execute("UPDATE threads SET app = 'Native Messages' WHERE id = ?", (thread,))
    audited.commit()
    report = render_report(audited)
    check_report_text(report)
    block = _block(report, claim_id)
    (note,) = NOTE_RE.findall(block)
    assert "Native Messages holds iMessages and SMS together." in note
    assert "may be either, whatever word the claim uses" in note
    on_thread = {  # the claims whose shown evidence or checks rest on a message in it
        st.claim.id
        for st in claim_states(audited)
        if any(
            audited.execute(
                "SELECT 1 FROM messages WHERE id = ? AND thread_id = ?", (r, thread)
            ).fetchone()
            for r in claim_record_ids(st)
        )
    }
    assert claim_id in on_thread
    for cid in pipeline.view_run(audited)["manifest"]:
        assert bool(NOTE_RE.search(_block(report, cid))) == (cid in on_thread), cid
    app = App(tmp_path / "case.db", expert="Test Expert", port=8765)
    page = app.handle(Request("GET", "/claim", {"id": claim_id}, {"host": "127.0.0.1:8765"})).text
    assert NOTE_RE.findall(page) == [note]


def test_an_assumption_naming_the_app_gets_the_note_with_no_record(audited):
    st = next(s for s in claim_states(audited) if s.assumptions)
    a = st.assumptions[0]
    named = a.model_copy(
        update={"params": a.params.model_copy(update={"channels": ("Native Messages",)})}
    )
    bare = dataclasses.replace(st, assumptions=[named], evidence=[], checks=[])
    assert "Native Messages holds iMessages and SMS together." in mixed_app_note(audited, bare)
    other = a.model_copy(update={"params": a.params.model_copy(update={"channels": ("WhatsApp",)})})
    assert mixed_app_note(audited, dataclasses.replace(bare, assumptions=[other])) == ""


def test_one_note_per_app_however_it_is_spelled_and_none_for_an_empty_name(audited):
    st = next(s for s in claim_states(audited) if s.assumptions)
    a = st.assumptions[0]

    def on(*channels: str) -> str:
        named = a.model_copy(update={"params": a.params.model_copy(update={"channels": channels})})
        return mixed_app_note(
            audited, dataclasses.replace(st, assumptions=[named], evidence=[], checks=[])
        )

    assert on("") == ""
    assert len(NOTE_RE.findall(on("Native Messages", "native messages", ""))) == 1
