"""Scenarios built from a Fact: one chat, one record, one or more sibling specs.

Each scenario function takes the scenario's random stream and the index of its first item, and
returns the Chat and the Specs built on its record; siblings share the record and differ in the
assumption and the family. Assumptions on trap, contradict and irrelevant families state the fact
itself (guide rule 12); only supports families and the message-level exceptions report what the
message says. The two report families (guide v0.4) sit beside the same record's supports and
contradicts items: a told frame of what a denial or another value rules out, and "never told"
of what a record says.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date

from core.contracts import AssumptionKind as K
from eval.stancedata.chat import long_date
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
    clock12,
    filler_lines,
    named_weekdays,
    pick_day,
    pick_tz,
    record_time,
    weekday_clash,
)  # fmt: skip
from eval.train.writers import (
    ACT_CLOCK,
    ACT_DAY,
    Spec,
    act_before,
    cap,
    kind_of,
    quoted,
    spec_contact,
    spec_count,
    spec_handle_owner,
    spec_in_window,
    spec_irrelevant,
    spec_never_told,
    spec_partial,
    spec_plain,
    spec_sender_mismatch,
    spec_time_mismatch,
    spec_time_window,
    spec_told_frame,
    spec_undated_denial,
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


def other_facts(f: Fact) -> list[Fact]:
    """The facts of every other scene, for an irrelevant assumption beside a record of f."""
    return [g for g in ALL_FACTS if g.scene != f.scene]


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
    """Another of the fact's values; a weekday that is the record's own is never one (a
    correction to "monday" is never sent on a Monday)."""
    rest = [x for x in st.values if x != v]
    fit = [x for x in rest if st.day.weekday() not in named_weekdays(fx.claim(st.f, x))]
    return rng.choice(fit or rest)


def marked(st: Setup, v: str) -> str:
    """`v` written as the record writes values in this scenario (with the marker if the record
    value carries one)."""
    return fx.mark(st.f, v) if st.vr != st.v else v


def free_days(f: Fact) -> tuple[int, ...]:
    """The weekdays (0 = Monday) that none of the fact's values names, or () if none names one.

    A record that says "on monday" (or a correction to it) is never sent on a Monday, where the
    word would mean that very day; a dated assumption about a named weekday then has one natural
    date (guide rule 24 and the round-4 weekday rule).
    """
    named = named_days(f)
    return tuple(d for d in range(7) if d not in named) if named else ()


def named_days(f: Fact) -> set[int]:
    """The weekdays (0 = Monday) that any of the fact's values names."""
    return {fx.DAY_NAMES.index(w.lower()) for v in f.values
            for w in fx.DAY_WORD.findall(fx.claim(f, v))}  # fmt: skip


def month_days(f: Fact) -> int:
    """The latest day of the month any of the fact's values names ("paid the rent on the 8th"),
    or 0. The record is sent later in that month, so each value's day has one natural date,
    in the record's month and before it."""
    return max((int(m[1]) for v in f.values if (m := ACT_DAY.search(fx.claim(f, v)))),
               default=0)  # fmt: skip


def days_free_of(*texts: str) -> tuple[int, ...]:
    """The weekdays none of the texts names as one particular day, or () if none names one: a
    line such as "whats the plan for sat" is never sent on that day."""
    named: set[int] = set().union(*(named_weekdays(t) for t in texts))
    return tuple(d for d in range(7) if d not in named) if named else ()


def setup(rng: random.Random, f: Fact, *, extra: int = 0, who: str | None = None,
          day: date | None = None, texts: tuple[str, ...] = ()) -> Setup:  # fmt: skip
    """The cast, the value and the record's local date. The date is never a weekday that the
    fact's values or `texts` (lines the scenario will add) name as one particular day."""
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
    if day is None:
        # A fact whose values name every weekday leaves none free; the record's value decides.
        fits = set(free_days(f) or days_free_of(fx.claim(f, v)) or range(7))
        fits &= set(days_free_of(*texts) or range(7))
        day = pick_day(rng, tuple(sorted(fits)), after_mday=month_days(f))
    vr = fx.mark(f, v) if f.money and rng.random() < 0.4 else v
    return Setup(f, app, owner, contacts, tz, day, who, sender, other, v, vr, values)


