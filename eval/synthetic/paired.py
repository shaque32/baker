"""Synthetic curated-report vs larger-source pairs for the paired selection audit. Everything here
is invented; no real case data.

Two pairs, each a curated Cellebrite-style Excel report and a UFDR package of the same phone that
holds more:

- **case01 item1**: the curated report is case01's own `item1.xlsx`, unchanged. The UFDR holds
  every record of it plus the records in PLANTED, PLANTED_CALLS and PLANTED_CONTACTS, and one
  message whose text differs (EDITED). PLANTED says what the paired audit must find for each.
- **pair02**: a small new story on item2's device, on 2026-03-29: a day past the 12th, so the
  report's dates read one way only (the Excel importer leaves a date such as 4/6 untimed).
  The report holds PAIR02_REPORT; the UFDR holds PAIR02_REPORT plus PAIR02_EXTRA.

    python -m eval.synthetic.paired --out eval/out/paired

writes item1.xlsx, item1-full.ufdr, pair02.xlsx and pair02-full.ufdr. The expectations below are
the generator's own key for its planted records, not gold labels: they say what was planted.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from eval.synthetic import case01_story as story
from eval.synthetic.case01_story import Call, Msg, et
from eval.synthetic.filler import make_filler
from eval.synthetic.generate import SEED, Rendered, render_device
from eval.synthetic.ufdr import case01_package, write_package
from eval.synthetic.xlsx import write_xlsx


@dataclass(frozen=True)
class Planted:
    """A record only the larger source holds, and what the paired audit must say about it."""

    msg: Msg
    state: str  # 'not_in_report' or 'may_be'
    near: tuple[str, ...] = ()  # claims it must be listed under (case01 claim ids)
    why: str = ""


# ---------------------------------------------------------------- case01 item1

# ¶6 (C05, C06) quotes "need 2 more by friday" (20:03:27 EDT) and "the package will be at
# marcs" (20:11:36) in the @northstar Telegram thread; ¶15 (C20) quotes "got the tickets"
# (12:42:09 EDT, 2026-03-25) in the SMS thread with Alex Turner.
PLANTED: tuple[Planted, ...] = (
    Planted(
        Msg("pp01", et("2026-03-12 20:06:30"), "pet_tg", "ns_tg", "or sunday works too"),
        "not_in_report", ("C05", "C06"), "between the two quotes of ¶6, 3 min 3 s after the first",
    ),
    Planted(
        Msg("pp02", et("2026-03-12 20:25:00"), "pet_tg", "ns_tg", "call me when ur close"),
        "not_in_report", ("C05", "C06"), "13 min 24 s after the last quote of ¶6",
    ),
    Planted(
        Msg("pp03", et("2026-03-12 19:55:00"), "pet_sms", "ilya_sms", "cant tonight, tmrw?"),
        "not_in_report", ("C05", "C06"), "another thread, 8 min 27 s before the first quote",
    ),
    Planted(
        Msg("pp04", et("2026-03-12 20:20:00"), "ns_tg", "pet_tg", "where r u"),
        "may_be", (), "same app and direction within an hour of a report message not found "
        "(EDITED), so it may be that message",
    ),
    Planted(
        Msg("pp05", et("2026-03-12 20:10:40"), "pet_tg", "ns_tg", "fine"),
        "may_be", (), "the report's 'fine' at 20:10:10 could be either, so code does not decide",
    ),
    Planted(
        Msg("pp06", et("2026-03-25 12:46:10"), "turner_sms", "pet_sms", "which entrance"),
        "not_in_report", ("C20",), "4 min 1 s after the quote of ¶15",
    ),
    Planted(
        Msg("pp07", et("2026-03-25 12:30:00"), "kevin_sms", "pet_sms", "u still selling the bike?"),
        "not_in_report", ("C20",), "a conversation the report does not hold at all",
    ),
    Planted(
        Msg("pp08", et("2026-02-25 10:00:00"), "pet_wa", "katya_wa", "pick up milk"),
        "not_in_report", (), "far from every claim's records: counted, listed under no claim",
    ),
)  # fmt: skip
PLANTED_CALLS: tuple[tuple[Call, tuple[str, ...]], ...] = (
    (Call("pc01", et("2026-03-12 20:30:00"), "pet_sms", "ilya_sms", 45), ("C05", "C06")),
)
PLANTED_CONTACTS = (("Kevin S", (("Mobile", "+12125550162"),)),)
# The larger source holds this message with other text, so the report's copy is not found.
EDITED = ("ns12", "friday hard. saturday?")


def _case01_story() -> tuple[list[Msg], list[Call]]:
    apps = {k: a.app for k, a in story.ACCOUNTS.items()}
    filler_msgs, filler_calls = make_filler(SEED, apps)
    return list(story.SCRIPTED_MESSAGES) + filler_msgs, list(story.SCRIPTED_CALLS) + filler_calls


def case01_item1() -> tuple[Rendered, Rendered]:
    """(case01's curated item1 report, item1's larger source with the planted records)."""
    msgs, calls = _case01_story()
    dev = next(d for d in story.DEVICES if d.key == "item1")
    curated = render_device(dev, msgs, calls)
    key, text = EDITED
    full_msgs = [replace(m, body=text) if m.key == key else m for m in msgs]
    full_msgs += [p.msg for p in PLANTED]
    full_calls = calls + [c for c, _ in PLANTED_CALLS]
    full = render_device(
        replace(dev, contacts=dev.contacts + PLANTED_CONTACTS), full_msgs, full_calls
    )
    return curated, full


# ---------------------------------------------------------------- pair02


def _q(key: str, at: str, sender: str, to: str, body: str) -> Msg:
    return Msg(key, et(f"2026-03-29 {at}"), sender, to, body)


# One morning on Marcus Reyes's phone (item2). The pair stands alone, never imported with case01.
PAIR02_REPORT: tuple[Msg, ...] = (
    _q("q01", "10:00:00", "rey_sms", "luis_sms", "you up"),
    _q("q02", "10:00:30", "luis_sms", "rey_sms", "yeah"),
    _q("q04", "10:05:00", "rey_sms", "luis_sms", "bring the jack"),
    _q("q09", "10:50:00", "jenna_wa", "rey_wa", "ok"),
)
PAIR02_REPORT_CALLS: tuple[Call, ...] = (
    Call("k02", et("2026-03-29 09:00:00"), "luis_sms", "rey_sms", 60),
)
PAIR02_EXTRA: tuple[Planted, ...] = (
    Planted(_q("q03", "10:00:45", "luis_sms", "rey_sms", "yeah"), "may_be",
            why="the report's 'yeah' could be either, so code does not decide"),
    Planted(_q("q05", "10:07:00", "luis_sms", "rey_sms", "which one"), "not_in_report",
            ("anchor",), "same thread, 2 min after the anchor"),
    Planted(_q("q06", "10:30:00", "rey_sms", "luis_sms", "the red one"), "not_in_report",
            ("anchor",), "same thread, 25 min after the anchor"),
    Planted(_q("q07", "12:00:00", "luis_sms", "rey_sms", "done"), "not_in_report",
            (), "same thread, 1 h 55 min after the anchor: not near it"),
    Planted(_q("q08", "10:10:00", "rey_wa", "jenna_wa", "running late"), "not_in_report",
            ("anchor",), "another thread, 5 min after the anchor"),
)  # fmt: skip
PAIR02_EXTRA_CALLS: tuple[Call, ...] = (
    Call("k01", et("2026-03-29 10:20:00"), "rey_sms", "luis_sms", 30),
)
PAIR02_ANCHOR = "q04"  # the message a claim would quote
# Listed near the anchor, in the order the audit must give: its own thread by time distance,
# then the other thread, then calls.
PAIR02_ORDER = ("q05", "q06", "q08", "k01")


def pair02() -> tuple[Rendered, Rendered]:
    """(the curated report, the larger source) of the small pair."""
    dev = replace(next(d for d in story.DEVICES if d.key == "item2"), key="pair02")
    curated = render_device(dev, list(PAIR02_REPORT), list(PAIR02_REPORT_CALLS))
    full = render_device(
        dev,
        list(PAIR02_REPORT) + [p.msg for p in PAIR02_EXTRA],
        list(PAIR02_REPORT_CALLS) + list(PAIR02_EXTRA_CALLS),
    )
    return curated, full


# ---------------------------------------------------------------- files


def write(out: Path) -> dict[str, Path]:
    """Every file of both pairs; names -> paths."""
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for stem, (curated, full) in (("item1", case01_item1()), ("pair02", pair02())):
        paths[f"{stem}.xlsx"] = out / f"{stem}.xlsx"
        write_xlsx(paths[f"{stem}.xlsx"], curated.sheets)
        xml, files = case01_package(full)
        paths[f"{stem}-full.ufdr"] = write_package(out / f"{stem}-full.ufdr", xml, files)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("eval/out/paired"))
    a = ap.parse_args(argv)
    for p in write(a.out).values():
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
