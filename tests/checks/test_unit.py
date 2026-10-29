"""Deterministic checks on a tiny hand-built case. Every value is invented."""

import sqlite3
from datetime import datetime as D

import pytest

from core.audit.assumptions import instantiate
from core.audit.checks import CHECKS, run_checks
from core.audit.invariants import FORBIDDEN_WORDS, check_report_text
from core.contracts import CheckOutcome, Claim, ClaimStatus, ClaimType
from core.db import apply_schema, connect
from tests.checks.helpers import check, stipulate, window

A, B = "person:a", "person:b"
MARCH = window(D(2026, 3, 1), D(2026, 4, 1), "in March")
APRIL = window(D(2026, 4, 1), D(2026, 4, 10), "April 1 to 9")


def build(
    fidelity: str = "full_extraction", tz2: str | None = "America/Chicago"
) -> sqlite3.Connection:
    conn = connect(":memory:")
    apply_schema(conn)
    for sid in ("p1", "p2"):
        conn.execute(
            "INSERT INTO sources VALUES (?, 'synthetic', ?, 'file_system', 'f', '0', NULL, NULL,"
            " NULL, '2026-05-01T00:00:00Z')",
            (sid, fidelity),
        )
    conn.executemany(
        "INSERT INTO devices VALUES (?, ?, 'x', 'phone', NULL, NULL, ?)",
        [("dev:p1", "p1", "America/New_York"), ("dev:p2", "p2", tz2)],
    )
    conn.executemany(
        "INSERT INTO accounts VALUES (?, ?, 'x', ?, ?, ?, ?)",
        [
            ("a:p1:own", "p1", "dev:p1", "SMS", "+15550000001", None),
            ("a:p1:b", "p1", None, "SMS", "+1 555 000 0002", "Bee"),
            ("a:p1:c", "p1", None, "SMS", "+15550000003", "Cee"),
            ("a:p2:own", "p2", "dev:p2", "SMS", "+15550000002", None),
            ("a:p2:a", "p2", None, "SMS", "+15550000001", "Ay"),
        ],
    )
    conn.executemany(
        "INSERT INTO threads VALUES (?, ?, 'x', NULL, 'SMS', NULL)", [("t1", "p1"), ("t2", "p2")]
    )
    msgs = [
        # id, source, thread, sender, ts_utc, body, recipient
        ("msg:p1:1", "p1", "t1", "a:p1:own", "2026-02-01T12:00:00Z", "start of data", "a:p1:c"),
        ("msg:p1:2", "p1", "t1", "a:p1:b", "2026-03-10T15:00:00Z", "see you at noon", "a:p1:own"),
        ("msg:p1:3", "p1", "t1", "a:p1:own", "2026-03-10T15:00:30Z", "ok", "a:p1:b"),
        ("msg:p1:4", "p1", "t1", "a:p1:c", "2026-03-11T15:00:00Z", "ok", "a:p1:own"),
        ("msg:p1:5", "p1", "t1", None, None, "no time here", "a:p1:own"),
        ("msg:p1:6", "p1", "t1", "a:p1:own", "2026-04-30T12:00:00Z", "end of data", "a:p1:c"),
        ("msg:p2:1", "p2", "t2", "a:p2:own", "2026-02-01T12:00:00Z", "start of data", "a:p2:a"),
        ("msg:p2:2", "p2", "t2", "a:p2:own", "2026-03-10T15:00:00Z", "see you at noon", "a:p2:a"),
        ("msg:p2:3", "p2", "t2", "a:p2:own", "2026-04-30T12:00:00Z", "end of data", "a:p2:a"),
    ]
    for mid, sid, tid, sender, ts, body, to in msgs:
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
            " ts_utc, body) VALUES (?, ?, 'x', ?, ?, 'unknown', ?, ?)",
            (mid, sid, tid, sender, ts, body),
        )
        conn.execute(
            "INSERT INTO message_recipients (message_id, account_id) VALUES (?, ?)", (mid, to)
        )
    stipulate(conn, A, "Ay", "dev:p1")
    stipulate(conn, B, "Bee", "dev:p2")
    return conn


