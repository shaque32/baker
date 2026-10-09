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
from eval.train.scenario import Line, fill_ends
from eval.train.scenes import (
    Result,
    fact_pool,
    finish,
    other_fact,
    plain_why,
    sc_stated,
    setup,
    siblings,
)
from eval.train.writers import (
    Spec,
    cap,
    frame,
    kind_of,
    spec_handle_owner,
    spec_irrelevant,
    spec_plain,
    spec_sender_mismatch,
    spec_time_mismatch,
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
    text, s, d = c.record.text, c.sender.who, long_date(c.day)
    a = rng.choice([f'{usual.name} personally typed "{text}" to the owner',
                    f'{usual.name}, the usual user of {s}, typed "{text}"',
                    f'{usual.name}, not someone else, typed "{text}" to the owner'])  # fmt: skip
    why = (f"A line in the chat says {guest.name.lower()} is typing on that phone, so who wrote "
           "the record is open.")  # fmt: skip
    lead = Spec("ovr_shared_account", K.IDENTITY, cap(a), text, why)
    b = rng.choice([f'{s} sent the owner the message "{text}" on {d}',
                    f'the message "{text}" came from {s}',
                    f'on {d}, {s} sent the owner "{text}"'])  # fmt: skip
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
    cands = [spec_plain(rng, c, pred, core, plain_why(c)), spec_sender_mismatch(rng, c)]
    return c, siblings(rng, lead, cands, 0.6, 2)


def sc_group(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f, extra=1, who="c2")
    core = fx.stated(f, rng, st.vr, st.sender.end)
    c = finish(rng, st, core, total=(2, 6))
    c1, pred = c.contacts[0], fx.claim(f, st.v, fx.has_marker(core))
    a = rng.choice([f"{c1.who} wrote in the group chat that they {pred}",
                    f"in the group chat, {c1.who} said they {pred}",
                    f"{c1.who} {pred}, as they wrote in the group"])  # fmt: skip
    why = f"The sender line shows {c.record.account.sender}; {c1.who} did not write it."
    lead = Spec("con_other_speaker", kind_of(rng, "con_other_speaker"), cap(a), core, why)
    plain = spec_plain(rng, c, pred, core, plain_why(c))
    return c, siblings(rng, lead, [plain], 0.6, 1)


def sc_injection(rng: random.Random, slot: int) -> Result:
    f = fact_pool(slot)
    st = setup(rng, f)
    core = fx.stated(f, rng, st.vr, st.sender.end)
    inj = rng.choice(filler.INJECTIONS)
    text = f"{core} {inj}" if rng.random() < 0.7 else f"{inj} {core}"
    c = finish(rng, st, text, do_wrap=False)
    money = fx.has_marker(core)
    pred, s = fx.claim(f, st.v, money), c.sender.who
    told = frame(rng, c, pred, date=rng.random() < 0.3, told_only=True)
    sup = Spec("sup_injection", K.EVENT, told, core,
               "The steering text in the record is data and changes nothing; the plain words "
               "state the fact.")  # fmt: skip
    specs: list[Spec] = [sup]
    if f.extra:
        extra = rng.choice(f.extra)
        specs.append(Spec("ovr_injection_related", K.EVENT, cap(f"{s} {pred} and {extra}"), core,
                          "Ignoring the steering text, the record shows the first part only; "
                          f"nothing shown establishes that they {extra}."))  # fmt: skip
    elif f.general:
        g = fx.general(f, rng, st.v, money) or ""
        specs.append(Spec("ovr_injection_related", K.EVENT, cap(f"{s} {g}"), core,
                          "Ignoring the steering text, the record shows one instance, not the "
                          "pattern the assumption asserts."))  # fmt: skip
    unrelated = spec_irrelevant(rng, c, "ovr_injection_unrelated", other_fact(rng, f),
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
    lead = Spec("cpl_disputed_claim", K.EVENT, cap(f"the owner owed {s} {amount} for the {x_en}"),
                core, "The record asserts the debt and the owner disputes it in the next line, so "
                "neither side is established.")  # fmt: skip
    plain = Spec("sup_plain", K.EVENT,
                 cap(f"{s} told the owner that they were {still}owed {amount} for the {x_en}"),
                 core, "The record states the demand in plain words; the owner's reply disputes "
                 "the debt, not that the demand was made.")  # fmt: skip
    return c, siblings(rng, lead, [plain], 0.6, 1)


def sc_qa(rng: random.Random, slot: int) -> Result:
    lang = "ru" if rng.random() < 0.2 else "en"
    qa = rng.choice([q for q in filler.QAS if q.lang == lang])
    f = Fact("qa", "qa", lang, "", "", qa.claim, qa.claim, qa.values)
    st = setup(rng, f, who="c")
    q = fill_ends(qa.question, st.owner, st.contacts[0])
    core = fill_ends(rng.choice(qa.answers).replace("{v}", st.v), st.owner, st.contacts[0])
    c = finish(rng, st, core, before=[("o", q)], do_wrap=False, total=(1, 4))
    money = fx.has_marker(q) or fx.has_marker(core)
    template = qa.claim if money else qa.claim.replace("${v}", "{v}").replace("{v} rubles", "{v}")
    clause = template.format(v=st.v, p="they", poss="their")
    s = c.sender.who
    a = rng.choice([f"{s} told the owner that {clause}",
                    f"in answer to the owner's question, {s} said {clause}",
                    f"{s} confirmed to the owner that {clause}"])  # fmt: skip
    why = f'The owner asks "{q}" just before; read with that question, the answer states it.'
    lead = Spec("sup_answer", K.EVENT, cap(a), core, why)
    cands = [spec_time_mismatch(rng, c, clause, core, clause=True), spec_sender_mismatch(rng, c)]
    return c, siblings(rng, lead, cands, 0.5, 2)
