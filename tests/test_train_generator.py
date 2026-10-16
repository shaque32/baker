"""The training generator: deterministic, valid items, every family, siblings, names, no leaks,
and the template rules of the labeling guide (fact-form assumptions, no gender, no open
references, supports assumptions that add nothing, spread-out templates)."""

from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from core.audit.assumption_filler import check_window
from eval.stancedata import bakerform as bf
from eval.stancedata.chat import Account
from eval.stancedata.families import FAMILIES
from eval.stancedata.model import GenItem
from eval.train import baker
from eval.train import generate as gen
from eval.train.baker_cast import FIRSTS_EN, FORMAL_RU, SURNAMES_RU, pids_in
from eval.train.baker_claim_ru import EXPLAIN_RU, OPENERS_RU, OWN_RU, TAILS_RU
from eval.train.baker_claim_words import EXPLAIN, OPENERS, OWN, TAILS
from eval.train.baker_cues import SURNAMES
from eval.train.baker_fam_denied import DENY_OPENERS, DENY_TAILS, QUESTIONS
from eval.train.baker_fam_sender import NICKS, NICKS_RU
from eval.train.baker_place import EDGE_FORMS, _edge_window
from eval.train.baker_scene import render
from eval.train.baker_text import words
from eval.train.glossary import PAIRS, SLANG
from eval.train.names import (
    AREA_CODES,
    PEOPLE_EN,
    PEOPLE_RU,
    Party,
    Person,
    cast,
    outside_account,
)
from eval.train.verbs import SUPPORT_VERBS_EN, SUPPORT_VERBS_RU
from eval.train.when import clear_part, far_parts

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "eval" / "train"
FIRST_LETTERS = set("ABCDEFGHIJKLM") | set("АБВГДЕЁЖЗИЙКЛ")


@pytest.fixture(scope="module")
def items() -> list[GenItem]:
    return gen.generate(600, 1)


@pytest.fixture(scope="module")
def many() -> list[GenItem]:
    return gen.generate(4000, 1)


@pytest.fixture(scope="module")
def combined() -> list[GenItem]:
    """The plain items of `items`, then one full cycle of Baker-wording items."""
    return gen.generate(600, 1, n_baker=len(baker.CYCLE))


def _dump(rows: list[GenItem]) -> list[str]:
    return [it.model_dump_json() for it in rows]


def test_deterministic_per_seed() -> None:
    a, b = gen.generate(80, 7), gen.generate(80, 7)
    assert _dump(a) == _dump(b)
    assert _dump(gen.generate(80, 8)) != _dump(a)
    # A shorter run is a prefix of a longer one: item i depends on the seed and its index only.
    assert _dump(gen.generate(30, 7)) == _dump(a)[:30]


def test_items_validate_with_ids_in_order(items: list[GenItem]) -> None:
    for n, it in enumerate(items, 1):
        assert isinstance(it, GenItem)
        GenItem.model_validate(it.model_dump(mode="json"))
        assert it.probe_id == f"T{n:06d}"
        assert it.source == "train_gen" and it.generator == gen.GENERATOR
        assert it.labeled_by.startswith("DRAFT")


def test_every_family_appears(combined: list[GenItem]) -> None:
    seen = {it.family for it in combined}
    assert seen == {f.family_id for f in FAMILIES}


def test_siblings_share_the_record_and_differ_in_assumption(items: list[GenItem]) -> None:
    groups: dict[str, list[GenItem]] = {}
    for it in items:
        groups.setdefault(it.group, []).append(it)
    multi = [g for g in groups.values() if len(g) > 1]
    assert len(multi) >= 60
    for g in multi:
        ids = [int(it.probe_id[1:]) for it in g]
        assert ids == list(range(ids[0], ids[0] + len(ids)))
        assert len({it.target.text for it in g}) == 1
        assert len({it.target.local_time for it in g}) == 1
        assert len({it.assumption for it in g}) == len(g)
        assert len({it.family for it in g}) == len(g)
    # A run cut at n can leave its final group with one member; it keeps the Tg id so that a
    # shorter run stays a prefix of a longer one. Every other lone item uses its own id.
    for it in items:
        if len(groups[it.group]) == 1:
            assert it.group == it.probe_id or it.group == items[-1].group


def test_quotes_are_verbatim_and_word_aligned(items: list[GenItem]) -> None:
    for it in items:
        q, text = it.proposed_quote, it.target.text
        assert q and q.strip() == q and q in text
        start = text.index(q)
        end = start + len(q)
        assert start == 0 or not (text[start - 1].isalnum() and q[0].isalnum())
        assert end == len(text) or not (text[end].isalnum() and q[-1].isalnum())
        if it.gold_stance == "irrelevant":
            assert q == text


def test_name_rule_area_codes_and_telegram_ids(items: list[GenItem]) -> None:
    for it in items:
        for line in it.lines():
            app, ident, *label = line.sender.split(" ")
            if app == "Instagram":
                assert ident[0].upper() in FIRST_LETTERS, line.sender
            if ident.startswith("+1"):
                assert ident[2:5] in AREA_CODES, line.sender
            if app == "Telegram":
                assert re.fullmatch(r"[34]\d{6}", ident), line.sender
            text = " ".join(label)
            if text and text != "(owner)":
                assert text.lstrip("@")[0].upper() in FIRST_LETTERS, line.sender


def test_mix_and_context_shape(items: list[GenItem]) -> None:
    stances = {s: sum(it.gold_stance == s for it in items) / len(items)
               for s in ("supports", "contradicts", "complicates", "irrelevant")}  # fmt: skip
    assert 0.2 < stances["supports"] < 0.4
    assert 0.15 < stances["contradicts"] < 0.35
    assert 0.25 < stances["complicates"] < 0.45
    assert 0.04 < stances["irrelevant"] < 0.18
    assert 0.1 < sum(it.lang in ("ru", "mixed") for it in items) / len(items) < 0.35
    for it in items:
        assert 1 <= len(it.context) <= 6
        assert 0 <= it.target_index <= len(it.context)


def test_package_source_never_touches_test_data() -> None:
    forbidden = ("case01", "case02", "gold", "heldout", "synthetic", "eval.heldout")
    for path in sorted(PACKAGE.glob("*.py")):
        text = path.read_text(encoding="utf-8").lower()
        for word in forbidden:
            assert word not in text, f"{path.name} mentions {word!r}"
        # GenItem's id field is named probe_id; nothing else about probes may appear.
        assert "probe" not in text.replace("probe_id", ""), f"{path.name} mentions a probe"
        assert "import" not in text or "eval.heldout" not in text


