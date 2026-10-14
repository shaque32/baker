"""Claim material for Baker's meaning, role and event templates (guide rule 29). All invented.

MEANINGS pair words a chat uses with the meaning a claim gives them: the claim's wording, the
same meaning as a chat says it, and two meanings of another kind altogether, so neither can be
true together with the claim's. ROLES and EVENTS give what a claim says someone did, with the
other person as {Q} and a street as {Street}; chat lines that bear on it without settling it
('>' marks a line to that person rather than from them); and denials, in that person's words,
that cover any time ({q} is the other person as the speaker names them). `together` marks an
act that needs both people in one place, so "i didnt see {q} at all" rules it out. Every person
and place name starts with A to M, like the rest of eval/train.
"""

from __future__ import annotations

from typing import NamedTuple

# (words, the claim's meaning, the same meaning in a chat, two meanings that rule it out)
MEANINGS: tuple[tuple[str, str, str, tuple[str, str]], ...] = (
    ("the blue box", "the storage unit on Halsey Street", "the storage unit on halsey st",
     ("my tackle box", "the recycling bin out back")),
    ("the cooler", "the safe in the back office", "the safe in the back office",
     ("the cooler we take to the beach", "the mini fridge in the garage")),
    ("the paperwork", "the cash from the weekend shifts", "the cash from the weekend shifts",
     ("the lease renewal forms", "the forms for the clinic")),
    ("the usual spot", "the parking lot behind the laundromat on Dekalb Avenue",
     "the lot behind the laundromat on dekalb ave",
     ("the diner on main", "the bench by the dog park")),
    ("the big one", "the moving truck", "the moving truck",
     ("the large pizza", "the big suitcase")),
    ("the tickets", "the gift cards", "the gift cards",
     ("the concert tickets", "the raffle tickets for the school")),
    ("the books", "the payment ledger for the shop", "the payment ledger for the shop",
     ("the library books", "my old textbooks")),
    ("the cookies", "the prepaid phones", "the prepaid phones",
     ("the cookies my mom baked", "the cookies from the bake sale")),
    ("the boat", "the gray sedan in the back lot", "the gray sedan in the back lot",
     ("my uncles fishing boat", "the inflatable raft")),
    ("the bakery", "the warehouse on Meserole Avenue", "the warehouse on meserole ave",
     ("the bakery on the corner", "the bread place by the train")),
    ("the homework", "the tax forms for the store", "the tax forms for the store",
     ("my sons math homework", "the reading for my class")),
    ("the laundry", "the cash deposits for the store", "the cash deposits for the store",
     ("my dirty clothes", "the towels from the gym")),
    ("the cake", "the down payment for the van", "the down payment for the van",
     ("the birthday cake for my niece", "the cheesecake from the deli")),
    ("the doctor", "the mechanic on Atlantic Avenue", "the mechanic on atlantic ave",
     ("my dentist", "the vet for the dog")),
    ("the red one", "the second storage locker", "the second storage locker",
     ("the red jacket", "the red cooler")),
    ("the music", "the delivery schedule", "the delivery schedule",
     ("the playlist for the party", "the band for the wedding")),
    ("the bank", "the safe at the apartment on Grand Street",
     "the safe at the apartment on grand st",
     ("the credit union on grand", "the piggy bank in the kids room")),
    ("the twins", "the two cars in the garage on Dean Street",
     "the two cars in the garage on dean st",
     ("my sisters twins", "the twin beds in the spare room")),
    ("the office", "the back room at the barbershop", "the back room at the barbershop",
     ("the home office in my apartment", "my desk at the insurance company")),
    ("lunch", "the weekly payment", "the weekly payment",
     ("an actual meal", "the sandwiches from the deli")),
    ("the cousins", "the spare tires in the garage", "the spare tires in the garage",
     ("my actual cousins", "my cousins from jersey")),
    ("the garden", "the stockroom behind the bodega", "the stockroom behind the bodega",
     ("the community garden", "my moms backyard")),
    ("the dog", "the black pickup truck", "the black pickup truck",
     ("my actual dog", "the neighbors dog")),
    ("the movie", "the meeting with the landlord", "the meeting with the landlord",
     ("the movie we saw", "the film for my class")),
    ("the shoes", "the envelopes of cash", "the envelopes of cash",
     ("my work boots", "the sneakers i ordered")),
    ("the farm", "the house on Elm Street", "the house on elm st",
     ("the farmers market on saturdays", "the petting zoo")),
    ("the coffee", "the bags of cash", "the bags of cash",
     ("actual coffee", "the coffee beans from the shop")),
    ("the kitchen", "the storage room behind the deli", "the storage room behind the deli",
     ("my kitchen at home", "the kitchen at my moms place")),
    ("the church", "the bar on Hart Street", "the bar on hart st",
     ("the church on 5th", "my moms church")),
    ("the lake", "the parking garage on Kent Avenue", "the parking garage on kent ave",
     ("the lake upstate", "the pond in the park")),
    ("the snacks", "the spare keys to the warehouse", "the spare keys to the warehouse",
     ("chips and soda", "the snacks for the kids")),
    ("the paint", "the batteries for the cameras", "the batteries for the cameras",
     ("the paint for the hallway", "the paint cans in the garage")),
    ("the gift", "the cash payment for the contractor", "the cash payment for the contractor",
     ("the present for my mom", "the birthday gift for my nephew")),
    ("the guitar", "the laptop from the office", "the laptop from the office",
     ("my old acoustic guitar", "the guitar my brother left here")),
    ("the blanket", "the duffel bag with the cash", "the duffel bag with the cash",
     ("the blanket on the couch", "the baby blanket from my aunt")),
    ("the cat", "the silver minivan", "the silver minivan", ("my actual cat", "the neighbors cat")),
)  # fmt: skip
PLURAL = frozenset({"the tickets", "the books", "the cookies", "the twins", "the cousins",
                    "the shoes", "the snacks"})  # fmt: skip

