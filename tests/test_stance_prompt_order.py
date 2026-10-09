"""The stance prompt v1.1 draft (eval/probe/stance_v1_1_draft.md) is the signed v1.0 wording in
a different order, so that consecutive model calls share a long prompt prefix.

These tests hold the draft to that: the same lines, the fixed instructions before the case
data, and a prefix that two calls on the same assumption share up to the record. The product
keeps using the signed core/audit/prompts/stance.md until Arsh signs the draft.

SYNTHETIC. Fake model only.
"""

from __future__ import annotations

import os
import shutil
from collections import Counter
from pathlib import Path

import pytest

from core.audit import stance
from core.audit._llm_json import fill_prompt, load_prompt, prompt_body
from core.db import connect
from core.llm.runtime import FakeModel
from eval import run_pipeline as rp
from eval.probe import time_case

DRAFT = Path("eval/probe/stance_v1_1_draft.md")


def _bodies() -> tuple[str, str]:
    return load_prompt(stance.PROMPT_FILE), prompt_body(DRAFT.read_text(encoding="utf-8"))


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


def test_the_speed_test_can_time_the_draft(conn):
    spec = Path("eval/probe_draft/case01_assumptions.jsonl")
    model = FakeModel(respond=lambda p: '{"stance": "irrelevant", "quote": "", "rationale": "n"}')
    signed = time_case._components(conn, model, spec, False)
    draft = time_case._components(conn, model, spec, False, DRAFT)
    assert draft.labeler.template == _bodies()[1]
    assert draft.labeler.prompt_version != signed.labeler.prompt_version
    (s_run,), (d_run,) = signed.labeler.model_runs, draft.labeler.model_runs
    assert s_run.prompt_sha256 != d_run.prompt_sha256  # outputs are never reused across prompts
