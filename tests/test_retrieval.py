"""Retrieval and context on a tiny hand-built case. Every value here is invented."""

import sqlite3

import pytest

from core.audit.context import HEADER, build_context, context_ids, render_context, render_for
from core.audit.retrieval import RetrievalQuery, SqlRetriever, query_for, search
from core.contracts import Assumption, AssumptionKind, ProvenanceTier
from core.enrich.local_time import format_local, parse_utc
from core.enrich.records import record_text
from core.enrich.text import extract_terms, quoted


def _assumption(text: str, claim_id: str = "c1") -> Assumption:
    return Assumption(
        id="a1",
        claim_id=claim_id,
        kind=AssumptionKind.EVENT,
        text=text,
        is_core=True,
        tier=ProvenanceTier.INFERRED,
    )


@pytest.fixture
def db(case_db: sqlite3.Connection) -> sqlite3.Connection:
    c = case_db
    c.execute(
        "INSERT INTO sources VALUES ('s1', 'synthetic', 'curated_report', 'logical', 's1.xlsx',"
        " ?, NULL, NULL, NULL, '2026-03-01T00:00:00Z')",
        ("0" * 64,),
    )
    c.execute(
        "INSERT INTO devices VALUES ('dev:s1', 's1', 'Summary!4', 'Phone A', NULL, NULL,"
        " 'America/New_York')"
    )
    accounts = [
        ("acct:s1:Telegram:100", "dev:s1", "Telegram", "100", "Owner"),
        ("acct:s1:Telegram:5550001", None, "Telegram", "5550001", "@oldname"),
        ("acct:s1:SMS:+12125550199", None, "SMS", "+12125550199", "Bo"),
        ("acct:s1:Phone:+12125550111", "dev:s1", "Phone", "+12125550111", None),
        ("acct:s1:Phone:+12125550199", None, "Phone", "+12125550199", None),
    ]
    for aid, dev, app, ident, name in accounts:
        c.execute(
            "INSERT INTO accounts VALUES (?, 's1', 'x', ?, ?, ?, ?)", (aid, dev, app, ident, name)
        )
    c.execute(
        "INSERT INTO threads VALUES ('thr:tg', 's1', 'Chats!3', 'dev:s1', 'Telegram', '@newname')"
    )
    c.execute("INSERT INTO threads VALUES ('thr:sms', 's1', 'Chats!90', 'dev:s1', 'SMS', 'Bo')")
    # 50 Telegram messages, one an hour from 2026-03-07 12:00Z, crossing the DST change.
    for i in range(50):
        own = i % 2 == 1
        hour = 12 + i
        ts = f"2026-03-{7 + hour // 24:02d}T{hour % 24:02d}:00:00Z"
        c.execute(
            "INSERT INTO messages VALUES (?, 's1', ?, 'thr:tg', ?, ?, ?, 0, ?, ?, NULL, 0, NULL)",
            (
                f"msg:s1:Chats!{3 + i}",
                f"Chats!{3 + i}",
                "acct:s1:Telegram:100" if own else "acct:s1:Telegram:5550001",
                "outgoing" if own else "incoming",
                ts,
                ts,
                "Пакет готов, ёлка"
                if i == 25
                else ("bring the package\nfriday" if i == 30 else f"chat {i}"),
            ),
        )
    c.execute(
        "INSERT INTO messages VALUES ('msg:s1:Chats!90', 's1', 'Chats!90', 'thr:sms',"
        " 'acct:s1:SMS:+12125550199', 'incoming', '2026-03-09T01:00:00Z', 0, 'raw', 'see you',"
        " NULL, 0, NULL)"
    )
    c.execute(
        "INSERT INTO messages VALUES ('msg:s1:Chats!91', 's1', 'Chats!91', 'thr:sms',"
        " NULL, 'unknown', NULL, NULL, '??', 'no time here', NULL, NULL, NULL)"
    )
    c.execute(
        "INSERT INTO message_recipients VALUES ('msg:s1:Chats!4', 'acct:s1:Telegram:5550001')"
    )
    c.execute(
        "INSERT INTO calls VALUES ('call:s1:Call Log!3', 's1', 'Call Log!3', 'dev:s1', 'Phone',"
        " 'acct:s1:Phone:+12125550111', 'acct:s1:Phone:+12125550199', 'outgoing',"
        " '2026-03-08T14:30:00Z', 0, 'raw', 123, 0)"
    )
    c.execute(
        "INSERT INTO contacts VALUES ('contact:s1:Contacts!3#1', 's1', 'Contacts!3', 'dev:s1',"
        " 'Bo Garage', '+1 (212) 555-0199')"
    )
    c.execute(
        "INSERT INTO attachments VALUES ('att:s1:Chats!40:1', 's1', 'Chats!40', 'msg:s1:Chats!40',"
        " 'invoice_march.pdf', NULL, NULL)"
    )
    return c


