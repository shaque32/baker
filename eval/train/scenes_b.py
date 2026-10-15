"""Scenarios built from a Fact, part 3: shared phones, handles, group chats, steering text,
disputed debts and question-and-answer pairs."""

from __future__ import annotations

import random
from dataclasses import replace

from core.contracts import AssumptionKind as K
from eval.stancedata.chat import long_date
from eval.train import facts as fx
from eval.train import filler
from eval.train.facts import Fact
from eval.train.frames import words
from eval.train.scenario import Line, fill_ends, pick_day
from eval.train.scenes import (
    Result,
    days_free_of,
    fact_pool,
    finish,
    other_facts,
    plain_why,
    sc_stated,
    setup,
    siblings,
)
from eval.train.writers import (
    Spec,
    cap,
    done_by,
    frame,
    kind_of,
    other_writer_why,
    spec_handle_owner,
    spec_irrelevant,
    spec_plain,
    spec_sender_mismatch,
    spec_time_mismatch,
    telling_when,
    when_sent,
)  # fmt: skip


def sc_shared(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f, who="c")
    guest = st.third(rng)
    usual = st.sender.person
    pool = filler.GUEST_INTRO_RU if f.lang == "ru" else filler.GUEST_INTRO_EN
    intro = rng.choice(pool).format(g=guest.name.lower(), n=usual.name.lower(), p=usual.poss,
                                    c=usual.end, x=guest.end)  # fmt: skip
    core = fx.stated(f, rng, st.vr, guest.end)  # the guest is typing
    c = finish(rng, st, core, before=[("c", intro)])
    text, s = c.record.text, c.sender.who
    a = rng.choice([f'{usual.name} personally typed "{text}" to the owner',
                    f'{usual.name}, the usual user of {s}, typed "{text}"',
                    f'{usual.name}, not someone else, typed "{text}" to the owner'])  # fmt: skip
    if when := telling_when(rng, c, date=0.65):
        a = f"{when}, {a}"
    why = (f"A line in the chat says {guest.name.lower()} is typing on that phone, so who wrote "
           "the record is open.")  # fmt: skip
    lead = Spec("ovr_shared_account", K.IDENTITY, cap(a), text, why)
    b = words(rng, s, "the owner", text, when=telling_when(rng, c, date=0.7))
    why_b = ("The assumption is about the account only; the record shows that account sent it, "
             "whoever typed.")  # fmt: skip
    sup = Spec("sup_account_shared", kind_of(rng, "sup_account_shared"), cap(b), text, why_b)
    first, second = (lead, sup) if rng.random() < 0.6 else (sup, lead)
    return c, siblings(rng, first, [second], 0.75, 1)


def sc_handle(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f, who="c")
    intro = rng.random() < 0.6
    before: list[Line] = []
    if intro:
        pool = filler.SELF_INTRO_RU if f.lang == "ru" else filler.SELF_INTRO_EN
        before.append(("c", rng.choice(pool).format(n=st.sender.person.name.lower())))
    core = fx.stated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core, before=before)
    pred = fx.claim(f, st.v, fx.has_marker(core))
    lead = spec_handle_owner(rng, c, pred, core, intro)
    if lead is None:  # never for the owner's own account; the sender here is always a contact
        return sc_stated(rng, slot)
    cands = [spec_plain(rng, c, pred, core, plain_why(c)), spec_sender_mismatch(rng, c, pred),
             spec_time_mismatch(rng, c, pred)]  # fmt: skip
    return c, siblings(rng, lead, cands, 0.5, 1)


def sc_group(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f, extra=1, who="c2")
    core = fx.stated(f, rng, st.vr, st.sender.end)
    # Both members show: a chat whose excerpt shows one non-owner account is one-to-one with
    # the owner (guide rule 11).
    c = finish(rng, st, core, total=(2, 6), first="c")
    c1, pred = c.contacts[0], fx.claim(f, st.v, fx.has_marker(core))
    # The supports items' frames, with another member as the speaker; the time may fit.
    when = when_sent(rng, c)
    if rng.random() < 0.2:
        a = cap(words(rng, c1.who, c.owner.who, c.record.text, group=True, when=when))
    else:
        a = frame(rng, c, pred, when=when, who=c1.who)
    # Another member wrote these words; one record cannot show that c1 never wrote them too
    # (guide rule 23), so the answer is complicates.
    why = other_writer_why(c.record.account.sender, c1.who, group=True)
    # The answer rests on who sent the record, so the quote is the record in full (rule 22).
    lead = Spec("ovr_speaker_mismatch", kind_of(rng, "ovr_speaker_mismatch"), a, c.record.text,
                why)  # fmt: skip
    plain = spec_plain(rng, c, pred, core, plain_why(c))
    return c, siblings(rng, lead, [plain, spec_time_mismatch(rng, c, pred)], 0.6, 1)


