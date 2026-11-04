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


def _quoting(conn):
    conn.executescript(
        "CREATE TABLE claims (id TEXT, text TEXT);"
        "INSERT INTO claims VALUES ('D22', 'On May 2, 2023, SUBJECT-1 wrote on Twitter: "
        "\"Done. It''s been deleted.\"');"
    )
    return Names(conn)


@pytest.mark.parametrize(
    "text",
    [
        # an assumption's text, a rule's reason and a check's search line (lowercased, curly)
        'The message "Done. It\'s been deleted." was sent by person:dev:item1:owner on Twitter',
        "Rule 2: 'The words \"Done. It's been deleted.\" mean what the claim says they mean' is "
        "not covered by a passing check or an accepted supporting item.",
        "Messages containing “done. it’s been deleted.” (verbatim)",
    ],
)
def test_words_quoted_from_a_claim_print_as_cited(conn, text):
    # Validation run 3: a claim quoting "It's been deleted." stopped the whole report, because
    # its words came back inside Mabillon's own sentences unmarked.
    from core.audit.invariants import check_report_text

    out = _quoting(conn).html(text)
    check_report_text(f"<p>{out}</p>")
    assert "Daniel Petrov" in out or "person:" not in text


def test_quoted_words_no_claim_holds_stay_the_tools_own(conn):
    from core.audit.invariants import InvariantViolation, check_report_text

    out = _quoting(conn).html('The phone "was deleted" by person:dev:item1:owner')
    with pytest.raises(InvariantViolation, match="deleted"):
        check_report_text(f"<p>{out}</p>")


def test_quoted_words_are_cited_only_as_whole_words(conn):
    from core.audit.invariants import InvariantViolation, check_report_text

    conn.executescript(
        "CREATE TABLE claims (id TEXT, text TEXT);"
        "INSERT INTO claims VALUES ('C1', 'He wrote \"the file stays undeleted here\".');"
        "INSERT INTO claims VALUES ('C2', 'She wrote one word: \"leader\".');"
    )
    names = Names(conn)
    marked = names.html('The record was marked "deleted".')
    # "deleted" stands only inside "undeleted": the tool's own word, checked
    with pytest.raises(InvariantViolation, match="deleted"):
        check_report_text("<p>" + marked + "</p>")
    # a one-word quote the claim makes is the document's word
    check_report_text("<p>" + names.html('The words "leader" mean what the claim says') + "</p>")


def test_a_claims_own_lines_cite_only_its_own_quotes(conn):
    from core.audit.invariants import InvariantViolation, check_report_text

    own, other = 'He wrote "it was deleted".', 'She wrote "see you at nine".'
    conn.execute("CREATE TABLE claims (id TEXT, text TEXT)")
    conn.executemany("INSERT INTO claims VALUES (?, ?)", [("C1", own), ("C2", other)])
    line = 'The message "it was deleted" was sent by person:dev:item1:owner'
    names = Names(conn)
    check_report_text("<p>" + names.for_claim(own).html(line) + "</p>")
    with pytest.raises(InvariantViolation, match="deleted"):  # another claim's words
        check_report_text("<p>" + names.for_claim(other).html(line) + "</p>")
    # the key of names shown stays shared with the report
    assert "person:dev:item1:owner" in names.used
