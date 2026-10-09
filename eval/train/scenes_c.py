"""Scenarios, part 4: time windows, the DST changes, the hand-written specials, small talk and
unrelated records, and the weighted table the generator draws from."""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

from core.contracts import AssumptionKind as K
from eval.stancedata.chat import long_date
from eval.train import facts as fx
from eval.train import filler, special, special_b, special_ru
from eval.train.facts import Fact
from eval.train.scenario import FALL_DST, SPRING_DST, TZS_US, clock12, fill_ends, month_year
from eval.train.scenes import (
    ALL_FACTS,
    Result,
    fact_pool,
    finish,
    other_fact,
    plain_why,
    sc_denial,
    sc_exact,
    sc_neg,
    sc_stated,
    setup,
    siblings,
)  # fmt: skip
from eval.train.scenes_b import sc_disputed, sc_group, sc_handle, sc_injection, sc_qa, sc_shared
from eval.train.scenes_d import sc_cond, sc_correction, sc_hear, sc_hedge, sc_plan, sc_question
from eval.train.writers import (
    Spec,
    cap,
    kind_of,
    spec_contact,
    spec_in_window,
    spec_irrelevant,
    spec_plain,
    spec_time_mismatch,
    spec_time_window,
)  # fmt: skip

SPECIALS = (special.PRONOUN + special.CODE_WORD + special.DIFFERENT_TOPIC + special_b.JOKE
            + special_b.COUNT + special_b.INFERENCE + special_b.RELATIVE_TIME
            + special_b.OTHER_STATE + special_ru.PRONOUN_RU + special_ru.CODE_WORD_RU
            + special_ru.DIFFERENT_TOPIC_RU + special_ru.JOKE_RU + special_ru.COUNT_RU
            + special_ru.INFERENCE_RU + special_ru.RELATIVE_TIME_RU + special_ru.OTHER_STATE_RU
            + special_ru.TRANSLATION_RU)  # fmt: skip
SPECIAL_WEIGHTS = {"ovr_pronoun": 1.2, "ovr_code_word": 1.3, "ovr_different_topic": 1.2,
                   "ovr_joke": 1.0, "ovr_count": 0.8, "cpl_inference": 1.0,
                   "cpl_relative_time": 0.9, "con_other_state": 1.3,
                   "ovr_translation": 1.0}  # fmt: skip


def sc_time(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core)
    pred = fx.claim(f, st.v, fx.has_marker(core))
    lead = spec_time_window(rng, c)
    cands = [spec_time_mismatch(rng, c, pred, core), spec_contact(rng, c), spec_in_window(rng, c),
             spec_plain(rng, c, pred, core, plain_why(c))]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.6, 3)


def sc_dst(rng: random.Random, slot: int) -> Result:
    """Records at the US daylight-saving changes, where the local clock reading decides."""
    f = fact_pool(slot, ru=0.1)
    day = rng.choice((SPRING_DST, FALL_DST))
    st = setup(rng, f, day=day)
    st.tz = rng.choice(TZS_US)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    hour, fold = (rng.choice((1, 3)), 0) if day == SPRING_DST else (1, rng.choice((0, 1)))
    c = finish(rng, st, core, hours=(hour, hour), fold=fold, total=(1, 4))
    s, o, d = c.sender.who, c.other.who, long_date(day)
    pred, stamp = fx.claim(f, st.v, fx.has_marker(core)), f"{clock12(c.local)} {c.local.tzname()}"
    if day == SPRING_DST and hour == 1:
        win = [
            f"before 2 a.m. on {d}, {s} texted {o}",
            f"between 1 and 2 a.m. on {d}, {s} messaged {o}",
        ]
        miss = [
            f"after 2 a.m. on {d}, {s} told {o} that they {pred}",
            f"after 3 a.m. on {d}, {s} told {o} that they {pred}",
        ]
    elif day == SPRING_DST:
        win = [
            f"after 2:30 a.m. on {d}, {s} texted {o}",
            f"between 3 and 4 a.m. on {d}, {s} messaged {o}",
        ]
        miss = [
            f"before 2:30 a.m. on {d}, {s} told {o} that they {pred}",
            f"before 3 a.m. on {d}, {s} told {o} that they {pred}",
        ]
    else:
        win = [
            f"between 1 and 2 a.m. on {d}, {s} messaged {o}",
            f"before 2 a.m. on {d}, {s} texted {o}",
        ]
        miss = [
            f"after 2 a.m. on {d}, {s} told {o} that they {pred}",
            f"before 1 a.m. on {d}, {s} told {o} that they {pred}",
        ]
    decides = "At the daylight-saving change the local clock reading decides: the record reads "
    sup = Spec("sup_time_window", K.TIME, cap(rng.choice(win)), c.record.text,
               f"{decides}{stamp} on {d}, inside the window.")  # fmt: skip
    mis = Spec("ovr_time_mismatch", K.TIME, cap(rng.choice(miss)), core,
               f"{decides}{stamp} on {d}, outside what the assumption states.")  # fmt: skip
    specs = [sup, mis]
    rng.shuffle(specs)
    return c, specs


