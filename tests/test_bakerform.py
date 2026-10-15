"""Baker-form item formats match what the product stores and shows. SYNTHETIC values only."""

from __future__ import annotations

import re
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from core.audit import context, invariants, readable
from core.audit.assumptions import TEMPLATES, instantiate, parse_params
from core.db import apply_schema
from core.enrich.local_time import format_local, parse_utc
from core.ingest.cellebrite_common import DateOrder, parse_time
from core.review.actions import stipulate_device_owner
from eval.stancedata import bakerform as bf
from eval.stancedata import names as nm
from eval.stancedata.chat import local_str
from eval.stancedata.model import GenItem

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


def test_contact_text_matches_the_product(conn: sqlite3.Connection) -> None:
    assert invariants.record_text(conn, "contact:item1:Contacts:3#1") == bf.contact_text(
        "Gus Tires", NUMBER_B
    )
    assert bf.contact_text(None, NUMBER_B) == f"(no name): {NUMBER_B}"


def test_call_rows_follow_guide_rule_28_not_yet_the_product(conn: sqlite3.Connection) -> None:
    # Baker shows and checks a call as core.enrich.records.call_text, without the report's time
    # (#76). Generated call rows still follow the signed guide's rule 28, with the time as the
    # report printed it. Aligning them changes the training data and the guide, so it is the
    # "Custom model for Baker" thread's change; then this test pins equality again.
    raw = bf.report_time(UTC_AT)
    assert bf.call_text("outgoing", NUMBER_A, NUMBER_B, raw, 84) == (
        f"outgoing call from {NUMBER_A} to {NUMBER_B} at {raw}, 84s"
    )
    assert invariants.record_text(conn, "call:item1:Calls:7") == (
        f"outgoing Phone call from {NUMBER_A} to {NUMBER_B}, duration 84 s"
    )


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


NAMES = {bf.owner_person(1): "Daniel Petrov", bf.named_person("vance"): "Rita Vance"}


def _named(conn: sqlite3.Connection) -> readable.CaseNames:
    """The fixture's case once an expert stipulated item1's user and confirmed Rita Vance's
    link to the other Telegram account."""
    stipulate_device_owner(conn, "dev:item1", NAMES[bf.owner_person(1)], "expert:Test")
    conn.execute(
        "INSERT INTO persons VALUES ('person:vance', 'Rita Vance', 'govdoc:c1')",
    )
    conn.execute(
        "INSERT INTO identity_links VALUES ('link:1', ?, 'person:vance', 'confirmed',"
        " 'confirmed', 'test', 'expert:Test', '2026-05-10T00:00:00Z')",
        (bf.account_id(1, *OTHER),),
    )
    return readable.case_names(conn)


def test_readable_sender_lines_are_the_products(conn: sqlite3.Connection) -> None:
    product = _named(conn)
    generated = nm.case_names(NAMES)
    owner_line = bf.sender_line(*OWNER, owner=True, persons=[bf.owner_person(1)])
    assert nm.readable_sender(owner_line, generated) == product.sender(bf.account_id(1, *OWNER))
    assert product.sender(bf.account_id(1, *OWNER)) == (
        "Telegram 5550147 (owner) [Daniel Petrov (the user of item1)]"
    )
    other_line = bf.sender_line(*OTHER, persons=[bf.named_person("vance")], shown_as="Rita")
    assert nm.readable_sender(other_line, generated) == product.sender(
        bf.account_id(1, *OTHER), "Rita"
    )
    assert nm.readable_sender(bf.sender_line(*OTHER), generated) == bf.sender_line(*OTHER)


def test_readable_assumptions_are_the_products(conn: sqlite3.Connection) -> None:
    product = _named(conn)
    params = parse_params(
        "event",
        {
            "person_ids": (bf.owner_person(1), bf.named_person("vance")),
            "account_ids": (bf.account_id(1, *OTHER), bf.account_id(1, "Phone", NUMBER_B)),
            "window": bf.window(datetime(2026, 5, 1), datetime(2026, 5, 3), TZ, "May 1 to 2"),
        },
    )
    generated = nm.case_names(NAMES, params.account_ids)
    text = TEMPLATES["event"].render(params, generated)
    assert text == TEMPLATES["event"].render(params, product)
    assert text == (
        "The event the claim states happened, involving Daniel Petrov (the user of item1) and"
        ' Rita Vance and Telegram 5550163/Phone +13125550188 "May 1 to 2" (America/Chicago)'
    )


