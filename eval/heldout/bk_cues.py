"""Record templates whose words carry the cue a family turns on. SYNTHETIC.

Square brackets mark the cue span, the words the item quotes; they are removed from the record
text (`cue_split`). Slots: {first} {sur} the named person (lowercase as texted; {First} {Sur}
capitalized), {first2} someone else, {old} {new} two handles without "@", and for weekday plans
{mod}{day} (a bare weekday, or "next " / "this " before it), {spot} and {thing}.
"""

from __future__ import annotations

import re

# A sender giving their own name: person_identity records (bk_identity_named).
ID_EN = (
    "[its {first} {sur}], new number, save it",
    "[{Sur} here], lost my old phone",
    "hey [this is {First} {Sur}] from the co-op",
    "[{First} {Sur} btw], we met at the swap meet",
    "[yeah this is {sur}], whats up",
    "sorry new phone, [its {sur}]",
    "[{Sur} speaking], go ahead",
    "[{First} {Sur} here], got ur number from the front desk",
    "[{first} {sur} from the club], saving ur number",
    "[this is {sur}'s number now], the old one is dead",
)
# The owner calls the sender by the name and the record answers to it: (owner line, record).
ID_ANSWER_EN = (
    ("is this {first} {sur}?", "[yes, {sur} here]"),
    ("{Sur}? from the club?", "[yep thats me, {First} {Sur}]"),
    ("hey, is this still {first} {sur}?", "[still {sur}, yeah]"),
    ("{First} {Sur}?", "[the one and only, {sur}]"),
)
ID_RU = (
    "[это {First} {Sur}], новый номер, сохрани",
    "[{Sur} на связи], старый телефон сломался",
    "привет, [это {First} {Sur}]",
    "[{First} {Sur}], мы виделись на ярмарке",
)
ID_ANSWER_RU = (("это {First} {Sur}?", "[да, это {Sur}]"),)

# A cue about who is typing on an account: authorship records (bk_author_cue).
AUTHOR_EN = (
    "[this is {first2} on {sur}'s phone], the van is unlocked",
    "[{first2} typing for {sur}], they're driving",
    "[{sur} asked me to text u], back in 20",
    "back by 6. [– {First} {Sur}]",
    "[its {sur}, on my sisters phone]",
    "[not {sur}, its {first2}], {sur} left the phone here",
    "[{first2} here, {sur} is busy]",
    "running behind [-{first2} for {Sur}]",
    "[{sur} dictating, {first2} typing]: bring the long ladder",
    "[sent from {sur}'s phone by {first2}]",
)
# The same, for an owner's own account; the cue names nobody the assumption names.
AUTHOR_OWNER_EN = (
    "[this is {first2}, borrowing this phone]",
    "[{first2} typing], the usual person on here is driving",
    "[not the usual person on this phone, its {first2}]",
    "[{first2} on this phone for now], mine died",
    "[its {first2} answering for the owner of this phone]",
)
AUTHOR_RU = (
    "[это {first2}, пишу с чужого телефона]",
    "[пишет {first2}, хозяин телефона за рулём]",
    "[пишу за хозяина, это {first2}]",
    "[не он, это {first2}], телефон остался у меня",
)

# A message saying two handles are one account, or that one became the other (bk_handles_said).
# SELF lines come from the account itself; the rest may come from anyone.
HANDLE_SELF_EN = (
    "[changed my @ from {old} to {new}]",
    "new handle [@{new}, used to be @{old}]",
    "[renamed {old} to {new}], update ur list",
)
HANDLE_ANY_EN = (
    "[@{old} is @{new} now], same account just renamed",
    "fyi [@{old} and @{new} are the same account], they renamed it",
    "[@{new} = @{old}], one account",
    "[follow @{new}, thats the old @{old} renamed]",
    "[{old} became {new}] after the rebrand",
    "heads up [@{old} switched to @{new}], same page",
)
HANDLE_SELF_RU = ("[сменил ник с @{old} на @{new}]",)
HANDLE_ANY_RU = (
    "[@{old} теперь @{new}], это тот же аккаунт",
    "[@{old} и @{new} — один аккаунт], просто переименовали",
)

