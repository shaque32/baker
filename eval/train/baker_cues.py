"""Records that carry a cue about people: names, who is typing, handle changes. All invented.

Surnames of named persons (person:<surname>) and every first name start with A to M (Russian А
to Л), like the rest of eval/train. Identity lines always give the surname of the person the
assumption names; typing cues always give the typist's first name; handle lines always give
every handle the assumption lists, exactly as it writes them.
"""

from __future__ import annotations

SURNAMES: tuple[str, ...] = (
    "adair", "ahern", "albrecht", "aldana", "amsel", "ardito", "ashby", "aubert", "bakshi",
    "balder", "barlow", "bastida", "beaumont", "belcher", "benning", "birch", "blaylock",
    "boateng", "brandt", "calder", "callis", "carrow", "castell", "cavanagh", "chaudry",
    "colby", "corwin", "crane", "dacosta", "dahl", "daley", "darrow", "deane", "dembele",
    "dorsey", "draper", "duarte", "eastman", "eberly", "eckert", "edris", "elkins", "ellery",
    "emberly", "esposito", "everett", "fairley", "falk", "farrow", "fenwick", "fiore",
    "fischer", "foley", "fontaine", "gable", "galloway", "garrity", "geller", "gilchrist",
    "gorman", "granger", "greer", "guzman", "hadley", "halloran", "hargrove", "haskell",
    "hayward", "hendry", "huang", "ibarra", "ingram", "irving", "ivers", "jaffe", "janssen",
    "jarvis", "jessup", "juarez", "kapoor", "keane", "kellerman", "kendrick", "kessler",
    "kimura", "kirkland", "koval", "kruger", "lachance", "lambert", "landry", "larkin",
    "leclerc", "lennox", "lindgren", "lockhart", "lowery", "lyle", "macklin", "maddox",
    "mahler", "marchetti", "mccall", "mendel", "merritt", "molina", "montague", "moretti",
    "mulvaney",
)  # fmt: skip

# The sender gives the named person's name: {first} a first name, {Sur} the capitalized surname.
ID_CUES: tuple[str, ...] = (
    "[its {first} {Sur}] btw, new number",
    "hey [this is {first} {Sur}] from {place}",
    "[{Sur} here], got ur msg",
    "[{first} {Sur} here], the {item} guy",
    "[this is {first} {Sur}], my cousin gave me ur number",
    "[yes this is {first} {Sur}]",
    "[yep its me, {first} {Sur}]",
    "u can [save me as {first} {Sur}]",
    "sry forgot to say, [its {first} {Sur}]",
    "hi! [{first} {Sur} from upstairs]",
    "[my name is {first} {Sur}], i called about the {item}",
    "[{first} {Sur} speaking]",
    "[{Sur} from the shop], ur order is in",
    "[ya its {Sur}], who else",
    "[sorry its {first} {Sur}], i changed phones",
    "[{first} {Sur} here], we met at {place}",
    "[this is {Sur}], returning ur call",
    "[it's {first} {Sur}], the landlord gave me this number",
    "hey [{first} {Sur} here], is the room still available",
    "[{Sur} again], did the payment go through",
    "[its {Sur}], save this one",
    "[{first} {Sur} on my new phone]",
    "[this is {first} {Sur} from the building]",
    "[hi its {first} {Sur}] from {place}",
    "[{first} {Sur} here], about the {item} u posted",
    "[{Sur} here], about the lease",
    "[{Sur} from the clinic], returning ur call",
    "[its {first} {Sur}], we spoke at {place}",
    "[{first} {Sur}, the new tenant]",
    "[coach {Sur} here], practice is still on",
)
# A line from the other party that calls the sender by the name, shown before the record.
CALLED_BY_NAME: tuple[str, ...] = (
    "is this {first} {Sur}?",
    "{first} {Sur}? ur sister passed me this number",
    "{Sur}? its about the {item}",
    "hey {first} {Sur}, quick question",
    "{first} {Sur}, right?",
    "hi, looking for {first} {Sur}",
)

