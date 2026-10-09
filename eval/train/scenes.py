"""Scenarios built from a Fact: one chat, one record, one or more sibling specs.

Each scenario function takes the scenario's random stream and the index of its first item, and
returns the Chat and the Specs built on its record; siblings share the record and differ in the
assumption and the family. Assumptions on trap, contradict and irrelevant families state the fact
itself (guide rule 12); only supports families and the message-level exceptions report what the
message says.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from core.contracts import AssumptionKind as K
from eval.train import facts as fx
from eval.train.facts import Fact
from eval.train.facts_en_a import FACTS_A
from eval.train.facts_en_b import FACTS_B
from eval.train.facts_en_c import FACTS_C
from eval.train.facts_en_d import FACTS_D
from eval.train.facts_en_e import FACTS_E
from eval.train.facts_en_f import FACTS_F
from eval.train.facts_ru import FACTS_RU
from eval.train.names import Party, Person, cast, third_party
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

FACTS_EN = FACTS_A + FACTS_B + FACTS_C + FACTS_D + FACTS_E + FACTS_F
ALL_FACTS = FACTS_EN + FACTS_RU
Result = tuple[Chat, list[Spec]]
PHI = 0.6180339887498949


def fact_pool(slot: int, ru: float = 0.2) -> Fact:
    """One fact per scenario, spread evenly over both pools.

    `slot` counts the fact scenarios built so far. A low-discrepancy sequence (multiples of phi)
    of it picks the fact, so consecutive scenarios take facts far apart and every fact backs
    nearly the same number of scenarios; the first `ru` share of the sequence takes a Russian
    fact.
    """
    u = (slot * PHI) % 1.0
    pool, t = (FACTS_RU, u / ru) if u < ru else (FACTS_EN, (u - ru) / (1 - ru))
    return pool[min(int(t * len(pool)), len(pool) - 1)]


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
    v: str  # the value as an assumption writes it
    vr: str  # the value as the record writes it, sometimes with a currency marker
    values: tuple[str, ...] = ()  # the fact's values, minus any cast member's first name

    def names(self) -> set[str]:
        return {p.person.name for p in [self.owner, *self.contacts]}

    def third(self, rng: random.Random) -> Person:
        return third_party(rng, self.f.lang, self.names())


def other_value(rng: random.Random, st: Setup, v: str) -> str:
    return rng.choice([x for x in st.values if x != v])


def marked(st: Setup, v: str) -> str:
    """`v` written as the record writes values in this scenario (with the marker if the record
    value carries one)."""
    return fx.mark(st.f, v) if st.vr != st.v else v


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
    v = rng.choice(values)
    vr = fx.mark(f, v) if f.money and rng.random() < 0.4 else v
    return Setup(f, app, owner, contacts, tz, day or pick_day(rng), who, sender, other, v, vr,
                 values)  # fmt: skip


def finish(rng: random.Random, st: Setup, core: str, *, before: list[Line] | None = None,
           after: list[Line] | None = None, hours: tuple[int, int] = (7, 23), fold: int = 0,
           do_wrap: bool = True, after_fill: bool = True, safe_after: bool = False,
           total: tuple[int, int] = (1, 6)) -> Chat:  # fmt: skip
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
    text = wrap(rng, core, rec_lang) if do_wrap else core
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


def fact_lead(c: Chat, fam: str, kind: K, pred: str, core: str, why: str) -> Spec:
    """A lead that states the fact of the sender (guide rule 12)."""
    return Spec(fam, kind, cap(f"{c.sender.who} {pred}"), core, why)


def sc_stated(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core)
    money = fx.has_marker(core)
    pred = fx.claim(f, st.v, money)
    lead = (
        spec_verbatim(rng, c)
        if rng.random() < 0.3
        else spec_plain(rng, c, pred, core, plain_why(c))
    )
    cands = [spec_time_mismatch(rng, c, pred, core), spec_sender_mismatch(rng, c),
             spec_handle_owner(rng, c, pred, core, False),
             spec_partial(rng, c, f, st.v, core, money), spec_count(rng, c, f, st.v, core, money),
             spec_time_window(rng, c), spec_contact(rng, c), spec_in_window(rng, c),
             spec_irrelevant(rng, c, "irr_other_topic", other_fact(rng, f), False),
             spec_plain(rng, c, pred, core, plain_why(c))]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.6)


def sc_exact(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.exact(f, rng, st.vr, st.sender.end)
    if core is None:
        return sc_stated(rng, slot)
    c = finish(rng, st, core)
    money = fx.has_marker(core)
    v2 = other_value(rng, st, st.v)
    why = (f"The record gives {fx.shown(f, st.v)} and rules out any other value; the "
           f"assumption says {fx.shown(f, v2)}.")  # fmt: skip
    lead = fact_lead(c, "con_other_value", kind_of(rng, "con_other_value"),
                     fx.claim(f, v2, money), core, why)  # fmt: skip
    pred = fx.claim(f, st.v, money)
    cands = [spec_plain(rng, c, pred, core, plain_why(c)), spec_time_mismatch(rng, c, pred, core),
             spec_handle_owner(rng, c, pred, core, False)]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.5, 2)


def _neg_pair(
    rng: random.Random, c: Chat, f: Fact, v: str, core: str, fam: str, why: str
) -> Result:
    money = fx.has_marker(core)
    lead = fact_lead(c, fam, K.EVENT, fx.claim(f, v, money), core, why)
    plain = spec_plain(rng, c, f"did not {fx.claim_base(f, v, money)}", core, plain_why(c),
                       told_only=True)  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.5, 1)


def sc_neg(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.negated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core)
    why = "The assumption's words appear inside a negation: the record says the act did not happen."
    return _neg_pair(rng, c, f, st.v, core, "ovr_negation", why)


def sc_denial(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    q = fx.asked(f, rng, st.vr, st.sender.end)
    other_who = "c" if st.who == "o" else "o"
    core = fx.negated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core, before=[(other_who, q)])
    why = "Asked directly, the sender denies it in plain words."
    return _neg_pair(rng, c, f, st.v, core, "con_denial", why)
