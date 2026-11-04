"""The eval's case setup enters the document's names for a phone and a number from case.json,
as the expert would (core/review/actions.name_device and name_account). case04 and case05 are
spent held-out cases: their names are development data for the testability step's dev check,
never a go/no-go.

In the case05 go/no-go, 8 of the 28 claims the step did not convert were stopped by the names
"the SAMSUNG", "the iPHONE", "the ONEPLUS" and "the BURNER", which the setup never entered.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.audit._llm_json import prompt_body
from core.audit.assumption_filler import LocalAssumptionFiller, Reject, _Account
from core.review import account_names, device_names
from eval import run_pipeline
from eval.synthetic import case04_generate, case05_generate
from tests.fake_model import FakeModel

ROOT = Path(__file__).resolve().parents[1]
DRAFT = prompt_body((ROOT / "docs/prompts/assumptions.md").read_text("utf-8"))


@pytest.fixture(scope="module")
def case05(tmp_path_factory) -> sqlite3.Connection:
    conn = run_pipeline.build_case("case05", tmp_path_factory.mktemp("c05") / "case05.db")
    yield conn
    conn.close()


@pytest.mark.parametrize("case", ["case04", "case05"])
def test_case_json_lists_the_names_the_generator_gives(case):
    gen = {"case04": case04_generate, "case05": case05_generate}[case]
    meta = json.loads((ROOT / f"eval/synthetic/{case}/case.json").read_text("utf-8"))
    assert {d["source_id"]: d["names"] for d in meta["devices"] if d["names"]} == gen.PHONE_NAMES
    assert meta["numbers"] == gen.NUMBER_NAMES


def test_case05_setup_enters_each_phones_and_numbers_names(case05):
    assert device_names.logged_names(case05) == {
        "dev:item1": ["the SAMSUNG"],
        "dev:item2": ["the iPHONE"],
        "dev:item3": ["the ONEPLUS"],
    }
    assert account_names.logged_names(case05) == {"+1 (720) 555-0186": ["the BURNER"]}
    holders = account_names.holders(case05, "+1 (720) 555-0186")
    assert holders and all(a.endswith(":+17205550186") for a in holders)
    actors = {
        a
        for (a,) in case05.execute(
            "SELECT actor FROM audit_log WHERE action IN (?, ?)",
            (device_names.ACTION, account_names.ACTION),
        )
    }
    assert actors == {run_pipeline.STIPULATION_ACTOR}


def test_case05_names_resolve_as_the_affidavit_defines_them(case05):
    filler = LocalAssumptionFiller(FakeModel("{}"), case05, template=DRAFT)
    assert filler._device("SAMSUNG") == "dev:item1"
    assert filler._device("the iPHONE") == "dev:item2"
    assert filler._device("ONEPLUS") == "dev:item3"
    odum = filler._person("SUBJECT-3")
    assert filler._person("COURIER") == odum  # the alias is "the COURIER"
    sms = filler._accounts(_Account(as_written="BURNER", app="SMS"), ["dev:item3"], "")
    assert sms == {"acct:item3:SMS:+17205550186"}
    with pytest.raises(Reject, match="not a person"):
        filler._person("the BURNER")
    with pytest.raises(Reject):  # the FENCE names a person, not a number, and is not entered
        filler._accounts(_Account(as_written="FENCE", app="SMS"), ["dev:item3"], "")


def test_case04_setup_enters_the_target_phone_and_the_prepaid(tmp_path):
    conn = run_pipeline.build_case("case04", tmp_path / "case04.db")
    try:
        assert device_names.logged_names(conn) == {"dev:item2": ["the TARGET PHONE"]}
        assert account_names.logged_names(conn) == {"+1 (312) 555-0199": ["the PREPAID"]}
        filler = LocalAssumptionFiller(FakeModel("{}"), conn, template=DRAFT)
        assert filler._device("TARGET PHONE") == "dev:item2"
        assert filler._person("DRIVER") == filler._person("SUBJECT-3")
    finally:
        conn.close()
