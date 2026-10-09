"""Hand-written scenarios for the families a fact grammar cannot produce, English.

Slots: {S} the record's sender as the phone shows it, {O} the other party, {pron} and {poss}
the sender's pronouns (always "they" and "their": an assumption genders nobody), {date} the
record's local date, {prev} the day before, {next} the day after, {clock} its local clock time,
{month} its month and year, {x} and {y} from xs and ys (chosen together when both have the same
length, else independently; {X} and {Y} capitalized), {c} and {o} Russian endings. A claim
names people and objects outright: never "the man", "it" or a relative time.
"""

from __future__ import annotations

from dataclasses import dataclass

Line = tuple[str, str]  # (who, text): who is "o" (owner) or "c" (contact)


@dataclass(frozen=True)
class Special:
    family: str
    lang: str
    rec_who: str  # who sends the record
    before: tuple[Line, ...]
    record: str
    after: tuple[Line, ...]
    quote: str  # a word-aligned substring of record after filling
    claim: str  # the assumption
    why: str  # the rationale
    xs: tuple[str, ...] = ()
    ys: tuple[str, ...] = ()


def S(family: str, record: str, claim: str, why: str, *, quote: str | None = None,
      before: tuple[Line, ...] = (), after: tuple[Line, ...] = (), who: str = "c",
      xs: tuple[str, ...] = (), ys: tuple[str, ...] = (), lang: str = "en") -> Special:  # fmt: skip
    return Special(family, lang, who, before, record, after, quote or record, claim, why, xs, ys)


PLACES = ("seat", "mat", "sink", "porch step", "mattress", "bench", "spare tire", "cooler")
OBJECTS = ("a knife", "a gun", "the cash", "the pills", "the stolen laptop", "a bag of weed",
           "the stolen watch", "the fake ids")  # fmt: skip
NAMES = ("ana", "bea", "cleo", "gus", "ike", "mara", "kofi", "dev")

PRONOUN = (
    S(
        "ovr_pronoun",
        "put it under the {x}",
        "{S} told {O} to put {y} under the {x}.",
        "The record says only 'it'; nothing shown says what it is, so the object is the "
        "assumption's own guess.",
        xs=PLACES,
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "bring that thing tmrw pls",
        "{S} asked {O} to bring {y} on {next}.",
        "'That thing' is never named in the record or the context shown.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "did u get rid of it yet",
        "{S} asked {O} whether {O} had gotten rid of {y}.",
        "'It' is unresolved in everything shown; the assumption supplies the object.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "leave it in the glovebox",
        "{S} told {O} to leave {y} in the glovebox.",
        "Nothing shown says what 'it' is.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "i moved it to the garage",
        "{S} moved {y} to the garage.",
        "The record does not say what was moved; the object comes from outside the chat.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "dont touch that till i get there",
        "{S} told {O} not to touch {y} before {S} arrived.",
        "'That' is not resolved by the record or the context shown.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "that thing is still in my trunk",
        "{S} kept {y} in {poss} trunk.",
        "What 'that thing' is never appears in the text shown.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "they picked it up this morning",
        "{Y} was collected on the morning of {date}.",
        "'It' has no antecedent in the record or the context shown.",
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "ok its under the {x}, go",
        "{Y} was under the {x}.",
        "The record places 'it' but never says what 'it' is.",
        xs=PLACES,
        ys=OBJECTS,
    ),
    S(
        "ovr_pronoun",
        "did u bring the thing",
        "{S} asked {O} whether {O} had brought {y}.",
        "'The thing' is unresolved; the assumption names the object itself.",
        ys=OBJECTS,
    ),
)

