"""Russian hand-written scenarios, including the disputed translation family.

Same slots as special.py. Russian past-tense endings: "{c}" the contact's, "{o}" the owner's.
"""

from __future__ import annotations

from eval.train.special import S

OBJECTS_RU = ("a knife", "a gun", "the cash", "the pills", "the stolen phone", "a bag of weed")
PLACES_RU = ("сиденье", "коврик", "матрас", "крыльцо", "запаску")

PRONOUN_RU = (
    S(
        "ovr_pronoun",
        "положи это под {x}",
        "{S} told {O} to put {y} under the {x}.",
        "The record says only 'это'; nothing shown says what it is.",
        xs=PLACES_RU,
        ys=OBJECTS_RU,
        lang="ru",
    ),
    S(
        "ovr_pronoun",
        "привези ту штуку завтра",
        "{S} asked {O} to bring {y} the next day.",
        "'Ту штуку' is never named in the text shown.",
        ys=OBJECTS_RU,
        lang="ru",
    ),
    S(
        "ovr_pronoun",
        "ты это уже выбросил{o}?",
        "{S} asked {O} whether {O} had thrown {y} away.",
        "'Это' has no antecedent in the record or the context shown.",
        ys=OBJECTS_RU,
        lang="ru",
    ),
    S(
        "ovr_pronoun",
        "оставь это в бардачке",
        "{S} told {O} to leave {y} in the glovebox.",
        "Nothing shown says what 'это' is.",
        ys=OBJECTS_RU,
        lang="ru",
    ),
    S(
        "ovr_pronoun",
        "я это в гараж убрал{c}",
        "{S} moved {y} to the garage.",
        "The record does not say what was moved.",
        ys=OBJECTS_RU,
        lang="ru",
    ),
    S(
        "ovr_pronoun",
        "эта штука до сих пор у меня в багажнике",
        "{S} kept {y} in {poss} trunk.",
        "'Эта штука' is never named in the text shown.",
        ys=OBJECTS_RU,
        lang="ru",
    ),
)

CODE_WORD_RU = (
    S(
        "ovr_code_word",
        "привези {y}",
        "'{y}' means drugs; {S} asked {O} to bring drugs.",
        "The plain word is '{y}'; nothing shown gives it another meaning.",
        ys=("товар", "посылочку", "зелень", "сахар"),
        lang="ru",
    ),
    S(
        "ovr_code_word",
        "нужно ещё {x} {y}",
        "'{y}' means pills; {S} asked {O} for more pills.",
        "Nothing shown decodes '{y}'; the record asks for {y}.",
        xs=("две", "три", "пять"),
        ys=("конфеты", "витаминки", "коробки"),
        lang="ru",
    ),
    S(
        "ovr_code_word",
        "{y} готов, заезжай после 6",
        "'{y}' means cocaine; {S} told {O} the cocaine was ready.",
        "The context shown does not establish that '{y}' stands for anything else.",
        ys=("товар", "сахар"),
        lang="ru",
    ),
    S(
        "ovr_code_word",
        "сколько за половинку",
        "{S} asked the price of half an ounce of cannabis.",
        "'Половинку' is tied to nothing in the text shown; the cannabis reading is a guess.",
        lang="ru",
    ),
    S(
        "ovr_code_word",
        "бумаги будут завтра",
        "'Бумаги' means forged documents; {S} promised {O} forged documents.",
        "The record says 'бумаги' (papers); forged is the assumption's own reading.",
        lang="ru",
    ),
)

