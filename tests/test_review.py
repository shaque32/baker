import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit._llm_json import PROMPTS_DIR, prompt_body, required_placeholders
from core.audit.review import (
    REVIEW_SCHEMA,
    LocalEvidenceReviewer,
    NeedsHumanReaderError,
    NotReviewableError,
    insert_review,
    is_reviewable,
    review_count,
)
from core.contracts import (
    EvidenceItem,
    EvidenceReviewer,
    EvidenceStatus,
    ModelCallOutcome,
    ProvenanceTier,
    ReviewDecision,
    ReviewerKind,
    SourceRef,
    Stance,
    evidence_id,
)
from tests.fake_model import FakeModel, make_assumption

SIGNED = (PROMPTS_DIR / "reviewer.md").read_text("utf-8")
RATIONALE = "LABELER-RATIONALE-SENTINEL: the garage clearly means the stash house"
NOW = datetime(2026, 10, 7, 3, 0, tzinfo=UTC)

ASSUMPTION = make_assumption("The sender asked to meet at the garage on March 5.")
QUOTE = "meet me at the garage"
ITEM = EvidenceItem(
    id=evidence_id(ASSUMPTION.id, "msg:src1:00012", Stance.SUPPORTS, QUOTE),
    assumption_id=ASSUMPTION.id,
    record_id="msg:src1:00012",
    ref=SourceRef(source_id="src1", locator="Chats!14"),
    stance=Stance.SUPPORTS,
    quote=QUOTE,
    quote_verified=True,
    rationale=RATIONALE,
    tier=ProvenanceTier.OBSERVED,
    status=EvidenceStatus.OPEN,
    model_run_id="run:stance:1",
)
CONTEXT = ">> 2026-03-05 21:01 -05:00 acct:a1 (Marc): meet me at the garage at 9"
ACCEPT = {"decision": "accept", "reason": "The message asks to meet at the garage."}


def reviewer(*replies, prior=0, **kw) -> tuple[LocalEvidenceReviewer, FakeModel]:
    model = FakeModel(*replies, **kw)
    rev = LocalEvidenceReviewer(
        model,
        model_name="qwen-14b-q4",
        template=prompt_body(SIGNED),
        prior_reviews=lambda _eid: prior,
        clock=lambda: NOW,
    )
    return rev, model


def test_conforms_to_contract_protocol():
    rev, _ = reviewer(ACCEPT)
    _: EvidenceReviewer = rev


def test_loads_signed_prompt_by_default():
    rev = LocalEvidenceReviewer(FakeModel(ACCEPT), model_name="m")
    assert {"assumption", "quote", "context"} <= required_placeholders(rev.template)


def test_accept_is_ai_accepted_never_confirmed():
    rev, model = reviewer(ACCEPT)
    d = rev.review(ASSUMPTION, ITEM, CONTEXT)
    assert isinstance(d, ReviewDecision)
    assert d.status is EvidenceStatus.AI_ACCEPTED
    assert d.reviewer_kind is ReviewerKind.AI
    assert d.reviewer == "ai:qwen-14b-q4"
    assert d.reason == ACCEPT["reason"]
    assert d.seq == 1 and d.id == f"rv:{ITEM.id}#1"
    assert d.model_run_id == "run:fake:1"
    assert d.model_call_id == "mc:run:fake:1#1"
    assert d.decided_at_utc == NOW
    assert model.schemas[0] is REVIEW_SCHEMA
    (call,) = rev.recorder.calls
    assert call.outcome is ModelCallOutcome.OK and call.subject_ids == (ITEM.id,)


def test_dismiss():
    rev, _ = reviewer({"decision": "dismiss", "reason": "Garage is slang here."})
    d = rev.review(ASSUMPTION, ITEM, CONTEXT)
    assert d.status is EvidenceStatus.DISMISSED
    assert d.reason == "Garage is slang here."


