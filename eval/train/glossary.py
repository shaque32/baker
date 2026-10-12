"""Every Russian-English pair the training generator relies on, for Arsh to sign.

PAIRS are dictionary meanings: a Russian record word (as the record writes it; inflected forms
match on the first five letters) and the English words an assumption may use for it. They back
supports items under guide rule 6 (plain Russian counts, literal meaning only). SLANG pairs are
idiomatic readings; they appear only in ovr_translation records and never back a supports item
(tests/test_train_generator.py checks both).
"""

from __future__ import annotations

PAIRS: tuple[tuple[str, str], ...] = (
    # verbs (past tense, with the first-person future on the same stem)
    ("заплатил", "paid pay"), ("заплачу", "paid pay"), ("платил", "paid pay"),
    ("оплатил", "paid pay"), ("оплачу", "paid pay"),
    ("поставил", "put"), ("поставлю", "put"),
    ("продал", "sold sell"), ("продам", "sold sell"),
    ("отработал", "worked work"), ("отработаю", "worked work"),
    ("одолжил", "lent lend"), ("одолжу", "lent lend"),
    ("купил", "bought buy"), ("куплю", "bought buy"),
    ("позвал", "invited invite"), ("позову", "invited invite"),
    ("забрал", "picked pick up"), ("заберу", "picked pick up"),
    ("поменял", "changed change"), ("поменяю", "changed change"),
    ("заказал", "ordered order booked book"), ("закажу", "ordered order booked book"),
    ("спустил", "took take down"), ("спущу", "took take down"),
    ("получил", "got get"), ("получу", "got get"),
    ("закрыл", "closed close"), ("закрою", "closed close"),
    ("сводил", "took take"), ("свожу", "took take"),
    ("отправил", "sent send"), ("отправлю", "sent send"),
    ("вернул", "gave give back returned return"), ("верну", "gave give back returned return"),
    ("прилетел", "landed land"), ("прилечу", "landed land"),
    ("подписал", "signed sign"), ("подпишу", "signed sign"),
    ("отдал", "handed hand gave give"), ("отдам", "handed hand gave give"),
    ("скопировал", "copied copy"), ("скопирую", "copied copy"),
    ("оставил", "left leave"), ("оставлю", "left leave"),
    ("залил", "put in"), ("залью", "put in"),
    ("привезли", "delivered"), ("взял", "took"), ("придёт", "coming come"),
    ("должен", "owe owed"), ("должна", "owe owed"),
    # nouns and the rest
    ("сантехник", "plumber"), ("электрик", "electrician"), ("грузчик", "movers"),
    ("аренд", "rent"), ("квартир", "apartment"), ("этаж", "floor"), ("договор", "contract"),
    ("залог", "deposit"), ("обратно", "back"),
    ("шины", "tires"), ("новые", "new"), ("новый", "new"), ("машин", "car"), ("лад", "Lada"),
    ("масло", "oil"), ("парковк", "parking"), ("бензин", "gas"),
    ("смен", "shift"), ("бар", "bar"), ("ночную", "night"), ("дневную", "day"),
    ("утреннюю", "morning"), ("чаевых", "tips"),
    ("брат", "brother"), ("сестр", "sister"), ("билет", "ticket tickets"),
    ("стрижк", "haircut"), ("маникюр", "manicure"),
    ("сочи", "Sochi"), ("казан", "Kazan"), ("москв", "Moscow"), ("поезд", "train"),
    ("отель", "hotel"),
    ("ремонт", "repair"), ("экран", "screen"), ("телефон", "phone"), ("ноутбук", "laptop"),
    ("фоток", "photos"), ("гб", "GB"),
    ("свадьб", "wedding"), ("человек", "people"), ("торт", "cake"), ("дидже", "DJ"),
    ("зал", "hall"), ("спортзал", "gym"), ("тренировок", "sessions"), ("тренер", "trainer"),
    ("дет", "kids"), ("школ", "school"), ("врач", "doctor"), ("мамины", "mom's"),
    ("лекарств", "medicine"), ("клиент", "clients"),
    ("коробок", "boxes"), ("плитк", "tile tiles"), ("склад", "warehouse"),
    ("установк", "installation"), ("окн", "window"), ("дрель", "drill"), ("газель", "van"),
    ("запчаст", "car parts"), ("зимнюю", "winter"), ("куртк", "coat"),
    ("руб", "rubles"), ("ещё", "still"), ("год", "year"), ("краск", "paint"),
    ("абонемент", "pass"), ("бассейн", "pool"), ("занятий", "classes"), ("йог", "yoga"),
    ("окрашиван", "coloring"), ("волос", "hair"), ("ресниц", "lashes"), ("переезд", "move"),
    ("часов", "hours"), ("нян", "babysitter"), ("коляск", "stroller"),
    ("коммуналк", "utilities"), ("ключ", "keys"), ("хозяин", "landlord"), ("штраф", "fine"),
    ("мойк", "car wash"),
    # values
    ("две", "two"), ("два", "two"), ("три", "three"), ("четыре", "four"), ("час", "one"),
    ("понедельник", "Monday"), ("вторник", "Tuesday"), ("сред", "Wednesday"),
    ("четверг", "Thursday"), ("пятниц", "Friday"), ("суббот", "Saturday"),
    ("воскресень", "Sunday"),
)  # fmt: skip

SLANG: tuple[tuple[str, str], ...] = (
    ("кинул", "stole from"),  # slang: complicates only (literally "threw")
    ("пробил", "ran a background check on"),  # slang: complicates only (literally "punched")
    ("слил", "leaked"),  # slang: complicates only (literally "poured out")
    ("сделали", "beat up"),  # slang: complicates only (literally "made")
    ("развела", "robbed swindled"),  # slang: complicates only (literally "led apart")
    ("забей", "drop the matter"),  # slang: complicates only (literally "hammer in")
    ("на мели", "broke, had no money"),  # slang: complicates only (literally "aground")
    ("крышует", "extorts protection money"),  # slang: complicates only (literally "roofs")
    ("отшила", "rejected"),  # slang: complicates only (literally "unsewed")
    ("сдал", "turned in to the police"),  # slang: complicates only (literally "handed over")
    ("занёс", "delivered a bribe"),  # slang: complicates only (literally "brought in")
)

RU_EN: dict[str, str] = dict(PAIRS + SLANG)