# Someone other than the usual user is typing, or the line is signed. {first} is the typist;
# {other} the person they type for, with {pron} and {poss} for {other}; {rel} fits {first}.
AUTHOR_CUES: tuple[str, ...] = (
    "[its {first}, {other} left {poss} phone at my place]",
    "[this is {first}, {other}s {rel}], {pron}s driving",
    "[{first} here on {other}s phone]",
    "[{first} typing for {other}], {pron} cant text rn",
    "[{other} gave me {poss} phone, its {first}]",
    "[not {other}, its {first}], {pron} forgot {poss} phone",
    "[{other} is in the shower, its {first}]",
    "[its {first} using this phone], mine died",
    "[{first} sending this for {other}]",
    "[{first} again on {other}s phone]",
    "[{other} asked me to text u, its {first}]",
    "[{first} speaking, {other} is busy]",
    "[{other} is asleep, its {first}]",
    "[ignore that last text, {first} sent it]",
    "[{first} here], {other} lent me the phone",
    "[im {other}s {rel} {first}], {pron} asked me to answer",
    "see u soon, [love {first}]",
    "[{ordinary} -{first}]",
    "[{first} on the family phone]",
    "[this is {first}, i have {other}s phone today]",
    "[{first} here, {other} handed me the phone]",
    "[its {first} not {other}]",
    "[{other} told me to answer, its {first}]",
    "[{first} from the front desk using this phone]",
)
# Russian typing cues; names in the nominative, {e} the past-tense ending for {other}.
AUTHOR_CUES_RU: tuple[str, ...] = (
    "[это {first}, {other} оставил{e} телефон у меня]",
    "[{other} в душе, это {first}]",
    "[это {first}, {other} за рулём]",
    "[не {other}, это {first}]",
    "[{other} спит, пишет {first}]",
    "[это {first}, {other} забыл{e} телефон дома]",
)
RELS = {
    "she": ("sister", "cousin", "roommate", "mom", "aunt", "niece", "coworker"),
    "he": ("brother", "cousin", "roommate", "dad", "uncle", "nephew", "coworker"),
}

# One handle became another, or two handles are one account; {h1}, {h2}, {h3} as written.
# A line with "my" or "i" (Russian: a verb ending in {e}) is the account speaking.
HANDLES_SAID: tuple[str, ...] = (
    "[changed my @ from {h1} to {h2}]",
    "[{h1} is now {h2}], same account",
    "[renamed the page from {h1} to {h2}]",
    "[{h2} is the same acct as {h1}], just a new name",
    "[it used to be {h1}, now its {h2}]",
    "[if u cant find {h1} its {h2} now]",
    "[{h1} and {h2} are the same account], she just changed the name",
    "[he switched his handle from {h1} to {h2}]",
    "[{h1} → {h2}], updated my username",
    "[same account, i just went from {h1} to {h2}]",
    "[follow {h2}, thats {h1} renamed]",
    "[{h1} got renamed to {h2}]",
    "[the shop page {h1} is {h2} now], same page",
    "[updated my handle: {h1} is now {h2}]",
    "[{h1} and {h2} are one account], dont follow twice",
    "[she renamed {h1} to {h2}]",
)
HANDLES_SAID_3: tuple[str, ...] = (
    "[went from {h1} to {h2} and now {h3}]",
    "[{h1}, {h2} and {h3} are all the same account]",
    "[it was {h1}, then {h2}, now its {h3}]",
)
HANDLES_SAID_RU: tuple[str, ...] = (
    "[сменил{e} ник с {h1} на {h2}]",
    "[{h1} теперь {h2}], аккаунт тот же",
    "[переименовал{e} страницу: была {h1}, стала {h2}]",
    "[{h1} и {h2} это один аккаунт]",
    "[теперь я {h2}, раньше был{e} {h1}]",
)

# Phrases whose meaning a claim might argue about; ordinary words, nothing decoded.
VAGUE: tuple[str, ...] = (
    "[same spot as last time]", "[bring the paperwork] when u come",
    "[need {n} more of the {color} ones]", "[the thing is ready] whenever",
    "[did u handle that yet]", "[ill take care of it], dont worry",
    "[is the package good to go]", "[tell him the usual]", "[we're square now]",
    "[the guy came through]", "[it went fine], talk later", "[it goes in the back, like before]",
    "[make sure its clean this time]", "[got the stuff from the guy]",
    "[keep it quiet for now]", "[the {color} bag is for u]", "[ask him if hes still in]",
    "[same as before, half now half later]", "[the delivery is set]",
    "[we're good on the other thing]", "[need the rest by end of month]",
    "[bring the extra just in case]", "[he knows what its for]", "[the order is in]",
    "[last batch was short]", "[tell her its handled]",
    "[its sitting in the {color} {vehicle}]", "[got {n} for u], come thru",
    "[the usual amount]", "[dont bring it inside]", "[the big one or the small one?]",
    "[he wants the same deal]", "[its taken care of]", "[we need to talk about the thing]",
    "[leave it with the doorman like before]", "[the stuff for the party is here]",
)  # fmt: skip
