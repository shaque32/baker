"""Rules 0.4.0, rule 1a: a failed check on an assumption the testability agent proposed (and an
examiner accepted) does not contradict the claim by itself. The claim stays unproven, the claim
page and the report say "Contradiction found, confirm to finalize", and the failure counts once
the expert confirms it, for as long as the check fails exactly that way. The audit, a verdict
re-run and verify-bundle read the same inputs (core/audit/testability.verdict_inputs).

Synthetic case01 only, with scripted fake models (tests/test_testability.py's C01 repair). The
contact check never fails on its own (a missing contact is inconclusive), so these tests make it
fail on C01 to stand for a check that fails on an agent's assumption.
"""

from __future__ import annotations

import html
import json
import sqlite3

import pytest

from core import pipeline
from core.audit import testability
from core.audit.checks import identity
from core.bundle import verify as verify_mod
from core.bundle.verify import FAIL, PASS
from core.contracts import CheckOutcome, ClaimStatus, Verdict
from core.report.html import render_report
from core.review.actions import ReviewError, confirm_agent_fail, decide_repair, set_claim_status
from core.review.redecide import redecide
from core.review.status import CONTRADICTION_FOUND, agent_fail_step, claim_state
from tests.test_testability import EXAMINER, _audit, _check, _components, _copy, _log

DETAIL = 'item1 has no contact "Marc Garage" with +12125550122.'


@pytest.fixture
def failing(monkeypatch):
    """The contact check fails on C01, with `detail` as it failed."""
    real = identity.ContactCheck.evaluate
    said = {"detail": DETAIL}

    def evaluate(self, assumption_id, p, data):  # noqa: ANN001, ANN202
        r = real(self, assumption_id, p, data)
        return r.model_copy(update={"outcome": CheckOutcome.FAIL, "detail": said["detail"]})

    monkeypatch.setattr(identity.ContactCheck, "evaluate", evaluate)
    return said


def _verdicts(conn) -> list:  # noqa: ANN001
    out = verify_mod._Out()
    verify_mod._verdicts(conn, pipeline.view_run(conn), out)
    return out.items


def _verdict(conn) -> Verdict:  # noqa: ANN001
    d = pipeline.load_verdict(conn, "C01", pipeline.view_run(conn)["run_id"])
    assert d is not None
    return d.verdict


def _failed_check(conn) -> str:  # noqa: ANN001
    st = claim_state(conn, "C01")
    assert st is not None
    (c,) = st.agent_fails
    return c.id


def _seen(conn) -> str:  # noqa: ANN001
    """The waiting failure as the claim page shows it (the form's `seen`)."""
    st = claim_state(conn, "C01")
    assert st is not None
    (c,) = st.agent_fails
    return st.agent_seen[c.id]


def _confirm(conn, reason: str = "Not on the phone.") -> None:  # noqa: ANN001
    confirm_agent_fail(conn, "C01", _failed_check(conn), EXAMINER, reason, seen=_seen(conn))


def test_a_failed_check_on_the_agents_assumption_waits_for_the_expert(tmp_path, failing):
    conn, first = _audit(tmp_path, signed=False)  # the examiner accepts in the audit
    try:
        assert first.manifest["C01"]["assumptions"]  # the agent's proposal was used
        assert _verdict(conn) is Verdict.UNPROVEN  # rules 0.3.0 gave contradicted here
        st = claim_state(conn, "C01")
        assert st is not None and st.contradiction_found and st.label == CONTRADICTION_FOUND
        (c,) = st.agent_fails
        assert c.check_name == "contact" and c.outcome is CheckOutcome.FAIL
        step = agent_fail_step(1)
        assert any(step in text for _p, text in st.needs())
        assert html.escape(step) in render_report(conn)
        d = pipeline.load_verdict(conn, "C01", first.run_id)
        assert d is not None and any("an assumption an agent proposed" in r for r in d.reasons)
        # its evidence was still labeled: a waiting failure settles nothing
        assert "C01" not in first.unlabeled
        assert [f.level for f in _verdicts(conn)] == [PASS]
    finally:
        conn.close()