def finish(rng: random.Random, st: Setup, core: str, *, before: list[Line] | None = None,
           after: list[Line] | None = None, hours: tuple[int, int] = (7, 23), fold: int = 0,
           do_wrap: bool = True, after_fill: bool = True, safe_after: bool = False,
           total: tuple[int, int] = (1, 6), quick: bool = False,
           first: str | None = None, placed: bool = False) -> Chat:  # fmt: skip
    """Pad the scenario lines with small talk, time them and assemble the Chat.

    A non-owner line is always on screen (guide rule 11); `first` makes the first small-talk
    line come from that party ("c" in a group chat, so both members show). With `safe_after`, no
    filler after the record can read as an answer or a confirmation (guide rule 13). With
    `quick`, the scenario's own lines sit within minutes of the record (a correction and what it
    corrects). With `placed` (a record that says where its sender is), no filler puts anyone
    anywhere ("im outside", "be there in 20"). Lines whose weekday words clash with their own
    date ("whats the plan for sat" sent on a Saturday) are drawn again.
    """
    for _ in range(60):
        chat = _finish_once(rng, st, core, before, after, hours, fold, do_wrap, after_fill,
                            safe_after, total, quick, first, placed)  # fmt: skip
        if not any(weekday_clash(m.text, chat.local_of(i).date())
                   for i, m in enumerate(chat.msgs)):  # fmt: skip
            return chat
    raise ValueError(f"no chat whose weekday words fit its dates for {core!r} on {st.day}")


def _finish_once(rng: random.Random, st: Setup, core: str, before: list[Line] | None,
                 after: list[Line] | None, hours: tuple[int, int], fold: int, do_wrap: bool,
                 after_fill: bool, safe_after: bool, total: tuple[int, int], quick: bool,
                 first: str | None, placed: bool) -> Chat:  # fmt: skip
    before, after = list(before or []), list(after or [])
    near = (len(before), len(after)) if quick else (0, 0)
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
        scene=st.f.scene, safe_after=safe_after, first=first or (None if has_contact else "c"),
        placed=placed,
    ) if need else ([], [])  # fmt: skip
    before, after = extra_before + before, after + extra_after
    lang = "mixed" if need and ctx_lang != rec_lang else rec_lang
    text = wrap(rng, core, rec_lang) if do_wrap else core
    when = record_time(rng, st.day, st.tz, hours, fold)
    return assemble(rng, tz=st.tz, app=st.app, owner=st.owner, contacts=st.contacts, lang=lang,
                    before=before, record=(st.who, text), after=after, when=when,
                    quick=near)  # fmt: skip


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


def more(rng: random.Random, lead: Spec, cands: list[Spec | None], p: float,
         most: int = 1) -> list[Spec]:  # fmt: skip
    """Siblings drawn apart from a scenario's own (see siblings), so that a family added to a
    scenario leaves the odds of its other siblings as they were."""
    return siblings(rng, lead, cands, p, most)[1:]


def plain_why(c: Chat) -> str:
    return (f"The record from {c.record.account.sender} states it in plain words; nothing in the "
            "context qualifies it.")  # fmt: skip


def fact_lead(c: Chat, fam: str, kind: K, pred: str, core: str, why: str) -> Spec:
    """A lead that states the fact of the sender (guide rule 12)."""
    return Spec(fam, kind, cap(f"{c.sender.who} {pred}"), core, why)


# The odds of the guide v0.4 families beside a scenario's own siblings (drawn apart, see more):
# a "never told" beside a stated fact; a told frame of the other value or a "never told" of the
# record's own beside another value; a told frame and an undated denial beside a denial.
Q_STATED, Q_EXACT, Q_NEG = 0.15, 0.4, 0.4


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
    cands = [spec_time_mismatch(rng, c, pred), spec_sender_mismatch(rng, c, pred),
             spec_handle_owner(rng, c, pred, core, False),
             spec_partial(rng, c, f, st.v, core, money), spec_count(rng, c, f, st.v, core, money),
             spec_time_window(rng, c), spec_contact(rng, c), spec_in_window(rng, c),
             spec_irrelevant(rng, c, "irr_other_topic", other_facts(f), False),
             spec_plain(rng, c, pred, core, plain_why(c))]  # fmt: skip
    never_told = more(rng, lead, [spec_never_told(rng, c, pred, core)], Q_STATED)
    return c, [*siblings(rng, lead, cands, 0.6), *never_told]


