"""Russian claim material for Baker's meaning template (guide rules 6 and 29). All invented.

As baker_claim_words.MEANINGS: (words, the claim's meaning in English, the same meaning in a
Russian chat, two meanings of another kind altogether). The words stay in one grammatical form
in every line ("посылка уже у меня", "посылка - это деньги за машину"), so the assumption quotes
them verbatim; every Russian meaning reads the same in the nominative and the accusative, so
"это ..." and "я имею в виду ..." both take it unchanged.
"""

from __future__ import annotations

MEANINGS_RU: tuple[tuple[str, str, str, tuple[str, str]], ...] = (
    ("посылка", "the money for the car", "деньги за машину",
     ("ящик с инструментами", "пакет с детскими вещами")),
    ("бабушкин сервиз", "the safe in the back room", "сейф в подсобке",
     ("сервиз, который бабушка подарила", "набор тарелок на кухне")),
    ("зелёная папка", "the prepaid phones", "предоплаченные телефоны",
     ("документы по квартире", "договор аренды")),
    ("большой заказ", "the cash for the contractor", "наличные для подрядчика",
     ("заказ мебели для кухни", "шкаф из магазина")),
    ("малыш", "the gray sedan in the back lot", "серый седан на заднем дворе",
     ("наш старый телевизор", "маленький чемодан")),
    ("документы", "the cash from the weekend shifts", "наличные за выходные смены",
     ("документы для визы", "бумаги из банка")),
    ("торт", "the down payment for the van", "задаток за фургон",
     ("торт на день рождения", "чизкейк из кафе")),
    ("старый друг", "the moving truck", "грузовик для переезда",
     ("старый диван в гараже", "мой старый велосипед")),
    ("второй ключ", "the storage unit on Grand Street", "склад на Гранд-стрит",
     ("запасной ключ от квартиры", "ключ от почтового ящика")),
    ("лекарство", "the envelopes of cash", "конверты с наличными",
     ("лекарство от давления", "витамины для мамы")),
    ("чайник", "the black pickup truck", "чёрный пикап",
     ("электрический чайник на кухне", "старый чайник с дачи")),
    ("билеты", "the gift cards", "подарочные карты", ("билеты на концерт", "билеты на поезд")),
)  # fmt: skip

SAY_RU = (
    "{p} - это {m}", "{p} = {m}", "{p} значит {m}", "напоминаю: {p} - это {m}",
    "{p}? это {m}", "чтобы было понятно: {p} - это {m}",
    "если я пишу {p}, это {m}",
)  # fmt: skip
OTHER_RU = (
    "{p} - это просто {m}, ничего больше", "{p} = {m}, и всё", "{p} значит {m}, больше ничего",
    "когда я говорю {p}, я имею в виду только {m}", "{p} - это {m} и ничего другого",
)  # fmt: skip
USE_RU = ("{p} уже у меня", "как там {p}?", "{p} на месте", "{p} у тебя?", "завтра будет {p}")
