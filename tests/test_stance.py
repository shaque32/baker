import hashlib
from pathlib import Path

import pytest

from core.audit._llm_json import PromptMissingError, prompt_body, prompt_version
from core.audit.stance import (
    NO_CLAIM,
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

SIGNED = prompt_body(
    (Path(__file__).parents[1] / "core/audit/prompts/stance.md").read_text("utf-8")
)
DRAFT = SIGNED  # the tests below fill the signed prompt (v1.1)
CLOUD = prompt_body(
    (Path(__file__).parents[1] / "core/audit/prompts/stance_cloud.md").read_text("utf-8")
)

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


def test_prompt_with_a_slot_the_labeler_does_not_fill_is_refused():
    """fill_prompt leaves an unknown slot in place, so the labeler refuses a prompt with one
    instead of sending the model a bare placeholder."""
    with_slot = DRAFT.replace("{assumption}", "{names}\n{assumption}", 1)
    with pytest.raises(ValueError, match=r"does not fill: \['names'\]"):
        LocalStanceLabeler(FakeModel(GOOD), template=with_slot)


def test_a_prompt_without_the_claim_slot_is_refused():
    """v1.0 had no {claim}; the labeler fills v1.1 only, so v1.0 is never sent by mistake."""
    v10 = DRAFT.replace("[CLAIM START]\n{claim}\n[CLAIM END]\n", "")
    with pytest.raises(ValueError, match=r"lacks placeholders: \['claim'\]"):
        LocalStanceLabeler(FakeModel(GOOD), template=v10)


def _with_template(a, template_id: str):
    return a.model_copy(update={"template_id": template_id})


@pytest.mark.parametrize("template_id", ["meaning", "role", "event"])
def test_the_claim_is_shown_for_templates_that_say_the_claim(template_id):
    model = FakeModel(GOOD)
    lab = LocalStanceLabeler(model, template=SIGNED, claim_text={"c1": "Petrov ran the crew."}.get)
    lab.label(_with_template(ASSUMPTION, template_id), CANDIDATE)
    assert "[CLAIM START]\nPetrov ran the crew.\n[CLAIM END]" in model.prompts[0]


@pytest.mark.parametrize("template_id", ["sender", "record_time", "same_account", "test_meaning"])
def test_other_templates_show_no_claim(template_id):
    model = FakeModel(GOOD)
    lab = LocalStanceLabeler(model, template=SIGNED, claim_text={"c1": "Petrov ran the crew."}.get)
    lab.label(_with_template(ASSUMPTION, template_id), CANDIDATE)
    assert "Petrov ran the crew." not in model.prompts[0]
    assert f"[CLAIM START]\n{NO_CLAIM}\n[CLAIM END]" in model.prompts[0]


def test_a_claim_with_no_text_shows_no_claim():
    model = FakeModel(GOOD)
    lab = LocalStanceLabeler(model, template=SIGNED, claim_text=lambda cid: None)
    lab.label(_with_template(ASSUMPTION, "meaning"), CANDIDATE)
    assert f"[CLAIM START]\n{NO_CLAIM}\n[CLAIM END]" in model.prompts[0]


def test_claim_text_cannot_inject_placeholders():
    model = FakeModel(GOOD)
    lab = LocalStanceLabeler(model, template=SIGNED, claim_text=lambda cid: "see {record}")
    lab.label(_with_template(ASSUMPTION, "meaning"), CANDIDATE)
    assert "[CLAIM START]\nsee {record}\n[CLAIM END]" in model.prompts[0]


def test_no_claim_matches_the_probe_runner():
    from eval.probe import prompts

    assert NO_CLAIM == prompts.NO_CLAIM


def test_the_assumption_renderer_is_used():
    model = FakeModel(GOOD)
    lab = LocalStanceLabeler(model, template=SIGNED, render_assumption=lambda a: "READABLE")
    lab.label(ASSUMPTION, CANDIDATE)
    assert "Assumption:\nREADABLE\n" in model.prompts[0]
    assert ASSUMPTION.text not in model.prompts[0]


# v1.2 (signed 2026-10-15, "Audit our model scoring") is v1.1 with these two sentences in the
# "contradicts" entry, after "no contact between").", and nothing else. Arsh chose on 2026-10-19
# ("Opus only") to give it to a cloud model only, as its own file; the local model keeps v1.1.
TOLD_FRAME = (
    "Likewise, when the assumption is that someone told, wrote or asked something, a message of"
    " theirs saying the opposite shows only what that message says; another message could still"
    ' have said it, so it is "complicates". A denial that names no time ("i never got it") covers'
    " only the time before it was sent: it rules out an assumption dated before the message and"
    " leaves an undated one open."
)
# SHA-256 of the body the told-frame bench runs sent to Opus 5.5 on 2026-10-15
# (stance_v1_1_told_frame_draft.md, file sha256 ba603d12..., in the shared cloud-bench folder),
# so the signed text is the tested text.
SIGNED_V1_2_BODY_SHA256 = "2863d8dbf66960f6de732ccb136c5ff29ceff0f202924a71ef58c56ab93bdc95"
# The version every local stance run has recorded since v1.1 was signed (2026-10-14).
SIGNED_V1_1_VERSION = "sha256:4c35f1cf01b0b227"


def test_the_signed_prompt_is_v1_1():
    head = (Path(__file__).parents[1] / "core/audit/prompts/stance.md").read_text("utf-8")
    assert "\nv1.1, signed by Arsh on 2026-10-14" in head
    assert prompt_version(SIGNED) == SIGNED_V1_1_VERSION
    for part in ("[CLAIM START]", "How names read:", "with no unstated fact needed",
                 "the same words on another date or from another"):  # fmt: skip
        assert part in SIGNED


def test_the_cloud_prompt_is_v1_2():
    head = (Path(__file__).parents[1] / "core/audit/prompts/stance_cloud.md").read_text("utf-8")
    assert "\nv1.2, signed by Arsh on 2026-10-15" in head
    assert hashlib.sha256(CLOUD.encode("utf-8")).hexdigest() == SIGNED_V1_2_BODY_SHA256


def test_v1_2_is_v1_1_with_the_told_frame_sentences_only():
    words = " ".join(CLOUD.split())
    assert words.count(TOLD_FRAME) == 1
    assert words.replace(TOLD_FRAME + " ", "") == " ".join(SIGNED.split())
    # In the "contradicts" entry, between the exclusion rule and the closing "more likely" line.
    entry = words.split('- "contradicts":', 1)[1].split('- "complicates":', 1)[0]
    assert entry.index('"no contact between"). ') < entry.index(TOLD_FRAME)
    assert entry.index(TOLD_FRAME) < entry.index("A record that only makes another reading")


def test_only_the_named_message_can_contradict_a_one_message_assumption():
    from core.audit.assumptions import instantiate
    from core.audit.stance import subject_stance

    p = {"quoted_text": "need 2 more by friday", "person_ids": ["person:petrov"]}
    sender = instantiate("C05", "sender", p, True)
    other, named = "customer wants it by friday", "ok need 2 more by friday!"
    assert subject_stance(sender, other, Stance.CONTRADICTS) == Stance.COMPLICATES
    assert subject_stance(sender, named, Stance.CONTRADICTS) == Stance.CONTRADICTS
    for s in (Stance.SUPPORTS, Stance.COMPLICATES, Stance.IRRELEVANT):
        assert subject_stance(sender, other, s) == s
    # Word-aligned like the checks: "need 2 more by friday" is not inside "need 2 more by fridays".
    assert (
        subject_stance(sender, "need 2 more by fridays", Stance.CONTRADICTS) == Stance.COMPLICATES
    )
    # Other templates are left alone, e.g. a contact entry with another name for the number.
    contact = instantiate(
        "C01",
        "contact_entry",
        {"device_ids": ["dev:item1"], "quoted_text": "Marc Garage", "account_ids": ["acct:x"]},
        True,
    )
    assert subject_stance(contact, "Mike +12125550122", Stance.CONTRADICTS) == Stance.CONTRADICTS
