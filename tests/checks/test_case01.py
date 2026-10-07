"""Deterministic checks on synthetic case01: one test per planted trap they must not fall for.

Expected outcomes follow Arsh's gold verdicts (eval/gold/case01/gold.jsonl). A check result is
not a verdict; these tests only pin what each check finds.
"""

import sqlite3
from datetime import datetime as D

import pytest

from core.contracts import CheckOutcome
from eval.synthetic.generate import generate
from tests.checks.helpers import check, stipulate, text, window

PETROV, REYES = "person:petrov", "person:reyes"
NORTHSTAR = ("acct:item1:Telegram:5551234", "acct:item2:Telegram:5551234")
MARC_0122 = ("acct:item1:Phone:+12125550122",)


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    db = out / "case01.db"
    generate(out, db)
    c = sqlite3.connect(db)
    stipulate(c, PETROV, "Daniel Petrov", "dev:item1")
    stipulate(c, REYES, "Marcus Reyes", "dev:item2")
    yield c
    c.close()


def test_c01_contact_entry(conn) -> None:
    r = check(conn, "contact_entry", device_ids=["dev:item1"], quoted_text="Marc Garage",
              account_ids=MARC_0122)  # fmt: skip
    assert r.outcome is CheckOutcome.PASS
    assert r.record_ids == ("contact:item1:Contacts!3#1",)


def test_c01_missing_contact_is_not_a_fail(conn) -> None:
    r = check(conn, "contact_entry", device_ids=["dev:item1"], quoted_text="Marc Garage",
              account_ids=["acct:item1:SMS:+12125550144"])  # fmt: skip
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "curated report" in r.detail


def test_c02_handle_change_is_one_telegram_account(conn) -> None:
    r = check(conn, "same_account", channels=["Telegram"], handles=["@alex92", "@northstar"])
    assert r.outcome is CheckOutcome.PASS
    assert "telegram 5551234" in r.detail
    assert "thr:item1:Telegram:7" in r.record_ids


def test_c03_count_follows_the_user_id_across_the_handle_change(conn) -> None:
    w = window(D(2026, 3, 10), D(2026, 4, 1), "From March 10 through March 31, 2026")
    common = dict(device_ids=["dev:item1"], person_ids=[PETROV], account_ids=NORTHSTAR,
                  channels=["Telegram"], window=w)  # fmt: skip
    r = check(conn, "message_count", expected_count=13, count_op="eq", **common)
    assert r.outcome is CheckOutcome.PASS
    assert len(r.record_ids) == 13
    assert r.record_ids[0] == "msg:item1:Chats!946" and r.source_ids == ("item1",)
    # Over-claiming is contradicted by the rows; under-claiming is not.
    assert check(conn, "message_count", expected_count=12, count_op="eq", **common).outcome is (
        CheckOutcome.FAIL
    )
    assert check(conn, "message_count", expected_count=14, count_op="eq", **common).outcome is (
        CheckOutcome.INCONCLUSIVE
    )
    assert check(conn, "message_count", expected_count=10, count_op="ge", **common).outcome is (
        CheckOutcome.PASS
    )
    # "At most" cannot pass on a curated report: it may have left messages out.
    assert check(conn, "message_count", expected_count=20, count_op="le", **common).outcome is (
        CheckOutcome.INCONCLUSIVE
    )


def test_c04_contact_with_the_account_long_before_march_12(conn) -> None:
    w = window(D(2026, 1, 1), D(2026, 3, 12), "before March 12, 2026")
    r = check(conn, "no_contact", person_ids=[PETROV], account_ids=NORTHSTAR, window=w)
    assert r.outcome is CheckOutcome.FAIL
    assert "msg:item1:Chats!938" in r.record_ids
    assert "2026-02-20 19:02:11 EST" in r.detail  # printed 2/21 in UTC


def test_c05_printed_next_day_is_still_march_12_on_the_phone(conn) -> None:
    w = window(D(2026, 3, 12), D(2026, 3, 13), "On March 12, 2026")
    r = check(
        conn, "record_time", quoted_text="need 2 more by friday", person_ids=[PETROV], window=w
    )
    assert r.outcome is CheckOutcome.PASS
    assert "2026-03-12 20:03:27 EDT (printed 3/13/2026 12:03:27 AM(UTC+0))" in r.detail
    s = check(conn, "sender", quoted_text="need 2 more by friday", person_ids=[PETROV])
    assert s.outcome is CheckOutcome.PASS
    assert s.record_ids == ("msg:item1:Chats!948",)


