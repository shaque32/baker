"""Russian hand-written scenarios, including the disputed translation family.

Same slots as special.py. Russian past-tense endings: "{c}" the contact's, "{o}" the owner's.
"""

from __future__ import annotations

from eval.train.special import MON_TO_THU, S

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
        "{S} asked {O} to bring {y} on {next}.",
        "'Ту штуку' is never named in the text shown.",
        ys=OBJECTS_RU,
        lang="ru",
    ),
    S(
        "ovr_pronoun",
        "ты это уже выбросил{o}?",
        "{S} asked {O} whether they had thrown {y} away.",
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
        xs=("две", "три", "четыре"),  # 2 to 4 take these forms; 5 and up would need "коробок"
        ys=("конфеты", "витаминки", "коробки"),
        lang="ru",
    ),
    S(
        "ovr_code_word",
        "{y} готов, заезжай после 6",
        "'{y}' means cocaine; {S} had cocaine ready for {O} after 6 p.m.",
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
        "'Бумаги' means forged documents; {S} promised {O} the documents for {next}.",
        "The record says 'бумаги' (papers); forged is the assumption's own reading.",
        lang="ru",
    ),
)

DIFFERENT_TOPIC_RU = (
    S(
        "ovr_different_topic",
        "детали пришли, забирай",
        "{S} had drugs ready for {O} to pick up.",
        "The context is a bike repair; 'детали' are its parts.",
        before=(("o", "как там велик"), ("c", "цепь и оба колеса, я ж говорил{c}")),
        lang="ru",
    ),
    S(
        "ovr_different_topic",
        "привезли, {x} коробок, в подсобке",
        "{X} kilos of drugs were in the back room of the shop.",
        "The context is a tile order; the boxes are tile.",
        before=(("o", "плитку привезли?"),),
        xs=("6", "8", "12"),
        lang="ru",
    ),
    S(
        "ovr_different_topic",
        "{x} порций готово к пяти",
        "{S} had {x} doses ready by 5 p.m. on {date}.",
        "The context is a banquet; 'порций' are servings of food.",
        before=(("c", "банкет в субботу"), ("o", "сколько готовишь")),
        xs=("40", "60"),
        lang="ru",
    ),
    S(
        "ovr_different_topic",
        "да, {x} руб налом, заедет вечером",
        "{S} agreed to sell drugs for {x} rubles on {date}.",
        "The context shows the sale is a game console.",
        before=(("o", "продал{c} приставку?"),),
        xs=("15000", "20000"),
        lang="ru",
    ),
)

JOKE_RU = (
    # The marker leaves sincerity open; the rationale never calls the record a joke (rule 24).
    S(
        "ovr_joke",
        "банк грабил{c}, ясное дело))",
        "{S} robbed a bank on {date}.",
        "The record's '))' and the owner's 'ахах' leave it unclear whether the sender meant it "
        "seriously, so the record does not establish a bank robbery.",
        before=(("o", "ты где был{c} весь день??"),),
        after=(("o", "ахах"),),
        lang="ru",
    ),
    S(
        "ovr_joke",
        "да почку продал{c} ахах",
        "{S} sold a kidney.",
        "The 'ахах' and the owner's '))' leave it unclear whether the sender meant it seriously; "
        "the record does not establish that a kidney was sold.",
        before=(("o", "откуда новые диски"),),
        after=(("o", "))"),),
        lang="ru",
    ),
    S(
        "ovr_joke",
        "старую хату спалил{c}, проще чем мыть)",
        "{S} set fire to the old apartment.",
        "The record's ')' and the owner's 'ахах' leave it unclear whether the sender meant it "
        "seriously, so the record does not establish a fire.",
        before=(("o", "как переезд"),),
        after=(("o", "ахах"),),
        lang="ru",
    ),
    S(
        "ovr_joke",
        "не могу, я в тюрьме))",
        "{S} was in jail.",
        "The '))' and the owner's 'лол' leave it unclear whether the sender meant it seriously, "
        "so the record does not establish that the sender was in jail.",
        before=(("o", "придёшь на игру?"),),
        after=(("o", "лол"),),
        lang="ru",
    ),
)

