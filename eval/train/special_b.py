"""English hand-written scenarios, part 2: jokes, counts, inferences, relative time, states.
Same slots as special.py."""

from __future__ import annotations

from eval.train.special import MON_TO_THU, NAMES, S

JOKE = (
    # Rationales say what the marker leaves open and never call the record a joke, venting or
    # harmless (guide rule 24).
    S(
        "ovr_joke",
        "robbing a bank obviously lol",
        "{S} robbed a bank on {date}.",
        "The record's 'lol', and the owner's 'lol' after it, leave it unclear whether the sender "
        "meant it seriously, so the record does not establish a bank robbery.",
        before=(("o", "where were u all afternoon??"),),
        after=(("o", "lol"),),
    ),
    S(
        "ovr_joke",
        "sold a kidney lmao",
        "{S} sold a kidney. || Before {next}, {S} sold a kidney.",
        "The 'lmao' and the owner's laughing reply leave it unclear whether the sender meant it "
        "seriously; the record does not establish that a kidney was sold.",
        before=(("o", "how'd u afford the new rims"),),
        after=(("o", "😂"),),
    ),
    S(
        "ovr_joke",
        "yeah i paid {x} in monopoly money haha",
        "{S} paid {X} in counterfeit money. || Before {next}, {S} paid {X} in counterfeit money.",
        "The 'haha' leaves it unclear whether the sender meant it seriously, so the record does "
        "not establish a payment in counterfeit money.",
        before=(("o", "did u pay {x} back"),),
        xs=NAMES,
    ),
    S(
        "ovr_joke",
        "i torched the old place, easier than cleaning lol",
        "{S} set fire to {poss} old place. || Before {next}, {S} set fire to {poss} old place.",
        "The record's 'lol' and the owner's laughing reply leave it unclear whether the sender "
        "meant it seriously; the record does not establish a fire.",
        before=(("o", "hows the move going"),),
        after=(("o", "lol"),),
    ),
    S(
        "ovr_joke",
        "cant, im in jail 😂",
        "{S} was in jail. || {S} was in jail on {date}.",
        "The '😂' and the owner's 'lol ok' leave it unclear whether the sender meant it "
        "seriously, so the record does not establish that the sender was in jail.",
        before=(("o", "u coming to the game"),),
        after=(("o", "lol ok"),),
    ),
    S(
        "ovr_joke",
        "im gonna burn his house down i swear lol",
        "{S} threatened to burn down the landlord's house. || On {date}, {S} threatened to burn "
        "down the landlord's house.",
        "The 'lol', and the owner's 'lol same', leave it unclear whether the sender meant it "
        "seriously, so the record does not establish a threat.",
        before=(("c", "my landlord raised rent again"),),
        after=(("o", "lol same"),),
    ),
    S(
        "ovr_joke",
        "like a thousand lol",
        "{S} saw a thousand clients on {date}.",
        "The 'lol' leaves it unclear whether the sender meant the number seriously, so the "
        "record does not establish a count.",
        before=(("o", "how many clients today"),),
    ),
    S(
        "ovr_joke",
        "yes i stole it and sold it on ebay 🙄",
        "{S} stole {O}'s charger and sold the charger on ebay. || Before {next}, {S} stole "
        "{O}'s charger and sold the charger on ebay.",
        "The eye-roll '🙄' leaves it unclear whether the sender meant it seriously, so the record "
        "does not establish a theft or a sale.",
        before=(("o", "did u take my charger"),),
    ),
    S(
        "ovr_joke",
        "yep blind drunk, hit three mailboxes lol",
        "{S} drove home drunk after the party. || Before {next}, {S} drove home drunk after the "
        "party.",
        "The record's 'lol' and the owner's laughing reply leave it unclear whether the sender "
        "meant it seriously; the record does not establish a drunk drive.",
        before=(("o", "u drove home after the party right?"),),
        after=(("o", "lol"),),
    ),
    S(
        "ovr_joke",
        "sure ill just rob the bar till lol",
        "The owner planned to rob the bar's till. || On {date}, the owner planned to rob the "
        "bar's till.",
        "The 'lol' leaves it unclear whether the owner meant it seriously, so the record does not "
        "establish a plan to rob the till.",
        before=(("c", "the dj wants 1200"),),
        who="o",
    ),
)

