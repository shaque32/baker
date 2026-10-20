"""Speed round 2's draft (eval/probe/stance_v1_1_draft.md) is the signed v1.0 wording in a
different order, so that consecutive model calls share a long prompt prefix. It was not signed.

These tests hold the draft to that: the same lines as v1.0 (whose body is docs/prompts/stance.md
draft v0.1), the fixed instructions before the case data, and a prefix that two calls on the
same assumption share up to the record. The product uses the signed v1.1 (2026-10-14), which
adds {claim}; its labeler refuses this draft, and the speed test times only drafts with v1.1's
slots.

SYNTHETIC. Fake model only.
"""

from __future__ import annotations

import os
import shutil
from collections import Counter
from pathlib import Path

import pytest

from core.audit import stance
from core.audit._llm_json import fill_prompt, prompt_body
from core.db import connect
from core.llm.runtime import FakeModel
from eval import run_pipeline as rp
from eval.probe import time_case

DRAFT = Path("eval/probe/stance_v1_1_draft.md")
V1_0 = Path("docs/prompts/stance.md")  # draft v0.1, signed word for word as v1.0


def _bodies() -> tuple[str, str]:
    """v1.0's body and the reordered draft's."""
    return (
        prompt_body(V1_0.read_text(encoding="utf-8")),
        prompt_body(DRAFT.read_text(encoding="utf-8")),
    )


def test_the_draft_has_the_signed_wording_line_for_line():
    signed, draft = _bodies()
    assert draft != signed
    assert Counter(signed.splitlines()) == Counter(draft.splitlines())


def test_every_fixed_instruction_comes_before_the_case_data():
    _, draft = _bodies()
    first_data = draft.index("{assumption}")
    for heading in (
        "Choose exactly one stance:",
        "Rules for the quote:",
        "Rules for the rationale:",
    ):
        assert draft.index(heading) < first_data
    # Only the data blocks and the one-line JSON reminder follow.
    assert draft.index("{assumption}") < draft.index("{record}") < draft.index("{context}")
    assert draft.rstrip().endswith('"rationale": "<one or two sentences>"}')


def test_two_calls_on_one_assumption_share_everything_before_the_record():
    signed, draft = _bodies()

    def shared(template: str) -> tuple[int, int]:
        a = fill_prompt(template, {"assumption": "A", "record": "first", "context": "c1"})
        b = fill_prompt(template, {"assumption": "A", "record": "second", "context": "c2"})
        return len(os.path.commonprefix([a, b])), a.index("first")

    draft_shared, draft_record_at = shared(draft)
    assert draft_shared == draft_record_at
    assert draft_shared > 4 * shared(signed)[0]


@pytest.fixture
def conn(tmp_path_factory, tmp_path):
    built = tmp_path_factory.mktemp("case") / "case01.db"
    rp.build_case("case01", built).close()  # type: ignore[attr-defined]
    copy = tmp_path / "case.db"
    shutil.copy(built, copy)
    db = connect(copy)
    yield db
    db.close()


def test_the_speed_test_can_time_a_draft_with_v1_1s_slots(conn, tmp_path):
    spec = Path("eval/probe_draft/case01_assumptions.jsonl")
    model = FakeModel(respond=lambda p: '{"stance": "irrelevant", "quote": "", "rationale": "n"}')
    signed = time_case._components(conn, model, spec, False)
    signed_text = (stance.PROMPTS_DIR / stance.PROMPT_FILE).read_text(encoding="utf-8")
    draft_file = tmp_path / "draft.md"
    draft_file.write_text(signed_text.replace("Choose exactly one stance:", "Pick one:"), "utf-8")
    draft = time_case._components(conn, model, spec, False, draft_file)
    assert draft.labeler.template == prompt_body(draft_file.read_text(encoding="utf-8"))
    assert draft.labeler.prompt_version != signed.labeler.prompt_version
    (s_run,), (d_run,) = signed.labeler.model_runs, draft.labeler.model_runs
    assert s_run.prompt_sha256 != d_run.prompt_sha256  # outputs are never reused across prompts
    # The draft goes through the product's wiring: names and the claim slot, as signed.
    assert draft.labeler.claim_text("C02") == signed.labeler.claim_text("C02") is not None
    # Round 2's reordered v1.0 has no {claim}; the product's wiring refuses it.
    with pytest.raises(ValueError, match=r"lacks placeholders: \['claim'\]"):
        time_case._components(conn, model, spec, False, DRAFT)
