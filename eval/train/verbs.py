"""The verbs a supports record must carry (one per language list), so a bare noun phrase such as
"200 flat" or a booking line never backs a supports item.

English entries are whole lowercase tokens: past-tense and present-perfect verbs of the facts,
the explicit plan, question and denial auxiliaries ("gonna", "did", "didnt") and the report
verbs of hearsay records. Russian entries are stems matched as prefixes, so the feminine past
("заплатила") and the first-person future ("заплачу") count. sup_answer records may be short
answers whose verb sits in the question, and sup_verbatim quotes the record, so neither is held
to this list.
"""

from __future__ import annotations

SUPPORT_VERBS_EN: frozenset[str] = frozenset(
    """paid picked let patched sold put brought dropped booked covered made closed hired won took
    lent sent lost did signed landed got backed invited ordered returned replaced had fixed washed
    renewed drove bought rented packed worked swapped logged trained tipped ran swam cancelled
    gave zelled spent charged checked sublet mounted filled shipped donated served benched cashed
    went owe owes owed didnt never gonna will ill ima planning says said told heard
    swears""".split()
)

SUPPORT_VERBS_RU: tuple[str, ...] = (
    "заплатил", "заплачу", "оплатил", "оплачу", "поставил", "поставлю", "продал", "продам",
    "отработал", "отработаю", "одолжил", "одолжу", "купил", "куплю", "позвал", "позову",
    "забрал", "заберу", "поменял", "поменяю", "заказал", "закажу", "спустил", "спущу", "получил",
    "получу", "закрыл", "закрою", "сводил", "свожу", "отправил", "отправлю", "вернул", "верну",
    "прилетел", "прилечу", "подписал", "подпишу", "отдал", "отдам", "скопировал", "скопирую",
    "оставил", "оставлю", "залил", "залью", "должен", "должна", "говорит", "сказал", "написал",
)  # fmt: skip
