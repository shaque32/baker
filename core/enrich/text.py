"""Text normalization and term extraction for keyword retrieval.

Deterministic and model-free. Matching is a recall aid only: a match never becomes evidence until
a stance label's quote is verified verbatim against the original text.
"""

from __future__ import annotations

import re
import unicodedata

WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*")
PHONE_RE = re.compile(r"(?<![\w])\+?\d[\d\s().-]{5,}\d(?![\w])")
QUOTED_RE = re.compile(r"[\"“]([^\"“”]{2,120})[\"”]|(?<!\w)'([^']{2,120})'(?!\w)")

MIN_ID_DIGITS = 5  # bare digit runs this long are treated as identifiers (user ids, numbers)
MIN_PREFIX_LEN = 4  # terms this long also match as a word prefix ("ticket" -> "tickets")

# Words that carry no search value in an assumption. Kept short and explicit on purpose.
STOPWORDS = frozenset(
    """
    a about above after again all also am an and any are as at be been before being between both
    but by can could did do does doing during each every for from further had has have having he
    her here hers him his how i if in into is it its itself just me more most my no nor not of off
    on once only or other our out over own same she should so some such than that the their them
    then there these they this those through to too under until up very was we were what when
    where which while who whom why will with would you your
    item items phone device message messages call calls account accounts user id contact contacts
    sent received exchanged recorded shows show appears appear entry list local time utc
    january february march april may june july august september october november december
    jan feb mar apr jun jul aug sep sept oct nov dec
    """.split()
)


def normalize(text: str) -> str:
    """Casefold, NFKC, and fold ё to е, so Russian and English compare plainly."""
    t = unicodedata.normalize("NFKC", text).casefold()
    return t.replace("ё", "е")


def tokens(text: str) -> list[str]:
    return WORD_RE.findall(normalize(text))


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def term_matches(term: str, toks: list[str], norm_text: str) -> bool:
    """A word matches a token (or a token prefix, if long enough); a phrase, a substring."""
    if " " in term:
        return term in norm_text
    if len(term) >= MIN_PREFIX_LEN:
        return any(t.startswith(term) for t in toks)
    return term in toks


def quoted(text: str) -> list[str]:
    """Strings in double quotes, or in single quotes that are not apostrophes, as written."""
    return _unique([(a or b).strip() for a, b in QUOTED_RE.findall(text)])


def extract_terms(text: str) -> tuple[list[str], list[str], list[str]]:
    """Split free text into (handles, numbers, keywords).

    handles: '@name' strings as written. numbers: digit strings of phone numbers and bare ids.
    keywords: normalized words and quoted phrases, stopwords removed, in first-seen order.
    """
    handles = _unique(HANDLE_RE.findall(text))
    rest = HANDLE_RE.sub(" ", text)
    numbers = [d for d in (digits(m) for m in PHONE_RE.findall(rest)) if len(d) >= 7]
    rest = PHONE_RE.sub(" ", rest)
    numbers += [m for m in re.findall(r"\d+", rest) if len(m) >= MIN_ID_DIGITS]
    phrases = [normalize(a or b).strip() for a, b in QUOTED_RE.findall(rest)]
    words = [re.sub(r"['’]s$", "", w) for w in tokens(rest)]
    words = [w for w in words if len(w) >= 3 and w not in STOPWORDS and not w.isdigit()]
    keywords = [p for p in phrases if " " in p] + words
    return handles, _unique(numbers), _unique(keywords)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