def test_cli_writes_file_and_manifest(tmp_path: Path) -> None:
    out = tmp_path / "train.jsonl"
    assert gen.main(["--n", "25", "--n-baker", "0", "--seed", "3", "--out", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 25
    side = out.with_name("train.jsonl.manifest.json")
    assert side.exists() and '"n": 25' in side.read_text(encoding="utf-8")


def test_every_excerpt_shows_a_non_owner_line(items: list[GenItem]) -> None:
    # Guide rule 11: the probe format has no recipient field, so a non-owner line is on screen.
    for it in items:
        assert any("(owner)" not in ln.sender for ln in it.lines()), it.probe_id


def test_supports_assumptions_report_the_message(items: list[GenItem]) -> None:
    # Guide rule 14: a supports assumption says what the message communicates, in the verbs
    # the message-level traps share (eval/train/frames.py).
    says = re.compile(r"\b(told|wrote|texted|sent|says|said|states|message|messaged|messages|"
                      r"in contact|replied|answer|asked|posted|mentioned|let .+ know|in touch|"
                      r"communicated|had contact|contact between|text)\b", re.I)  # fmt: skip
    for it in items:
        if it.gold_stance == "supports":
            assert says.search(it.assumption), it.assumption


def test_fact_families_state_the_fact(items: list[GenItem]) -> None:
    # Guide rule 12: a correction, a denial or another value contradicts a fact, not a report.
    report = re.compile(r"\b(told|wrote|texted|said|says|states)\b|message (says|states)|"
                        r"sent (the owner|.*message)")  # fmt: skip
    fams = {"ovr_later_correction", "con_other_value", "con_other_state", "con_denial",
            "con_correction", "ovr_negation"}  # fmt: skip
    for it in items:
        if it.family in fams:
            assert not report.search(it.assumption), it.assumption


def test_count_records_show_one_instance(items: list[GenItem]) -> None:
    # Guide rule 16: never a competing quantifier that could read as contradicts.
    quant = re.compile(r"\b(usually|most|basically|sometimes|почти|обычно|иногда)\b|"
                       r"times a week|\d or \d")  # fmt: skip
    for it in items:
        if it.family == "ovr_count":
            assert not quant.search(it.target.text.lower()), it.target.text


def test_handle_owner_names_fit_the_account(items: list[GenItem]) -> None:
    # The assumed person's first name never names a third party in the record, and the shown
    # label or handle never carries a different person's name.
    from eval.train.names import PEOPLE_EN, PEOPLE_RU

    pool = {p.name.lower() for p in PEOPLE_EN + PEOPLE_RU}
    for it in items:
        if it.family != "ovr_handle_owner":
            continue
        # The named person follows any leading date phrase ("Before May 25, 2025, Dina ...").
        lead = re.match(rf"(?:(?:Before|By|Prior to) (?:{CLOCK} on )?{WDAY}{LONG_DATE.pattern}, )?",
                        it.assumption)  # fmt: skip
        first = it.assumption[lead.end() if lead else 0 :].split()[0].rstrip(",").lower()
        assert not re.search(rf"\b{first}\b", it.target.text.lower()), it.assumption
        app, ident, *label = it.target.sender.split(" ")
        shown = [" ".join(label).lstrip("@").lower()] if label else []
        if app == "Instagram":
            shown.append(ident.lower())
        for s in shown:
            names = {n for n in pool if re.search(rf"(^|[^a-zа-яё]){n}([^a-zа-яё]|$)", s)}
            assert names <= {first}, (it.assumption, it.target.sender)


# --- assumption wording -------------------------------------------------------------------

QUOTED = re.compile(r'"[^"]*"')
PERSON = set("i i'm im i'll ill my me mine we our us u ur you your yours я мне меня мой моя моё "
             "мои мы нам нас наш ты тебе тебя твой вы вам вас ваш".split())  # fmt: skip
GENDER = set("he she his him her hers он она его её ему ей".split())
OPEN_REFERENCE = re.compile(
    r"\b(it|him|her|them)\b|\bthe (man|woman)\b|\b(last night|the night before|yesterday|tonight|"
    r"tomorrow|tmrw|this weekend|this morning|the next day|that week|that month|that year|"
    r"вчера|сегодня|завтра)\b"
)
REPORT_OK = {f.family_id for f in FAMILIES if f.stance.value == "supports"} | {
    "ovr_sender_mismatch", "ovr_time_mismatch", "con_in_window", "ovr_speaker_mismatch",
}  # fmt: skip
REPORT = re.compile(
    r"\b(said|says|stated|states|wrote|texted|messaged|сказал|сказала|написал|написала|говорит|"
    r"пишет)\b|\btold\b[^.;]*?\bthat\b|\btold\b(?![^.;]*?\bto\b)|\b(the|a|that|in a) message\b|"
    r"\bmessage from\b"
)
CURRENCY = re.compile(r"\$|\b(dollars?|bucks|rubles?)\b|\bруб|₽")


def _bare(a: str) -> str:
    """The assumption, lowercased, without its quoted record spans."""
    return QUOTED.sub(" ", a).lower()


def _tokens(s: str) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", s.lower())


def test_assumptions_never_speak_in_first_or_second_person(items: list[GenItem]) -> None:
    for it in items:
        assert not set(_tokens(_bare(it.assumption))) & PERSON, it.assumption


def test_assumptions_never_gender_anyone(items: list[GenItem]) -> None:
    # The owner is "the owner", an account is its label or handle, a pronoun is "they".
    for it in items:
        assert not set(_tokens(_bare(it.assumption))) & GENDER, it.assumption


def test_assumptions_resolve_references_and_dates(items: list[GenItem]) -> None:
    # No object placeholder, no "the man", no relative time: a record's "last night" becomes a
    # local date in the assumption. No "had had" from a bound on an act that starts with "had".
    for it in items:
        assert not OPEN_REFERENCE.search(_bare(it.assumption)), it.assumption
        assert "had had" not in it.assumption, it.assumption


def test_report_frames_only_in_message_families(items: list[GenItem]) -> None:
    # Guide rule 12: trap, contradict and irrelevant families state the fact; "told ... that",
    # "said ...", "the message says" belong to supports families and the message-level
    # exceptions only.
    for it in items:
        if it.family not in REPORT_OK:
            assert not REPORT.search(_bare(it.assumption)), (it.family, it.assumption)


def test_currency_gloss_needs_a_marker(items: list[GenItem]) -> None:
    for it in items:
        if CURRENCY.search(_bare(it.assumption)):
            texts = " ".join(ln.text for ln in it.lines()).lower()
            assert CURRENCY.search(texts), (it.assumption, it.target.text)


def test_no_doubled_parties_or_pronouns(items: list[GenItem]) -> None:
    doubled = re.compile(r"\b(u|you) (paid|pay|owe|owed|lent|lend|sent|send|gave|give) (u|you)\b")
    for it in items:
        a = it.assumption.lower()
        assert "the owner and the owner" not in a, a
        m = re.search(r"the owner and (.+?) (exchanged|were in contact)", a)
        assert m is None or m.group(1) != "the owner", a
        for ln in it.lines():
            assert not doubled.search(ln.text.lower()), ln.text


def test_irrelevant_assumptions_are_plain_facts(items: list[GenItem]) -> None:
    # Never a contact pattern or an identity link, which the excerpt itself bears on.
    bad = re.compile(r"\bin contact\b|no contact|exchanged|messag|belongs to|texted|called|wrote")
    for it in items:
        if it.family.startswith("irr_"):
            assert not bad.search(_bare(it.assumption)), it.assumption


# --- record wording -----------------------------------------------------------------------

TAIL = r"(lol|haha|ugh|tbh|fr|👍|\.\.\.|лол|ахах|\)+)"
BAD_TAIL = re.compile(rf"\?\s*{TAIL}\s*$|\. done\b|\. ok\b|\bso yeah\b|, finally\b|"
                      r"\. (done|lol|btw|thx|ok|finally|haha|fyi|лол|всё|ок|кароч)\b")  # fmt: skip
QUALIFIER = re.compile(r"\b(total|including|incl|about|around|roughly|at least|at most|plus|"
                       r"примерно|около|минимум|всего)\b|tip included")  # fmt: skip
REVEAL = re.compile(r"\d|\$|\b(bucks|dollars?|cash|venmo|paid|pay|money|for real|nah|jk|actually|"
                    r"бабки|налом|деньги)\b|\bруб|на самом деле")  # fmt: skip
SUP_RECORD_FAMILIES = {"sup_plain", "sup_time_window", "sup_contact", "sup_account_shared",
                       "sup_injection"}  # fmt: skip


def test_decorations_are_single_and_never_after_a_question(items: list[GenItem]) -> None:
    for it in items:
        for ln in it.lines():
            assert not BAD_TAIL.search(ln.text.lower()), ln.text


def test_other_value_records_state_the_value_plainly(items: list[GenItem]) -> None:
    for it in items:
        if it.family == "con_other_value":
            assert not QUALIFIER.search(it.target.text.lower()), it.target.text


def test_joke_records_keep_the_joke_to_themselves(items: list[GenItem]) -> None:
    # The joke marker sits in the record; no later line from the same sender gives the real value.
    for it in items:
        if it.family == "ovr_joke":
            later = [ln for ln in it.lines()[it.target_index + 1:]
                     if ln.sender == it.target.sender]  # fmt: skip
            for ln in later:
                assert not REVEAL.search(ln.text.lower()), (it.target.text, ln.text)


def test_supports_records_carry_a_verb(items: list[GenItem]) -> None:
    for it in items:
        if it.family in SUP_RECORD_FAMILIES:
            toks = re.findall(r"[^\W\d_]+", it.target.text.lower())
            assert any(t in SUPPORT_VERBS_EN or t.startswith(SUPPORT_VERBS_RU) for t in toks), (
                it.family,
                it.target.text,
            )


def test_dates_fall_in_the_window(items: list[GenItem]) -> None:
    for it in items:
        for ln in it.lines():
            d = date.fromisoformat(ln.local_time[:10])
            assert date(2024, 1, 1) <= d <= date(2026, 9, 30), ln.local_time


RECORD_FRAME = set(
    "i u the a an to of on for at in my me ur did didnt not never nope yeah yes just gonna will "
    "ill ima planning this that tmrw later tonight weekend first thing when get there after work "
    "pretty sure think like so wait ok k btw yo hey lol haha ugh fr tbh remember right probably "
    "cant believe certain says said heard from told swears according да нет я ты не так и уже "
    "вроде "
    "кажется помню по-моему уверен уверена говорит сказал сказала написал написала что завтра на "
    "неделе после работы обещаю если точно ровно ни больше меньше только всё ну кароч короче "
    "слушай блин а лол ахах".split()
)


def test_record_templates_are_spread_out(many: list[GenItem]) -> None:
    # No content 5-gram of the record texts (frame words out, numbers folded) backs more than 1%
    # of the items, so no single fact template dominates.
    counts: Counter[tuple[str, ...]] = Counter()
    for it in many:
        toks = [
            "#" if re.search(r"\d", t) else t
            for t in re.findall(r"[\w#$]+", it.target.text.lower())
            if t not in RECORD_FRAME
        ]
        counts.update({tuple(toks[i:i + 5]) for i in range(len(toks) - 4)})  # fmt: skip
    gram, n = counts.most_common(1)[0]
    assert n <= len(many) * 0.01, (gram, n)


# --- supports assumptions add nothing the record lacks ------------------------------------

FRAME = set(
    "told owner that they their would asked whether thought without being sure said says wrote "
    "texted messaged message messages sent came from exchanged were contact between through "
    "before after morning afternoon evening night states group chat answer question confirmed "
    "according telegram user shown instagram account saved personally typed usual someone else "
    "noon midnight into than with january february march april may june july august september "
    "october november december "
    # The report and contact frames (eval/train/frames.py) and time phrases (eval/train/when.py).
    "mentioned know text saying posted answering reply replied words each other touch "
    "communicated "
    "traded passed been there later earlier sometime about around approximately during late prior "
    "monday tuesday wednesday thursday friday saturday sunday".split()
)
IRREGULAR = {"paid": "pay", "sold": "sell", "sent": "send", "lent": "lend", "bought": "buy",
             "brought": "bring", "made": "make", "took": "take", "came": "come", "won": "win",
             "lost": "lose", "went": "go", "gave": "give", "left": "leave", "drove": "drive",
             "flew": "fly", "spent": "spend", "kept": "keep", "ran": "run", "swam": "swim",
             "got": "get", "had": "have", "did": "do", "told": "tell", "showed": "show",
             "could": "can", "were": "be", "was": "be", "owed": "owe"}  # fmt: skip


def _stem(w: str) -> str:
    """A rough stem: irregular past to base, common suffixes off, first five letters."""
    w = IRREGULAR.get(w, w)
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if len(w) >= 4 and w.endswith("e"):
        w = w[:-1]
    if len(w) >= 4 and w[-1] == w[-2]:
        w = w[:-1]
    return w[:5]


def _ru_hit(key: str, text: str, tokens: list[str]) -> bool:
    if " " in key:
        return key in text
    return any(t.startswith(key[:5] if len(key) >= 5 else key) for t in tokens)


def _allowed_stems(it: GenItem) -> set[str]:
    text = " ".join(ln.text for ln in it.lines()).lower()
    tokens = re.findall(r"[^\W\d_]+", text)
    words = set(tokens) | set(re.findall(r"[^\W\d_]+", " ".join(ln.sender for ln in it.lines())))
    for ru, en in PAIRS:
        if _ru_hit(ru, text, tokens):
            words |= set(en.lower().split())
    return {_stem(w.lower()) for w in words} | {_stem(w) for w in FRAME}


def test_supports_assumptions_add_nothing(items: list[GenItem]) -> None:
    # Every content word of a supports assumption appears in the record or the context (first
    # five letters, inflection allowed), or is a listed translation of a Russian word there.
    for it in items:
        if it.gold_stance != "supports":
            continue
        allowed = _allowed_stems(it)
        for w in re.findall(r"[^\W\d_]+", _bare(it.assumption)):
            if len(w) >= 4 and w not in FRAME:
                assert _stem(w) in allowed, (w, it.assumption, [ln.text for ln in it.lines()])


def test_slang_pairs_never_back_a_supports_item(items: list[GenItem]) -> None:
    for it in items:
        if it.gold_stance == "supports":
            text = " ".join(ln.text for ln in it.lines()).lower()
            tokens = re.findall(r"[^\W\d_]+", text)
            for ru, _ in SLANG:
                assert not _ru_hit(ru, text, tokens), (ru, it.target.text)


# --- round 3: wording leftovers an expert would notice ------------------------------------

PARTY = re.compile(
    r"the owner|the contact saved as \S+|Telegram user \d+|"
    r"the (?:Instagram|Telegram|Signal|WhatsApp) account \S+|\+1 \d{3}-\d{3}-\d{4}"
)
NOUN_STOP = set(
    "the a an and or to of for in on at with as that by from up out into than if so but was "
    "were is are be had has have did do not no they their them it its this who whether would "
    "said told says wrote texted asked before after until when while about back more less off "
    "such на в и не за с к у по из от до о а но что это как ещё уже".split()
)
RU_NUMERAL = {"один": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5,
              "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10}  # fmt: skip
RU_COUNTED = re.compile(
    r"\b(\d+|одна|один|два|две|три|четыре|пять|шесть|семь|восемь|девять|десять) "
    r"(коробк\w*|конфет\w*|витамин\w*|тренировок|занятий|часов|человек|минут\w*)\b"
)
RU_FORMS = {"коробк": ("коробка", "коробки", "коробок"), "конфет": ("конфета", "конфеты", "конфет"),
            "витамин": ("витаминка", "витаминки", "витаминок"),
            "минут": ("минута", "минуты", "минут")}  # fmt: skip
SEASONAL = {"merry christmas": {12}, "happy new year": {12, 1}, "happy thanksgiving": {11},
            "с новым годом": {12, 1}, "с рождеством": {12, 1}}  # fmt: skip
WEEKDAY = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|"
                     r"понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье")  # fmt: skip
RELATIVE_DAY = re.compile(r"\b(this weekend|tmrw|tomorrow|tonight)\b|\bзавтра\b|\bна неделе\b")
WORD_TAIL = re.compile(r"\s*(lol|haha|ugh|tbh|fr|👍|лол|ахах|\.\.\.)$")


def _count_class(num: str) -> int:
    """0: the singular, 1: the form after 2 to 4, 2: the genitive plural (5 and up, 11 to 14)."""
    n = RU_NUMERAL.get(num) or int(num)
    if n % 100 in range(11, 15) or n % 10 == 0 or n % 10 >= 5:
        return 2
    return 0 if n % 10 == 1 else 1


def test_no_read_plainly_prefix(items: list[GenItem]) -> None:
    for it in items:
        assert "read plainly" not in it.assumption.lower(), it.assumption


def test_party_named_once_per_assumption(items: list[GenItem]) -> None:
    # "X paid 45, as X wrote in the group": the second mention of a party is "they".
    for it in items:
        counts = Counter(PARTY.findall(it.assumption))
        assert all(n == 1 for n in counts.values()), (counts, it.assumption)


def test_no_repeated_noun_phrase_in_assumption(items: list[GenItem]) -> None:
    # "bought the Honda ... and paid cash for the honda": no two-word phrase appears twice.
    for it in items:
        toks = _tokens(re.sub(r"\b[ap]\.m\.", " ", _bare(it.assumption)))
        pairs = Counter(
            (x, y)
            for x, y in zip(toks, toks[1:], strict=False)
            if x not in NOUN_STOP and y not in NOUN_STOP
        )
        assert all(n == 1 for n in pairs.values()), (pairs, it.assumption)


def test_russian_numerals_agree_with_nouns(items: list[GenItem]) -> None:
    # 2 to 4 take "коробки", 5 and up (and 11 to 14) take "коробок".
    for it in items:
        for ln in it.lines():
            for num, noun in RU_COUNTED.findall(ln.text.lower()):
                cls = _count_class(num)
                stem = next((s for s in RU_FORMS if noun.startswith(s)), None)
                if stem:
                    assert noun == RU_FORMS[stem][cls], (num, noun, ln.text)
                else:  # nouns the pools only use in the genitive plural
                    assert cls == 2, (num, noun, ln.text)


def test_seasonal_greetings_match_the_month(items: list[GenItem]) -> None:
    for it in items:
        for ln in it.lines():
            month = int(ln.local_time[5:7])
            for greeting, months in SEASONAL.items():
                assert greeting not in ln.text.lower() or month in months, (ln.text, ln.local_time)


def test_no_fyi_in_any_line(items: list[GenItem]) -> None:
    for it in items:
        for ln in it.lines():
            assert not re.search(r"\bfyi\b", ln.text.lower()), ln.text


def test_weekday_never_pairs_with_a_relative_day(items: list[GenItem]) -> None:
    # "on friday this weekend": a record that names its day takes no second time word.
    for it in items:
        t = it.target.text.lower()
        assert not (WEEKDAY.search(t) and RELATIVE_DAY.search(t)), it.target.text


def test_tails_never_follow_short_replies(items: list[GenItem]) -> None:
    # "no tbh", "nothing else fr": a tail never follows a clause of fewer than three words.
    for it in items:
        for ln in it.lines():
            m = WORD_TAIL.search(ln.text)
            if m and m.start() > 0:  # a bare "lol" or "fr" is the whole reply, not a tail
                last = re.split(r"[,;:]", ln.text[: m.start()])[-1]
                assert len(re.findall(r"[^\W\d_]+", last)) >= 3, ln.text


# --- guide v0.3: strict contradicts, rationales that claim only what is shown -------------

WEEKDAY_NAMES = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                 r"понедельник\w*", r"вторник\w*", r"сред[аеуы]", r"четверг\w*", r"пятниц[аеуы]",
                 r"суббот[аеуы]", r"воскресень[еюя]")  # fmt: skip
WEEKDAY_NAME = re.compile("|".join(rf"\b({d})\b" for d in WEEKDAY_NAMES))
# A quoted phrase: "..." or '...'; an apostrophe inside a word ("owner's") opens no quote.
QUOTED_PHRASE = re.compile(r"\"[^\"]*\"|(?<!\w)'(?:[^']|(?<=\w)'(?=\w))*'(?!\w)")
DECLARES = re.compile(r"at the same time|\bjok(e|es|ing)\b|\bvent(s|ing)?\b|\bharmless\b|"
                      r"\bsarcas|\bliterally\b|\bobvious")  # fmt: skip
LAUGH_MARK = re.compile(r"\b(lol|haha\w*|lmao\w*|лол|ахах\w*)\b|😂|🤣|\)")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")  # fmt: skip
LONG_DATE = re.compile(rf"\b({'|'.join(MONTHS)}) (\d{{1,2}}), (\d{{4}})")
CLOCK = r"(noon|midnight|\d{1,2}(?::\d{2})? [ap]\.m\.)"
# A date's own weekday may go before it ("Friday, May 2, 2025", eval/train/when.py say_day).
WDAY = r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), )?"
# A clock on a date ("by 2 p.m. on March 3, 2026", "at 9:12 a.m. on March 3, 2026"), and a
# bound that is a date alone ("before March 3, 2026": the days before it).
CLOCK_ON = re.compile(rf"\b(?:by|before|at) {CLOCK} on {WDAY}{LONG_DATE.pattern}", re.I)
CLOCK_BOUND = re.compile(rf"\b(?:by|before) {CLOCK} on {WDAY}{LONG_DATE.pattern}", re.I)
BEFORE_DATE = re.compile(rf"\b(?:before|prior to) {WDAY}{LONG_DATE.pattern}", re.I)
# An act with its own clock time or day of the month ("landed in Chicago at noon").
ACT_AT = re.compile(r"\bat (noon|midnight|\d{1,2})(?::(\d{2}))?(?![\w:]| [ap]\.m\.)")
ACT_TRAIN = re.compile(r"\b(\d{1,2})(am|pm) train\b")
ACT_ON = re.compile(r"\bon the (\d{1,2})(?:st|nd|rd|th)\b(?! floor)")
EN_WEEKDAY = re.compile(rf"\b({'|'.join(WEEKDAY_NAMES[:7])})\b", re.I)


def _unquoted_weekdays(text: str) -> list[int]:
    """The weekdays (0 = Monday) a text names outside its quoted phrases."""
    bare = QUOTED_PHRASE.sub(" ", text.lower())
    return [(m.lastindex - 1) % 7 for m in WEEKDAY_NAME.finditer(bare) if m.lastindex]


