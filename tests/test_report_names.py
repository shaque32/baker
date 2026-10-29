"""The case's ids shown by name on the screen and in the report (core/report/names.py)."""

from __future__ import annotations

import html
import re
import sqlite3

import pytest

from core.audit.invariants import QUOTED_SPAN
from core.report.names import Names


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(
        "CREATE TABLE persons (id TEXT, name TEXT);"
        "CREATE TABLE devices (id TEXT, label TEXT);"
        "CREATE TABLE accounts (id TEXT, app TEXT, identifier TEXT);"
        "INSERT INTO persons VALUES ('person:dev:item1:owner', 'Daniel Petrov');"
        "INSERT INTO devices VALUES ('dev:item1', 'Apple iPhone 13 (A2482)');"
        "INSERT INTO accounts VALUES ('acct:item1:Telegram:5551234', 'Telegram', '5551234');"
        "INSERT INTO accounts VALUES ('acct:item2:Telegram:5551234', 'Telegram', '5551234');"
    )
    yield c
    c.close()


def test_ids_show_by_name_with_the_id_kept_in_the_title(conn):
    names = Names(conn)
    text = (
        "dev:item1 holds eq 13 messages between person:dev:item1:owner and "
        "acct:item1:Telegram:5551234/acct:item2:Telegram:5551234."
    )
    out = names.html(text)
    plain = re.sub(r"<[^>]+>", "", out)
    assert plain == (
        "Apple iPhone 13 (A2482) holds exactly 13 messages between Daniel Petrov and "
        "Telegram 5551234."  # one account held on two phones is named once
    )
    assert "<span title='person:dev:item1:owner'>" in out
    # each name is the case's text, which the forbidden-word check leaves as written
    assert len(QUOTED_SPAN.findall(out)) == 3


def test_an_id_inside_another_id_stays_whole(conn):
    out = Names(conn).html("per stipulation stip:device_owner:dev:item1")
    assert out == "per stipulation stip:device_owner:dev:item1"


def test_an_id_the_case_does_not_name_stays_as_written(conn):
    assert Names(conn).html("belongs to person:sokolov") == "belongs to person:sokolov"


def test_the_key_lists_each_name_once_whatever_the_ids_case(conn):
    names = Names(conn)
    names.html("acct:item1:Telegram:5551234 and acct:item1:telegram:5551234 and dev:item1")
    key = names.key_table()
    assert key.count("acct:item1:") == 1
    assert '<td class="mono">dev:item1</td>' in key
    assert Names(conn).key_table() == ""


def test_two_people_named_alike_keep_their_ids(conn):
    conn.execute("INSERT INTO persons VALUES ('person:dev:item2:owner', 'Daniel Petrov')")
    out = re.sub(r"<[^>]+>", "", Names(conn).html("person:dev:item1:owner"))
    assert out == "Daniel Petrov (person:dev:item1:owner)"


def test_only_the_fillers_count_wording_becomes_words(conn):
    shown = Names(conn).html("Messages containing 'lt 3 left' verbatim; dev:item1 holds ge 2 calls")
    out = html.unescape(re.sub(r"<[^>]+>", "", shown))
    assert "'lt 3 left'" in out and "holds at least 2 calls" in out