def test_reviewer_never_sees_labeler_rationale():
    rev, model = reviewer(ACCEPT)
    rev.review(ASSUMPTION, ITEM, CONTEXT)
    prompt = model.prompts[0]
    assert "SENTINEL" not in prompt
    assert ITEM.quote in prompt and ASSUMPTION.text in prompt and CONTEXT in prompt


BAD = [
    pytest.param("accept", ModelCallOutcome.INVALID_OUTPUT, id="bare-word"),
    pytest.param('{"decision": "accept"}', ModelCallOutcome.INVALID_OUTPUT, id="no-reason"),
    pytest.param({"decision": "accept", "reason": ""}, ModelCallOutcome.INVALID_OUTPUT, id="empty"),
    pytest.param(
        {"decision": "accept", "reason": "  "}, ModelCallOutcome.INVALID_OUTPUT, id="blank"
    ),
    pytest.param(
        {"decision": "Accept", "reason": "ok"}, ModelCallOutcome.INVALID_OUTPUT, id="case"
    ),
    pytest.param(
        {"decision": "confirm", "reason": "ok"}, ModelCallOutcome.INVALID_OUTPUT, id="conf"
    ),
    pytest.param(
        {"decision": "accept", "reason": "ok", "confidence": 0.99},
        ModelCallOutcome.INVALID_OUTPUT,
        id="extra-field",
    ),
    pytest.param(
        '{"decision":"dismiss","decision":"accept","reason":"ok"}',
        ModelCallOutcome.INVALID_OUTPUT,
        id="dup-key",
    ),
    pytest.param(
        '{"decision":"accept","reason":"ok"}\n{"decision":"accept"}',
        ModelCallOutcome.INVALID_OUTPUT,
        id="two-objects",
    ),
    pytest.param(
        {"decision": "accept", "reason": "x" * 5000},
        ModelCallOutcome.INVALID_OUTPUT,
        id="reason-too-long",
    ),
    pytest.param(TimeoutError("model hung"), ModelCallOutcome.ERROR, id="model-raises"),
    pytest.param("", ModelCallOutcome.ERROR, id="port-runtime-error"),
]


@pytest.mark.parametrize(("reply", "outcome"), BAD)
def test_any_failure_is_a_dismissal(reply, outcome):
    rev, _ = reviewer(reply)
    d = rev.review(ASSUMPTION, ITEM, CONTEXT)
    assert d.status is EvidenceStatus.DISMISSED
    assert "could not be completed" in d.reason
    (call,) = rev.recorder.calls
    assert call.outcome is outcome
    assert d.model_call_id == call.id


def test_failure_keeps_raw_output():
    rev, _ = reviewer("accept!!")
    rev.review(ASSUMPTION, ITEM, CONTEXT)
    assert rev.recorder.calls[0].raw_output == "accept!!"


def test_blank_context_is_a_dismissal_without_calling():
    rev, model = reviewer(ACCEPT)
    d = rev.review(ASSUMPTION, ITEM, "  \n ")
    assert d.status is EvidenceStatus.DISMISSED and "no context" in d.reason
    assert d.model_call_id is None
    assert model.prompts == []


def test_model_without_run_id_decides_nothing():
    rev, model = reviewer(ACCEPT, run_id="")
    with pytest.raises(NotReviewableError):
        rev.review(ASSUMPTION, ITEM, CONTEXT)
    assert model.prompts == []


@pytest.mark.parametrize("quote", ["я волнуюсь за Маркуса", "ok Катя"])
def test_non_english_quote_waits_for_a_human(quote):
    rev, model = reviewer(ACCEPT)
    item = ITEM.model_copy(update={"quote": quote})
    assert not is_reviewable(item)
    with pytest.raises(NeedsHumanReaderError):
        rev.review(ASSUMPTION, item, CONTEXT)
    assert model.prompts == []


