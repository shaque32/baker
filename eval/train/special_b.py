"""English hand-written scenarios, part 2: jokes, counts, inferences, relative time, states.
Same slots as special.py."""

from __future__ import annotations

from eval.train.special import NAMES, S

JOKE = (
    S(
        "ovr_joke",
        "robbing a bank obviously lol",
        "{S} robbed a bank on {date}.",
        "The owner asks where the sender was; the record's own 'lol' marks the answer as a joke.",
        before=(("o", "where were u all afternoon??"),),
        after=(("o", "lol"),),
    ),
    S(
        "ovr_joke",
        "sold a kidney lmao",
        "{S} sold a kidney.",
        "An obvious joke in answer to a money question, marked by 'lmao'; nothing shown treats "
        "it as real.",
        before=(("o", "how'd u afford the new rims"),),
        after=(("o", "😂"),),
    ),
    S(
        "ovr_joke",
        "yeah i paid {x} in monopoly money haha",
        "{S} paid {X} in counterfeit money.",
        "'Haha' and monopoly money mark the record as a joke; nothing shown treats it as real.",
        before=(("o", "did u pay {x} back"),),
        xs=NAMES,
    ),
    S(
        "ovr_joke",
        "i torched the old place, easier than cleaning lol",
        "{S} set fire to {poss} old apartment.",
        "'Lol' marks the record as a joke; nothing shown treats it as real.",
        before=(("o", "hows the move going"),),
        after=(("o", "lol"),),
    ),
    S(
        "ovr_joke",
        "cant, im in jail 😂",
        "{S} was in jail.",
        "The '😂' marks the record as a joke; nothing shown says the sender was in jail.",
        before=(("o", "u coming to the game"),),
        after=(("o", "lol ok"),),
    ),
    S(
        "ovr_joke",
        "im gonna burn his house down i swear lol",
        "{S} threatened to burn down the landlord's house.",
        "'Lol' and 'i swear' mark the record as venting, not a threat.",
        before=(("c", "my landlord raised rent again"),),
        after=(("o", "lol same"),),
    ),
    S(
        "ovr_joke",
        "like a thousand lol",
        "{S} saw a thousand clients on {date}.",
        "'Like a thousand lol' is hyperbole; nothing shown treats it as a count.",
        before=(("o", "how many clients today"),),
    ),
    S(
        "ovr_joke",
        "yes i stole it and sold it on ebay 🙄",
        "{S} stole {O}'s charger and sold the charger on ebay.",
        "The '🙄' marks the record as sarcasm; nothing shown treats it as real.",
        before=(("o", "did u take my charger"),),
    ),
    S(
        "ovr_joke",
        "yep blind drunk, hit three mailboxes lol",
        "{S} drove home drunk after the party.",
        "'Lol' marks the record as a joke; nothing shown treats it as real.",
        before=(("o", "u drove home after the party right?"),),
        after=(("o", "lol"),),
    ),
    S(
        "ovr_joke",
        "sure ill just rob the bar till lol",
        "The owner planned to rob the bar's till.",
        "'Lol' marks the owner's line as a joke about the cost; nothing shown treats it as a plan.",
        before=(("c", "the dj wants 1200"),),
        who="o",
    ),
)

COUNT = (
    S(
        "ovr_count",
        "dropped it by noon like always",
        "{S} made a delivery before noon every week in {month}.",
        "The record shows one drop and a loose 'like always'; it does not show every week.",
    ),
    S(
        "ovr_count",
        "same as every friday, 2 bags",
        "{S} delivered two bags every Friday that year.",
        "One Friday is shown; 'every friday' is the sender's loose phrase, not a record of each.",
    ),
    S(
        "ovr_count",
        "went this morning before work, like always",
        "{S} went to the gym every day in {month}.",
        "One visit and a loose 'like always' are shown; the other days are not.",
        before=(("o", "u still going to the gym"),),
    ),
    S(
        "ovr_count",
        "paid {x} like i always do",
        "{S} paid {X} every month.",
        "The record shows one payment and a loose phrase; the other months are not shown.",
        xs=NAMES,
    ),
    S(
        "ovr_count",
        "did the thursday run again, like always",
        "{S} and {O} met every week in {month}.",
        "One run and a loose 'like always' are shown; the other weeks are not.",
    ),
    S(
        "ovr_count",
        "{x}s late again, every single time",
        "{X} was late every day that week.",
        "One instance plus a loose complaint; the other days are not shown.",
        xs=NAMES,
    ),
    S(
        "ovr_count",
        "took the kids this morning, like always",
        "{S} took the kids every morning that month.",
        "One morning and a loose phrase are shown; the other mornings are not.",
    ),
    S(
        "ovr_count",
        "8 clients today, same as always",
        "{S} did 8 clients every day.",
        "One day's count and a loose 'same as always' are shown; no other days are.",
    ),
    S(
        "ovr_count",
        "went again today, like always",
        "{S} went every day.",
        "One visit and a loose 'like always' are shown; the other days are not.",
    ),
)

