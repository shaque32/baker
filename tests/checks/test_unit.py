"""Deterministic checks on a tiny hand-built case. Every value is invented."""

import sqlite3
from datetime import datetime as D

import pytest

from core.audit.assumptions import instantiate
from core.audit.checks import CHECKS, run_checks
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
    assert r.id == f"chk:{a.id}|absence@1.0.0"
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