# Plans for one weekday (bk_weekday_*). The whole record is the quoted words.
WEEKDAY_EN = (
    "lets do {mod}{day} at {spot}",
    "{mod}{day} works, ill bring {thing}",
    "can u cover {mod}{day} at {spot}?",
    "we're on for {mod}{day}, meet at {spot}",
    "ill drop {thing} off {mod}{day} after work",
    "see u {mod}{day} at {spot}",
    "how about {mod}{day}, {spot} around 10",
    "{mod}{day} it is, {spot} at 7",
    "pencil me in for {mod}{day} at {spot}",
    "bring {thing} {mod}{day}, we'll need it",
    "{mod}{day} morning at {spot}?",
    "ok {mod}{day} then, ill text when im near {spot}",
)
WEEKDAY_RU = (
    "давай {acc} {spot}",
    "{acc} привезу {thing}",
    "увидимся {acc} {spot}",
    "сможешь подменить меня {acc}?",
    "{acc} буду {spot} к десяти",
    "заеду {acc} после работы, {spot}",
)
DAYS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
# Accusative with its preposition: bare, "next" and "this" forms, Monday first.
DAYS_RU = {
    "": ("в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу",
         "в воскресенье"),
    "next ": ("в следующий понедельник", "в следующий вторник", "в следующую среду",
              "в следующий четверг", "в следующую пятницу", "в следующую субботу",
              "в следующее воскресенье"),
    "this ": ("в этот понедельник", "в этот вторник", "в эту среду", "в этот четверг",
              "в эту пятницу", "в эту субботу", "в это воскресенье"),
}  # fmt: skip

SPOTS = {
    "apiary": ("the north yard", "the honey house"),
    "rink": ("the rental counter", "gate 3"),
    "kiln": ("the studio", "the kiln room"),
    "orchard": ("the press barn", "the farm stand"),
    "tow": ("the impound lot", "the yard office"),
    "theater": ("the scene shop", "the stage door"),
    "courier": ("the dispatch office", "the bike room"),
    "laundry": ("the laundromat", "the folding tables"),
    "print": ("the print shop", "the cutter table"),
    "rowing": ("the boathouse", "the dock"),
    "piano": ("the storage unit", "the loading dock"),
    "greenhouse": ("bay 2", "the potting bench"),
    "locksmith": ("the key shop", "the van"),
    "pantry": ("the pantry", "the back dock"),
    "tailor": ("the alterations shop", "the fitting room"),
    "telescope": ("the dark site", "the clubhouse"),
}
THINGS = {
    "apiary": ("the extractor", "the spare supers"),
    "rink": ("the skate sharpener", "the spare pucks"),
    "kiln": ("the glaze buckets", "the shelf posts"),
    "orchard": ("the extra crates", "the orchard ladders"),
    "tow": ("the jump pack", "the dolly set"),
    "theater": ("the gaff tape", "the prop crates"),
    "courier": ("the spare bag", "the u-lock"),
    "laundry": ("the quarters", "the new belt"),
    "print": ("the proofs", "the toner"),
    "rowing": ("the coxbox", "the slings"),
    "piano": ("the piano board", "the moving blankets"),
    "greenhouse": ("the seedling trays", "the shade cloth"),
    "locksmith": ("the key blanks", "the pick set"),
    "pantry": ("the hand trucks", "the intake forms"),
    "tailor": ("the dress form", "the steamer"),
    "telescope": ("the dob", "the red flashlights"),
}
SPOTS_RU = {
    "apiary": ("на пасеке", "у ульев"),
    "rink": ("на катке", "у проката"),
    "kiln": ("в мастерской", "у печи"),
    "orchard": ("в саду", "у пресса"),
    "tow": ("на стоянке", "у офиса"),
    "laundry": ("в прачечной", "у сушилок"),
    "print": ("в типографии", "у резака"),
    "greenhouse": ("в теплице", "у рассады"),
}
THINGS_RU = {
    "apiary": ("медогонку", "запасные рамки"),
    "rink": ("точилку", "запасные шайбы"),
    "kiln": ("глазурь", "подставки"),
    "orchard": ("ящики", "лестницы"),
    "tow": ("пусковое", "тележки"),
    "laundry": ("монеты", "новый ремень"),
    "print": ("пробники", "тонер"),
    "greenhouse": ("кассеты", "сетку"),
}

_CUE = re.compile(r"\[([^\]]+)\]")


def cue_split(marked: str) -> tuple[str, str]:
    """('its neve quarrie, new number', 'its neve quarrie') from '[its neve quarrie], new
    number': the record text and the cue span the item quotes."""
    found = _CUE.findall(marked)
    if len(found) != 1:
        raise ValueError(f"one cue span expected: {marked!r}")
    return _CUE.sub(r"\1", marked), found[0]


def fill(template: str, **values: str) -> str:
    """str.format for the slots a template uses; unused values are ignored."""
    return template.format_map(values)