COUNT = (
    # A record that names a weekday is sent on that day; the rationale says what is shown (one
    # message and a loose phrase) and names no weekday outside the record's own words.
    S(
        "ovr_count",
        "dropped the kids at school by 8 like always",
        "{S} dropped the kids at school by 8 a.m. every weekday in {month}.",
        "The record shows one drop-off and a loose 'like always'; it does not show the other days.",
        days=(0, 1, 2, 3, 4),
    ),
    S(
        "ovr_count",
        "same as every friday, 2 bags",
        "{S} dropped off two bags of laundry every Friday in {month}.",
        "The record is one message using the loose phrase 'same as every friday'; it does not "
        "show a drop-off on each of the days the assumption covers.",
        before=(("o", "how many bags of laundry did u drop off"),),
        days=(4,),
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
        "{S} did the Thursday run every week in {month}.",
        "One message about 'the thursday run' and a loose 'like always' are shown; the other "
        "weeks are not.",
        days=(3, 4),
    ),
    S(
        "ovr_count",
        "{x}s late again, every single time",
        "{X} was late every day in the week of {date}.",
        "One instance plus a loose complaint; the other days are not shown.",
        xs=NAMES,
    ),
    S(
        "ovr_count",
        "took the kids this morning, like always",
        "{S} took the kids every morning in {month}.",
        "One morning and a loose phrase are shown; the other mornings are not.",
    ),
    S(
        "ovr_count",
        "8 clients today, same as always",
        "{S} had 8 clients every day in {month}.",
        "One day's count and a loose 'same as always' are shown; no other days are.",
    ),
    S(
        "ovr_count",
        "went again today, like always",
        "{S} went every day in {month}.",
        "One visit and a loose 'like always' are shown; the other days are not.",
    ),
)

INFERENCE = (
    # The assumption infers something about what the record is about, never about a subject
    # the record does not name (a neighbor nobody mentions, a car nobody is said to take).
    S(
        "cpl_inference",
        "70 and sunny, staying another week",
        "{S} was in Phoenix on {date}.",
        "Warm weather does not name the city; the place is an inference.",
    ),
    S(
        "cpl_inference",
        "left the keys on the hook, van's gassed up",
        "{S} drove the van on {date}. || {S} drove the van.",
        "Keys and a full tank suggest a drive but do not show one.",
    ),
    S(
        "cpl_inference",
        "i dont work there anymore",
        "{S} quit {poss} job at the bar. || Before {next}, {S} quit {poss} job at the bar.",
        "Not working there any more could be quitting or being let go.",
        before=(("o", "u still at the bar on 5th?"),),
    ),
    S(
        "cpl_inference",
        "landed. ugh humidity",
        "{S} was in Miami on {date}. || {S} was in Miami.",
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
        "Someone smoked cannabis in the hallway on {date}. || Someone smoked cannabis in the "
        "hallway.",
        "A smell does not show that anyone smoked there, or when.",
    ),
    S(
        "cpl_inference",
        "{x} left an hour ago, the corollas not in the driveway",
        "{X} took the Corolla on {date}. || {X} took the Corolla.",
        "The record says {x} left and the Corolla is gone; it does not say {x} took it.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "{x} showed up with a black eye",
        "{X} was in a fight. || Before {next}, {X} was in a fight.",
        "A black eye has other causes; the fight is an inference.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "{x}s bags are by the door",
        "{X} was moving out. || On {date}, {X} was moving out.",
        "Packed bags suggest a departure but do not show a move.",
        xs=NAMES,
    ),
    S(
        "cpl_inference",
        "3 missed calls from the landlord",
        "The landlord was angry with {S}. || On {date}, the landlord was angry with {S}.",
        "Missed calls show no reason; the anger is inferred.",
    ),
)