def without_undated_row(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("DELETE FROM message_recipients WHERE message_id = 'msg:p1:5'")
    conn.execute("DELETE FROM messages WHERE id = 'msg:p1:5'")
    return conn


def test_absence_passes_only_on_full_extractions_that_cover_the_window() -> None:
    r = check(without_undated_row(build()), "no_contact", person_ids=[A, B], window=APRIL)
    assert r.outcome is CheckOutcome.PASS
    assert "full extraction" in r.detail
    assert r.source_ids == ("p1", "p2")


def test_absence_on_a_curated_report_is_inconclusive() -> None:
    conn = without_undated_row(build("curated_report"))
    r = check(conn, "no_contact", person_ids=[A, B], window=APRIL)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "curated report" in r.detail


def test_absence_outside_the_data_span_is_inconclusive() -> None:
    june = window(D(2026, 6, 1), D(2026, 6, 10), "June 1 to 9")
    r = check(without_undated_row(build()), "no_contact", person_ids=[A, B], window=june)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "do not span the window" in r.detail


def test_absence_on_an_app_with_no_records_is_inconclusive() -> None:
    conn = without_undated_row(build())
    r = check(conn, "no_contact", person_ids=[A, B], channels=["WhatsApp"], window=APRIL)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "no WhatsApp records" in r.detail


def test_absence_with_an_unplaceable_row_is_inconclusive() -> None:
    # An undated message between the two, and one to A with no sender: either may be contact.
    conn = build()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, body) VALUES ('msg:p1:7', 'p1', 'x', 't1', 'a:p1:b', 'unknown', NULL, 'hm')"
    )
    conn.execute(
        "INSERT INTO message_recipients (message_id, account_id) VALUES ('msg:p1:7', 'a:p1:own')"
    )
    r = check(conn, "no_contact", person_ids=[A, B], window=APRIL)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert r.record_ids == ("msg:p1:5", "msg:p1:7")


def test_absence_fails_on_contact_matching_numbers_across_formats() -> None:
    r = check(build(), "no_contact", person_ids=[A, B], window=MARCH)
    assert r.outcome is CheckOutcome.FAIL
    # "+1 555 000 0002" on p1 is the same number as p2's own +15550000002.
    assert {"msg:p1:2", "msg:p1:3", "msg:p2:2"} <= set(r.record_ids)
    assert "msg:p1:4" not in r.record_ids  # from a third party


def test_unknown_person_cannot_be_searched() -> None:
    r = check(build(), "no_contact", person_ids=[A, "person:nobody"], window=APRIL)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "no confirmed stipulation or confirmed link" in r.detail


def test_rejected_stipulation_is_not_used() -> None:
    conn = build()
    conn.execute("UPDATE stipulations SET status = 'rejected' WHERE person_id = ?", (B,))
    r = check(conn, "no_contact", person_ids=[A, B], window=MARCH)
    assert r.outcome is CheckOutcome.INCONCLUSIVE


def test_proposed_stipulation_is_not_ownership() -> None:
    conn = build()
    conn.execute(
        "UPDATE stipulations SET status = 'proposed', decided_by = NULL, decided_at_utc = NULL"
        " WHERE person_id = ?",
        (B,),
    )
    r = check(conn, "no_contact", person_ids=[A, B], window=MARCH)
    assert r.outcome is CheckOutcome.INCONCLUSIVE  # would be a fail if B's phone counted
    assert "is proposed, not confirmed" in r.detail
    s = check(conn, "sender", quoted_text="see you at noon", person_ids=[B], device_ids=["dev:p2"])
    assert s.outcome is CheckOutcome.INCONCLUSIVE


def test_confirmed_identity_link_adds_an_account() -> None:
    conn = build()
    conn.execute("INSERT INTO persons VALUES ('person:c', 'Cee', 'expert:test')")
    conn.execute(
        "INSERT INTO identity_links VALUES ('link:1', 'a:p1:c', 'person:c', 'confirmed',"
        " 'confirmed', 'expert said so', 'expert:test', '2026-10-07T00:00:00Z')"
    )
    r = check(conn, "no_contact", person_ids=[A, "person:c"], window=MARCH)
    assert r.outcome is CheckOutcome.FAIL
    assert r.record_ids == ("msg:p1:4",)


