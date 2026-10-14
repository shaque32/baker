"""The held-out stance set generator: fixed output, fixed composition, clean sources."""

from __future__ import annotations

import contextlib
import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from core.audit.quotes import verify_quote
from eval.heldout import GENERATOR, ID_PREFIX, SEEDS, SOURCE, bk_meanings, bk_names, scene
from eval.heldout.bk_common import BK_GENERATOR
from eval.heldout.bk_schedule import BK_COMPOSITION
from eval.heldout.data_complicates import HEARSAY
from eval.heldout.data_support import QA
from eval.heldout.frames import names_in
from eval.heldout.generate import generate, plain_items
from eval.heldout.glossary import RU_EN_PAIRS, SLANG_FORMS
from eval.heldout.pools import (
    AREA_CODES,
    AWAY,
    CYRILLIC_FULL,
    MENTIONED_RU,
    NEUTRAL_EN,
    NEUTRAL_MIXED,
    NEUTRAL_RU,
    PLACES,
    WEEKDAYS_EN,
)
from eval.heldout.schedule import COMPOSITION, CONTRADICTS_FAMILIES, MISMATCH_TRAPS
from eval.heldout.text import normalized
from eval.heldout.verbs import has_past_verb
from eval.stancedata.bakerform import ZONE_OF
from eval.stancedata.chat import write_jsonl
from eval.stancedata.families import family
from eval.stancedata.model import GenItem
from eval.stancedata.names import case_names

PACKAGE = Path(__file__).resolve().parent.parent / "eval" / "heldout"

# The test split, exactly; the dev split is half of every number.
BLOCKS = {
    "clear_support": 200,
    "contradicts": 390,
    "complicates": 120,
    "irrelevant": 80,
}
MINIMUMS = {"sup_": 15, "con_": 40, "cpl_": 15}
OVERREACH_GATED = 340  # every ovr_* family except ovr_translation
OVERREACH_MISMATCH_TRAPS = 120  # time, sender, speaker and later-correction traps
OVERREACH_OTHER_MIN = 12
TRANSLATION = 20
TOTAL = 1150
# GO_BAR.md: at least 1,000 gated items; the bar needs 420 gold contradicts, kept with a margin.
GATED_MIN = 1000
CONTRADICTS_MIN = 440


@pytest.fixture(scope="module")
def test_items() -> list[GenItem]:
    return generate("test")


@pytest.fixture(scope="module")
def dev_items() -> list[GenItem]:
    return generate("dev")


def _dump(items: list[GenItem]) -> list[str]:
    return [it.model_dump_json() for it in items]


def _plain(items: list[GenItem]) -> list[GenItem]:
    """The plain-sentence items. The items in Baker's own wording (bk_*) follow them in each
    split and have tests of their own at the end of this file."""
    return [it for it in items if not it.family.startswith("bk_")]


def _by_family(items: list[GenItem]) -> Counter[str]:
    return Counter(it.family for it in items)


def _check_composition(items: list[GenItem], scale: int) -> None:
    fam = _by_family(items)
    assert sum(fam.values()) == TOTAL // scale
    for family_id, n in COMPOSITION.items():
        assert fam[family_id] == n // scale, family_id
    cats = Counter(family(it.family).category for it in items)
    for block, n in BLOCKS.items():
        assert cats[block] == n // scale, block
    for prefix, floor in MINIMUMS.items():
        for family_id, n in fam.items():
            if family_id.startswith(prefix):
                assert n >= floor // scale, family_id
    gated = sum(n for f, n in fam.items() if f.startswith("ovr_") and f != "ovr_translation")
    assert gated == OVERREACH_GATED // scale
    assert sum(fam[f] for f in MISMATCH_TRAPS) >= OVERREACH_MISMATCH_TRAPS // scale
    for family_id, n in fam.items():
        if family_id.startswith("ovr_") and family_id not in MISMATCH_TRAPS:
            assert n >= OVERREACH_OTHER_MIN // scale, family_id
    assert fam["ovr_translation"] == TRANSLATION // scale
    assert fam["irr_other_topic"] > 0 and fam["irr_pleasantry"] > 0
    stances = Counter(it.gold_stance for it in items)
    assert stances["contradicts"] >= CONTRADICTS_MIN // scale
    assert sum(it.disputed is None for it in items) >= GATED_MIN // scale
    # Guide v0.3: contradicts come only from these families; the four traps are complicates.
    contra = {it.family for it in items if it.gold_stance == "contradicts"}
    assert contra == set(CONTRADICTS_FAMILIES)
    for family_id in MISMATCH_TRAPS:
        assert family(family_id).stance == "complicates", family_id


def test_generation_is_deterministic(test_items: list[GenItem], dev_items: list[GenItem]) -> None:
    assert _dump(generate("test")) == _dump(test_items)
    assert _dump(generate("dev")) == _dump(dev_items)


def test_test_split_composition(test_items: list[GenItem]) -> None:
    _check_composition(_plain(test_items), 1)


def test_dev_split_is_half_with_the_same_shape(dev_items: list[GenItem]) -> None:
    _check_composition(_plain(dev_items), 2)


@pytest.mark.parametrize("split", ["test", "dev"])
def test_items_validate_and_ids_run_in_order(split: str, request: pytest.FixtureRequest) -> None:
    items = request.getfixturevalue(f"{split}_items")
    prefix = ID_PREFIX[split]
    for i, it in enumerate(items, start=1):
        GenItem.model_validate(it.model_dump())
        baker = it.family.startswith("bk_")
        assert it.source == SOURCE
        assert it.generator == (BK_GENERATOR if baker else GENERATOR)
        assert it.probe_id == f"{prefix}{i:06d}"
        assert it.group == it.probe_id
        assert it.rationale.strip()
        assert (0 if baker else 1) <= len(it.context) <= 6  # a contact row stands alone
    assert SEEDS["test"] != SEEDS["dev"]


