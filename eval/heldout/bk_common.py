"""What every family writer in Baker's own wording shares: line pools, context lines, quotes,
the draft a writer returns and the step that turns it into a checked item.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.audit.quotes import verify_quote
from eval.heldout import SOURCE, bk_lines_a, bk_lines_b, bk_lines_c, bk_lines_d
from eval.heldout.bk_lines_ru import CTX_RU, SAY_RU, SMALL_RU
from eval.heldout.bk_scene import Acct, Excerpt, Phone, Scene, chat, sides, split_counts
from eval.heldout.bk_time import Win
from eval.heldout.text import normalized
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import local_str
from eval.stancedata.model import GenItem

# 1.1.0: "at about" is Baker's eight minutes either side and never "noon"; a "this <weekday>"
# rationale names why the week is open. A new version draws every Baker item afresh.
BK_GENERATOR = "eval.heldout.baker 1.1.0"

SAY: dict[str, tuple[str, ...]] = {}
CTX: dict[str, tuple[str, ...]] = {}
for _mod in (bk_lines_a, bk_lines_b, bk_lines_c, bk_lines_d):
    SAY.update(_mod.SAY)
    CTX.update(_mod.CTX)
SMALL_EN = bk_lines_d.SMALL_EN
SITS = tuple(SAY)
RU_SITS = tuple(SAY_RU)


@dataclass
class BkDraft:
    """What a family writer returns; `finish` turns it into a checked GenItem."""

    family: str
    template: str
    params: dict[str, Any]
    ex: Excerpt
    quote: str
    rationale: str
    phone: Phone | None  # the phone the record came from
    lang: str
    scene: Scene
    win: Win | None = None
    facts: dict[str, Any] = field(default_factory=dict)  # what tests re-check
    claim: str | None = None  # the claim's text, for the meaning, role and event templates
    mentions: set[str] = field(default_factory=set)  # person ids whose names the lines use

    @property
    def device(self) -> str:
        if self.phone is None:
            raise ValueError("a draft needs its record's phone")
        return self.phone.dev


def finish(d: BkDraft, probe_id: str, names: dict[str, str]) -> GenItem:
    """The checked item, read by the names the case gives its people (`names`: person id ->
    name); the rationale and claim are already written with those names."""
    return bf.build_baker_item(
        probe_id=probe_id,
        family_id=d.family,
        source=SOURCE,
        generator=BK_GENERATOR,
        lang=d.lang,
        template_id=d.template,
        params=d.params,
        lines=d.ex.lines,
        target=d.ex.target,
        quote=d.quote,
        rationale=d.rationale,
        device=d.device,
        claim=d.claim,
        names=names,
    )


# ------------------------------------------------------------------ context lines


def ctx_pool(sit: str, lang: str) -> tuple[str, ...]:
    if lang == "ru":
        return CTX_RU.get(sit, ()) + SMALL_RU
    if lang == "mixed":
        return CTX.get(sit, ()) + SMALL_EN + SMALL_RU[:6]
    return CTX.get(sit, ()) + SMALL_EN


def ctx_texts(
    rng: random.Random, sit: str, lang: str, n: int, avoid: tuple[str, ...] = ()
) -> list[str]:
    """n different context lines for a chat about sit; none holds any of the `avoid` words."""
    bad = [normalized(a) for a in avoid if a]
    pool = [t for t in ctx_pool(sit, lang) if not any(b and b in normalized(t) for b in bad)]
    if len(pool) < n:
        raise RuntimeError(f"too few context lines for {sit} ({lang})")
    return rng.sample(pool, n)


def chat_excerpt(
    rng: random.Random,
    sc: Scene,
    ph: Phone,
    me: Acct,
    other: Acct,
    utc: datetime,
    text: str,
    mine: bool,
    sit: str,
    lang: str,
    count: tuple[int, int] = (1, 5),
    avoid: tuple[str, ...] = (),
    where: str = "both",
    spread: tuple[int, int] = (20, 1500),
) -> Excerpt:
    """A one-to-one chat around the record, both sides on screen. `where` keeps the context
    lines before or after the record only ("before", "after")."""
    nb, na = split_counts(rng, *count)
    if where == "before":
        nb, na = max(nb + na, 1), 0
    elif where == "after":
        nb, na = 0, max(nb + na, 1)
    nb, na = min(nb, 3), min(na, 3)
    marks = sides(rng, nb, na, mine)
    texts = ctx_texts(rng, sit, lang, nb + na, avoid=(text, *avoid))
    texts.sort(key=lambda t: not t.endswith("?"))  # questions read best before the record
    pairs = list(zip(marks, texts, strict=True))
    return chat(rng, sc, ph, me, other, utc, text, mine, pairs[:nb], pairs[nb:], spread)


# ------------------------------------------------------------------ quotes and wording


def clause(rng: random.Random, text: str, share: float = 0.5) -> str:
    """The quoted words for a record: the whole text, or now and then its longest clause."""
    parts = [p.strip() for p in text.split(",")]
    best = max(parts, key=len)
    if best != text and len(best.split()) >= 3 and rng.random() < share:
        if verify_quote(best, text):
            return best
    return text


def when(line: bf.Line) -> str:
    """The record's time as its line prints it."""
    return line.local_time


def shown_in(utc: datetime, tz: str) -> str:
    return local_str(utc, tz)


def window_words(win: Win) -> str:
    return f'"{win.raw}" ({win.tz})'


def pick(rng: random.Random, *options: str) -> str:
    return rng.choice(options)


def own_apps(rng: random.Random, app: str, extra: tuple[str, ...] = ()) -> tuple[str, ...]:
    """One to three own accounts: the chat's app, any the item needs, and now and then another."""
    apps = [app, *extra]
    for more in ("Phone", "Telegram", "Instagram", "WhatsApp"):
        if len(dict.fromkeys(apps)) < 3 and more not in apps and rng.random() < 0.25:
            apps.append(more)
    return tuple(dict.fromkeys(apps))[:3]