def test_c05_wrong_sender_fails(conn) -> None:
    r = check(conn, "sender", quoted_text="need 2 more by friday", account_ids=NORTHSTAR)
    assert r.outcome is CheckOutcome.FAIL


def test_c09_call_time_after_the_dst_change(conn) -> None:
    w = window(D(2026, 3, 9, 19, 50), D(2026, 3, 9, 20, 6), "At about 7:58 p.m. on March 9, 2026")
    r = check(conn, "record_time", channels=["call"], person_ids=[PETROV], account_ids=MARC_0122,
              device_ids=["dev:item1"], window=w)  # fmt: skip
    assert r.outcome is CheckOutcome.PASS
    assert r.record_ids == ("call:item1:Call Log!9",)
    assert "2026-03-09 19:58:02 EDT" in r.detail


def test_calls_outside_the_window_are_never_a_fail(conn) -> None:
    w = window(D(2026, 3, 9, 3, 0), D(2026, 3, 9, 3, 5), "3 a.m. on March 9")
    r = check(conn, "record_time", channels=["call"], person_ids=[PETROV], account_ids=MARC_0122,
              device_ids=["dev:item1"], window=w)  # fmt: skip
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "may be other calls" in r.detail


def test_c10_printed_utc_time_is_not_the_phones_time(conn) -> None:
    w = window(D(2026, 3, 5, 2, 31), D(2026, 3, 5, 2, 32), "At 2:31 a.m. on March 5, 2026")
    r = check(conn, "record_time", quoted_text="its done", person_ids=[PETROV, REYES], window=w)
    assert r.outcome is CheckOutcome.FAIL
    assert set(r.record_ids) == {"msg:item1:Chats!1011", "msg:item2:Chats!903"}
    assert "2026-03-04 21:31:00 EST" in r.detail


def test_window_stated_in_utc_matches_the_printed_time(conn) -> None:
    w = window(D(2026, 3, 5, 2, 31), D(2026, 3, 5, 2, 32), "02:31 UTC", tz="UTC")
    r = check(conn, "record_time", quoted_text="its done", device_ids=["dev:item1"], window=w)
    assert r.outcome is CheckOutcome.PASS
    assert "phone is set to America/New_York, not UTC" in r.detail


def test_c11_message_came_before_the_1005_call(conn) -> None:
    # "After the 10:05 p.m. call" is a window on the message that starts at 10:05 p.m.
    w = window(D(2026, 3, 14, 22, 5), D(2026, 3, 15, 6, 0), "after the 10:05 p.m. call")
    r = check(conn, "record_time", quoted_text="move it tonight", person_ids=[PETROV], window=w)
    assert r.outcome is CheckOutcome.FAIL
    assert "2026-03-14 21:50:20 EDT" in r.detail


def test_c14_contact_inside_the_gap_on_sms_telegram_and_calls(conn) -> None:
    w = window(D(2026, 3, 20), D(2026, 3, 24), "between March 20 and March 23, 2026")
    r = check(conn, "no_contact", person_ids=[PETROV, REYES], window=w)
    assert r.outcome is CheckOutcome.FAIL
    for rid in ("msg:item1:Chats!1020", "msg:item1:Chats!1031", "call:item1:Call Log!16",
                "msg:item2:Chats!923"):  # fmt: skip
        assert rid in r.record_ids


def test_c14_whatsapp_silence_on_curated_reports_proves_nothing(conn) -> None:
    w = window(D(2026, 3, 20), D(2026, 3, 24), "between March 20 and March 23, 2026")
    r = check(conn, "no_contact", person_ids=[PETROV, REYES], channels=["WhatsApp"], window=w)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "curated report" in r.detail and "Not found does not mean" in r.detail
    assert r.source_ids == ("item1", "item2")
    # The last WhatsApp message before the gap prints 3/20 in UTC but is Mar 19 on the phone.
    assert r.record_ids == ()


def test_c16_shared_account_check_names_the_account_not_the_person(conn) -> None:
    r = check(conn, "sender", quoted_text="got the money, come get it",
              account_ids=["acct:item1:Instagram:dp_garage"])  # fmt: skip
    assert r.outcome is CheckOutcome.PASS
    assert "person:" not in text(r)


def test_c19_a_phone_contact_is_not_read_as_a_telegram_user(conn) -> None:
    # "Alex" is a saved phone number. Contacts do not say which app an entry is for, so the
    # check must not invent a Telegram account for it, nor call the two different.
    r = check(conn, "same_account", channels=["Telegram"], handles=["@northstar", "Alex"])
    assert r.outcome is CheckOutcome.INCONCLUSIVE