# ---------------------------------------------------------------- terms


def test_terms_split_handles_numbers_and_keywords():
    handles, numbers, keywords = extract_terms(
        'On March 12, PETROV wrote "need 2 more" to @north.star (user 5551234), +1 (212) 555-0122.'
    )
    assert handles == ["@north.star"]
    assert numbers == ["5551234", "12125550122"]
    assert keywords[0] == "need 2 more"
    assert "march" not in keywords and "12" not in keywords


def test_apostrophes_are_not_quotes():
    assert quoted("Item 1's contact list has 'Marc Garage' and \"Катя\"") == ["Marc Garage", "Катя"]


# ---------------------------------------------------------------- retrieval


def test_nothing_named_means_nothing_returned(db):
    assert search(db, RetrievalQuery(), k=10) == []
    assert SqlRetriever().retrieve(_assumption("the thing happened"), db, k=10) == []


def test_handle_resolves_through_thread_title_and_display_name(db):
    q = query_for(_assumption("@newname and @oldname are one account"), db, claim="")
    assert q.thread_ids == ("thr:tg",)
    assert q.account_ids == ("acct:s1:Telegram:5550001",)
    assert q.unresolved == ()
    got = search(db, q, k=100)
    assert {c.record_id for c in got} >= {f"msg:s1:Chats!{3 + i}" for i in range(50)}


def test_unresolved_identifiers_are_reported(db):
    q = query_for(_assumption("@nobody wrote to 9998887777"), db, claim="")
    assert q.unresolved == ("@nobody", "9998887777")


def test_number_matches_accounts_calls_and_contacts_by_digits(db):
    q = query_for(_assumption("contact with 212-555-0199"), db, claim="")
    got = [c.record_id for c in search(db, q, k=100)]
    assert "msg:s1:Chats!90" in got
    assert "call:s1:Call Log!3" in got
    assert "contact:s1:Contacts!3#1" in got


def test_keyword_folds_case_and_yo_and_matches_prefix(db):
    got = search(db, RetrievalQuery(keywords=("пакет", "елка")), k=5)
    assert [c.record_id for c in got] == ["msg:s1:Chats!28"]
    assert got[0].retrieval_score == 1.0
    got = search(db, RetrievalQuery(keywords=("packag",)), k=5)
    assert [c.record_id for c in got] == ["msg:s1:Chats!33"]


def test_keywords_rank_within_a_party_filter(db):
    q = RetrievalQuery(thread_ids=("thr:tg",), keywords=("package",))
    got = search(db, q, k=3)
    assert got[0].record_id == "msg:s1:Chats!33"
    assert got[0].retrieval_score > got[1].retrieval_score
    # Ties after the hit keep time order.
    assert [c.record_id for c in got[1:]] == ["msg:s1:Chats!3", "msg:s1:Chats!4"]


def test_window_is_start_inclusive_end_exclusive_and_drops_unknown_times(db):
    from datetime import UTC, datetime

    q = RetrievalQuery(
        thread_ids=("thr:tg", "thr:sms"),
        start_utc=datetime(2026, 3, 7, 13, tzinfo=UTC),
        end_utc=datetime(2026, 3, 7, 15, tzinfo=UTC),
    )
    assert [c.record_id for c in search(db, q, k=100)] == ["msg:s1:Chats!4", "msg:s1:Chats!5"]
    q = RetrievalQuery(thread_ids=("thr:sms",), start_utc=datetime(2026, 1, 1, tzinfo=UTC))
    assert "msg:s1:Chats!91" not in [c.record_id for c in search(db, q, k=100)]