DIFFERENT_TOPIC_RU = (
    S(
        "ovr_different_topic",
        "детали пришли, забирай",
        "{S} told {O} that drugs were ready for pickup.",
        "The context is a bike repair; 'детали' are its parts.",
        before=(("o", "как там велик"), ("c", "цепь и оба колеса, я ж говорил{c}")),
        lang="ru",
    ),
    S(
        "ovr_different_topic",
        "привезли, {x} коробок, в подсобке",
        "{S} said {x} kilos had arrived at the shop.",
        "The context is a tile order; the boxes are tile.",
        before=(("o", "плитку привезли?"),),
        xs=("6", "8", "12"),
        lang="ru",
    ),
    S(
        "ovr_different_topic",
        "{x} порций готово к пяти",
        "{S} had {x} doses ready by 5 p.m.",
        "The context is a banquet; 'порций' are servings of food.",
        before=(("c", "банкет в субботу"), ("o", "сколько готовишь")),
        xs=("40", "60"),
        lang="ru",
    ),
    S(
        "ovr_different_topic",
        "да, {x} налом, заедет вечером",
        "{S} agreed to sell drugs for {x} rubles that evening.",
        "The context shows the sale is a game console.",
        before=(("o", "продал{c} приставку?"),),
        xs=("15000", "20000"),
        lang="ru",
    ),
)

JOKE_RU = (
    S(
        "ovr_joke",
        "банк грабил{c}, ясное дело))",
        "{S} robbed a bank that afternoon.",
        "The owner asks where the sender was; the sender's next line says it was a joke.",
        before=(("o", "ты где был{c} весь день??"),),
        after=(("c", "шучу, в мфц три часа просидел{c}"),),
        lang="ru",
    ),
    S(
        "ovr_joke",
        "почку продал{c} ахах",
        "{S} sold a kidney.",
        "The sender answers a question about money with an obvious joke and then gives the "
        "real answer.",
        before=(("o", "откуда новые диски"),),
        after=(("o", "))"), ("c", "да не, премию дали")),
        lang="ru",
    ),
    S(
        "ovr_joke",
        "старую хату спалил{c}, проще чем мыть)",
        "{S} set fire to the old apartment.",
        "The next line from the same sender says it was a joke.",
        before=(("o", "как переезд"),),
        after=(("c", "шучу, ещё отмываю"),),
        lang="ru",
    ),
    S(
        "ovr_joke",
        "не могу, я в тюрьме))",
        "{S} was in jail.",
        "The sender's next line withdraws it as a joke.",
        before=(("o", "придёшь на игру?"),),
        after=(("c", "шучу, у мамы застрял{c}"),),
        lang="ru",
    ),
)

COUNT_RU = (
    S(
        "ovr_count",
        "как всегда, к обеду доставил{c}",
        "{S} made a delivery before noon every week in {month}.",
        "The record shows one delivery and a loose 'как всегда'; it does not show every week.",
        lang="ru",
    ),
    S(
        "ovr_count",
        "был{c} в зале утром, как всегда",
        "{S} went to the gym every day in {month}.",
        "One visit and a loose 'как всегда' are shown; the other days are not.",
        before=(("o", "ты в зал ходишь ещё?"),),
        lang="ru",
    ),
    S(
        "ovr_count",
        "две сумки доставил{c}, как каждую пятницу",
        "{S} delivered two bags every Friday that year.",
        "One Friday is shown; 'как каждую пятницу' is a loose phrase, not a record of each.",
        lang="ru",
    ),
)

INFERENCE_RU = (
    S(
        "cpl_inference",
        "тут +30 и море, остаёмся ещё на неделю",
        "{S} was in Sochi on {date}.",
        "Heat and the sea do not name the city; the place is an inference.",
        lang="ru",
    ),
    S(
        "cpl_inference",
        "не, с мая туда не хожу",
        "{S} quit the bar job.",
        "Not going there since May could be quitting, being let go or a leave; the record "
        "does not say which.",
        before=(("o", "ты ещё в баре работаешь?"),),
        lang="ru",
    ),
    S(
        "cpl_inference",
        "ключи на крючке, бак полный",
        "{S} drove the van that day.",
        "Keys and a full tank suggest a drive but do not show one.",
        lang="ru",
    ),
    S(
        "cpl_inference",
        "у него свет горел в 2 ночи",
        "The man the chat refers to was home at 2 a.m.",
        "A light on is an inference about who was home, not an observation of it.",
        lang="ru",
    ),
    S(
        "cpl_inference",
        "карту отклонило на заправке",
        "{S} had no money on {date}.",
        "A declined card can have many causes; no balance is shown.",
        lang="ru",
    ),
)

