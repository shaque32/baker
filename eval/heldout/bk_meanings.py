"""Wording for the meaning template (guide rule 29): words a chat uses, the meaning a claim
gives them, and what their user says they mean. SYNTHETIC.

PHRASES are (situation, words, what the words plainly name in that situation). CODES are the
meanings a claim gives such words. A usage line uses the words without saying what they mean;
an EXPLAIN line from their user says what they mean: the claim's meaning (bk_meaning_said) or
the plain thing (bk_meaning_other), which is another kind of thing than the claim's meaning
and never names it. Slots: {p} the words, {x} the meaning explained, {spot} a place from the
situation.
"""

from __future__ import annotations

PHRASES = (
    ("apiary", "the white jugs", "the jugs of sugar syrup for the hives"),
    ("apiary", "the nuc box", "the little starter hive"),
    ("apiary", "the queen cages", "the cages the new queens came in"),
    ("apiary", "the smoker fuel", "the bag of pine needles for the smoker"),
    ("apiary", "the frame grips", "the tongs for lifting frames out of a hive"),
    ("apiary", "the bee brush", "the soft brush for moving bees off the frames"),
    ("rink", "the skate bag", "the bag of rental skates"),
    ("rink", "the puck bucket", "the bucket of practice pucks"),
    ("rink", "the blade guards", "the rubber covers for skate blades"),
    ("rink", "the sharpening stone", "the stone for touching up skate edges"),
    ("rink", "the lesson cones", "the orange cones for the skating lessons"),
    ("rink", "the first aid kit", "the box of bandages and ice packs"),
    ("kiln", "the bisque bowls", "the bowls that have been fired once"),
    ("kiln", "the slip jar", "the jar of liquid clay"),
    ("kiln", "the trimming tools", "the tools for trimming pots on the wheel"),
    ("kiln", "the kiln gloves", "the heat gloves for unloading the kiln"),
    ("kiln", "the wax resist", "the wax we paint on the bottoms of pots"),
    ("kiln", "the clay scraps", "the bag of trimmed clay for reclaiming"),
    ("orchard", "the cider crates", "the crates of cider apples"),
    ("orchard", "the windfalls", "the apples that fell on the ground"),
    ("orchard", "the press cloths", "the cloths we press the apples in"),
    ("orchard", "the picking bags", "the canvas bags we pick apples into"),
    ("orchard", "the pruning saw", "the saw for cutting back branches"),
    ("orchard", "the jug labels", "the labels for the cider jugs"),
    ("tow", "the tow chains", "the chains we tow cars with"),
    ("tow", "the lockout kit", "the tools for opening locked cars"),
    ("tow", "the wheel chocks", "the blocks we put behind the wheels"),
    ("tow", "the tow lights", "the magnet lights we put on a towed car"),
    ("tow", "the plug kit", "the kit for patching flat tires"),
    ("tow", "the spare straps", "the extra straps for tying cars down"),
    ("theater", "the prop crates", "the crates of stage props"),
    ("theater", "the costume bags", "the garment bags of costumes for the show"),
    ("theater", "the gel sheets", "the colored sheets for the stage lights"),
    ("theater", "the glow tape", "the tape that marks the stage edges in the dark"),
    ("theater", "the scripts binder", "the binder of marked-up scripts"),
    ("theater", "the wig box", "the box of wigs for the show"),
    ("courier", "the bike pump", "the floor pump for the bike tires"),
    ("courier", "the manifest", "the list of the day's drops"),
    ("courier", "the rain covers", "the plastic covers for the bags"),
    ("courier", "the spare tubes", "the extra inner tubes for flats"),
    ("courier", "the delivery slips", "the signed slips from the drops"),
    ("courier", "the bike lights", "the lights for riding after dark"),
    ("laundry", "the lost and found bin", "the bin of clothes people forget"),
    ("laundry", "the lint brushes", "the brushes for cleaning the dryer screens"),
    ("laundry", "the detergent jugs", "the big jugs of soap"),
    ("laundry", "the drying racks", "the racks we hang delicates on"),
    ("laundry", "the stain kit", "the kit of stain removers"),
    ("laundry", "the rolling baskets", "the carts we push wet loads in"),
    ("print", "the riso drum", "the drum of the riso printer"),
    ("print", "the paper cutter", "the guillotine for trimming prints"),
    ("print", "the ink tubes", "the tubes of printing ink"),
    ("print", "the brayers", "the rollers for spreading ink"),
    ("print", "the test prints", "the first prints we check the colors on"),
    ("print", "the screen frames", "the frames for screen printing"),
    ("rowing", "the coxbox", "the speaker the cox shouts through"),
    ("rowing", "the rigger wrenches", "the wrenches for adjusting the riggers"),
    ("rowing", "the erg handles", "the spare handles for the rowing machines"),
    ("rowing", "the life vests", "the life jackets for the coach boat"),
    ("rowing", "the seat pads", "the foam pads for the rowing seats"),
    ("rowing", "the stroke watch", "the watch that counts strokes per minute"),
    ("piano", "the piano board", "the board we strap pianos to"),
    ("piano", "the tuning kit", "the tools for tuning pianos"),
    ("piano", "the moving straps", "the straps for carrying pianos"),
    ("piano", "the key covers", "the felt covers for the keys"),
    ("piano", "the caster cups", "the cups that go under piano wheels"),
    ("piano", "the shims", "the wooden shims for leveling a piano"),
    ("greenhouse", "the shade cloth", "the cloth we hang over the plants"),
    ("greenhouse", "the potting mix", "the soil for repotting"),
    ("greenhouse", "the heat mats", "the warming pads under the seedlings"),
    ("greenhouse", "the plant tags", "the little labels for the pots"),
    ("greenhouse", "the watering wands", "the long nozzles for the hoses"),
    ("greenhouse", "the seed packets", "the packets of seeds for spring"),
    ("locksmith", "the key blanks", "the uncut keys"),
    ("locksmith", "the rekey kit", "the kit for changing a lock's pins"),
    ("locksmith", "the code machine", "the machine that cuts keys by code"),
    ("locksmith", "the tension wrenches", "the small tools for turning a lock while picking it"),
    ("locksmith", "the pin trays", "the trays of lock pins"),
    ("locksmith", "the key tags", "the paper tags we label keys with"),
    ("pantry", "the intake forms", "the sign-up sheets for clients"),
    ("pantry", "the dry goods", "the canned and boxed food"),
    ("pantry", "the cold boxes", "the coolers for the milk and eggs"),
    ("pantry", "the produce crates", "the crates of fresh vegetables"),
    ("pantry", "the volunteer badges", "the name badges for volunteers"),
    ("pantry", "the diaper boxes", "the boxes of donated diapers"),
    ("tailor", "the dress form", "the mannequin we fit clothes on"),
    ("tailor", "the hem box", "the box of hemming orders"),
    ("tailor", "the button tin", "the tin of spare buttons"),
    ("tailor", "the pattern rolls", "the rolls of paper patterns"),
    ("tailor", "the pin cushions", "the cushions we keep pins in"),
    ("tailor", "the thread box", "the box of thread spools"),
    ("telescope", "the dob", "the big telescope"),
    ("telescope", "the eyepiece case", "the case of telescope eyepieces"),
    ("telescope", "the star charts", "the printed maps of the sky"),
    ("telescope", "the dew heaters", "the heating straps that keep the optics dry"),
    ("telescope", "the finder scope", "the small scope for aiming the big one"),
    ("telescope", "the power tank", "the battery pack that runs the telescopes"),
)

