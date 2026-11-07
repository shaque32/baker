"""Plain guidance on each claim (core/review/guidance.py).

Every claim says what its verdict means, what it does not mean, and the judgment calls the
records cannot settle, in the same words on the claim page and in the report. Guidance never
changes a verdict or a label. Synthetic case01 only."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from core import db
from core.audit.invariants import FORBIDDEN_WORDS
from core.contracts import ClaimType, EvidenceStatus, Stance, SupportedBasis
from core.report.html import render_report
from core.review import actions, guidance
from core.review.redecide import redecide
from core.review.status import claim_state, claim_states
from eval import run_pipeline
from tests.test_report_consistency import _audit
from tests.test_review_screen import RUN_TIME, key_items
from ui.pages import Page, claim_page

EXPERT = "expert:Test Expert"


def at(hours: float):  # noqa: ANN201
    return lambda: RUN_TIME + timedelta(hours=hours)


@pytest.fixture(scope="module")
def audited(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("guidance") / "case01.db"
    conn = run_pipeline.build_case("case01", path)
    _audit(conn, RUN_TIME)
    conn.close()
    return path


@pytest.fixture
def conn(audited, tmp_path):  # noqa: ANN201
    copy = tmp_path / "case01.db"
    copy.write_bytes(audited.read_bytes())
    c = db.connect(copy)
    yield c
    c.close()


def test_every_claim_gets_plain_guidance_with_no_forbidden_word(conn):
    states = claim_states(conn)
    assert states
    for st in states:
        g = guidance.for_claim(conn, st)
        assert g.means and g.not_means
        text = " ".join([g.means, g.not_means, *g.judgment_calls])
        assert FORBIDDEN_WORDS.search(text) is None, (st.claim.id, text)


def test_guidance_never_changes_the_label(conn):
    before = [(st.claim.id, st.label) for st in claim_states(conn)]
    for st in claim_states(conn):
        guidance.for_claim(conn, st)
    assert [(st.claim.id, st.label) for st in claim_states(conn)] == before


def test_judgment_claim_types_carry_a_call_and_record_types_do_not(conn):
    for st in claim_states(conn):
        needs = guidance.for_claim(conn, st).judgment_calls
        if st.claim.claim_type in guidance.TYPE_CALLS:
            assert guidance.TYPE_CALLS[st.claim.claim_type] in needs
        elif st.claim.claim_type in (ClaimType.COMMUNICATION, ClaimType.TIMING, ClaimType.COUNT):
            assert needs == []  # ownership is confirmed in this case


def test_unconfirmed_phone_ownership_is_a_judgment_call(conn):
    """The case's assumptions name person:petrov; give that person a phone-ownership
    stipulation an expert has not confirmed, the state rules.py waits on."""
    conn.execute("INSERT OR IGNORE INTO persons VALUES ('person:petrov', 'Daniel Petrov', 't')")
    conn.execute(
        "INSERT INTO stipulations (id, kind, subject_id, person_id, statement, status)"
        " VALUES ('stip:device_owner:test', 'device_owner', 'dev:item1', 'person:petrov',"
        " 'Item 1 is Daniel Petrov''s phone', 'proposed')"
    )
    conn.commit()
    named = [
        st
        for st in claim_states(conn)
        if any(a.is_core and "person:petrov" in a.params.person_ids for a in st.assumptions)
    ]
    assert named
    for st in named:
        lines = guidance.for_claim(conn, st).judgment_calls
        assert lines[0] == (
            "Phone ownership is not confirmed for Daniel Petrov. The verdict waits on an expert "
            "confirming who owns the phone."
        )
    conn.execute(
        "UPDATE stipulations SET status = 'confirmed', decided_by = ?, decided_at_utc = 't'"
        " WHERE id = 'stip:device_owner:test'",
        (EXPERT,),
    )
    conn.commit()
    for st in named:
        assert not any(
            ln.startswith("Phone ownership") for ln in guidance.for_claim(conn, st).judgment_calls
        )


def test_unproven_never_reads_as_did_not_happen(conn):
    st = claim_state(conn, "C14")  # an absence claim, unproven in this case
    assert st is not None and st.label == "Unproven"
    g = guidance.for_claim(conn, st)
    assert g.not_means == guidance.NOT_FOUND
    assert "never means it did not happen" in g.not_means


def test_an_expert_confirmed_claim_drops_the_type_line(conn):
    for eid in key_items(conn, "C06"):
        actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Matches.", at(1))
    redecide(conn, EXPERT, at(2))
    st = claim_state(conn, "C06")
    assert st is not None and st.decision is not None
    if st.decision.supported_basis is not SupportedBasis.CONFIRMED:
        pytest.skip("C06 is not expert-confirmed by its key items in this case")
    assert (
        guidance.TYPE_CALLS[ClaimType.CONTENT_MEANING]
        not in guidance.for_claim(conn, st).judgment_calls
    )


def test_the_claim_page_and_the_report_show_the_same_block(conn):
    st = claim_state(conn, "C06")
    assert st is not None
    block = guidance.html(guidance.for_claim(conn, st))
    page = claim_page(conn, Page("t", "Tester"), "C06")
    assert page is not None and block in page
    assert block in render_report(conn)


def test_partial_expert_support_is_not_called_neither(conn):
    """An expert accepts the support for one core part of C08 while another core part has none:
    the verdict stays unproven, and the guidance says part is supported, not "neither"."""
    st = claim_state(conn, "C08")
    assert st is not None
    core = [a for a in st.assumptions if a.is_core]
    with_support = [
        a
        for a in core
        if any(e.assumption_id == a.id and e.stance == Stance.SUPPORTS for e in st.evidence)
    ]
    assert with_support and len(with_support) < len(core)
    for e in st.evidence:
        if e.stance == Stance.SUPPORTS:
            actions.decide_evidence(conn, e.id, EvidenceStatus.ACCEPTED, EXPERT, "Matches.", at(1))
    redecide(conn, EXPERT, at(2))
    st = claim_state(conn, "C08")
    assert st is not None and st.label == "Unproven" and not st.awaiting_expert
    g = guidance.for_claim(conn, st)
    assert g.means.startswith("Some core parts of this claim have support")
    assert g.not_means == guidance.NOT_FOUND
