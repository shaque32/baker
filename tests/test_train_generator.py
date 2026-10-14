"""The training generator: deterministic, valid items, every family, siblings, names, no leaks,
and the template rules of the labeling guide (fact-form assumptions, no gender, no open
references, supports assumptions that add nothing, spread-out templates)."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
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
    "texted messaged message messages sent came from exchanged were contact between before after "
    "morning afternoon evening night states group chat answer question confirmed "
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
# A clock on a date ("by 2 p.m. on March 3, 2026", "at 9:12 a.m. on March 3, 2026"), and a
# bound that is a date alone ("before March 3, 2026": the days before it).
CLOCK_ON = re.compile(rf"\b(?:by|before|at) {CLOCK} on {LONG_DATE.pattern}", re.I)
CLOCK_BOUND = re.compile(rf"\b(?:by|before) {CLOCK} on {LONG_DATE.pattern}", re.I)
BEFORE_DATE = re.compile(rf"\bbefore {LONG_DATE.pattern}", re.I)
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


def test_contradicts_assumptions_end_by_the_record(many: list[GenItem]) -> None:
    # Rule 23: a record rules an act or a place out only up to the moment it was sent ("still in
    # denver" at 12:09 rules out "landed in New York by noon", never "that day"). A contradicts
    # assumption names no later date; one that names the record's date ends by its local clock;
    # denials, negations and any assumption naming a weekday always carry that bound.
    assert CLOCK_ON.findall("By 2 p.m. on March 3, 2026, X had paid") == [
        ("2 p.m.", "March", "3", "2026")]  # fmt: skip
    assert BEFORE_DATE.findall("X landed at noon before March 3, 2026") == [("March", "3", "2026")]
    seen: Counter[str] = Counter()
    for it in many:
        if it.gold_stance != "contradicts" or it.family == "con_in_window":
            continue
        a, lt = it.assumption, it.target.local_time
        day, minute = date.fromisoformat(lt[:10]), int(lt[11:13]) * 60 + int(lt[14:16])
        assert all(_date(*m) <= day for m in LONG_DATE.findall(a)), (a, lt)
        clocks = [(_minute_of(t), _date(*m)) for t, *m in CLOCK_ON.findall(a)]
        assert all(t <= minute for t, d in clocks if d == day), (a, lt)
        if it.family in ("con_other_value", "con_correction"):
            # A value the record gives is bounded at its own minute: by an earlier hour, 4 of
            # "exactly 5" lash sets could already have been done.
            assert all(t == minute for t, d in clocks if d == day), (a, lt)
        # The record's date appears only with a clock at or before the record's, or as the
        # date-only bound "before" it.
        ends = [d for _, d in clocks] + [_date(*m) for m in BEFORE_DATE.findall(a)]
        if day in [_date(*m) for m in LONG_DATE.findall(a)]:
            assert day in ends, (a, lt)
        if it.family in ("con_denial", "ovr_negation") or EN_WEEKDAY.search(a):
            assert ends, (a, lt)
            seen["clock" if clocks else "date"] += 1
    assert seen["clock"] > 100, seen


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
    assert seen["clock"] >= 5, seen


TIME_ON = re.compile(rf"\b(by|before|after|at) {CLOCK} on {LONG_DATE.pattern}", re.I)


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
                ok = {"before": t <= minute, "after": t > minute}.get(word, True)
            else:
                ok = True
            assert ok, (it.family, it.assumption, lt)
            seen[it.gold_stance] += 1
    assert seen["supports"] > 100 and seen["complicates"] > 100, seen


def test_other_state_names_the_place(many: list[GenItem]) -> None:
    # Rule 23: never "home" when nothing shows where home is.
    for it in many:
        if it.family == "con_other_state":
            assert not re.search(r"\bhome\b|\bдома\b|\bдомой\b", it.target.text.lower()), it