CODE_WORD = (
    S(
        "ovr_code_word",
        "need {x} more of the {y}",
        "'{y}' means pills; {S} asked {O} for {x} more pills.",
        "Nothing shown says '{y}' means anything other than {y}; the decoding is the assumption's.",
        xs=("2", "3", "5", "a few"),
        ys=("blue ones", "party favors", "snacks", "candy", "vitamins", "cookies"),
    ),
    S(
        "ovr_code_word",
        "bring the {y} when u come",
        "By '{y}' {S} meant drugs; {S} asked {O} to bring drugs.",
        "The record says '{y}'; no context shown gives it a hidden meaning.",
        ys=("groceries", "paperwork", "party favors", "food", "candy", "stuff"),
    ),
    S(
        "ovr_code_word",
        "got the {y}? im outside",
        "'{y}' refers to the stolen cards; {S} asked whether {O} had the stolen cards.",
        "The plain word is '{y}'; reading it as stolen cards needs outside knowledge.",
        ys=("groceries", "paperwork", "food", "stuff", "snacks"),
    ),
    S(
        "ovr_code_word",
        "the {y} is ready, swing by after 6",
        "'{y}' means cocaine; {S} had cocaine ready for {O} after 6 p.m.",
        "The context shown does not establish that '{y}' stands for anything else.",
        ys=("food", "paperwork", "stuff", "candy"),
    ),
    S(
        "ovr_code_word",
        "left the {y} in the mailbox",
        "{S} left drugs, called '{y}', in the mailbox.",
        "Nothing shown decodes '{y}'; the record says only that {y} was left.",
        ys=("groceries", "paperwork", "snacks", "candy"),
    ),
    S(
        "ovr_code_word",
        "how much for a half",
        "{S} asked the price of half an ounce of cannabis.",
        "'A half' is not tied to anything in the text shown; the cannabis reading is a guess.",
        quote="how much for a half",
    ),
    S(
        "ovr_code_word",
        "can u do {x} plates by friday",
        "'Plates' means stolen license plates; {S} ordered {x} stolen license plates for Friday.",
        "The record says 'plates'; nothing shown makes them license plates or stolen.",
        xs=("20", "30", "40"),
    ),
    S(
        "ovr_code_word",
        "ill have the {y} for u tmrw",
        "'{y}' stands for counterfeit bills; {S} promised {O} counterfeit bills for {next}.",
        "The reading of '{y}' as counterfeit bills comes from outside the chat.",
        ys=("paperwork", "party favors", "stuff", "groceries"),
    ),
    S(
        "ovr_code_word",
        "need the {y} by 9, big night",
        "'{y}' means ecstasy; {S} asked {O} for ecstasy before 9 p.m. on {date}.",
        "Nothing in the record or context shown gives '{y}' a hidden meaning.",
        ys=("candy", "party favors", "snacks", "vitamins"),
    ),
)

DIFFERENT_TOPIC = (
    S(
        "ovr_different_topic",
        "the parts are in, come get them",
        "{S} had drugs ready for {O} to pick up.",
        "The context is a bike repair; the words fit the assumption only out of context.",
        before=(("o", "hows the bike coming along"), ("c", "chain and both tires, told u")),
    ),
    S(
        "ovr_different_topic",
        "its here, {x} boxes, back of the shop",
        "{X} kilos of drugs were at the back of the shop.",
        "The context is a tile order; 'boxes' are boxes of tile unless something shows otherwise.",
        before=(("o", "did the tile order ship"),),
        xs=("6", "8", "12"),
    ),
    S(
        "ovr_different_topic",
        "{x} plates ready by 5",
        "{S} had {x} stolen license plates ready by 5 p.m. on {date}.",
        "The context is catering; the plates are dinner plates in that reading.",
        before=(("c", "catering for sat is set"), ("o", "nice, how many")),
        xs=("40", "60", "80"),
    ),
    S(
        "ovr_different_topic",
        "yep ${x} cash, come by tonight",
        "{S} agreed to sell {O} drugs for ${x} on {date}.",
        "The context shows the sale is a game console.",
        before=(("o", "u still selling the ps5"),),
        xs=("250", "300", "350"),
    ),
    S(
        "ovr_different_topic",
        "we pushed like 200 shots tonight",
        "{S} sold 200 doses of a drug on {date}.",
        "The context is a bar shift; 'shots' are drinks in that reading.",
        before=(("o", "how was the shift"),),
    ),
    S(
        "ovr_different_topic",
        "hid the extra boards behind the shed so nobody takes them",
        "{S} hid stolen goods behind the shed.",
        "The context is a deck build; the boards are lumber for it.",
        before=(("o", "hows the deck"), ("c", "almost done, ran out of screws")),
    ),
    S(
        "ovr_different_topic",
        "ill bring the muscle, 3 guys",
        "{S} brought three men to intimidate someone.",
        "The context is a move; 'muscle' means people to carry furniture there.",
        before=(("c", "moving day is sat, truck at 9"), ("o", "i cant lift the couch alone")),
    ),
    S(
        "ovr_different_topic",
        "cleaned him out, got full asking",
        "{S} robbed the buyer of the car.",
        "The context is a car sale; 'cleaned him out' is about the price in that reading.",
        before=(("o", "how'd the car sale go"),),
    ),
    S(
        "ovr_different_topic",
        "yeah wiped it clean, nothing left on it",
        "{S} destroyed evidence on a laptop.",
        "The context is a laptop repair; wiping a drive is part of the repair.",
        before=(("o", "laptop fixed?"),),
        after=(("o", "cool, did u reinstall windows"),),
    ),
    S(
        "ovr_different_topic",
        "ill bring the goods, 6 bottles",
        "{S} delivered contraband to the wedding.",
        "The context is a wedding; the bottles are drinks for it.",
        before=(("c", "nails at 2 then the wedding"), ("o", "who's bringing wine")),
    ),
    S(
        "ovr_different_topic",
        "dropped the box at the back door like u said",
        "{S} delivered drugs to the back door.",
        "The context is a laptop part; the box is that delivery.",
        before=(("o", "the laptop fan came in, can u bring it"),),
    ),
)
