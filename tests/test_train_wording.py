"""Wording rules of the training generator's plain items that keep each label plainly right:
an act whose verb could be an instruction carries its subject (guide rule 14), a bare "no" only
answers a question the excerpt shows, and a record that says where its sender is meets no
filler that puts anyone somewhere. SYNTHETIC data only."""

from __future__ import annotations

import random
import re

import pytest

from eval.stancedata.model import GenItem
from eval.train import facts as fx
from eval.train import filler
from eval.train import generate as gen
from eval.train.facts_en_a import FACTS_A
from eval.train.facts_en_b import FACTS_B
from eval.train.facts_en_c import FACTS_C
from eval.train.facts_en_d import FACTS_D
from eval.train.facts_en_e import FACTS_E
from eval.train.facts_en_f import FACTS_F
from eval.train.facts_ru import FACTS_RU
from eval.train.scenario import filler_pools

FACTS_EN = FACTS_A + FACTS_B + FACTS_C + FACTS_D + FACTS_E + FACTS_F
# Words a record may open on before its verb: decorations, "just", "yep", "never", ...
LEAD = {"yo", "hey", "ok", "k", "btw", "so", "wait", "lol", "just", "yep", "nope", "never",
        "probably", "and"}  # fmt: skip
SELF_CORRECTION = re.compile(r"^(?:\w+ )?(?:wait no|no wait)\b")
BARE_NO = re.compile(r"^(?:(?:yo|hey|ok|k|btw|so|wait|lol|ну|кароч|короче|слушай,|блин,|а,)\s+)?"
                     r"(?:no|nope|нет)\b[,.!]?\s|,\s*(?:no|nope|нет)\s*$", re.I)  # fmt: skip
QUESTION = re.compile(r"\?|^(?:\w+ )?(?:so )?did (?:u|you)\b|\bor not$", re.I)


@pytest.fixture(scope="module")
def many() -> list[GenItem]:
    return gen.generate(4000, 1)


def _opens_on_same_past(text: str) -> bool:
    words = re.findall(r"[a-z']+", text.lower())
    i = 0
    while i < len(words) and words[i] in LEAD:
        i += 1
    return i < len(words) and words[i] in fx.SAME_PAST


def test_same_past_acts_carry_a_subject() -> None:
    facts = [f for f in FACTS_EN if f.acted.split(" ", 1)[0] in fx.SAME_PAST]
    assert facts, "the pool has acts like 'put 200 in savings'"
    rng = random.Random(7)  # noqa: S311 - fixed draws, not security
    for f in facts:
        for v in f.values:
            for _ in range(30):
                forms = [
                    fx.stated(f, rng, v),
                    fx.negated(f, rng, v),
                    fx.negated(f, rng, v, never=True),
                    fx.negated(f, rng, v, answer=True),
                    fx.hedged(f, rng, v),
                    fx.exact(f, rng, v) or "",
                ]
                assert not any(_opens_on_same_past(t) for t in forms), (f.key, forms)
                # A yes-or-no question asks whether it was done, never whether to do it.
                assert not _opens_on_same_past(fx.asked(f, rng, v)), f.key


def test_records_report_acts_with_their_subject(many: list[GenItem]) -> None:
    for it in many:
        # A pronoun record is an instruction on purpose: "put it under the bench".
        if it.family in {"ovr_pronoun", "irr_other_topic"}:
            continue
        assert not _opens_on_same_past(it.target.text), (it.probe_id, it.target.text)


def test_a_bare_no_answers_a_question_shown(many: list[GenItem]) -> None:
    seen = 0
    for it in many:
        text = it.target.text.strip()
        if not BARE_NO.search(text) or SELF_CORRECTION.match(text):
            continue
        seen += 1
        before = it.context[: it.target_index]
        asked = any(QUESTION.search(m.text) and m.sender != it.target.sender for m in before)
        assert asked, (it.probe_id, text)
    assert seen, "denials that answer a question keep their 'no'"


def test_negations_drop_a_bare_no_unless_they_answer() -> None:
    rng = random.Random(3)  # noqa: S311 - fixed draws, not security
    for f in FACTS_EN[:40] + FACTS_RU[:20]:
        v = f.values[0]
        for _ in range(20):
            assert not BARE_NO.search(fx.negated(f, rng, v)), f.key
            assert not BARE_NO.search(fx.negated(f, rng, v, never=True)), f.key


def _filled(lines: tuple[str, ...]) -> set[str]:
    """Each line as a chat shows it: Russian past endings filled for either speaker."""
    out = set()
    for t in lines:
        for o in ("", "а"):
            for c in ("", "а"):
                out.add(t.replace("{o}", o).replace("{c}", c))
    return out


def _bare_line(text: str, lang_pools: tuple[tuple[str, ...], tuple[str, ...]]) -> set[str]:
    """The line and the line without one decoration."""
    prefixes, suffixes = lang_pools
    out = {text}
    out |= {text[len(p) :] for p in prefixes if text.startswith(p)}
    out |= {text[: -len(s)] for s in suffixes if text.endswith(s)}
    return out


def test_placed_pools_put_no_one_anywhere() -> None:
    for lang, place in (("en", filler.PLACE_EN), ("ru", filler.PLACE_RU)):
        for safe in (False, True):
            scene_lines, generic = filler_pools(lang, "special", safe, placed=True)
            assert not set(scene_lines + generic) & set(place)
            # Without `placed` the pools are as before.
            assert set(place) & set(filler_pools(lang, "special", False)[1])


def test_records_that_place_their_sender_meet_no_place_filler(many: list[GenItem]) -> None:
    place = _filled(filler.PLACE_EN) | _filled(filler.PLACE_RU)
    decorations = (
        filler.PREFIX_EN + filler.PREFIX_RU,
        filler.SUFFIX_EN + filler.SUFFIX_RU,
    )
    seen = 0
    for it in many:
        if it.family != "con_other_state":
            continue
        seen += 1
        for m in it.context:
            assert not _bare_line(m.text, decorations) & place, (it.probe_id, m.text)
    assert seen
