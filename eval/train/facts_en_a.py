"""English facts, part 1: home repair, used cars, moving, bar shifts, gyms, family.

Each fact is one plain act. The `exact` record forms state the value and rule out any other
without a qualifier that leaves room ("total", "about", "tip included"); `extra` and `general`
forms name no person by pronoun and no relative time, because they go into assumptions.
"""

from __future__ import annotations

from eval.train.facts import Fact

DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
NAMES = ("ana", "gus", "mara", "kofi", "bea", "ike", "dev", "cleo")


def F(
    key: str,
    scene: str,
    act: str,
    acted: str,
    claim: str,
    values: tuple[str, ...],
    *,
    base: str | None = None,
    exact: tuple[str, ...] = (),
    extra: tuple[str, ...] = (),
    general: tuple[str, ...] = (),
) -> Fact:
    """An English fact; the base claim is the claim with the verb in its base form."""
    if base is None:
        base = act.split(" ", 1)[0] + " " + claim.split(" ", 1)[1]
    return Fact(
        key, scene, "en", act, acted, claim, base, values, exact=exact, extra=extra, general=general
    )


FACTS_A: tuple[Fact, ...] = (
    F("plumber", "repair", "pay the plumber {v}", "paid the plumber {v}", "paid the plumber ${v}",
      ("250", "300", "400", "450", "600"),
      exact=("paid the plumber exactly {v}", "paid the plumber {v}, not a cent more"),
      extra=("tipped the plumber 40 on top", "got a written receipt"),
      general=("paid the plumber every month this year",)),
    F("tile", "repair", "pick up {v} boxes of tile from the depot",
      "picked up {v} boxes of tile from the depot", "picked up {v} boxes of tile from the depot",
      ("4", "6", "8", "12"), exact=("picked up exactly {v} boxes of tile from the depot",),
      extra=("paid cash for the tile",), general=("picked up tile from the depot every morning",)),
    F("drywall", "repair", "let the drywall guy in on {v}", "let the drywall guy in on {v}",
      "let the drywall guy in on {V}", DAYS,
      exact=("let the drywall guy in on {v}, the only day he came",),
      extra=("stayed the whole time",),
      general=("let the drywall guy in every day that week",)),
    F("roof", "repair", "patch {v} spots on the roof", "patched {v} spots on the roof",
      "patched {v} spots on the roof", ("two", "three", "four"),
      exact=("patched {v} spots on the roof and thats all of them",),
      extra=("replaced the gutter too",)),
    F("electric", "repair", "pay the electrician {v} for the panel",
      "paid the electrician {v} for the panel", "paid the electrician ${v} for the panel",
      ("800", "900", "1200", "1500"),
      exact=("paid the electrician exactly {v} for the panel, nothing else",),
      extra=("paid in cash",), general=("paid the electrician every week",)),
    F("brakes", "cars", "pay {v} for the new brake pads", "paid {v} for the new brake pads",
      "paid ${v} for the new brake pads", ("180", "220", "260", "300"),
      exact=("paid exactly {v} for the new brake pads, parts and labor",),
      extra=("had the rotors turned too",)),
    F("corolla", "cars", "sell the corolla to a guy in yonkers for {v}",
      "sold the corolla to a guy in yonkers for {v}",
      "sold the Corolla to a guy in Yonkers for ${v}",
      ("3500", "4000", "4200", "5000"),
      exact=("sold the corolla to a guy in yonkers for exactly {v}, final price",),
      extra=("signed the title over the same day",), general=("sold a car every month",)),
    F("van", "cars", "pick the van up from the garage on {v}",
      "picked the van up from the garage on {v}", "picked the van up from the garage on {V}", DAYS,
      exact=("picked the van up from the garage on {v}, only trip i made there",),
      extra=("paid the balance in cash",)),
    F("tires", "cars", "put {v} new tires on the truck", "put {v} new tires on the truck",
      "put {v} new tires on the truck", ("2", "4"),
      exact=("put {v} new tires on the truck, thats all it needed",),
      extra=("got the alignment done",)),
    F("movers", "moving", "pay the movers {v}", "paid the movers {v}", "paid the movers ${v}",
      ("350", "400", "500", "650"),
      exact=("paid the movers exactly {v}", "paid the movers {v}, not a cent more"),
      extra=("tipped each mover 20",), general=("paid the movers every time they came",)),
    F("boxes", "moving", "bring {v} boxes down to the truck", "brought {v} boxes down to the truck",
      "brought {v} boxes down to the truck", ("10", "15", "20", "30"),
      exact=("brought {v} boxes down to the truck, thats every single one",),
      extra=("loaded the couch too",)),
    F("oldkeys", "moving", "drop the old apartment keys with the super on {v}",
      "dropped the old apartment keys with the super on {v}",
      "dropped the old apartment keys with the super on {V}", DAYS,
      exact=("dropped the old apartment keys with the super on {v}, one trip",),
      extra=("got the deposit back at the same time",)),
    F("uhaul", "moving", "book the uhaul for {v}", "booked the uhaul for {v}",
      "booked the uhaul for {V}", DAYS,
      exact=("booked the uhaul for {v}, no other day was open",),
      extra=("paid for the insurance too",)),
    F("shift", "shifts", "cover {v}s shift saturday", "covered {v}s shift saturday",
      "covered {V}'s shift on Saturday", ("ana", "gus", "mara", "kofi", "bea"),
      exact=("covered {v}s shift saturday, nobody elses",), extra=("stayed for close",),
      general=("covered a shift every saturday",)),
    F("tips", "shifts", "make {v} in tips", "made {v} in tips", "made ${v} in tips",
      ("120", "180", "240", "310"), exact=("made exactly {v} in tips after tipout",),
      extra=("worked a double",), general=("made ${v} in tips every night",)),
    F("close", "shifts", "close the bar at {v}", "closed the bar at {v}", "closed the bar at {v}",
      ("1", "2", "midnight", "3"), exact=("closed the bar at {v} sharp, not a minute later",),
      extra=("counted the drawer alone",)),
    F("hire", "shifts", "hire {v} new bartenders", "hired {v} new bartenders",
      "hired {v} new bartenders", ("two", "three", "four"),
      exact=("hired {v} new bartenders and thats the whole list",), extra=("let the old one go",)),
    F("gym", "gym", "pay the gym {v} for the year", "paid the gym {v} for the year",
      "paid the gym ${v} for the year", ("300", "400", "480", "600"),
      exact=("paid the gym exactly {v} for the year",), extra=("signed up for the trainer too",),
      general=("paid the gym every month",)),
    F("games", "gym", "win {v} games at the court", "won {v} games at the court",
      "won {v} games at the court", ("two", "three", "five"),
      exact=("won {v} games at the court, lost the rest",), extra=("sprained an ankle",),
      general=("won every game that week",)),
    F("court", "gym", "book the court for {v}", "booked the court for {v}",
      "booked the court for {v}", ("6", "7", "8", "9"),
      exact=("booked the court for {v}, only slot left",), extra=("paid for two hours",)),
    F("pickup", "family", "pick the kids up from school at {v}",
      "picked the kids up from school at {v}", "picked the kids up from school at {v}",
      ("2:30", "3", "3:15", "3:45"), exact=("picked the kids up from school at {v} sharp",),
      extra=("took the kids to the dentist after",),
      general=("picked the kids up every day that week",)),
    F("meds", "family", "pay {v} for moms prescription", "paid {v} for moms prescription",
      "paid ${v} for mom's prescription", ("40", "65", "90", "120"),
      exact=("paid exactly {v} for moms prescription",), extra=("picked up moms groceries too",)),
    F("dentist", "family", "take {v} to the dentist", "took {v} to the dentist",
      "took {V} to the dentist", ("lina", "milo", "jada", "eli"),
      exact=("took {v} to the dentist, just {v}, nobody else",), extra=("paid the copay",),
      general=("took the kids to the dentist every month",)),
    F("daycare", "family", "pay daycare {v} for the month", "paid daycare {v} for the month",
      "paid the daycare ${v} for the month", ("900", "1100", "1400", "1600"),
      exact=("paid daycare exactly {v} for the month, nothing extra",),
      extra=("paid next month early too",), general=("paid the daycare ${v} every month",)),
)  # fmt: skip
