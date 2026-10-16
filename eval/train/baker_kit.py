"""Shared pieces for the Baker-wording family writers: the scenes most families start from,
record and context texts, and the assembly of one draft into a checked GenItem.

A writer returns a Draft: the scene, the record's phone, the excerpt's events with the record at
`target`, the template parameters, the quote, the rationale and, for the meaning, role and event
templates, the claim. Drafts use Baker's ids; `finish` casts a name for every person the item
involves (baker_cast.py), renders every line from the scene (brackets included) and builds the
item with eval.stancedata.bakerform, which prints the assumption and the lines by name.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

from eval.stancedata import bakerform as bf
from eval.stancedata.model import GenItem
from eval.stancedata.names import bracketed
from eval.train.baker_cast import SURNAMES_RU, cast, fill_claim, pids_in, readable
from eval.train.baker_cues import SURNAMES, VAGUE
from eval.train.baker_scene import (
    MSG_APPS,
    Acc,
    Cast,
    Ev,
    Phone,
    Scene,
    Who,
    items,
    render,
    thread,
)
from eval.train.baker_text import FILLER, cyrillic, decorate, fill, salt_of, split_ru, spread
from eval.train.baker_time import at, pick_day
from eval.train.baker_words_a import HOME
from eval.train.baker_words_b import OUT
from eval.train.baker_words_ru import HOME_RU, VAGUE_RU, agree
from eval.train.names import Person

ORDINARY = {"en": HOME + OUT, "ru": HOME_RU}
VAGUE_BY = {"en": VAGUE, "ru": VAGUE_RU}
QUOTING = ("sender", "record_time", "weekday_date", "meaning")
USED_BEFORE = ("bk_meaning_said", "bk_meaning_other")  # the words' user wrote them earlier too
# What a photo's or a file's own message may say: plain words that bear on nothing. Baker's
# adapter shows that message as its own line just before the attachment's file name.
CAPTIONS = {
    "en": ("here", "this one", "pic", "look", "see this", "here u go", "this", "check it",
           "sending now", "the photo", "📷", "lol look", "one more", "and this"),
    "ru": ("вот", "смотри", "фото", "держи", "вот это", "глянь", "лови", "ещё одно"),
}  # fmt: skip
CAPTIONED = 0.4  # the share of attachment records whose message has a caption


@dataclass
class Draft:
    family: str
    template: str
    params: dict[str, Any]
    scene: Scene
    phone: Phone  # the record's phone
    evs: list[Ev]
    target: int
    quote: str
    rationale: str
    notes: dict[str, Any] = field(default_factory=dict)  # facts the tests re-check
    claim: str = ""  # the claim's text, people as {{person id}} or {{person id|last}}
    names: dict[str, str] = field(default_factory=dict)  # names a writer fixed: id -> name


def names_for(rng: random.Random, d: Draft, lines: list[bf.Line]) -> dict[str, str]:
    """A name for every person the item's params, brackets, claim and rationale mention; a
    chat record's brackets include those of its members (the recipients its lines list)."""
    pids = {*d.params.get("person_ids", ()), *pids_in(d.claim), *pids_in(d.rationale)}
    chat = lines[d.target].kind == "message"
    accounts = {s for ln in lines for s in (ln.sender, *(ln.recipients if chat else ()))}
    pids |= {pid for s in accounts for pid in bracketed(s)}
    shown = " ".join(f"{ln.sender.split(' [')[0]} {ln.text}" for ln in lines).casefold()
    return cast(rng, pids, d.names, d.scene.owners, dict(d.scene.people), shown)


OWN_GENDER = ("bk_author_cue", "bk_handles_said")  # records already in the speaker's gender


def agree_all(d: Draft) -> None:
    """Russian lines from people the item names, in each one's own gender; a record changed
    takes its quote, quoted words, rationale and claim along."""
    for i, e in enumerate(d.evs):
        person = d.scene.speaker(e.frm)
        if person is None or person.lang != "ru" or (i == d.target and d.family in OWN_GENDER):
            continue
        text = agree(e.text, person.end)
        if text == e.text:
            continue
        d.evs[i] = replace(e, text=text)
        if i == d.target:
            d.quote, d.rationale = agree(d.quote, person.end), agree(d.rationale, person.end)
            d.claim = agree(d.claim, person.end)
            if "quoted_text" in d.params:
                d.params["quoted_text"] = agree(d.params["quoted_text"], person.end)


