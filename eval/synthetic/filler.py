"""Background chatter for case01. SYNTHETIC.

Seeded and deterministic. Filler only uses background threads (owner <-> a person who is not
part of any trap), never writes WhatsApp inside the gap window, and never uses a reserved word,
so it cannot create or break a planted trap.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from eval.synthetic.case01_story import (
    CASE_END,
    CASE_START,
    WA_GAP_END,
    WA_GAP_START,
    Call,
    Msg,
    eastern_offset_min,
)

EN = (
    "u up?",
    "omw",
    "running 10 min late",
    "lol",
    "sounds good",
    "can u call me later",
    "did u eat",
    "heading home",
    "ok cool",
    "thx",
    "np",
    "see u tomorrow",
    "traffic is crazy",
    "what time?",
    "after 6 works",
    "cant today",
    "maybe weekend",
    "haha true",
    "good morning",
    "how was work",
    "long day",
    "im tired",
    "rain again",
    "got it",
    "on my way back",
    "can u grab milk",
    "rent is due friday",
    "the heat is off again",
    "ill text u when im there",
    "parking was a nightmare",
    "nice",
    "yeah",
    "nah",
    "bet",
    "who's coming",
    "just landed",
    "phone almost dead",
    "pick up some bread",
    "happy bday!!",
    "game tonight?",
    "knicks lost again",
    "gym at 7?",
    "leg day lol",
    "skipping today",
    "ok see u there",
    "door code is 4412",
    "fixing the sink tomorrow",
    "send me the address",
    "almost there",
    "five min",
    "dinner at moms sunday",
    "can u pick me up",
    "battery light came on",
    "oil change done",
    "invoice paid",
    "customer wants it by friday",
    "need a quote for brake pads",
    "in stock?",
    "two sets of tires 225/45r17",
    "delivery tuesday am",
    "thanks again",
    "all good",
)

RU = (
    "привет",
    "как дела?",
    "всё хорошо",
    "позвони мне",
    "я на работе",
    "скоро буду",
    "ты где?",
    "спасибо",
    "доброе утро",
    "спокойной ночи",
    "как мама?",
    "купи хлеба",
    "я дома",
    "устал",
    "в субботу приедешь?",
    "давай завтра",
    "не могу сейчас",
    "ладно",
    "хорошо",
    "люблю тебя",
    "ты поел?",
    "холодно сегодня",
    "напиши когда доедешь",
    "ок",
    "мама передаёт привет",
    "приезжай на ужин",
    "посмотри фото",
    "с днём рождения!",
    "как работа?",
    "перезвоню",
    "всё нормально",
    "до завтра",
)

ES = ("ya llegué", "gracias mijo", "llámame", "te quiero", "cuídate", "ok mamá")


@dataclass(frozen=True)
class FillerThread:
    device: str
    owner_acct: str
    other_acct: str
    n: int
    langs: tuple[str, ...]  # pool keys, chosen per message
    calls: int = 0  # phone calls; only for SMS threads


FILLER_THREADS: tuple[FillerThread, ...] = (
    FillerThread("item1", "pet_sms", "ilya_sms", 260, ("en",), calls=10),
    FillerThread("item1", "pet_wa", "katya_wa", 220, ("ru", "ru", "en")),
    FillerThread("item1", "pet_wa", "mamap_wa", 180, ("ru",)),
    FillerThread("item1", "pet_sms", "jake_sms", 120, ("en",), calls=4),
    FillerThread("item1", "pet_sms", "landlord_sms", 40, ("en",), calls=2),
    FillerThread("item1", "pet_tg", "oksana_tg", 140, ("ru", "ru", "en")),
    FillerThread("item2", "rey_sms", "jenna_sms", 240, ("en",), calls=12),
    FillerThread("item2", "rey_wa", "jenna_wa", 120, ("en",)),
    FillerThread("item2", "rey_sms", "luis_sms", 120, ("en",), calls=5),
    FillerThread("item2", "rey_wa", "mamar_wa", 160, ("en", "es")),
    FillerThread("item2", "rey_sms", "kevin_sms", 60, ("en",), calls=2),
    FillerThread("item2", "rey_sms", "tires_sms", 50, ("en",), calls=2),
    FillerThread("item2", "rey_tg", "dre_tg", 130, ("en",)),
)

POOLS = {"en": EN, "ru": RU, "es": ES}


def _in_wa_gap(at: datetime) -> bool:
    return WA_GAP_START <= at < WA_GAP_END


def _random_time(rng: random.Random) -> datetime:
    days = (CASE_END - CASE_START).days
    day = CASE_START + timedelta(days=rng.randrange(days))
    # local hour 8..23, converted back to UTC with the right offset for that date
    local_hour = rng.choice(range(8, 24))
    at = day + timedelta(hours=local_hour, minutes=rng.randrange(60), seconds=rng.randrange(60))
    # CASE_START is local midnight in UTC; correct for a DST change inside the range
    return at - timedelta(minutes=eastern_offset_min(at) - eastern_offset_min(CASE_START))


def make_filler(seed: int, accounts_app: dict[str, str]) -> tuple[list[Msg], list[Call]]:
    rng = random.Random(seed)  # noqa: S311 - synthetic data, not crypto
    msgs: list[Msg] = []
    calls: list[Call] = []
    for t in FILLER_THREADS:
        is_wa = accounts_app[t.owner_acct] == "WhatsApp"
        made = 0
        while made < t.n:
            at = _random_time(rng)
            burst = min(rng.randint(2, 8), t.n - made)
            sender_is_owner = rng.random() < 0.5
            for _ in range(burst):
                if at >= CASE_END:
                    break
                if is_wa and _in_wa_gap(at):
                    break
                lang = rng.choice(t.langs)
                body = rng.choice(POOLS[lang])
                sender, to = (
                    (t.owner_acct, t.other_acct)
                    if sender_is_owner
                    else (t.other_acct, t.owner_acct)
                )
                msgs.append(
                    Msg(f"f:{t.device}:{t.other_acct}:{made:04d}", at, sender, to, body, lang)
                )
                made += 1
                at += timedelta(seconds=rng.randint(20, 900))
                if rng.random() < 0.6:
                    sender_is_owner = not sender_is_owner
        for i in range(t.calls):
            at = _random_time(rng)
            outgoing = rng.random() < 0.5
            caller, callee = (
                (t.owner_acct, t.other_acct) if outgoing else (t.other_acct, t.owner_acct)
            )
            answered = rng.random() < 0.8
            calls.append(
                Call(
                    f"fc:{t.device}:{t.other_acct}:{i:02d}",
                    at,
                    caller,
                    callee,
                    rng.randint(15, 900) if answered else 0,
                    answered,
                )
            )
    return msgs, calls
