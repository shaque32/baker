from pathlib import Path

from core.audit._llm_json import prompt_body
from core.claims.extract import CLAIMS_SCHEMA, LocalClaimExtractor
from core.contracts import ClaimExtractor, ClaimStatus, ClaimType, GovDocParagraph
from tests.fake_model import FakeModel

DRAFT = prompt_body((Path(__file__).parents[1] / "docs/prompts/claims.md").read_text("utf-8"))

PARA = GovDocParagraph(
    id="para:gd1:5",
    govdoc_id="gd1",
    page=1,
    para_no=5,
    label="5",
    char_start=0,
    char_end=120,
    text="On March 5, 2026, the user of Item 1 sent 14 messages to Marc Garage. "
    "None of them mention money.",
)


def extractor(*replies, **kw):
    model = FakeModel(*replies, **kw)
    return LocalClaimExtractor(model, template=DRAFT), model


def test_conforms_to_contract_protocol():
    ex, _ = extractor({"claims": []})
    _: ClaimExtractor = ex


def test_verbatim_spans_kept_others_dropped():
    reply = {
        "claims": [
            {
                "text": "The user of Item 1 sent 14 messages to Marc Garage on March 5, 2026.",
                "claim_type": "count",
                "span": "the user of Item 1 sent 14 messages to Marc Garage",
            },
            {
                "text": "None of the messages mention money.",
                "claim_type": "absence",
                "span": "None of them mention cash.",  # not verbatim
            },
            {"text": "Extra", "claim_type": "guilt", "span": "None of them"},  # bad type
            {"text": "No span", "claim_type": "event"},  # missing field
        ]
    }
    ex, model = extractor(reply)
    claims = ex.extract([PARA])
    assert [c.claim_type for c in claims] == [ClaimType.COUNT]
    c = claims[0]
    assert c.id == "claim:para:gd1:5:1"
    assert c.paragraph_id == PARA.id
    assert c.status is ClaimStatus.PROPOSED
    assert c.model_run_id == "run:fake:1"
    assert [d.index for d in ex.drops] == [1, 2, 3]
    assert model.schemas[0] is CLAIMS_SCHEMA
    assert PARA.text in model.prompts[0]


def test_whole_output_dropped_is_recorded():
    ex, _ = extractor("not json")
    assert ex.extract([PARA]) == []
    assert ex.drops[0].index is None
    (call,) = ex.recorder.calls
    assert call.raw_output == "not json" and ex.drops[0].model_call_id == call.id


def test_duplicates_dropped_and_empty_paragraph_skipped():
    item = {"text": "Claim.", "claim_type": "event", "span": "None of them"}
    ex, model = extractor({"claims": [item, item]})
    empty = PARA.model_copy(update={"id": "para:gd1:6", "text": "  "})
    assert len(ex.extract([PARA, empty])) == 1
    assert len(model.prompts) == 1
    assert ex.drops[0].reason == "duplicate claim"


def test_claim_with_invented_number_is_dropped():
    reply = {
        "claims": [
            {
                "text": "The user of Item 1 sent 15 messages to Marc Garage.",
                "claim_type": "count",
                "span": "the user of Item 1 sent 14 messages to Marc Garage",
            },
            {"text": "Blank span.", "claim_type": "event", "span": "   "},
        ]
    }
    ex, _ = extractor(reply)
    assert ex.extract([PARA]) == []
    assert "numbers not in paragraph" in ex.drops[0].reason
    assert ex.drops[1].reason == "span not verbatim in paragraph"


def test_span_across_a_pdf_line_break_is_kept():
    from core.claims.extract import span_in

    para = '6. PETROV wrote to @northstar: "need 2 more by friday". The package in\nthe message'
    assert span_in("The package in the message", para)  # the model wrote a space for the break
    assert span_in("The package in\nthe message", para)
    assert not span_in("The package is in the message", para)  # words still exact
    assert not span_in("the package in the message", para)  # case still exact
    assert not span_in("   ", para)
