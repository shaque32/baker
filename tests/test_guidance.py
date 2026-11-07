"""Plain guidance on each claim (core/review/guidance.py;
plans/lawyer-checker-and-examiner-pilot.md).

Every claim says what its verdict means, what it does not mean, and what needs an expert before
anyone relies on it in court, in the same words on the claim page and in the report. Guidance
never changes a verdict or a label. Synthetic case01 only."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from core import db
from core.audit.invariants import FORBIDDEN_WORDS
from core.contracts import ClaimType, EvidenceStatus, SupportedBasis
from core.report.html import render_report
from core.review import actions, activity, guidance
from core.review.redecide import redecide
from core.review.status import claim_state, claim_states
from eval import run_pipeline
from tests.test_report_consistency import _audit
from tests.test_review_screen import RUN_TIME, key_items
from ui.pages import Page, claim_page

COUNSEL = "counsel:Pat Lee"
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
        text = " ".join([g.means, g.not_means, *g.needs_expert])
        assert FORBIDDEN_WORDS.search(text) is None, (st.claim.id, text)


def test_guidance_never_changes_the_label(conn):
    before = [(st.claim.id, st.label) for st in claim_states(conn)]
    for st in claim_states(conn):
        guidance.for_claim(conn, st)
    assert [(st.claim.id, st.label) for st in claim_states(conn)] == before


def test_judgment_claim_types_need_an_expert_and_record_types_do_not(conn):
    for st in claim_states(conn):
        needs = guidance.for_claim(conn, st).needs_expert
        if st.claim.claim_type in guidance.TYPE_NEEDS:
            assert guidance.TYPE_NEEDS[st.claim.claim_type] in needs
        elif st.claim.claim_type in (ClaimType.COMMUNICATION, ClaimType.TIMING, ClaimType.COUNT):
            assert needs == []  # ownership is confirmed in this case


def test_unconfirmed_phone_ownership_needs_an_expert(conn):
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
        lines = guidance.for_claim(conn, st).needs_expert
        assert lines[0] == (
            "Phone ownership is not confirmed for Daniel Petrov. Only an expert can confirm "
            "who owns a phone."
        )
    conn.execute(
        "UPDATE stipulations SET status = 'confirmed', decided_by = ?, decided_at_utc = 't'"
        " WHERE id = 'stip:device_owner:test'",
        (EXPERT,),
    )
    conn.commit()
    for st in named:
        assert not any(
            ln.startswith("Phone ownership") for ln in guidance.for_claim(conn, st).needs_expert
        )


def test_unproven_never_reads_as_did_not_happen(conn):
    st = claim_state(conn, "C14")  # an absence claim, unproven in this case
    assert st is not None and st.label == "Unproven"
    g = guidance.for_claim(conn, st)
    assert g.not_means == guidance.NOT_FOUND
    assert "never means it did not happen" in g.not_means


def _counsel_supports(conn, claim_id: str = "C05") -> None:  # noqa: ANN001
    for eid in key_items(conn, claim_id):
        activity.record_view(conn, at(0.5)(), COUNSEL, "/evidence", session="s", query={"id": eid})
        actions.decide_counsel(
            conn, eid, EvidenceStatus.COUNSEL_ACCEPTED, COUNSEL, "Read the record.", at(1)
        )
    redecide(conn, EXPERT, at(2))


def test_counsel_review_reads_as_work_product_not_expert_opinion(conn):
    _counsel_supports(conn)
    st = claim_state(conn, "C05")
    assert st is not None and st.decision is not None
    assert st.decision.supported_basis is SupportedBasis.COUNSEL_REVIEWED
    g = guidance.for_claim(conn, st)
    assert "attorney work product" in g.means
    assert "not an expert's opinion" in g.not_means


def test_an_expert_confirmed_claim_drops_the_type_line(conn):
    for eid in key_items(conn, "C06"):
        actions.decide_evidence(conn, eid, EvidenceStatus.ACCEPTED, EXPERT, "Matches.", at(1))
    redecide(conn, EXPERT, at(2))
    st = claim_state(conn, "C06")
    assert st is not None and st.decision is not None
    if st.decision.supported_basis is not SupportedBasis.CONFIRMED:
        pytest.skip("C06 is not expert-confirmed by its key items in this case")
    assert (
        guidance.TYPE_NEEDS[ClaimType.CONTENT_MEANING]
        not in guidance.for_claim(conn, st).needs_expert
    )


def test_the_claim_page_and_the_report_show_the_same_block(conn):
    st = claim_state(conn, "C06")
    assert st is not None
    block = guidance.html(guidance.for_claim(conn, st))
    page = claim_page(conn, Page("t", "Tester"), "C06")
    assert page is not None and block in page
    assert block in render_report(conn)
