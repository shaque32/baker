from pathlib import Path

import pytest

from core.audit._llm_json import PROMPTS_DIR, prompt_body
from core.audit.review import (
    REVIEW_SCHEMA,
    LocalEvidenceReviewer,
    NotReviewableError,
)
from core.contracts import (
    Assumption,
    AssumptionKind,
    EvidenceItem,
    EvidenceReviewer,
    EvidenceStatus,
    ProvenanceTier,
    SourceRef,
    Stance,
)
from tests.fake_model import FakeModel

SIGNED = (PROMPTS_DIR / "reviewer.md").read_text("utf-8")
RATIONALE = "LABELER-RATIONALE-SENTINEL: the garage clearly means the stash house"

ASSUMPTION = Assumption(
    id="asm:c1:1",
    claim_id="c1",
    kind=AssumptionKind.MEANING,
    text="The sender asked to meet at the garage on March 5.",
    is_core=True,
    tier=ProvenanceTier.INFERRED,
)
ITEM = EvidenceItem(
    id="ev:asm:c1:1:msg:src1:00012",
    assumption_id=ASSUMPTION.id,
    record_id="msg:src1:00012",
    ref=SourceRef(source_id="src1", locator="Chats!14"),
    stance=Stance.SUPPORTS,
    quote="meet me at the garage",
    quote_verified=True,
    rationale=RATIONALE,
    tier=ProvenanceTier.OBSERVED,
    status=EvidenceStatus.OPEN,
    model_run_id="run:stance:1",
)
CONTEXT = ">> 2026-03-05 21:01 -05:00 acct:a1 (Marc): meet me at the garage at 9"
ACCEPT = {"decision": "accept", "reason": "The message asks to meet at the garage."}


def reviewer(*replies, **kw) -> tuple[LocalEvidenceReviewer, FakeModel]:
    model = FakeModel(*replies, **kw)
    return LocalEvidenceReviewer(model, template=prompt_body(SIGNED)), model


def test_conforms_to_contract_protocol():
    rev, _ = reviewer(ACCEPT)
    _: EvidenceReviewer = rev


def test_loads_signed_prompt_by_default():
    rev = LocalEvidenceReviewer(FakeModel(ACCEPT))
    assert "{assumption}" in rev.template


def test_accept_is_ai_accepted_never_confirmed():
    rev, model = reviewer(ACCEPT)
    out = rev.review_with_reason(ASSUMPTION, ITEM, CONTEXT)
    assert out.status is EvidenceStatus.AI_ACCEPTED
    assert out.reason == ACCEPT["reason"]
    assert out.error is None
    assert out.reviewer == "ai_reviewer"
    assert model.schemas[0] is REVIEW_SCHEMA
    assert rev.review(ASSUMPTION, ITEM, CONTEXT) is EvidenceStatus.AI_ACCEPTED


def test_dismiss():
    rev, _ = reviewer({"decision": "dismiss", "reason": "Garage is slang here."})
    out = rev.review_with_reason(ASSUMPTION, ITEM, CONTEXT)
    assert out.status is EvidenceStatus.DISMISSED
    assert out.error is None


def test_reviewer_never_sees_labeler_rationale():
    rev, model = reviewer(ACCEPT)
    rev.review(ASSUMPTION, ITEM, CONTEXT)
    prompt = model.prompts[0]
    assert "SENTINEL" not in prompt
    assert ITEM.quote in prompt and ASSUMPTION.text in prompt and CONTEXT in prompt


BAD = [
    pytest.param("accept", id="bare-word"),
    pytest.param('{"decision": "accept"}', id="no-reason"),
    pytest.param({"decision": "accept", "reason": ""}, id="empty-reason"),
    pytest.param({"decision": "accept", "reason": "   "}, id="blank-reason"),
    pytest.param({"decision": "Accept", "reason": "ok"}, id="wrong-case"),
    pytest.param({"decision": "confirm", "reason": "ok"}, id="confirm"),
    pytest.param({"decision": "accept", "reason": "ok", "confidence": 0.99}, id="extra-field"),
    pytest.param('{"decision":"dismiss","decision":"accept","reason":"ok"}', id="dup-key"),
    pytest.param('{"decision":"accept","reason":"ok"}\n{"decision":"accept"}', id="two-objects"),
    pytest.param(TimeoutError("model hung"), id="model-raises"),
    pytest.param({"decision": "accept", "reason": "x" * 5000}, id="reason-too-long"),
]


@pytest.mark.parametrize("reply", BAD)
def test_any_failure_is_a_dismissal(reply):
    rev, _ = reviewer(reply)
    out = rev.review_with_reason(ASSUMPTION, ITEM, CONTEXT)
    assert out.status is EvidenceStatus.DISMISSED
    assert out.error
    assert "unusable" in out.reason


def test_failure_keeps_raw_output():
    rev, _ = reviewer("accept!!")
    assert rev.review_with_reason(ASSUMPTION, ITEM, CONTEXT).raw_output == "accept!!"


def test_model_without_run_id_dismisses_without_calling():
    rev, model = reviewer(ACCEPT, run_id="")
    assert rev.review(ASSUMPTION, ITEM, CONTEXT) is EvidenceStatus.DISMISSED
    assert model.prompts == []


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
    other = ASSUMPTION.model_copy(update={"id": "asm:c2:1"})
    with pytest.raises(NotReviewableError):
        rev.review(other, ITEM, CONTEXT)


def test_suggested_marker_strips_human_header():
    marked = SIGNED.replace(
        "agents only wire it to the local model.\n",
        "agents only wire it to the local model.\n<!-- prompt starts -->\n",
    )
    assert "<!-- prompt starts -->" in marked
    rev = LocalEvidenceReviewer(FakeModel(ACCEPT), template=prompt_body(marked))
    assert "HUMAN-OWNED" not in rev.template


def test_draft_docs_have_required_placeholders():
    from core.audit._llm_json import required_placeholders
    from core.audit.stance import PLACEHOLDERS as STANCE_PH
    from core.claims.extract import PLACEHOLDERS as CLAIM_PH

    root = Path(__file__).parents[1] / "docs/prompts"
    for name, ph in (("stance.md", STANCE_PH), ("claims.md", CLAIM_PH)):
        body = prompt_body((root / name).read_text("utf-8"))
        assert ph <= required_placeholders(body), name