def sc_exact(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.exact(f, rng, st.vr, st.sender.end)
    if core is None:
        return sc_stated(rng, slot)
    c = finish(rng, st, core)
    money = fx.has_marker(core)
    v2 = other_value(rng, st, st.v)
    # Values are quoted: a weekday the record names is never read as the record's own date.
    why = (f"The record gives {quoted(st.vr)} and rules out any other value; the assumption "
           f"says {quoted(fx.claim_value(f, v2, money))}.")  # fmt: skip
    pred2 = fx.claim(f, v2, money)
    kind = kind_of(rng, "con_other_value")
    if fx.names_day(pred2) or ACT_DAY.search(pred2):
        # "the only day he came was tuesday" rules out a Wednesday before the message, not a
        # later one: the assumption dates the act before the record's date (guide rule 23).
        why += " The assumption dates the act before the message."
        lead = Spec("con_other_value", kind, act_before(rng, c, c.sender.who, pred2), core, why)
    else:
        lead = fact_lead(c, "con_other_value", kind, pred2, core, why)
    pred = fx.claim(f, st.v, money)
    cands = [spec_plain(rng, c, pred, core, plain_why(c)), spec_in_window(rng, c),
             spec_handle_owner(rng, c, pred, core, False),
             spec_sender_mismatch(rng, c, pred), spec_time_mismatch(rng, c, pred)]  # fmt: skip
    # A report of the value the record rules out (complicates), or that the sender never told
    # the value the record gives (contradicts), beside the other value it rules out.
    report = more(rng, lead, [spec_told_frame(rng, c, pred2, core),
                              spec_never_told(rng, c, pred, core)], Q_EXACT)  # fmt: skip
    return c, [*siblings(rng, lead, cands, 0.5, 3), *report]


# Acts done again and again (a shift's tips, laps, a sitter's pay, the rent each month) or at
# their own clock time ("closed the bar at 1"): "didnt" denies one occasion without naming it,
# so an assumption dated to another occasion would stay open. Their denials and negations say
# "never", which covers every occasion before the message.
REPEATED = frozenset({
    "tips", "close", "games", "court", "pickup", "clients", "poker", "landed", "rent", "gas",
    "tank", "hours", "paycheck", "tipout", "sessions", "laps", "lostgames", "sitter", "tutor",
    "groceries", "atm", "lashes", "braids", "color", "blowout", "haircut", "kidscuts",
    "extrashifts", "tabs", "tables", "bench", "trail", "savings", "tomom", "boston", "chicago",
    "checkin", "daycare", "trainer", "gym", "chair", "utilities", "phonebill", "loan",
    "insurance", "renters", "parkpass", "yoga", "copay", "oilchange", "storage", "landlord",
    "meds", "supplies", "developer", "booth", "bartab", "miles", "swap", "dentist", "airport",
    "lent", "ru_parking", "ru_gas", "ru_tips", "ru_close", "ru_kids", "ru_shift", "ru_hours",
    "ru_wash", "ru_sitter", "ru_haircut", "ru_manicure", "ru_color", "ru_lashes", "ru_rent",
    "ru_landed", "ru_utilities", "ru_gym", "ru_pool", "ru_meds", "ru_sister", "ru_lent",
    "ru_trainer", "ru_yoga", "ru_fine",
})  # fmt: skip


def _neg_pair(rng: random.Random, c: Chat, f: Fact, v: str, core: str, fam: str) -> Result:
    """A denial or a negated statement against the act it negates, dated before the record.

    The sender's words rule the act out only up to the moment they were sent (guide rule 23),
    so the assumption dates the act before the record's date, never by the record's own
    minute. When the words cover the time themselves ("never", a named day), the assumption is
    a plain date-level fact with no clock. The rationale says what the words state conflicts
    with the assumption; whether they are true is for the expert (rule 24).
    """
    money = fx.has_marker(core)
    q, t, d = quoted(core), clock12(c.local), long_date(c.day)
    pred = fx.claim(f, v, money)
    plain = fx.NEVER.search(core) is not None or fx.names_day(pred)
    a = act_before(rng, c, c.sender.who, pred, clock=0.0 if plain else 0.55)
    if fam == "con_denial":
        why = rng.choice([
            f"Asked directly, the sender answers {q} at {t} on {d}; what those words state "
            "cannot be true together with the assumption, which dates the act before the "
            "answer. Whether the denial is true is for the expert.",
            f"The sender's answer, sent at {t} on {d}, is {q}. What it states cannot be true "
            "together with the assumption, which places the act before the answer. Whether "
            "the answer is true is for the expert.",
        ])  # fmt: skip
    else:
        why = rng.choice([
            f"The assumption's act appears in the record inside a negation ({q}, sent at {t} on "
            f"{d}). What the sender's words state cannot be true together with the assumption, "
            "which dates the act before the message; whether they are true is for the expert.",
            f"On {d} the sender writes {q}, the assumption's act inside a negation. What those "
            "words state cannot be true together with the assumption, which places the act "
            "before the message; whether they are true is for the expert.",
        ])  # fmt: skip
    lead = Spec(fam, K.EVENT, a, core, why)
    plain_sib = spec_plain(rng, c, f"did not {fx.claim_base(f, v, money)}", core, plain_why(c),
                           told_only=True)  # fmt: skip
    # The same words against a report that the sender said the act happened (a told frame)
    # and, when the denial names no time, against the act with no time or a later one: both
    # complicates, beside the dated act this denial rules out (guide v0.4, rules 12 and 23).
    # A told frame always comes with the report of the denial itself ("said they did not"),
    # which supports: the two differ only in what the sender is reported to have said.
    cands = [spec_told_frame(rng, c, pred, core)]
    if undated(c, pred):
        cands.append(spec_undated_denial(rng, c, pred, core))
    sibs, extra = siblings(rng, lead, [plain_sib], 0.5, 1), more(rng, lead, cands, Q_NEG, 2)
    if any(s.family == "ovr_told_frame" for s in extra) and len(sibs) == 1:
        sibs.append(plain_sib)
    return c, [*sibs, *extra]


# Words that give a denial, or a question it may answer, a time of its own ("didnt pay him
# yesterday", "did u pay him on friday?"): such a denial covers that time, so it is never an
# undated one (guide rule 23). Broad on purpose: a word that only might name a time keeps the
# record out of ovr_undated_denial.
TIMED = re.compile(
    r"\b(yesterday|today|tonight|tmrw|tomorrow|morning|afternoon|evening|night|nights|week|"
    r"weekend|month|year|earlier|ago|last|this|since|until|till|before|after|then|already|yet|"
    r"anymore|again|noon|midnight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|"
    r"tue|tues|wed|thu|thur|thurs|fri|sat|sun|january|february|march|april|june|july|august|"
    r"september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\b|\b\d{1,2}(?::\d{2})?\s?(?:am|pm|a\.m\.|p\.m\.)|\bat \d|\bon the \d|\d(?:st|nd|rd|th)\b|"
    r"вчера|сегодня|завтра|утр|днём|днем|вечер|ноч|недел|месяц|\bгод|понедельник|вторник|"
    r"сред[уа]|четверг|пятниц|суббот|воскресень|раньше|назад|уже|ещё|еще|пока|после|до \d|"
    r"\b(?:in|on|by|since|until|till|for) may\b|\bmay \d|\b\d{1,2}/\d{1,2}\b|январ|феврал|"
    r"\bмарт|апрел|\bма[йя]\b|\bиюн|\bиюл|август|сентябр|октябр|ноябр|декабр",
    re.I,
)


def undated(c: Chat, pred: str) -> bool:
    """Whether a denial record names no time of its own: neither its words, nor a question
    sent before it, nor the act it denies ("returned the drill on monday") names one."""
    if fx.names_day(pred) or ACT_DAY.search(pred) or ACT_CLOCK.search(pred):
        return False
    asked = [m.text for m in c.msgs[: c.target] if "?" in m.text]
    return not any(TIMED.search(t) for t in [c.record.text, *asked])


def sc_neg(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.negated(f, rng, st.vr, st.sender.end, never=f.key in REPEATED)
    c = finish(rng, st, core)
    return _neg_pair(rng, c, f, st.v, core, "ovr_negation")


def sc_denial(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    q = fx.asked(f, rng, st.vr, st.sender.end)
    other_who = "c" if st.who == "o" else "o"
    core = fx.negated(f, rng, st.vr, st.sender.end, never=f.key in REPEATED, answer=True)
    c = finish(rng, st, core, before=[(other_who, q)], quick=True)
    return _neg_pair(rng, c, f, st.v, core, "con_denial")