CODES = (
    "the cash from the weekend sales",
    "the second phone",
    "the spare key to the storage unit",
    "the envelope of cash for the landlord",
    "the money owed to the crew",
    "the van's spare plates",
    "the ledger with the cash counts",
    "the stack of prepaid cards",
    "the deposit for the unit",
    "the key to the back gate",
    "the payout for the drivers",
    "the backup hard drive",
)

# Lines that use the words and say nothing about what they mean (records for bk_claim_open,
# and the earlier use a SAID or OTHER line explains). {is} {means} {goes} {stays} {it} agree
# with the words ("the tow chains are", "the nuc box is", "come get them").
USAGE = (
    "left {p} by {spot}",
    "can u grab {p} on ur way",
    "{p} {is} in the back of my car",
    "dont forget {p}",
    "put {p} under the bench at {spot}",
    "{p} {goes} to {spot} at 6",
    "bring {p} when u come by",
    "{p} {is} at {spot} if u need {it}",
    "moved {p} over to {spot}",
    "{p} {is} ready, come get {it}",
    "{p} {stays} at {spot} for now",
    "drop {p} with me at {spot}",
)
USAGE_Q = (
    "{is} {p} still at {spot}?",
    "did u grab {p}?",
    "where did u put {p}?",
    "who has {p} now?",
    "can u check on {p} at {spot}?",
    "{is} {p} in ur car or mine?",
)