RELATIVE_TIME = (
    # Only phrases that can point to either of two dates near midnight (guide rule 17).
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
        "sent the rent earlier tonight",
        "{S} sent the rent on {prev}.",
        "Sent at {clock}, just after midnight; 'earlier tonight' may fall before or after "
        "midnight, so the date is open.",
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
    # The record names where the sender is (or what holds) when it is sent. A record rules out
    # only what it covers up to that moment (guide rule 23), so the assumption is dated before
    # the record's date, covers the whole of it ("all day on"), or holds a window around the
    # record's clock, never its own minute: never "home" without a named place, never quitting
    # a job against working a shift, never "closed" against an event.
    S(
        "con_other_state",
        "back in queens since sunday, just got off the 7 train",
        "{S} was in Lisbon on {prev}.",
        "At {clock} on {date} the sender writes 'back in queens since sunday, just got off the 7 "
        "train'. Being back in Queens since then cannot be true together with being in Lisbon "
        "the day before the message; whether it is true is for the expert.",
        quote="back in queens since sunday",
        days=(1, 2, 3, 4, 5),
    ),
    S(
        "con_other_state",
        "im at the dmv in yonkers, the line is out the door",
        "{S} was at JFK airport all day on {date}. || {S} was at JFK airport from {hour} to "
        "{later} on {date}.",
        "At {clock} the sender writes 'im at the dmv in yonkers', which cannot be true together "
        "with being at the airport at that time on that date.",
        quote="im at the dmv in yonkers",
    ),
    S(
        "con_other_state",
        "flight got cancelled, still in denver",
        "{S} had landed in New York by {hour} on {date}.",
        "Sent at {clock}, 'flight got cancelled, still in denver' cannot be true together with "
        "the assumption, whose time ends at {hour}, before the message.",
        quote="still in denver",
    ),
    S(
        "con_other_state",
        "im still in lisbon, my flight got moved to next week",
        "{S} had flown back to New York before {date}.",
        "On {date} the sender writes 'im still in lisbon, my flight got moved to next week', "
        "which cannot be true together with having flown back before that date.",
        quote="im still in lisbon, my flight got moved to next week",
    ),
    S(
        "con_other_state",
        "sold the corolla 3 weeks ago, the new owner has it",
        "{S} still owned the Corolla on {lastweek}.",
        "On {date} the sender writes 'sold the corolla 3 weeks ago'. What those words state "
        "cannot be true together with still owning it a week before; whether they are true is "
        "for the expert.",
        quote="sold the corolla 3 weeks ago",
    ),
    S(
        "con_other_state",
        "we moved out of the 3rd floor apartment a month ago",
        "{S} was still living in the 3rd-floor apartment on {lastweek}.",
        "On {date} the sender writes 'we moved out of the 3rd floor apartment a month ago', "
        "which cannot be true together with still living there a week before.",
    ),
    S(
        "con_other_state",
        "never had a car, i take the bus everywhere",
        "{S} owned a car on {lastweek}.",
        "On {date} the sender writes 'never had a car'. What those words state cannot be true "
        "together with owning one a week before; whether they are true is for the expert.",
        quote="never had a car",
    ),
    S(
        "con_other_state",
        "still in chicago for work, back friday",
        "{S} had come back to Boston from Chicago before {date}.",
        "On {date} the sender writes 'still in chicago for work, back friday', which cannot be "
        "true together with having come back before that date.",
        quote="still in chicago for work, back friday",
        days=MON_TO_THU,
    ),
    S(
        "con_other_state",
        "landed in miami an hour ago, waiting on my bag",
        "{S} was in Chicago all day on {date}. || {S} was in Chicago from {hour} to {later} on "
        "{date}.",
        "At {clock} the sender is waiting on a bag after landing in Miami ('landed in miami an "
        "hour ago, waiting on my bag'), which cannot be true together with the assumption.",
    ),
    S(
        "con_other_state",
        "on the train to philly, just passed trenton",
        "{S} was in Boston all day on {date}. || {S} was in Boston from {hour} to {later} on "
        "{date}.",
        "At {clock} the sender writes 'on the train to philly, just passed trenton', which "
        "cannot be true together with being in Boston at that time on that date.",
    ),
    S(
        "con_other_state",
        "still at my moms in albany, driving back tmrw",
        "{S} had left Albany before {date}.",
        "On {date} the sender writes 'still at my moms in albany, driving back tmrw'. Being "
        "still in Albany then cannot be true together with the assumption; whether it is true "
        "is for the expert.",
        quote="still at my moms in albany",
    ),
)
