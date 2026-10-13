"""Reading the dates and times a government document states (core/timeline/stated.py).

Every sentence here is invented for the test.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from core.timeline.stated import ABOUT_MINUTES, StatedTime, read_paragraph


def read(text: str, doc_years: set[int] | None = None) -> list[StatedTime]:
    out = read_paragraph("para:t:1:1", 1, 1, "1", text, doc_years or set())
    for st in out:
        assert text[st.start_i : st.end_i] == st.raw  # always a verbatim slice
        assert st.sentence in text
    return out


def one(text: str, doc_years: set[int] | None = None) -> StatedTime:
    got = read(text, doc_years)
    assert len(got) == 1, [g.raw for g in got]
    return got[0]


def test_a_plain_date_is_the_whole_day():
    st = one("On March 12, 2026, the subject sent a message.")
    assert st.kind == "day"
    assert (st.start, st.end) == (datetime(2026, 3, 12), datetime(2026, 3, 13))
    assert st.text == "March 12, 2026"


def test_a_line_break_inside_a_date_still_reads():
    st = one("PETROV first made contact on March 12,\n2026, two days later.")
    assert st.start == datetime(2026, 3, 12)
    assert st.text == "March 12, 2026"


def test_ranges_end_after_their_last_day():
    st = one("They had no contact between March 20 and March 23, 2026.")
    assert st.kind == "range" and st.raw.startswith("between")
    assert (st.start, st.end) == (datetime(2026, 3, 20), datetime(2026, 3, 24))
    st = one("From March 10 through March 31, 2026, the phone recorded messages.")
    assert (st.start, st.end) == (datetime(2026, 3, 10), datetime(2026, 4, 1))
    st = one("The account was active March 20-23, 2026.")
    assert (st.start, st.end) == (datetime(2026, 3, 20), datetime(2026, 3, 24))


def test_and_joins_two_dates_into_a_range_only_after_between():
    got = read("Messages were sent on March 6 and March 9, 2026.")
    assert [g.kind for g in got] == ["day", "day"]


def test_open_ranges_leave_one_end_open():
    st = one("Before March 12, 2026, no message mentions the garage.")
    assert st.kind == "open" and st.start is None and st.end == datetime(2026, 3, 12)
    assert st.raw.startswith("Before")
    st = one("Since March 10, 2026, the handle reads @northstar.")
    assert st.kind == "open" and st.start == datetime(2026, 3, 10) and st.end is None
    st = one("After March 10, 2026, nothing was sent.")
    assert st.start == datetime(2026, 3, 11) and st.end is None


def test_a_time_of_day_before_or_after_the_date_is_one_moment():
    st = one("At 2:31 a.m. on March 5, 2026, the subject texted.")
    assert st.kind == "moment"
    assert (st.start, st.end) == (datetime(2026, 3, 5, 2, 31), datetime(2026, 3, 5, 2, 32))
    st = one("On March 14, 2026, at 10:05 p.m., a call came in.")
    assert st.start == datetime(2026, 3, 14, 22, 5)
    st = one("The call was placed March 14, 2026 at 22:05.")
    assert st.start == datetime(2026, 3, 14, 22, 5)


def test_about_is_eight_minutes_either_side():
    st = one("At about 7:58 p.m. on March 9, 2026, a call was placed.")
    assert st.approx
    about = timedelta(minutes=ABOUT_MINUTES)
    assert st.start == datetime(2026, 3, 9, 19, 58) - about
    assert st.end == datetime(2026, 3, 9, 19, 59) + about


def test_a_time_range_on_one_day():
    st = one("They met between 8 and 9 p.m. on March 9, 2026.")
    assert (st.start, st.end) == (datetime(2026, 3, 9, 20), datetime(2026, 3, 9, 21))


def test_a_zone_the_document_names_is_kept():
    st = one("At 2:31 a.m. UTC on March 5, 2026, the message was sent.")
    assert st.zone == "UTC" and st.zone_words == "UTC"
    st = one("At 9:31 p.m. EST on March 4, 2026, the message was sent.")
    assert st.zone == "Etc/GMT+5"


def test_numeric_dates_are_read_only_when_one_order_is_possible():
    assert one("Sent on 3/25/2026 at noon.").start == datetime(2026, 3, 25, 12)
    assert one("Sent on 25/3/2026.").start == datetime(2026, 3, 25)
    st = one("Sent on 3/5/2026.")
    assert st.kind == "ambiguous" and not st.compared
    assert st.readings == (date(2026, 3, 5), date(2026, 5, 3))
    assert one("Sent on 3/3/2026.").start == datetime(2026, 3, 3)  # same either way
    assert one("Sent on 2026-03-05.").start == datetime(2026, 3, 5)
    assert one("Sent on 3/5/26.").kind == "unread"


def test_a_missing_year_comes_from_the_paragraph_or_the_document_only_when_there_is_one():
    assert one("In 2026 the phone was seized. On March 12 a message was sent.").start == (
        datetime(2026, 3, 12)
    )
    assert one("On March 12 a message was sent.", {2026}).start == datetime(2026, 3, 12)
    st = one("On March 12 a message was sent.", {2025, 2026})
    assert st.kind == "unread" and "more than one" in st.note
    assert one("On March 12 a message was sent.").kind == "unread"


def test_dates_inside_quoted_words_belong_to_the_message():
    st = one('On March 12, 2026, he wrote "see you March 20 at 8 pm".')
    assert st.start == datetime(2026, 3, 12)


def test_a_weekday_is_checked_against_the_calendar():
    ok = one("They agreed to meet on Monday, March 9, 2026.")
    assert ok.weekday_ok is True and "the calendar agrees" in (ok.weekday_note or "")
    bad = one("They agreed to meet on Tuesday, March 9, 2026.")
    assert bad.weekday_ok is False and "it was a Monday" in (bad.weekday_note or "")


def test_on_or_about_is_that_day_and_noted():
    st = one("On or about March 12, 2026, the subject called.")
    assert st.kind == "day" and st.on_or_about and st.raw.lower().startswith("on or about")


def test_a_time_with_no_date_is_listed_not_guessed():
    got = read("On March 9, 2026 they talked. Later, at 9:15 p.m., he called.")
    kinds = sorted(g.kind for g in got)
    assert kinds == ["day", "unread"]
    assert next(g for g in got if g.kind == "unread").note.startswith("a time of day")


def test_an_impossible_date_is_not_read():
    st = one("On February 30, 2026, a message was sent.")
    assert st.kind == "unread" and st.note == "not a calendar date"