def test_never_reviews_an_item_that_already_has_a_decision():
    # e.g. an expert accepted, then undid it (status back to open): the AI must not step in.
    rev, model = reviewer(ACCEPT, prior=2)
    assert not is_reviewable(ITEM, prior_reviews=2)
    with pytest.raises(NotReviewableError, match="already reviewed"):
        rev.review(ASSUMPTION, ITEM, CONTEXT)
    assert model.prompts == []


def test_is_reviewable():
    assert is_reviewable(ITEM)
    assert not is_reviewable(ITEM.model_copy(update={"stance": Stance.CONTRADICTS}))


@pytest.mark.parametrize(
    "update",
    [
        {"stance": Stance.CONTRADICTS},
        {"stance": Stance.COMPLICATES},
        {"stance": Stance.IRRELEVANT},
        {"status": EvidenceStatus.ACCEPTED},
        {"status": EvidenceStatus.DISMISSED},
        {"status": EvidenceStatus.AI_ACCEPTED},
        {"quote": "  "},
    ],
)
def test_refuses_items_it_must_not_touch(update):
    rev, model = reviewer(ACCEPT)
    with pytest.raises(NotReviewableError):
        rev.review(ASSUMPTION, ITEM.model_copy(update=update), CONTEXT)
    assert model.prompts == []


def test_refuses_item_for_another_assumption():
    rev, _ = reviewer(ACCEPT)
    other = make_assumption("Something else.", claim_id="c2")
    with pytest.raises(NotReviewableError):
        rev.review(other, ITEM, CONTEXT)


def test_model_name_required():
    with pytest.raises(ValueError):
        LocalEvidenceReviewer(FakeModel(ACCEPT), model_name=" ", template=prompt_body(SIGNED))


def test_store_and_count_reviews(case_db: sqlite3.Connection):
    cols = {r[1] for r in case_db.execute("PRAGMA table_info(evidence_reviews)")}
    if "reason" not in cols:
        pytest.skip("schema v0.2 (evidence_reviews) not applied yet")
    case_db.execute("PRAGMA foreign_keys = OFF")
    rev, _ = reviewer(ACCEPT, prior=0)
    d = rev.review(ASSUMPTION, ITEM, CONTEXT)
    insert_review(case_db, d)
    assert review_count(case_db, ITEM.id) == 1
    row = case_db.execute(
        "SELECT reviewer_kind, reviewer, status, reason, decided_at_utc FROM evidence_reviews"
    ).fetchone()
    assert row == ("ai", "ai:qwen-14b-q4", "ai_accepted", ACCEPT["reason"], "2026-10-07T03:00:00Z")
    # The pipeline wires prior_reviews to the table: a second AI review is refused.
    rev2 = LocalEvidenceReviewer(
        FakeModel(ACCEPT),
        model_name="m",
        template=prompt_body(SIGNED),
        prior_reviews=lambda eid: review_count(case_db, eid),
    )
    with pytest.raises(NotReviewableError):
        rev2.review(ASSUMPTION, ITEM, CONTEXT)


def test_suggested_marker_strips_human_header():
    marked = SIGNED.replace(
        "agents only wire it to the local model.\n",
        "agents only wire it to the local model.\n<!-- prompt starts -->\n",
    )
    assert "<!-- prompt starts -->" in marked
    rev = LocalEvidenceReviewer(FakeModel(ACCEPT), model_name="m", template=prompt_body(marked))
    assert "HUMAN-OWNED" not in rev.template


def test_draft_docs_have_required_placeholders():
    from core.audit.stance import PLACEHOLDERS as STANCE_PH
    from core.audit.translation import PLACEHOLDERS as TR_PH
    from core.claims.extract import PLACEHOLDERS as CLAIM_PH

    root = Path(__file__).parents[1] / "docs/prompts"
    drafts = (("stance.md", STANCE_PH), ("claims.md", CLAIM_PH), ("translation.md", TR_PH))
    for name, ph in drafts:
        body = prompt_body((root / name).read_text("utf-8"))
        assert ph <= required_placeholders(body), name