def test_a_confirmed_failure_contradicts_from_the_next_verdict_run(tmp_path, failing):
    conn, first = _audit(tmp_path, signed=False)
    try:
        check, seen = _failed_check(conn), _seen(conn)
        for actor, cid, reason, why in (
            ("system", check, "Read it.", "expert"),
            (EXAMINER, check, " ", "say why"),
            (EXAMINER, "check:nothing", "Read it.", "not waiting"),
        ):
            with pytest.raises(ReviewError, match=why):
                confirm_agent_fail(conn, "C01", cid, actor, reason, seen=seen)
        confirm_agent_fail(
            conn, "C01", check, EXAMINER, "The contact is not on the phone.", seen=seen
        )
        ((actor, entry),) = _log(conn, testability.CONFIRM_ACTION)
        assert actor == EXAMINER and entry["check_id"] == check
        assert entry["reason"] == "The contact is not on the phone."
        st = claim_state(conn, "C01")
        assert st is not None and st.agent_fails == [] and st.decided_after_run
        assert _verdict(conn) is Verdict.UNPROVEN  # nothing changes until the verdicts re-run
        with pytest.raises(ReviewError, match="not waiting"):
            confirm_agent_fail(conn, "C01", check, EXAMINER, "Again.", seen=seen)
        redecide(conn, EXAMINER)
        assert _verdict(conn) is Verdict.CONTRADICTED
        d = pipeline.load_verdict(conn, "C01", pipeline.view_run(conn)["run_id"])
        assert d is not None and d.cited_check_ids == (check,)
        assert "an expert confirmed the failure" in d.reasons[0]
        assert [f.level for f in _verdicts(conn)] == [PASS]
        assert all(f.level != FAIL for f in _check(conn))
    finally:
        conn.close()


def test_rejecting_the_proposal_undoes_a_confirm(tmp_path, failing):
    conn, first = _audit(tmp_path, signed=False)
    try:
        _confirm(conn)
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "Wrong reading.")
        redecide(conn, EXAMINER)
        assert _verdict(conn) is Verdict.UNPROVEN
        st = claim_state(conn, "C01")
        assert st is not None and st.agent_fails == []  # the next audit does not use it
        assert [f.level for f in _verdicts(conn)] == [PASS]
        second = pipeline.run_audit(conn, _components(conn, signed=False), claim_ids=["C01"])
        assert "C01" in second.not_tested and second.manifest["C01"]["assumptions"] == []
    finally:
        conn.close()


def test_a_rejection_after_the_verdicts_used_a_confirm_marks_them_not_current(tmp_path, failing):
    """A stale tab's reject after the confirm re-ran the verdicts: the shown contradicted no
    longer follows from the log, so the claim says to re-run them (Codex on #166)."""
    conn, first = _audit(tmp_path, signed=False)
    try:
        _confirm(conn)
        redecide(conn, EXAMINER)
        st = claim_state(conn, "C01")
        assert _verdict(conn) is Verdict.CONTRADICTED and st is not None
        assert not st.decided_after_run
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "Wrong reading.")
        st = claim_state(conn, "C01")
        assert st is not None and st.decided_after_run and st.stale
        assert any("Re-run verdicts" in text for _p, text in st.needs())
        redecide(conn, EXAMINER)
        assert _verdict(conn) is Verdict.UNPROVEN
        st = claim_state(conn, "C01")
        assert st is not None and not st.decided_after_run
    finally:
        conn.close()


def test_a_rejection_with_no_confirm_to_undo_leaves_the_verdicts_current(tmp_path, failing):
    conn, first = _audit(tmp_path, signed=False)
    try:
        decide_repair(conn, "C01", first.run_id, 1, False, EXAMINER, "Wrong reading.")
        st = claim_state(conn, "C01")
        assert st is not None and not st.decided_after_run
    finally:
        conn.close()


def test_a_confirm_binds_to_the_failure_the_expert_saw(tmp_path, failing):
    """A page left open across a later audit whose check failed another way confirms nothing:
    the form carries the failure it showed (Codex on #168)."""
    conn, _first = _audit(tmp_path, signed=False)
    try:
        check, seen = _failed_check(conn), _seen(conn)
        failing["detail"] = 'item1 has the contact "Marc Garage" with another number.'
        pipeline.run_audit(conn, _components(conn, signed=False), claim_ids=["C01"])
        assert _failed_check(conn) == check and _seen(conn) != seen  # same check, new failure
        with pytest.raises(ReviewError, match="changed after the page you read"):
            confirm_agent_fail(conn, "C01", check, EXAMINER, "Not on the phone.", seen=seen)
        assert _log(conn, testability.CONFIRM_ACTION) == []
        assert _verdict(conn) is Verdict.UNPROVEN
        _confirm(conn)  # the failure on screen now
        assert len(_log(conn, testability.CONFIRM_ACTION)) == 1
    finally:
        conn.close()


