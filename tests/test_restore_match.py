"""Context Restore matching: folding, cores, search and verification. All text is invented."""

from __future__ import annotations

import random

import pytest

from core.contracts import MatchMethod, SourceRef
from core.restore.fold import differences, fold, has_cyrillic
from core.restore.match import MAX_MATCHES, Body, Found, Index, cores, find, omitted, verify


def _index(*texts: str) -> Index:
    return Index(
        Body(f"msg:s:{i}", SourceRef(source_id="s", locator=f"Chats!{i}"), t)
        for i, t in enumerate(texts, start=1)
    )


def _found(excerpt: str, *texts: str) -> list[tuple[str, MatchMethod, list[str]]]:
    idx = _index(*texts)
    out = find(excerpt, idx)
    return [
        (f.record_id, f.method, [idx.body_text(f.record_id)[a:b] for a, b in f.spans])
        for f in out.found
    ]


# ---------------------------------------------------------------- folding


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("The Package", "the package"),
        ("the   package\nwill be", "the package will be"),
        ("it’s “done”", 'it\'s "done"'),
        ("a — b", "a - b"),
        ("wait…", "wait..."),
        ("zero​width", "zerowidth"),
        ("ещё", "еще"),
        ("ёж", "ёж"),  # combining diaeresis folds with its base letter
        ("ﬁne", "fine"),  # NFKC ligature
    ],
)
def test_tolerant_fold_equates(a: str, b: str) -> None:
    assert fold(a).text == fold(b).text


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("its done", "it's done"),  # punctuation still has to agree
        ("need 2 more", "need two more"),
        ("move it tonight", "move it tomorrow"),
        ("й", "и"),  # a breve is a different letter, not a mark to drop
    ],
)
def test_tolerant_fold_keeps_differences(a: str, b: str) -> None:
    assert fold(a).text != fold(b).text


@pytest.mark.parametrize(
    ("cyr", "lat"),
    [
        ("Привет, Саша", "privet, sasha"),
        ("Мария", "Maria"),
        ("Мария", "Mariya"),
        ("Фёдор", "Fyodor"),
        ("Дмитрий", "Dmitry"),
        ("Катя", "Katya"),
        ("Михаил", "Mikhail"),
        ("Михаил", "Mihail"),
    ],
)
def test_transliteration_fold_equates(cyr: str, lat: str) -> None:
    assert fold(cyr, "transliteration").text == fold(lat, "transliteration").text


def test_fold_maps_back_to_original_spans() -> None:
    text = "  Hello,\n\n  “World”  "
    f = fold(text)
    assert f.text == 'hello, "world"'
    a, b = f.span(0, len(f.text))
    assert text[a:b] == "Hello,\n\n  “World”"
    i = f.text.index("world")
    a, b = f.span(i, i + 5)
    assert text[a:b] == "World"


def test_transliteration_spans_map_back() -> None:
    text = "ну, Михаил приедет"
    f = fold(text, "transliteration")
    i = f.text.index("mihail")
    a, b = f.span(i, i + len("mihail"))
    assert text[a:b] == "Михаил"


def test_differences_names_what_was_set_aside() -> None:
    assert differences("The  Package", "the package", "tolerant") == [
        "spacing or line breaks",
        "letter case",
    ]
    assert differences("it’s", "it's", "tolerant") == ["quote, apostrophe or dash style"]
    assert differences("same", "same", "tolerant") == []
    assert "Cyrillic and Latin spelling" in differences("privet", "привет", "transliteration")


# ---------------------------------------------------------------- cores


def test_cores_set_labels_quotes_and_closing_marks_aside() -> None:
    ex = '3/12/2026 4:15 PM PETROV: "need 2 more by friday."'
    got = [ex[a:b] for a, b in cores(ex)]
    assert got[0] == ex
    assert "need 2 more by friday." in got
    assert got[-1] == "need 2 more by friday"


def test_label_stripped_core_needs_two_words() -> None:
    ex = "[3/12/26 16:15] PETROV: ok"
    assert "ok" not in [ex[a:b] for a, b in cores(ex)]
    assert _found(ex, "ok", "ok sure") == []


# ---------------------------------------------------------------- search


def test_exact_match() -> None:
    got = _found("need 2 more by friday", "hello", "need 2 more by friday")
    assert got == [("msg:s:2", MatchMethod.EXACT, ["need 2 more by friday"])]


def test_exact_partial_quote_is_word_aligned() -> None:
    assert _found("package", "the packages are here") == []
    got = _found("its done", "bits done", "ok its done now")
    assert got == [("msg:s:2", MatchMethod.EXACT, ["its done"])]


