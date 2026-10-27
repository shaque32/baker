"""Real affidavit wording the filler reads by code: the date first and then its time, a zone
written beside the time, and the names real exports give apps. All wording here is made up
for these tests, on synthetic case01 (phones in America/New_York).
"""

import re
import sqlite3
from datetime import UTC
from datetime import datetime as D
from pathlib import Path

import pytest

from core.audit.assumption_filler import (
    LocalAssumptionFiller,
    Reject,
    _ProposalOut,
    _Window,
    check_window,
    stated_windows,
    written_zone,
)
from core.contracts import Claim, ClaimStatus, ClaimType
from eval.synthetic.generate import generate
from tests.checks.helpers import stipulate
from tests.fake_model import FakeModel

ROOT = Path(__file__).parents[1]
PETROV, REYES = "person:petrov", "person:reyes"
QUOTE = "need 2 more by friday"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    out = tmp_path_factory.mktemp("case01")
    db = out / "case01.db"
    generate(out, db)
    c = sqlite3.connect(db)
    stipulate(c, PETROV, "Daniel Petrov", "dev:item1")
    stipulate(c, REYES, "Marcus Reyes", "dev:item2")
    c.execute("PRAGMA foreign_keys = OFF")
    for i, app in enumerate(("Wickr Pro", "Kik Messenger", "Microsoft Teams", "Native Messages")):
        c.execute(
            "INSERT INTO threads (id, source_id, locator, device_id, app, title)"
            " VALUES (?, 'src:none', ?, 'dev:item1', ?, NULL)",
            (f"thr:wording:{i}", f"wording/{i}", app),
        )
    yield c
    c.close()


def filler(conn) -> LocalAssumptionFiller:
    template = "{claim} {paragraph} {templates} {channels}"
    return LocalAssumptionFiller(FakeModel("{}"), conn, template=template)


def claim(text: str, kind: ClaimType = ClaimType.COMMUNICATION) -> Claim:
    return Claim(id="X", paragraph_id="para:none", text=text, claim_type=kind,
                 status=ClaimStatus.ACCEPTED)  # fmt: skip


def proposal(template_id: str = "record_time", **kw) -> _ProposalOut:
    base = dict(people=["PETROV"], accounts=[], handles=[], phones=[], channels=[],
                quoted_text=QUOTE, count=None, duration=None, window=None)  # fmt: skip
    return _ProposalOut.model_validate({"template_id": template_id, **base, **kw})


def W(as_written: str, start: str, end: str, zone: str = "phone") -> dict:  # noqa: N802
    return {"as_written": as_written, "start": start, "end": end, "zone": zone}


# ---------------------------------------------------------------- stated_windows


@pytest.mark.parametrize(
    ("text", "start", "end", "zone"),
    [
        (
            "On January 9, 2026, at approximately 7:58 p.m. EST, Item 1 placed a call.",
            "19:50",
            "20:06",
            "EST",
        ),
        ("On January 9, 2026, at 2:31 a.m., Item 1 placed a call.", "02:31", "02:32", None),
        ("On Friday, January 9, 2026, at about noon ET, Item 1 called.", "11:52", "12:08", "ET"),
        ("On January 9, 2026, around 4:10 p.m. (EST), Item 1 called.", "16:02", "16:18", "EST"),
        (
            "On January 9, 2026, between 9 and 11 p.m. EST, Item 1 sent texts.",
            "21:00",
            "23:01",
            "EST",
        ),  # fmt: skip
        (
            "On January 9, 2026, from 9 p.m. to 11 p.m. Eastern Time, Item 1 sent texts.",
            "21:00",
            "23:01",
            "Eastern Time",
        ),
        (
            "At approximately 7:58 p.m. EST on January 9, 2026, Item 1 placed a call.",
            "19:50",
            "20:06",
            "EST",
        ),
        (
            "Between 9 and 11 p.m. EST on January 9, 2026, Item 1 sent texts.",
            "21:00",
            "23:01",
            "EST",
        ),  # fmt: skip
    ],
)
def test_the_date_first_and_a_written_zone_are_read(text, start, end, zone):
    (w,) = stated_windows(text)
    assert (w.start.strftime("%H:%M"), w.end.strftime("%H:%M"), w.zone) == (start, end, zone)
    assert w.start.date() == D(2026, 1, 9).date()
    assert w.raw in text
    check_window(w.start, w.end, w.raw, text, "", "record_time")