def test_count_and_its_limits() -> None:
    conn = build()
    common = dict(person_ids=[A, B], device_ids=["dev:p1"], window=MARCH)
    assert check(conn, "message_count", expected_count=2, count_op="eq", **common).outcome is (
        CheckOutcome.PASS
    )
    assert check(conn, "message_count", expected_count=1, count_op="eq", **common).outcome is (
        CheckOutcome.FAIL
    )
    # A full extraction can pass "at most".
    assert check(conn, "message_count", expected_count=5, count_op="le", **common).outcome is (
        CheckOutcome.PASS
    )


def test_count_over_rows_the_tool_numbered_as_copies_neither_passes_nor_fails() -> None:
    import json

    conn = build()
    conn.execute(
        "INSERT INTO source_coverage VALUES ('p1', 'cellebrite_excel', '0.3.0', ?)",
        (json.dumps({"numbered_copy_records": ["msg:p1:3"]}),),
    )
    common = dict(person_ids=[A, B], device_ids=["dev:p1"], window=MARCH)
    for want in (1, 2):
        r = check(conn, "message_count", expected_count=want, count_op="eq", **common)
        assert r.outcome is CheckOutcome.INCONCLUSIVE
        assert "1 of the matching messages is numbered by the extraction tool" in r.detail
        assert not FORBIDDEN_WORDS.search(r.detail), r.detail


def test_count_detail_never_uses_forbidden_words() -> None:
    # Baker reports the source's deletion flag; it never says a record was deleted.
    conn = build()
    conn.execute("UPDATE messages SET deleted_flag = 1 WHERE id = 'msg:p1:2'")
    r = check(conn, "message_count", person_ids=[A, B], device_ids=["dev:p1"], window=MARCH,
              expected_count=2, count_op="eq")  # fmt: skip
    assert "1 of them carry the source's deletion flag" in r.detail
    assert not FORBIDDEN_WORDS.search(r.detail), r.detail
    assert not FORBIDDEN_WORDS.search(r.searched), r.searched
    check_report_text(f"<td>{r.detail}</td>")  # the report renders the detail as Baker's text


def test_count_on_a_phone_in_no_source_is_inconclusive() -> None:
    r = check(build(), "message_count", person_ids=[A, B], device_ids=["dev:zz"], window=MARCH,
              expected_count=1, count_op="eq")  # fmt: skip
    assert r.outcome is CheckOutcome.INCONCLUSIVE


def test_time_with_no_usable_timestamp_is_inconclusive() -> None:
    r = check(build(), "record_time", quoted_text="no time here", window=MARCH)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "No usable time" in r.detail


def test_time_reports_each_record_in_its_own_phones_zone() -> None:
    # 15:00Z is 11:00 in New York (p1) and 10:00 in Chicago (p2).
    w = window(D(2026, 3, 10, 11), D(2026, 3, 10, 12), "11 a.m. New York time")
    r = check(build(), "record_time", quoted_text="see you at noon", person_ids=[A, B], window=w)
    assert r.outcome is CheckOutcome.PASS
    assert "2026-03-10 11:00:00 EDT" in r.detail and "2026-03-10 10:00:00 CDT" in r.detail
    assert "p2's phone is set to America/Chicago" in r.detail


def test_time_with_unknown_phone_zone_is_said() -> None:
    w = window(D(2026, 3, 10, 11), D(2026, 3, 10, 12), "11 a.m.")
    r = check(build(tz2=None), "record_time", quoted_text="see you at noon", device_ids=["dev:p2"],
              window=w)  # fmt: skip
    assert r.outcome is CheckOutcome.PASS  # the UTC comparison does not need the phone's zone
    assert "does not say its phone's time zone" in r.detail


def test_sender_with_mixed_senders_is_inconclusive() -> None:
    r = check(build(), "sender", quoted_text="ok", person_ids=[A])
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "different or unknown senders" in r.detail


def test_sender_never_matches_part_of_a_word() -> None:
    r = check(build(), "sender", quoted_text="see you at no", person_ids=[A])
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "Not found does not mean" in r.detail


def test_check_refuses_an_assumption_from_another_template() -> None:
    a = instantiate("C1", "no_contact", {"person_ids": [A, B], "window": MARCH})
    r = CHECKS["count"].run(a, build())
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "does not apply" in r.searched


