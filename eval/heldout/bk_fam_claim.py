"""Writers for the claim families that turn on an act or a role (guide rule 29), shown with the
claim: bk_claim_open, whose records bear on the claim and settle nothing, and bk_claim_denied,
where the claim's person rules it out in their own words after its time."""

from __future__ import annotations

import random

from eval.heldout import bk_acts as acts
from eval.heldout import bk_claimkit as ck
from eval.heldout import bk_pick as pk
from eval.heldout import bk_time as bt
from eval.heldout.bk_build import pair
from eval.heldout.bk_common import BkDraft, pick, window_words
from eval.heldout.bk_cues import quote_split
from eval.heldout.bk_naming import owner_sur, sur
from eval.heldout.bk_schedule import BkSlot
from eval.stancedata import bakerform as bf

_WHY_FORM = {
    "plan": "is a plan for the act the claim states; a plan does not show the act happened",
    "did": "says the act was done, but a message shows what was said, not the act itself",
    "ask": "asks about the act the claim states; a question does not show it happened",
    "tell": "tells them to do the act the claim states; an instruction does not show it was done",
    "from": "bears on the role the claim states, but a message cannot show the role itself",
    "to": "asks or tells them about the role the claim states; it bears on the role without "
    "showing it",
}


def _meaning_open(s: BkSlot, rng: random.Random) -> BkDraft:
    """The record uses the words, or asks about them, and nothing shown says what they mean."""
    pr = pair(rng, s, linked=rng.random() < 0.4)
    mine = rng.random() < 0.5
    ex = pr.chat(rng, s, pk.some_time(rng, pr.p.tz), s.text, mine, sit=s.sit, avoid=(s.words,))
    who = rng.random()
    if who < 0.35:
        actor = owner_sur(rng, pr.sc, pr.p)
    elif who < 0.65 and pr.linked:
        actor = sur(pr.linked)
    else:
        actor = sur(bf.named_person(s.person))
    claim = pick(
        rng,
        f'{actor} used "{s.words}" to mean {s.meaning}.',
        f'When {actor} wrote "{s.words}", {actor} meant {s.meaning}.',
    )
    why = pick(
        rng,
        f'The record uses "{s.words}", but nothing shown says what the words mean, so it '
        "leaves the meaning the claim gives them open.",
        f'"{s.words}" is in the record, yet no line explains it; whether it means what the '
        "claim says is not settled here.",
    )
    return BkDraft(s.family, "meaning", {"quoted_text": s.words}, ex, s.words, why, pr.p,
                   s.lang, pr.sc, claim=claim, facts={"variant": s.variant})  # fmt: skip