@pytest.mark.parametrize(
    "text",
    [
        # a second time, joined to the first
        "On January 9, 2026, at approximately 7:58 p.m. and 8:15 p.m. EST, Item 1 called.",
        "On January 9, 2026, beginning at approximately 8:00 p.m., Item 1 placed calls.",
        "On January 9, 2026, there was no contact between them after 10:00 a.m. EST.",
        "On January 9, 2026, Item 1 called REYES at 9:15 p.m.",  # the time is not tied
        "On January 9, 2026, between approximately 9:10 and 9:40 p.m., Item 1 sent texts.",
        "between January 9, 2026 at 9 p.m. and January 10, 2026 at 1 a.m., Item 1 called.",
        "from January 9, 2026, at 9 p.m., Item 1 called REYES.",
        "On January 9, 2026, between 9 and 11, Item 1 called.",  # no a.m. or p.m.
        "On January 9, 2026, at 21:00, Item 1 called.",
        "On January 9, 2026, at midnight, Item 1 called.",
        "On January 9 and 10, 2026, at 9 p.m., Item 1 called.",  # one time on two days
    ],
)
def test_a_time_no_range_reads_is_never_widened_to_the_whole_day(text):
    assert stated_windows(text) is None


def test_a_zone_right_after_a_plain_date_is_kept():
    (w,) = stated_windows("On March 3, 2026 (UTC), Item 1 called.")
    assert (w.raw, w.zone, w.start, w.end) == (
        "On March 3, 2026 (UTC)",
        "UTC",
        D(2026, 3, 3),
        D(2026, 3, 4),
    )
    (w,) = stated_windows("On January 9, 2026, EST, Item 1 called.")
    assert w.zone == "EST"
    (w,) = stated_windows("On March 3, 2026, PT and Item 1 spoke.")  # initials, not a zone
    assert (w.raw, w.zone) == ("On March 3, 2026", None)
    (w,) = stated_windows("At 9:15 p.m. on March 3, 2026 (UTC), Item 1 called.")
    assert (w.zone, w.start.strftime("%H:%M")) == ("UTC", "21:15")


def test_a_count_after_the_date_is_not_a_time():
    (w,) = stated_windows("On January 9, 2026, between 10 and 12 messages were sent.")
    assert (w.start, w.end) == (D(2026, 1, 9), D(2026, 1, 10))


def test_written_zone_reads_only_a_zone_right_after_a_time():
    assert written_zone("On July 9, 2026, at 7:58 p.m. (EDT)") == "EDT"
    assert written_zone("at about 7:58 p.m.", "On July 9, 2026, at about 7:58 p.m. EDT, X") == (
        "EDT"
    )
    assert written_zone("At 9 p.m. on May 2, 2026 at the MT office") is None
    assert written_zone("On July 3, 2026 (EST)") == "EST"
    assert written_zone("On July 3, 2026", "On July 3, 2026, EST, X called") == "EST"
    assert written_zone("On July 3, 2026", "On July 3, 2026, PT called") is None  # initials
    assert written_zone("at 9 p.m. est") is None  # abbreviations only in capitals
    with pytest.raises(Reject, match="more than one time zone"):
        written_zone("between 9 p.m. EDT and 10 p.m. CDT")


# ---------------------------------------------------------------- the zone, checked by code


def _window(conn, text: str, w: dict | None):
    return filler(conn)._resolve(claim(text), "", proposal(window=w)).params["window"]


def test_the_claims_zone_wins_over_the_models(conn):
    # The model wrote UTC times and said UTC; the claim says EDT. check_window refuses the
    # model's times, and the claim's own range is read in the phone's zone, which is EDT then.
    text = f'On July 9, 2026, at approximately 7:58 p.m. EDT, PETROV wrote "{QUOTE}".'
    w = _window(conn, text, W("at approximately 7:58 p.m. EDT", "2026-07-09T23:50",
                              "2026-07-10T00:06", "UTC"))  # fmt: skip
    assert w.tz == "America/New_York"
    assert w.start_utc == D(2026, 7, 9, 23, 50, tzinfo=UTC)
    assert w.end_utc.replace(microsecond=0) == D(2026, 7, 10, 0, 5, 59, tzinfo=UTC)


def test_a_written_utc_is_read_as_utc_whatever_the_model_says(conn):
    text = f'At 11:58 p.m. UTC on July 9, 2026, PETROV wrote "{QUOTE}".'
    w = _window(conn, text, W("At 11:58 p.m. UTC on July 9, 2026", "2026-07-09T23:58",
                              "2026-07-09T23:59", "phone"))  # fmt: skip
    assert (w.tz, w.start_utc) == ("UTC", D(2026, 7, 9, 23, 58, tzinfo=UTC))