def test_checks_never_write_to_the_database() -> None:
    conn = build()
    before = conn.total_changes
    check(conn, "no_contact", person_ids=[A, B], window=MARCH)
    check(conn, "message_count", person_ids=[A, B], device_ids=["dev:p1"], window=MARCH,
          expected_count=2, count_op="eq")  # fmt: skip
    check(conn, "same_account", channels=["SMS"], handles=["Bee", "Ay"])
    assert conn.total_changes == before


def test_run_checks_ids_follow_the_contract() -> None:
    a = instantiate("C1", "no_contact", {"person_ids": [A, B], "window": MARCH})
    (r,) = run_checks(a, build())
    assert r.id == f"chk:{a.id}|absence@1.0.1"
    assert r.assumption_id == a.id and r.searched


@pytest.mark.parametrize("name", sorted(CHECKS))
def test_every_check_has_a_name_and_version(name: str) -> None:
    assert CHECKS[name].name == name and CHECKS[name].version


def test_pipeline_hooks() -> None:
    from core.audit import assumptions, checks, quotes

    conn = build()
    assert quotes.create(conn) is quotes.verify_quote
    all_checks = checks.create(conn)
    a = instantiate("C1", "no_contact", {"person_ids": [A, B], "window": MARCH})
    assert [c.name for c in all_checks if c.applies_to(a)] == ["absence"]
    claim = Claim(id="C1", paragraph_id="p", text="t", claim_type=ClaimType.ABSENCE,
                  status=ClaimStatus.ACCEPTED)  # fmt: skip
    assert assumptions.create(conn).build(claim) == []  # no filler: nothing proposed


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("see you next monday", "qualified"),
        ("monday or tuesday works", "exactly one weekday"),
        ("no day here", "exactly one weekday"),
    ],
)
def test_weekday_ambiguity_is_inconclusive(body: str, why: str) -> None:
    conn = build()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, body) VALUES ('msg:p1:9', 'p1', 'x', 't1', 'a:p1:own', 'unknown',"
        " '2026-03-06T23:00:00Z', ?)",
        (body,),
    )
    day = window(D(2026, 3, 9), D(2026, 3, 10), "Monday")
    r = check(conn, "weekday_date", quoted_text=body, window=day)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert why in r.detail


def test_weekday_named_on_that_same_weekday_is_open() -> None:
    conn = build()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, body) VALUES ('msg:p1:9', 'p1', 'x', 't1', 'a:p1:own', 'unknown',"
        " '2026-03-09T15:00:00Z', 'monday it is')"
    )  # a Monday in New York
    day = window(D(2026, 3, 9), D(2026, 3, 10), "Monday")
    r = check(conn, "weekday_date", quoted_text="monday it is", window=day)
    assert r.outcome is CheckOutcome.INCONCLUSIVE


def test_weekday_uses_the_phones_date_not_utc() -> None:
    # 02:00Z on Saturday Mar 7 is Friday Mar 6, 9 p.m. in New York, so "saturday" is Mar 7.
    # Read in UTC it would be sent on a Saturday, and the day would be open.
    conn = build()
    conn.execute(
        "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
        " ts_utc, body) VALUES ('msg:p1:9', 'p1', 'x', 't1', 'a:p1:own', 'unknown',"
        " '2026-03-07T02:00:00Z', 'brunch saturday')"
    )
    day = window(D(2026, 3, 7), D(2026, 3, 8), "Saturday, March 7")
    assert check(conn, "weekday_date", quoted_text="brunch saturday", window=day).outcome is (
        CheckOutcome.PASS
    )


def _forwarded(conn: sqlite3.Connection, source_id: str, *ids: str, reason: str = "forwarded"):
    """What an importer writes for messages the extraction marks as forwarded."""
    import json

    conn.execute(
        "INSERT INTO source_coverage VALUES (?, 'synthetic', '0', ?)",
        (source_id, json.dumps({"forwarded_records": {reason: list(ids)}})),
    )
    return conn