COUNT_RU = (
    S(
        "ovr_count",
        "как всегда, к обеду доставил{c}",
        "{S} made a delivery before noon every week in {month}.",
        "The record shows one delivery and a loose 'как всегда'; it does not show the other weeks.",
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
        "{S} delivered two bags every Friday in {month}.",
        "The record is one message using the loose phrase 'как каждую пятницу'; it does not "
        "show a delivery on each of the days the assumption covers.",
        days=(4,),
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
        "свет {x} горел в 2 ночи",
        "{y} was home at 2 a.m. on {date}.",
        "A light on is an inference about who was home, not an observation of it.",
        xs=("у димы", "у лёши", "у глеба"),
        ys=("Дима", "Лёша", "Глеб"),
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
        "вчера вечером ключи отдал{c}",
        "{S} handed over the keys on {prev}.",
        "Sent at {clock}, just after midnight; 'вчера вечером' may mean either of two evenings.",
        lang="ru",
    ),
    S(
        "cpl_relative_time",
        "ночью заплатил{c} {x}",
        "{S} paid {y} on {date}.",
        "Sent at {clock}; 'ночью' straddles midnight, so the date is open.",
        xs=("диме", "лёше", "кате"),
        ys=("Дима", "Лёша", "Катя"),
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
    # Where the sender is, or what holds, when the message is sent; the assumption is dated
    # before the record's date, covers the whole of it, or is bounded by a whole hour before
    # the record's clock (guide rule 23). Never "дома" without a named place.
    S(
        "con_other_state",
        "уже три дня в москве, сижу в кафе на арбате",
        "{S} was still in Sochi on {prev}.",
        "On {date} the sender writes 'уже три дня в москве, сижу в кафе на арбате', which "
        "cannot be true together with being in Sochi the day before the message.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "я ещё в сочи, рейс перенесли на следующую неделю",
        "{S} had flown back to Moscow before {date}.",
        "On {date} the sender writes 'я ещё в сочи, рейс перенесли на следующую неделю'. Being "
        "still in Sochi then cannot be true together with the assumption; whether it is true is "
        "for the expert.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "ладу продал{c} три недели назад, она уже у нового хозяина",
        "{S} still owned the Lada on {lastweek}.",
        "On {date} the sender writes 'ладу продал{c} три недели назад'. What those words state "
        "cannot be true together with still owning it a week before; whether they are true is "
        "for the expert.",
        quote="ладу продал{c} три недели назад",
        lang="ru",
    ),
    S(
        "con_other_state",
        "рейс отменили, сижу в казани",
        "{S} had landed in Moscow by {hour} on {date}.",
        "Sent at {clock}, 'рейс отменили, сижу в казани' cannot be true together with the "
        "assumption, whose time ends at {hour}, before the message.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "мы съехали с той квартиры на третьем этаже месяц назад",
        "{S} was still living in the third-floor apartment on {lastweek}.",
        "On {date} the sender writes 'мы съехали с той квартиры на третьем этаже месяц назад', "
        "which cannot be true together with still living there a week before.",
        lang="ru",
    ),
    S(
        "con_other_state",
        "я в питере до пятницы, по работе",
        "{S} was in Moscow all day on {date}.",
        "At {clock} the sender writes 'я в питере до пятницы', which cannot be true together "
        "with being in Moscow all day on that date.",
        quote="я в питере до пятницы",
        days=MON_TO_THU,
        lang="ru",
    ),
    S(
        "con_other_state",
        "еду в электричке в тверь, только проехали клин",
        "{S} was in Kazan all day on {date}.",
        "At {clock} the sender writes 'еду в электричке в тверь, только проехали клин'. Being on "
        "that train then cannot be true together with the assumption; whether it is true is for "
        "the expert.",
        lang="ru",
    ),
)

TRANSLATION_RU = (
    # Only slang whose readings really compete in the record's own words: "кинул" can be threw,
    # ditched or scammed, "занёс" brought or paid a bribe. Where the context fixes the meaning
    # ("жениха отшила", "я на мели") the item would be a plain translation, so none is here.
    # The rationale names the competing readings and says a translator must settle them (guide
    # rules 6 and 24); it never calls the literal reading odd.
    S(
        "ovr_translation",
        "{x} меня кинул",
        "{y} stole money from {S}.",
        "'кинул' can mean the sender was ditched or let down, or that they were scammed out of "
        "money; the assumption takes the last reading, and the record does not settle which the "
        "sender meant without a translator.",
        quote="кинул",
        xs=("дима", "лёша", "глеб"),
        ys=("Дима", "Лёша", "Глеб"),
        lang="ru",
    ),
    S(
        "ovr_translation",
        "{x} слил всё",
        "{y} leaked everything.",
        "'слил всё' can mean that person leaked everything, blew everything or poured it all "
        "out; the assumption takes the first reading, and the record does not settle which the "
        "sender meant without a translator.",
        quote="слил",
        xs=("дима", "лёша", "глеб"),
        ys=("Дима", "Лёша", "Глеб"),
        lang="ru",
    ),
    S(
        "ovr_translation",
        "мы {x} сделали",
        "{S} and others beat {y} up.",
        "'сделали' here can mean the sender's side beat that person in a game or a contest, or "
        "beat them up; the assumption takes the second reading, and the record does not settle "
        "which the sender meant without a translator.",
        quote="сделали",
        xs=("диму", "лёшу", "глеба"),
        ys=("Дима", "Лёша", "Глеб"),
        lang="ru",
    ),
    S(
        "ovr_translation",
        "{x} меня развела на бабки",
        "{y} swindled {S} out of money.",
        "'развела на бабки' can mean that person talked the sender into spending money or "
        "swindled them out of it; the assumption takes the second reading, and the record does "
        "not settle which the sender meant without a translator.",
        quote="развела на бабки",
        xs=("катя", "лена", "даша"),
        ys=("Катя", "Лена", "Даша"),
        lang="ru",
    ),
    S(
        "ovr_translation",
        "я {x} сдал{c}",
        "{S} turned {y} in to the police.",
        "'сдал' can mean the sender handed that person over or dropped them off somewhere, or "
        "informed on them; the assumption takes the last reading and adds the police, and the "
        "record does not settle which the sender meant without a translator.",
        quote="сдал{c}",
        xs=("диму", "лёшу", "глеба"),
        ys=("Дима", "Лёша", "Глеб"),
        lang="ru",
    ),
    S(
        "ovr_translation",
        "бабки {x} занёс",
        "{y} delivered a bribe.",
        "'занёс' can mean that person simply brought the money over or that they paid a bribe; "
        "the assumption takes the second reading, and the record does not settle which the "
        "sender meant without a translator.",
        quote="занёс",
        xs=("дима", "лёша", "глеб"),
        ys=("Дима", "Лёша", "Глеб"),
        lang="ru",
    ),
)
