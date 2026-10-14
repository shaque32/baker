"""Readable names for model input (core/audit/readable.py). SYNTHETIC data only."""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from core.audit.assumptions import TEMPLATES, instantiate, local_window
from core.audit.readable import CaseNames, assumption_text, case_names
from core.review.actions import stipulate_device_owner, withdraw_stipulation

EXPERT = "expert:Test Examiner"
WINDOW = local_window(datetime(2026, 5, 2), datetime(2026, 5, 3), "America/Chicago", "on May 2")


def _source(conn: sqlite3.Connection, sid: str) -> None:
    conn.execute(
        "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
        " imported_at_utc) VALUES (?, 'synthetic', 'curated_report', 'logical', ?, ?,"
        " '2026-05-10T00:00:00Z')",
        (sid, f"{sid}.xlsx", "0" * 64),
    )
    conn.execute(
        "INSERT INTO devices (id, source_id, locator, label)"
        " VALUES (?, ?, 'Device', 'Apple iPhone')",
        (f"dev:{sid}", sid),
    )


def _account(
    conn: sqlite3.Connection, aid: str, sid: str, app: str, ident: str, own: bool = False
) -> None:
    conn.execute(
        "INSERT INTO accounts (id, source_id, locator, device_id, app, identifier)"
        " VALUES (?, ?, 'Accounts', ?, ?, ?)",
        (aid, sid, f"dev:{sid}" if own else None, app, ident),
    )


def _person(conn: sqlite3.Connection, pid: str, name: str) -> None:
    conn.execute(
        "INSERT INTO persons (id, name, created_by) VALUES (?, ?, 'govdoc:c1')", (pid, name)
    )


def _link(conn: sqlite3.Connection, aid: str, pid: str, status: str) -> None:
    decided = status != "proposed"
    conn.execute(
        "INSERT INTO identity_links (id, account_id, person_id, status, tier, basis, decided_by,"
        " decided_at_utc) VALUES (?, ?, ?, ?, ?, 'test', ?, ?)",
        (
            f"link:{aid}|{pid}",
            aid,
            pid,
            status,
            "confirmed" if status == "confirmed" else "inferred",
            EXPERT if decided else None,
            "2026-05-10T00:00:00Z" if decided else None,
        ),
    )


@pytest.fixture
def names(case_db: sqlite3.Connection) -> CaseNames:
    """Two phones. item1's owner is stipulated as Daniel Petrov; item2 saved his number as
    "Dan P". Rita Vance has a confirmed link to a Telegram account both phones list; Omar
    Haddad has only a proposed link."""
    conn = case_db
    _source(conn, "item1")
    _source(conn, "item2")
    _account(conn, "acct:item1:SMS:+12125550111", "item1", "SMS", "+12125550111", own=True)
    _account(conn, "acct:item2:SMS:+1 (212) 555-0111", "item2", "SMS", "+1 (212) 555-0111")
    _account(conn, "acct:item1:Telegram:5550147", "item1", "Telegram", "5550147")
    _account(conn, "acct:item2:Telegram:5550147", "item2", "Telegram", "5550147")
    _account(conn, "acct:item2:WhatsApp:+13055550190", "item2", "WhatsApp", "+13055550190")
    _person(conn, "person:vance", "Rita Vance")
    _person(conn, "person:haddad", "Omar Haddad")
    _link(conn, "acct:item1:Telegram:5550147", "person:vance", "confirmed")
    _link(conn, "acct:item2:WhatsApp:+13055550190", "person:haddad", "proposed")
    stipulate_device_owner(conn, "dev:item1", "Daniel Petrov", EXPERT)
    return case_names(conn)


def test_people_read_by_name(names: CaseNames) -> None:
    assert names.person("person:dev:item1:owner") == "Daniel Petrov (the user of item1)"
    assert names.person("person:vance") == "Rita Vance"
    # No stipulation for item2: its user is named by the phone, never by a guess.
    assert names.person("person:dev:item2:owner") == "the user of item2"
    assert names.person("person:nobody") == "person:nobody"
    assert names.phone("dev:item2") == "item2"


