"""The fixed text normalizations Context Restore matches with, each keeping a map back to the
original characters.

Two levels, both deterministic and model-free:
- tolerant: Unicode NFKC; letter case (and ё as е); every run of whitespace or line breaks as
  one space; curly and straight quotes and apostrophes alike; every dash and hyphen alike;
  the ellipsis character as three dots; zero-width characters and emoji variation selectors
  dropped. Nothing else: punctuation, spelling and word order still have to agree.
- transliteration: tolerant, then Cyrillic letters written in Latin by one fixed table, then a
  short list of common spelling variants folded on both sides ("kh" as "h", "ia" as "ya", "iy"
  as "y", ...). Matches at this level count only when one side is written in Cyrillic.

fold() returns the folded text plus, for each folded character, the span of original text it
came from, so a match found in folded text maps back to an exact span of the stored message.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

Level = Literal["tolerant", "transliteration"]

# Characters that change nothing a reader sees: zero-width spaces and joiners, the byte-order
# mark, the word joiner, the soft hyphen and variation selectors (emoji style).
_IGNORABLE = frozenset("​‌‍⁠﻿­" + "".join(chr(c) for c in range(0xFE00, 0xFE10)))
_QUOTE_MAP = {
    **dict.fromkeys("‘’‚‛′`´ʼ", "'"),
    **dict.fromkeys("“”„‟«»″", '"'),
    **dict.fromkeys("‐‑‒–—―−", "-"),
}
_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
}  # fmt: skip
# Spelling variants folded on both sides after transliteration, longest first. "'" is the
# soft sign as some transliterations write it.
_VARIANTS = (
    ("kh", "h"),
    ("ja", "ya"),
    ("ju", "yu"),
    ("jo", "e"),
    ("ia", "ya"),
    ("iu", "yu"),
    ("iy", "y"),
    ("ii", "y"),
    ("yy", "y"),
    ("yo", "e"),
    ("x", "ks"),
    ("'", ""),
)
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")


@dataclass(frozen=True)
class Folded:
    text: str
    starts: tuple[int, ...]  # original start index of each folded character
    ends: tuple[int, ...]  # original end index (exclusive) of each folded character

    def span(self, i: int, j: int) -> tuple[int, int]:
        """The original span behind folded characters i..j (j exclusive, j > i)."""
        return self.starts[i], self.ends[j - 1]


def has_cyrillic(text: str) -> bool:
    return _CYRILLIC_RE.search(text) is not None


def _clusters(text: str) -> list[tuple[int, int]]:
    """A base character with the combining marks after it, so "е" plus a combining diaeresis
    folds as "ё" (then "е"), never as a bare "е" plus a stray mark."""
    out: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        j = i + 1
        while j < len(text) and unicodedata.combining(text[j]):
            j += 1
        out.append((i, j))
        i = j
    return out


def fold(text: str, level: Level = "tolerant") -> Folded:
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for a, b in _clusters(text):
        cluster = "".join(ch for ch in text[a:b] if ch not in _IGNORABLE)
        if not cluster:
            continue
        for ch in unicodedata.normalize("NFKC", cluster).casefold():
            if ch.isspace():
                ch = " "
            ch = _QUOTE_MAP.get(ch, "е" if ch == "ё" else ch)
            pieces = _CYRILLIC.get(ch, ch) if level == "transliteration" else ch
            for out in pieces:
                if out == " " and (not chars or chars[-1] == " "):
                    if chars:
                        ends[-1] = b  # the run of whitespace maps to one space
                    continue
                chars.append(out)
                starts.append(a)
                ends.append(b)
    if chars and chars[-1] == " ":
        chars.pop()
        starts.pop()
        ends.pop()
    if level == "transliteration":
        chars, starts, ends = _fold_variants(chars, starts, ends)
    return Folded("".join(chars), tuple(starts), tuple(ends))


def _fold_variants(
    chars: list[str], starts: list[int], ends: list[int]
) -> tuple[list[str], list[int], list[int]]:
    oc: list[str] = []
    os_: list[int] = []
    oe: list[int] = []
    i = 0
    while i < len(chars):
        for pat, rep in _VARIANTS:
            n = len(pat)
            if "".join(chars[i : i + n]) == pat:
                if rep:
                    for ch in rep:
                        oc.append(ch)
                        os_.append(starts[i])
                        oe.append(ends[i + n - 1])
                elif oe:
                    oe[-1] = ends[i + n - 1]  # a dropped character joins the one before it
                i += n
                break
        else:
            oc.append(chars[i])
            os_.append(starts[i])
            oe.append(ends[i])
            i += 1
    return oc, os_, oe


# ---------------------------------------------------------------- what differed (for display)

_STEPS: tuple[tuple[str, object], ...] = (
    ("spacing or line breaks", lambda s: " ".join(s.split())),
    (
        "quote, apostrophe or dash style",
        lambda s: "".join(_QUOTE_MAP.get(c, c) for c in s if c not in _IGNORABLE),
    ),
    ("Unicode form", lambda s: unicodedata.normalize("NFKC", s)),
    ("letter case", lambda s: s.casefold().replace("ё", "е")),
)


def differences(exhibit_text: str, record_text: str, level: str) -> list[str]:
    """Plain words for what the tolerant normalization had to set aside, step by step, until
    the two texts agreed. Display only; the match itself was decided by fold()."""
    if exhibit_text == record_text:
        return []
    x, y = exhibit_text, record_text
    out: list[str] = []
    for name, step in _STEPS:
        nx, ny = step(x), step(y)  # type: ignore[operator]
        if (nx, ny) != (x, y) and x != y:
            out.append(name)
        x, y = nx, ny
        if x == y:
            break
    if x != y or level == "transliteration":
        out.append("Cyrillic and Latin spelling" if level == "transliteration" else "other")
    return out
