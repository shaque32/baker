"""Past-tense and present-perfect verb forms a supports record must carry.

A bare noun phrase ("set at the Pulaski Room 8 to close") can be a booking or a plan as easily
as a report, so it never supports an assumption that the act happened. Every record of
sup_plain, sup_time_window, sup_contact, sup_account_shared and sup_injection contains one of
these forms; sup_answer's answer may be short because the question carries the verb, and
sup_verbatim quotes the record. The lists are fixed: a new template that needs a new form adds
it here.
"""

from __future__ import annotations

import re

PAST_VERBS_EN: tuple[str, ...] = (
    "accepted", "agreed", "been", "bought", "brought", "called", "came", "caught", "changed",
    "cleaned", "cleared", "clocked", "closed", "counted", "did", "dropped", "drove", "fed",
    "finished", "fueled", "gave", "got", "had", "handled", "kept", "left", "loaded", "locked",
    "made", "met", "moved", "offered", "packed", "paid", "parked", "passed", "picked", "played",
    "poured", "put", "rained", "ran", "said", "scored", "sealed", "set up", "shipped", "showed",
    "signed", "sold", "spun", "stayed", "threw", "tied", "took", "tutored", "unloaded", "walked",
    "was", "went", "were", "worked",
)  # fmt: skip

PAST_VERBS_RU: tuple[str, ...] = (
    "была", "был", "взял", "взяла", "вернулись", "вернулся", "вызвал", "вызвался", "выгулял",
    "вышел", "вышла", "вышли", "дали", "договорился", "залили", "занимался", "заняли",
    "заплатил", "заправились", "закрыл", "закрылся", "закончили", "заходил", "оплатил",
    "оплатила", "опоздали", "освободил", "оставил", "оставили", "отвёз", "отметился",
    "отправил", "отпустили", "отработала", "отыграли", "перевела", "перенёс", "пересчитали",
    "подписал", "поймали", "показал", "получила", "поменял", "поставили", "привёз", "привезли",
    "приехал", "пришла", "пришло", "продал", "продали", "прошли", "расставил", "сгрузил",
    "сделали", "сломался", "согласилась", "согласились", "уехали",
)  # fmt: skip

_EN = re.compile(r"\b(" + "|".join(re.escape(v) for v in PAST_VERBS_EN) + r")\b")
_RU = re.compile(r"(?<![а-яё])(" + "|".join(PAST_VERBS_RU) + r")(?![а-яё])")


def has_past_verb(text: str) -> bool:
    """Whether a record text carries a listed English or Russian past form."""
    low = text.lower()
    return bool(_EN.search(low) or _RU.search(low))
