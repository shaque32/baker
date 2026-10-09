"""The held-out stance set generator: fixed output, fixed composition, clean sources."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from eval.heldout import GENERATOR, ID_PREFIX, SEEDS, SOURCE
from eval.heldout.generate import generate
from eval.heldout.pools import AREA_CODES, CYRILLIC_FULL
from eval.heldout.schedule import COMPOSITION, FOUR_TRAPS
from eval.heldout.text import normalized
from eval.stancedata.families import family
from eval.stancedata.model import GenItem

PACKAGE = Path(__file__).resolve().parent.parent / "eval" / "heldout"

# The test split, exactly; the dev split is half of every number.
BLOCKS = {
    "clear_support": 200, "contradicts": 300, "complicates": 120, "irrelevant": 80,
}  # fmt: skip
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