def test_sender_lines_show_confirmed_people_across_phones(names: CaseNames) -> None:
    # case01 paragraph 10.1: the stipulated owner's number on another phone, saved as "Dan P".
    assert (
        names.sender("acct:item2:SMS:+1 (212) 555-0111", "Dan P")
        == "SMS +1 (212) 555-0111 Dan P [Daniel Petrov (the user of item1)]"
    )
    assert (
        names.sender("acct:item1:SMS:+12125550111")
        == "SMS +12125550111 (owner) [Daniel Petrov (the user of item1)]"
    )
    # A link confirmed on one phone's copy of the account holds for the same account on another.
    assert names.sender("acct:item2:Telegram:5550147") == "Telegram 5550147 [Rita Vance]"
    # A proposed link never shows.
    assert names.sender("acct:item2:WhatsApp:+13055550190", "Omar") == "WhatsApp +13055550190 Omar"
    assert names.sender(None) == "unknown sender"
    assert names.sender("acct:item9:SMS:+1") == "account acct:item9:SMS:+1"


def test_withdrawn_stipulation_drops_the_name(case_db: sqlite3.Connection) -> None:
    _source(case_db, "item1")
    _account(case_db, "acct:item1:SMS:+12125550111", "item1", "SMS", "+12125550111", own=True)
    sid = stipulate_device_owner(case_db, "dev:item1", "Daniel Petrov", EXPERT)
    withdraw_stipulation(case_db, sid, EXPERT)
    names = case_names(case_db)
    assert names.person("person:dev:item1:owner") == "the user of item1"
    assert names.sender("acct:item1:SMS:+12125550111") == "SMS +12125550111 (owner)"


def test_accounts_print_once_and_counts_read_as_words(names: CaseNames) -> None:
    assert names.accounts(
        [
            "acct:item1:Telegram:5550147",
            "acct:item2:Telegram:5550147",
            "acct:item2:WhatsApp:+13055550190",
        ]
    ) == ["Telegram 5550147", "WhatsApp +13055550190"]
    # SMS numbers share one space across formats, as the checks match them.
    assert names.accounts(["acct:item1:SMS:+12125550111", "acct:item2:SMS:+1 (212) 555-0111"]) == [
        "SMS +12125550111"
    ]
    assert [names.count(op, 12) for op in ("eq", "ge", "le")] == [
        "exactly 12",
        "at least 12",
        "at most 12",
    ]


def test_assumptions_render_readable_and_stored_text_keeps_ids(names: CaseNames) -> None:
    sender = instantiate(
        "c10.1",
        "sender",
        {"quoted_text": "move it tonight", "person_ids": ["person:dev:item1:owner"]},
        True,
    )
    assert sender.text == 'The message "move it tonight" was sent by person:dev:item1:owner'
    assert (
        assumption_text(sender, names)
        == 'The message "move it tonight" was sent by Daniel Petrov (the user of item1)'
    )
    count = instantiate(
        "c4",
        "message_count",
        {
            "window": WINDOW,
            "expected_count": 12,
            "count_op": "ge",
            "device_ids": ["dev:item2"],
            "person_ids": ["person:dev:item1:owner"],
            "account_ids": ["acct:item1:Telegram:5550147", "acct:item2:Telegram:5550147"],
        },
        True,
    )
    assert assumption_text(count, names) == (
        "item2 holds at least 12 messages between Daniel Petrov (the user of item1) and "
        'Telegram 5550147 "on May 2" (America/Chicago)'
    )
    contact = TEMPLATES["contact_entry"].render(
        instantiate(
            "c5",
            "contact_entry",
            {
                "device_ids": ["dev:item2"],
                "quoted_text": "Dan P",
                "account_ids": ["acct:item2:SMS:+1 (212) 555-0111"],
            },
            True,
        ).params,
        names,
    )
    assert contact == 'item2 has a contact "Dan P" with the number of SMS +1 (212) 555-0111'
    identity = instantiate(
        "c6",
        "person_identity",
        {"account_ids": ["acct:item2:Telegram:5550147"], "person_ids": ["person:vance"]},
        True,
    )
    assert assumption_text(identity, names) == "Telegram 5550147 belongs to Rita Vance"


def test_unfitting_template_keeps_the_stored_text(names: CaseNames) -> None:
    a = instantiate("c7", "role", {"person_ids": ["person:vance"]}, True)
    broken = a.model_copy(update={"template_id": "no_such_template"})
    assert assumption_text(broken, names) == a.text
    assert assumption_text(a, names) == "Rita Vance played the role the claim states"
