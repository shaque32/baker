"""Baker-form item formats match what the product stores and shows. SYNTHETIC values only."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime

import pytest

from core.audit import context, invariants
from core.audit.assumptions import instantiate
from core.db import apply_schema
from core.enrich.local_time import format_local, parse_utc
from core.ingest.cellebrite_common import DateOrder, parse_time
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import local_str

TZ = "America/Chicago"
OWNER = ("Telegram", "5550147")
OTHER = ("Telegram", "5550163")
NUMBER_A, NUMBER_B = "+13125550161", "+13125550188"
UTC_AT = datetime(2026, 5, 3, 2, 10, 44, tzinfo=UTC)  # 9:10:44 p.m. CDT on May 2


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    apply_schema(c)
    c.execute(
        "INSERT INTO sources VALUES ('item1', 'cellebrite_excel', 'curated_report', 'logical',"
        " 'item1.xlsx', 'x', NULL, NULL, NULL, '2026-05-10T00:00:00Z')"
    )
    c.execute(
        "INSERT INTO devices VALUES ('dev:item1', 'item1', 'Device', 'Item 1', NULL, NULL, ?)",
        (TZ,),
    )
    rows = [
        (bf.account_id(1, *OWNER), "dev:item1", *OWNER),
        (bf.account_id(1, *OTHER), None, *OTHER),
        (bf.account_id(1, "Phone", NUMBER_A), "dev:item1", "Phone", NUMBER_A),
        (bf.account_id(1, "Phone", NUMBER_B), None, "Phone", NUMBER_B),
    ]
    for aid, dev, app, ident in rows:
        c.execute(
            "INSERT INTO accounts VALUES (?, 'item1', 'Accounts:1', ?, ?, ?, NULL)",
            (aid, dev, app, ident),
        )
    c.execute(
        "INSERT INTO threads VALUES ('thr:item1:Telegram:1', 'item1', 'Chats:1', 'dev:item1',"
        " 'Telegram', NULL)"
    )
    stamp = UTC_AT.strftime("%Y-%m-%dT%H:%M:%SZ")
    c.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, ts_offset_min, ts_raw, body) VALUES ('msg:item1:1', 'item1', 'Chats:1:1',"
        " 'thr:item1:Telegram:1', ?, 'incoming', ?, 0, ?, 'gate code 1190')",
        (bf.account_id(1, *OTHER), stamp, bf.report_time(UTC_AT)),
    )
    c.execute(
        "INSERT INTO calls VALUES ('call:item1:Calls:7', 'item1', 'Calls:7', 'dev:item1', 'Phone',"
        " ?, ?, 'outgoing', ?, 0, ?, 84, 0)",
        (
            bf.account_id(1, "Phone", NUMBER_A),
            bf.account_id(1, "Phone", NUMBER_B),
            stamp,
            bf.report_time(UTC_AT),
        ),
    )
    c.execute(
        "INSERT INTO contacts VALUES ('contact:item1:Contacts:3#1', 'item1', 'Contacts:3',"
        " 'dev:item1', 'Gus Tires', ?)",
        (NUMBER_B,),
    )
    return c


def test_call_and_contact_text_match_the_product(conn: sqlite3.Connection) -> None:
    raw = bf.report_time(UTC_AT)
    assert invariants.record_text(conn, "call:item1:Calls:7") == bf.call_text(
        "outgoing", NUMBER_A, NUMBER_B, raw, 84
    )
    assert invariants.record_text(conn, "contact:item1:Contacts:3#1") == bf.contact_text(
        "Gus Tires", NUMBER_B
    )
    assert bf.contact_text(None, NUMBER_B) == NUMBER_B


def test_sender_lines_follow_the_product_and_the_adapter(conn: sqlite3.Connection) -> None:
    # The adapter (eval/stancemodel time_case01.case_item) prints the product's "(this phone)"
    # as "(owner)"; persons in brackets come after it.
    own = context._sender(conn, bf.account_id(1, *OWNER)).replace(" (this phone)", " (owner)")
    assert own == bf.sender_line(*OWNER, owner=True)
    assert context._sender(conn, bf.account_id(1, *OTHER)) == bf.sender_line(*OTHER)
    assert bf.sender_line(*OWNER, owner=True, persons=[bf.owner_person(1)]) == (
        "Telegram 5550147 (owner) [person:dev:item1:owner]"
    )
    lines = context.build_context(conn, "contact:item1:Contacts:3#1")
    assert (lines[0].sender, lines[0].local_time) == (bf.CONTACT_SENDER, bf.CONTACT_TIME)


def test_local_time_matches_the_adapter() -> None:
    from zoneinfo import ZoneInfo

    shown = format_local(parse_utc(UTC_AT.isoformat()), ZoneInfo(TZ), None)
    assert re.sub(r"\s*\(UTC[+-]\d\d:\d\d\)$", "", shown) == local_str(UTC_AT, TZ)
    assert local_str(UTC_AT, TZ) == "2026-05-02 21:10:44 CDT"


@pytest.mark.parametrize("offset", [0, -300, 330])
def test_report_time_parses_back_to_the_same_instant(offset: int) -> None:
    raw = bf.report_time(UTC_AT, offset)
    assert parse_time(raw, DateOrder(mdy_votes=1), None).ts.utc == UTC_AT


def test_report_time_prints_like_a_cellebrite_report() -> None:
    assert bf.report_time(UTC_AT) == "5/3/2026 2:10:44 AM(UTC+0)"
    assert bf.report_time(UTC_AT, -300) == "5/2/2026 9:10:44 PM(UTC-5)"


def test_assumption_text_is_the_products_own() -> None:
    params = {
        "quoted_text": "gate code 1190",
        "account_ids": (bf.account_id(1, *OTHER),),
        "window": bf.window(datetime(2026, 5, 2), datetime(2026, 5, 3), TZ, "on May 2, 2026"),
    }
    text = bf.assumption_text("record_time", **params)
    assert text == instantiate("C99", "record_time", params).text
    assert text == (
        'The message "gate code 1190" (acct:item1:Telegram:5550163) was sent "on May 2, 2026"'
        " (America/Chicago)"
    )
    with pytest.raises(ValueError):
        bf.assumption_text("record_time", quoted_text="gate code 1190")  # no window


def test_zone_table_covers_every_abbreviation_its_zones_print() -> None:
    for zone in bf.ZONES:
        for month in (1, 7):
            shown = local_str(datetime(2026, month, 15, 18, tzinfo=UTC), zone).split()[-1]
            assert bf.ZONE_OF[shown] == zone


def test_ids() -> None:
    assert bf.device_id(2) == "dev:item2"
    assert bf.owner_person(2) == "person:dev:item2:owner"
    assert bf.named_person("vance") == "person:vance"
    with pytest.raises(ValueError):
        bf.named_person("Vance")
    with pytest.raises(ValueError):
        bf.account_id(1, "Email", "x")
