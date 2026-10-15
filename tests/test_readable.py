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


def test_people_who_share_a_name_never_read_alike(case_db: sqlite3.Connection) -> None:
    _source(case_db, "item1")
    _source(case_db, "item2")
    _account(case_db, "acct:item2:SMS:+12125550144", "item2", "SMS", "+12125550144")
    _person(case_db, "person:alex-smith", "Alex Smith")
    _person(case_db, "person:alex-smith-1a2b3c4d", "alex  smith")
    _person(case_db, "person:daniel-petrov", "Daniel Petrov")
    _person(case_db, "person:mara-lind", "Mara Lind")
    _link(case_db, "acct:item2:SMS:+12125550144", "person:alex-smith-1a2b3c4d", "confirmed")
    stipulate_device_owner(case_db, "dev:item1", "Daniel Petrov", EXPERT)
    stipulate_device_owner(case_db, "dev:item2", "Daniel Petrov", EXPERT)
    names = case_names(case_db)
    assert names.person("person:alex-smith") == "Alex Smith (person:alex-smith)"
    assert (
        names.sender("acct:item2:SMS:+12125550144")
        == "SMS +12125550144 [alex  smith (person:alex-smith-1a2b3c4d)]"
    )
    # Phone users are told apart by their phones; a document person of the same name by id.
    assert names.person("person:dev:item1:owner") == "Daniel Petrov (the user of item1)"
    assert names.person("person:dev:item2:owner") == "Daniel Petrov (the user of item2)"
    assert names.person("person:daniel-petrov") == "Daniel Petrov (person:daniel-petrov)"
    assert names.person("person:mara-lind") == "Mara Lind"
    labels = [names.person(pid) for (pid,) in case_db.execute("SELECT id FROM persons")]
    assert len(set(labels)) == len(labels)


def test_a_withdrawn_users_name_is_not_shown_so_it_shares_nothing(
    case_db: sqlite3.Connection,
) -> None:
    _source(case_db, "item1")
    _person(case_db, "person:daniel-petrov", "Daniel Petrov")
    sid = stipulate_device_owner(case_db, "dev:item1", "Daniel Petrov", EXPERT)
    withdraw_stipulation(case_db, sid, EXPERT)
    names = case_names(case_db)
    assert names.person("person:daniel-petrov") == "Daniel Petrov"
    assert names.person("person:dev:item1:owner") == "the user of item1"


def test_a_source_holding_two_phones_names_each(case_db: sqlite3.Connection) -> None:
    _source(case_db, "item1")
    case_db.execute(
        "INSERT INTO devices (id, source_id, locator, label)"
        " VALUES ('dev:item1#2', 'item1', 'Device 2', 'Apple iPad')"
    )
    names = case_names(case_db)
    assert names.phone("dev:item1") == "item1 (dev:item1)"
    assert names.phone("dev:item1#2") == "item1 (dev:item1#2)"


class _FakeLocal:
    """A local model stand-in: records each prompt, answers "irrelevant"."""

    name = "fake-14b"
    sha256 = "ab" * 32

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
        from types import SimpleNamespace

        self.prompts.append(prompt)
        return SimpleNamespace(raw_text='{"stance": "irrelevant", "quote": "", "rationale": "r"}')


def test_the_stance_model_reads_the_cases_names(names: CaseNames, case_db: sqlite3.Connection):
    """Stance prompt v1.1 end to end: case01 paragraph 10.1's shape, where item2 saved the
    stipulated owner's number as "Dan P". The model reads names, the chat's members and, for a
    template that says "the claim", the claim; the stored assumption keeps Baker's ids."""
    from core.audit import stance
    from core.contracts import EvidenceCandidate, ProvenanceTier, SourceRef

    conn = case_db
    conn.execute(
        "INSERT INTO threads VALUES ('thr:item2:SMS', 'item2', 'Chats', 'dev:item2', 'SMS', NULL)"
    )
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, sender_raw,"
        " direction, ts_utc, ts_offset_min, ts_raw, body) VALUES ('msg:item2:Chats!3', 'item2',"
        " 'Chats!3', 'thr:item2:SMS', 'acct:item2:SMS:+1 (212) 555-0111', 'Dan P', 'incoming',"
        " '2026-05-03T02:10:44Z', -300, '5/2/2026 9:10:44 PM', 'move it tonight')"
    )
    conn.execute(
        "INSERT INTO sources (id, kind, fidelity, extraction_type, file_name, sha256,"
        " imported_at_utc) VALUES ('gd', 'govdoc', 'unknown', 'not_applicable', 'aff.pdf', ?,"
        " '2026-05-10T00:00:00Z')",
        ("1" * 64,),
    )
    conn.execute("INSERT INTO govdocs VALUES ('gd:1', 'gd', 'Affidavit', 'affidavit')")
    claim = 'PETROV wrote "move it tonight", directing the crew.'
    conn.execute(
        "INSERT INTO govdoc_paragraphs (id, govdoc_id, page, para_no, label, char_start, char_end,"
        " text) VALUES ('p10', 'gd:1', 1, 10, '10.1', 0, ?, ?)",
        (len(claim), claim),
    )
    conn.execute(
        "INSERT INTO claims VALUES ('C10', 'p10', ?, 'communication', 'accepted', NULL)", (claim,)
    )
    model = _FakeLocal()
    labeler = stance.create(conn, model=model)
    cand = EvidenceCandidate(
        record_id="msg:item2:Chats!3",
        ref=SourceRef(source_id="item2", locator="Chats!3"),
        text="move it tonight",
        tier=ProvenanceTier.OBSERVED,
        retrieval_score=1.0,
    )
    owner = "person:dev:item1:owner"
    sender = instantiate(
        "C10", "sender", {"quoted_text": "move it tonight", "person_ids": [owner]}, True
    )
    role = instantiate("C10", "role", {"person_ids": [owner]}, True)
    labeler.try_label(sender, cand)
    labeler.try_label(role, cand)
    sent, roled = model.prompts
    dan = "Daniel Petrov (the user of item1)"
    assert f'Assumption:\nThe message "move it tonight" was sent by {dan}\n' in sent
    assert f"Assumption:\n{dan} played the role the claim states\n" in roled
    assert "[CLAIM START]\n(not needed for this assumption)\n[CLAIM END]" in sent
    assert f"[CLAIM START]\n{claim}\n[CLAIM END]" in roled
    assert (
        f"[CONTEXT START]\nMembers seen in this chat's records: SMS +1 (212) 555-0111 [{dan}]\n"
    ) in sent
    assert f"] SMS +1 (212) 555-0111 Dan P [{dan}], incoming: move it tonight" in sent
    assert owner not in sent and "acct:" not in sent
    assert sender.text.endswith(owner)  # the stored text keeps the id