def test_tolerant_match_maps_to_original_text() -> None:
    body = "The package   will be\nat Marc’s"
    got = _found("the package will be at marc's", body)
    assert got == [("msg:s:1", MatchMethod.TOLERANT, [body])]


def test_label_and_quotes_in_exhibit() -> None:
    got = _found('3/12/2026 8:11 PM @northstar: "The package will be at Marcs."',
                 "the package will be at marcs")  # fmt: skip
    assert got == [("msg:s:1", MatchMethod.TOLERANT, ["the package will be at marcs"])]


def test_transliteration_needs_cyrillic_on_one_side() -> None:
    got = _found("mama peredaet privet", "мама передаёт привет")
    assert got == [("msg:s:1", MatchMethod.TRANSLITERATION, ["мама передаёт привет"])]
    # Both sides Latin: the variant folds ("ia" as "ya") never make a match on their own.
    assert _found("Maria called", "Marya called") == []


def test_exact_beats_tolerant_and_stops_the_search() -> None:
    got = _found("its done", "its done", "Its Done")
    assert got == [("msg:s:1", MatchMethod.EXACT, ["its done"])]


def test_ellipsis_marks_omitted_words() -> None:
    body = "got the money from him, come get it"
    idx = _index(body)
    out = find("got the money … come get it", idx)
    (f,) = out.found
    assert [body[a:b] for a, b in f.spans] == ["got the money", "come get it"]
    assert omitted(body, f.spans) == [" from him, "]


def test_ellipsis_pieces_must_be_in_order_in_one_message() -> None:
    assert _found("come get it ... got the money", "got the money, come get it") == []
    assert _found("got the money ... come get it", "got the money", "come get it") == []


def test_not_found() -> None:
    idx = _index("hello there", "see you at 8")
    out = find("we never talked about this", idx)
    assert out.found == [] and out.total == 0 and out.core is None


def test_every_match_is_listed_up_to_the_cap() -> None:
    texts = ["ok"] * (MAX_MATCHES + 5)
    idx = _index(*texts)
    out = find("ok", idx)
    assert out.total == MAX_MATCHES + 5
    assert len(out.found) == MAX_MATCHES


# ---------------------------------------------------------------- verification


def _f(method: MatchMethod, spans, excerpt_spans) -> Found:  # noqa: ANN001
    return Found("msg:s:1", SourceRef(source_id="s", locator="x"), method, spans, excerpt_spans)


def test_verify_rejects_tampered_matches() -> None:
    body = "the package will be at marcs"
    ex = "package will be"
    good = _f(MatchMethod.EXACT, ((4, 19),), ((0, 15),))
    assert verify(ex, body, good)
    assert not verify(ex, body, _f(MatchMethod.EXACT, ((5, 20),), ((0, 15),)))  # shifted
    assert not verify(ex, body, _f(MatchMethod.EXACT, ((5, 19),), ((1, 15),)))  # mid-word
    assert not verify(ex, body, _f(MatchMethod.EXACT, ((4, 19), (0, 3)), ((0, 7), (8, 15))))
    assert not verify(ex, body, _f(MatchMethod.EXACT, ((4, 99),), ((0, 15),)))  # out of range
    assert not verify("PACKAGE WILL BE", body, _f(MatchMethod.EXACT, ((4, 19),), ((0, 15),)))
    assert verify("PACKAGE WILL BE", body, _f(MatchMethod.TOLERANT, ((4, 19),), ((0, 15),)))
    # transliteration with no Cyrillic on either side is not a transliteration
    assert not verify("Maria", "Marya", _f(MatchMethod.TRANSLITERATION, ((0, 5),), ((0, 5),)))


def test_random_excerpts_of_real_bodies_are_found_and_verified() -> None:
    rng = random.Random(7)  # noqa: S311 - a seeded test sample
    bodies = [
        "Привет! Как дела? Завтра в 8 у гаража",
        "dont text me about it, use telegram",
        "the package will be at marcs",
        "ok see you  at 8\nbring the stuff",
        "мама передаёт привет",
    ]
    idx = _index(*bodies)
    for _ in range(200):
        n = rng.randrange(len(bodies))
        words = bodies[n].split()
        i = rng.randrange(len(words))
        j = rng.randrange(i + 1, len(words) + 1)
        excerpt = " ".join(words[i:j])
        if rng.random() < 0.5:
            excerpt = excerpt.upper()
        out = find(excerpt, idx)
        assert out.found, excerpt
        for f in out.found:
            assert verify(excerpt, bodies[int(f.record_id.rsplit(":", 1)[1]) - 1], f)
        assert f"msg:s:{n + 1}" in {f.record_id for f in out.found} or not any(
            ch.isalnum() for ch in excerpt
        )


def test_has_cyrillic() -> None:
    assert has_cyrillic("ок") and not has_cyrillic("ok")
