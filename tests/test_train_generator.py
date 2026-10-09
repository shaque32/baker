"""The training generator: deterministic, valid items, every family, siblings, names, no leaks."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from eval.stancedata.families import FAMILIES
from eval.stancedata.model import GenItem
from eval.train import generate as gen
from eval.train.names import AREA_CODES

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "eval" / "train"
FIRST_LETTERS = set("ABCDEFGHIJKLM") | set("АБВГДЕЁЖЗИЙКЛ")


@pytest.fixture(scope="module")
def items() -> list[GenItem]:
    return gen.generate(600, 1)


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


def test_every_family_appears(items: list[GenItem]) -> None:
    seen = {it.family for it in items}
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
    assert gen.main(["--n", "25", "--seed", "3", "--out", str(out)]) == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 25
    side = out.with_name("train.jsonl.manifest.json")
    assert side.exists() and '"n": 25' in side.read_text(encoding="utf-8")


def test_every_excerpt_shows_a_non_owner_line(items: list[GenItem]) -> None:
    # Guide rule 11: the probe format has no recipient field, so a non-owner line is on screen.
    for it in items:
        assert any("(owner)" not in ln.sender for ln in it.lines()), it.probe_id


def test_supports_assumptions_report_the_message(items: list[GenItem]) -> None:
    # Guide rule 14: a supports assumption says what the message communicates.
    says = re.compile(r"\b(told|wrote|texted|sent|says|said|states|message|messaged|messages|"
                      r"in contact|confirmed|answer|asked)\b")  # fmt: skip
    for it in items:
        if it.gold_stance == "supports":
            assert says.search(it.assumption), it.assumption


def test_fact_families_state_the_fact(items: list[GenItem]) -> None:
    # Guide rule 12: a correction, a denial or another value contradicts a fact, not a report.
    report = re.compile(r"\b(told|wrote|texted|said|says|states)\b|message (says|states)|"
                        r"sent (the owner|.*message)")  # fmt: skip
    fams = {"ovr_later_correction", "con_other_value", "con_other_state", "con_denial"}
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
        first = it.assumption.split()[0].rstrip(",").lower()
        assert not re.search(rf"\b{first}\b", it.target.text.lower()), it.assumption
        app, ident, *label = it.target.sender.split(" ")
        shown = [" ".join(label).lstrip("@").lower()] if label else []
        if app == "Instagram":
            shown.append(ident.lower())
        for s in shown:
            names = {n for n in pool if re.search(rf"(^|[^a-zа-яё]){n}([^a-zа-яё]|$)", s)}
            assert names <= {first}, (it.assumption, it.target.sender)
