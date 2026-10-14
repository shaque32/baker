"""Scenarios built from a Fact, part 2: plans, conditions, questions, hedges, hearsay and
corrections (the corrected record and the correcting one). Every lead states the fact (guide
rule 12); the supports sibling reports what the message says, in the third person and with no
qualifier the record lacks."""

from __future__ import annotations

import random

from core.contracts import AssumptionKind as K
from eval.train import facts as fx
from eval.train import filler
from eval.train.facts import Fact
from eval.train.scenario import Line
from eval.train.scenes import (
    Result,
    Setup,
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
from eval.train.writers import (
    Spec,
    act_before,
    bounded,
    cap,
    quoted,
    spec_in_window,
    spec_irrelevant,
    spec_plain,
    spec_sender_mismatch,
    spec_verbatim,
)  # fmt: skip


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
    # A bound before or after the record: a question settles neither (guide rule 23).
    a = bounded(rng, c, o, pred, after=rng.random() < 0.5) if rng.random() < 0.45 else cap(
        f"{o} {pred}")  # fmt: skip
    lead = Spec("ovr_question", K.EVENT, a, core, why)
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
    if rng.random() < 0.45:
        a = bounded(rng, c, c.sender.who, pred, after=rng.random() < 0.5)
        lead = Spec("cpl_hedge", K.EVENT, a, core, why)
    else:
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
    if rng.random() < 0.45:
        a = bounded(rng, c, n, pred, after=rng.random() < 0.5)
    else:
        a = rng.choice([f"{n} {pred}", f"{n}, whom the chat mentions, {pred}"])
    why = (f"The sender only reports what {third.name.lower()} said; nothing shown confirms it "
           "first hand.")  # fmt: skip
    lead = Spec("cpl_hearsay", K.EVENT, cap(a), core, why)
    # The supports sibling keeps the hearsay; "they" is the third person just named, so nobody
    # is gendered and no name is repeated.
    said = rng.choice([f"{n} said they {pred}", f"{n} said that they {pred}"])
    plain = spec_plain(rng, c, said, core, plain_why(c), told_only=True, bare=True)
    return c, siblings(rng, lead, [plain], 0.5, 1)


INTERJECTIONS_EN = ("ok", "k", "?", "wait what")
INTERJECTIONS_RU = ("ок", "ага", "?", "в смысле")


def _settles(f: Fact, v: str) -> str:
    """What a correction leaves unsettled, in a rationale's words."""
    if f.money:
        return "the amount"
    if fx.is_day(f, v):
        return "the day"
    return "which value is right"


def _correction(rng: random.Random, f: Fact, st: Setup, v2: str,
                quotable: bool) -> tuple[str, str | None]:  # fmt: skip
    """The same sender's correction of st.vr to v2, and the words that state the replacement."""
    pool = filler.CORRECTIONS_RU if f.lang == "ru" else filler.CORRECTIONS_EN
    text, quote = rng.choice([p for p in pool if p[1] is not None or not quotable])
    slots = dict(v1=st.vr, v2=marked(st, v2), c=st.sender.end)
    return text.format(**slots), quote.format(**slots) if quote else None


def _interjection(rng: random.Random, st: Setup) -> Line:
    """The other party's short reaction between a statement and its correction."""
    pool = INTERJECTIONS_RU if st.f.lang == "ru" else INTERJECTIONS_EN
    return ("c" if st.who == "o" else "o", rng.choice(pool))


def sc_correction(rng: random.Random, slot: int) -> Result:
    """The record states a value; the same sender corrects it minutes later (guide rule 22).

    The record is complicates: the correcting message, not the record, carries the
    contradiction, and the rationale names it.
    """
    f = fact_pool(slot)
    st = setup(rng, f)
    v1, v2 = st.v, other_value(rng, st, st.v)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    corr, _ = _correction(rng, f, st, v2, quotable=False)
    after: list[Line] = [(st.who, corr)]
    if rng.random() < 0.4:
        after.insert(0, _interjection(rng, st))
    c = finish(rng, st, core, after=after, quick=True)
    money = fx.has_marker(core)
    why = (f"The record says {quoted(st.vr)}, but the same sender corrects it to "
           f"{quoted(marked(st, v2))} later in the chat ({quoted(corr)}), so the record alone does "
           f"not settle {_settles(f, v1)}.")  # fmt: skip
    pred = fx.claim(f, v1, money)
    if rng.random() < 0.45:
        a = bounded(rng, c, c.sender.who, pred, after=rng.random() < 0.5)
        lead = Spec("ovr_later_correction", K.EVENT, a, core, why)
    else:
        lead = fact_lead(c, "ovr_later_correction", K.EVENT, pred, core, why)
    irr = spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False)
    return c, siblings(rng, lead, [irr], 0.3, 1)


def sc_corrected(rng: random.Random, slot: int) -> Result:
    """The record is the same sender's correction of a value given just before (guide rule 19).

    The assumption states the original value as a plain fact (rule 12) and the quote is the
    correcting words, which state the replacement: contradicts, the mirror of
    ovr_later_correction, where the corrected statement is the record.
    """
    f = fact_pool(slot)
    st = setup(rng, f)
    v1, v2 = st.v, other_value(rng, st, st.v)
    first = fx.stated(f, rng, st.vr, st.sender.end)
    corr, quote = _correction(rng, f, st, v2, quotable=True)
    if quote is None:  # _correction(quotable=True) never draws an unquotable correction
        raise ValueError(f"no quotable correction for {f.key}")
    before: list[Line] = [(st.who, first)]
    if rng.random() < 0.3:
        before.append(_interjection(rng, st))
    # The correction is quoted as written: no decoration, so no "lol" can make it read as a
    # joke (rule 24).
    c = finish(rng, st, corr, before=before, do_wrap=False, quick=True)
    money = fx.has_marker(first)
    why = rng.choice([
        f"The record is the sender's own correction of the earlier {quoted(first)}: "
        f"{quoted(quote)}. What it states cannot be true together with the assumption, which "
        "keeps the earlier value; whether the correction is right is for the expert.",
        f"Minutes after writing {quoted(first)}, the same sender corrects it: {quoted(quote)}. "
        "What the correction states cannot be true together with the assumption; whether it is "
        "right is for the expert.",
    ])  # fmt: skip
    pred = fx.claim(f, v1, money)
    # A weekday could come round again after the message, so an assumption about one dates the
    # act before the record's date (guide rule 23); other values need no date.
    if fx.names_day(pred):
        lead = Spec("con_correction", K.EVENT, act_before(rng, c, c.sender.who, pred), quote, why)
    else:
        lead = fact_lead(c, "con_correction", K.EVENT, pred, quote, why)
    cands = [spec_verbatim(rng, c), spec_in_window(rng, c), spec_sender_mismatch(rng, c),
             spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False)]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.5, 2)
