"""The assumption filler on what the local model really answered, replayed.

eval/fixtures/mac_run_2026-10-12/assumption_filler.json holds the 27 claims the 14B model
proposed for synthetic case01 on Arsh's Mac (the first full case in the browser) and the
filler's raw output for each. In that run only 5 claims got any assumption; the other 22 were
never tested and the screen showed them as a plain "Unproven". Code now reads the dates the
claim states itself (stated_windows) instead of trusting the model's arithmetic, and every
untested claim keeps the reasons it was refused. This test keeps both from slipping back.
"""

import json
import sqlite3
from pathlib import Path

import pytest

from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import LocalAssumptionFiller
from core.audit.assumptions import TemplateAssumptionBuilder
from core.contracts import Claim, ClaimStatus, ClaimType
from eval.synthetic.generate import generate
from tests.checks.helpers import stipulate
from tests.fake_model import FakeModel

ROOT = Path(__file__).parents[1]
DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))
RUN = json.loads(
    (ROOT / "eval/fixtures/mac_run_2026-10-12/assumption_filler.json").read_text("utf-8")
)
TESTED_IN_THE_RUN = 5  # what the Mac run itself got, before code read the stated dates
TESTED_NOW = 10


def _name(c: dict) -> str:
    return f"¶{c['paragraph_label']}.{c['claim_no']}"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    db = out / "case01.db"
    generate(out, db)
    conn = sqlite3.connect(db)
    stipulate(conn, "person:petrov", "Daniel Petrov", "dev:item1")
    stipulate(conn, "person:reyes", "Marcus Reyes", "dev:item2")
    conn.execute("PRAGMA foreign_keys = OFF")
    paragraphs = {c["paragraph_label"]: c["paragraph"] for c in RUN["claims"]}
    for label, text in paragraphs.items():
        conn.execute(
            "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start,"
            " char_end, text) VALUES (?, 'gd', 1, ?, ?, 0, ?, ?)",
            (f"para:{label}", int(label), label, len(text), text),
        )
    answers = {c["text"]: c["model_output"] for c in RUN["claims"]}

    def reply(prompt: str) -> str:
        for text, output in answers.items():
            if f"[CLAIM START]\n{text}\n[CLAIM END]" in prompt:
                return output
        raise AssertionError("a prompt for a claim the run never saw")

    builder = TemplateAssumptionBuilder(
        LocalAssumptionFiller(FakeModel(reply), conn, template=DRAFT)
    )
    result = {}
    for c in RUN["claims"]:
        claim = Claim(
            id=f"claim:para:{c['paragraph_label']}:{c['claim_no']}",
            paragraph_id=f"para:{c['paragraph_label']}",
            text=c["text"],
            claim_type=ClaimType(c["claim_type"]),
            status=ClaimStatus.ACCEPTED,
        )
        result[_name(c)] = (builder.build(claim), builder.refused(claim.id))
    yield result
    conn.close()


def test_more_claims_are_tested_than_in_the_run(built):
    tested = sorted(n for n, (a, _) in built.items() if any(x.is_core for x in a))
    assert len(built) == 27
    assert len(tested) >= TESTED_NOW > TESTED_IN_THE_RUN, tested


def test_every_untested_claim_keeps_why(built):
    for name, (assumptions, refused) in built.items():
        if not assumptions:
            assert refused, f"{name} got no assumption and no reason"


def test_dated_quotes_are_timed_on_the_day_the_claim_states(built):
    # ¶6.1 "On March 12, 2026, PETROV wrote to @northstar ..." (gold C05) had no time range.
    (rt,) = [a for a in built["¶6.1"][0] if a.template_id == "record_time"]
    assert rt.params.quoted_text == "need 2 more by friday"
    assert rt.params.window.raw == "On March 12, 2026"
    assert rt.params.window.start_utc.isoformat() == "2026-03-12T04:00:00+00:00"
    # ¶11.1 "no contact ... between March 20 and March 23, 2026" (gold C14): the model ended
    # its range on March 22; the claim's own words end it at the close of March 23.
    (nc,) = built["¶11.1"][0]
    assert nc.template_id == "no_contact"
    assert nc.params.window.end_utc.isoformat() == "2026-03-24T03:59:59.999999+00:00"


def test_names_not_in_the_case_stay_refused(built):
    # ALEXANDER SOKOLOV is no person the expert created: identity is never guessed.
    assumptions, refused = built["¶14.1"]
    assert assumptions == []
    assert any("matches no person" in r for r in refused)
