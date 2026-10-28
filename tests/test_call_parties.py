"""A call the model named without its parties gets them from the claim's own words, on the one
app the claim names, and the time check then searches that app's calls only. Synthetic case01
with two made-up app calls; made-up wording only.
"""

import json
import sqlite3

import pytest

from core.audit.assumption_filler import LocalAssumptionFiller, Reject
from core.audit.assumptions import TemplateAssumptionBuilder
from core.audit.checks import CHECKS
from core.contracts import CheckOutcome, ClaimType
from eval.synthetic.generate import generate
from tests.checks.helpers import stipulate
from tests.fake_model import FakeModel
from tests.test_affidavit_wording import W, claim, filler, proposal

PETROV, REYES = "person:petrov", "person:reyes"
PETROV_WA = "acct:item1:WhatsApp:12125550111@s.whatsapp.net"
MARC_WA = "acct:item1:WhatsApp:12125550122@s.whatsapp.net"
# One account as each phone recorded it: one key, so one party.
MARC_WA_BOTH = [MARC_WA, "acct:item2:WhatsApp:12125550122@s.whatsapp.net"]
MARCUS_TG_BOTH = ["acct:item1:Telegram:7001002", "acct:item2:Telegram:7001002"]
WHEN = W("On March 9, 2026", "2026-03-09T00:00", "2026-03-10T00:00")


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    generate(out, out / "case01.db")
    c = sqlite3.connect(out / "case01.db")
    stipulate(c, PETROV, "Daniel Petrov", "dev:item1")
    stipulate(c, REYES, "Marcus Reyes", "dev:item2")
    c.execute("PRAGMA foreign_keys = OFF")
    # A WhatsApp call from PETROV to Marc's number on March 9, and a Telegram call PETROV and
    # REYES had the same evening.
    rows = [
        ("call:wa:1", "WhatsApp", PETROV_WA, MARC_WA, "2026-03-09T23:00:00Z"),
        ("call:tg:1", "Telegram", "acct:item1:Telegram:7001001", "acct:item1:Telegram:7001002",
         "2026-03-09T23:30:00Z"),
    ]  # fmt: skip
    for cid, app, frm, to, ts in rows:
        c.execute(
            "INSERT INTO calls VALUES (?, 'item1', ?, 'dev:item1', ?, ?, ?, 'outgoing', ?, 0,"
            " NULL, 60, 0)",
            (cid, cid, app, frm, to, ts),
        )
    yield c
    c.close()


def build(conn, text: str, kind: ClaimType = ClaimType.COMMUNICATION, **change):
    answer = {**proposal(people=[], quoted_text="", window=WHEN).model_dump(), **change}
    f = LocalAssumptionFiller(FakeModel(json.dumps({"assumptions": [answer]})), conn,
                              template="{claim} {paragraph} {templates} {channels}")  # fmt: skip
    assumptions = TemplateAssumptionBuilder(f).build(claim(text, kind))
    return assumptions, f


@pytest.mark.parametrize(
    ("text", "people", "accounts", "app"),
    [
        ("On March 9, 2026, PETROV placed a WhatsApp call to (212) 555-0122.", [PETROV],
         MARC_WA_BOTH, "WhatsApp"),
        ("On March 9, 2026, (212) 555-0122 had a WhatsApp call with PETROV.", [PETROV],
         MARC_WA_BOTH, "WhatsApp"),
        ("On March 9, 2026, Daniel Petrov placed a Telegram call to Marcus Reyes.",
         [PETROV, REYES], [], "Telegram"),
        # A quoted display name of exactly one account on the app.
        ('On March 9, 2026, PETROV placed a Telegram call to "Marcus R".', [PETROV],
         MARCUS_TG_BOTH, "Telegram"),
        # An identifier written as it is recorded.
        ("On March 9, 2026, the Telegram user 7001002 called PETROV.", [PETROV],
         MARCUS_TG_BOTH, "Telegram"),
        # One account and the phone it called.
        ("On March 9, 2026, the Telegram user 7001002 called Item 1.", [], MARCUS_TG_BOTH,
         "Telegram"),
    ],
)  # fmt: skip
def test_a_calls_parties_come_from_the_claim(conn, text, people, accounts, app):
    (a,), f = build(conn, text, channels=["call"])
    assert not f.drops, f.drops
    assert list(a.params.person_ids) == people
    assert set(a.params.account_ids) == set(accounts)
    assert set(a.params.channels) == {"call", app}