# The words' user says what they mean ({m}); the meaning is exactly the claim's. {is} agrees.
SAY = (
    "when i say {p} i mean {m}", "{p} = {m}, just so we're clear", "by {p} i mean {m}",
    "{p} means {m}", "just so u know, {p} {is} {m}", "{p} is what i call {m}",
    "ok so {p} {is} {m}", "to be clear, {p} {is} {m}", "{p}? thats {m}",
    "remember {p} {is} {m}", "if i say {p} i mean {m}",
)  # fmt: skip
# The words' user gives them a meaning ({m}) that cannot be true together with the claim's.
OTHER = (
    "{p} {is} just {m}, nothing else", "by {p} i mean {m}, thats it", "{p} = {m}, nothing else",
    "i only ever mean {m} when i say {p}", "{p} means {m}, nothing more",
    "when i say {p} i only mean {m}", "{p} has only ever meant {m}",
    "{p} {is} {m} and nothing else",
)  # fmt: skip
# The words used and left unexplained.
USE = (
    "did u handle {p}", "{p} {is} ready", "dont forget {p}", "i have {p}", "{p} {is} all set",
    "we need to talk about {p}", "check on {p} today", "{p} {is} sorted", "any news on {p}",
    "leave {p} to me",
)  # fmt: skip
# What a claim says words referred to, for words the chat never explains.
TOPICS = (
    "a shipment of prepaid phones", "the cash owed for the van", "a meeting with the buyers",
    "a payment to the contractor", "the keys to the warehouse", "a delivery of cash",
    "the money from the weekend shifts", "a pickup at the warehouse on Meserole Avenue",
    "the rent money for the apartment on Dean Street", "the gift cards from the store",
    "a car parked in the garage on Kent Avenue", "the second storage locker",
    "the envelopes for the landlord", "a drop-off at the storage unit on Halsey Street",
    "the spare tires in the garage", "the black pickup truck", "the laptops from the office",
    "the deposit for the moving truck", "the duffel bag with the cash", "the silver minivan",
)  # fmt: skip


