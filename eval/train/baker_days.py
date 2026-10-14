"""Plans that name a weekday, for Baker's weekday template. Every line is invented.

Each line plans one particular occasion ("lets do thursday at the gym"), never a repeating one
("we close early thursdays"), so the weekday it names points to one date: the next such day
after the message, unless the line itself says "next" or "this".
"""

from __future__ import annotations

DAYS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
SHORT_EN = {1: "tues", 3: "thurs", 4: "fri"}  # short forms that read only as a day

# {wd}: a bare weekday.
PLANS: tuple[str, ...] = (
    "[lets do {wd} at {place}]",
    "[can u come by {wd}] to look at the {item}",
    "[{wd} works for me], bring the {item}",
    "[i can drop it off {wd}]",
    "[see u {wd} at {place}]",
    "[movers are booked for {wd}]",
    "[lets meet {wd} instead]",
    "[{wd} is the only day i can do]",
    "[how about {wd} after work]",
    "[im free {wd}], come over",
    "[we can finish the {item} on {wd}]",
    "[lets push it to {wd}]",
    "[the inspection is {wd}] so clean up",
    "[ill bring the {item} {wd}]",
    "[{wd} at {place}?]",
    "[practice moved to {wd}]",
    "[can we do the walkthrough {wd}]",
    "[i'll swing by {wd} morning]",
    "[{wd} night works]",
    "[book the room for {wd}]",
    "[we're doing dinner {wd}], u in?",
    "[the guy can only come {wd}]",
    "[lets get the {item} {wd}]",
    "[the kids have their game {wd}]",
    "[lets paint the hallway {wd}]",
    "[i have the car {wd}], can help then",
    "[pickup is {wd}], dont forget",
    "[the vet appt is {wd}]",
    "[lets move the couch {wd}]",
    "[can u babysit {wd}]",
    "[{wd} works better for the movers]",
    "[haircut is {wd}], can u drive me",
    "[the plumber is coming {wd}]",
    "[party is {wd} at {place}]",
    "[i can return the {item} {wd}]",
    "[{wd} after lunch?] for the {item}",
)
# {wd} with "next" or "this" before it.
NEXT_THIS: tuple[str, ...] = (
    "[next {wd} at {place}]",
    "[lets do next {wd}]",
    "[how about next {wd}]",
    "[this {wd} works]",
    "[lets do this {wd}]",
    "[see u this {wd}]",
    "[can u come by next {wd}]",
    "[movers are booked for next {wd}]",
    "[this {wd} at {place}?]",
    "[next {wd} is better for me]",
    "[i can drop it off this {wd}]",
    "[the inspection is next {wd}]",
    "[practice moved to this {wd}]",
    "[next {wd} after work?]",
    "[book it for this {wd}]",
    "[we're doing dinner next {wd}]",
)

# Russian weekday phrases: "в четверг", "на четверг", "в следующий четверг", "в этот четверг".
V_RU = ("в понедельник", "во вторник", "в среду", "в четверг", "в пятницу", "в субботу",
        "в воскресенье")  # fmt: skip
NA_RU = ("на понедельник", "на вторник", "на среду", "на четверг", "на пятницу", "на субботу",
         "на воскресенье")  # fmt: skip
NEXT_RU = ("в следующий понедельник", "в следующий вторник", "в следующую среду",
           "в следующий четверг", "в следующую пятницу", "в следующую субботу",
           "в следующее воскресенье")  # fmt: skip
THIS_RU = ("в этот понедельник", "в этот вторник", "в эту среду", "в этот четверг",
           "в эту пятницу", "в эту субботу", "в это воскресенье")  # fmt: skip
# {v}: a phrase from V_RU (or NEXT_RU, THIS_RU); {na}: one from NA_RU.
PLANS_RU: tuple[str, ...] = (
    "[давай {v}] после работы",
    "[могу заехать {v}]",
    "[{v} подойдёт], приноси инструменты",
    "[встретимся {v} у входа]",
    "[грузчики будут {v}]",
    "[давай перенесём {na}]",
    "[мастер придёт {v}]",
    "[забери коробки {v}]",
    "[{v} я свободна], заходи",
)
OPEN_RU: tuple[str, ...] = (
    "[давай {v}] после работы",
    "[могу заехать {v}]",
    "[встретимся {v} у входа]",
    "[грузчики будут {v}]",
    "[мастер придёт {v}]",
)