def _laughs(text: str) -> bool:
    """A laugh or smiley marker; a parenthetical such as "(auto)" is not a smiley."""
    return bool(LAUGH_MARK.search(re.sub(r"\([^()]*\)", " ", text)))


def _minute_of(clock: str) -> int:
    if clock in ("noon", "midnight"):
        return 720 if clock == "noon" else 0
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))? ([ap])\.m\.", clock)
    assert m, clock
    return (int(m.group(1)) % 12 + (12 if m.group(3) == "p" else 0)) * 60 + int(m.group(2) or 0)


def _act_minute(text: str) -> int | None:
    """An act's own clock time, read as early as is natural: a school pickup or a hotel
    check-in "at 3" is 3 p.m., a landing "at 8" may be 8 a.m., a bar closes at 2 in the night."""
    if m := ACT_TRAIN.search(text):
        return (int(m[1]) % 12 + (12 if m[2] == "pm" else 0)) * 60
    if m := ACT_AT.search(text):
        if m[1] in ("noon", "midnight"):
            return 720 if m[1] == "noon" else 0
        h, pm = int(m[1]), re.search(r"\b(picked the kids up|checked in)\b", text)
        return (h + (12 if h < 12 and pm else 0)) * 60 + int(m[2] or 0)
    return None


def _date(month: str, day: str, year: str) -> date:
    return date(int(year), MONTHS.index(month.capitalize()) + 1, int(day))


def _local(line) -> datetime:
    return datetime.strptime(line.local_time[:19], "%Y-%m-%d %H:%M:%S")


def test_rationale_weekdays_match_the_record(many: list[GenItem]) -> None:
    # Guide rule 24: a weekday a rationale names outside a quoted phrase is the record's own
    # local weekday ("One Friday is shown" on a Thursday record was wrong).
    assert _unquoted_weekdays("One Friday is shown; 'every friday' is a loose phrase.") == [4]
    assert _unquoted_weekdays("Not 'в понедельник' but the owner's пятницу.") == [4]
    assert _unquoted_weekdays("The record gives 'monday'; the assumption says 'Tuesday'.") == []
    for it in many:
        day = date.fromisoformat(it.target.local_time[:10]).weekday()
        assert set(_unquoted_weekdays(it.rationale)) <= {day}, (it.rationale, it.target.local_time)


def test_rationales_say_what_is_uncertain(many: list[GenItem]) -> None:
    # Rule 24: a joke marker leaves sincerity open, a denial or a correction conflicts with the
    # assumption in what it says (its truth is for the expert), a slang reading needs a
    # translator, and a date, sender or speaker mismatch leaves the assumption open (rule 23).
    # Quoted words ("got the deposit back at the same time") are the record's or the
    # assumption's, not the rationale's own claim.
    for it in many:
        why = it.rationale.lower()
        assert not DECLARES.search(QUOTED_PHRASE.sub(" ", why)), (it.family, it.rationale)
        if it.family == "ovr_joke":
            assert re.search(r"unclear whether the (sender|owner) meant", why), it.rationale
        if it.family in ("con_denial", "ovr_negation", "con_correction"):
            assert "cannot be true together with" in why and "for the expert" in why, it.rationale
        if it.family == "ovr_translation":
            assert "translator" in why, it.rationale
        if it.family in ("ovr_time_mismatch", "ovr_sender_mismatch", "ovr_speaker_mismatch"):
            assert re.search(r"does not show whether|cannot show|is not shown", why), it.rationale


def test_laugh_markers_only_mark_jokes(many: list[GenItem]) -> None:
    # A laugh or smiley leaves open whether the sender meant it (rule 24), so no supports or
    # contradicts record carries one, and no line after such a record laughs.
    assert _laughs("ну ок))") and _laughs("paid him lol") and not _laughs("(auto) stance=x")
    for it in many:
        if it.gold_stance in ("supports", "contradicts"):
            assert not _laughs(it.target.text), (it.family, it.target.text)
            for ln in it.lines()[it.target_index + 1 :]:
                assert not _laughs(ln.text), (it.family, it.target.text, ln.text)


def test_corrections_mark_the_right_message(many: list[GenItem]) -> None:
    # Rules 19 and 22: the correcting message is con_correction (contradicts, quoting the
    # correcting words); the statement it corrects is ovr_later_correction (complicates), whose
    # rationale names the correction. One sender, within minutes.
    seen: Counter[str] = Counter()
    for it in many:
        if it.family not in ("con_correction", "ovr_later_correction"):
            continue
        lines, i = it.lines(), it.target_index
        mine = [j for j, ln in enumerate(lines) if ln.sender == it.target.sender and j != i]
        if it.family == "con_correction":
            j = max(j for j in mine if j < i)  # the statement it corrects comes first
            assert it.proposed_quote not in lines[j].text, (it.proposed_quote, lines[j].text)
        else:
            j = min(j for j in mine if j > i)  # the correction comes after
            assert lines[j].text in it.rationale, (lines[j].text, it.rationale)
        assert abs(j - i) <= 2, [ln.text for ln in lines]
        assert abs((_local(lines[j]) - _local(lines[i])).total_seconds()) <= 600
        seen[it.family] += 1
    assert seen["con_correction"] >= 20 and seen["ovr_later_correction"] >= 20, seen


# The day a booking is for, which may lie after the record ("before May 7, 2025, X booked the
# uhaul for Monday, May 12, 2025"), and a window of clock times on a date.
FOR_DAY = re.compile(rf"\bfor ({'|'.join(d.capitalize() for d in WEEKDAY_NAMES[:7])}), "
                     rf"{LONG_DATE.pattern}")  # fmt: skip
WINDOW = re.compile(rf"\b(?:from|between) {CLOCK} (?:to|and) {CLOCK} on {WDAY}{LONG_DATE.pattern}",
                    re.I)  # fmt: skip
ALL_DAY = re.compile(rf"\ball day on {WDAY}{LONG_DATE.pattern}")
NEVER = re.compile(r"\bnever\b|ни разу|никогда")


def test_contradicts_assumptions_end_by_the_record(many: list[GenItem]) -> None:
    # Rule 23: a record rules an act or a place out only up to the moment it was sent ("still in
    # denver" at 12:09 rules out "had landed in New York by noon", never "that day"). Apart from
    # the day a booking is for, a contradicts assumption names no date after the record's. A
    # clock on the record's date is an earlier one or a window around the record's minute, never
    # the record's own minute. A value the record gives carries no clock at all. A denial or a
    # negation dates the act before the record's date, or bounds it by that date ("before May 7,
    # 2025"); where the record says "never" or the assumption names a weekday, it has no clock.
    assert CLOCK_ON.findall("By 2 p.m. on March 3, 2026, X had paid") == [
        ("2 p.m.", "March", "3", "2026")]  # fmt: skip
    assert BEFORE_DATE.findall("X landed at noon before March 3, 2026") == [("March", "3", "2026")]
    assert FOR_DAY.findall("booked the uhaul for Monday, May 12, 2025") == [
        ("Monday", "May", "12", "2025")]  # fmt: skip
    seen: Counter[str] = Counter()
    for it in many:
        if it.gold_stance != "contradicts" or it.family == "con_in_window":
            continue
        a, lt = it.assumption, it.target.local_time
        day, minute = date.fromisoformat(lt[:10]), int(lt[11:13]) * 60 + int(lt[14:16])
        booked = [_date(*m[1:]) for m in FOR_DAY.findall(a)]
        assert all(d > day for d in booked), (a, lt)
        rest = FOR_DAY.sub(" ", a)
        dates = [_date(*m) for m in LONG_DATE.findall(rest)]
        assert all(d <= day for d in dates), (a, lt)
        windows = [(_minute_of(lo), _minute_of(hi), _date(*m))
                   for lo, hi, *m in WINDOW.findall(rest)]  # fmt: skip
        windows += [(0, 24 * 60, _date(*m)) for m in ALL_DAY.findall(rest)]
        assert all(lo <= minute <= hi for lo, hi, d in windows if d == day), (a, lt)
        clocks = [(_minute_of(t), _date(*m)) for t, *m in CLOCK_ON.findall(rest)]
        assert all(t < minute for t, d in clocks if d == day), (a, lt)
        before = [_date(*m) for m in BEFORE_DATE.findall(rest)]
        # The record's date appears only in a window, with an earlier clock, or as the bound
        # "before" it.
        if day in dates:
            assert day in [d for _, d in clocks] + before + [d for *_, d in windows], (a, lt)
        if it.family in ("con_other_value", "con_correction"):
            assert not clocks and not windows, (a, lt)
        if it.family in ("con_denial", "ovr_negation"):
            assert dates, (a, lt)
            assert all(d < day or d in before for d in dates), (a, lt)
            assert all(d < day for _, d in clocks), (a, lt)
            # The act's own weekday is one the record names; a date's weekday alone (when.py
            # say_day) leaves the act at any time that day.
            own_day = {WEEKDAY_NAMES.index(w.lower()) for w in EN_WEEKDAY.findall(a)}
            own_day &= set(_weekday_mentions(it.target.text))
            if NEVER.search(it.target.text.lower()) or own_day:
                # The act's own clock ("never closed the bar at midnight") is not an added time.
                own = it.target.text.lower()
                added = [t for t, *_ in CLOCK_ON.findall(rest) if f"at {t}" not in own]
                assert not added, (a, it.target.text)
                seen["date-level"] += 1
        seen["clock"] += bool(clocks)
        seen["window"] += bool(windows)
        seen["booked"] += bool(booked)
    assert seen["clock"] >= 20 and seen["window"] >= 5 and seen["booked"] >= 5, seen
    assert seen["date-level"] >= 20, seen


def test_clock_bounds_never_cut_into_the_act(many: list[GenItem]) -> None:
    # "By 10 a.m. on January 5, X had landed in Chicago at noon" makes no sense: a clock bound
    # on an act is never earlier than the act's own time, and an act on a later day of the month
    # than the bound's date takes a date bound instead. A bound on the telling ("before 3 a.m.,
    # X told Y that they took the 6am train") or on a quoted message is a different matter.
    assert _act_minute("landed in Chicago at 3") == 180 and _act_minute("checked in at 3") == 900
    assert _act_minute("took the 8am train") == 480 and _act_minute("at 9:12 a.m. on May 3") is None
    assert ACT_ON.search("on the 1st") and not ACT_ON.search("on the 4th floor")
    seen: Counter[str] = Counter()
    for it in many:
        a = QUOTED.sub(" ", it.assumption)
        bounds = CLOCK_BOUND.findall(a)
        if not bounds or re.search(r"\b(told|wrote|said|confirmed|texted|messaged)\b", a):
            continue
        t, *d = bounds[0]
        if m := ACT_ON.search(a):
            assert int(m[1]) <= _date(*d).day, (it.family, a)
            seen["day"] += 1
        act = _act_minute(a)
        if act is not None:
            assert act <= _minute_of(t), (it.family, a)
            seen["clock"] += 1
    # Few acts with their own time take a clock bound now (a dated trap keeps the act's time
    # and names the date); the writers are checked at every minute below.
    assert seen["clock"] >= 1, seen


def test_writer_bounds_never_cut_into_the_act_at_any_minute() -> None:
    # The clock bounds done_by and bounded put on an act with its own time are never earlier
    # than that time and never the record's own minute, wherever in the day the record falls.
    from eval.train.writers import bounded, done_by

    assert _act_minute("closed the bar at 1") == 60
    rng = random.Random(0)  # noqa: S311 - a seeded test sample
    preds = ("landed in Chicago at noon", "picked the kids up at 3", "took the 8am train",
             "closed the bar at 1", "checked in at 4:30", "paid the plumber $300")  # fmt: skip
    seen: Counter[str] = Counter()
    for hour in range(24):
        for minute in (0, 9, 31, 59):
            local = datetime(2025, 5, 7, hour, minute)
            c = SimpleNamespace(local=local, day=local.date())
            for pred in preds:
                for _ in range(3):
                    for a in (done_by(rng, c, "X", pred, p=1.0), bounded(rng, c, "X", pred),
                              bounded(rng, c, "X", pred, after=True)):  # fmt: skip
                        for t, *d in CLOCK_BOUND.findall(a):
                            assert _date(*d) == local.date(), a
                            assert _minute_of(t) != hour * 60 + minute, (a, local)
                            act = _act_minute(a)
                            assert act is None or act <= _minute_of(t), (a, local)
                            seen["own time" if act is not None else "plain"] += 1
    assert seen["own time"] > 100 and seen["plain"] > 100, seen


TIME_ON = re.compile(rf"\b(by|before|after|at) {CLOCK} on {WDAY}{LONG_DATE.pattern}", re.I)


def test_stated_times_hold_or_miss_the_record(many: list[GenItem]) -> None:
    # A supports assumption's time holds the record ("before 9:40 p.m." for a record at 9:14
    # p.m., never "before 9:10 p.m."); a time mismatch's misses it.
    seen: Counter[str] = Counter()
    for it in many:
        lt = it.target.local_time
        day, minute = date.fromisoformat(lt[:10]), int(lt[11:13]) * 60 + int(lt[14:16])
        mismatch = it.family == "ovr_time_mismatch"
        if "daylight-saving" in it.rationale or it.gold_stance == "contradicts":
            continue  # a DST record reads its clock twice; contradicts has its own test
        for word, t, *d in TIME_ON.findall(QUOTED.sub(" ", it.assumption)):
            if _date(*d) != day:
                continue
            t, word = _minute_of(t), word.lower()
            if it.gold_stance == "supports":
                ok = {"before": t > minute, "after": t < minute, "at": t == minute,
                      "by": t >= minute}[word]  # fmt: skip
            elif mismatch:
                ok = {"before": t <= minute, "after": t > minute, "at": t != minute,
                      "by": t < minute}[word]  # fmt: skip
            else:
                ok = True
            assert ok, (it.family, it.assumption, lt)
            seen[it.gold_stance] += 1
    assert seen["supports"] > 100 and seen["complicates"] > 100, seen


# The other shapes eval/train/when.py gives a time: a looser bound or "about" a clock on a
# date, a range of clock times, a part of the day, and a bound of dates.
LOOSE_ON = re.compile(rf"\b(no later than|no earlier than|sometime before|sometime after|"
                      rf"at about|at around|around|at approximately) {CLOCK} on "
                      rf"{WDAY}{LONG_DATE.pattern}", re.I)  # fmt: skip