class Act(NamedTuple):
    claim: str  # what the claim says the person did, after their name
    together: bool  # the act needs both people in one place
    bearing: tuple[str, ...]
    never: tuple[str, ...]  # denials that cover any time


ROLES = (
    Act("worked as the driver for {Q}'s deliveries", False,
        ("van is gassed up, ill do the runs tmrw", "dropped off the last one, heading home",
         "3 more stops then im done for today", "traffic on {street} is killing my route",
         ">can u do the deliveries again tmrw?"),
        ("i never drove for {q}, ever", "i never made a single delivery for {q}")),
    Act("kept the payment records for {Q}'s shop", False,
        ("updated the numbers, ill send the sheet tonight",
         "entered all the receipts from the shop",
         "the totals for the week dont add up, checking again",
         ">did u update the sheet for the shop?"),
        ("i never kept any records for {q}", "i have never done the books for {q}")),
    Act("collected rent payments for {Q} from the tenants of the building on {Street}", False,
        ("two tenants still havent paid this month", "got the rent from 3B, still waiting on 2A",
         "knocked on every door, half of them paid", ">did 4C pay u yet?"),
        ("i never collected rent from anyone for {q}",
         "i have never taken a cent of rent for {q}")),
    Act("scheduled the shifts for {Q}'s cleaning crew", False,
        ("moved everyone to the early shift tmrw", "need someone to cover the 6am",
         "the new schedule is up, check ur slot", ">can u put me on nights next week?"),
        ("i never made a schedule for {q} or the crew", "i have never scheduled anybody for {q}")),
    Act("worked as a courier for {Q}, carrying envelopes between the shop and the warehouse on "
        "{Street}", False,
        ("picking up the envelope at 3", "on my way to the warehouse with the envelope",
         "left the envelope with the guy at the warehouse", ">is the envelope at the shop yet?"),
        ("i never carried anything for {q}", "i have never taken an envelope anywhere for {q}")),
    Act("recruited workers for {Q}'s moving crew", False,
        ("found two more guys who can start next week", "my cousin wants in on the moving jobs",
         "told the guys from the gym about the jobs", ">u find anyone else for the crew?"),
        ("i never found a single worker for {q}", "i have never recruited anybody for {q}")),
    Act("managed the storage unit {Q} rented on {Street}", False,
        ("moved the boxes into the unit", "changed the lock on the unit, new code tmrw",
         "the unit is almost full", ">do u have the key to the unit?"),
        ("i never had anything to do with any storage unit {q} rented",
         "i have never managed any unit for {q}")),
    Act("acted as a lookout for {Q} outside the warehouse on {Street}", False,
        ("nobody around out front, all quiet", "a patrol car drove by twice",
         "still out front, nothing happening", ">anyone outside right now?"),
        ("i never stood outside any warehouse for {q}", "i was never a lookout for {q}")),
    Act("ran the cash register at {Q}'s store on {Street}", False,
        ("drawer came up $20 short tonight", "register is closed out for the day",
         "the card reader keeps freezing", ">did u close out the register?"),
        ("i never worked the register for {q}", "i have never run a register for {q}")),
    Act("arranged the resale of prepaid phones for {Q}", False,
        ("sold 4 more today", "got a buyer for the last 2", "the guy on {street} wants 3 more",
         ">how many phones are left?"),
        ("i never sold a single phone for {q}", "i have never resold anything for {q}")),
    Act("dispatched the drivers for {Q}'s car service", False,
        ("sent two cars to the airport run", "need a driver at the hospital in 10",
         "all cars are out right now", ">who's taking the 8am pickup?"),
        ("i never dispatched anybody for {q}", "i have never worked dispatch for {q}")),
    Act("showed the apartments on {Street} on {Q}'s behalf", False,
        ("showed 2B to a couple today, they want it", "the people for 3A never showed up",
         "need the keys for 4C before the showing", ">can u show the apartment again tmrw?"),
        ("i never showed any apartment for {q}", "i have never done a showing for {q}")),
)  # fmt: skip

