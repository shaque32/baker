"""Scenarios built from a Fact, part 2: plans, conditions, questions, hedges, hearsay and later
corrections. Every lead states the fact (guide rule 12); the supports sibling reports what the
message says, in the third person and with no qualifier the record lacks."""

from __future__ import annotations

import random

from core.contracts import AssumptionKind as K
from eval.train import facts as fx
from eval.train import filler
from eval.train.scenario import Line
from eval.train.scenes import (
    Result,
    fact_lead,
    fact_pool,
    finish,
    marked,
    other_fact,
    other_value,
    plain_why,
    setup,
    siblings,
)
from eval.train.writers import Spec, cap, spec_irrelevant, spec_plain


def sc_plan(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.planned(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core, safe_after=True)
    money = fx.has_marker(core)
    why = "The record states a plan or intention; nothing shown says the act happened."
    lead = fact_lead(c, "ovr_plan", K.EVENT, fx.claim(f, st.v, money), core, why)
    plain = spec_plain(rng, c, f"would {fx.claim_base(f, st.v, money)}", core, plain_why(c),
                       told_only=True)  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_cond(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    third = st.third(rng)
    rep: str | None = None
    if f.lang == "en":
        cnd, rep = rng.choice(fx.CONDITIONS)
        cnd, act = cnd.format(n=third.name.lower()), f.act.format(v=st.vr)
        core = rng.choice([f"if {cnd} ill {act}", f"ill {act} if {cnd}",
                           f"only if {cnd} will i {act}", f"if {cnd} then ill {act}"])  # fmt: skip
    else:
        core = fx.conditional(f, rng, st.vr, st.sender.end, n=third.name.lower())
    c = finish(rng, st, core, safe_after=True)
    money = fx.has_marker(core)
    why = ("The record makes the act conditional; nothing shown says the condition was met or "
           "the act done.")  # fmt: skip
    lead = fact_lead(c, "ovr_hypothetical", K.EVENT, fx.claim(f, st.v, money), core, why)
    if rep is None:
        return c, [lead]
    rep = rep.format(N=third.name, p="they", poss="their", o=c.other.who)
    plain = spec_plain(rng, c, f"would {fx.claim_base(f, st.v, money)} if {rep}", core,
                       plain_why(c), told_only=True)  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_question(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.asked(f, rng, st.vr, st.other.end)
    c = finish(rng, st, core, safe_after=True, total=(1, 4))
    money = fx.has_marker(core)
    o, pred = c.other.who, fx.claim(f, st.v, money)
    why = "The record is a question, not a statement; nothing shown answers it."
    lead = Spec("ovr_question", K.EVENT, cap(f"{o} {pred}"), core, why)
    asked = cap(f"{c.sender.who} asked {o} whether they {pred}")
    plain = Spec(
        "sup_plain", K.EVENT, asked, core, "The record is that question, restated plainly."
    )
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_hedge(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.hedged(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core)
    money = fx.has_marker(core)
    pred = fx.claim(f, st.v, money)
    why = "The sender hedges the statement rather than asserting it; it is not stated as certain."
    lead = fact_lead(c, "cpl_hedge", K.EVENT, pred, core, why)
    plain = spec_plain(rng, c, f"thought they {pred}, without being sure", core, plain_why(c),
                       told_only=True)  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_hear(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    third = st.third(rng)
    core = fx.reported(f, rng, st.vr, third.name.lower(), third.pron, third.end)
    c = finish(rng, st, core)
    money = fx.has_marker(core)
    n, pred = third.name, fx.claim(f, st.v, money)
    a = rng.choice([f"{n} {pred}", f"{n}, whom the chat mentions, {pred}"])
    why = (f"The sender only reports what {third.name.lower()} said; nothing shown confirms it "
           "first hand.")  # fmt: skip
    lead = Spec("cpl_hearsay", K.EVENT, cap(a), core, why)
    # The supports sibling keeps the hearsay; "they" is the third person just named, so nobody
    # is gendered and no name is repeated.
    said = rng.choice([f"{n} said they {pred}", f"{n} said that they {pred}"])
    plain = spec_plain(rng, c, said, core, plain_why(c), told_only=True, bare=True)
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_correction(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    v1, v2 = st.v, other_value(rng, st, st.v)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    corr = rng.choice(filler.CORRECTIONS_RU if f.lang == "ru" else filler.CORRECTIONS_EN)
    corr = corr.format(v1=st.vr, v2=marked(st, v2), c=st.sender.end)
    after: list[Line] = [(st.who, corr)]
    if rng.random() < 0.4:
        other_who = "c" if st.who == "o" else "o"
        after.insert(0, (other_who, rng.choice(("ok", "k", "?", "wait what") if f.lang == "en"
                                               else ("ок", "ага", "?", "в смысле"))))  # fmt: skip
    c = finish(rng, st, core, after=after)
    money = fx.has_marker(core)
    s1, s2 = fx.shown(f, v1), fx.shown(f, v2)
    why = (
        f"The same sender's later message replaces {s1} with {s2}, "
        "so the record's figure does not stand."
    )
    lead = fact_lead(c, "ovr_later_correction", K.EVENT, fx.claim(f, v1, money), core, why)
    irr = spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False)
    return c, siblings(rng, lead, [irr], 0.3, 1)