PART_ON = re.compile(rf"\b(?:(?:on|during) the (morning|afternoon|evening|night) of|"
                     rf"in the (morning|afternoon|evening) on|late in the (evening) on) "
                     rf"{WDAY}{LONG_DATE.pattern}", re.I)  # fmt: skip
DATE_BOUND = re.compile(rf"\b(on or before|on or after|before|prior to|after) "
                        rf"{WDAY}{LONG_DATE.pattern}", re.I)  # fmt: skip
DATE_RANGE = re.compile(
    rf"\bfrom {WDAY}{LONG_DATE.pattern} through {WDAY}{LONG_DATE.pattern}", re.I
)
# A part of the day holds a supports item's record (PART_SPAN), and misses a time trap's by
# two hours from its widest reading: "3 in the morning", "11 in the evening" (the supports
# items say "late in the evening" until 11:30 p.m.), and "the night of May 2", which can mean
# its small hours or its late evening, misses only the daytime between them.
PART_SPAN = {"morning": (300, 720), "afternoon": (720, 1020), "evening": (1020, 1260),
             "night": (1260, 1440)}  # fmt: skip
PART_WIDE = {"morning": (0, 720), "afternoon": (720, 1020), "evening": (1020, 1440)}


def _part_misses(part: str, minute: int) -> bool:
    if part == "night":
        return 360 + 120 <= minute <= 1080 - 120
    lo, hi = PART_WIDE[part]
    return minute <= lo - 120 or minute >= hi + 120


def test_parts_of_the_day_miss_only_by_their_widest_reading() -> None:
    # Every minute of the day: a part the time trap offers as a miss (when.far_parts) is two
    # hours from its widest reading, so "the evening" never misses 11:03 p.m., which a
    # supports item may call "late in the evening".
    for minute in range(24 * 60):
        for part in far_parts(minute):
            assert _part_misses(part, minute) and part != clear_part(minute), (part, minute)
    assert "evening" not in far_parts(23 * 60 + 3) and "night" in far_parts(10 * 60)
    assert "night" not in far_parts(17 * 60)  # "Friday night at 6" is said


def test_other_time_shapes_hold_or_miss_the_record(many: list[GenItem]) -> None:
    # A supports assumption's time holds the record's local time, whatever its shape; a time
    # mismatch's misses it: "about" a clock an hour or more away, a range whose nearest end is
    # 3 minutes or more away (as near as a supports item's range holds it), a part of the day
    # two hours or more from its widest reading, a bound or a range of dates that leaves the
    # record's date out. No shape gives the answer away: "the night of" comes up on both
    # sides, and a range of dates only in the contact windows, which sup_contact and
    # con_in_window share, never in the time trap alone.
    assert PART_ON.findall("late in the evening on Friday, May 2, 2025") == [
        ("", "", "evening", "May", "2", "2025")]  # fmt: skip
    assert not _part_misses("evening", 23 * 60 + 3) and _part_misses("night", 10 * 60)
    seen: Counter[object] = Counter()
    for it in many:
        lt = it.target.local_time
        day, minute = date.fromisoformat(lt[:10]), int(lt[11:13]) * 60 + int(lt[14:16])
        sup, miss = it.gold_stance == "supports", it.family == "ovr_time_mismatch"
        if not (sup or miss) or "daylight-saving" in it.rationale:
            continue
        a = QUOTED.sub(" ", it.assumption)
        for word, t, *d in LOOSE_ON.findall(a):
            if _date(*d) != day:
                continue
            t, word = _minute_of(t), word.lower()
            if word in ("no later than", "sometime before"):
                ok = t >= minute if sup else t < minute
            elif word in ("no earlier than", "sometime after"):
                ok = t <= minute if sup else t > minute
            else:
                ok = abs(t - minute) <= 5 if sup else abs(t - minute) >= 60
            assert ok, (it.family, it.assumption, lt)
            seen["loose"] += 1
        for lo, hi, *d in WINDOW.findall(a):
            if _date(*d) == day:
                lo, hi = _minute_of(lo), _minute_of(hi)
                ok = lo + 2 < minute < hi - 2 if sup else minute < lo - 2 or minute > hi + 2
                assert ok, (it.family, it.assumption, lt)
                seen["range"] += 1
        for *parts, month, dd, year in PART_ON.findall(a):
            if _date(month, dd, year) == day:
                part = ("night" if parts[2] else parts[0] or parts[1]).lower()
                lo, hi = PART_SPAN[part]
                ok = lo <= minute < hi if sup else _part_misses(part, minute)
                assert ok, (it.family, it.assumption, lt)
                seen["part"] += 1
                seen["night", sup] += part == "night"
        for word, *d in DATE_BOUND.findall(a):
            b, word = _date(*d), word.lower()
            holds = {"before": day < b, "prior to": day < b, "on or before": day <= b,
                     "after": day > b, "on or after": day >= b}[word]  # fmt: skip
            assert holds == sup, (it.family, it.assumption, lt)
            seen["date bound"] += 1
        for d in DATE_RANGE.findall(a):
            assert (_date(*d[:3]) <= day <= _date(*d[3:])) == sup, (it.family, it.assumption, lt)
            seen["date range", sup] += 1
    assert min(seen[k] for k in ("loose", "range", "part", "date bound")) >= 10, seen
    assert seen["night", True] and seen["night", False] and not seen["date range", False], seen


EDGE_ON = re.compile(rf"\b(before|by|no later than|sometime before|after|no earlier than|"
                     rf"sometime after) {CLOCK} on {WDAY}{LONG_DATE.pattern}", re.I)  # fmt: skip
UPPER_WORDS = {"before", "by", "no later than", "sometime before"}
UTC_STATED = re.compile(rf"{CLOCK} on {WDAY}{LONG_DATE.pattern}', its UTC time")


def _record_minute(it: GenItem) -> tuple[date, int]:
    lt = it.target.local_time
    return date.fromisoformat(lt[:10]), int(lt[11:13]) * 60 + int(lt[14:16])


def test_bounds_come_as_near_whether_they_hold_or_miss(many: list[GenItem]) -> None:
    # A bound, or a range's nearest end, falls as near the record's minute in a supports item
    # as in a time trap (when.edge_time, when.clock_range): run 6's supports items had bounds
    # 3 to 14 minutes from the record and its time traps never missed by less than 15, so a
    # near bound read as supports. Never nearer than 3 minutes, which would point at the
    # message itself.
    near: Counter[tuple[bool, bool]] = Counter()
    for it in many:
        day, minute = _record_minute(it)
        sup, miss = it.gold_stance == "supports", it.family == "ovr_time_mismatch"
        if not (sup or miss) or "daylight-saving" in it.rationale or it.family == "sup_contact":
            continue  # sup_contact states its contact windows with when.span, as con_in_window
        a = QUOTED.sub(" ", it.assumption)
        gaps = [abs(_minute_of(t) - minute) for _, t, *d in EDGE_ON.findall(a) if _date(*d) == day]
        gaps += [min(abs(_minute_of(lo) - minute), abs(_minute_of(hi) - minute))
                 for lo, hi, *d in WINDOW.findall(a) if _date(*d) == day]  # fmt: skip
        for gap in gaps:
            assert gap >= 3, (it.family, it.assumption, it.target.local_time)
            near[sup, gap < 15] += 1
    share = {sup: near[sup, True] / (near[sup, True] + near[sup, False]) for sup in (True, False)}
    assert near[False, True] >= 10 and abs(share[True] - share[False]) < 0.15, (near, share)


def test_time_traps_miss_on_another_date_as_well(many: list[GenItem]) -> None:
    # A time trap may hold the record's clock on another date, mostly the day before or after
    # (or give the record's UTC clock on its UTC date); a bound then runs away from the
    # record's date, before a time on an earlier date or after one on a later date, since the
    # other bounds would take the record's date in, and "the night of" another date, which can
    # run into the next, never comes up. A supports item's clock and part of the day are
    # always on the record's own date.
    seen: Counter[str] = Counter()
    for it in many:
        day = _record_minute(it)[0]
        sup, miss = it.gold_stance == "supports", it.family == "ovr_time_mismatch"
        if not (sup or miss) or "daylight-saving" in it.rationale:
            continue
        a = QUOTED.sub(" ", it.assumption)
        for word, _, *d in EDGE_ON.findall(a):
            if (other := _date(*d)) != day:
                assert miss, (it.family, it.assumption, it.target.local_time)
                assert (other < day) == (word.lower() in UPPER_WORDS), (it.assumption, day)
                seen["bound"] += 1
        for *parts, month, dd, year in PART_ON.findall(a):
            if (other := _date(month, dd, year)) != day:
                assert miss and abs((other - day).days) <= 3, (it.family, it.assumption)
                assert parts[0].lower() != "night" and not parts[2], it.assumption
                seen["part"] += 1
        for _, _, *d in WINDOW.findall(a):
            if _date(*d) != day:
                assert miss, (it.family, it.assumption, it.target.local_time)
                seen["range"] += 1
        if miss and "its UTC time" in it.rationale:  # the record's UTC clock, on its UTC date
            utc = _utc(it.target.local_time)[0]
            ((t, *d),) = UTC_STATED.findall(it.rationale)
            assert _date(*d) == utc.date() != day, (it.rationale, it.target.local_time)
            assert abs(_minute_of(t) - utc.hour * 60 - utc.minute) <= 2, it.rationale
            seen["utc"] += 1
    assert min(seen[k] for k in ("bound", "part", "range")) >= 5 and seen["utc"], seen


# Words that make a message's exact words name one message: a sender or time trap's record
# would rule these out (guide rule 23), so no family uses them (eval/train/frames.py).
ONE_MESSAGE = re.compile(r'\bwas the one who\b|\bthe (?:message|text|words) "[^"]*" '
                         r'(?:was|were|came|in the group)')  # fmt: skip


def test_no_assumption_makes_the_words_name_one_message(many: list[GenItem]) -> None:
    assert ONE_MESSAGE.search('the text "ok" came from Bo')
    assert not ONE_MESSAGE.search('Bo sent the owner the message "ok"')
    for it in many:
        assert not ONE_MESSAGE.search(it.assumption), (it.family, it.assumption)


def test_other_state_names_the_place(many: list[GenItem]) -> None:
    # Rule 23: never "home" when nothing shows where home is.
    for it in many:
        if it.family == "con_other_state":
            assert not re.search(r"\bhome\b|\bдома\b|\bдомой\b", it.target.text.lower()), it


# --- guide v0.3 follow-up: no surface cue gives the label away ----------------------------

CUE_CLOCK = re.compile(r"\b\d{1,2}(:\d{2})? ?[ap]\.?m\.?(?!\w)|\bnoon\b|\bmidnight\b", re.I)
STANCES = ("supports", "contradicts", "complicates", "irrelevant")


def _cues(rows: list[str]) -> tuple[float, float, float, float]:
    """Clock %, date %, ends-with-a-period % and mean length of a set of assumptions."""
    n = len(rows)
    return (100 * sum(bool(CUE_CLOCK.search(a)) for a in rows) / n,
            100 * sum(bool(LONG_DATE.search(a)) for a in rows) / n,
            100 * sum(a.endswith(".") for a in rows) / n,
            sum(len(a) for a in rows) / n)  # fmt: skip


def test_every_assumption_ends_with_a_period(many: list[GenItem]) -> None:
    for it in many:
        assert it.assumption.endswith("."), it.assumption


# Verbs that need both sides to have written (frames.CONTACT_NO and the shapes beside it).
TWO_WAY = re.compile(r"\bexchang|\beach other\b|\btraded?\b|\bcommunicat")
# The windows a contact assumption states (eval/train/when.py span), and a first contact's
# time (frames.first_contact, frames.none_before).
CUTOFF = re.compile(r"\bfirst\b|\bbegan\b|had not exchanged any messages before")
CONTACT_CLOCK = re.compile(rf"\b(after|before) {CLOCK} on {WDAY}{LONG_DATE.pattern}", re.I)
CONTACT_DATE = re.compile(
    rf"\b(on or before|on or after|before|after|on) {WDAY}{LONG_DATE.pattern}", re.I
)
OR_DATES = re.compile(rf"\bon {LONG_DATE.pattern} or {LONG_DATE.pattern}", re.I)
IN_MONTH = re.compile(rf"\b(?:in|during) ({'|'.join(MONTHS)}) (\d{{4}})\b", re.I)