INFERENCE = (
    S(
        "cpl_inference",
        "70 and sunny, staying another week",
        "{S} was in Phoenix on {date}.",
        "Warm weather does not name the city; the place is an inference.",
    ),
    S(
        "cpl_inference",
        "left the keys on the hook, van's gassed up",
        "{S} drove the van that day.",
        "Keys and a full tank suggest a drive but do not show one.",
    ),
    S(
        "cpl_inference",
        "i dont work there anymore",
        "{S} quit the bar job.",
        "Not working there any more could be quitting or being let go.",
    ),
    S(
        "cpl_inference",
        "landed. ugh humidity",
        "{S} was in Miami.",
        "Humidity does not name the city.",
    ),
    S(
        "cpl_inference",
        "the lights were on at {x}s place at 2am",
        "{X} was home at 2 a.m. on {date}.",
        "A light on is an inference about who was home, not an observation.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "my card got declined at the gas station",
        "{S} had no money on {date}.",
        "A declined card can have many causes; no balance is shown.",
    ),
    S(
        "cpl_inference",
        "smells like weed in the hallway again",
        "The neighbor was smoking cannabis in the hallway.",
        "A smell does not show who was smoking or where.",
    ),
    S(
        "cpl_inference",
        "the corollas not in the driveway",
        "{X} took the Corolla.",
        "A missing car does not show who took it.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "{x} showed up with a black eye",
        "{X} was in a fight.",
        "A black eye has other causes; the fight is an inference.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "{x}s bags are by the door",
        "{X} was moving out.",
        "Packed bags suggest a departure but do not show a move.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "3 missed calls from the landlord",
        "The landlord was angry about the rent.",
        "Missed calls show no reason; the rent and the anger are inferred.",
    ),
)

RELATIVE_TIME = (
    S(
        "cpl_relative_time",
        "dropped the keys off last night",
        "{S} dropped the keys off on {date}.",
        "Sent at {clock}, just after midnight; 'last night' may mean either of two evenings.",
    ),
    S(
        "cpl_relative_time",
        "paid {x} last night",
        "{S} paid {X} on {prev}.",
        "Sent at {clock}; 'last night' at that hour could be the evening before or two before.",
        xs=NAMES,
    ),
    S(
        "cpl_relative_time",
        "fixed the sink tonight",
        "{S} fixed the sink on {date}.",
        "Sent at {clock} after midnight; 'tonight' straddles two dates.",
    ),
    S(
        "cpl_relative_time",
        "sent the rent yesterday",
        "{S} paid the rent on {prev}.",
        "Sent at {clock}, right after midnight; the sender may still count the earlier date as "
        "today.",
    ),
    S(
        "cpl_relative_time",
        "got back from the airport tonight",
        "{S} returned from the airport on {date}.",
        "Sent at {clock}; 'tonight' may fall on either side of midnight.",
    ),
    S(
        "cpl_relative_time",
        "picked the kids up last night around 11",
        "{S} picked the kids up on {prev}.",
        "Sent at {clock}; which evening 'last night' names depends on the sender.",
    ),
)

OTHER_STATE = (
    S(
        "con_other_state",
        "been home in queens since sunday",
        "{S} was still in Lisbon on {date}.",
        "Being home since Sunday cannot hold with still being in Lisbon on {date}.",
    ),
    S(
        "con_other_state",
        "im at the shop now, car wont be done till 5",
        "{S} was at the airport at {clock} on {date}.",
        "The record places the sender at the shop at that moment.",
    ),
    S(
        "con_other_state",
        "quit the bar 2 weeks ago",
        "{S} worked a shift at the bar on {date}.",
        "Having quit two weeks earlier rules out a shift on {date}.",
    ),
    S(
        "con_other_state",
        "the vans been at the garage all week",
        "{S} drove the van to Boston on {date}.",
        "A van at the garage all week cannot have been driven to Boston on {date}.",
    ),
    S(
        "con_other_state",
        "sold the corolla in march",
        "{S} still owned the Corolla on {date}.",
        "Sold in March cannot hold with still owning it on {date}.",
    ),
    S(
        "con_other_state",
        "still in the hospital, 3rd day",
        "{S} was at work on {date}.",
        "The sender was in the hospital at the time, not at work.",
    ),
    S(
        "con_other_state",
        "we moved out of the 3rd floor place last month",
        "{S} lived in the 3rd-floor apartment on {date}.",
        "Having moved out the month before rules out living there on {date}.",
    ),
    S(
        "con_other_state",
        "ive been off the gym since the surgery, 2 months now",
        "{S} was at the gym on {date}.",
        "Two months away from the gym cannot hold with being there on {date}.",
    ),
    S(
        "con_other_state",
        "flight got cancelled, still in denver",
        "{S} landed in New York on {date}.",
        "Still being in Denver rules out having landed in New York by the message.",
    ),
    S(
        "con_other_state",
        "never had a car, i take the bus everywhere",
        "{S} drove {poss} own car to the wedding.",
        "Never having had a car rules out driving one's own car.",
    ),
    S(
        "con_other_state",
        "the salons been closed since the flood, 3 weeks",
        "{S} did clients at the salon on {date}.",
        "A salon closed for three weeks rules out clients there on {date}.",
    ),
    S(
        "con_other_state",
        "im still in lisbon, flight is thursday",
        "{S} was in New York on {date}.",
        "Still being in Lisbon rules out being in New York at the time of the message.",
    ),
)
