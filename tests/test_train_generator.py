"""The training generator: deterministic, valid items, every family, siblings, names, no leaks,
and the template rules of the labeling guide (fact-form assumptions, no gender, no open
references, supports assumptions that add nothing, spread-out templates)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from eval.stancedata.families import FAMILIES
from eval.stancedata.model import GenItem
from eval.train import generate as gen
from eval.train.glossary import PAIRS, SLANG
from eval.train.names import AREA_CODES
from eval.train.verbs import SUPPORT_VERBS_EN, SUPPORT_VERBS_RU

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "eval" / "train"
FIRST_LETTERS = set("ABCDEFGHIJKLM") | set("АБВГДЕЁЖЗИЙКЛ")


@pytest.fixture(scope="module")
def items() -> list[GenItem]:
    return gen.generate(600, 1)


@pytest.fixture(scope="module")
def many() -> list[GenItem]:
    return gen.generate(4000, 1)


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


# --- assumption wording -------------------------------------------------------------------

QUOTED = re.compile(r'"[^"]*"')
PERSON = set("i i'm im i'll ill my me mine we our us u ur you your yours я мне меня мой моя моё "
             "мои мы нам нас наш ты тебе тебя твой вы вам вас ваш".split())  # fmt: skip
GENDER = set("he she his him her hers он она его её ему ей".split())
OPEN_REFERENCE = re.compile(
    r"\b(it|him|her|them)\b|\bthe (man|woman)\b|\b(last night|the night before|yesterday|tonight|"
    r"tomorrow|tmrw|this weekend|this morning|the next day|вчера|сегодня|завтра)\b"
)
REPORT_OK = {f.family_id for f in FAMILIES if f.stance.value == "supports"} | {
    "ovr_sender_mismatch", "ovr_time_mismatch", "con_in_window", "con_other_speaker"}  # fmt: skip
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
    # local date in the assumption.
    for it in items:
        assert not OPEN_REFERENCE.search(_bare(it.assumption)), it.assumption


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
    "texted messaged message messages sent came from exchanged were contact between before after "
    "morning afternoon evening night read plainly states group chat answer question confirmed "
    "according telegram user shown instagram account saved personally typed usual someone else "
    "noon midnight into than with january february march april may june july august september "
    "october november december".split()
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