@pytest.mark.parametrize("reason", ["forwarded", "embedded"])
def test_sender_never_credits_forwarded_words_to_the_forwarder(reason: str) -> None:
    args = {"quoted_text": "see you at noon", "person_ids": [B], "device_ids": ["dev:p2"]}
    assert check(build(), "sender", **args).outcome is CheckOutcome.PASS
    r = check(_forwarded(build(), "p2", "msg:p2:2", reason=reason), "sender", **args)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "msg:p2:2 on SMS is marked as forwarded" in r.detail
    assert "was sent by" not in r.detail


def test_any_check_resting_on_a_forwarded_message_is_inconclusive() -> None:
    w = window(D(2026, 3, 10, 11), D(2026, 3, 10, 12), "11 a.m. New York time")
    args = {"quoted_text": "see you at noon", "person_ids": [A, B], "window": w}
    assert check(build(), "record_time", **args).outcome is CheckOutcome.PASS
    r = check(_forwarded(build(), "p1", "msg:p1:2"), "record_time", **args)
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "Inconclusive (forwarded rule 2)" in r.detail and "msg:p1:2" in r.detail
    # a forwarded message the outcome does not rest on changes nothing
    other = check(_forwarded(build(), "p1", "msg:p1:6"), "record_time", **args)
    assert other.outcome is CheckOutcome.PASS