# Both explanation families use these lines, so no wording tells them apart: only whether
# {x} is the claim's meaning. Brackets mark the clause an item quotes when the rest adds
# nothing to the answer (guide rule 7); an unmarked line is all deciding text.
EXPLAIN = (
    "when i say {p} i mean {x}",
    "by {p} i mean {x}",
    "[{p} = {x}], thats what i meant",
    "[{p} {is} {x}], should have said",
    "to be clear [{p} {is} {x}]",
    "{p}? i meant {x}",
    "{p} {means} {x}",
    "{p}, as in {x}",
)

# Kinds a plain meaning shares with some claimed meanings. bk_meaning_other never pairs words
# whose plain thing is of a claimed meaning's kind (key blanks against a spare key, a list of
# drops against a ledger, a speaker against a second phone): the explanation must plainly be
# another kind of thing, never one the claimed thing could hide behind.
_KINDS = {
    "lock": ("the lockout kit", "the key blanks", "the rekey kit", "the code machine",
             "the tension wrenches", "the pin trays", "the key tags", "the key covers"),
    "paper": ("the manifest", "the delivery slips", "the intake forms", "the hem box",
              "the scripts binder", "the star charts", "the test prints", "the pattern rolls",
              "the jug labels", "the plant tags", "the key tags"),
    "device": ("the coxbox", "the stroke watch", "the power tank", "the bike lights",
               "the tow lights", "the dew heaters", "the heat mats", "the code machine"),
}  # fmt: skip
CODE_KIND = {
    "the second phone": "device",
    "the backup hard drive": "device",
    "the spare key to the storage unit": "lock",
    "the key to the back gate": "lock",
    "the ledger with the cash counts": "paper",
}


def clash(words: str, code: str) -> bool:
    """Whether the words' plain thing is of the same kind as the claimed meaning."""
    return words in _KINDS.get(CODE_KIND.get(code, ""), ())


def agree(words: str) -> dict[str, str]:
    """The verb forms that agree with the words: plural when the last word ends in s."""
    last = words.split()[-1]
    plural = last.endswith("s") and not last.endswith("ss")
    if plural:
        return {"is": "are", "means": "mean", "goes": "go", "stays": "stay", "it": "them"}
    return {"is": "is", "means": "means", "goes": "goes", "stays": "stays", "it": "it"}


# What the other side asks between the use and the explanation; it never names a meaning.
ASK = ("what do u mean?", "wait what", "huh?", "sorry, which one?", "what's that",
       "meaning what", "lost me there", "?")  # fmt: skip
# What the other side says after it: an acknowledgement that settles nothing else.
ACK = ("ah ok", "got it", "ok makes sense", "k thx", "ok", "gotcha", "right, ok")

# Russian words a Russian chat uses (nominative and accusative alike), and usage lines.
PHRASES_RU = (
    ("apiary", "белые канистры"), ("apiary", "запасные рамки"), ("rink", "синий ящик"),
    ("rink", "запасные коньки"), ("kiln", "мешки с глиной"), ("kiln", "старый круг"),
    ("orchard", "ящики с сидром"), ("orchard", "старый пресс"), ("tow", "запасной трос"),
    ("tow", "большой домкрат"), ("laundry", "синие мешки"), ("laundry", "старый барабан"),
    ("print", "пробные листы"), ("print", "старый резак"), ("greenhouse", "чёрные кассеты"),
    ("greenhouse", "длинный стол"),
)  # fmt: skip
USAGE_RU = (
    "положили {p} {spot}",
    "не забудь {p}",
    "{p} уже {spot}",
    "забери {p} по дороге",
    "{p} пока {spot}",
    "{p} сейчас {spot}, если что",
)
USAGE_Q_RU = ("{p} всё ещё {spot}?", "{p} у тебя?", "где сейчас {p}?")