EVENTS = (
    Act("met {Q} at the parking lot behind the laundromat on {Street}", True,
        ("running late, be at the lot in 20", "parked out back, where r u",
         "at the laundromat lot now", ">u still coming to the lot?"),
        ("i never met up with {q} behind any laundromat", "i have never met {q} at a parking lot")),
    Act("delivered two boxes to {Q}'s apartment on {Street}", False,
        ("the boxes are in my trunk", "leaving now with the boxes", "2 boxes, both taped up",
         ">did u drop the boxes off yet?"),
        ("i never brought any boxes to {q}", "i have never delivered anything to {q}s apartment")),
    Act("picked up a rental van with {Q} from the lot on {Street}", True,
        ("the rental place opens at 8, ill grab the van then", "got the confirmation for the van",
         "they want a deposit for the van", ">is the van ready?"),
        ("i never rented any van with {q}", "i have never picked up a van with {q}")),
    Act("paid {Q} $1,500 in cash", False,
        ("got the 1500 together", "counting it out now, all there", "taking the cash out today",
         ">do u have the 1500?"),
        ("i never gave {q} any cash", "i have never paid {q} a dollar")),
    Act("drove {Q} to the warehouse on {Street}", True,
        ("gas first then the warehouse", "leaving for the warehouse in 10",
         "car is out front, ready when u are", ">what time r we leaving for the warehouse?"),
        ("i never drove {q} to any warehouse", "i have never given {q} a ride anywhere")),
    Act("dropped off the keys to the storage unit at {Q}'s shop", False,
        ("i have the keys to the unit, ill swing by the shop", "left the keys on the counter",
         "keys are on my ring, coming now", ">did u bring the keys?"),
        ("i never dropped off any keys at {q}s shop", "i have never left anything at {q}s shop")),
    Act("loaded the van at the warehouse on {Street} with {Q}", True,
        ("bring gloves, the boxes are heavy", "at the warehouse, where r u",
         "half the boxes are in, need a hand", ">how many boxes left to load?"),
        ("i never loaded anything with {q}", "i have never been to a warehouse with {q}")),
    Act("visited {Q} at the barbershop on {Street}", True,
        ("ill stop by the barbershop after work", "here, come out front",
         "line at the barbershop is long, ill wait", ">u coming by the barbershop today?"),
        ("i never went to see {q} at any barbershop", "i have never visited {q} at a barbershop")),
    Act("handed {Q} an envelope outside the deli on {Street}", True,
        ("meet me outside the deli, i have it", "outside the deli now",
         "got the envelope in my jacket, see u soon", ">u have the envelope?"),
        ("i never handed {q} any envelope", "i have never given {q} anything outside a deli")),
    Act("brought a generator to {Q}'s garage", False,
        ("the generator is in my truck", "ill bring the generator by the garage later",
         "the generator is heavy, need help unloading", ">is the generator coming today?"),
        ("i never brought a generator to {q}s garage",
         "i have never brought anything to {q}s garage")),
)  # fmt: skip

# Denials of a day or a stretch of days: {dc} a date as a chat writes it ("may 3rd"), {span} a
# stretch ("from may 1st through the 9th"), {city} where the speaker was instead.
DAY_DENIALS = (
    "i didnt see {q} at all on {dc}", "i was never with {q} on {dc}",
    "i was in {city} all day on {dc}, i didnt see {q}",
    "i spent all of {dc} in {city} and never saw {q}",
)  # fmt: skip
SPAN_DENIALS = (
    "i didnt see {q} at all {span}", "i was not with {q} once {span}",
    "i was in {city} {span} and didnt see {q} once",
    "i was out of town in {city} {span}, i never saw {q}",
)  # fmt: skip
CITIES = ("Albany", "Atlanta", "Baltimore", "Boston", "Buffalo", "Charlotte", "Chicago",
          "Cleveland", "Columbus", "Dallas", "Detroit", "El Paso", "Hartford", "Houston",
          "Indianapolis", "Jacksonville", "Kansas City", "Las Vegas", "Louisville", "Memphis",
          "Miami", "Milwaukee")  # fmt: skip
