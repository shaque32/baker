"""Wording for the role and event templates (guide rule 29): the acts and roles a claim states,
and the records that bear on them or deny them. SYNTHETIC.

An act or a role is never a message or a call, so no message can be it. Lines "from" the person
the claim names plan, report or describe the act or role (they bear on it and settle nothing:
a message shows what was said); lines "to" them ask or tell them about it. DENY lines rule it
out in the person's own words for all time before they were sent; DENY_DAY and ALIBI lines rule
it out for the dates they name. Slots: {z} another person's surname as texted ({Z} in a claim),
{spot} {thing} from the situation, {hh} a clock time, {day} a date as texted ("march 3"),
{first} {last} two dates as texted, {city} a city. Brackets mark the clause an item quotes
when the rest of the line adds nothing to the answer (guide rule 7).
"""

from __future__ import annotations

ACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "meet": {
        "claim": ("met {Z} at {spot}",),
        "q": ("meet {z} at {spot}",),
        "past": ("met {z} at {spot}",),
        "plan": ("meeting {z} at {spot} at {hh}", "ill see {z} at {spot} around {hh}",
                 "heading to {spot} to meet {z}"),
        "did": ("[met {z} at {spot}], all sorted", "[saw {z} at {spot}], done",
                "just left {spot}, {z} was there"),
        "ask": ("did u meet {z} at {spot}?", "r u still meeting {z} at {spot}?",
                "did {z} show up at {spot}?"),
        "tell": ("meet {z} at {spot} at {hh}", "go see {z} at {spot} before {hh}"),
        "deny": ("[i never met {z} at {spot}], not once",
                 "[never met up with {z} anywhere], {spot} or otherwise"),
        "deny_day": ("[i didnt meet {z} on {day}], wasnt at {spot} at all",
                     "didnt see {z} at {spot} on {day} or any other day"),
    },
    "hand": {
        "claim": ("handed {Z} {thing} at {spot}",),
        "q": ("give {z} {thing}",),
        "past": ("gave {z} {thing}",),
        "plan": ("bringing {thing} for {z} to {spot}", "ill give {z} {thing} at {spot}",
                 "{thing} is in my bag for {z}"),
        "did": ("gave {z} {thing} at {spot}", "{z} has {thing} now, handed it over at {spot}",
                "[handed off {thing} to {z}], all good"),
        "ask": ("did {z} get {thing} from u?", "did u give {z} {thing}?",
                "has {z} got {thing} yet?"),
        "tell": ("give {thing} to {z} at {spot}", "hand {z} {thing} when u see them"),
        "deny": ("[i never gave {z} {thing}], never had it",
                 "[never handed {z} anything], not at {spot} or anywhere"),
        "deny_day": ("[i didnt give {z} anything on {day}], wasnt even at {spot}",),
    },
    "drive": {
        "claim": ("drove {Z} to {spot}",),
        "q": ("drive {z} to {spot}",),
        "past": ("drove {z} to {spot}",),
        "plan": ("picking {z} up at {hh}, then {spot}", "ill drive {z} to {spot} after work",
                 "giving {z} a ride to {spot} at {hh}"),
        "did": ("dropped {z} at {spot}", "[drove {z} over to {spot}], done",
                "{z} is at {spot} now, gave them a lift"),
        "ask": ("did u drive {z} to {spot}?", "is {z} getting a ride to {spot} from u?"),
        "tell": ("drive {z} to {spot} at {hh}", "take {z} to {spot} when ur free"),
        "deny": ("[i never drove {z} anywhere], not once",
                 "[never gave {z} a ride], not to {spot}"),
        "deny_day": ("[i didnt drive anyone on {day}], my car was in the shop",),
    },
    "pickup": {
        "claim": ("picked up {thing} from {Z} at {spot}",),
        "q": ("pick up {thing} from {z}",),
        "past": ("picked up {thing} from {z}",),
        "plan": ("grabbing {thing} from {z} at {spot}", "ill get {thing} off {z} at {spot}",
                 "on my way to {spot} for {thing}, {z} has it"),
        "did": ("[got {thing} from {z}], its in my trunk", "picked up {thing} from {z} at {spot}",
                "{thing} is with me now, {z} handed it over"),
        "ask": ("did u get {thing} from {z}?", "do u have {thing} from {z} yet?"),
        "tell": ("get {thing} from {z} at {spot}", "pick up {thing} from {z} before {hh}"),
        "deny": ("[never picked anything up from {z}], ever",
                 "[i never got {thing} from {z}], never did"),
        "deny_day": ("i didnt pick anything up from {z} on {day}",),
    },
    "pay": {
        "claim": ("paid {Z} in cash at {spot}",),
        "q": ("pay {z} in cash",),
        "past": ("paid {z} in cash",),
        "plan": ("bringing {z} the cash at {spot}", "ill pay {z} at {spot} at {hh}",
                 "cash for {z} is in the envelope"),
        "did": ("paid {z} at {spot}, cash", "{z} got paid, cash, at {spot}",
                "[handed {z} the cash], we're square"),
        "ask": ("did u pay {z}?", "did {z} get the cash from u?", "is {z} paid up?"),
        "tell": ("pay {z} at {spot}", "take the cash to {z} at {spot} at {hh}"),
        "deny": ("[never paid {z} a cent], ever", "[i never gave {z} any cash], not at {spot}"),
        "deny_day": ("[i didnt pay {z} anything on {day}], not a cent",),
    },
    "key": {
        "claim": ("gave {Z} the key to {spot}",),
        "q": ("give {z} the key to {spot}",),
        "past": ("gave {z} the key to {spot}",),
        "plan": ("leaving the key to {spot} with {z}", "ill pass {z} the key to {spot}",
                 "spare key to {spot} is going to {z}"),
        "did": ("gave {z} the key to {spot}", "{z} has the key to {spot} now",
                "key to {spot} is with {z}"),
        "ask": ("does {z} have the key to {spot}?", "did u give {z} the key?"),
        "tell": ("give {z} the key to {spot}", "leave the key to {spot} with {z}"),
        "deny": ("never gave {z} a key to anything", "i never gave {z} the key to {spot}"),
        "deny_day": ("[i didnt give {z} any key on {day}], still have both of mine",),
    },
}  # fmt: skip

