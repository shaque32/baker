"""What the claim-family writers share (guide rule 29): the claim's wording, the person it is
about and the account bracketed with them, and the lines the other side writes around a
record."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from eval.heldout import bk_acts as acts
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import Pair, pair, shown_as
from eval.heldout.bk_naming import owner_sur, sur
from eval.heldout.bk_scene import Acct, Excerpt, chat
from eval.heldout.bk_schedule import BkSlot
from eval.heldout.text import normalized
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import long_date

EVENT_KINDS = ("on", "On", "through", "before", "after", "between", "about")


def when(win: bt.Win) -> str:
    """The window's words opening a claim: 'On May 2, 2026', 'Sometime from May 1 through
    May 4, 2026', 'At about 9 p.m. on May 2, 2026'."""
    if win.kind == "through":
        return f"Sometime {win.raw}"
    return win.raw[:1].upper() + win.raw[1:]


def texted(day: date) -> str:
    """A date as a chat writes it: 'march 3'."""
    return f"{day:%B} {day.day}".lower()


def dial(number: str) -> str:
    """'+15035550147' as a document prints it: '(503) 555-0147'."""
    return f"({number[2:5]}) {number[5:8]}-{number[8:]}"


def label(a: Acct) -> str:
    """An account as a claim names it."""
    if a.app == "Telegram":
        return f"Telegram user {a.ident}"
    if a.app == "Instagram":
        return f"the Instagram account {a.ident}"
    return dial(a.ident)


def fill(template: str, s: BkSlot, **more: str) -> str:
    return template.format_map({**s.vals, **more})


def act_words(s: BkSlot, form: str = "claim") -> str:
    """The act or role from the slot's table entry, filled ('met Pruett at the dock')."""
    table = acts.ACTS if s.vals["kind"] == "act" else acts.ROLES
    return fill(table[s.act][form][0], s)


def role_span(rng: random.Random, tz: str) -> bt.Win:
    first = bt.base_day(rng)
    return bt.through(first, first + timedelta(days=rng.randint(6, 40)), tz)


def role_claim(span: bt.Win, actor: str, s: BkSlot) -> str:
    return f"{span.raw[:1].upper()}{span.raw[1:]}, {actor} {act_words(s)}."


def event_claim(win: bt.Win, actor: str, s: BkSlot) -> str:
    return f"{when(win)}, {actor} {act_words(s)}."


@dataclass
class Party:
    """The chat a claim's person is on: their account (`acct`) is bracketed with them, as a
    linked third party or as the phone's stipulated user; `actor` is how the claim names
    them."""

    pr: Pair
    person: str
    acct: Acct
    actor: str

    @property
    def shown(self) -> str:
        return shown_as(self.pr.sc, self.pr.p, self.acct)

    def mine(self, from_person: bool) -> bool:
        """Whether a record from (or to) the person is the owner's own line."""
        own = self.acct == self.pr.me
        return own if from_person else not own


def party(rng: random.Random, s: BkSlot, linked: bool) -> Party:
    if linked:
        pr = pair(rng, s, linked=True)
        return Party(pr, pr.linked, pr.other, sur(pr.linked))
    pr = pair(rng, s)
    return Party(pr, pr.p.owner, pr.me, owner_sur(rng, pr.sc, pr.p))


def after_end(rng: random.Random, win: bt.Win, tz: str) -> datetime:
    """A time 1 to 20 days after the window's last day, in the daytime."""
    for _ in range(50):
        day = win.last_day() + timedelta(days=rng.randint(1, 20))
        utc = bt.local_instant(day, rng.randint(8 * 60, 22 * 60), tz)
        if utc is not None and bt.outside_by(utc, win, tz) >= bt.DAY:
            return utc + timedelta(seconds=rng.randrange(60))
    raise RuntimeError(f"no time after {win.raw!r}")


def around(
    rng: random.Random,
    p: Party,
    utc: datetime,
    text: str,
    mine: bool,
    before: list[tuple[bool, str]],
    after: list[tuple[bool, str]],
) -> Excerpt:
    """The person's chat with the record and the given lines (mine?, text) around it; the
    other side always shows at least one line."""
    if all(m == mine for m, _ in before + after):
        after = [*after, (not mine, rng.choice(acts.ACKS))]
    seen = {normalized(text)}
    for _, line in before + after:
        if normalized(line) in seen:
            raise ValueError(f"a line repeats in the chat: {line!r}")
        seen.add(normalized(line))
    return chat(rng, p.pr.sc, p.pr.p, p.pr.me, p.pr.other, utc, text, mine, before, after)


def other_side(rng: random.Random, mine: bool, opener: float, ack: float) -> tuple[list, list]:
    """An opener before and an acknowledgement after, each now and then, from the side that
    did not write the record."""
    before = [(not mine, rng.choice(acts.OPENERS))] if rng.random() < opener else []
    after = [(not mine, rng.choice(acts.ACKS))] if rng.random() < ack else []
    return before, after


def person_ids(rng: random.Random, s: BkSlot, person: str, share: float = 0.4) -> list[str]:
    """The claim's person, and now and then the other person the claim names."""
    if s.person2 and rng.random() < share:
        return [person, bf.named_person(s.person2)]
    return [person]


def long(day: date) -> str:
    return long_date(day)