def finish(d: Draft, probe_id: str, generator: str, rng: random.Random) -> GenItem:
    agree_all(d)
    lines = [render(d.scene, d.phone, e) for e in d.evs]
    quoted = d.params.get("quoted_text")
    earlier = d.family in USED_BEFORE or d.notes.get("used_before")  # bk_claim_open's own meaning
    if quoted and d.template in QUOTING and not earlier:
        for i, ln in enumerate(lines):
            if i != d.target and quoted.casefold() in ln.text.casefold():
                raise ValueError(f"{probe_id}: the quoted words also stand on a context line")
    names = names_for(rng, d, lines)
    return bf.build_baker_item(
        probe_id=probe_id, family_id=d.family, source="train_gen", generator=generator,
        lang=lang_of(lines, d.target), template_id=d.template, params=d.params, lines=lines,
        target=d.target, quote=d.quote, rationale=readable(d.rationale, names),
        device=d.phone.dev, claim=fill_claim(d.claim, names) or None, names=names,
        captioned=captioned(d.evs, d.target),
    )  # fmt: skip


def captioned(evs: list[Ev], target: int) -> bool:
    """Whether the record is an attachment shown after its message's caption (chat())."""
    rec, cap = evs[target], evs[target - 1] if target else None
    return rec.kind == "att" and cap is not None and cap.kind == "msg" and (
        (cap.utc, cap.frm, cap.to) == (rec.utc, rec.frm, rec.to)
    )  # fmt: skip


MACHINE = re.compile(
    r"^(?:(?:incoming|outgoing|missed) call from |(?:IMG|VID|PXL|Screenshot)_[\w-]+\.\w+$)"
)


def lang_of(lines: list[bf.Line], target: int) -> str:
    """'ru' when every worded line is Russian, 'mixed' when Russian and English lines meet.
    Call texts and file names are the report's, in no chat language."""
    worded = [ln.text for ln in lines
              if any(ch.isalpha() for ch in ln.text) and not MACHINE.match(ln.text)]  # fmt: skip
    ru = [cyrillic(t) for t in worded]
    if all(ru) and ru:
        return "ru"
    return "mixed" if any(ru) else "en"


# ---------------------------------------------------------------- texts


def record_text(rng: random.Random, k: int, family: str, vague: bool = False) -> tuple[str, str]:
    """(text, quotable span) of the k-th ordinary record of a family; one in ten is Russian.
    No two of a family's records share a pool line and lap, so none repeats."""
    ru, ordinal = split_ru(k)
    lang = "ru" if ru else "en"
    pool = (VAGUE_BY if vague else ORDINARY)[lang]
    idx, lap = spread(ordinal, len(pool), salt_of(f"{family}|{lang}|{vague}"))
    text, core = fill(rng, pool[idx])
    return decorate(text, lap, lang), core


def quoted_words(rng: random.Random, text: str, core: str) -> str:
    """What an assumption quotes from a record: its marked span, or the whole message."""
    return text if rng.random() < 0.45 else core


def chatter(rng: random.Random, lang: str, n: int, avoid: str = "") -> list[str]:
    """n context lines: mostly short fillers, sometimes an everyday line; none holds `avoid`."""
    out: list[str] = []
    while len(out) < n:
        if lang == "ru" and rng.random() < 0.06:
            line = rng.choice(FILLER["en"][:12])  # people switch to "ok" or "omw" mid-chat
        elif rng.random() < 0.3:
            line = fill(rng, rng.choice(ORDINARY[lang]))[0]
        else:
            line = rng.choice(FILLER[lang])
        if avoid and avoid.casefold() in line.casefold():
            continue
        out.append(line)
    return out


def lang_of_text(text: str) -> str:
    return "ru" if cyrillic(text) else "en"


# ---------------------------------------------------------------- people


def slug(rng: random.Random) -> str:
    """A named person the document names: an invented surname, sometimes a numbered stand-in."""
    if rng.random() < 0.08:
        return bf.named_person(f"doe_{rng.randrange(10, 9999):04d}")
    return bf.named_person(rng.choice(SURNAMES))


def named_slug(rng: random.Random, p: Person) -> str:
    """The person:<surname> for a chat person an item names in full: a surname that suits them
    (a Russian speaker's in its Latin form, in their gender)."""
    if p.lang == "ru":
        return bf.named_person(rng.choice(SURNAMES_RU)[p.pron == "she"].lower())
    return bf.named_person(rng.choice(SURNAMES))


def surname_of(pid: str) -> str:
    return pid.split(":", 1)[1]