def test_a_confirm_binds_to_the_claim_and_proposal_the_expert_saw(tmp_path, failing):
    """A page left open across a claim edit confirms nothing on the edited claim, even when the
    next audit's check fails the same way on the same proposed assumption: the form carries the
    claim text and the proposal it showed with the failure (Codex on #166)."""
    conn, _first = _audit(tmp_path, signed=False)
    try:
        check, seen = _failed_check(conn), _seen(conn)
        (c,) = claim_state(conn, "C01").agent_fails  # type: ignore[union-attr]
        failed = testability.check_sha256(c)
        (text,) = conn.execute("SELECT text FROM claims WHERE id = 'C01'").fetchone()
        set_claim_status(conn, "C01", ClaimStatus.EDITED, EXAMINER, text=text + " (as edited)")
        pipeline.run_audit(conn, _components(conn, signed=False), claim_ids=["C01"])
        (c,) = claim_state(conn, "C01").agent_fails  # type: ignore[union-attr]
        assert c.id == check and testability.check_sha256(c) == failed  # the same failure
        with pytest.raises(ReviewError, match="changed after the page you read"):
            confirm_agent_fail(conn, "C01", check, EXAMINER, "Not on the phone.", seen=seen)
        assert _log(conn, testability.CONFIRM_ACTION) == []
        assert _verdict(conn) is Verdict.UNPROVEN
        _confirm(conn)  # the edited claim's failure, as its page shows it
        assert len(_log(conn, testability.CONFIRM_ACTION)) == 1
    finally:
        conn.close()


def test_a_confirm_holds_only_while_the_check_fails_the_same_way(tmp_path, failing):
    conn, first = _audit(tmp_path, signed=False)
    try:
        _confirm(conn)
        again = pipeline.run_audit(conn, _components(conn, signed=False), claim_ids=["C01"])
        assert again.manifest["C01"]["assumptions"] == first.manifest["C01"]["assumptions"]
        assert _verdict(conn) is Verdict.CONTRADICTED  # the same failure, confirmed
        assert [f.level for f in _verdicts(conn)] == [PASS]
        failing["detail"] = 'item1 has the contact "Marc Garage" with another number.'
        pipeline.run_audit(conn, _components(conn, signed=False), claim_ids=["C01"])
        assert _verdict(conn) is Verdict.UNPROVEN  # another failure waits for the expert
        assert claim_state(conn, "C01").agent_fails  # type: ignore[union-attr]
        assert [f.level for f in _verdicts(conn)] == [PASS]
    finally:
        conn.close()


def test_verify_bundle_fails_a_confirm_that_is_not_an_experts(tmp_path, failing):
    conn, _first = _audit(tmp_path, signed=False)
    try:
        _confirm(conn)
        redecide(conn, EXAMINER)
        copy = _copy(conn, tmp_path)
        copy.execute("UPDATE audit_log SET actor = 'system' WHERE action = ?",
                     (testability.CONFIRM_ACTION,))  # fmt: skip
        details = [f.detail for f in _check(copy) if f.level == FAIL]
        assert any("not by an expert" in d for d in details)
        # and the stored contradicted no longer follows from the rules
        assert any(f.level == FAIL for f in _verdicts(copy))
        copy.close()
    finally:
        conn.close()


def test_the_claim_page_shows_each_failure_and_confirms_one(tmp_path, failing):
    from ui.app import App, Request

    conn, _first = _audit(tmp_path, signed=False)
    check = _failed_check(conn)
    conn.close()
    app = App(tmp_path / "case01.db", "Dana Reyes", 8765, model_check=None)
    host = {"host": "127.0.0.1:8765"}
    page = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(host))).body.decode()
    card = page.split("<section class='agent' id='agent-fail'>", 1)[1].split("</section>", 1)[0]
    assert testability.PROPOSED_MARK in card and html.escape(CONTRADICTION_FOUND) in card
    assert card.count("Confirm this failure") == 1 and card.count("value='reject'") == 1
    assert html.escape(DETAIL) in card and "confirm all" not in page.lower()
    form = {
        "token": app.token,
        "claim": "C01",
        "check": check,
        "seen": card.split("name='seen' value='", 1)[1].split("'", 1)[0],
        "reason": "The phone has no such contact.",
        "next": "/claim?id=C01",
    }
    stale = app.handle(
        Request("POST", "/testability/confirm", {}, dict(host), {**form, "seen": "0" * 64})
    )
    assert stale.status == 303
    page = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(host))).body.decode()
    assert "changed after the page you read" in page and "id='agent-fail'" in page
    app.handle(Request("POST", "/testability/confirm", {}, dict(host), form))
    page = app.handle(Request("GET", "/claim", {"id": "C01"}, dict(host))).body.decode()
    assert "id='agent-fail'" not in page
    c = sqlite3.connect(tmp_path / "case01.db")
    try:
        ((actor, entry),) = _log(c, testability.CONFIRM_ACTION)
        assert actor == "expert:Dana Reyes" and entry["via"] == "claim page"
        assert _verdict(c) is Verdict.CONTRADICTED  # the page re-ran the verdicts
        run = json.loads(c.execute(
            "SELECT config_json FROM pipeline_runs ORDER BY started_at_utc DESC LIMIT 1"
        ).fetchone()[0])  # fmt: skip
        assert run["mode"] == "rules_only"
    finally:
        c.close()