@pytest.mark.parametrize(
    ("text", "said"),
    [
        (f'On July 9, 2026, at 7:58 p.m. EST, PETROV wrote "{QUOTE}".', "EST (UTC-05:00)"),
        (f'On January 9, 2026, at 7:58 p.m. CST, PETROV wrote "{QUOTE}".', "CST (UTC-06:00)"),
        (f'At 7:58 p.m. CT on January 9, 2026, PETROV wrote "{QUOTE}".', "CT (UTC-06:00)"),
    ],
)
def test_a_zone_the_phone_is_not_in_then_is_refused(conn, text, said):
    with pytest.raises(Reject, match=r"the claim gives the time in " + re.escape(said)):
        _window(conn, text, None)


def test_a_zone_the_claim_writes_after_the_models_words_is_checked(conn):
    # The model's words stop before the zone; code still reads the zone that follows them.
    text = f'At 7:58 p.m. CST on January 9, 2026, PETROV wrote "{QUOTE}".'
    w = _Window.model_validate(W("At 7:58 p.m.", "2026-01-09T19:58", "2026-01-09T19:59"))
    with pytest.raises(Reject, match="CST"):
        filler(conn)._window(text, "", w, [], "record_time")


def test_a_whole_day_in_utc_is_read_in_utc(conn):
    text = f'On July 9, 2026 (UTC), PETROV wrote "{QUOTE}".'
    w = _window(conn, text, None)
    assert (w.tz, w.start_utc) == ("UTC", D(2026, 7, 9, tzinfo=UTC))
    w = _window(conn, text, W("On July 9, 2026 (UTC)", "2026-07-09T00:00", "2026-07-10T00:00",
                              "UTC"))  # fmt: skip
    assert (w.tz, w.start_utc) == ("UTC", D(2026, 7, 9, tzinfo=UTC))


def test_a_zone_after_the_models_date_is_checked(conn):
    text = f'On July 9, 2026 (EST), PETROV wrote "{QUOTE}".'
    w = _Window.model_validate(W("On July 9, 2026", "2026-07-09T00:00", "2026-07-10T00:00"))
    with pytest.raises(Reject, match=r"EST \(UTC-05:00\)"):
        filler(conn)._window(text, "", w, [], "record_time")


def test_a_zone_that_matches_the_phone_reads_as_before(conn):
    text = f'On January 9, 2026, at 7:58 p.m. EST, PETROV wrote "{QUOTE}".'
    w = _window(conn, text, None)
    assert (w.tz, w.start_utc) == ("America/New_York", D(2026, 1, 10, 0, 58, tzinfo=UTC))
    plain = f'On January 9, 2026, at 7:58 p.m., PETROV wrote "{QUOTE}".'
    assert _window(conn, plain, None).start_utc == w.start_utc


# ---------------------------------------------------------------- app names from real exports


@pytest.mark.parametrize(
    ("word", "app"),
    [
        ("Wickr", "Wickr Pro"),
        ("Kik", "Kik Messenger"),
        ("Teams", "Microsoft Teams"),
        ("iMessage", "Native Messages"),
    ],  # fmt: skip
)
def test_the_word_a_document_uses_names_the_exports_app(conn, word, app):
    text = f'On January 9, 2026, PETROV wrote "{QUOTE}" on {word}.'
    out = filler(conn)._resolve(claim(text), "", proposal("sender", channels=[app]))
    assert out.params["channels"] == [app]


def test_a_word_two_apps_go_by_is_refused(conn):
    # case01 has an SMS app, so "texted" could be SMS or Native Messages
    text = f'On January 9, 2026, PETROV texted "{QUOTE}".'
    with pytest.raises(Reject, match="could be 'Native Messages' or 'SMS'"):
        filler(conn)._resolve(claim(text), "", proposal("sender", channels=["Native Messages"]))
    vocab = {"wickr pro": "Wickr Pro", "wickr me": "Wickr Me"}
    with pytest.raises(Reject, match="could be 'Wickr Pro' or 'Wickr Me'"):
        LocalAssumptionFiller._alias("PETROV wrote on Wickr.", "Wickr Pro", vocab, "sender")


def test_no_count_is_read_from_an_app_that_holds_more_than_the_word_names(conn):
    text = "On January 9, 2026, PETROV sent REYES 3 iMessages."
    with pytest.raises(Reject, match="holds more than"):
        filler(conn)._resolve(claim(text, ClaimType.COUNT), "", proposal(
            "message_count", quoted_text="", people=["PETROV", "REYES"],
            channels=["Native Messages"], count={"value": 3}))  # fmt: skip


def test_an_app_the_claim_does_not_name_is_still_refused(conn):
    text = f'On January 9, 2026, PETROV wrote "{QUOTE}" on Signal.'
    with pytest.raises(Reject, match="does not name the channel 'Wickr Pro'"):
        filler(conn)._resolve(claim(text), "", proposal("sender", channels=["Wickr Pro"]))