@dataclass
class Setup:
    """A one-to-one chat on `phone` between its owner and `partner`, on `app`."""

    scene: Scene
    phone: Phone
    partner: Who
    app: str
    you_pid: str | None  # the partner's bracketed person id, if any
    other: Phone | None = None  # a second phone in the scene

    @property
    def me(self) -> Acc:
        return self.phone.owner.acc(self.app)

    @property
    def you(self) -> Acc:
        return self.partner.acc(self.app)

    @property
    def me_phone(self) -> Acc:
        return self.phone.owner.acc("Phone")

    @property
    def you_phone(self) -> Acc:
        return self.partner.acc("Phone")


def setup(
    rng: random.Random,
    kind: str,
    app: str | None = None,
    lang: str = "en",
    taken: tuple[str, ...] = (),
) -> Setup:
    """kind 'third': the partner is a third party with no brackets; 'linked': a third party an
    expert linked to a named person; 'phones': the owner of a second phone in the scene. No one
    in the scene has a first name in `taken`."""
    cast = Cast(rng)
    cast.taken |= set(taken)
    app = app or rng.choice(MSG_APPS)
    nums = items(rng, 2)
    phone = cast.phone(nums[0], (app, "Phone"), lang)
    if kind == "phones":
        other = cast.phone(nums[1], (app, "Phone"), lang)
        return Setup(Scene((phone, other)), phone, other.owner, app, other.person, other)
    partner = cast.who(lang, named=kind == "linked")
    if kind == "linked":  # a Russian speaker's surname in its Latin form, in their gender
        pid = named_slug(rng, partner.person) if lang == "ru" else slug(rng)
        links = tuple((partner.acc(a), pid) for a in dict.fromkeys((app, "Phone", "SMS")))
        return Setup(Scene((phone,), links, ((pid, partner.person),)), phone, partner, app, pid)
    return Setup(Scene((phone,)), phone, partner, app, None)


def with_other_phone(rng: random.Random, s: Setup, lang: str = "en") -> Setup:
    """The same chat in a scene with a second phone whose owner takes no part in it."""
    if s.other is not None:
        return s
    cast = Cast(rng)
    for who in (s.phone.owner, s.partner):
        cast.taken |= {who.person.name, who.number, who.tg, who.ig}
    taken = {p.item for p in s.scene.phones}
    other = cast.phone(rng.choice([n for n in range(1, 10) if n not in taken]), ("SMS",), lang)
    scene = Scene((*s.scene.phones, other), s.scene.links, s.scene.people)
    return Setup(scene, s.phone, s.partner, s.app, s.you_pid, other)


def pick_kind(rng: random.Random, weights: tuple[int, int, int] = (5, 2, 3)) -> str:
    return rng.choices(("third", "linked", "phones"), weights=weights)[0]


def chat(
    rng: random.Random,
    s: Setup,
    text: str,
    utc: datetime,
    from_me: bool,
    lang: str,
    spread_s: int = 900,
    n_before: int | None = None,
    n_after: int | None = None,
    avoid: str = "",
    kind: str = "msg",
    lead: str = "",
) -> tuple[list[Ev], int]:
    """The record (from the owner's side or the partner's) in its own chat; `lead`, if given,
    is a line from the other end just before the record. An attachment's message may carry a
    caption, its own line just before the attachment, at the same time."""
    frm, to = (s.me, s.you) if from_me else (s.you, s.me)
    nb = rng.randint(1, 3) if n_before is None else n_before
    na = rng.randint(0, 3) if n_after is None else n_after
    rec = Ev(utc, frm, text, kind, to=to)
    evs, target = thread(rng, rec, chatter(rng, lang, nb, avoid), chatter(rng, lang, na, avoid),
                         spread_s)  # fmt: skip
    if lead:
        evs.insert(target, Ev(utc - timedelta(seconds=rng.randint(5, 20)), to, lead, to=frm))
        target += 1
        while target > 3:  # at most three lines before the record
            evs.pop(0)
            target -= 1
    if kind == "att" and rng.random() < CAPTIONED:  # three lines before the caption, at most
        while True:
            cap = rng.choice(CAPTIONS[lang]) if rng.random() < 0.7 else chatter(rng, lang, 1)[0]
            if not avoid or avoid.casefold() not in cap.casefold():
                break
        evs.insert(target, Ev(utc, frm, cap, to=to))
        target += 1
    return evs, target


def any_time(rng: random.Random, zone: str) -> datetime:
    """A record time on a random day, between 7 a.m. and 11 p.m. on the phone's clock."""
    return at(pick_day(rng), rng.randint(7, 22), rng.randrange(60), rng.randrange(60), zone)
