"""Text helpers: slot rendering, Russian number agreement, casual styling, clocks and names."""

from __future__ import annotations

import random
import re
from datetime import date, datetime

from eval.stancedata.chat import Account, long_date, pretty_phone

_SLOT = re.compile(r"\{(\w+)(?::([^}]*))?\}")


def ru_count(n: int, one: str, few: str, many: str) -> str:
    """'3 паллеты', '5 паллет', '21 паллета': the noun form Russian uses after a number."""
    if n % 10 == 1 and n % 100 != 11:
        form = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        form = few
    else:
        form = many
    return f"{n} {form}"


def render(template: str, values: dict[str, object]) -> str:
    """Fill {slot} and {n:one|few|many} placeholders. Unknown slots are left as they are."""

    def sub(m: re.Match[str]) -> str:
        name, forms = m.group(1), m.group(2)
        if name not in values:
            return m.group(0)
        value = values[name]
        if forms is not None:
            one, few, many = forms.split("|")
            return ru_count(int(value), one, few, many)
        return str(value)

    return _SLOT.sub(sub, template)


def slots_used(template: str) -> set[str]:
    return {m.group(1) for m in _SLOT.finditer(template)}


def capitalize_first(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def clock12(local: datetime) -> str:
    """'9:40 p.m.', '12:05 a.m.': the clock reading assumptions use."""
    hour = local.hour % 12 or 12
    suffix = "a.m." if local.hour < 12 else "p.m."
    return f"{hour}:{local.minute:02d} {suffix}"


def clock12_hm(hh: int, mm: int) -> str:
    hour = hh % 12 or 12
    suffix = "a.m." if hh < 12 else "p.m."
    return f"{hour}:{mm:02d} {suffix}"


def date_phrase(day: date) -> str:
    return long_date(day)


def casual(rng: random.Random, text: str, lower_p: float = 0.9) -> str:
    """Mostly lowercase, as people text. Applied to a whole line before any quote is cut."""
    if text != text.lower() and rng.random() < lower_p:
        return text.lower()
    return text


_VOWELS = "aeiou"


def typo(rng: random.Random, text: str, p: float = 0.12) -> str:
    """Occasionally mangle one ASCII word of a context line (never a record)."""
    if rng.random() >= p:
        return text
    words = text.split(" ")
    idx = [i for i, w in enumerate(words) if len(w) >= 5 and w.isascii() and w.isalpha()]
    if not idx:
        return text
    i = rng.choice(idx)
    w = words[i]
    if rng.random() < 0.5:
        k = rng.randrange(1, len(w) - 1)
        w = w[:k] + w[k + 1] + w[k] + w[k + 2 :]
    else:
        vowels = [k for k, ch in enumerate(w) if ch in _VOWELS and 0 < k < len(w) - 1]
        if vowels:
            k = rng.choice(vowels)
            w = w[:k] + w[k + 1 :]
    words[i] = w
    return " ".join(words)


def account_phrase(rng: random.Random, acct: Account, style: str | None = None) -> str:
    """How an assumption names an account: as the phone shows it, never as a person."""
    if acct.owner:
        return "the owner"
    if acct.app == "Telegram":
        if acct.label and acct.label.startswith("@"):
            forms = (
                f"Telegram user {acct.identifier}",
                f"Telegram user {acct.identifier} (shown as {acct.label})",
                f"the Telegram account {acct.identifier} (shown as {acct.label})",
            )
        elif acct.label:
            forms = (
                f"Telegram user {acct.identifier}",
                f"Telegram user {acct.identifier} (saved as {acct.label})",
            )
        else:
            forms = (f"Telegram user {acct.identifier}",)
    elif acct.app == "Instagram":
        forms = (
            f"the Instagram account {acct.identifier}",
            f"the Instagram user {acct.identifier}",
        )
    else:
        number = pretty_phone(acct.identifier)
        if acct.label:
            forms = (
                f"the contact saved as {acct.label}",
                f"the number saved as {acct.label}",
                f"{number} (saved as {acct.label})",
                f"the {acct.app} contact saved as {acct.label}",
            )
        else:
            forms = (number, f"the {acct.app} account {number}", f"the number {number}")
    if style == "short":
        return forms[0]
    return rng.choice(forms)


def normalized(text: str) -> str:
    """Case, punctuation and spacing folded away: the form duplicate checks compare."""
    return " ".join(re.findall(r"\w+", text.casefold()))
