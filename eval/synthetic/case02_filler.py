"""Background chatter for case02 (HIDDEN eval case). SYNTHETIC.

Seeded and deterministic. Filler only uses background threads (an owner with a person who is in
no trap), plus the 'Westside Flips' group before Mar 18. It never uses a reserved word, never
writes in the BRANDT and MERCER thread on Mar 24 (the negation trap's day), and stops each phone
at its seizure, so it cannot create or break a planted trap.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from eval.synthetic.case02_story import (
    CASE_START,
    GROUPS,
    ITEM1_END,
    ITEM2_END,
    Call,
    Msg,
    central,
    central_offset_min,
    ct,
)

EN = (
    "wya",
    "omw",
    "lmk",
    "bet",
    "say less",
    "no cap",
    "fr fr",
    "lowkey tired",
    "deadass",
    "bruh",
    "smh",
    "ight",
    "tbh idk",
    "running 10 late",
    "sounds good",
    "u up?",
    "call u later",
    "did u eat",
    "heading home",
    "ok cool",
    "thx",
    "np",
    "see u tmrw",
    "traffic on the kennedy is insane",
    "what time?",
    "after 6 works",
    "cant today",
    "maybe this weekend",
    "haha true",
    "morning",
    "how was work",
    "long day",
    "snowing again",
    "got it",
    "on my way back",
    "grab milk pls",
    "rent is due the 1st",
    "heat is out again",
    "text me when ur there",
    "parking was a nightmare",
    "nice",
    "yeah",
    "nah",
    "who's coming",
    "phone about to die",
    "happy bday!!",
    "bulls game tonight?",
    "they lost again lol",
    "gym at 7?",
    "skipping today",
    "ok see u there",
    "send me the address",
    "almost there",
    "five min",
    "dinner sunday?",
    "can u pick me up",
    "check engine light came on",
    "oil change done",
    "thanks again",
    "all good",
    "W",
    "thats crazy",
    "lol",
    "same",
)

# Spanish with Chicago Mexican slang. Nothing here touches a trap.
ES = (
    "qué onda",
    "ahorita no puedo",
    "no manches",
    "órale",
    "ya comiste?",
    "te marco al rato",
    "está bien",
    "gracias mija",
    "cuídate mucho",
    "dónde andas?",
    "llego en 10",
    "bendiciones",
    "te quiero mucho",
    "jajaja",
    "sale",
    "nel",
    "simón",
    "qué haces?",
    "mañana te veo",
    "salúdame a tu papá",
    "ya llegó tu tía",
    "hace mucho frío",
    "no se me olvida",
    "a qué hora sales?",
    "ya voy",
    "buenas noches",
    "buenos días mijo",
    "qué padre",
    "ni modo",
    "luego te cuento",
    "está cañón",
    "échale ganas",
)

# Work chatter for BRANDT's dispatcher thread.
WORK = (
    "route 14 today",
    "truck 9 is in the bay",
    "can u cover saturday",
    "clock in by 6",
    "invoice sent",
    "customer wants a call back",
    "running behind on deliveries",
    "pallet jack is broken again",
    "timesheet due friday",
    "ok boss",
    "copy",
    "on it",
)

POOLS = {"en": EN, "es": ES, "work": WORK}


@dataclass(frozen=True)
class FillerThread:
    device: str
    owner_acct: str
    other: str  # Acct key, or a GROUPS key
    n: int
    langs: tuple[str, ...]  # pool keys, chosen per message
    calls: int = 0
    call_owner: str | None = None  # SMS accounts used for calls
    call_other: str | None = None
    end: datetime | None = None  # defaults to the device's seizure
    skip_dates: tuple[str, ...] = ()  # Central dates (YYYY-MM-DD) with no filler


GROUP_FILLER_END = ct("2026-03-18 00:00:00")

FILLER_THREADS: tuple[FillerThread, ...] = (
    FillerThread(
        "item1",
        "nb_sms",
        "kyle_sms",
        170,
        ("en",),
        calls=8,
        call_owner="nb_sms",
        call_other="kyle_sms",
        skip_dates=("2026-03-24",),
    ),
    FillerThread("item1", "nb_wa", "erin_wa", 150, ("en",)),
    FillerThread(
        "item1",
        "nb_sms",
        "gary_sms",
        70,
        ("work", "work", "en"),
        calls=6,
        call_owner="nb_sms",
        call_other="gary_sms",
    ),
    FillerThread("item1", "nb_ig", "erin_ig", 50, ("en",)),
    FillerThread("item1", "nb_tg", "theo_tg", 90, ("en",)),
    FillerThread("item1", "nb_wa", "wf", 70, ("en", "en", "es"), end=GROUP_FILLER_END),
    FillerThread(
        "item2",
        "rq_sms",
        "dani_sms",
        200,
        ("en", "en", "es"),
        calls=10,
        call_owner="rq_sms",
        call_other="dani_sms",
    ),
    FillerThread(
        "item2",
        "rq_wa",
        "mama_wa",
        150,
        ("es",),
        calls=4,
        call_owner="rq_sms",
        call_other="mama_sms",
    ),
    FillerThread(
        "item2",
        "rq_wa",
        "vic_wa",
        110,
        ("es", "es", "en"),
        calls=3,
        call_owner="rq_sms",
        call_other="vic_sms",
    ),
    FillerThread("item2", "rq_ig", "jay_ig", 60, ("en",)),
    FillerThread("item2", "rq_wa", "mari_wa", 40, ("es", "en")),
)

DEVICE_END = {"item1": ITEM1_END, "item2": ITEM2_END}


def _random_time(rng: random.Random, end: datetime) -> datetime:
    days = (end - CASE_START).days
    day = CASE_START + timedelta(days=rng.randrange(days))
    # Central hour 8..23, converted back to UTC with the right offset for that date
    local_hour = rng.choice(range(8, 24))
    at = day + timedelta(hours=local_hour, minutes=rng.randrange(60), seconds=rng.randrange(60))
    # CASE_START is Central midnight in UTC; correct for the DST change inside the range
    return at - timedelta(minutes=central_offset_min(at) - central_offset_min(CASE_START))


def make_filler(seed: int) -> tuple[list[Msg], list[Call]]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not crypto
    msgs: list[Msg] = []
    calls: list[Call] = []
    for t in FILLER_THREADS:
        end = t.end or DEVICE_END[t.device]
        group = GROUPS.get(t.other)
        made = 0
        while made < t.n:
            at = _random_time(rng, end)
            burst = min(rng.randint(2, 8), t.n - made)
            sender_is_owner = rng.random() < 0.5
            for _ in range(burst):
                if at >= end or central(at).strftime("%Y-%m-%d") in t.skip_dates:
                    break
                lang = rng.choice(t.langs)
                body = rng.choice(POOLS[lang])
                lang_code = "es" if lang == "es" else "en"
                if group is not None:
                    sender = rng.choice(group.members)
                    to = group.key
                else:
                    sender, to = (
                        (t.owner_acct, t.other) if sender_is_owner else (t.other, t.owner_acct)
                    )
                msgs.append(
                    Msg(f"f:{t.device}:{t.other}:{made:04d}", at, sender, to, body, lang_code)
                )
                made += 1
                at += timedelta(seconds=rng.randint(20, 900))
                if rng.random() < 0.6:
                    sender_is_owner = not sender_is_owner
        for i in range(t.calls):
            if t.call_owner is None or t.call_other is None:
                raise ValueError(f"{t.other}: calls need call_owner and call_other")
            at = _random_time(rng, end)
            while central(at).strftime("%Y-%m-%d") in t.skip_dates:
                at = _random_time(rng, end)
            outgoing = rng.random() < 0.5
            caller, callee = (
                (t.call_owner, t.call_other) if outgoing else (t.call_other, t.call_owner)
            )
            answered = rng.random() < 0.8
            calls.append(
                Call(
                    f"fc:{t.device}:{t.call_other}:{i:02d}",
                    at,
                    caller,
                    callee,
                    rng.randint(15, 900) if answered else 0,
                    answered,
                )
            )
    return msgs, calls
