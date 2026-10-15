"""Text mechanics for the Baker-wording items: slots, the quotable span, unique picks, fillers.

A pool line marks the part an assumption may quote with [brackets] and its variable words with
{slots}. `fill` returns the message and its quotable span. `spread` gives the k-th item of a
family a pool line no earlier item of that family used, so record texts never repeat within a
family; once a pool is used up, the next lap adds a fixed decoration per lap.
"""

from __future__ import annotations

import math
import random
import re
import zlib

SLOTS: dict[str, tuple[str, ...]] = {
    "item": ("ladder", "drill", "cooler", "extension cord", "spare key", "van keys", "charger",
             "tool bag", "folding table", "car seat", "bike pump", "paperwork", "invoice",
             "tile samples", "paint cans", "speaker", "dolly", "tarp", "air mattress", "printer",
             "router", "space heater", "jumper cables", "stroller", "toolbox", "sander",
             "box fan", "mini fridge", "rice cooker", "laptop bag", "duffel", "garden hose",
             "shop vac", "step stool", "monitor", "floor lamp", "suitcase", "camping chairs"),
    "place": ("the laundromat", "the bodega", "the shop", "the garage", "the gym", "the clinic",
              "the library", "the bank", "the lobby", "the loading dock", "the storage unit",
              "the back office", "the front desk", "the corner store", "the car wash",
              "the post office", "the hardware store", "the pharmacy", "the deli",
              "the dry cleaner", "the bus stop", "the side entrance", "the parking garage",
              "the mailroom", "the basement", "the community center", "the daycare",
              "the tire place", "the food hall", "the rec center"),
    "n": ("2", "3", "4", "5", "6", "7", "8", "9", "10", "12"),
    "money": ("$20", "$35", "$40", "$60", "$75", "$80", "$95", "$120", "$150", "$240"),
    "mins": ("5 min", "10 min", "15 min", "20 min", "half an hour", "45 min"),
    "street": ("Atlantic Ave", "Bedford Ave", "Court St", "Flatbush Ave", "Myrtle Ave",
               "Graham Ave", "Lexington", "Amsterdam Ave", "Broadway", "Canal St", "Delancey",
               "Hudson St", "Jamaica Ave", "Knickerbocker", "Bushwick Ave", "Ditmars",
               "Main St", "Metropolitan Ave", "Classon Ave", "Lorimer"),
    "floor": ("2nd floor", "3rd floor", "4th floor", "5th floor", "top floor", "ground floor"),
    "food": ("pizza", "tacos", "dumplings", "pho", "bagels", "wings", "curry", "sushi",
             "burgers", "ramen", "empanadas", "falafel"),
    "color": ("blue", "black", "white", "red", "green", "gray", "silver", "yellow"),
    "vehicle": ("van", "truck", "car", "minivan", "pickup", "hatchback"),
}  # fmt: skip
_SLOT = re.compile(r"\{(\w+)\}")


def fill(rng: random.Random, line: str) -> tuple[str, str]:
    """(message, quotable span) for one pool line; {code} is a four-digit number."""

    def one(m: re.Match[str]) -> str:
        name = m.group(1)
        if name == "code":
            n = rng.randrange(1000, 10000)
            return str(n + 1 if n in (1190, 4471) else n)  # never the guide's own examples
        return rng.choice(SLOTS[name])

    text = _SLOT.sub(one, line)
    m = re.search(r"\[([^\]]+)\]", text)
    core = m.group(1) if m else text
    return text.replace("[", "").replace("]", ""), core


def salt_of(name: str) -> int:
    return zlib.crc32(name.encode("utf-8"))


def spread(k: int, n: int, salt: int) -> tuple[int, int]:
    """(index, lap): the k-th pick from a pool of n. Within a lap every index comes once, in an
    order fixed by salt, so picks k < n never repeat; the lap number tells later picks apart."""
    stride = 7919 + salt % 977
    while math.gcd(stride, n) != 1:
        stride += 1
    return (salt + k * stride) % n, k // n


def combo(k: int, sizes: tuple[int, ...], salt: int) -> tuple[int, ...]:
    """Distinct index tuples for distinct k < prod(sizes), spread over the whole product."""
    total = math.prod(sizes)
    idx, _ = spread(k % total, total, salt)
    out = []
    for size in sizes:
        idx, r = divmod(idx, size)
        out.append(r)
    return tuple(out)


def split_ru(k: int, period: int = 10, slot: int = 3) -> tuple[bool, int]:
    """Whether item k of a family is Russian (one in `period`), and its ordinal in its language."""
    if k % period == slot:
        return True, k // period
    return False, k - k // period - (1 if k % period > slot else 0)


DECOR = {
    "en": (("ok ", ""), ("", " thx"), ("hey ", ""), ("", " pls"), ("so ", ""), ("", " ok?")),
    "ru": (("слушай, ", ""), ("", " спс"), ("короче, ", ""), ("", " ок?"), ("ну ", ""),
           ("", " плиз")),
}  # fmt: skip


def decorate(text: str, lap: int, lang: str) -> str:
    """Lap 0 keeps the line; each later lap adds its own opener or tail."""
    if lap == 0:
        return text
    pre, post = DECOR[lang][(lap - 1) % len(DECOR[lang])]
    return f"{pre}{text}{post}"


FILLER = {
    "en": ("ok", "k", "ok thx", "got it", "sounds good", "omw", "np", "👍", "yep", "cool",
           "will do", "ok one sec", "sure", "lmk", "almost there", "kk", "perfect", "ty",
           "no worries", "bet", "ok cool", "alright", "say less", "ok ill check", "lemme see",
           "nvm found it", "brb", "in the car", "one min", "yes pls", "thx!!", "appreciate it",
           "wait what", "ok ok", "true", "just saw this", "my bad", "send a pic", "which one",
           "got ur msg", "no rush", "for sure", "copy that", "ok noted", "makes sense",
           "on it", "ty ty", "ok good", "fair", "all good"),
    "ru": ("ок", "понял", "поняла", "спасибо", "давай", "ага", "хорошо", "ладно", "норм",
           "уже еду", "окей", "принято", "секунду", "почти на месте", "👍", "ясно", "спс",
           "без проблем", "напиши потом", "ок, жду", "сейчас посмотрю", "уже выхожу",
           "да, видел", "щас гляну", "договорились", "ну ок", "поняла, спасибо"),
}  # fmt: skip

STOP = frozenset(
    "a an the to of in on at by for and or but so if is it its im i u ur me my we you your he "
    "she his her they them their this that be was are am do did not no ok k pls thx with from "
    "up out all just get got can will as there here what when where who how".split()
)


def words(text: str) -> set[str]:
    """The content words of a text, lowercased, for checking that two texts share none."""
    return {w for w in re.findall(r"[^\W_]+", text.lower()) if w not in STOP and len(w) > 1}


def cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яё]", text.lower()))