def _with_embedded_copies(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Copies the UFDR importer imports from inside other messages (locator .../Embedded[n]),
    marked forwarded and listed as embedded_copy. Dated here on purpose, to show the checks
    leave them out even when they carry a time."""
    import json

    copies = [
        # a copy of "see you at noon" between A and B in March: would inflate the count
        ("msg:p1:e1", "x/Embedded[1]", "a:p1:b", "2026-03-10T15:00:00Z", "see you at noon"),
        # a copy dated in April between A and B: would break the absence
        ("msg:p1:e2", "x/Embedded[2]", "a:p1:b", "2026-04-05T15:00:00Z", "ok"),
    ]
    for mid, loc, sender, ts, body in copies:
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id, direction,"
            " ts_utc, body, forwarded) VALUES (?, 'p1', ?, 't1', ?, 'unknown', ?, ?, 1)",
            (mid, loc, sender, ts, body),
        )
        conn.execute(
            "INSERT INTO message_recipients (message_id, account_id) VALUES (?, 'a:p1:own')",
            (mid,),
        )
    conn.execute(
        "INSERT INTO source_coverage VALUES ('p1', 'synthetic', '0', ?)",
        (json.dumps({"forwarded_records": {"embedded_copy": ["msg:p1:e1", "msg:p1:e2"]}}),),
    )
    return conn


@pytest.mark.parametrize(
    ("template", "params"),
    [
        ("message_count", dict(person_ids=[A, B], device_ids=["dev:p1"], window=MARCH,
                               expected_count=2, count_op="eq")),
        ("no_contact", dict(person_ids=[A, B], window=APRIL)),
    ],
)  # fmt: skip
def test_embedded_copies_are_not_counted(template, params) -> None:
    """A copy carried inside another message is never counted beside the message it copies:
    count and absence outcomes and wording are the same as for the case without the copies."""
    plain = check(without_undated_row(build()), template, **params)
    with_copies = check(_with_embedded_copies(without_undated_row(build())), template, **params)
    assert plain.outcome is CheckOutcome.PASS
    assert with_copies.outcome is CheckOutcome.PASS
    assert with_copies.detail == plain.detail
    assert set(with_copies.record_ids) == set(plain.record_ids)
    assert not {"msg:p1:e1", "msg:p1:e2"} & set(with_copies.record_ids)


@pytest.mark.parametrize(
    ("template", "params"),
    [
        ("record_time", dict(quoted_text="see you at noon", person_ids=[A, B],
                             window=window(D(2026, 3, 10, 11), D(2026, 3, 10, 12),
                                           "11 a.m. New York time"))),
        # both phones: the copy sits on p1, and a sender check reads only the phones it names
        ("sender", dict(quoted_text="see you at noon", person_ids=[B],
                        device_ids=["dev:p1", "dev:p2"])),
    ],
)  # fmt: skip
def test_a_copy_carrying_the_quoted_words_makes_the_check_inconclusive(template, params) -> None:
    """A quote-picked check keeps a copy that carries the same words: the copy's sender and
    time are not verified, so the outcome is inconclusive and names the copy."""
    plain = check(without_undated_row(build()), template, **params)
    with_copies = check(_with_embedded_copies(without_undated_row(build())), template, **params)
    assert plain.outcome is CheckOutcome.PASS
    assert with_copies.outcome is CheckOutcome.INCONCLUSIVE
    assert "msg:p1:e1" in with_copies.record_ids


def test_a_copy_recipient_is_not_a_participant_of_the_thread_that_carried_it() -> None:
    """A thread titled with the handle names its real participants only: the recipient of an
    embedded copy inside it is the copy's addressee, not someone in that conversation."""
    from core.audit.checks._common import CaseData, resolve_handle

    conn = build()
    conn.execute("INSERT INTO threads VALUES ('t3', 'p1', 'x', NULL, 'SMS', 'Zed')")
    for mid, loc, sender, to in (
        ("msg:p1:z1", "x", "a:p1:c", "a:p1:own"),
        ("msg:p1:z2", "x/Embedded[1]", "a:p1:own", "a:p1:b"),
    ):
        conn.execute(
            "INSERT INTO messages (id, source_id, locator, thread_id, sender_account_id,"
            " direction, body) VALUES (?, 'p1', ?, 't3', ?, 'unknown', 'hi')",
            (mid, loc, sender),
        )
        conn.execute(
            "INSERT INTO message_recipients (message_id, account_id) VALUES (?, ?)", (mid, to)
        )
    data = CaseData(conn)
    assert resolve_handle(data, "Zed", None).keys == {data.accounts["a:p1:c"].key}


def test_handle_resolving_checks_record_the_version_that_skips_copy_recipients() -> None:
    """Handle resolution changed (embedded copies' recipients are no longer thread
    participants), so every check resolving handles records a bumped version."""
    r = check(build(), "sender", quoted_text="see you at noon", person_ids=[B],
              device_ids=["dev:p2"])  # fmt: skip
    assert r.id.endswith("|sender@1.0.2")
    assert {CHECKS[n].version for n in ("absence", "same_account")} == {"1.0.1"}
    # The checks that match a quote's text record the fold (curly quotes, runs of spaces).
    assert {CHECKS[n].version for n in ("sender", "weekday")} == {"1.0.2"}
    assert CHECKS["time"].version == "1.0.3"  # and a call is on the app named beside "call"
    assert CHECKS["count"].version == "1.1.0"  # and counts calls (validation fill f)


def _typed(conn: sqlite3.Connection, body: str) -> sqlite3.Connection:
    conn.execute("UPDATE messages SET body = ? WHERE id = 'msg:p2:2'", (body,))
    return conn


@pytest.mark.parametrize(
    ("body", "quoted"),
    [
        ("I\u2019m at the dock", "I'm at the dock"),  # the phone kept a curly apostrophe
        ("I'm at the dock", "I\u2019m at the dock"),  # the claim has one
        ("He said \u201cgo\u201d now", 'He said "go" now'),
        ("Yay!  Do we go?", "Yay! Do we go?"),  # two spaces in the export, one in the claim
        ("Yay!\nDo we go?", "Yay! Do we go?"),
        ("Yay! Do we go?", "Yay!  Do we go?"),  # the fold applies to both sides
    ],
)
def test_the_text_match_reads_curly_quotes_as_straight_and_space_runs_as_one(
    body: str, quoted: str
) -> None:
    conn = _typed(build(), body)
    r = check(conn, "sender", quoted_text=quoted, person_ids=[B], device_ids=["dev:p2"])
    assert r.outcome is CheckOutcome.PASS and r.record_ids == ("msg:p2:2",)
    assert "curly quotes read as straight and runs of spaces as one" in r.searched
    t = check(conn, "record_time", quoted_text=quoted, person_ids=[B], window=MARCH)
    assert t.outcome is CheckOutcome.PASS and t.record_ids == ("msg:p2:2",)


@pytest.mark.parametrize(
    "quoted",
    [
        "Im at the dock",  # a missing apostrophe is not folded in
        "I`m at the dock",  # nor is a backtick
        "I'm at the do",  # still word-aligned
        "i'm at the dock",  # and case still counts
    ],
)
def test_the_fold_changes_nothing_else(quoted: str) -> None:
    conn = _typed(build(), "I\u2019m at the dock")
    r = check(conn, "sender", quoted_text=quoted, person_ids=[B], device_ids=["dev:p2"])
    assert r.outcome is CheckOutcome.INCONCLUSIVE and "Not found does not mean" in r.detail


def test_quote_verification_stays_exact() -> None:
    from core.audit.quotes import verify_quote

    assert not verify_quote("I'm at the dock", "I\u2019m at the dock")
    assert not verify_quote("Yay! Do", "Yay!  Do")


def _with_calls(
    conn: sqlite3.Connection, times: list[str], durations: list[int | None] | None = None
) -> sqlite3.Connection:
    for i, ts in enumerate(times):
        conn.execute(
            "INSERT INTO calls (id, source_id, locator, device_id, app, from_account_id,"
            " to_account_id, direction, ts_utc, duration_s) VALUES (?, 'p1', 'x', 'dev:p1',"
            " 'SMS', 'a:p1:own', 'a:p1:b', 'outgoing', ?, ?)",
            (f"call:p1:{i}", ts, 60 if durations is None else durations[i]),
        )
    return conn


def test_a_count_of_calls_counts_calls_and_never_fails() -> None:
    # Fill f: with 'call' among the channels the count check counts calls, not messages.
    conn = _with_calls(build(), ["2026-03-10T15:00:00Z", "2026-03-12T15:00:00Z"])
    common = dict(person_ids=[A, B], device_ids=["dev:p1"], window=MARCH, channels=["call"])
    r = check(conn, "message_count", expected_count=2, count_op="eq", **common)
    assert r.outcome is CheckOutcome.PASS, r.detail
    assert r.record_ids == ("call:p1:0", "call:p1:1") and "Counted 2 calls" in r.detail
    # More rows than the claim says is no fail: calls that did not connect stay in the log.
    r = check(conn, "message_count", expected_count=1, count_op="eq", **common)
    assert r.outcome is CheckOutcome.INCONCLUSIVE and "never fails" in r.detail
    # Another app's calls are not counted when an app is named.
    r = check(conn, "message_count", expected_count=2, count_op="eq",
              **{**common, "channels": ["call", "Signal"]})  # fmt: skip
    assert r.outcome is CheckOutcome.INCONCLUSIVE and "Counted 0 calls" in r.detail


def test_a_call_with_no_length_may_not_have_connected() -> None:
    # A zero or missing length leaves the count open: "spoke twice" needs two connected calls.
    common = dict(person_ids=[A, B], device_ids=["dev:p1"], window=MARCH, channels=["call"])
    for durations in ([60, 0], [60, None]):
        conn = _with_calls(build(), ["2026-03-10T15:00:00Z", "2026-03-12T15:00:00Z"], durations)
        for op in ("eq", "ge"):
            r = check(conn, "message_count", expected_count=2, count_op=op, **common)
            assert r.outcome is CheckOutcome.INCONCLUSIVE, (durations, op, r.detail)
            assert "may not have connected" in r.detail
            assert not FORBIDDEN_WORDS.search(r.detail), r.detail
    # The source's deletion flag is named, as for messages, and does not change the outcome.
    conn = _with_calls(build(), ["2026-03-10T15:00:00Z", "2026-03-12T15:00:00Z"])
    conn.execute("UPDATE calls SET deleted_flag = 1 WHERE id = 'call:p1:0'")
    r = check(conn, "message_count", expected_count=2, count_op="eq", **common)
    assert r.outcome is CheckOutcome.PASS and "1 of them carry the source's deletion" in r.detail


def test_two_calls_seconds_apart_may_be_one_call_stored_twice() -> None:
    conn = _with_calls(build(), ["2026-03-10T15:00:00Z", "2026-03-10T15:00:12Z"])
    r = check(conn, "message_count", person_ids=[A, B], device_ids=["dev:p1"], window=MARCH,
              channels=["call"], expected_count=2, count_op="eq")  # fmt: skip
    assert r.outcome is CheckOutcome.INCONCLUSIVE
    assert "may hold one call twice" in r.detail
    assert not FORBIDDEN_WORDS.search(r.detail), r.detail