def claim_open(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_claim_open: the words with nothing to explain them, or a record from or to the
    claim's person's bracketed account that bears on the act or role and settles nothing."""
    if s.variant.startswith("meaning"):
        return _meaning_open(s, rng)
    p = ck.party(rng, s, linked=rng.random() < 0.6)
    from_person = s.variant.endswith("from")
    mine = p.mine(from_person)
    form = s.vals["form"]
    if s.vals["kind"] == "role":
        span = ck.role_span(rng, p.pr.p.tz)
        utc = bt.place_inside(rng, span, p.pr.p.tz)
        claim, params, win = ck.role_claim(span, p.actor, s), {"person_ids": [p.person]}, None
        inside = ""
    else:
        win = pk.pick_window(rng, p.pr.p.tz, ck.EVENT_KINDS)
        utc = bt.place_inside(rng, win, p.pr.p.tz)
        claim = ck.event_claim(win, p.actor, s)
        params = {"person_ids": ck.person_ids(rng, s, p.person), "window": win.tw()}
        inside = f", inside {window_words(win)}"
    if from_person:
        before, after = ck.other_side(rng, mine, 0.6, 0.6)
    else:  # nothing after a question or an instruction answers it
        before, after = [(not mine, rng.choice(acts.OPENERS))], []
    ex = ck.around(rng, p, utc, s.text, mine, before, after)
    way = "from" if from_person else "to"
    why = f"The record, {way} {p.shown}{inside}, {_WHY_FORM[form]}."
    template = "role" if s.vals["kind"] == "role" else "event"
    return BkDraft(s.family, template, params, ex, s.quote, why, p.pr.p, s.lang, p.pr.sc, win,
                   claim=claim,
                   mentions={bf.named_person(s.person2)},
                   facts={"variant": s.variant, "form": form})  # fmt: skip


def _denial_text(rng: random.Random, s: BkSlot, win: bt.Win) -> tuple[str, str, str]:
    """The denial, the clause it rests on, and what it covers: 'never' (all time before it),
    or the window's dates."""
    entry = acts.ACTS[s.act]
    if win.kind == "before" or rng.random() < 0.45:
        return s.text, s.quote, "never"
    city = rng.choice(acts.CITIES)
    first, last = win.first_day(), win.last_day()
    if first == last and rng.random() < 0.5:
        marked = ck.fill(rng.choice(entry["deny_day"]), s, day=ck.texted(first))
    elif first == last:
        marked = ck.fill(rng.choice(acts.ALIBI_DAY), s, day=ck.texted(first), city=city)
    else:
        lo = first - bt.DAY * rng.randint(0, 2)
        hi = last + bt.DAY * rng.randint(0, 2)
        marked = ck.fill(rng.choice(acts.ALIBI_SPAN), s, first=ck.texted(lo),
                         last=ck.texted(hi), city=city)  # fmt: skip
    return (*quote_split(marked), "dates")


def claim_denied(s: BkSlot, rng: random.Random) -> BkDraft:
    """bk_claim_denied: the claim's person, from an account bracketed with them, rules the act
    or role out in their own words, sent after the claim's time and covering all of it."""
    p = ck.party(rng, s, linked=s.variant.endswith("linked"))
    tz = p.pr.p.tz
    mine = p.mine(True)
    if s.vals["kind"] == "role":
        span = ck.role_span(rng, tz)
        utc = ck.after_end(rng, span, tz)
        claim, params, win = ck.role_claim(span, p.actor, s), {"person_ids": [p.person]}, None
        text, quote, covers, template = s.text, s.quote, "never", "role"
    else:
        win = pk.pick_window(rng, tz, ("on", "On", "through", "before", "between", "about"))
        utc = ck.after_end(rng, win, tz)
        claim = ck.event_claim(win, p.actor, s)
        params = {"person_ids": ck.person_ids(rng, s, p.person), "window": win.tw()}
        text, quote, covers = _denial_text(rng, s, win)
        template = "event"
    before, after = ck.other_side(rng, mine, 0.0, 0.5)
    if rng.random() < 0.55:
        ask = rng.choice(acts.ASK_DENY).format(act_q=ck.act_words(s, "q"),
                                               act_past=ck.act_words(s, "past"))  # fmt: skip
        before = [(not mine, ask)]
    ex = ck.around(rng, p, utc, text, mine, before, after)
    what = "role" if template == "role" else "act"
    scope = "for all time before it" if covers == "never" else "for the claim's dates"
    why = pick(
        rng,
        f"{p.shown}, bracketed with the claim's person, rules the {what} out in its own words "
        f"{scope}, sent {ex.record.local_time}, after the claim's time; what it says cannot be "
        "true together with the claim.",
        f"Sent after the claim's time ({ex.record.local_time}), the record from {p.shown} "
        f"denies the {what} the claim states {scope}, so it conflicts with the assumption.",
    )
    return BkDraft(s.family, template, params, ex, quote, why, p.pr.p, s.lang, p.pr.sc, win,
                   claim=claim, mentions={bf.named_person(s.person2)},
                   facts={"variant": s.variant, "covers": covers})  # fmt: skip
