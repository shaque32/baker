"""Scenarios built from a Fact: one chat, one record, one or more sibling specs.

Each scenario function takes the scenario's random stream and returns the Chat and the Specs
built on its record; siblings share the record and differ in the assumption and the family.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from core.contracts import AssumptionKind as K
from eval.train import facts as fx
from eval.train import filler
from eval.train.facts import Fact
from eval.train.facts_en_a import FACTS_A
from eval.train.facts_en_b import FACTS_B
from eval.train.facts_ru import FACTS_RU
from eval.train.names import Party, cast, person
from eval.train.scenario import (
    Chat,
    Line,
    assemble,
    filler_lines,
    pick_day,
    pick_tz,
    record_time,
)  # fmt: skip
from eval.train.writers import (
    Spec,
    cap,
    frame,
    kind_of,
    spec_contact,
    spec_count,
    spec_handle_owner,
    spec_in_window,
    spec_irrelevant,
    spec_partial,
    spec_plain,
    spec_sender_mismatch,
    spec_time_mismatch,
    spec_time_window,
    spec_verbatim,
    wrap,
)  # fmt: skip

FACTS_EN = FACTS_A + FACTS_B
ALL_FACTS = FACTS_EN + FACTS_RU
Result = tuple[Chat, list[Spec]]


def fact_pool(rng: random.Random, ru: float = 0.2) -> Fact:
    return rng.choice(FACTS_RU if rng.random() < ru else FACTS_EN)


def other_fact(rng: random.Random, f: Fact) -> Fact:
    return rng.choice([g for g in ALL_FACTS if g.scene != f.scene])


@dataclass
class Setup:
    f: Fact
    app: str
    owner: Party
    contacts: list[Party]
    tz: str
    day: date
    who: str  # "o", "c" or "c2": who sends the record
    sender: Party
    other: Party
    v: str
    values: tuple[str, ...] = ()  # the fact's values, minus any cast member's first name


def other_value(rng: random.Random, st: Setup, v: str) -> str:
    return rng.choice([x for x in st.values if x != v])


def setup(rng: random.Random, f: Fact, *, extra: int = 0, who: str | None = None,
          day: date | None = None) -> Setup:  # fmt: skip
    app, owner, contacts = cast(rng, f.lang, extra)
    tz = pick_tz(rng, f.lang)
    if who is None:
        who = "o" if rng.random() < 0.25 else "c"
    sender = owner if who == "o" else contacts[1 if who == "c2" else 0]
    other = contacts[0] if who == "o" else owner
    # A value that is someone's first name ("covered Kofi's shift") never names a cast member,
    # so a third party in the record never shares the sender's name.
    cast_names = {p.person.name.lower() for p in [owner, *contacts]}
    values = tuple(v for v in f.values if v.lower() not in cast_names)
    if len(values) < 2:
        values = f.values
    return Setup(f, app, owner, contacts, tz, day or pick_day(rng), who, sender, other,
                 rng.choice(values), values)  # fmt: skip


def finish(rng: random.Random, st: Setup, core: str, *, before: list[Line] | None = None,
           after: list[Line] | None = None, hours: tuple[int, int] = (7, 23), fold: int = 0,
           do_wrap: bool = True, after_fill: bool = True, safe_after: bool = False,
           done_ok: bool = True, total: tuple[int, int] = (1, 6)) -> Chat:  # fmt: skip
    """Pad the scenario lines with small talk, time them and assemble the Chat.

    A non-owner line is always on screen (guide rule 11). With `safe_after`, no filler after
    the record can read as an answer or a confirmation (guide rule 13).
    """
    before, after = list(before or []), list(after or [])
    rec_lang = st.f.lang
    ctx_lang = rec_lang
    if rng.random() < (0.12 if rec_lang == "ru" else 0.03):
        ctx_lang = "en" if rec_lang == "ru" else "ru"
    whos = ("o", "c", "c2") if len(st.contacts) > 1 else ("o", "c")
    need = max(0, rng.randint(*total) - len(before) - len(after))
    has_contact = st.who != "o" or any(w != "o" for w, _ in before + after)
    if not has_contact and need == 0:
        need = 1
    n_before = need if not after_fill else rng.randint(0, need)
    extra_before, extra_after = filler_lines(
        rng, ctx_lang, n_before, need - n_before, st.owner, st.contacts, whos,
        scene=st.f.scene, safe_after=safe_after, first=None if has_contact else "c",
    ) if need else ([], [])  # fmt: skip
    before, after = extra_before + before, after + extra_after
    lang = "mixed" if need and ctx_lang != rec_lang else rec_lang
    text = wrap(rng, core, rec_lang, done_ok) if do_wrap else core
    when = record_time(rng, st.day, st.tz, hours, fold)
    return assemble(rng, tz=st.tz, app=st.app, owner=st.owner, contacts=st.contacts, lang=lang,
                    before=before, record=(st.who, text), after=after, when=when)  # fmt: skip


def siblings(rng: random.Random, lead: Spec, cands: list[Spec | None], p: float,
             most: int = 3) -> list[Spec]:  # fmt: skip
    """The lead spec, plus up to `most` siblings from different families with probability p."""
    pool = [s for s in cands if s is not None and s.family != lead.family]
    if rng.random() >= p or not pool:
        return [lead]
    picked: list[Spec] = []
    for s in rng.sample(pool, len(pool)):
        if all(s.family != t.family for t in picked):
            picked.append(s)
        if len(picked) >= most:
            break
    return [lead, *picked]


def plain_why(c: Chat) -> str:
    return (f"The record from {c.record.account.sender} states it in plain words; nothing in the "
            "context qualifies it.")  # fmt: skip


def sc_stated(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    core = fx.stated(f, rng, st.v, st.sender.end)
    c = finish(rng, st, core)
    pred = fx.claim(f, st.v)
    lead = (
        spec_verbatim(rng, c)
        if rng.random() < 0.3
        else spec_plain(rng, c, pred, core, plain_why(c))
    )
    cands = [spec_time_mismatch(rng, c, pred, core), spec_sender_mismatch(rng, c),
             spec_handle_owner(rng, c, pred, core, False), spec_partial(rng, c, f, st.v, core),
             spec_count(rng, c, f, st.v, core), spec_time_window(rng, c), spec_contact(rng, c),
             spec_in_window(rng, c),
             spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False),
             spec_plain(rng, c, pred, core, plain_why(c))]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.6)


def sc_exact(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    core = fx.exact(f, rng, st.v, st.sender.end)
    if core is None:
        return sc_stated(rng)
    c = finish(rng, st, core)
    v2 = other_value(rng, st, st.v)
    a = cap(f"{c.sender.who} {fx.claim(f, v2)}")  # the fact itself (guide rule 12)
    why = (f"The record gives {fx.shown(f, st.v)} and rules out any other value; the "
           f"assumption says {fx.shown(f, v2)}.")  # fmt: skip
    lead = Spec("con_other_value", kind_of(rng, "con_other_value"), a, core, why)
    pred = fx.claim(f, st.v)
    cands = [spec_plain(rng, c, pred, core, plain_why(c)), spec_time_mismatch(rng, c, pred, core),
             spec_handle_owner(rng, c, pred, core, False)]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.5, 2)


def _neg_pair(
    rng: random.Random, c: Chat, f: Fact, v: str, core: str, fam: str, why: str
) -> Result:
    a = cap(f"{c.sender.who} {fx.claim(f, v)}")  # the fact itself (guide rule 12)
    lead = Spec(fam, K.EVENT, a, core, why)
    plain = spec_plain(rng, c, f"did not {fx.claim_base(f, v)}", core, plain_why(c), told_only=True)
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_neg(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    core = fx.negated(f, rng, st.v, st.sender.end)
    c = finish(rng, st, core, done_ok=False)
    why = "The assumption's words appear inside a negation: the record says the act did not happen."
    return _neg_pair(rng, c, f, st.v, core, "ovr_negation", why)


def sc_denial(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    q = fx.asked(f, rng, st.v, st.sender.end)
    other_who = "c" if st.who == "o" else "o"
    core = fx.negated(f, rng, st.v, st.sender.end)
    c = finish(rng, st, core, before=[(other_who, q)], done_ok=False)
    why = "Asked directly, the sender denies it in plain words."
    return _neg_pair(rng, c, f, st.v, core, "con_denial", why)


def sc_plan(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    core = fx.planned(f, rng, st.v, st.sender.end)
    c = finish(rng, st, core, safe_after=True, done_ok=False)
    a = frame(rng, c, fx.claim(f, st.v), date=rng.random() < 0.2)
    why = "The record states a plan or intention; nothing shown says the act happened."
    lead = Spec("ovr_plan", K.EVENT, a, core, why)
    plain = spec_plain(
        rng, c, f"would {fx.claim_base(f, st.v)}", core, plain_why(c), told_only=True
    )
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_cond(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    cnd: str | None = None
    if f.lang == "en":
        cnd, act = rng.choice(fx.CONDITIONS), f.act.format(v=st.v)
        core = rng.choice([f"if {cnd} ill {act}", f"ill {act} if {cnd}",
                           f"only if {cnd} will i {act}", f"if {cnd} then ill {act}"])  # fmt: skip
    else:
        core = fx.conditional(f, rng, st.v, st.sender.end)
    c = finish(rng, st, core, safe_after=True, done_ok=False)
    a = frame(rng, c, fx.claim(f, st.v), date=rng.random() < 0.2)
    why = ("The record makes the act conditional; nothing shown says the condition was met or "
           "the act done.")  # fmt: skip
    lead = Spec("ovr_hypothetical", K.EVENT, a, core, why)
    if cnd is None:
        return c, [lead]
    plain = spec_plain(
        rng, c, f"would {fx.claim_base(f, st.v)} if {cnd}", core, plain_why(c), told_only=True
    )
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_question(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    core = fx.asked(f, rng, st.v, st.other.end)
    c = finish(rng, st, core, safe_after=True, done_ok=False, total=(1, 4))
    o, op = c.other.who, c.other.pron
    a = rng.choice(
        [f"{o} {fx.claim(f, st.v)}", f"{o} told {c.sender.who} that {op} {fx.claim(f, st.v)}"]
    )
    why = "The record is a question, not a statement; nothing shown answers it."
    lead = Spec("ovr_question", K.EVENT, cap(a), core, why)
    asked = cap(f"{c.sender.who} asked {o} whether {op} {fx.claim(f, st.v)}")
    plain = Spec(
        "sup_plain", K.EVENT, asked, core, "The record is that question, restated plainly."
    )
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_hedge(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    core = fx.hedged(f, rng, st.v, st.sender.end)
    c = finish(rng, st, core)
    a = frame(rng, c, fx.claim(f, st.v), date=rng.random() < 0.2)
    why = "The sender hedges the statement rather than asserting it; it is not stated as certain."
    lead = Spec("cpl_hedge", K.EVENT, a, core, why)
    p = c.sender.pron
    plain = spec_plain(rng, c, f"thought {p} {fx.claim(f, st.v)}, without being sure", core,
                       plain_why(c), told_only=True)  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_hear(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    names = {p.person.name for p in [st.owner, *st.contacts]}
    third = person(rng, f.lang)
    while third.name in names:
        third = person(rng, f.lang)
    core = fx.reported(f, rng, st.v, third.name.lower(), third.pron, third.end)
    c = finish(rng, st, core)
    pred = fx.claim(f, st.v)
    a = rng.choice([f"{third.name} {pred}", f"{third.name}, whom the chat mentions, {pred}"])
    why = (f"The sender only reports what {third.name.lower()} said; nothing shown confirms it "
           "first hand.")  # fmt: skip
    lead = Spec("cpl_hearsay", K.EVENT, cap(a), core, why)
    plain = spec_plain(rng, c, f"{third.name} said {third.pron} {pred}", core, plain_why(c),
                       told_only=True, bare=True)  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_correction(rng: random.Random) -> Result:
    f = fact_pool(rng)
    st = setup(rng, f)
    v1, v2 = st.v, other_value(rng, st, st.v)
    core = fx.stated(f, rng, v1, st.sender.end)
    corr = rng.choice(filler.CORRECTIONS_RU if f.lang == "ru" else filler.CORRECTIONS_EN)
    corr = corr.format(v1=v1, v2=v2, c=st.sender.end)
    after: list[Line] = [(st.who, corr)]
    if rng.random() < 0.4:
        other_who = "c" if st.who == "o" else "o"
        after.insert(0, (other_who, rng.choice(("ok", "k", "?", "wait what") if f.lang == "en"
                                               else ("ок", "ага", "?", "в смысле"))))  # fmt: skip
    c = finish(rng, st, core, after=after)
    s = c.sender.who
    a = f"{s} {fx.claim(f, v1)}"  # the fact itself, never "as the record states" (rule 12)
    s1, s2 = fx.shown(f, v1), fx.shown(f, v2)
    why = (
        f"The same sender's later message replaces {s1} with {s2}, "
        "so the record's figure does not stand."
    )
    lead = Spec("ovr_later_correction", K.EVENT, cap(a), core, why)
    irr = spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False)
    return c, siblings(rng, lead, [irr], 0.3, 1)
