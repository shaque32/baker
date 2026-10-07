from pathlib import Path

import pytest

from core.audit._llm_json import PromptMissingError, prompt_body
from core.audit.stance import (
    STANCE_SCHEMA,
    DroppedStanceLabel,
    LocalStanceLabeler,
)
from core.contracts import (
    EvidenceCandidate,
    ModelCallOutcome,
    ProvenanceTier,
    SourceRef,
    Stance,
    StanceLabeler,
)
from tests.fake_model import FakeModel, make_assumption

DRAFT = prompt_body((Path(__file__).parents[1] / "docs/prompts/stance.md").read_text("utf-8"))

ASSUMPTION = make_assumption("The sender asked to meet at the garage on March 5.")
CANDIDATE = EvidenceCandidate(
    record_id="msg:src1:00012",
    ref=SourceRef(source_id="src1", locator="Chats!14"),
    text="meet me at the garage at 9",
    tier=ProvenanceTier.OBSERVED,
    retrieval_score=0.9,
)
GOOD = {"stance": "supports", "quote": "meet me at the garage", "rationale": "Asks to meet."}


def labeler(*replies, **kw) -> tuple[LocalStanceLabeler, FakeModel]:
    model = FakeModel(*replies, **kw)
    return LocalStanceLabeler(model, template=DRAFT), model


def test_conforms_to_contract_protocol():
    lab, _ = labeler(GOOD)
    assert isinstance(lab, LocalStanceLabeler)
    _: StanceLabeler = lab  # static conformance


def test_good_output_becomes_label_with_ids_from_inputs():
    lab, model = labeler({**GOOD, "stance": "supports"})
    label = lab.label(ASSUMPTION, CANDIDATE)
    assert label.stance is Stance.SUPPORTS
    assert label.assumption_id == ASSUMPTION.id
    assert label.record_id == CANDIDATE.record_id
    assert label.model_run_id == "run:fake:1"
    assert label.model_call_id == "mc:run:fake:1#1"
    assert model.schemas[0] is STANCE_SCHEMA
    (call,) = lab.recorder.calls
    assert call.outcome is ModelCallOutcome.OK
    assert call.subject_ids == (ASSUMPTION.id, CANDIDATE.record_id)
    assert call.prompt == model.prompts[0]


def test_prompt_contains_inputs_and_no_header():
    lab, model = labeler(GOOD)
    lab.label(ASSUMPTION, CANDIDATE)
    prompt = model.prompts[0]
    assert ASSUMPTION.text in prompt
    assert CANDIDATE.text in prompt
    assert "DRAFT for Arsh" not in prompt
    assert '{"stance": "supports"' in prompt  # literal JSON braces survive filling


def test_evidence_text_cannot_inject_placeholders():
    cand = CANDIDATE.model_copy(update={"text": "see {context} and {assumption}"})
    lab, model = labeler(GOOD)
    lab.label(ASSUMPTION, cand)
    assert "see {context} and {assumption}" in model.prompts[0]


def test_renderers_are_used():
    model = FakeModel(GOOD)
    lab = LocalStanceLabeler(
        model,
        template=DRAFT,
        render_record=lambda c: f"[REC {c.record_id}] {c.text}",
        render_context=lambda c: "CTX-LINE",
    )
    lab.label(ASSUMPTION, CANDIDATE)
    assert "[REC msg:src1:00012]" in model.prompts[0]
    assert "CTX-LINE" in model.prompts[0]


BAD_OUTPUTS = [
    pytest.param("not json", id="not-json"),
    pytest.param('```json\n{"stance":"supports"}\n```', id="code-fence"),
    pytest.param("[]", id="array"),
    pytest.param('{"stance":"supports","quote":"x","rationale":"r"} trailing', id="trailing"),
    pytest.param(
        '{"stance":"supports","stance":"irrelevant","quote":"x","rationale":"r"}', id="dup-key"
    ),
    pytest.param({**GOOD, "stance": "SUPPORTS"}, id="wrong-case"),
    pytest.param({**GOOD, "stance": "strongly_supports"}, id="unknown-stance"),
    pytest.param({**GOOD, "verdict": "supported"}, id="extra-field"),
    pytest.param({"stance": "supports", "quote": "x"}, id="missing-rationale"),
    pytest.param({**GOOD, "rationale": "   "}, id="blank-rationale"),
    pytest.param({**GOOD, "quote": ""}, id="supports-without-quote"),
    pytest.param({**GOOD, "stance": "contradicts", "quote": "  "}, id="contradicts-blank-quote"),
    pytest.param({**GOOD, "quote": 12}, id="quote-not-string"),
    pytest.param({**GOOD, "quote": "x" * 5000}, id="quote-too-long"),
    pytest.param(RuntimeError("CUDA out of memory"), id="model-raises"),
    pytest.param(None, id="model-returns-none"),
]


@pytest.mark.parametrize("reply", BAD_OUTPUTS)
def test_bad_output_is_dropped(reply):
    lab, _ = labeler(reply if reply is not None else (lambda p: None))
    result = lab.try_label(ASSUMPTION, CANDIDATE)
    assert result.label is None
    assert result.dropped_reason
    with pytest.raises(DroppedStanceLabel):
        lab.label(ASSUMPTION, CANDIDATE)


def test_dropped_output_keeps_raw_text_for_the_log():
    lab, _ = labeler("nonsense output")
    result = lab.try_label(ASSUMPTION, CANDIDATE)
    assert result.raw_output == "nonsense output"
    assert result.call is not None
    assert result.call.outcome is ModelCallOutcome.INVALID_OUTPUT
    assert result.prompt_version.startswith("sha256:")


@pytest.mark.parametrize("reply", [RuntimeError("CUDA out of memory"), ""])
def test_runtime_error_is_recorded_as_error(reply):
    lab, _ = labeler(reply)
    result = lab.try_label(ASSUMPTION, CANDIDATE)
    assert result.label is None
    assert result.call.outcome is ModelCallOutcome.ERROR
    assert result.call.raw_output == ""


def test_call_numbers_continue_per_run():
    lab, _ = labeler(GOOD, "bad", GOOD)
    ids = [lab.try_label(ASSUMPTION, CANDIDATE).call.id for _ in range(3)]
    assert ids == ["mc:run:fake:1#1", "mc:run:fake:1#2", "mc:run:fake:1#3"]


def test_irrelevant_may_have_empty_quote():
    lab, _ = labeler({"stance": "irrelevant", "quote": "", "rationale": "Other topic."})
    assert lab.label(ASSUMPTION, CANDIDATE).stance is Stance.IRRELEVANT


def test_model_without_run_id_is_dropped():
    lab, model = labeler(GOOD, run_id=None)
    result = lab.try_label(ASSUMPTION, CANDIDATE)
    assert result.label is None and result.call is None
    assert model.prompts == []


def test_missing_signed_prompt_fails_loudly(tmp_path):
    with pytest.raises(PromptMissingError):
        LocalStanceLabeler(FakeModel(GOOD), prompts_dir=tmp_path)


def test_prompt_without_placeholders_is_refused():
    with pytest.raises(ValueError, match="placeholders"):
        LocalStanceLabeler(FakeModel(GOOD), template="label {assumption} please")