def test_items_read_by_name() -> None:
    lines = [
        bf.message_line(1, *OTHER, UTC_AT, TZ, "whats the code"),
        bf.message_line(
            1,
            *OWNER,
            UTC_AT + timedelta(minutes=1),
            TZ,
            "gate code 1190",
            owner=True,
            persons=[bf.owner_person(1)],
        ),
    ]
    common = {
        "probe_id": "T999999",
        "family_id": "bk_sender_shown",
        "source": "train_gen",
        "generator": "eval.train test",
        "lang": "en",
        "template_id": "sender",
        "params": {"quoted_text": "gate code 1190", "person_ids": [bf.owner_person(1)]},
        "lines": lines,
        "target": 1,
        "quote": "gate code 1190",
        "rationale": "The line's brackets show Daniel Petrov sent the quoted words.",
        "device": "dev:item1",
    }
    item = bf.build_baker_item(**common, names=NAMES)
    assert item.assumption == (
        'The message "gate code 1190" was sent by Daniel Petrov (the user of item1)'
    )
    assert item.target.sender == "Telegram 5550147 (owner) [Daniel Petrov (the user of item1)]"
    assert item.baker_names == {bf.owner_person(1): "Daniel Petrov"}
    assert GenItem.model_validate(item.model_dump()) == item
    with pytest.raises(ValueError, match="no name for person:dev:item1:owner"):
        bf.build_baker_item(**common, names={})
    leaked = item.model_dump() | {
        "target": item.target.model_copy(update={"sender": lines[1].sender})
    }
    with pytest.raises(ValueError, match="an id shows where a name belongs"):
        GenItem.model_validate(leaked)


def test_chat_members_are_the_products(conn: sqlite3.Connection) -> None:
    """A message item carries its chat's members, and the line they make is the one the product
    prints for the record's chat: the accounts of the chat's senders and listed recipients. In
    the fixture's chat only Rita Vance writes; the owner's account is listed as her message's
    recipient, and is a member all the same."""
    thread = "thr:item1:Telegram:1"
    conn.execute(
        "INSERT INTO message_recipients VALUES ('msg:item1:1', ?, NULL)",
        (bf.account_id(1, *OWNER),),
    )
    product = _named(conn)
    member_ids = [
        r[0]
        for r in conn.execute(
            "SELECT sender_account_id FROM messages WHERE thread_id = ? UNION"
            " SELECT r.account_id FROM message_recipients r JOIN messages m"
            " ON m.id = r.message_id WHERE m.thread_id = ?",
            (thread, thread),
        )
    ]
    vance, owner = [bf.named_person("vance")], [bf.owner_person(1)]
    to_owner = [bf.sender_line(*OWNER, owner=True, persons=owner)]
    lines = [bf.message_line(1, *OTHER, UTC_AT, TZ, "gate code 1190", persons=vance,
                             recipients=to_owner)]  # fmt: skip
    item = bf.build_baker_item(
        probe_id="T999998",
        family_id="bk_sender_shown",
        source="train_gen",
        generator="eval.train test",
        lang="en",
        template_id="sender",
        params={"quoted_text": "gate code 1190", "person_ids": vance},
        lines=lines,
        target=0,
        quote="gate code 1190",
        rationale="The line's brackets show Rita Vance sent the quoted words.",
        device="dev:item1",
        names=NAMES,
    )
    assert readable.members_line(item.baker_members or ()) == product.members(member_ids)
    assert product.members(member_ids) == (
        "Members seen in this chat's records: Telegram 5550147 (owner) [Daniel Petrov (the user"
        " of item1)]; Telegram 5550163 [Rita Vance]"
    )
    assert item.baker_names == NAMES
    assert GenItem.model_validate(item.model_dump()) == item
    missing = item.model_dump() | {"baker_members": item.baker_members[:1]}
    with pytest.raises(ValueError, match="members hold every line's sender"):
        GenItem.model_validate(missing)


def test_only_a_chat_record_carries_members() -> None:
    call = bf.call_line(1, UTC_AT, TZ, "outgoing", NUMBER_A, NUMBER_B, 84, owner=True)
    contact = bf.contact_line(1, "Gus Tires", NUMBER_B)
    assert (call.kind, contact.kind) == ("call", "contact")
    msg = bf.message_line(1, *OTHER, UTC_AT + timedelta(minutes=2), TZ, "gate code 1190")
    assert msg.kind == "message"
    with pytest.raises(ValueError, match="only its own chat's messages"):
        bf.build_baker_item(
            probe_id="T999997",
            family_id="bk_sender_shown",
            source="train_gen",
            generator="eval.train test",
            lang="en",
            template_id="sender",
            params={"quoted_text": "gate code 1190", "person_ids": [bf.owner_person(1)]},
            lines=[call, msg],
            target=1,
            quote="gate code 1190",
            rationale="The line shows who sent the quoted words.",
            device="dev:item1",
        )


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