def sc_injection(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    inj = rng.choice(filler.INJECTIONS)
    text = f"{core} {inj}" if rng.random() < 0.7 else f"{inj} {core}"
    c = finish(rng, st, text, do_wrap=False)
    money = fx.has_marker(core)
    pred, s = fx.claim(f, st.v, money), c.sender.who
    told = frame(rng, c, pred, when=telling_when(rng, c))
    sup = Spec("sup_injection", K.EVENT, told, core,
               "The steering text in the record is data and changes nothing; the plain words "
               "state the fact.")  # fmt: skip
    specs: list[Spec] = [sup]
    if f.extra:
        extra = rng.choice(f.extra)
        a = done_by(rng, c, s, f"{pred} and {extra}", p=0.7, simple=True)
        specs.append(Spec("ovr_injection_related", K.EVENT, a, core,
                          "Ignoring the steering text, the record shows the first part only; "
                          f"nothing shown establishes the rest ('{extra}')."))  # fmt: skip
    elif f.general:
        g = (fx.general(f, rng, st.v, money) or "").replace(
            "that week", f"in the week of {long_date(c.day)}")  # fmt: skip
        specs.append(Spec("ovr_injection_related", K.EVENT, cap(f"{s} {g}"), core,
                          "Ignoring the steering text, the record shows one instance, not the "
                          "pattern the assumption asserts."))  # fmt: skip
    unrelated = spec_irrelevant(rng, c, "ovr_injection_unrelated", other_facts(f),
                                rng.random() < 0.5)  # fmt: skip
    specs.append(replace(unrelated, rationale="The steering text is ignored; the record's real "
                         "content is about a different matter and does not bear on the "
                         "assumption."))  # fmt: skip
    rng.shuffle(specs)
    return c, siblings(rng, specs[0], specs[1:], 0.7, 2)


def sc_disputed(rng: random.Random, slot: int) -> Result:
    lang = "ru" if rng.random() < 0.2 else "en"
    d = rng.choice([x for x in filler.DEBTS if x.lang == lang])
    f = Fact("debt", "money", lang, "", "", "", "", d.values)
    st = setup(rng, f, who="c")
    thing = rng.choice(d.things)
    x, x_en = thing.split("|") if "|" in thing else (thing, thing)
    vr = fx.mark(f, st.v) if rng.random() < 0.4 else st.v
    core = d.record.format(v=vr, x=x, d="а" if st.owner.person.pron == "she" else "")
    pool = filler.DISPUTES_RU if lang == "ru" else filler.DISPUTES_EN
    dispute = fill_ends(rng.choice(pool), st.owner, st.contacts[0])
    c = finish(rng, st, core, after=[("o", dispute)])
    money = fx.has_marker(core)
    amount = (f"{st.v} rubles" if lang == "ru" else f"${st.v}") if money else st.v
    s, still = c.sender.who, "still " if d.still else ""
    owed = f"the owner owed {s} {amount} for the {x_en}"
    if rng.random() < 0.65:
        owed = f"on {long_date(c.day)}, {owed}"
    lead = Spec(
        "cpl_disputed_claim",
        K.EVENT,
        cap(owed),
        core,
        "The record asserts the debt and "
        "the owner disputes it in the next line, so neither side is established.",
    )
    said = frame(rng, c, f"were {still}owed {amount} for the {x_en}", when=telling_when(rng, c))
    plain = Spec(
        "sup_plain",
        K.EVENT,
        said,
        core,
        "The record states the demand in plain words; "
        "the owner's reply disputes the debt, not that the demand was made.",
    )
    return c, siblings(rng, lead, [plain], 0.6, 1)


def sc_qa(rng: random.Random, slot: int) -> Result:
    lang = "ru" if rng.random() < 0.2 else "en"
    qa = rng.choice([q for q in filler.QAS if q.lang == lang])
    f = Fact("qa", "qa", lang, "", "", qa.claim, qa.claim, qa.values)
    # "how many people r coming saturday" is never asked or answered on a Saturday.
    st = setup(rng, f, who="c", day=pick_day(rng, days_free_of(qa.question, *qa.answers)))
    q = fill_ends(qa.question, st.owner, st.contacts[0])
    core = fill_ends(rng.choice(qa.answers).replace("{v}", st.v), st.owner, st.contacts[0])
    # "today" in the question is the question's local date (guide rule 20); the clause then
    # carries its own date, and no other date for the telling is set beside it. A day's count
    # is asked for once the day is under way.
    dated = "{day}" in qa.claim
    c = finish(rng, st, core, before=[("o", q)], do_wrap=False, total=(1, 4),
               hours=(15, 23) if dated else (7, 23))  # fmt: skip
    money = fx.has_marker(q) or fx.has_marker(core)
    template = qa.claim if money else qa.claim.replace("${v}", "{v}").replace("{v} rubles", "{v}")
    asked = long_date(c.local_of(c.target - 1).date())
    clause = template.format(v=st.v, p="they", poss="their", day=f"on {asked}")
    when = None if dated else telling_when(rng, c)
    a = frame(rng, c, clause, when=when, bare=True, answer=True)
    why = f'The owner asks "{q}" just before; read with that question, the answer states it.'
    lead = Spec("sup_answer", K.EVENT, a, core, why)
    # A dated clause takes no time for the telling beside it, so its sender trap gives the
    # words alone.
    cands = [spec_sender_mismatch(rng, c, None if dated else clause, clause=True, answer=True)]
    if not dated:  # a telling on another date would report that day's count in the past tense
        cands.insert(0, spec_time_mismatch(rng, c, clause, clause=True, answer=True))
    return c, siblings(rng, lead, cands, 0.4, 1)