ROLES: dict[str, dict[str, tuple[str, ...]]] = {
    "driver": {
        "claim": ("drove for {Z}, making the runs to {spot}",),
        "q": ("drive for {z}",),
        "past": ("drove for {z}",),
        "from": ("doing the run to {spot} for {z} at {hh}", "did two runs to {spot} for {z}",
                 "van's loaded, [heading to {spot} for {z}]"),
        "to": ("can u do {z}'s run to {spot} at {hh}?", "r u still driving for {z}?",
               "{z} needs a driver for {spot} at {hh}, u in?"),
        "deny": ("[i never drove for {z}], not once", "[never did a single run for {z}], ever"),
    },
    "cash": {
        "claim": ("held the cash for {Z}",),
        "q": ("hold cash for {z}",),
        "past": ("held cash for {z}",),
        "from": ("[{z}'s cash is with me], counted it twice", "holding {z}'s money for now",
                 "put {z}'s cash in the safe at {spot}"),
        "to": ("do u still have {z}'s cash?", "can u hold the cash for {z} again?",
               "how much of {z}'s money do u have?"),
        "deny": ("[never held cash for {z}], never touched their money",
                 "[i never kept a dollar for {z}], ever"),
    },
    "watch": {
        "claim": ("kept watch at {spot} for {Z}",),
        "q": ("keep watch for {z}",),
        "past": ("kept watch for {z}",),
        "from": ("at {spot}, all quiet, ill text {z} if anyone comes",
                 "[watching {spot} for {z}], nothing yet",
                 "still out at {spot} keeping an eye out for {z}"),
        "to": ("can u watch {spot} for {z} at {hh}?", "r u keeping an eye on {spot} for {z}?",
               "{z} wants someone at {spot} at {hh}, can u?"),
        "deny": ("[i never kept watch for {z}], anywhere",
                 "[never stood watch for {z}], not at {spot}, not anywhere"),
    },
    "messages": {
        "claim": ("carried messages for {Z}",),
        "q": ("carry messages for {z}",),
        "past": ("carried messages for {z}",),
        "from": ("[told {z} what u said], they're fine with it", "passed ur note on to {z}",
                 "{z} got ur message from me"),
        "to": ("can u pass this on to {z}?", "tell {z} we're still on",
               "let {z} know the answer is yes"),
        "deny": ("[never passed anything on for {z}], i dont even talk to them",
                 "[i never carried a message for {z}], ever"),
    },
    "keys": {
        "claim": ("held the keys to {spot} for {Z}",),
        "q": ("hold the keys to {spot} for {z}",),
        "past": ("held the keys to {spot} for {z}",),
        "from": ("[i have the keys to {spot}], opening at {hh}", "locked up {spot} for {z}",
                 "got the keys to {spot} from {z}"),
        "to": ("u still have the keys to {spot}?", "can u open {spot} for {z} at {hh}?"),
        "deny": ("[never had keys to {spot}], not once",
                 "i never held a key to {spot} for {z} or anyone"),
    },
    "books": {
        "claim": ("kept the books for {Z}",),
        "q": ("keep the books for {z}",),
        "past": ("kept the books for {z}",),
        "from": ("[updated {z}'s sheet], 3 payments missing",
                 "[logged {z}'s numbers], all balanced", "{z}'s ledger is done"),
        "to": ("did u update {z}'s sheet?", "can u log the numbers for {z}?",
               "is {z}'s ledger balanced?"),
        "deny": ("[never kept any books for {z}], never saw their numbers",
                 "[i never did {z}'s books], not once"),
    },
}  # fmt: skip

# Placing oneself elsewhere for the whole of the claim's dates, away from the place it names.
ALIBI_DAY = (
    "i was in {city} all day on {day}, nowhere near {spot}",
    "spent all of {day} in {city}, never went near {spot}",
    "on {day} i was in {city} from morning to night, not at {spot}",
)
ALIBI_SPAN = (
    "i was in {city} from {first} to {last}, the whole time, nowhere near {spot}",
    "from {first} to {last} i was in {city}, never went near {spot}",
)
CITIES = ("reno", "boise", "fresno", "spokane", "tulsa", "omaha", "tucson", "duluth",
          "albany", "savannah", "billings", "flagstaff")  # fmt: skip
HOURS = ("5", "6", "6:30", "7", "8", "9", "10")

# Lines the other side writes around these records: an opener before, an acknowledgement
# after; neither names a time nor answers anything.
OPENERS = ("hey", "yo", "hey u around", "quick one", "hi", "u there?")
ACKS = ("ok", "got it", "k", "alright", "noted", "ok thx", "understood")
# The other side asking about the act before a denial; it names no time.
ASK_DENY = (
    "did u ever {act_q}?",
    "ppl are saying u {act_past}",
    "be honest, did u {act_q}?",
)