@pytest.mark.parametrize(
    ("text", "why"),
    [
        # No app, or two: the words alone never pick the app.
        ("On March 9, 2026, PETROV called (212) 555-0122.", "names 0 apps"),
        ("On March 9, 2026, PETROV placed a WhatsApp or Telegram call to REYES.", "names 2 apps"),
        # An app's name inside an address names no app.
        ("On March 9, 2026, PETROV placed a call to telegram.user@example.com.", "names 0 apps"),
        # A party that is not one account refuses every party.
        ('On March 9, 2026, PETROV placed a Telegram call to "Nobody Known".', "not one account"),
        ("On March 9, 2026, a Telegram call was placed.", "names no party"),
        # Baker Eval on #164: a name that is someone's, or someone acted for or spoken of, or
        # that sits in another clause, is no party.
        ("On March 9, 2026, PETROV's lawyer placed a Telegram call to REYES.",
         "may not be a party"),
        ("On March 9, 2026, PETROV’s phone placed a WhatsApp call to (212) 555-0122.",
         "may not be a party"),
        ("On March 9, 2026, REYES placed a Telegram call on behalf of PETROV.",
         "may not be a party"),
        ("On March 9, 2026, REYES placed a Telegram call to Marcus about PETROV.",
         "may not be a party"),
        ("On March 9, 2026, after speaking with PETROV, REYES placed a Telegram call.",
         "joins another clause"),
        ("On March 9, 2026, REYES placed a Telegram call while PETROV waited.",
         "joins another clause"),
        # Codex on #164: two parties written as accounts would be read as one, either of them.
        ("On March 9, 2026, the Telegram user 7001001 called the Telegram user 7001002.",
         "two parties as accounts"),
        # Codex on #164: a party the case does not know, or only one side of the call.
        ("On March 9, 2026, PETROV placed a Telegram call to @unknownuser.", "not one account"),
        ("On March 9, 2026, PETROV placed a Telegram call to jon@example.org.",
         "not one account"),
        ("On March 9, 2026, PETROV placed a Telegram call to 7009999.", "not one account"),
        ("On March 9, 2026, PETROV placed a Telegram call to Jonathan.", "one side of the call"),
        ("On March 9, 2026, on Item 1, PETROV placed a Telegram call to Jonathan.",
         "one side of the call"),
    ],
)  # fmt: skip
def test_a_call_whose_parties_are_not_plain_is_refused(conn, text, why):
    assumptions, f = build(conn, text, channels=["call"])
    assert assumptions == []
    assert any(why in d.reason for d in f.drops), f.drops


def test_the_phone_the_claim_writes_scopes_the_call(conn):
    # Codex on #164: the phone counted as the call's other side is kept as its scope.
    text = "On March 9, 2026, the Telegram user 7001002 called Item 1."
    (a,), _ = build(conn, text, channels=["call"])
    assert list(a.params.device_ids) == ["dev:item1"]


def test_the_models_other_app_is_refused(conn):
    text = "On March 9, 2026, PETROV placed a WhatsApp call to (212) 555-0122."
    assumptions, f = build(conn, text, channels=["call", "Telegram"])
    assert assumptions == []


def test_an_app_without_call_gets_call(conn):
    # The model wrote the app but not "call" (a "FaceTime call" proposed on FaceTime).
    text = "On March 9, 2026, PETROV placed a WhatsApp call to (212) 555-0122."
    (a,), f = build(conn, text, channels=["WhatsApp"])
    assert set(a.params.channels) == {"call", "WhatsApp"}


def test_a_model_party_is_kept(conn):
    # Code fills only a call the model left without parties.
    text = "On March 9, 2026, PETROV placed a WhatsApp call to (212) 555-0122."
    (a,), _ = build(conn, text, channels=["call"], people=["PETROV"])
    assert a.params.account_ids == () and set(a.params.channels) == {"call"}


def test_the_time_check_searches_the_named_apps_calls_only(conn):
    text = "On March 9, 2026, PETROV placed a WhatsApp call to (212) 555-0122."
    (a,), _ = build(conn, text, channels=["call"])
    r = CHECKS["time"].run(a, conn)
    assert r.outcome is CheckOutcome.PASS and list(r.record_ids) == ["call:wa:1"]
    # The same parties on Telegram: the WhatsApp call does not count.
    tg = a.model_copy(
        update={"params": a.params.model_copy(update={"channels": ("Telegram", "call")})}
    )
    assert CHECKS["time"].run(tg, conn).outcome is CheckOutcome.INCONCLUSIVE
    # "call" alone admits every app's calls, as before.
    any_app = a.model_copy(update={"params": a.params.model_copy(update={"channels": ("call",)})})
    assert CHECKS["time"].run(any_app, conn).outcome is CheckOutcome.PASS


def test_call_app_reads_only_app_names(conn):
    f = filler(conn)
    assert f._call_app("a WhatsApp call", []) == "WhatsApp"
    with pytest.raises(Reject):
        f._call_app("the phone call", [])  # a phone app is never picked by the words