RELATIVE_TIME_RU = (
    S(
        "cpl_relative_time",
        "вчера вечером доставил{c}",
        "{S} dropped it off on {prev}.",
        "Sent at {clock}, just after midnight; 'вчера вечером' may mean either of two evenings.",
        lang="ru",
    ),
    S(
        "cpl_relative_time",
        "ночью заплатил{c} ему",
        "{S} paid him on {date}.",
        "Sent at {clock}; 'ночью' straddles midnight, so the date is open.",
        lang="ru",
    ),
    S(
        "cpl_relative_time",
        "сегодня вечером починил{c} раковину наконец",
        "{S} fixed the sink on {date}.",
        "Sent at {clock} after midnight; 'сегодня вечером' most "
        "likely means the evening before this date.",
        lang="ru",
    ),
)

OTHER_STATE_RU = (
    S(
        "con_other_state",
        "я дома с воскресенья",
        "{S} was still in Sochi on {date}.",
        "Being home since Sunday cannot hold with still being in Sochi on {date}.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "уже две недели как уволен{c} из бара",
        "{S} worked a shift at the bar on {date}.",
        "Having quit two weeks earlier rules out a shift on {date}.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "ладу продал{c} ещё в марте",
        "{S} still owned the Lada on {date}.",
        "Sold in March cannot hold with still owning it on {date}.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "я ещё в сочи, рейс в четверг",
        "{S} was in Moscow on {date}.",
        "Still being in Sochi rules out being in Moscow at the time of the message.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "в зал не хожу уже два месяца после операции",
        "{S} was at the gym on {date}.",
        "Two months away from the gym cannot hold with being there on {date}.",
        lang="ru",
    ),
)

TRANSLATION_RU = (
    S(
        "ovr_translation",
        "он меня кинул",
        "The man in the message stole money from {S}.",
        "'Кинул' literally means threw; the reading as a theft is slang and loose.",
        quote="кинул",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "я его пробил{c}",
        "{S} ran a background check on the man.",
        "'Пробил' literally means punched through; the background-check reading is slang.",
        quote="пробил{c}",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "он слил всё",
        "The man leaked everything to the police.",
        "'Слил' literally means poured out; leaking to the police is a slang reading and adds "
        "the police.",
        quote="слил",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "мы его сделали",
        "{S} and others beat the man up.",
        "'Сделали' literally means made; beating him up is a slang reading.",
        quote="сделали",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "она меня развела на бабки",
        "The woman robbed {S}.",
        "'Развела на бабки' is slang for swindled; robbery is a looser reading still.",
        quote="развела на бабки",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "забей на него",
        "{S} told {O} to drop the matter with the man.",
        "'Забей' literally means hammer or beat; dropping the matter is the slang reading.",
        quote="забей",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "я на мели",
        "{S} had no money.",
        "'На мели' literally means aground; being broke is the idiomatic reading.",
        quote="на мели",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "он крышует этот бар",
        "The man extorts protection money from the bar.",
        "'Крышует' is slang; the literal words say nothing about money or extortion.",
        quote="крышует",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "она его отшила",
        "The woman rejected the man.",
        "'Отшила' literally means unsewed; rejection is the slang reading.",
        quote="отшила",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "я его сдал{c}",
        "{S} turned the man in to the police.",
        "'Сдал' literally means handed over; informing to the police is a slang reading.",
        quote="сдал{c}",
        lang="ru",
    ),
    S(
        "ovr_translation",
        "бабки он занёс",
        "The man delivered a bribe.",
        "'Занёс бабки' says he brought money; a bribe is a loose reading.",
        quote="занёс",
        lang="ru",
    ),
)