def sc_special(rng: random.Random, slot: int) -> Result:
    fams = sorted(SPECIAL_WEIGHTS)
    fam = rng.choices(fams, [SPECIAL_WEIGHTS[k] for k in fams])[0]
    lang = "ru" if fam == "ovr_translation" or rng.random() < 0.2 else "en"
    sp = rng.choice([x for x in SPECIALS if x.family == fam and x.lang == lang])
    f = Fact("special", "special", lang, "", "", "", "", ("x", "y"))
    st = setup(rng, f, who=sp.rec_who)
    # Slot values that are names never name a chat member.
    cast_names = {n.lower() for n in st.names()}
    if sp.xs and sp.ys and len(sp.xs) == len(sp.ys):
        pairs = list(zip(sp.xs, sp.ys, strict=True))
    else:
        pairs = [(x, y) for x in sp.xs or [""] for y in sp.ys or [""]]
    clean = [p for p in pairs if not any(n in (p[0] + " " + p[1]).lower() for n in cast_names)]
    x, y = rng.choice(clean or pairs)

    def fill(t: str) -> str:
        t = t.replace("{X}", cap(x)).replace("{Y}", cap(y)).replace("{x}", x).replace("{y}", y)
        return fill_ends(t, st.owner, st.contacts[0])

    before = [(w, fill(t)) for w, t in sp.before]
    after = [(w, fill(t)) for w, t in sp.after]
    hours = (0, 1) if fam == "cpl_relative_time" else (7, 23)
    # A joke's own marker must be the last word on it: no filler follows it (round-2 rule H).
    c = finish(rng, st, fill(sp.record), before=before, after=after, hours=hours,
               do_wrap=rng.random() < 0.7, after_fill=fam != "ovr_joke")  # fmt: skip
    slots = dict(S=c.sender.who, O=c.other.who, pron="they", poss="their", date=long_date(c.day),
                 prev=long_date(c.day - timedelta(days=1)), clock=clock12(c.local),
                 next=long_date(c.day + timedelta(days=1)), month=month_year(c.day))  # fmt: skip
    lead = Spec(fam, kind_of(rng, fam), cap(fill(sp.claim).format(**slots)), fill(sp.quote),
                fill(sp.why).format(**slots))  # fmt: skip
    irr = spec_irrelevant(rng, c, "irr_other_topic", rng.choice(ALL_FACTS), False)
    return c, siblings(rng, lead, [irr], 0.2, 1)


LAUGHS = {"lol", "haha", "lmaooo", "ахах", "ахахах", "лол"}


def sc_pleasantry(rng: random.Random, slot: int) -> Result:
    lang = "ru" if rng.random() < 0.2 else "en"
    f = Fact("talk", "talk", lang, "", "", "", "", ("x",))
    st = setup(rng, f)
    pool = filler.PLEASANTRIES_RU if lang == "ru" else filler.PLEASANTRIES_EN
    core = rng.choice(pool)
    if rng.random() < 0.4:  # two bits of small talk in one message, sharing no word
        words = set(re.findall(r"\w+", core.lower()))
        # The second bit is never a bare laugh ("thx, lol" would read as a tail).
        rest = [x for x in pool if x != core and not words & set(re.findall(r"\w+", x.lower()))
                and not set(re.findall(r"\w+", x.lower())) <= LAUGHS]  # fmt: skip
        core += rng.choice((" ", ", ")) + rng.choice(rest)
    c = finish(rng, st, core, do_wrap=False)
    lead = spec_irrelevant(rng, c, "irr_pleasantry", rng.choice(ALL_FACTS), rng.random() < 0.7)
    why = "The record is a greeting or small talk with no bearing on the assumption."
    return c, [replace(lead, rationale=why)]


def sc_irrelevant(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core)
    return c, [spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False)]


Scenario = Callable[[random.Random, int], Result]
SCENARIOS: tuple[tuple[Scenario, float], ...] = (
    (sc_stated, 11), (sc_exact, 6), (sc_neg, 4), (sc_denial, 4), (sc_plan, 5), (sc_cond, 4),
    (sc_question, 4), (sc_hedge, 4), (sc_hear, 4), (sc_correction, 4), (sc_shared, 4),
    (sc_handle, 5), (sc_group, 4), (sc_injection, 5), (sc_disputed, 3), (sc_qa, 4), (sc_time, 4),
    (sc_dst, 2), (sc_special, 30), (sc_pleasantry, 4), (sc_irrelevant, 2),
)  # fmt: skip


# Scenarios built without a Fact: they do not advance the fact slot.
FACT_FREE: frozenset[Scenario] = frozenset({sc_special, sc_pleasantry, sc_disputed, sc_qa})


def takes_fact(scenario: Scenario) -> bool:
    """Whether the scenario draws its record from the fact pools (see scenes.fact_pool)."""
    return scenario not in FACT_FREE


def pick_scenario(rng: random.Random) -> Scenario:
    return rng.choices([s for s, _ in SCENARIOS], [w for _, w in SCENARIOS])[0]