def _contact_window(a: str) -> tuple[datetime, datetime]:
    """The local [start, end) a contact assumption states; for a first contact, the time
    before which it denies any, from datetime.min."""

    def at(month: str, dd: str, year: str, minute: int = 0) -> datetime:
        return datetime.combine(_date(month, dd, year), time()) + timedelta(minutes=minute)

    one = timedelta(days=1)
    if CUTOFF.search(a):
        if m := CONTACT_CLOCK.search(a):
            return datetime.min, at(*m.groups()[2:], _minute_of(m[2]))
        m = CONTACT_DATE.search(a)
        assert m and m[1].lower() in ("on", "before"), a
        return datetime.min, at(*m.groups()[1:])
    if m := WINDOW.search(a):
        return at(*m.groups()[2:], _minute_of(m[1])), at(*m.groups()[2:], _minute_of(m[2]))
    if m := CONTACT_CLOCK.search(a):
        d = at(*m.groups()[2:])
        t = d + timedelta(minutes=_minute_of(m[2]))
        return (t, d + one) if m[1].lower() == "after" else (d, t)
    if m := PART_ON.search(a):
        lo, hi = PART_SPAN[("night" if m[3] else m[1] or m[2]).lower()]
        d = at(*m.groups()[3:])
        return d + timedelta(minutes=lo), d + timedelta(minutes=hi)
    if (m := DATE_RANGE.search(a)) or (m := OR_DATES.search(a)):
        return at(*m.groups()[:3]), at(*m.groups()[3:]) + one
    if m := IN_MONTH.search(a):
        first = date(int(m[2]), MONTHS.index(m[1].capitalize()) + 1, 1)
        after = date(first.year + first.month // 12, first.month % 12 + 1, 1)
        return datetime.combine(first, time()), datetime.combine(after, time())
    m = CONTACT_DATE.search(a)
    assert m, a
    d = at(*m.groups()[1:])
    return {"on": (d, d + one), "before": (datetime.min, d),
            "on or before": (datetime.min, d + one), "after": (d + one, datetime.max),
            "on or after": (d, datetime.max)}[m[1].lower()]  # fmt: skip


def test_two_way_contact_denials_show_both_sides_writing(many: list[GenItem]) -> None:
    # One message alone leaves "did not exchange messages" open (strict contradicts), so a
    # denial in those verbs states a window that holds the record and a line from the other
    # side, and a first contact in them comes after a line from each side. And an answer is
    # never "confirmed": "55 so far" gives a number, not a settled one.
    assert _contact_window("the owner and Bo first texted each other after 9 p.m. on May 2, "
                           "2025") == (datetime.min, datetime(2025, 5, 2, 21))  # fmt: skip
    seen: Counter[bool] = Counter()
    for it in many:
        if it.family == "sup_answer":
            assert "confirmed" not in it.assumption, it.assumption
        if it.family != "con_in_window" or not TWO_WAY.search(it.assumption):
            continue
        start, end = _contact_window(QUOTED.sub(" ", it.assumption))
        assert start <= _local(it.target) < end, (it.probe_id, it.assumption, it.target)
        other = [x for x in it.context if x.account_id != it.target.account_id]
        assert any(start <= _local(x) < end for x in other), (it.probe_id, it.assumption)
        seen[start == datetime.min] += 1
    assert seen[True] >= 5 and seen[False] >= 20, seen


def _who(sender: str) -> str:
    """How an assumption names the account a line's sender field shows (names.Party.who)."""
    app, ident, *rest = sender.split(" ", 2)
    owner = rest == ["(owner)"]
    label = None if owner or not rest else rest[0]
    return Party(Account(app, ident, label, owner=owner), Person("x", "they", "en")).who


def _first_word(who: str) -> str | None:
    """The first word of the name an account shows ("Ilya" in "the contact saved as Ilya
    (work)"), or None for an account shown by its number, id or username alone."""
    m = re.search(r"saved as (.+)$|\(shown as @?(.+)\)$", who)
    return re.findall(r"[^\W\d_]+", (m[1] or m[2]).lower())[0] if m else None


WRITER_WHY = re.compile(r"The words came from (.+), not (.+); the record does not show whether "
                        r"\2 also wrote them\.")  # fmt: skip


def test_sender_traps_name_another_account_in_the_supports_shapes(many: list[GenItem]) -> None:
    # Guide rule 23: a sender trap's claimed sender never sent the record. It is the other side
    # of the chat, or an account no line shows (names.outside_account), at times one whose name
    # matches the chat contact's: the phone shows two accounts, and nothing merges them. Its
    # shapes are the supports items' (frames.py): a report, the message as the subject, or the
    # exact words.
    seen: Counter[str] = Counter()
    for it in many:
        if it.family != "ovr_sender_mismatch":
            continue
        m = WRITER_WHY.fullmatch(it.rationale)
        assert m and m[1] == it.target.sender, it.rationale
        # Every chat on the phone is the owner's, shown or not.
        claimed, members = m[2], {_who(ln.sender) for ln in it.lines()} | {"the owner"}
        assert claimed != _who(it.target.sender), it.assumption
        assert claimed in it.assumption or claimed[:1].upper() + claimed[1:] in it.assumption
        if claimed in members:
            seen["other side"] += 1
        else:
            seen["outside"] += 1
            names = {_first_word(w) for w in members} - {None}
            seen["namesake"] += _first_word(claimed) in names
        a = it.assumption
        seen["words" if it.target.text in a else "says" if " says " in a else "report"] += 1
    total = seen["other side"] + seen["outside"]
    assert 0.2 * total <= seen["outside"] <= 0.4 * total, seen
    assert seen["namesake"] >= 5 and seen["says"] >= 5, seen
    assert seen["report"] + seen["says"] >= 0.4 * total, seen


def test_supports_keep_only_if(many: list[GenItem]) -> None:
    # "only if jonah calls back will i pay" makes the condition needed, not enough on its own:
    # a supports report that dropped "only" would say more than the record (rule 14).
    seen = 0
    for it in many:
        if it.gold_stance == "supports" and re.search(r"\bonly if\b", it.target.text.lower()):
            assert re.search(r"\bonly if\b", it.assumption), it.assumption
            seen += 1
    assert seen >= 3, seen


def test_outside_accounts_are_never_members() -> None:
    # names.outside_account: never a member's identifier or name as the phone shows it; half
    # the time the first contact's own person behind another account.
    rng, namesakes = random.Random(7), 0  # noqa: S311 - a seeded test sample
    for i in range(2000):
        app, owner, contacts = cast(rng, ("en", "ru")[i % 2], extra=i % 3 == 0)
        members = [owner, *contacts]
        x = outside_account(rng, app, members)
        assert x.account.app == app and not x.account.owner
        assert x.account.identifier not in {m.account.identifier for m in members}
        assert x.who not in {m.who for m in members}
        namesakes += x.person == contacts[0].person
    assert 800 <= namesakes <= 1200, namesakes


def test_surface_cues_are_balanced_across_labels(many: list[GenItem]) -> None:
    # A clock time, a date, a final period or the length never gives the label away: per label,
    # each rate stays within 8 points of the overall rate and the mean length within 15% of it.
    assert _cues(["At noon on May 2, 2025, X paid.", "X paid"]) == (50.0, 50.0, 50.0, 18.5)
    overall = _cues([it.assumption for it in many])
    for stance in STANCES:
        rates = _cues([it.assumption for it in many if it.gold_stance == stance])
        for k in range(3):
            assert abs(rates[k] - overall[k]) <= 8, (stance, k, rates, overall)
        assert abs(rates[3] - overall[3]) <= 0.15 * overall[3], (stance, rates, overall)


# --- the seven shapes and rule 11, as rules over the generated items ----------------------

CAP_WEEKDAYS = "|".join(d.capitalize() for d in WEEKDAY_NAMES[:7])
WEEKDAY_ON_DATE = re.compile(rf"\b(on|for) ({CAP_WEEKDAYS}), {LONG_DATE.pattern}")
EN_SHORT = ("mon", "tue|tues", "wed", "thu|thur|thurs", "fri", "sat", "sun")
GENERIC_DAY = re.compile(r"\b(every|each|like every)\s+$|\b(каждую|каждый|каждое|по)\s+$")


def _weekday_mentions(text: str) -> list[int]:
    """The particular weekdays (0 = Monday) a line names: not plural ("fridays"), not generic
    ("every friday", "по пятницам"), not part of a name ("the thursday league")."""
    t = text.lower()
    out = []
    for d in range(7):
        for m in re.finditer(rf"\b({WEEKDAY_NAMES[d]}|{EN_SHORT[d]})\b(?!s\b)", t):
            if m[0] in ("sun", "sat") and re.search(r"\b(the|in the)\s+$", t[: m.start()]):
                continue
            if GENERIC_DAY.search(t[: m.start()]) or re.match(r"\s+(run|league)\b", t[m.end() :]):
                continue
            out.append(d)
        for m in re.finditer(rf"(?<![\w-]){WEEKDAY_NAMES[7 + d]}", t):
            if not GENERIC_DAY.search(t[: m.start()]):
                out.append(d)
    return out


# Families whose dates need not be an act's: a message sent on another date, a window of
# contact, an unrelated event.
ANY_DAY = {"ovr_time_mismatch", "con_in_window", "irr_other_topic", "irr_pleasantry",
           "ovr_injection_unrelated"}  # fmt: skip


def test_weekday_words_fit_each_lines_date(many: list[GenItem]) -> None:
    # Shape 4: no line names its own weekday as a particular day ("whats the plan for sat" is
    # never sent on a Saturday); a weekday an assumption dates is that date's weekday, a past
    # act's date falls before the record, and a plan's or a booking's after it. A date may
    # carry its weekday anywhere (eval/train/when.py say_day): the record's own date, or any
    # date in the families above.
    assert _weekday_mentions("whats the plan for sat") == [5]
    assert _weekday_mentions("every friday, the thursday league, fridays") == []
    assert _weekday_mentions("вернул в среду, по средам нет") == [2]
    seen: Counter[str] = Counter()
    for it in many:
        for ln in it.lines():
            day = date.fromisoformat(ln.local_time[:10]).weekday()
            assert day not in _weekday_mentions(ln.text), (ln.text, ln.local_time)
        day = date.fromisoformat(it.target.local_time[:10])
        for word, weekday, *m in WEEKDAY_ON_DATE.findall(it.assumption):
            d = _date(*m)
            assert d.strftime("%A") == weekday, it.assumption
            if d == day or it.family in ANY_DAY:
                seen["any"] += 1
                continue
            ahead = word == "for" or it.family in ("ovr_plan", "ovr_hypothetical")
            assert d > day if ahead else d < day, (it.family, it.assumption, it.target.local_time)
            seen["ahead" if ahead else "past"] += 1
    assert seen["past"] >= 100 and seen["ahead"] >= 20 and seen["any"] >= 20, seen


BETWEEN_DATES = re.compile(rf"\bbetween {LONG_DATE.pattern} and {LONG_DATE.pattern}")


def test_date_windows_never_say_between(many: list[GenItem]) -> None:
    # Shape 5: "between May 2 and May 4" leaves the end open; "on May 2, 2025 or May 3, 2025",
    # "from May 2, 2025 through May 4, 2025" or one date say it.
    for it in many:
        assert not BETWEEN_DATES.search(it.assumption), it.assumption
        assert not BETWEEN_DATES.search(it.rationale), it.rationale


REL_OK = re.compile(r"\b(tonight|last night|earlier tonight|an hour ago)\b|вчера|ночью")
REL_ONE_DATE = re.compile(r"\bthis (morning|afternoon|evening)\b|\btoday\b|сегодня|утром|днём")


def test_relative_time_records_can_mean_two_dates(many: list[GenItem]) -> None:
    # Shape 2 and rule 17: sent just after midnight, with a phrase that can point to either of
    # two dates; never one that points to one date only ("this afternoon").
    seen = 0
    for it in many:
        if it.family == "cpl_relative_time":
            t = it.target.text.lower()
            assert REL_OK.search(t) and not REL_ONE_DATE.search(t), t
            assert int(it.target.local_time[11:13]) < 3, it.target.local_time
            seen += 1
    assert seen >= 10


def test_translation_traps_rest_on_a_slang_reading(many: list[GenItem]) -> None:
    # Shape 6 and rule 6: the record carries a glossary slang word, the assumption takes that
    # word's slang reading, and the rationale names the readings that compete.
    gloss = dict(SLANG)
    seen = 0
    for it in many:
        if it.family != "ovr_translation":
            continue
        text = it.target.text.lower()
        tokens = re.findall(r"[^\W\d_]+", text)
        hits = [ru for ru, _ in SLANG if _ru_hit(ru, text, tokens)]
        a = it.assumption.lower()
        assert any(w in a for ru in hits for w in gloss[ru].lower().split() if len(w) > 3), (
            text, it.assumption)  # fmt: skip
        assert re.search(r"can mean .+ or ", it.rationale), it.rationale
        seen += 1
    assert seen >= 10


# Parties as the phone shows them, and words that carry no topic (as in eval/train/topics.py).
PARTY_NAME = re.compile(
    r"\b[Tt]he contact saved as (?:(?:[A-ZА-ЯЁ][\w'.-]*|[а-яё][\w-]*|\([^)]*\))\s?)+|"
    r"\bTelegram user \d+(?: \(shown as [^)]*\))?|\b[Tt]he Instagram account \S+|\+1 [\d-]+|"
    r"\b[Tt]he owner\b"
)
TOPIC_FRAME = set(
    "a an the to of in on at by for and or but so if as is it its im i'm u ur i me my we us "
    "you your he she his her him our they them their be was were am are do did does not no "
    "yes yep ok k lol fr tbh rn pls thx omw that this with from have has had been into than "
    "when while about every each also only just still again before after until over under "
    "then there here what who how why where which all any some one off up out owner contact "
    "saved account user telegram instagram whatsapp signal shown group chat message messages "
    "wrote said told texted january february march april may june july august september "
    "october november december morning afternoon evening night noon midnight today tonight "
    "tomorrow tmrw yesterday".split()
)
TOPIC_IRREGULAR = {**IRREGULAR, "kids": "kid", "children": "kid", "men": "man",
                   "people": "person", "boxes": "box", "taken": "take", "driven": "drive",
                   "gone": "go", "given": "give", "done": "do", "gotten": "get", "been": "be",
                   "seen": "see", "flown": "fly", "stolen": "steal", "shown": "show"}  # fmt: skip
# Nouns anyone can name with no antecedent: places and institutions, and parts of a day.
ANCHORLESS = set("gym airport dentist doctor vet atm bank train bus school police hospital store "
                 "pharmacy dmv park morning afternoon evening night week".split())  # fmt: skip


def _topic(text: str) -> set[str]:
    low = text.lower()
    tokens = re.findall(r"[^\W\d_]+", low)
    words = set(tokens)
    for ru, en in PAIRS + SLANG:
        if _ru_hit(ru, low, tokens):
            words |= set(en.lower().split())
    return {_stem(TOPIC_IRREGULAR.get(w, w)) for w in words if len(w) >= 2 and w not in TOPIC_FRAME}


def test_irrelevant_assumptions_share_no_topic_with_the_chat(many: list[GenItem]) -> None:
    # Shape 7 and rule 21: no topic word of an irrelevant assumption appears in any line of the
    # chat or any label it shows, and the assumption names nothing whose referent the chat
    # would have to show ("the venue"; "their rent" and "the gym" need none).
    seen = 0
    for it in many:
        if it.gold_stance != "irrelevant":
            continue
        a = PARTY_NAME.sub(" ", it.assumption)
        shown: set[str] = set()
        for ln in it.lines():
            label = re.sub(r"^\S+ \+?\d+|\(owner\)", " ", ln.sender)
            shown |= _topic(ln.text) | _topic(label)
        assert not _topic(LONG_DATE.sub(" ", a)) & shown, (it.assumption, it.target.text)
        for m in re.finditer(r"\b[Tt]he ((?:[\w'-]+ )?[\w'-]+)", a):
            assert set(m[1].lower().split()) & ANCHORLESS, (m[0], it.assumption)
        seen += 1
    assert seen >= 100


RECIPIENT = re.compile(r"\b(to|told|texted|sent|messaged) the owner\b|\bthe owner and\b|"
                       r"\bin a message to the owner\b")  # fmt: skip
WHOLE_RECORD = {"sup_time_window", "sup_contact", "con_in_window", "ovr_time_mismatch",
                "ovr_sender_mismatch", "ovr_speaker_mismatch"}  # fmt: skip


def test_group_chats_show_two_members(many: list[GenItem]) -> None:
    # Rule 11: a chat showing one non-owner account is one-to-one with the owner, so no
    # assumption calls it a group; in a group chat no assumption names the owner as the
    # recipient.
    seen = 0
    for it in many:
        others = {ln.sender for ln in it.lines() if "(owner)" not in ln.sender}
        a = QUOTED.sub(" ", it.assumption)
        if re.search(r"\bgroup chat\b|\bthe group\b", a):
            assert len(others) >= 2, (it.assumption, [ln.sender for ln in it.lines()])
            seen += 1
        if len(others) >= 2:
            assert not RECIPIENT.search(a), it.assumption
    assert seen >= 20


def test_time_and_sender_answers_quote_the_whole_record(many: list[GenItem]) -> None:
    # Rule 22: where the answer rests on the record's time or sender, the quote is the record.
    for it in many:
        if it.family in WHOLE_RECORD:
            assert it.proposed_quote == it.target.text, (it.family, it.proposed_quote)


# ---------------------------------------------------------------- Baker's own wording (bk_*)

BK_N = 2900  # a hundred items of each family, two hundred of bk_unrelated
BK_RUN = 7250  # `make stancedata`: 250 of each family, 500 of bk_unrelated
BK_FAMILY = {f.family_id: f for f in FAMILIES}
BK_INSIDE = {"bk_time_inside", "bk_call_inside", "bk_call_length", "bk_no_contact_inside",
             "bk_count_one", "bk_other_phone", "bk_party_unshown", "bk_claim_open",
             "bk_event_is_record"}  # fmt: skip
BK_MEANING = {"bk_meaning_said", "bk_meaning_other"}  # the words' user explains them
BK_FRAMED = {  # the openers and tails that may frame a quoted clause (rule 7)
    "bk_meaning_said": (OPENERS + OPENERS_RU, TAILS + TAILS_RU),
    "bk_meaning_other": (OPENERS + OPENERS_RU, TAILS + TAILS_RU),
    "bk_claim_denied": (DENY_OPENERS, DENY_TAILS),
}
# Words that would tell the meaning families apart by wording alone.
BK_MARKERS = re.compile(
    r"\b(only|just|nothing else|nothing more|thats it|that's it)\b"
    r"|только|просто|ничего больше|больше ничего|ничего другого|\bи вс[её]\b"
)
CLAIMED = ("meaning", "role", "event")  # the templates whose items show the claim
ROOT = {f: m for m, f in SURNAMES_RU}  # Belova reads as Belov: one surname, two forms
BK_OUTSIDE = {"bk_time_outside", "bk_outside_window"}
BK_CUE = {"bk_identity_named", "bk_author_cue", "bk_handles_said"}
BK_SENDER = re.compile(r"(\S+) (\S+)( \(owner\))?(?: \[([^\]]+)\])?")
BK_CALL = re.compile(r"(?:incoming|outgoing|missed) call from (\S+) to (\S+) at .+, (\d+)s")
BK_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
BK_DAY = {**{d: i for i, d in enumerate(BK_DAYS)}, "tues": 1, "thurs": 3, "fri": 4}
BK_DAY_RU = ("понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресенье")
BK_EN_DAY = re.compile(rf"\b(next |this )?({'|'.join(BK_DAY)})\b")
BK_LETTERS = set("abcdefghijklm")
PEOPLE_NAMES = {p.name for p in (*PEOPLE_EN, *PEOPLE_RU)}
MINUTE, HOUR, DAY = timedelta(minutes=1), timedelta(hours=1), timedelta(days=1)


@pytest.fixture(scope="module")
def bk() -> list[Any]:
    """Baker-wording items with the drafts they came from (scene, phone, events)."""
    return baker.generate_with_drafts(BK_N, 1, 12001)


def _brackets(sender: str) -> set[str]:
    m = BK_SENDER.fullmatch(sender)
    return set(m.group(4).split(", ")) if m and m.group(4) else set()


def _ids(d: Any) -> list[bf.Line]:
    """The draft's lines as Baker's ids print them (an item shows its people by name)."""
    return [render(d.scene, d.phone, e) for e in d.evs]


def _rec_ids(d: Any) -> set[str]:
    """The person ids in the record line's brackets."""
    return _brackets(_ids(d)[d.target].sender)


def _utc(local_time: str) -> tuple[datetime, str]:
    """A line's time as UTC, and the phone zone its abbreviation names (guide rule 27)."""
    stamp, abbr = local_time.rsplit(" ", 1)
    zone = bf.ZONE_OF[abbr]
    wall = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    for fold in (0, 1):
        aware = wall.replace(tzinfo=ZoneInfo(zone), fold=fold)
        if aware.tzname() == abbr:
            return aware.astimezone(UTC), zone
    raise AssertionError(local_time)


def _window(it: GenItem) -> tuple[datetime, datetime, str, str]:
    """The assumption's window as wall-clock [start, end) in its zone, and its raw words."""
    w = it.baker_params["window"]
    tz = ZoneInfo(w["tz"])
    start = datetime.fromisoformat(w["start_utc"]).astimezone(tz).replace(tzinfo=None)
    end = datetime.fromisoformat(w["end_utc"]) + timedelta(microseconds=1)
    return start, end.astimezone(tz).replace(tzinfo=None), w["tz"], w["raw"]


def _margins(
    it: GenItem, line: Any, bounds: tuple[datetime, datetime] | None = None
) -> dict[str, timedelta]:
    """How far inside (+) or outside (-) the window a line is, read in the window's zone and in
    the phone's: the smaller of the wall-clock and the elapsed distance to the nearest edge.
    `bounds` replaces the window's own wall-clock start and end."""
    utc, phone = _utc(line.local_time)
    start, end, tz, _ = _window(it)
    start, end = bounds or (start, end)
    out = {}
    for zone in dict.fromkeys((tz, phone)):
        z = ZoneInfo(zone)
        wall = utc.astimezone(z).replace(tzinfo=None)
        s, e = start.replace(tzinfo=z), end.replace(tzinfo=z)
        if start <= wall < end and s <= utc < e:
            out[zone] = min(wall - start, end - wall, utc - s, e - utc)
        elif start <= wall < end or s <= utc < e:
            out[zone] = timedelta(0)
        else:
            out[zone] = -min(abs(wall - start), abs(wall - end), abs(utc - s), abs(utc - e))
    return out


def test_baker_schedule_ids_and_labels(bk: list[Any]) -> None:
    counts = Counter(baker.slot(j)[0] for j in range(BK_RUN))
    assert counts == {f: 500 if f == "bk_unrelated" else 250 for f in baker.WRITERS}
    assert set(baker.WRITERS) == {f for f in BK_FAMILY if f.startswith("bk_")}
    ks: dict[str, list[int]] = defaultdict(list)
    for j in range(BK_RUN):
        fam, k = baker.slot(j)
        ks[fam].append(k)
    assert all(v == list(range(len(v))) for v in ks.values())
    for j, (it, d, _) in enumerate(bk):
        GenItem.model_validate(it.model_dump(mode="json"))
        assert it.probe_id == f"T{12001 + j:06d}" and it.generator == baker.GENERATOR
        assert it.source == "train_gen" and it.family == baker.slot(j)[0] == d.family
        f = BK_FAMILY[it.family]
        assert it.gold_stance == f.stance.value and it.baker_template in f.templates
        assert it.device_id == d.phone.dev
        said = f"{it.assumption} {it.rationale} {it.baker_claim or ''}".lower()
        for word in ("guilty", "innocent", "leader", "deleted", "gang"):
            assert not re.search(rf"\b{word}", said), (it.probe_id, word)
    templates = Counter(it.baker_template for it, _, _ in bk if it.family == "bk_unrelated")
    assert len(templates) == 12 and min(templates.values()) >= 16


def test_baker_claims_show_on_meaning_role_and_event_only(bk: list[Any]) -> None:
    # Rule 29: the claim shows with the meaning, role and event templates, in its own words;
    # a meaning claim quotes the words, and a role or event claim holds its window's raw words.
    seen: Counter[str] = Counter()
    for it, _, _ in bk:
        claim, p = it.baker_claim, it.baker_params
        assert bool(claim) == (it.baker_template in CLAIMED), it.probe_id
        if not claim:
            continue
        seen[it.baker_template] += 1
        assert claim.endswith(".") and claim[0].isupper() and "{" not in claim, claim
        assert not re.search(r"[ap]\.m\.\.", QUOTED.sub('""', claim)), claim  # one full stop
        if it.baker_template == "meaning":
            assert f'"{p["quoted_text"]}"' in claim, it.probe_id
        elif "window" in p:
            assert p["window"]["raw"] in claim, (it.probe_id, claim)
    assert min(seen.values()) >= 90, seen


def test_baker_items_show_names_never_ids(bk: list[Any]) -> None:
    # Rule 25: the assumption, the lines, the claim and the rationale show people by name.
    for it, d, _ in bk:
        shown = [it.assumption, it.rationale, it.baker_claim or ""]
        shown += [f"{ln.sender} {ln.text}" for ln in it.lines()]
        for text in shown:
            assert not re.search(r"\b(person|acct|dev):", text), (it.probe_id, text)
        names = it.baker_names or {}
        assert set(names) >= set(it.baker_params.get("person_ids", ())), it.probe_id
        firsts = [n.split(" ")[0] for n in names.values()]
        lasts = [ROOT.get(x, x) for x in (n.split(" ")[1] for n in names.values())]
        assert len(set(firsts)) == len(firsts) and len(set(lasts)) == len(lasts), names
        for pid in set().union(*(_brackets(ln.sender) for ln in _ids(d))):
            assert pid in names, (it.probe_id, pid)


def test_baker_runs_are_deterministic_and_leave_plain_items_alone() -> None:
    a = gen.generate(40, 3, n_baker=30)
    assert _dump(a) == _dump(gen.generate(40, 3, n_baker=30))
    assert _dump(a[:40]) == _dump(gen.generate(40, 3))
    assert _dump(gen.generate(40, 3, n_baker=12)) == _dump(a)[:52]
    assert [it.probe_id for it in a[40:]] == [f"T{n:06d}" for n in range(41, 71)]


def test_cli_writes_baker_items_after_the_plain_ones(tmp_path: Path) -> None:
    out = tmp_path / "train.jsonl"
    assert gen.main(["--n", "10", "--n-baker", "24", "--seed", "2", "--out", str(out)]) == 0
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert [r["generator"] for r in rows] == [gen.GENERATOR] * 10 + [baker.GENERATOR] * 24
    assert rows[10]["probe_id"] == "T000011"
    m = json.loads(out.with_name("train.jsonl.manifest.json").read_text(encoding="utf-8"))
    assert (m["n"], m["n_plain"], m["n_baker"]) == (34, 10, 24)


def test_baker_brackets_follow_the_scene(bk: list[Any]) -> None:
    # Rule 26: "(owner)" marks the record phone's own account; the brackets hold the owner of
    # every phone that has the account as its own, on any phone, and the links the scene confirms.
    for it, d, _ in bk:
        names = it.baker_names or {}
        for line, ids, ev in zip(it.lines(), _ids(d), d.evs, strict=True):
            assert (line.text, line.local_time) == (ids.text, ids.local_time), it.probe_id
            if ev.kind == "contact":
                assert (line.sender, line.local_time) == ("contact list", "no time in source")
                continue
            m = BK_SENDER.fullmatch(ids.sender)
            assert m and (m.group(1), m.group(2)) == (ev.frm.app, ev.frm.ident), ids.sender
            assert bool(m.group(3)) == (ev.frm in d.phone.own), ids.sender
            want = {bf.owner_person(p.item) for p in d.scene.phones if ev.frm in p.own}
            want |= {pid for acc, pid in d.scene.links if acc == ev.frm}
            assert _brackets(ids.sender) == want, (it.probe_id, ids.sender)
            for pid in want:  # the item shows each one by name
                assert names[pid] in line.sender, (it.probe_id, line.sender)


def _captioned(it: GenItem) -> bool:
    """The record follows a line with its own sender and time: its message's caption."""
    t = it.target_index
    cap = it.context[t - 1] if t else None
    return cap is not None and (cap.sender, cap.local_time) == (it.target.sender,
                                                                it.target.local_time)  # fmt: skip


def test_baker_excerpts_show_a_non_owner_line(bk: list[Any]) -> None:
    for it, _, _ in bk:
        assert any("(owner)" not in ln.sender for ln in it.lines()), it.probe_id
        assert len(it.context) <= (7 if _captioned(it) else 6)


def test_baker_captioned_attachments_follow_their_message(bk: list[Any]) -> None:
    # As Baker's small-model adapter shows one (eval/stancemodel's case_item): the attachment's
    # message, captioned, as its own line, then the file name, marked, with the same sender and
    # time; up to three lines before the message, as before any record. Nothing else shares a
    # line's time, and a caption-less attachment is its one marked line.
    seen: Counter[bool] = Counter()
    for it, d, _ in bk:
        t, rec = it.target_index, d.evs[d.target]
        times = [ln.local_time for ln in it.lines() if ln.local_time != "no time in source"]
        if not _captioned(it):
            assert len(set(times)) == len(times) and t <= 3, it.probe_id
            seen[False] += rec.kind == "att"
            continue
        seen[True] += 1
        cap = it.context[t - 1]
        assert rec.kind == "att" and d.evs[d.target - 1].kind == "msg", it.probe_id
        assert bk_file(it.target.text) and cap.text.strip() and not bk_file(cap.text)
        assert len(set(times)) == len(times) - 1 and t <= 4, it.probe_id
    assert 0.25 < seen[True] / (seen[True] + seen[False]) < 0.55, seen


def bk_file(text: str) -> bool:
    return bool(re.fullmatch(r"(?:IMG|VID|PXL|Screenshot)_[\w-]+\.\w+", text))


def test_baker_chat_records_carry_their_chats_members(bk: list[Any]) -> None:
    # Rule 26: a message's or attachment's excerpt is its own chat, between one of the record
    # phone's own accounts and one other, and the item carries both for the members line
    # Baker's context opens with; a call or a contact row has no chat and no members.
    for it, d, _ in bk:
        rec = d.evs[d.target]
        if rec.kind in ("call", "contact"):
            assert it.baker_members is None, it.probe_id
            continue
        chat = {rec.frm, rec.to}
        assert len(chat) == 2 and len(chat & set(d.phone.own)) == 1, it.probe_id
        for e in d.evs:
            assert e.kind in ("msg", "att") and {e.frm, e.to} == chat, it.probe_id
        assert it.baker_members == tuple(sorted({ln.sender for ln in it.lines()})), it.probe_id


# Window words careful readers could take either way, read from the words alone: "since May
# 1" may or may not hold the 1st, "between May 1 and May 9" the 1st and the 9th, "from May 1 to
# May 9" and "May 1–9" the 9th; "on or about May 2" may reach days either side.
BK_LOOSE_FIRST = re.compile(r"^(?:since|between [A-Z])")
BK_LOOSE_LAST = re.compile(
    r"^(?:between [A-Z]|from [A-Z][a-z]+\.? \d+ to |during [A-Z][a-z]+\.? \d+–)"
)
BK_FUZZY = re.compile(r"\bon or about\b", re.IGNORECASE)
BK_ABOUT = re.compile(r"\b(?:at about|at approximately|at around|around) \d")
# A window's clock is never noon or midnight, in any spelling ("12 p.m." reads either way).
BK_NOON = re.compile(r"\bnoon\b|\bmidnight\b|\b12(?::00)? ?(?:[ap]\.m\.|[AP]M)(?!\w)")


def test_baker_windows_hold_or_miss_their_records(bk: list[Any]) -> None:
    seen: Counter[str] = Counter()
    for it, _, _ in bk:
        timed = it.family in BK_INSIDE | BK_OUTSIDE | {"bk_zone_edge"}
        if "window" not in it.baker_params or not timed:
            continue
        start, end, tz, raw = _window(it)
        m = _margins(it, it.target)
        about = end - start == 16 * MINUTE
        clock = start.time() != time() or end.time() != time()
        # Baker reads "at about 9 p.m." as 8:52 to 9:08, and "around" or "at approximately"
        # the same way (core/audit/assumption_filler.py).
        assert about == bool(BK_ABOUT.search(raw)) and not BK_NOON.search(raw), (it.probe_id, raw)
        if it.family in BK_INSIDE and about:
            utc, phone = _utc(it.target.local_time)
            wall = utc.astimezone(ZoneInfo(tz)).replace(tzinfo=None)
            assert tz == phone and abs(wall - (start + (end - start) / 2)) <= 5 * MINUTE
        elif it.family in BK_INSIDE:  # never on a day a reader may leave out
            firm = (start + DAY if BK_LOOSE_FIRST.search(raw) else start,
                    end - DAY if BK_LOOSE_LAST.search(raw) else end)  # fmt: skip
            assert min(_margins(it, it.target, firm).values()) >= HOUR, (it.probe_id, raw, m)
        elif it.family in BK_OUTSIDE:
            need = 2 * HOUR if clock else 21 * DAY if BK_FUZZY.search(raw) else DAY
            assert max(m.values()) <= -need, (it.probe_id, raw, m)
        else:
            assert len(m) == 2 and sorted(v > timedelta(0) for v in m.values()) == [False, True]
            assert min(abs(v) for v in m.values()) >= 10 * MINUTE, (it.probe_id, m)
            utc, _ = _utc(it.target.local_time)
            wall = utc.astimezone(ZoneInfo(tz)).replace(tzinfo=None)
            near_start = abs(wall - start) < abs(wall - end)
            loose = BK_LOOSE_FIRST if near_start else BK_LOOSE_LAST
            assert not BK_FUZZY.search(raw) and not loose.search(raw), (it.probe_id, raw)
        seen[it.family] += 1
    assert set(seen) == BK_INSIDE | BK_OUTSIDE | {"bk_zone_edge"}


def test_baker_windows_pass_bakers_own_window_check(bk: list[Any]) -> None:
    # Every window is one Baker's filler could hold for its words (check_window): "after May 2"
    # starts at midnight on May 3, as the words mean and as the check reads it since #66.
    shapes: Counter[str] = Counter()
    for it, _, _ in bk:
        if "window" not in it.baker_params or it.baker_template == "weekday_date":
            continue
        start, end, _, raw = _window(it)
        check_window(start, end, raw, raw, raw, it.baker_template)
        shapes[re.sub(r"[A-Z][a-z]+\.?|\d+(?:st|nd|rd|th)?", "_", raw)] += 1
    assert len(shapes) >= 60, shapes.most_common()


def test_zone_edge_windows_pass_bakers_own_window_check() -> None:
    # A range across New Year or a clock range ending at noon comes up about once in tens of
    # thousands of items, too rarely for the bk sample, so the zone-edge windows are drawn here
    # many times: both dates of a range share a year, no clock is noon, and Baker's filler
    # could hold every window for its words.
    assert BK_NOON.search("between 9 a.m. and 12 p.m. on May 2, 2025")
    seen: Counter[object] = Counter()
    for i in range(30000):
        form = EDGE_FORMS[i % len(EDGE_FORMS)]
        rng = random.Random(i)  # noqa: S311 - synthetic data, not security
        win, _ = _edge_window(rng, form, "America/Chicago")
        assert not BK_NOON.search(win.raw), win.raw
        if form == "through":
            assert win.start.year == (win.end - DAY).year, win.raw
            seen["through", win.start.month == 12 and win.end.month == 1] += 1
        check_window(win.start, win.end, win.raw, win.raw, win.raw, "")
        seen[form] += 1
    assert seen["through", True] >= 5 and seen["between"] >= 3000, seen


def _weekday(quoted: str) -> tuple[int, str]:
    """The weekday a plan names (0 is Monday) and the word before it: "", "next" or "this"."""
    low = quoted.lower()
    ru = [i for i, stem in enumerate(BK_DAY_RU) if stem in low]
    if ru:
        assert len(ru) == 1, quoted
        this = re.search(r"\bв (этот|эту|это) ", low)
        prefix = "next" if "следующ" in low else "this" if this else ""
        return ru[0], prefix
    found = BK_EN_DAY.findall(low)
    assert len(found) == 1, quoted
    return BK_DAY[found[0][1]], found[0][0].strip()


def test_baker_weekdays_relate_to_their_dates(bk: list[Any]) -> None:
    seen: Counter[str] = Counter()
    for it, _, _ in bk:
        if it.baker_template != "weekday_date" or it.family == "bk_unrelated":
            continue
        utc, zone = _utc(it.target.local_time)
        start, end, tz, raw = _window(it)
        sent_at = utc.astimezone(ZoneInfo(zone))
        day, sent = start.date(), sent_at.date()
        assert tz == zone and start.hour == 0 and end - start == timedelta(days=1)
        assert raw == f"{BK_DAYS[day.weekday()].capitalize()}, {day:%B} {day.day}, {day.year}"
        assert 8 <= sent_at.hour <= 21
        wd, prefix = _weekday(it.baker_params["quoted_text"])
        # A plan for the send day's own weekday is sent before 10 a.m., so a time of day it
        # names ("monday morning") can still be that day's.
        assert wd != sent.weekday() or sent_at.hour <= 9, it.probe_id
        gap = (day - sent).days
        # "this <weekday>" is plain only for a later day of the same Monday-to-Saturday week.
        later_this_week = sent.weekday() < wd <= 5
        if it.family == "bk_weekday_next":
            assert prefix in ("", "this") and wd == day.weekday() and 1 <= gap <= 6, it.probe_id
            assert later_this_week or not prefix, it.probe_id
        elif it.family == "bk_weekday_open" and prefix:
            first = sent + timedelta(days=(wd - sent.weekday()) % 7)
            assert wd != sent.weekday() and day in (first, first + timedelta(days=7))
            assert prefix == "next" or not later_this_week, it.probe_id
            # "this" names a day of the send day's week, never one a week after the coming one
            assert prefix == "next" or day == first, it.probe_id
        elif it.family == "bk_weekday_open":
            assert wd == sent.weekday() and gap in (0, 7), it.probe_id
        elif it.family == "bk_weekday_wrong":
            assert not prefix
            assert wd not in (day.weekday(), sent.weekday()) and 1 <= gap <= 6, it.probe_id
        else:
            # Sent after the date: this record means a later date, but the same words sent
            # before it could mean it (rule 23), so the family is complicates.
            assert it.family == "bk_weekday_after" and it.gold_stance == "complicates"
            assert not prefix and wd == day.weekday() and 2 <= -gap <= 6, it.probe_id
        seen[f"{it.family}|{prefix}"] += 1
    assert len(seen) == 7 and min(seen.values()) >= 15, seen


def test_baker_calls_name_their_numbers_and_lengths(bk: list[Any]) -> None:
    seen = 0
    for it, d, _ in bk:
        m = BK_CALL.fullmatch(it.target.text)
        if m is None or it.family in ("bk_unrelated", "bk_claim_open"):
            continue
        seen += 1
        frm, to, dur = m.group(1), m.group(2), int(m.group(3))
        p = it.baker_params
        accounts = {a.split(":")[-1] for a in p.get("account_ids", ())}
        persons = set(p.get("person_ids", ()))
        assert it.target.sender.split(" ")[:2] == ["Phone", frm]
        assert to in accounts and (frm in accounts or persons & _rec_ids(d)), it.probe_id
        assert len(persons) <= 1, it.probe_id
        stated = p.get("duration_s")
        if it.family == "bk_call_length":
            assert dur < stated[0] / 2 or dur > 2 * stated[1], it.probe_id
        elif stated:
            assert stated[0] * 1.1 <= dur <= stated[1] * 0.9, it.probe_id
    assert seen >= 250


def test_baker_contact_rows_sit_on_the_named_phone(bk: list[Any]) -> None:
    seen = 0
    for it, _, _ in bk:
        if it.family not in ("bk_contact_row", "bk_contact_row_differs"):
            continue
        seen += 1
        p = it.baker_params
        assert not it.context and it.target.sender == "contact list"
        assert p["device_ids"] == [it.device_id]
        assert p["account_ids"][0].startswith(it.device_id.replace("dev:", "acct:") + ":Phone:")
        number = p["account_ids"][0].rsplit(":", 1)[1]
        name, row_number = it.target.text.rsplit(": ", 1)
        if it.family == "bk_contact_row":
            assert (name, row_number) == (p["quoted_text"], number)
        elif name == p["quoted_text"]:
            assert row_number != number
        else:
            assert row_number == number
            first = {w for w in re.findall(r"\w+", name) if w in PEOPLE_NAMES}
            assert first and not first & set(re.findall(r"\w+", p["quoted_text"]))
    assert seen == 200


def test_baker_sender_families_name_the_right_party(bk: list[Any]) -> None:
    seen: Counter[str] = Counter()
    for it, d, _ in bk:
        rec, p, ids = d.evs[d.target], it.baker_params, _ids(d)
        own = f":{rec.frm.app}:{rec.frm.ident}"
        if it.family == "bk_sender_shown":
            if p.get("person_ids"):
                assert p["person_ids"][0] in _rec_ids(d)
            else:
                assert all(a.endswith(own) for a in p["account_ids"])
            assert p.get("channels", [rec.frm.app]) == [rec.frm.app]
            if d.notes.get("elsewhere"):  # another phone's user's own number: no "(owner)"
                seen["elsewhere"] += 1
                assert "(owner)" not in it.target.sender and rec.frm not in d.phone.own
                assert p["person_ids"][0].startswith("person:dev:"), it.probe_id
        elif it.family == "bk_sender_other":
            for x in p.get("person_ids", ()):
                assert x not in _rec_ids(d)
                assert any(x in _brackets(ln.sender) for ln in ids), it.probe_id
            for a in p.get("account_ids", ()):
                assert a.rsplit(":", 1)[1] != rec.frm.ident, it.probe_id
        elif it.family == "bk_party_unshown":
            unshown = [x for x in p["person_ids"] if not x.startswith("person:dev:")]
            assert len(unshown) == 1, it.probe_id
            assert all(unshown[0] not in _brackets(ln.sender) for ln in ids)
            called = re.search(r'addresses \S+ \S+ as "([^"]+)"', it.rationale)
            if called:  # the owner calls the record's sender by name, just before the record
                seen["called"] += 1  # (before its caption, for a captioned attachment)
                lead = d.evs[d.target - (2 if _captioned(it) else 1)]
                assert lead.frm in d.phone.own and called.group(1) in lead.text, it.probe_id
                assert rec.frm not in d.phone.own and not _rec_ids(d), it.probe_id
    assert seen["elsewhere"] >= 30 and seen["called"] >= 30, seen


def test_baker_quotes_follow_the_guide(bk: list[Any]) -> None:
    # Rule 22: time and sender answers quote the whole record; cue families quote the cue.
    # Rule 7: the meaning families quote the explanation and bk_claim_denied the denial, without
    # an opener or tail the answer does not rest on ("remember ", ", period").
    seen: Counter[str] = Counter()
    for it, d, _ in bk:
        q, text, p = it.proposed_quote, it.target.text, it.baker_params
        assert q and q in text
        quoting = it.baker_template in ("weekday_date", "meaning")
        # bk_claim_open's own-meaning items explain the words in the meaning families' frames.
        explains = it.family in BK_MEANING or (it.family == "bk_claim_open" and "clause" in d.notes)
        if it.family in BK_FRAMED or explains:
            heads, tails = BK_FRAMED.get(it.family, BK_FRAMED["bk_meaning_other"])
            head, _, tail = text.partition(q)
            assert head in heads and tail in tails, (it.probe_id, head, tail)
            if explains:
                assert p["quoted_text"].casefold() in q.casefold(), it.probe_id
            seen[f"{it.family}|{q == text}"] += 1
        elif quoting and it.family not in BK_MEANING | {"bk_unrelated"}:
            assert q == p["quoted_text"], it.probe_id
        elif it.family == "bk_handles_said":
            assert all(h in q for h in p["handles"]), it.probe_id
        elif it.family == "bk_identity_named":
            assert p["person_ids"][0].split(":")[1] in q.lower(), it.probe_id
        elif it.family != "bk_author_cue":
            assert q == text, (it.family, q)
        skip = BK_MEANING | {"bk_unrelated", "bk_contact_row_differs"}
        if "quoted_text" in p and it.family not in skip and not explains:
            assert p["quoted_text"] in text and p["quoted_text"] not in " ".join(
                ln.text for ln in it.context
            ), it.probe_id
    assert all(seen[f"{f}|{whole}"] >= 5 for f in BK_FRAMED for whole in (True, False)), seen


def test_baker_own_frames_speak_in_the_first_person() -> None:
    # A frame counts as the sender's own usage only when it says so ("i", "me", "я"). "у нас"
    # may only place a thing ("это у нас сейф" reads as "our safe"), so no frame leans on it.
    first_person = re.compile(r"\b(?:i|me)\b|(?<![а-яё])я(?![а-яё])")
    assert OWN <= set(EXPLAIN) and OWN_RU <= set(EXPLAIN_RU)
    for frame in OWN | OWN_RU:
        assert first_person.search(frame), frame
    for frame in set(EXPLAIN) - OWN | set(EXPLAIN_RU) - OWN_RU:
        assert not first_person.search(frame), frame
    assert not any("у нас" in frame for frame in EXPLAIN_RU)
    # No tail confines the meaning to later messages ("for next time" coins the words).
    assert not any("next time" in tail for tail in TAILS)


_CLAIM_ON = re.compile(r"\bon ([A-Z][a-z]+ \d{1,2}, \d{4})")
_CLAIM_IN = re.compile(r"\bin ([A-Z][a-z]+ \d{4})")


def _claim_before_record(claim: str, local: date) -> bool:
    """Whether the claim's date or month ends before the record's local date."""
    if m := _CLAIM_ON.search(claim):
        return datetime.strptime(m.group(1), "%B %d, %Y").date() < local
    if m := _CLAIM_IN.search(claim):
        month = datetime.strptime(m.group(1), "%B %Y").date()
        return (month.year, month.month) < (local.year, local.month)
    return False


def test_baker_meaning_records_come_from_the_words_user(bk: list[Any]) -> None:
    # Rule 29: only the words' own user can say what they meant; nobody else uses them here.
    # Another meaning is complicates: with the user named (bk_meaning_other), since no claim
    # here is dated wholly before the record, and like a denial the explanation says nothing
    # about messages it does not cover; with no one named (bk_claim_open), since one account's
    # meaning cannot rule out another's use (rule 23).
    assert next(f for f in FAMILIES if f.family_id == "bk_meaning_other").stance == "complicates"
    seen: Counter[str] = Counter()
    for it, d, _ in bk:
        own_meaning = it.family == "bk_claim_open" and "clause" in d.notes
        if it.family not in BK_MEANING and not own_meaning:
            continue
        w, rec = it.baker_params["quoted_text"].casefold(), d.evs[d.target]
        users = {e.frm for e in d.evs if w in e.text.casefold()}
        assert users == {rec.frm} == {d.notes["user"]}, it.probe_id
        before = [e for e in d.evs[: d.target] if w in e.text.casefold()]
        assert bool(before) == d.notes["used_before"], it.probe_id
        assert w in rec.text.casefold() or before, it.probe_id
        # The explanation gives the meaning as the sender's own, or follows the sender's own
        # use of the words: never an explanation that may be of someone else's words.
        assert d.notes["own"] or d.notes["used_before"], (it.probe_id, rec.text)
        named = d.notes["named"]
        assert named or it.family != "bk_meaning_other", it.probe_id
        assert not named or it.family != "bk_claim_open", it.probe_id
        # A named claim names the person the record's line carries in brackets; else no one.
        assert bool(pids_in(d.claim) & _rec_ids(d)) == named == bool(pids_in(d.claim)), it.probe_id
        rec_day = rec.utc.astimezone(ZoneInfo(d.phone.zone)).date()
        assert not _claim_before_record(d.claim, rec_day), (it.probe_id, d.claim)
        seen[f"own|{d.notes['own']}"] += 1
        seen[f"{it.family}|{d.notes['used_before']}"] += 1
        seen[f"named|{it.family}|{named}"] += 1
        seen[it.lang] += 1
    assert len([k for k in seen if k.startswith("bk_")]) == 6, seen
    assert {k for k in seen if k.startswith("named|")} == {
        "named|bk_meaning_said|True", "named|bk_meaning_said|False",
        "named|bk_meaning_other|True", "named|bk_claim_open|False",
    }, seen  # fmt: skip
    assert seen["own|True"] and seen["own|False"] and seen["ru"] + seen["mixed"] >= 10, seen


def test_baker_names_numbers_and_handles(bk: list[Any]) -> None:
    # Training names start with A to M (Russian А to Л); numbers are fictional 555-01xx ones.
    for it, _, _ in bk:
        shown = [it.assumption, it.rationale, it.baker_claim or ""]
        for t in shown + [f"{ln.sender} {ln.text}" for ln in it.lines()]:
            for number in re.findall(r"\+1\d{10}", t):
                assert number[2:5] in AREA_CODES and number[5:10] == "55501", t
        for pid in it.baker_params.get("person_ids", ()):
            assert pid.startswith("person:dev:") or pid.split(":")[1][0] in BK_LETTERS, pid
        for name in (it.baker_names or {}).values():
            first, last = name.split(" ")
            assert first[0] in FIRST_LETTERS and last[0] in FIRST_LETTERS, name
        for ln in it.lines():
            app, ident = (ln.sender.split(" ") + [""])[:2]
            if app == "Telegram":
                assert re.fullmatch(r"[34]\d{6}", ident), ln.sender
            if app == "Instagram":
                assert ident[0] in BK_LETTERS, ln.sender
        for h in it.baker_params.get("handles", ()):
            assert re.fullmatch(r"@[a-z0-9_.]{5,}", h) and h[1] in BK_LETTERS, h
            assert "." not in h or it.baker_params["channels"] == ["Instagram"], h
    assert all(s[0] in BK_LETTERS for s in SURNAMES)
    latin = [*FIRSTS_EN, *FORMAL_RU.values(), *(x for pair in SURNAMES_RU for x in pair)]
    assert all(x[0] in FIRST_LETTERS for x in latin)
    nicks = [*NICKS.values(), *NICKS_RU.values(), *NICKS, *NICKS_RU]
    assert all(x[0].upper() in FIRST_LETTERS for x in nicks)


def test_baker_language_mix(bk: list[Any]) -> None:
    langs = Counter(it.lang for it, _, _ in bk)
    assert 0.06 < (langs["ru"] + langs["mixed"]) / len(bk) < 0.16 and langs["mixed"] > 0
    for it, _, _ in bk:
        texts = [ln.text for ln in it.lines()]
        if it.lang in ("ru", "mixed"):
            assert any(re.search(r"[а-яё]", t, re.I) for t in texts), it.probe_id
        else:
            assert not any(re.search(r"[а-яё]", t, re.I) for t in texts), it.probe_id


def test_baker_records_never_repeat_within_a_family(bk: list[Any]) -> None:
    texts: dict[str, list[str]] = defaultdict(list)
    for it, _, _ in bk:
        texts[it.family].append(it.target.text)
    for fam, rows in texts.items():
        assert len(set(rows)) == len(rows), fam


def test_baker_counts_stay_open(bk: list[Any]) -> None:
    # One message cannot settle a count: the stated number is more than the excerpt shows.
    seen = 0
    for it, _, _ in bk:
        p = it.baker_params
        if it.baker_template != "message_count" or it.family == "bk_unrelated":
            continue
        seen += 1
        shown = sum(max(_margins(it, ln).values()) >= timedelta(0) for ln in it.lines())
        assert p["expected_count"] >= 2 and p["expected_count"] > shown, it.probe_id
        assert len(p["device_ids"]) == 1
    assert seen >= 175


def test_baker_no_contact_records_show_both_parties(bk: list[Any]) -> None:
    seen = 0
    for it, d, _ in bk:
        if it.family != "bk_no_contact_inside":
            continue
        seen += 1
        p, rec = it.baker_params, d.evs[d.target]
        accounts = {ln.account_id.split(":", 2)[2] for ln in it.lines()}
        brackets = set().union(*(_brackets(ln.sender) for ln in _ids(d)))
        assert set(p.get("person_ids", ())) <= brackets, it.probe_id
        for a in p.get("account_ids", ()):
            assert a.split(":", 2)[2] in accounts or a.rsplit(":", 1)[1] in it.target.text
        assert it.device_id in p.get("device_ids", [it.device_id])
        assert p.get("channels", ["call"] if rec.kind == "call" else [rec.frm.app]) == (
            ["call"] if rec.kind == "call" else [rec.frm.app]
        )
        ends = {rec.frm, rec.to}
        named = set(p.get("account_ids", ()))
        for pid in p.get("person_ids", ()):
            assert ends & d.scene.holders(pid), it.probe_id
        assert all(any(d.phone.aid(e) == a for e in ends if e) for a in named), it.probe_id
    assert seen == 100


def test_baker_identity_and_authorship_name_the_record_account(bk: list[Any]) -> None:
    for it, d, _ in bk:
        p = it.baker_params
        if it.family in ("bk_identity_named", "bk_account_silent", "bk_author_cue"):
            assert p["account_ids"] == [it.target.account_id], it.probe_id
            assert len(p["person_ids"]) == 1
        if it.family == "bk_identity_named":
            assert not p["person_ids"][0].startswith("person:dev:")
            assert not _brackets(it.target.sender), it.probe_id
        if it.family == "bk_claim_open" and it.baker_template != "meaning":
            rec, pid = d.evs[d.target], p["person_ids"][0]  # the claim's actor is in the chat
            assert {rec.frm, rec.to} & d.scene.holders(pid), it.probe_id
            assert any(pid in _brackets(ln.sender) for ln in _ids(d)), it.probe_id


def test_baker_event_records_are_the_event(bk: list[Any]) -> None:
    # Rule 29: the record is the act the claim states, between the parties it names, plainly
    # inside the window (test_baker_windows_hold_or_miss_their_records checks the window).
    seen: Counter[str] = Counter()
    for it, d, _ in bk:
        if it.family != "bk_event_is_record":
            continue
        rec, p = d.evs[d.target], it.baker_params
        seen[rec.kind] += 1
        pids, accts = p["person_ids"], p.get("account_ids", ())
        assert len(pids) + len(accts) == 2 and rec.to is not None, it.probe_id
        ends = {rec.frm, rec.to}
        held = [ends & d.scene.holders(pid) for pid in pids]
        held += [{e for e in ends if d.phone.aid(e) == a} for a in accts]
        assert all(held) and set().union(*held) == ends, it.probe_id
        assert rec.frm in d.scene.holders(pids[0]), it.probe_id  # the actor sent it or called
    assert seen["call"] >= 15 and seen["msg"] >= 60, seen


def test_baker_denials_come_after_the_window_from_the_named_person(bk: list[Any]) -> None:
    # Rule 29: the named person's own words, from an account carrying them in brackets, sent
    # after the claim's window ended, rule the act out for that whole time.
    seen: Counter[str] = Counter()
    for it, d, _ in bk:
        if it.family != "bk_claim_denied":
            continue
        p, rec = it.baker_params, d.evs[d.target]
        assert p["person_ids"][0] in _rec_ids(d), it.probe_id
        assert rec.utc is not None and rec.utc >= datetime.fromisoformat(p["window"]["end_utc"])
        seen[f"{it.baker_template}|{d.notes['kind']}"] += 1
    assert len(seen) == 4 and min(seen.values()) >= 5, seen


def test_baker_denials_say_no_only_to_a_question_shown(bk: list[Any]) -> None:
    # A denial opens "no, " only right after the other end's question, which the excerpt shows.
    seen: Counter[str] = Counter()
    for it, d, _ in bk:
        if it.family != "bk_claim_denied":
            continue
        rec = d.evs[d.target]
        prev = d.evs[d.target - 1] if d.target else None
        asked = prev is not None and prev.frm == rec.to and prev.text in QUESTIONS
        assert asked == d.notes["asked"], it.probe_id
        if rec.text.startswith("no, "):
            assert asked, it.probe_id
        seen[f"{asked}|{rec.text.startswith('no, ')}"] += 1
    assert seen["True|True"] >= 3 and seen["True|False"] >= 3, seen


def test_baker_meaning_families_differ_in_meaning_alone(bk: list[Any]) -> None:
    # Both meaning families explain in the same frames, openers and tails: no marker such as
    # "only" or "nothing else" stands in either, so the wording never gives the label away.
    seen: Counter[str] = Counter()
    for it, _, _ in bk:
        if it.family in BK_MEANING:
            assert not BK_MARKERS.search(it.target.text.casefold()), it.probe_id
            seen[it.family] += 1
    assert min(seen.values()) >= 90, seen


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def test_baker_claims_show_every_party(bk: list[Any]) -> None:
    # Rule 29: each party of a claimed message or call is shown, by a bracket carrying the
    # person on some line or by the account the claim gives for them ("texted Dara Ahern at
    # (347) 555-0132"); every claim gives each account its assumption names, and an Instagram
    # handle built on a first name belongs to someone the claim names by that first name.
    seen: Counter[str] = Counter()
    for it, _, _ in bk:
        claim, p, names = it.baker_claim or "", it.baker_params, it.baker_names or {}
        if it.family == "bk_event_is_record":
            for pid in p["person_ids"]:
                assert any("[" in ln.sender and names[pid] in ln.sender for ln in it.lines()), (
                    it.probe_id
                )
        if not claim:
            continue
        for aid in p.get("account_ids", ()):
            ident = aid.split(":", 3)[3]
            num = _digits(ident)[-10:]
            assert (len(num) >= 7 and num in _digits(claim)) or ident.lstrip(
                "@"
            ).casefold() in claim.casefold(), (it.probe_id, ident)
            stems = [f for f in FIRSTS_EN if ident.startswith(f.lower())]
            if ":Instagram:" in aid and stems and it.lang == "en":
                assert f"{max(stems, key=len)} " in claim, (it.probe_id, ident)
            seen[it.family] += 1
    assert seen["bk_event_is_record"] >= 40 and seen["bk_claim_open"] >= 3, seen


def test_baker_unrelated_records_share_nothing_with_the_assumption(bk: list[Any]) -> None:
    for it, d, _ in bk:
        if it.family != "bk_unrelated":
            continue
        p, t = it.baker_params, it.baker_template
        shown = " ".join(f"{ln.sender} {ln.account_id} {ln.text}" for ln in _ids(d))
        seen = set().union(*(words(ln.text) for ln in it.lines()))
        if "quoted_text" in p:
            assert not words(p["quoted_text"]) & seen, (it.probe_id, p["quoted_text"])
        for h in p.get("handles", ()):
            assert h[1:] not in shown, it.probe_id
        if not (t == "sender" or (t == "record_time" and "quoted_text" in p)):
            # only a sender or time assumption may name the record's own sender
            for a in p.get("account_ids", ()):
                assert a.rsplit(":", 1)[1] not in shown, (it.probe_id, a)
        if t in ("role", "event", "authorship", "person_identity"):
            assert not any(pid in shown for pid in p["person_ids"]), it.probe_id
        if it.baker_claim:  # the claim is about no one a line carries in brackets
            names = it.baker_names or {}
            bracketed = set().union(*(_brackets(ln.sender) for ln in _ids(d)))
            assert not any(names[x] in it.baker_claim for x in bracketed), it.probe_id