def test_attachment_found_by_file_name(db):
    got = search(db, RetrievalQuery(keywords=("invoice",)), k=5)
    assert [c.record_id for c in got] == ["att:s1:Chats!40:1"]


def test_candidates_are_observed_and_cite_their_source(db):
    for c in search(db, RetrievalQuery(thread_ids=("thr:tg",)), k=100):
        assert c.tier == ProvenanceTier.OBSERVED
        assert c.ref.source_id == "s1"
        assert c.text == record_text(db, c.record_id)


def test_retrieval_is_deterministic(db):
    q = query_for(_assumption("@newname sent the package"), db, claim="")
    assert search(db, q, k=20) == search(db, q, k=20)


def test_claim_text_adds_terms(db):
    q = query_for(_assumption("the outgoing message exists"), db, claim='Bo wrote "see you"')
    assert "see you" in q.keywords


# ---------------------------------------------------------------- context


def test_context_is_twenty_either_side_in_thread_order(db):
    ids = context_ids(db, "msg:s1:Chats!28")
    assert len(ids) == 40
    assert ids[0] == "msg:s1:Chats!8" and ids[-1] == "msg:s1:Chats!48"
    assert "msg:s1:Chats!28" not in ids
    assert context_ids(db, "msg:s1:Chats!3")[0] == "msg:s1:Chats!4"  # clipped at thread start


def test_context_lines_show_account_direction_and_device_local_time(db):
    lines = build_context(db, "msg:s1:Chats!4", window=1)
    assert [ln.is_target for ln in lines] == [False, True, False]
    target = lines[1]
    assert target.sender == "Telegram 100 (this phone)"
    assert target.direction == "outgoing"
    assert target.local_time == "2026-03-07 08:00:00 EST (UTC-05:00)"
    assert lines[0].sender == "Telegram 5550001"
    # The stale first-seen display name is never shown.
    assert "@oldname" not in render_context(lines)


def test_local_time_follows_dst_not_the_printed_offset(db):
    lines = build_context(db, "msg:s1:Chats!50", window=0)
    assert lines[0].local_time.endswith("EDT (UTC-04:00)")  # 2026-03-09 13:00Z, after DST


def test_render_marks_target_and_keeps_one_line_per_message(db):
    text = render_for(db, "msg:s1:Chats!33", window=1)
    rows = text.splitlines()
    assert rows[0] == HEADER
    assert len(rows) == 4
    assert rows[2].startswith(">> [") and "bring the package \\n friday" in rows[2]


def test_call_context_places_the_call_among_same_phone_messages(db):
    lines = build_context(db, "call:s1:Call Log!3", window=2)
    assert [ln.is_target for ln in lines] == [False, False, True, False, False]
    call = lines[2]
    assert (
        call.body == "[call] outgoing Phone call from +12125550111 to +12125550199, duration 123 s"
    )
    assert call.local_time == "2026-03-08 10:30:00 EDT (UTC-04:00)"


def test_attachment_context_centers_on_its_message(db):
    lines = build_context(db, "att:s1:Chats!40:1", window=1)
    assert [ln.record_id for ln in lines if ln.is_target] == ["msg:s1:Chats!40"]


def test_contact_shows_only_its_own_line(db):
    assert context_ids(db, "contact:s1:Contacts!3#1") == ()
    rows = render_for(db, "contact:s1:Contacts!3#1").splitlines()
    assert rows[1:] == [
        ">> [no time in source] contact list, none: [contact] Bo Garage: +1 (212) 555-0199"
    ]
    assert render_for(db, "contact:s1:missing") == "(no surrounding messages)"


def test_unknown_time_and_zone_are_said_plainly():
    assert format_local(None, None, "??") == "time unknown (source shows '??')"
    assert format_local(parse_utc("2026-03-07T12:00:00Z"), None, None) == (
        "2026-03-07 12:00:00 UTC (device zone unknown)"
    )
