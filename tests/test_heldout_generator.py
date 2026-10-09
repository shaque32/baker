"""The held-out stance set generator: fixed output, fixed composition, clean sources."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from eval.heldout import GENERATOR, ID_PREFIX, SEEDS, SOURCE
from eval.heldout.generate import generate
from eval.heldout.glossary import RU_EN_PAIRS
from eval.heldout.pools import AREA_CODES, CYRILLIC_FULL, MENTIONED_RU, PLACES, WEEKDAYS_EN
from eval.heldout.schedule import COMPOSITION, FOUR_TRAPS
from eval.heldout.text import normalized
from eval.stancedata.families import family
from eval.stancedata.model import GenItem

PACKAGE = Path(__file__).resolve().parent.parent / "eval" / "heldout"

# The test split, exactly; the dev split is half of every number.
BLOCKS = {
    "clear_support": 200,
    "contradicts": 300,
    "complicates": 120,
    "irrelevant": 80,
}
MINIMUMS = {"sup_": 15, "con_": 40, "cpl_": 15}
OVERREACH_GATED = 300  # every ovr_* family except ovr_translation
OVERREACH_FOUR_TRAPS = 120
OVERREACH_OTHER_MIN = 12
TRANSLATION = 20
TOTAL = 1020


@pytest.fixture(scope="module")
def test_items() -> list[GenItem]:
    return generate("test")


@pytest.fixture(scope="module")
def dev_items() -> list[GenItem]:
    return generate("dev")


def _dump(items: list[GenItem]) -> list[str]:
    return [it.model_dump_json() for it in items]


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
    assert sum(fam[f] for f in FOUR_TRAPS) >= OVERREACH_FOUR_TRAPS // scale
    for family_id, n in fam.items():
        if family_id.startswith("ovr_") and family_id not in FOUR_TRAPS:
            assert n >= OVERREACH_OTHER_MIN // scale, family_id
    assert fam["ovr_translation"] == TRANSLATION // scale
    assert fam["irr_other_topic"] > 0 and fam["irr_pleasantry"] > 0
    stances = Counter(it.gold_stance for it in items)
    assert stances["contradicts"] >= 420 // scale


def test_generation_is_deterministic(test_items: list[GenItem], dev_items: list[GenItem]) -> None:
    assert _dump(generate("test")) == _dump(test_items)
    assert _dump(generate("dev")) == _dump(dev_items)


def test_test_split_composition(test_items: list[GenItem]) -> None:
    _check_composition(test_items, 1)


def test_dev_split_is_half_with_the_same_shape(dev_items: list[GenItem]) -> None:
    _check_composition(dev_items, 2)


@pytest.mark.parametrize("split", ["test", "dev"])
def test_items_validate_and_ids_run_in_order(split: str, request: pytest.FixtureRequest) -> None:
    items = request.getfixturevalue(f"{split}_items")
    prefix = ID_PREFIX[split]
    for i, it in enumerate(items, start=1):
        GenItem.model_validate(it.model_dump())
        assert it.source == SOURCE
        assert it.generator == GENERATOR
        assert it.probe_id == f"{prefix}{i:06d}"
        assert it.group == it.probe_id
        assert it.rationale.strip()
        assert 1 <= len(it.context) <= 6
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
    for it in test_items:
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
    for app, ident, label in _accounts(test_items + dev_items):
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
    for it in test_items + dev_items:
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


def test_later_corrections_replace_the_same_slot(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        if it.family != "ovr_later_correction":
            continue
        fix = next(line.text for line in _after_target(it) if line.sender == it.target.sender)
        assert _NEGATION.search(fix.lower()), (it.probe_id, fix)
        got = _slot_values(fix)
        kind = next((k for k in ("place", "day", "number") if len(got[k]) >= 2), None)
        assert kind, (it.probe_id, fix)
        had = _slot_values(it.target.text)[kind]
        assert got[kind] & had, (it.probe_id, "the correction repeats the record's value", fix)
        assert got[kind] - had, (it.probe_id, "the correction names a new value", fix)


# Rule 12: assumptions state facts. These families are about a message or a contact pattern
# (verbatim text, timing, sender, contact) or restate what a message communicates (supports).
_REPORT_ALLOWED = {
    "sup_verbatim",
    "sup_contact",
    "sup_account_shared",
    "ovr_sender_mismatch",
    "ovr_time_mismatch",
    "con_in_window",
    "con_other_speaker",
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
        for it in test_items + dev_items
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
    telegram instagram whatsapp signal phone sender between before after during that this with
    from their they there were been being have having into onto over under when while then than
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
    for it in test_items + dev_items:
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
    r"\$|\b(dollars?|bucks?|rubles?)\b|рубл|(?<![а-яё])руб(?![а-яё])|бакс", re.IGNORECASE
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


def test_no_doubled_parties_or_pronouns(
    test_items: list[GenItem], dev_items: list[GenItem]
) -> None:
    for it in test_items + dev_items:
        assert "the owner and the owner" not in it.assumption, it.probe_id
        assert not _DOUBLED_PARTY.search(it.assumption), (it.probe_id, it.assumption)
        for line in [it.target, *it.context]:
            assert not _DOUBLED_PRONOUN.search(line.text), (it.probe_id, line.text)