def test_only_translation_items_are_disputed(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        assert (it.disputed is not None) == (it.family == "ovr_translation"), it.probe_id


def test_record_texts_are_unique_within_test_and_disjoint_from_dev(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    test_records = [normalized(it.target.text) for it in test_items]
    assert len(set(test_records)) == len(test_records)
    dev_records = {normalized(it.target.text) for it in dev_items}
    assert not set(test_records) & dev_records
    test_assumptions = [normalized(it.assumption) for it in test_items]
    assert len(set(test_assumptions)) == len(test_assumptions)


def test_russian_share_in_every_block(test_items: list[GenItem]) -> None:
    by_block: dict[str, Counter[str]] = {}
    for it in _plain(test_items):
        by_block.setdefault(it.family.split("_")[0], Counter())[it.lang] += 1
    for block, langs in by_block.items():
        n = sum(langs.values())
        assert 0.15 <= langs["ru"] / n <= 0.3, (block, langs)
        assert langs["mixed"] >= 1, block
        assert langs["en"] > langs["ru"], block


_SENDER = re.compile(r"^(\w+) (\S+)(?: (.+))?$")


def _accounts(items: list[GenItem]) -> list[tuple[str, str, str | None]]:
    out = []
    for it in items:
        for line in [it.target, *it.context]:
            m = _SENDER.match(line.sender)
            assert m, line.sender
            out.append((m.group(1), m.group(2), m.group(3)))
    return out


def test_labels_phones_and_telegram_ids_follow_the_pools(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for app, ident, label in _accounts(_plain(test_items + dev_items)):
        if label and label != "(owner)":
            first = label.lstrip("@")[0].upper()
            assert "N" <= first <= "Z" or "М" <= first <= "Я", label
        if app == "Telegram":
            assert re.fullmatch(r"[89]\d{6}", ident), ident
        elif app != "Instagram":
            m = re.fullmatch(r"\+1(\d{3})555(01\d{2})", ident)
            assert m, ident
            assert m.group(1) in AREA_CODES, ident


def test_assumptions_and_rationales_avoid_banned_words(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    banned = re.compile(r"\b(guilty|innocent|leader|deleted)\b", re.IGNORECASE)
    for it in test_items + dev_items:
        assert not banned.search(it.assumption + " " + it.rationale), it.probe_id


def test_package_source_is_clean() -> None:
    forbidden = [
        "case" + "01",
        "case" + "02",
        "probe" + "_draft",
        "eval/" + "gold",
        "eval." + "synthetic",
    ]
    for path in sorted(PACKAGE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, (path.name, needle)
        assert "eval.train" not in text, path.name
        assert "from eval import train" not in text, path.name


def test_every_excerpt_shows_the_other_party(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        senders = [line.sender for line in [it.target, *it.context]]
        assert any(not s.endswith("(owner)") for s in senders), it.probe_id


_SAYS = re.compile(
    r"\b(told|said|wrote|sent|messages?|messaged|replied|answered|asked|confirmed|exchanged)\b",
    re.IGNORECASE,
)


def test_supports_assumptions_say_what_the_message_communicates(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in _plain(test_items + dev_items):  # Baker's templates are the product's wording
        if it.gold_stance == "supports":
            assert _SAYS.search(it.assumption), (it.probe_id, it.assumption)


_QUANTIFIER = re.compile(
    r"\b(usually|most days|mostly|always|every|как обычно|обычно|всегда|как каждый|как каждую)\b",
    re.IGNORECASE,
)


def test_count_records_show_one_instance(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family == "ovr_count":
            assert not _QUANTIFIER.search(it.target.text), (it.probe_id, it.target.text)


def test_handle_owner_accounts_fit_the_named_person(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    cyrillic_first = {lat: cyr.split()[0] for lat, cyr, _ in CYRILLIC_FULL}
    for it in test_items + dev_items:
        if it.family != "ovr_handle_owner":
            continue
        m = re.search(r"belongs to (.+?)(?:,|;|\.$)", it.rationale)
        assert m, it.rationale
        full = m.group(1)
        first = full.split()[0].lower()
        firsts = {first, cyrillic_first.get(full, first).lower()}
        app, ident, label = _SENDER.match(it.target.sender).groups()
        if app == "Instagram":
            assert ident.lower().startswith(first), (it.probe_id, ident, full)
        if label:
            core = label.lstrip("@").lower()
            initials = re.fullmatch(r"[^\W\d_]\.[^\W\d_]\.", label)
            assert initials or any(core.startswith(f) for f in firsts), (it.probe_id, label, full)
        assert full in it.assumption, (it.probe_id, it.assumption)


# ------------------------------------------------------------------ corrections, plans, reports

_NEGATION = re.compile(r"\bnot\b|(?<![а-яё])не(?![а-яё])")
_RU_DAY_STEMS = ("понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресень")
_ALL_PLACES = sorted({p for places in PLACES.values() for p in places}, key=len, reverse=True)


def _slot_values(text: str) -> dict[str, set[str]]:
    """The place, weekday and number values a line carries, by slot type."""
    low = text.lower()
    places: set[str] = set()
    for p in _ALL_PLACES:  # longest first: a place inside a longer place name is not a second one
        if p.lower() in low:
            places.add(p)
            low = low.replace(p.lower(), " ")
    days = {d for d in WEEKDAYS_EN if re.search(rf"\b{d}\b", low)}
    days |= {stem for stem in _RU_DAY_STEMS if stem in low}
    return {"place": places, "day": days, "number": set(re.findall(r"\d+", low))}


def _after_target(it: GenItem):
    return it.context[it.target_index :]


def _correction(it: GenItem) -> tuple[str, str]:
    """(the original statement, the same sender's correction) of a correction item."""
    if it.family == "ovr_later_correction":  # the record is the original; the fix comes later
        fix = next(line.text for line in _after_target(it) if line.sender == it.target.sender)
        return it.target.text, fix
    before = it.context[: it.target_index]  # con_correction: the record is the fix
    original = next(line.text for line in reversed(before) if line.sender == it.target.sender)
    return original, it.target.text


def test_corrections_replace_the_same_slot(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 19: a correction names the replacement and the value it replaces."""
    for it in test_items + dev_items:
        if it.family not in ("ovr_later_correction", "con_correction"):
            continue
        original, fix = _correction(it)
        assert _NEGATION.search(fix.lower()), (it.probe_id, fix)
        got = _slot_values(fix)
        kind = next((k for k in ("place", "day", "number") if len(got[k]) >= 2), None)
        assert kind, (it.probe_id, fix)
        had = _slot_values(original)[kind]
        assert got[kind] & had, (it.probe_id, "the correction repeats the record's value", fix)
        assert got[kind] - had, (it.probe_id, "the correction names a new value", fix)
        if it.family == "con_correction":  # rule 22: the quote is the correcting words
            quoted = _slot_values(it.proposed_quote)[kind]
            assert _NEGATION.search(it.proposed_quote.lower()), (it.probe_id, it.proposed_quote)
            assert quoted & had and quoted - had, (it.probe_id, it.proposed_quote)
            assert original in it.rationale, (it.probe_id, "the rationale names the original")
        else:  # rule 22: the rationale names the later message that overturns the record
            assert fix in it.rationale and "does not settle" in it.rationale, it.probe_id


# Rule 12: assumptions state facts. These families are about a message or a contact pattern
# (verbatim text, timing, sender, contact) or restate what a message communicates (supports).
_REPORT_ALLOWED = {
    "sup_verbatim",
    "sup_contact",
    "sup_account_shared",
    "ovr_sender_mismatch",
    "ovr_time_mismatch",
    "ovr_speaker_mismatch",
    "con_in_window",
    "sup_plain",
    "sup_answer",
    "sup_injection",
}
_REPORT_FRAMES = re.compile(
    r"says that|said that|the message|wrote to the owner that|told the owner that"
    r"|\b(?:told|wrote to) [^.]{0,80}? that\b"
    r"|сообщени|написал[а]? владельцу|сказал[а]? владельцу",
    re.IGNORECASE,
)


def test_assumptions_state_facts_not_reports(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    bad = [
        (it.probe_id, it.family, it.assumption)
        for it in _plain(test_items + dev_items)
        if it.family not in _REPORT_ALLOWED and _REPORT_FRAMES.search(it.assumption)
    ]
    assert not bad, bad[:10]


_PLAN_EN = re.compile(
    r"\b(lets|let's|ill|i'll|we'll|gonna|going to|will|tomorrow|tmrw|next week"
    r"|planning to|plan to)\b"
)
_PLAN_RU = re.compile(
    r"(?<![а-яё])(буду|будем|собираюсь|собираемся|давай|поедем|поеду|завтра|планирую)(?![а-яё])"
)


def test_plan_records_carry_a_plan_marker(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family == "ovr_plan":
            text = it.target.text.lower()
            assert _PLAN_EN.search(text) or _PLAN_RU.search(text), (it.probe_id, text)


def test_shared_account_claims_name_the_person(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family == "ovr_shared_account":
            m = re.search(r"does not show that (.+?) wrote it", it.rationale)
            assert m and m.group(1) in it.assumption, (it.probe_id, it.assumption)


# ------------------------------------------------------------------------ assumption wording

_GENDERED_EN = re.compile(r"\b(he|she|his|him|her|hers)\b", re.IGNORECASE)
_GENDERED_RU = re.compile(r"(?<![а-яё])(он|она|его|её|ему|ей)(?![а-яё])")
_RELATIVE = re.compile(
    r"\b(last night|the night before|yesterday|tonight|tomorrow|this weekend|the man|the woman)\b"
    r"|(?<![а-яё])(вчера|сегодня|завтра)(?![а-яё])",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"\b(it|him|her|them)\b", re.IGNORECASE)


def _outside_quotes(text: str) -> str:
    """The assumption's own words: verbatim record quotes and name glosses are left out."""
    return re.sub(r'"[^"]*"', '""', text)


def test_assumptions_carry_no_gender(test_items: list[GenItem], dev_items: list[GenItem]) -> None:
    for it in test_items + dev_items:
        assert not _GENDERED_EN.search(_outside_quotes(it.assumption)), (it.probe_id, it.assumption)
        assert not _GENDERED_RU.search(_outside_quotes(it.assumption)), (it.probe_id, it.assumption)


def test_assumptions_resolve_times_and_objects(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        own = _outside_quotes(it.assumption)
        assert not _RELATIVE.search(own), (it.probe_id, it.assumption)
        assert not _PLACEHOLDER.search(own), (it.probe_id, it.assumption)


# Words the assumption frames and dates use; never content a record could lack.
_FRAME_WORDS = set(
    """
    told wrote said says sent message messages messaged exchanged replied answered asked
    confirmed least themselves someone others
    read timed owner contact saved number account user shown group according chat shows record
    telegram instagram whatsapp signal phone sender writer between before after during that this
    with from their they there were been being have having into onto over under when while then than
    also both some same other later earlier morning night evening afternoon noon midnight week
    month year today local time could would should might will shall must does done doing
    around until through within without because where which what whose still each every
    january february march april may june july august september october november december
    """.split()
)
_GLOSSARY_WORDS = {w for _, en in RU_EN_PAIRS for w in re.findall(r"[a-z]{4,}", en.lower())}
_RU_NAMES_EN = {lat.lower() for *_, lat in MENTIONED_RU}
_RU_NAMES_EN |= {full.split()[0].lower() for full, _, _ in CYRILLIC_FULL}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zа-яё]+", text.lower()))


# Irregular past forms, so "paid" counts as present when the record says "pay".
_BASE_FORMS = {
    "brought": "bring",
    "left": "leave",
    "paid": "pay",
    "came": "come",
    "went": "go",
    "kept": "keep",
    "took": "take",
    "gave": "give",
    "drove": "drive",
    "sold": "sell",
    "made": "make",
    "ran": "run",
    "met": "meet",
    "threw": "throw",
    "thrown": "throw",
    "held": "hold",
    "fed": "feed",
}


def _known(word: str, pool: set[str]) -> bool:
    """A content word counts as present when a pool word shares its first five letters."""
    forms = {word, _BASE_FORMS.get(word, word)}
    return any(
        w[:5] == t[:5] if len(t) >= 5 else (len(t) >= 3 and w.startswith(t))
        for t in pool
        for w in forms
    )


def test_supports_assumptions_add_nothing_the_record_lacks(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    bad = []
    for it in _plain(test_items + dev_items):
        if it.gold_stance != "supports":
            continue
        lines = [it.target, *it.context]
        pool = set()
        for line in lines:
            pool |= _tokens(line.text) | _tokens(line.sender)
        if it.lang != "en":  # a Russian record is restated through the signed pair list
            pool |= _GLOSSARY_WORDS | _RU_NAMES_EN
        for word in re.findall(r"[a-z]{4,}", _outside_quotes(it.assumption).lower()):
            if word not in _FRAME_WORDS and not _known(word, pool):
                bad.append((it.probe_id, it.family, word, it.assumption))
    assert not bad, bad[:15]


_CURRENCY = re.compile(
    r"\$|\b(dollars?|bucks?|rubles?)\b|рубл|(?<![а-яё])руб(?![а-яё])|бакс|доллар", re.IGNORECASE
)


def test_currency_words_come_from_the_record(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family.startswith("irr_"):  # an irrelevant item's assumption restates no record
            continue
        if _CURRENCY.search(it.assumption):
            texts = " ".join(line.text for line in [it.target, *it.context])
            assert _CURRENCY.search(texts), (it.probe_id, it.assumption)


_CONTACT_SHAPES = re.compile(
    r"exchanged messages|messaged|sent [^.]*message|messages? (from|to|of)|no contact"
    r"|belongs to|is the person|\bhandle\b|account of",
    re.IGNORECASE,
)


def test_irrelevant_assumptions_are_not_about_contact_or_identity(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family.startswith("irr_"):
            assert not _CONTACT_SHAPES.search(it.assumption), (it.probe_id, it.assumption)


_QUALIFIERS = re.compile(
    r"\b(total|including|incl|tip included|about|around|roughly|at least|at most|plus)\b"
    r"|(?<![а-яё])(примерно|около|минимум|всего)(?![а-яё])",
    re.IGNORECASE,
)


def test_other_value_records_state_the_value_plainly(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family == "con_other_value":
            assert not _QUALIFIERS.search(it.target.text), (it.probe_id, it.target.text)


_RETRACTION = re.compile(
    r"\d|\$|\b(dollars?|bucks?|for real|nah|jk|actually)\b|на самом деле", re.IGNORECASE
)


def test_jokes_are_never_walked_back_by_the_joker(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family == "ovr_joke":
            for line in _after_target(it):
                if line.sender == it.target.sender:
                    assert not _RETRACTION.search(line.text), (it.probe_id, line.text)


_DOUBLED_PARTY = re.compile(r"\b(.{4,60}?) and \1\b")
_DOUBLED_PRONOUN = re.compile(r"\b(u|you|i|me|ты|я|мне|тебе) \w+ \1\b", re.IGNORECASE)
# A slot filled with a value that already carries the article ("took the the Riverside brunch job").
_DOUBLED_WORD = re.compile(r"\b(the|a|an|to|on|in|at|for|of|and|в|на|и|с|у) \1\b", re.IGNORECASE)


def test_no_doubled_parties_or_pronouns(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        assert "the owner and the owner" not in it.assumption, it.probe_id
        assert not _DOUBLED_PARTY.search(it.assumption), (it.probe_id, it.assumption)
        assert not _DOUBLED_WORD.search(it.assumption), (it.probe_id, it.assumption)
        for line in [it.target, *it.context]:
            assert not _DOUBLED_PRONOUN.search(line.text), (it.probe_id, line.text)
            assert not _DOUBLED_WORD.search(line.text), (it.probe_id, line.text)


# ------------------------------------------------------------- supports records: verb, no slang

_VERB_FAMILIES = {
    "sup_plain",
    "sup_time_window",
    "sup_contact",
    "sup_account_shared",
    "sup_injection",
}
_SLANG = re.compile("|".join(SLANG_FORMS))


def test_supports_records_carry_a_past_verb(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family in _VERB_FAMILIES:
            assert has_past_verb(it.target.text), (it.probe_id, it.family, it.target.text)


def test_supports_records_avoid_slang_pairs(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.gold_stance != "supports":
            continue
        texts = [it.target.text]
        if it.family == "sup_answer" and it.target_index > 0:  # the question carries the verb
            texts.append(it.context[it.target_index - 1].text)
        for text in texts:
            assert not _SLANG.search(text.lower()), (it.probe_id, it.family, text)


# --------------------------------------------------------- group chats: attribution; filler

_ATTRIBUTION = re.compile(r"(?:wrote|said) in the group chat")
_EXCLUSIVE = re.compile(r"was the one who|the group member who|\bonly\b", re.IGNORECASE)


def test_speaker_mismatch_assumptions_attribute_the_words(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """The family's point is who wrote it, so the assumption names the writer (rule 12 allows
    attribution), and never claims that no one else wrote it: two members can both offer to
    drive, so the record leaves the assumption open (rule 23)."""
    for it in test_items + dev_items:
        if it.family == "ovr_speaker_mismatch":
            assert _ATTRIBUTION.search(it.assumption), (it.probe_id, it.assumption)
            assert not _EXCLUSIVE.search(_outside_quotes(it.assumption)), it.probe_id


def _names(phrase: str, sender: str) -> bool:
    """Whether an assumption's account phrase names the account of this line's sender."""
    if sender.endswith("(owner)"):
        return phrase == "the owner"
    app, ident, label = _SENDER.match(sender).groups()
    if ident.startswith("+1"):
        ident = f"+1 {ident[2:5]}-{ident[5:8]}-{ident[8:]}"
    return ident in phrase or bool(label and label in phrase)


_NOT_FROM = re.compile(r"not from (.+?)(?:;|, as the group)")


def test_mismatch_accounts_are_on_screen(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 11: the account the assumption names has a line in the excerpt."""
    for it in test_items + dev_items:
        if it.family not in ("ovr_sender_mismatch", "ovr_speaker_mismatch"):
            continue
        m = _NOT_FROM.search(_outside_quotes(it.rationale))
        assert m, (it.probe_id, it.rationale)
        named = m.group(1)
        assert any(_names(named, line.sender) for line in it.context), (it.probe_id, named)
        assert not _names(named, it.target.sender), (it.probe_id, named)


def test_fillers_by_core_senders_are_small_talk(monkeypatch: pytest.MonkeyPatch) -> None:
    """A filler by someone who sends a core line is small talk, never a situation line that
    could sit in tension with what the record says."""
    origin: dict[str, bool] = {}  # filler text -> drawn from the small-talk pool
    draw = scene.Chat.filler

    def spy(
        self: scene.Chat,
        rng,
        neutral: bool = False,
        used: set[str] | None = None,
        calm: bool = False,
        settled: bool = False,
    ) -> str:
        track = used if used is not None else set()
        before = set(track)
        text = draw(self, rng, neutral, track, calm, settled)
        small = NEUTRAL_RU if self.lang == "ru" else NEUTRAL_EN + NEUTRAL_MIXED
        drawn = track - before  # the base line the draw added, before casual spelling and typos
        origin[text] = drawn.pop() in small if drawn else bool(neutral)
        return text

    monkeypatch.setattr(scene.Chat, "filler", spy)
    for it in generate("test") + generate("dev"):
        lines = [it.target, *it.context]
        core = {ln.sender for ln in lines if ln.text not in origin}
        for ln in lines:
            if ln.text in origin and not origin[ln.text]:
                assert ln.sender not in core, (it.probe_id, ln.sender, ln.text)


def test_record_senders_never_say_they_are_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """No filler line of the record's own sender puts them elsewhere or on the way ("on my
    way", "in a meeting"), which could sit beside a record that says where they are."""
    base_of: dict[str, str] = {}  # filler text -> the pool line it was drawn from
    draw = scene.Chat.filler

    def spy(
        self: scene.Chat,
        rng,
        neutral: bool = False,
        used: set[str] | None = None,
        calm: bool = False,
        settled: bool = False,
    ) -> str:
        track = used if used is not None else set()
        before = set(track)
        text = draw(self, rng, neutral, track, calm, settled)
        drawn = track - before
        if drawn:
            base_of[text] = drawn.pop()
        return text

    monkeypatch.setattr(scene.Chat, "filler", spy)
    for it in generate("test") + generate("dev"):
        for ln in it.context:
            if ln.sender == it.target.sender and ln.text in base_of:
                assert base_of[ln.text] not in AWAY, (it.probe_id, ln.text, it.target.text)


_BARE_DENIAL = re.compile(r"^\s*(no|nope|nah|нет|неа)\s*,|,\s*(no|nope|нет)\W*$", re.IGNORECASE)
_ASKS = re.compile(r"\?|^(did|do|does|are|is|was|were|can|could|will|would|u|you)\b", re.IGNORECASE)


def test_bare_denials_show_their_question(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A record that opens (or ends) on a bare "no" denies something; the question it answers,
    from another sender, is on screen before it."""
    for it in test_items + dev_items:
        if not _BARE_DENIAL.search(it.target.text):
            continue
        before = it.context[: it.target_index]
        asked = [ln for ln in before if ln.sender != it.target.sender and _ASKS.search(ln.text)]
        assert asked, (it.probe_id, it.family, it.target.text)


# Verbs whose past form is their base form: with no subject, "set up 40 chairs" reads as an
# instruction as easily as a report.
_SAME_PAST = {"put", "cut", "set", "let", "hit", "read", "quit", "shut", "spread"}
_OPENERS = set("ok okay ya yeah yes yep no nope just already finally also then so lol k".split())


def test_supports_records_never_read_as_instructions(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.gold_stance != "supports":
            continue
        for clause in re.split(r"[,.;:!?]", it.target.text.lower()):
            words = re.findall(r"[a-z']+", clause)
            while words and words[0] in _OPENERS:
                words.pop(0)
            assert not (words and words[0] in _SAME_PAST), (it.probe_id, it.target.text)


# ------------------------------------------------- rationales and records under guide v0.3

_WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _record_weekday(it: GenItem) -> str:
    return datetime.strptime(it.target.local_time[:10], "%Y-%m-%d").strftime("%A")


def test_rationale_weekdays_match_the_record_date(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 24: a weekday a rationale names in its own words is the record's local weekday;
    a weekday inside a quoted phrase is the record's or the context's own word."""
    for it in test_items + dev_items:
        own = _outside_quotes(it.rationale)
        for day in _WEEKDAY_NAMES:
            if re.search(rf"\b{day}\b", own, re.IGNORECASE):
                assert day == _record_weekday(it), (it.probe_id, it.family, it.rationale)


_DECLARED = re.compile(
    r"plain denial|cannot be true at the same time|\b(jokes?|joking|kidding|venting|harmless)\b",
    re.IGNORECASE,
)


def test_rationales_say_what_is_uncertain_instead_of_declaring_it(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 24: a denial conflicts in what it says, never as a fact; a joke marker leaves
    sincerity open; a slang reading is open because its translation is not settled."""
    for it in test_items + dev_items:
        own = _outside_quotes(it.rationale)
        assert not _DECLARED.search(own), (it.probe_id, it.family, it.rationale)
        if it.family in ("con_denial", "ovr_negation"):
            assert "cannot be true together" in own or "rules the assumption out" in own, (
                it.probe_id
            )
        if it.family == "con_denial":
            assert "whether the denial is true" in own or "not whether it is true" in own
        if it.family == "ovr_joke":
            assert "unclear whether" in own and "seriously" in own, it.probe_id
        if it.family == "ovr_translation":
            assert "the assumption reads it as" in own and "do not settle" in own, it.probe_id


_JOKE_RETRACTION = re.compile(
    r"\b(jk|j/k|kidding|for real|actually|seriously)\b|шучу|на самом деле|серьёзно", re.IGNORECASE
)


def test_joke_records_are_not_retracted_in_the_record(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A record that takes its own joke back ("jk its in the truck") settles what the sender
    meant; a joke item leaves it open, so the record carries only the marker."""
    for it in test_items + dev_items:
        if it.family == "ovr_joke":
            assert not _JOKE_RETRACTION.search(it.target.text), (it.probe_id, it.target.text)


def test_contradicting_records_need_no_slang(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 23: a contradiction needs nothing unstated, a slang reading included."""
    for it in test_items + dev_items:
        if it.gold_stance == "contradicts":
            assert not _SLANG.search(it.target.text.lower()), (it.probe_id, it.target.text)


_STILL = re.compile(r"\b(?:still|remained|had not yet left)\b")


def test_state_assumptions_hold_on_the_record_date(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 23: con_other_state claims the incompatible state on the record's own local date
    (weekday and date), never a span the record does not speak to."""
    for it in test_items + dev_items:
        if it.family != "con_other_state":
            continue
        day = datetime.strptime(it.target.local_time[:10], "%Y-%m-%d")
        stamp = f"{day.strftime('%A')}, {day.strftime('%B')} {day.day}, {day.year}"
        assert stamp in it.assumption, (it.probe_id, stamp, it.assumption)
        assert _STILL.search(it.assumption), (it.probe_id, it.assumption)
        assert stamp in it.rationale, (it.probe_id, it.rationale)


def test_mismatch_traps_leave_the_assumption_open(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 23: one record cannot show that no other matching message exists."""
    for it in test_items + dev_items:
        if it.family in ("ovr_time_mismatch", "ovr_sender_mismatch", "ovr_speaker_mismatch"):
            assert "does not show whether" in it.rationale, (it.probe_id, it.rationale)


_DENIAL_WORDS = re.compile(
    r"\b(no|not|never|nope|didnt|wasnt|nothing|nobody|lie)\b|n't"
    r"|(?<![а-яё])(не|нет|ни)(?![а-яё])",
    re.IGNORECASE,
)


def test_denial_quotes_carry_the_denial(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 22: the quote of a denial or a negation holds the denying words themselves."""
    for it in test_items + dev_items:
        if it.family in ("con_denial", "ovr_negation"):
            assert _DENIAL_WORDS.search(it.proposed_quote), (it.probe_id, it.proposed_quote)


def test_contacts_are_not_named_in_the_record(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A record from the contact saved as Nico that says "it went to Nico like always" reads as
    self-reference, so no contact on screen carries the name of a person the record talks
    about. The shared-account families name the account's usual user on purpose."""
    for it in test_items + dev_items:
        if it.family in ("sup_account_shared", "ovr_shared_account"):
            continue
        for line in [it.target, *it.context]:
            label = _SENDER.match(line.sender).group(3)
            if not label or label.endswith("(owner)"):
                continue
            first = re.split(r"[^\w]+", label.lstrip("@"))[0]
            assert not names_in(first, it.target.text), (it.probe_id, label, it.target.text)


# ------------------------------------------- rule 23: values pin the same thing and occasion

_NEGATED = re.compile(
    r"(?:\bnot\b|(?<![а-яё])не(?![а-яё]))\s+(?:за\s+|во?\s+)?([^,.]+)", re.IGNORECASE
)
_RU_DAYS = {
    "понедельник": "monday",
    "вторник": "tuesday",
    "сред": "wednesday",
    "четверг": "thursday",
    "пятниц": "friday",
    "суббот": "saturday",
    "воскресень": "sunday",
}
_SAME_DAY = re.compile(
    r"\b(today|tonight|last night|yesterday)\b|сегодня|вчера|прошлой ночью", re.IGNORECASE
)
_DAY_WORDS = {"today": 0, "tonight": 0, "сегодня": 0}  # the rest name the day before


def _days_in(text: str) -> set[str]:
    low = text.lower()
    days = {d for d in WEEKDAYS_EN if re.search(rf"\b{d}\b", low)}
    return days | {en for stem, en in _RU_DAYS.items() if stem in low}


def _negates_the_assumed_value(record: str, assumption: str) -> bool:
    """Whether the record itself rules out the very value the assumption gives: "..., not 15",
    "не в среду", or "nowhere else" on the day the assumption names."""
    low = assumption.lower()
    numbers = set(re.findall(r"\d+", assumption))
    if re.search(r"\bnowhere else\b", record, re.IGNORECASE):
        if _days_in(record) & _days_in(assumption):
            return True
    for m in _NEGATED.finditer(record):
        phrase = m.group(1).strip().lower()
        got = set(re.findall(r"\d+", phrase))
        if got:
            if got <= numbers:
                return True
            continue
        days = _days_in(phrase)
        if days:
            if days & _days_in(assumption):
                return True
            continue
        if phrase and phrase in low:
            return True
    return False


def _pins_the_day(it: GenItem) -> bool:
    """The other way to pin the occasion: the assumption carries the local date the record's
    "today" or "last night" names, and the record is sent by day, where rule 17 cannot apply."""
    m = _SAME_DAY.search(it.target.text)
    sent = datetime.strptime(it.target.local_time[:19], "%Y-%m-%d %H:%M:%S")
    if not m or not 7 <= sent.hour <= 22:
        return False
    back = _DAY_WORDS.get(m.group(0).lower(), 1)
    day = (sent - timedelta(days=back)).date()
    return f"{day.strftime('%B')} {day.day}, {day.year}" in it.assumption


def test_values_and_corrections_pin_the_same_thing_and_occasion(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 23: "sold 32 jars, exactly" leaves room for another sale of 30. A value record
    negates the assumption's value for the same named thing, or both pin the same day."""
    for it in test_items + dev_items:
        if it.family not in ("con_other_value", "con_correction"):
            continue
        pinned = _negates_the_assumed_value(it.target.text, it.assumption) or _pins_the_day(it)
        assert pinned, (it.probe_id, it.family, it.target.text, it.assumption)


_RELATIVE_DAY = re.compile(
    r"\b(today|tonight|yesterday|last night|this morning)\b|сегодня|вчера|ночью|за ночь",
    re.IGNORECASE,
)


def test_relative_days_in_contradicting_records_are_sent_by_day(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 17: a relative day in a contradicting record, or in the question or original
    statement it answers, is read at a send time between 7 a.m. and 11 p.m. local, and an
    original and its correction share one local date."""
    for it in test_items + dev_items:
        if it.gold_stance != "contradicts":
            continue
        texts = [it.target.text]
        if it.family == "con_denial":
            texts.append(it.context[it.target_index - 1].text)
        if it.family == "con_correction":
            original, _ = _correction(it)
            texts.append(original)
            line = next(ln for ln in it.context if ln.text == original)
            assert line.local_time[:10] == it.target.local_time[:10], it.probe_id
        if any(_RELATIVE_DAY.search(t) for t in texts):
            assert 7 <= int(it.target.local_time[11:13]) <= 22, (it.probe_id, it.target)


_FULL_DATE = re.compile(
    r"(?:(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), )?"
    r"((?:January|February|March|April|May|June|July|August|September|October|November"
    r"|December) \d{1,2}, \d{4})"
)


def test_denied_acts_are_dated_before_the_message(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 23: an undated past-tense denial covers the act at any time before it was sent and
    leaves a later act open, so the assumption dates the act before the message ("Before
    April 1, 2025, ..."). A weekday the record or its question names is that weekday's own
    date in the week before the message (rule 24)."""
    for it in _plain(test_items + dev_items):
        if it.family not in ("con_denial", "ovr_negation"):
            continue
        sent = date.fromisoformat(it.target.local_time[:10])
        found = list(_FULL_DATE.finditer(it.assumption))
        assert found, (it.probe_id, it.assumption)
        for m in found:
            day = datetime.strptime(m.group(2), "%B %d, %Y").date()
            assert m.group(1) in (None, day.strftime("%A")), (it.probe_id, it.assumption)
            if it.assumption[: m.start()].endswith("Before "):
                assert day <= sent, (it.probe_id, it.assumption)
            else:
                assert day < sent, (it.probe_id, it.assumption)
        texts = [it.target.text]
        if it.family == "con_denial":
            texts.append(it.context[it.target_index - 1].text)
        for name in set().union(*(_days_in(t) for t in texts)):
            want = sent - timedelta(days=(sent.weekday() - WEEKDAYS_EN.index(name)) % 7 or 7)
            stamp = f"{want.strftime('%A')}, {want.strftime('%B')} {want.day}, {want.year}"
            assert stamp in it.assumption, (it.probe_id, stamp, it.assumption)


# An answer's element whose tense or time the record leaves open ("done, back at 6").
_OPEN_ELEMENT = re.compile(
    r"\bback at\b|\b(?:until|till|by) (?:\d|\{t\})|\bsold out\b|\bwas sold\b|\bfinished by\b"
)
_PAST_CLOCK = re.compile(r"\bat (\d{1,2})(?::(\d\d))?(?![\d:])|\bthe (\d{1,2})(?::(\d\d))? run\b")


def test_answers_leave_open_elements_out_and_come_after_their_clock(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A sup_answer fact keeps no second element whose tense or time the record leaves open,
    in any answer template, and a past event at a clock time ("both, at 8") is answered at
    least an hour after its latest daytime reading (1 to 6:30 as p.m., 7 to 12 as morning)."""
    for t in QA:
        assert not _OPEN_ELEMENT.search(t.that or t.vp), t.text
    for it in _plain(test_items + dev_items):
        if it.family != "sup_answer":
            continue
        own = _outside_quotes(it.assumption)
        assert not _OPEN_ELEMENT.search(own), (it.probe_id, it.assumption)
        if "set for" in own:  # a schedule, not a past event
            continue
        sent = datetime.strptime(it.target.local_time[:16], "%Y-%m-%d %H:%M")
        for m in _PAST_CLOCK.finditer(own):
            hour = int(m.group(1) or m.group(3))
            minute = int(m.group(2) or m.group(4) or 0)
            latest = (hour + 12 if 1 <= hour <= 6 else hour) * 60 + minute
            assert sent.hour * 60 + sent.minute >= latest + 60, (it.probe_id, it.target)


def test_shared_account_facts_claim_no_typist(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A shared account's fact calls whoever typed it "the writer", never the account's user
    or the sender, so the assumption claims nothing about who typed."""
    for it in _plain(test_items + dev_items):
        if it.family == "sup_account_shared":
            own = _outside_quotes(it.assumption)
            assert not re.search(r"account's user|\bthe sender\b", own), it.assumption


def test_count_generalizations_name_no_period(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """ "That month" can end before the occasion an ovr_count record speaks of, or start after
    it; the generalization names no period of its own."""
    for it in _plain(test_items + dev_items):
        if it.family == "ovr_count":
            assert not re.search(r"\bthat (?:week|weekend|month|year)\b", it.assumption), (
                it.probe_id,
                it.assumption,
            )


_SECOND_HAND = re.compile(
    r"\b(?:says|heard|told me|according to)\b"
    r"|(?<![а-яё])(?:говорит|слышал|слышала|по словам)(?![а-яё])",
    re.IGNORECASE,
)


def test_hearsay_carries_its_marker_and_states_are_the_senders_own(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Rule 18: a cpl_hearsay record passes on what the sender heard and says so ("says",
    "heard", "told me", "according to"); a con_other_state record about a third person is the
    sender's own claim, with no such marker."""
    for t in HEARSAY:
        assert _SECOND_HAND.search(t.text), t.text
    for it in _plain(test_items + dev_items):
        if it.family == "cpl_hearsay":
            assert _SECOND_HAND.search(it.target.text), (it.probe_id, it.target.text)
        if it.family == "con_other_state":
            assert not _SECOND_HAND.search(it.target.text), (it.probe_id, it.target.text)


# ================================================================== Baker's own wording (bk_*)
#
# These items follow the plain ones in each split. Their checks re-derive every fact from the
# item itself: times from the lines' local clock and zone, windows from the document's words,
# calls from the call text, and brackets from the sender lines.

_PLAIN_SHA = {  # the plain part of each split (eval.heldout 1.3.0): no bk_* change moves it
    "test": "992b7c924a5abc5f6c0847efe52815434ac0324e1fae11cc112fc648585c7407",
    "dev": "13cc45af73f8b3105c5323d91d1927440b6c277a9646b580496808fe7edf24bd",
}
_ABBR_HOURS = {"EST": -5, "EDT": -4, "CST": -6, "CDT": -5, "MST": -7, "MDT": -6, "PST": -8,
               "PDT": -7}  # fmt: skip
_BK_SENDER = re.compile(
    r"^(SMS|WhatsApp|Telegram|Signal|Instagram|Phone) (\S+)( \(owner\))?(?: \[([^\]]+)\])?$"
)
_CALL = re.compile(
    r"^(incoming|outgoing) call from (\+1\d{10}) to (\+1\d{10}) at "
    r"(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d\d):(\d\d) (AM|PM)\(UTC([+-]\d+)\), (\d+)s$"
)


def _bk(items: list[GenItem]) -> list[GenItem]:
    return [it for it in items if it.family.startswith("bk_")]


def _in_order(it: GenItem) -> list:
    lines = list(it.context)
    lines.insert(it.target_index, it.target)
    return lines


def _item_no(it: GenItem) -> int:
    return int((it.device_id or "").removeprefix("dev:item"))


def _utc(line) -> datetime:  # noqa: ANN001
    """The UTC instant of a line, from its local clock reading and zone abbreviation."""
    local = datetime.strptime(line.local_time[:19], "%Y-%m-%d %H:%M:%S")
    return (local - timedelta(hours=_ABBR_HOURS[line.local_time[20:]])).replace(tzinfo=UTC)


def _phone_tz(it: GenItem) -> str:
    return ZONE_OF[it.target.local_time[20:]]


def _who(it: GenItem) -> dict[str, str]:
    """Each name the item prints in brackets -> the person id it stands for. Lines read by
    name (core/audit/readable.py), and no two people of an item read alike."""
    people = it.baker_names or {}
    names = case_names(people)
    who = {names.person(pid): pid for pid in people}
    assert len(who) == len(people), it.probe_id
    return who


def _sender(line, who: dict[str, str]) -> tuple[str, str, bool, tuple[str, ...]]:  # noqa: ANN001
    """(app, identifier, owner?, the person ids its brackets name) of a sender line."""
    m = _BK_SENDER.match(line.sender)
    assert m, line.sender
    labels = m.group(4).split(", ") if m.group(4) else []
    assert labels == sorted(set(labels)), line.sender  # printed in order, once each
    return m.group(1), m.group(2), bool(m.group(3)), tuple(who[x] for x in labels)


def _call(line) -> dict[str, object] | None:  # noqa: ANN001
    m = _CALL.match(line.text)
    if not m:
        return None
    mo, d, y, hh, mi, ss = (int(m.group(i)) for i in (4, 5, 6, 7, 8, 9))
    hh = hh % 12 + (12 if m.group(10) == "PM" else 0)
    printed = datetime(y, mo, d, hh, mi, ss) - timedelta(hours=int(m.group(11)))
    return {"direction": m.group(1), "frm": m.group(2), "to": m.group(3),
            "utc": printed.replace(tzinfo=UTC), "dur": int(m.group(12))}  # fmt: skip


def _acct(aid: str) -> tuple[int, str, str]:
    _, item, app, ident = aid.split(":", 3)
    return int(item.removeprefix("item")), app, ident


def test_bk_composition_follows_the_plain_items(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for items, scale in ((test_items, 1), (dev_items, 2)):
        bk = _bk(items)
        fam = _by_family(bk)
        assert fam == {f: n // scale for f, n in BK_COMPOSITION.items()}
        assert sum(fam.values()) == 696 // scale  # 24 per family, 48 unrelated (test split)
        first = len(items) - len(bk)
        assert first == TOTAL // scale
        assert not _bk(items[:first]), "Baker-wording items come after every plain item"
        for it in bk:
            assert it.generator == BK_GENERATOR and it.device_id and it.baker_template


@pytest.mark.parametrize("split", ["test", "dev"])
def test_bk_items_leave_the_plain_bytes_alone(split: str, tmp_path: Path) -> None:
    digest = write_jsonl(plain_items(split), tmp_path / f"{split}.jsonl")
    assert digest == _PLAIN_SHA[split]


def test_bk_sender_lines_follow_the_bracket_rule(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """One rule for every line: "(owner)" marks the record phone's own accounts, whose brackets
    carry its stipulated owner; an account reads the same on every line; own accounts on number
    apps share one number, so a number's brackets do not depend on the app."""
    for it in _bk(test_items + dev_items):
        p, who = _item_no(it), _who(it)
        own = f"person:dev:item{p}:owner"
        seen: dict[tuple[str, str], str] = {}
        by_number: dict[str, tuple[str, ...]] = {}
        for line in _in_order(it):
            if line.sender == "contact list":
                assert len(it.context) == 0 and line.local_time == "no time in source"
                assert line.account_id.startswith(f"acct:item{p}:Phone:+1"), it.probe_id
                continue
            app, ident, owner, persons = _sender(line, who)
            assert line.account_id == f"acct:item{p}:{app}:{ident}", (it.probe_id, line)
            assert owner == (own in persons), (it.probe_id, line.sender)
            for person in persons:
                assert re.fullmatch(r"person:(dev:item[1-9]:owner|[a-z][a-z0-9_]*)", person)
            assert seen.setdefault((app, ident), line.sender) == line.sender, it.probe_id
            if app in ("SMS", "WhatsApp", "Signal", "Phone"):
                key = (*sorted(persons), "(owner)" if owner else "")
                assert by_number.setdefault(ident, key) == key, (it.probe_id, ident)


def test_bk_names_and_numbers_follow_the_pools(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    handles = {h.lstrip("@") for _, *pair in bk_names.HANDLE_PAIRS for h in pair}
    latin = [
        *bk_names.SLUGS,
        *bk_names.ROLE_SLUGS,
        *bk_names.FIRSTS,
        *bk_names.WITHHELD.values(),
        *bk_names.RU_LATIN.values(),
        *(n for pair in bk_names.OWNERS for n in pair),
    ]
    for name in latin:
        assert "N" <= name[0].upper() <= "Z", name
    for _, sur, first in bk_names.RU_PEOPLE:
        assert "М" <= sur[0] <= "Я" and "М" <= first[0] <= "Я", sur
    for first in (*bk_names.RU_FIRSTS, *bk_names.RU_LATIN):
        assert "М" <= first[0] <= "Я", first
    for it in _bk(test_items + dev_items):
        params, who = it.baker_params or {}, _who(it)
        persons = list(params.get("person_ids", []))
        for line in _in_order(it):
            if line.sender != "contact list":
                persons += _sender(line, who)[3]
        assert set(persons) == set(it.baker_names or {}), it.probe_id
        for person in persons:
            slug = person.removeprefix("person:")
            assert slug.startswith("dev:item") or "n" <= slug[0] <= "z", (it.probe_id, person)
        for name in (it.baker_names or {}).values():  # first name and surname, N to Z
            assert re.fullmatch(r"[N-Z][a-z]+ [N-Z][a-z]+", name), (it.probe_id, name)
        for aid in [line.account_id for line in _in_order(it)] + params.get("account_ids", []):
            _, app, ident = _acct(aid)
            if app == "Telegram":
                assert re.fullmatch(r"[89]\d{6}", ident), (it.probe_id, ident)
            elif app == "Instagram":
                assert ident in bk_names.NEUTRAL_IG or ident in handles, (it.probe_id, ident)
            else:
                m = re.fullmatch(r"\+1(\d{3})555(01\d{2})", ident)
                assert m and m.group(1) in AREA_CODES, (it.probe_id, ident)


def _cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яё]", text.lower()))


def test_bk_russian_records_are_about_one_in_ten(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for items in (test_items, dev_items):
        worded = [
            it
            for it in _bk(items)
            if it.target.sender != "contact list"
            and not _call(it.target)
            and not re.fullmatch(r"\S+\.\w{3,4}", it.target.text)
        ]
        langs = Counter(it.lang for it in worded)
        assert 0.07 <= (langs["ru"] + langs["mixed"]) / len(worded) <= 0.15, langs
        assert langs["mixed"] >= 1, langs
    for it in _bk(test_items + dev_items):
        assert _cyrillic(it.target.text) == (it.lang != "en"), (it.probe_id, it.target.text)
        if it.lang == "mixed":
            assert any(not _cyrillic(line.text) for line in it.context), it.probe_id
        if it.lang == "en":
            assert not any(_cyrillic(line.text) for line in it.context), it.probe_id


# Past-tense forms that mark the speaker's or the listener's gender, which no item decides: a
# man's "понял" from an account an item ties to a woman would hint who typed it ("клиент
# видел?" speaks of a third person and may stay).
_GENDERED_RU = re.compile(
    r"(?<![а-яё])(?:понял|принял|выручил|надел|помыл|заточил|забрал|оставил|сменил"
    r"|нашёл|нашел)а?(?![а-яё])|(?<![а-яё])(?:развела|нашла|загрузила|размяла|упаковала"
    r"|поставила|заказала|пересадила|обработала)(?![а-яё])"
)


def test_bk_russian_lines_never_mark_gender(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in _bk(test_items + dev_items):
        for line in [it.target, *it.context]:
            assert not _GENDERED_RU.search(line.text.lower()), (it.probe_id, line.text)


def test_bk_record_texts_never_repeat(test_items: list[GenItem], dev_items: list[GenItem]) -> None:
    """No family repeats a record, and no Baker-wording record repeats anywhere in the
    held-out set, dev split included."""
    records = [normalized(it.target.text) for it in _bk(test_items + dev_items)]
    assert len(set(records)) == len(records)
    plain = {normalized(it.target.text) for it in _plain(test_items + dev_items)}
    assert not plain & set(records)


_WORDS_QUOTED = {"bk_sender_shown", "bk_sender_other", "bk_time_inside", "bk_weekday_next",
                 "bk_weekday_open", "bk_weekday_wrong", "bk_weekday_after"}  # fmt: skip
_CUE_QUOTED = {"bk_identity_named", "bk_handles_said", "bk_author_cue"}
_CLAUSE_QUOTED = {"bk_meaning_said", "bk_meaning_other", "bk_claim_denied", "bk_claim_open"}


def test_bk_quotes_follow_the_quote_rules(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """The quoted words when the template quotes words; the cue for identity, authorship and
    handles; for an explanation, a denial or a record bearing on an act or role, the clause the
    answer rests on (guide rule 7): the whole record, or the record less a tail after a comma
    or a lead-in that adds nothing; otherwise the record's whole text (its time, sender,
    numbers or length decide, or it is the claimed message itself)."""
    clauses = Counter()
    for it in _bk(test_items + dev_items):
        quoted = (it.baker_params or {}).get("quoted_text")
        rec, quote = it.target.text, it.proposed_quote
        assert verify_quote(quote, rec), it.probe_id
        words = it.family in _WORDS_QUOTED or (
            it.family in ("bk_time_outside", "bk_zone_edge", "bk_party_unshown", "bk_claim_open")
            and quoted is not None
            and it.baker_template != "contact_entry"
        )
        if words:
            assert quote == quoted, it.probe_id
        elif it.family in _CUE_QUOTED:  # the cue span; its content is checked per family
            assert len(quote.split()) >= 2, it.probe_id
        elif it.family in _CLAUSE_QUOTED:
            tail = rec.startswith(quote + ", ") or rec == f"to be clear {quote}"
            assert rec == quote or tail or rec.endswith(f", {quote}"), (it.probe_id, quote)
            clauses[it.family, rec == quote] += 1
        else:
            assert quote == rec, it.probe_id
    for family_id in _CLAUSE_QUOTED:  # some records are all deciding text, some are not
        assert clauses[family_id, True] and clauses[family_id, False], (family_id, clauses)


# ------------------------------------------------------------------ bk windows, read from words

_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December")  # fmt: skip
_DATE = r"([A-Z][a-z]+) (\d{1,2}), (\d{4})"
_ONE_DAY = timedelta(days=1)


def _date(month: str, day: str, year: str) -> datetime:
    return datetime(int(year), _MONTHS.index(month) + 1, int(day))


def _hour(word: str) -> int:
    if word == "noon":
        return 12
    m = re.fullmatch(r"(\d{1,2}) (a\.m\.|p\.m\.)", word)
    assert m, word
    return int(m.group(1)) % 12 + (12 if m.group(2) == "p.m." else 0)


def _readings(raw: str) -> tuple[list[tuple[datetime, datetime]], datetime | None]:
    """Every reading of a window's words as wall-clock [start, end), and the clock time of an
    "at about" window. Open ends are far outside any record."""
    far_past, far_future = datetime(2000, 1, 1), datetime(2100, 1, 1)
    if m := re.fullmatch(rf"[Oo]n {_DATE}", raw):
        d = _date(*m.groups())
        return [(d, d + _ONE_DAY)], None
    if m := re.fullmatch(rf"([A-Z][a-z]+day), {_DATE}", raw):
        d = _date(*m.groups()[1:])
        assert d.strftime("%A") == m.group(1), raw
        return [(d, d + _ONE_DAY)], None
    if m := re.fullmatch(rf"from ([A-Z][a-z]+) (\d{{1,2}})(?:, (\d{{4}}))? through {_DATE}", raw):
        last = _date(*m.groups()[3:])
        first = _date(m.group(1), m.group(2), m.group(3) or str(last.year))
        assert first < last, raw
        return [(first, last + _ONE_DAY)], None
    if m := re.fullmatch(rf"before {_DATE}", raw):
        d = _date(*m.groups())
        return [(far_past, d), (far_past, d + _ONE_DAY)], None
    if m := re.fullmatch(rf"after {_DATE}", raw):
        d = _date(*m.groups())
        return [(d + _ONE_DAY, far_future), (d, far_future)], None
    if m := re.fullmatch(rf"between (.+?) and (.+?) on {_DATE}", raw):
        d = _date(*m.groups()[2:])
        start, end = d + timedelta(hours=_hour(m.group(1))), d + timedelta(hours=_hour(m.group(2)))
        assert start < end, raw
        return [(start, end)], None
    if m := re.fullmatch(rf"at about (.+?) on {_DATE}", raw):
        # Baker reads "at about 9 p.m." as 8:52 to 9:08 (core/audit/assumption_filler.py), and
        # only before "a.m." or "p.m.", so never "at about noon".
        assert m.group(1) != "noon", raw
        at = _date(*m.groups()[1:]) + timedelta(hours=_hour(m.group(1)))
        return [(at - timedelta(minutes=8), at + timedelta(minutes=8))], at
    raise AssertionError(f"unexpected window words: {raw!r}")


def _wall(wall: datetime, tz: str) -> datetime:
    return wall.replace(tzinfo=ZoneInfo(tz)).astimezone(UTC)


def _inside_by(utc: datetime, readings: list, tz: str) -> timedelta:
    """How far inside every reading, read in tz, the instant is (negative: outside one)."""
    return min(min(utc - _wall(s, tz), _wall(e, tz) - utc) for s, e in readings)


def _outside_by(utc: datetime, readings: list, tz: str) -> timedelta:
    """How far outside every reading, read in tz, the instant is (negative: inside one)."""
    return min(max(_wall(s, tz) - utc, utc - _wall(e, tz)) for s, e in readings)


def _window_of(it: GenItem) -> tuple[list, datetime | None, str] | None:
    w = (it.baker_params or {}).get("window")
    if w is None:
        return None
    readings, about = _readings(w["raw"])
    start, end = readings[0]
    stated_start = datetime.fromisoformat(w["start_utc"])
    stated_end = datetime.fromisoformat(w["end_utc"]) + timedelta(microseconds=1)
    if not w["raw"].startswith("before"):
        assert stated_start == _wall(start, w["tz"]), (it.probe_id, w)
    if not w["raw"].startswith("after"):
        assert stated_end == _wall(end, w["tz"]), (it.probe_id, w)
    return readings, about, w["tz"]


_INSIDE = {"bk_time_inside", "bk_call_inside", "bk_call_length", "bk_count_one",
           "bk_no_contact_inside", "bk_other_phone", "bk_party_unshown", "bk_claim_open",
           "bk_event_is_record"}  # fmt: skip


def test_bk_windows_match_their_words_and_records_keep_their_margins(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Plainly inside: an hour from every edge under every reading, in the named zone and on
    the phone's clock ("at about": within five minutes, same zone). Plainly outside: a day (dates)
    or two hours (clock times) beyond every edge in both zones. A zone edge: inside in one zone
    and outside in the other, by ten minutes or more."""
    seen = Counter()
    for it in _bk(test_items + dev_items):
        found = _window_of(it)
        if found is None or it.family in ("bk_unrelated",) or it.family.startswith("bk_weekday"):
            continue
        readings, about, tz = found
        utc, phone = _utc(it.target), _phone_tz(it)
        zones = {tz, phone}
        if it.family in _INSIDE:
            if about is not None:
                assert tz == phone and abs(utc - _wall(about, tz)) <= timedelta(minutes=5)
            else:
                assert all(_inside_by(utc, readings, z) >= timedelta(hours=1) for z in zones)
            seen["inside"] += 1
        elif it.family in ("bk_time_outside", "bk_outside_window"):
            need = timedelta(hours=2) if re.match(r"between|at about", _raw(it)) else _ONE_DAY
            assert all(_outside_by(utc, readings, z) >= need for z in zones), it.probe_id
            if it.family == "bk_outside_window" and not _call(it.target):
                for line in it.context:  # no message between the parties falls inside
                    assert all(_outside_by(_utc(line), readings, z) > timedelta(0) for z in zones)
            seen["outside"] += 1
        elif it.family == "bk_zone_edge":
            assert tz != phone, it.probe_id
            named, own = _inside_by(utc, readings, tz), _inside_by(utc, readings, phone)
            margin = timedelta(minutes=10)
            assert (named >= margin and own <= -margin) or (own >= margin and named <= -margin)
            seen["named" if named > own else "phone"] += 1
    assert min(seen.values()) >= 12 and len(seen) == 4, seen


def _raw(it: GenItem) -> str:
    return (it.baker_params or {})["window"]["raw"]


# ------------------------------------------------------------------ bk calls, rows, weekdays


def test_bk_calls_read_from_their_text(test_items: list[GenItem], dev_items: list[GenItem]) -> None:
    """A call's printed time is its line's instant; its line shows the calling number; the
    assumption names that side by the person in its brackets and the other side by its Phone
    account, the call text's other number; a stated length holds the call with a tenth to
    spare, or (bk_call_length) misses it by half the minimum or twice the maximum."""
    checked = Counter()
    for it in _bk(test_items + dev_items):
        who = _who(it)
        for line in _in_order(it):
            call = _call(line)
            if call is not None:
                app, ident, _, _ = _sender(line, who)
                assert call["utc"] == _utc(line), (it.probe_id, line.text)
                assert app == "Phone" and ident == call["frm"] != call["to"], it.probe_id
        call = _call(it.target)
        if call is None or it.family in ("bk_unrelated", "bk_party_unshown"):
            continue
        params = it.baker_params or {}
        assert params["person_ids"][0] in _sender(it.target, who)[3], it.probe_id
        assert len(params["person_ids"]) == 1 and len(params["account_ids"]) == 1, it.probe_id
        _, app, ident = _acct(params["account_ids"][0])
        assert app == "Phone" and ident == call["to"], it.probe_id
        span, dur = params.get("duration_s"), int(call["dur"])  # type: ignore[call-overload]
        if it.family == "bk_call_length":
            assert dur < span[0] / 2 or dur > 2 * span[1], it.probe_id
        elif span:
            assert span[0] <= 0.9 * dur and span[1] >= 1.1 * dur, it.probe_id
        checked[it.family] += 1
    assert checked["bk_call_inside"] == 36 and checked["bk_call_length"] == 36, checked
    assert checked["bk_event_is_record"] == 12, checked


def test_bk_contact_rows_sit_on_the_named_phone(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in _bk(test_items + dev_items):
        if it.target.sender != "contact list":
            continue
        params = it.baker_params or {}
        name, number = it.target.text.rsplit(" ", 1)
        if it.baker_template != "contact_entry":
            assert it.family == "bk_unrelated" and it.baker_template in ("role", "event")
            continue
        assert params["device_ids"] == [it.device_id], it.probe_id
        item, app, ident = _acct(params["account_ids"][0])
        assert (item, app) == (_item_no(it), "Phone"), it.probe_id
        same = (name == params["quoted_text"], number == ident)
        if it.family == "bk_contact_row":
            assert same == (True, True), it.probe_id
        elif it.family == "bk_contact_row_differs":
            assert sum(same) == 1, it.probe_id
        else:
            assert same == (False, False), it.probe_id
            assert not set(name.split()) & set(params["quoted_text"].split()), it.probe_id


_DAYS_RU = ("понедельник", "вторник", "сред", "четверг", "пятниц", "суббот", "воскресен")


def _planned(text: str) -> tuple[int, str]:
    """The one weekday a plan names (Monday 0) and the word before it: "", "next" or "this"."""
    low = text.lower()
    found = []
    for d, day in enumerate(WEEKDAYS_EN):
        for m in re.finditer(rf"\b(?:(next|this) )?{day}\b", low):
            found.append((d, m.group(1) or ""))
    for d, stem in enumerate(_DAYS_RU):
        for m in re.finditer(rf"(?<![а-яё])в(?:о)? (?:(следующ|эт)\w* )?{stem}", low):
            found.append((d, {"следующ": "next", "эт": "this"}.get(m.group(1) or "", "")))
    assert len(found) == 1, text
    return found[0]


def test_bk_weekday_items_relate_the_dates(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """next: a bare weekday, the date's, sent one to six days before it. open: the weekday the
    record was sent on (the date that day or a week on, sent before 10 a.m.), or "next"/"this"
    with the date one of its readings. wrong: another weekday than the date's. after: the
    date's weekday, sent after the date (complicates, rule 23)."""
    for it in _bk(test_items + dev_items):
        if not it.family.startswith("bk_weekday"):
            continue
        w = (it.baker_params or {})["window"]
        readings, _ = _readings(w["raw"])
        target = readings[0][0].date()
        assert readings[0][1] - readings[0][0] == _ONE_DAY and w["tz"] == _phone_tz(it)
        sent = datetime.strptime(it.target.local_time[:10], "%Y-%m-%d").date()
        day, mod = _planned(it.target.text)
        delta = (target - sent).days
        upcoming = (day - sent.weekday() - 1) % 7 + 1
        if it.family == "bk_weekday_next":
            assert mod == "" and day == target.weekday() and 1 <= delta <= 6, it.probe_id
        elif it.family == "bk_weekday_open":
            if mod == "":
                assert day == sent.weekday() and delta in (0, 7), it.probe_id
                # Sent before 10 a.m., so a time the plan names ("at 7") can be that day's.
                assert int(it.target.local_time[11:13]) <= 9, it.probe_id
            else:
                assert day == target.weekday() and delta in (upcoming, upcoming + 7), it.probe_id
                # "this" is plain for a later day of the same Monday-to-Saturday week.
                assert mod == "next" or not sent.weekday() < day <= 5, it.probe_id
        elif it.family == "bk_weekday_wrong":
            assert mod == "" and day != target.weekday(), it.probe_id
        else:
            assert it.family == "bk_weekday_after" and it.gold_stance == "complicates"
            assert mod == "" and day == target.weekday() and -6 <= delta <= -1, it.probe_id


# ------------------------------------------------------------------ bk parties on screen


def _on_line(it: GenItem, line, party: list[str]) -> bool:  # noqa: ANN001
    """Whether a line of the item shows a party: a person in its brackets, or one of the
    party's account ids as its sender or as a number in its call text."""
    if line.sender == "contact list":
        return False
    app, ident, _, persons = _sender(line, _who(it))
    call = _call(line)
    for name in party:
        if name.startswith("person:") and name in persons:
            return True
        if name.startswith("acct:"):
            _, a, i = _acct(name)
            if (a, i) == (app, ident) or (call and a == "Phone" and i in (call["frm"], call["to"])):
                return True
    return False


def _parties(it: GenItem) -> list[list[str]]:
    params = it.baker_params or {}
    out = [[p] for p in params.get("person_ids", [])]
    if params.get("account_ids"):
        out.append(list(params["account_ids"]))
    return out


def _chat_accounts(it: GenItem) -> set[str]:
    return {line.account_id for line in _in_order(it)}


_BOTH_SHOWN = {"bk_no_contact_inside", "bk_count_one", "bk_other_phone", "bk_outside_window",
               "bk_event_is_record"}  # fmt: skip
_CLAIMED = {"bk_claim_open", "bk_claim_denied"}


def test_bk_named_parties_are_shown_as_each_family_needs(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in _bk(test_items + dev_items):
        f, rec, parties, lines = it.family, it.target, _parties(it), _in_order(it)
        if f == "bk_sender_shown" or (f == "bk_time_inside" and parties):
            assert len(parties) == 1 and _on_line(it, rec, parties[0]), it.probe_id
        elif f == "bk_time_inside":
            assert "(anyone)" in it.assumption, it.probe_id
        elif f == "bk_sender_other":
            assert not _on_line(it, rec, parties[0]), it.probe_id
            assert any(_on_line(it, line, parties[0]) for line in it.context), it.probe_id
        elif f == "bk_party_unshown":
            named = [p for p in (it.baker_params or {})["person_ids"] if "dev:item" not in p]
            assert named and not any(_on_line(it, ln, named) for ln in lines), it.probe_id
        elif f in _BOTH_SHOWN:
            assert len(parties) == 2, it.probe_id
            if _call(rec):
                assert all(_on_line(it, rec, party) for party in parties), it.probe_id
            else:  # a one-to-one chat: the record's sender and the one other account
                assert len(_chat_accounts(it)) == 2, it.probe_id
                assert all(any(_on_line(it, ln, party) for ln in lines) for party in parties)
                assert any(_on_line(it, rec, party) for party in parties), it.probe_id
        elif f in ("bk_identity_named", "bk_account_silent", "bk_author_cue"):
            assert len(parties) == 2 and _on_line(it, rec, parties[1]), it.probe_id
            persons = _sender(rec, _who(it))[3]
            assert persons == (() if f != "bk_author_cue" else persons), it.probe_id
            assert all(p not in persons or "dev:item" in p for p in parties[0]), it.probe_id
        elif f in _CLAIMED and it.baker_template != "meaning":
            # one chat with the claim's person, bracketed on the record (from them) or on the
            # other side's lines (to them); the other person the claim names has no account
            person, *other = (it.baker_params or {})["person_ids"]
            assert len(_chat_accounts(it)) == 2 and len(other) <= 1, it.probe_id
            assert any(_on_line(it, ln, [person]) for ln in lines), it.probe_id
            assert f == "bk_claim_open" or _on_line(it, rec, [person]), it.probe_id
            assert not any(_on_line(it, ln, other) for ln in lines), it.probe_id


def test_bk_counts_and_phones_leave_the_answer_open(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A count is above the messages on screen; bk_other_phone names another phone than the
    record's; bk_no_contact_inside covers the record's phone."""
    for it in _bk(test_items + dev_items):
        params = it.baker_params or {}
        if it.baker_template == "message_count" and it.family != "bk_unrelated":
            assert len(_in_order(it)) < params["expected_count"], it.probe_id
        if it.family == "bk_other_phone":
            assert params["device_ids"] != [it.device_id], it.probe_id
        elif it.baker_template in ("message_count", "no_contact") and it.family != "bk_unrelated":
            assert params.get("device_ids", [it.device_id]) == [it.device_id], it.probe_id
        if it.baker_template == "no_contact" and params.get("channels"):
            assert params["channels"] == [_sender(it.target, _who(it))[0]], it.probe_id


# ------------------------------------------------------------------ bk cues and unrelated records

_RU_SURNAMES = {lat: sur for lat, sur, _ in bk_names.RU_PEOPLE}
_ALL_NAMES = {n.lower() for n in (*bk_names.FIRSTS, *bk_names.RU_FIRSTS)} | {
    s for s in (*bk_names.SLUGS, *bk_names.ROLE_SLUGS) if not s.startswith("name_")
}


def test_bk_cues_carry_what_their_family_turns_on(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Identity: the cue gives the named person's surname. Handles: the cue names both
    handles. Silent accounts: the record names nobody."""
    for it in _bk(test_items + dev_items):
        params = it.baker_params or {}
        quote = it.proposed_quote.lower()
        if it.family == "bk_identity_named":
            slug = params["person_ids"][0].removeprefix("person:")
            assert slug in quote or _RU_SURNAMES.get(slug, "#").lower() in quote, it.probe_id
        elif it.family == "bk_handles_said":
            assert params["channels"][0] in ("Instagram", "Telegram"), it.probe_id
            assert all(h.lstrip("@").lower() in quote for h in params["handles"]), it.probe_id
        elif it.family == "bk_account_silent":
            words = set(re.findall(r"[a-zа-яё]+", it.target.text.lower()))
            assert not words & _ALL_NAMES, (it.probe_id, it.target.text)


def test_bk_unrelated_records_hold_none_of_the_matter(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """The record holds none of the quoted words or handles, is not a call or message between
    the named parties, is not from a named account, and is not a row with the name or number."""
    shapes = Counter()
    for it in _bk(test_items + dev_items):
        if it.family != "bk_unrelated":
            continue
        params, rec = it.baker_params or {}, it.target
        text = normalized(rec.text)
        shapes[_call(rec) is not None, rec.sender == "contact list", it.baker_template] += 1
        if params.get("quoted_text"):
            assert normalized(params["quoted_text"]) not in text, it.probe_id
            assert not any(normalized(params["quoted_text"]) in normalized(ln.text)
                           for ln in it.context), it.probe_id  # fmt: skip
        for handle in params.get("handles", []):
            assert handle.lstrip("@").lower() not in rec.text.lower() + rec.sender.lower()
        named = ("no_contact", "message_count", "person_identity")
        if it.baker_template in named or params.get("channels") == ["call"]:
            accounts = [p for party in _parties(it) for p in party if p.startswith("acct:")]
            assert not any(_on_line(it, ln, accounts) for ln in _in_order(it)), it.probe_id
            assert accounts, it.probe_id
        if it.baker_template in ("role", "event"):
            assert rec.sender == "contact list", it.probe_id
    assert len(shapes) >= 10, shapes


# ------------------------------------------------------------------ bk claims (guide rule 29)

_CLAIM_TEMPLATES = {"meaning", "role", "event"}
_MEANT = re.compile(
    r'(?:.+ used "(?P<w1>.+)" to mean|When .+ wrote "(?P<w2>.+)", .+ meant) (?P<m>.+)\.'
)
_NOT = r"(?:not|never|nothing to do with)"


def test_bk_claims_show_with_their_templates(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """A meaning, role or event item shows the claim, and nothing else does. The claim quotes
    the words (meaning) or names its person by surname (role, event), and carries no ids."""
    shown = Counter()
    for it in _bk(test_items + dev_items):
        claim, params = it.baker_claim, it.baker_params or {}
        if it.baker_template not in _CLAIM_TEMPLATES:
            assert claim is None, it.probe_id
            continue
        assert claim and claim[0].isupper() and claim[-1] in '."', it.probe_id
        if it.baker_template == "meaning":
            assert f'"{params["quoted_text"]}"' in claim, it.probe_id
        else:
            surname = (it.baker_names or {})[params["person_ids"][0]].split()[-1]
            assert surname in claim, (it.probe_id, claim)
        shown[it.family] += 1
    for family_id in ("bk_claim_open", "bk_meaning_said", "bk_meaning_other",
                      "bk_event_is_record", "bk_claim_denied"):  # fmt: skip
        assert shown[family_id] == 36, shown
    assert shown["bk_unrelated"] > 0, shown


def test_bk_ids_and_users_names_never_show_in_texts(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """Names replace ids in what a model reads, and no line's text names a phone's stipulated
    user: only the case names them."""
    for it in _bk(test_items + dev_items):
        lines = _in_order(it)
        texts = [it.assumption, it.rationale, it.baker_claim or "", *(ln.sender for ln in lines)]
        assert not any(i in t for t in texts for i in ("person:", "acct:", "dev:")), it.probe_id
        words = {w for ln in lines for w in re.findall(r"[a-z]+", ln.text.lower())}
        for pid, name in (it.baker_names or {}).items():
            if pid.endswith(":owner"):
                assert not set(name.lower().split()) & words, (it.probe_id, name)


def test_bk_meaning_records_follow_their_family(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """bk_claim_open: the record uses or asks about the words, and no line says what they mean
    or uses them before. bk_meaning_said and bk_meaning_other: the account that used the words
    on an earlier line explains them in the record, as the claim's meaning (said) or as the
    plain thing they name (other), of another kind than the claim's meaning and never naming
    it; neither denies anything, and the quote holds the explanation. The claim names the
    words' user."""
    plain_of = {words: plain for _, words, plain in bk_meanings.PHRASES}
    seen = Counter()
    for it in _bk(test_items + dev_items):
        if it.baker_template != "meaning" or it.family == "bk_unrelated":
            continue
        m = _MEANT.fullmatch(it.baker_claim or "")
        assert m, it.probe_id
        raw_words, raw_meaning = m["w1"] or m["w2"], m["m"]
        words, meaning = normalized(raw_words), normalized(raw_meaning)
        rec, rest = normalized(it.target.text), [normalized(ln.text) for ln in it.context]
        quote = normalized(it.proposed_quote)
        assert words == normalized((it.baker_params or {})["quoted_text"]) and words in rec
        if it.family == "bk_claim_open":
            assert not any(words in t or meaning in t for t in rest) and meaning not in rec
        else:
            earlier = it.context[: it.target_index]
            sender = it.target.sender
            assert any(words in normalized(ln.text) and ln.sender == sender for ln in earlier)
            label = sender.split(" [", 1)[1].rstrip("]")
            assert label.split(" (")[0].split()[-1] in (it.baker_claim or ""), it.probe_id
            assert words in quote and not re.search(rf"\b{_NOT}\b", rec), it.probe_id
            if it.family == "bk_meaning_said":
                assert meaning in quote, it.probe_id
            else:
                assert normalized(plain_of[raw_words]) in quote, it.probe_id
                assert meaning not in rec and not bk_meanings.clash(raw_words, raw_meaning)
        seen[it.family] += 1
    assert seen == {"bk_claim_open": 12, "bk_meaning_said": 36, "bk_meaning_other": 36}, seen


def _dial(number: str) -> str:
    return f"({number[2:5]}) {number[5:8]}-{number[8:]}"


def test_bk_event_records_are_the_claimed_message_or_call(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """bk_event_is_record: the claim opens with the window's words and quotes the record's
    text word for word (a message) or dials the call's other number (a call), and it names
    each person of the assumption."""
    for it in _bk(test_items + dev_items):
        if it.family != "bk_event_is_record":
            continue
        claim, rec = it.baker_claim or "", it.target
        assert claim.lower().removeprefix("sometime ").startswith(_raw(it).lower())
        call = _call(rec)
        if call is None:
            assert f'"{rec.text}"' in claim and it.proposed_quote == rec.text, it.probe_id
        else:
            assert " called " in claim and _dial(str(call["to"])) in claim, it.probe_id
        for person in (it.baker_params or {})["person_ids"]:
            assert (it.baker_names or {})[person].split()[-1] in claim, it.probe_id


_TEXTED = re.compile(r"\b(" + "|".join(m.lower() for m in _MONTHS) + r") (\d{1,2})\b")
_SPAN = re.compile(r"From (.+?) through ([A-Z][a-z]+ \d{1,2}, \d{4}), ")


def _texted_day(month: str, day: str, near: date) -> date:
    """A date a chat writes without a year ('march 3'), in the year that puts it nearest."""
    days = []
    for year in (near.year - 1, near.year, near.year + 1):
        with contextlib.suppress(ValueError):  # february 29
            days.append(date(year, _MONTHS.index(month.capitalize()) + 1, int(day)))
    return min(days, key=lambda d: abs(d - near))


def test_bk_denials_come_after_the_claim_and_cover_it(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """bk_claim_denied: sent a day or more after the claim's time (a role's span opens its
    claim), the record rules the act or role out for all time before it ("never", no dates)
    or for dates that hold every day of the claim's window."""
    covers = Counter()
    for it in _bk(test_items + dev_items):
        if it.family != "bk_claim_denied":
            continue
        utc, text = _utc(it.target), it.target.text.lower()
        if it.baker_template == "event":
            readings, _, tz = _window_of(it) or ([], None, "")
            assert not _raw(it).startswith("after"), it.probe_id
        else:
            m = _SPAN.match(it.baker_claim or "")
            assert m, it.probe_id
            readings, _ = _readings(f"from {m.group(1)} through {m.group(2)}")
            tz = _phone_tz(it)
        for z in {tz, _phone_tz(it)}:
            assert _outside_by(utc, readings, z) >= _ONE_DAY, it.probe_id
            assert utc > _wall(readings[0][1], z), it.probe_id
        start, end = readings[0]
        named = [_texted_day(mo, d, start.date()) for mo, d in _TEXTED.findall(text)]
        if not named:
            assert re.search(r"\b(never|ever)\b", text), it.probe_id
            covers["never"] += 1
            continue
        assert len(named) in (1, 2), it.probe_id
        last_day = (end - timedelta(microseconds=1)).date()
        assert named[0] <= start.date() and named[-1] >= last_day, (it.probe_id, text)
        covers["dates"] += 1
    assert covers["never"] >= 12 and covers["dates"] >= 6, covers


# The short forms a chat may call a first name by (eval/heldout/bk_fam_sender.py, _SHORT).
_SHORT_FORMS = {"philippa": "pippa", "rosalind": "ros", "thaddeus": "thad", "xander": "xan",
                "quincy": "quin", "tamar": "tam"}  # fmt: skip


def test_bk_unshown_parties_are_called_by_name_in_a_third(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    """bk_party_unshown: in a third of the items the owner, answering the record, calls the
    unbracketed account by a word of the named person's name or a short form of it. The person
    still shows in no bracket (see the parties test), so the answer stays open (rule 26)."""
    for items, want in ((test_items, 8), (dev_items, 4)):
        called = 0
        for it in _bk(items):
            if it.family != "bk_party_unshown":
                continue
            lines, who = _in_order(it), _who(it)
            person = next(p for p in (it.baker_params or {})["person_ids"] if "dev:" not in p)
            name = (it.baker_names or {})[person].lower().split()
            forms = {*name, _SHORT_FORMS.get(name[0], name[0])}
            hits = [ln for ln in lines if forms & set(re.findall(r"[a-z]+", ln.text.lower()))]
            if not hits:
                continue
            called += 1
            assert hits == [lines[-1]] and it.target_index == len(lines) - 2, it.probe_id
            assert _sender(lines[-1], who)[2] and not _sender(it.target, who)[2], it.probe_id
        assert called == want, (want, called)
