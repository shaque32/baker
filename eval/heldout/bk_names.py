"""Names for items in Baker's own wording: document persons, first names, handles, contacts.

SYNTHETIC. Every name is invented for the held-out set. Latin names and person slugs start
with N to Z and Cyrillic names with М to Я (the training generator owns the first half of each
alphabet). None of these names is used by the plain held-out families either.
"""

from __future__ import annotations

# Surnames a government document names; Baker's person id is person:<slug>. A few use the
# numbered form a document gets when it withholds a name ("name_0417").
SLUGS = (
    "norcott", "quarrie", "tolliver", "wexley", "pashkov", "yelland", "renfrew", "ostrander",
    "selwyn", "vukovic", "zandvoort", "upshaw", "pellow", "treadwell", "nyquist", "roebuck",
    "varley", "oyelaran", "whitlam", "sabatini", "quennell", "yoxall", "trask", "naseby",
    "prentiss", "ruddock", "stavely", "ulbrich", "verhoef", "winslade", "zelenko", "orrell",
    "pruett", "rasko", "thorne", "nettleford", "seaver", "voskuijl", "yarrow", "quist",
    "tamsett", "ollerby", "redgrave", "strand", "wardell", "zubiri", "penhallow", "ridley",
    "sorrell", "teague", "norgaard", "vasko", "outhwaite", "parrish", "rookwood", "saltash",
    "name_0417", "name_0388", "name_0562", "name_0731",
)  # fmt: skip

# Slugs held back for the role template, whose text shows nothing but the person id; each role
# item gets its own, so no two role assumptions read alike.
ROLE_SLUGS = (
    "nolan_0215", "pemberton", "quayle", "rathbone", "standish", "thurlow", "underhill",
    "vellacott", "westbury", "yeardley", "zahradnik", "oakeshott", "pilbeam", "radcliffe",
    "sherbourne", "tennant", "vaillant", "worsley", "yardley", "zimmer", "northam", "osgood",
)  # fmt: skip

# First names for people who type or introduce themselves, and for saved contact names.
FIRSTS = (
    "Neve", "Nils", "Odette", "Ozzie", "Pim", "Quill", "Ronan", "Ruthie", "Sully", "Saoirse",
    "Tibor", "Tilde", "Ulla", "Vesna", "Wendell", "Xander", "Yusra", "Zofia", "Zuri", "Remy",
    "Rook", "Ottilie", "Nuno", "Philippa", "Quincy", "Rosalind", "Seren", "Thaddeus", "Vito",
    "Yael", "Zev", "Noa", "Oona", "Pax", "Rhys", "Silas", "Tamar", "Una", "Wynn", "Ximena",
)  # fmt: skip

# Russian people: (Latin slug, Cyrillic surname, Cyrillic first name).
RU_PEOPLE = (
    ("orlova", "Орлова", "Ника"),
    ("nikitin", "Никитин", "Матвей"),
    ("rybakov", "Рыбаков", "Платон"),
    ("sobolev", "Соболев", "Савва"),
    ("panina", "Панина", "Мила"),
    ("tarasov", "Тарасов", "Семён"),
    ("osipova", "Осипова", "Таисия"),
    ("shestakov", "Шестаков", "Ян"),
    ("polyakova", "Полякова", "Олеся"),
    ("yakushev", "Якушев", "Мирон"),
    ("savelyeva", "Савельева", "Ульяна"),
    ("rodionov", "Родионов", "Тимофей"),
)
RU_FIRSTS = ("Мила", "Ника", "Платон", "Савва", "Семён", "Таисия", "Ян", "Мирон", "Ульяна")

# Instagram usernames: an account's identifier on Instagram.
IG_HANDLES = (
    "nightjar.prints", "oakmoss.studio", "pinegate.bees", "quietcove.rows", "rivet.and.rope",
    "saltmarsh.kiln", "thistle.press", "umber.clayworks", "velvet.hems", "willowbrook.cider",
    "yardbird.tow", "zephyr.courier", "nuno.rows", "odette.sews", "pim.prints", "quincy.locks",
    "ronan.lifts", "sully.skates", "tibor.tunes", "ulla.grows", "vito.hauls", "xander.rides",
    "yael.pots", "zev.stargazes", "noa.pantry", "oona.irons", "pax.pianos", "rhys.rinks",
    "silas.sorts", "tamar.tees", "una.blooms", "ximena.keys", "yosef.cider", "zaid.zines",
    "nettle.and.fern", "orbit.club", "plumline.stage", "rinkside.ruthie", "seedtray.seren",
)  # fmt: skip

# Handle pairs one account went by, as a document writes them (with "@"): (app, old, new).
HANDLE_PAIRS = (
    ("Instagram", "@orchard.neve", "@neve.presses"),
    ("Instagram", "@kilnside.ottilie", "@ottilie.ceramics"),
    ("Instagram", "@rinkrat.sully", "@sully.skates.co"),
    ("Instagram", "@pim.inks", "@pim.prints.shop"),
    ("Instagram", "@tibor.keys", "@tibor.tunes.pianos"),
    ("Instagram", "@ulla.sprouts", "@ulla.greenhouse"),
    ("Instagram", "@xander.pedals", "@xander.courier"),
    ("Instagram", "@yael.mud", "@yael.pottery"),
    ("Instagram", "@zev.looksup", "@zev.astro"),
    ("Instagram", "@rhys.zamboni", "@rhys.icecrew"),
    ("Instagram", "@tamar.stitches", "@tamar.alterations"),
    ("Instagram", "@una.blooms", "@una.plantshop"),
    ("Instagram", "@noa.cans", "@noa.foodshare"),
    ("Instagram", "@silas.spins", "@silas.washfold"),
    ("Instagram", "@quill.hauls", "@quill.towing"),
    ("Instagram", "@vesna.oars", "@vesna.rowclub"),
    ("Telegram", "@rookwood_tow", "@rookwood_towing"),
    ("Telegram", "@nils_hives", "@nils_apiary"),
    ("Telegram", "@ozzie_backstage", "@ozzie_stagecrew"),
    ("Telegram", "@remy_locks", "@remy_lockworks"),
    ("Telegram", "@ruthie_pantry", "@ruthie_foodbank"),
    ("Telegram", "@saoirse_seams", "@saoirse_tailoring"),
    ("Telegram", "@wendell_bees", "@wendell_honey"),
    ("Telegram", "@yusra_riso", "@yusra_printworks"),
    ("Telegram", "@zofia_cider", "@zofia_orchards"),
    ("Telegram", "@tilde_scopes", "@tilde_darksky"),
    ("Telegram", "@philippa_rows", "@philippa_sculls"),
    ("Telegram", "@thaddeus_moves", "@thaddeus_pianomovers"),
    ("Telegram", "@nuno_spokes", "@nuno_rides"),
    ("Telegram", "@oona_folds", "@oona_laundry"),
    ("Telegram", "@vito_flatbed", "@vito_tows"),
    ("Telegram", "@quincy_keys", "@quincy_safes"),
    ("Telegram", "@rosalind_props", "@rosalind_theatre"),
    ("Telegram", "@seren_seedlings", "@seren_nursery"),
    ("Telegram", "@ximena_ice", "@ximena_rink"),
    ("Telegram", "@zuri_glaze", "@zuri_kilnworks"),
    ("Telegram", "@wynn_courier", "@wynn_rides"),
    ("Telegram", "@pax_tuning", "@pax_pianos"),
    ("Telegram", "@noa_shelves", "@noa_pantry_crew"),
    ("Telegram", "@yosef_presses", "@yosef_ciderhouse"),
    ("Instagram", "@remy.cuts.keys", "@remy.locksmithing"),
    ("Instagram", "@ottilie.throws", "@ottilie.wheelhouse"),
    ("Telegram", "@nils_frames", "@nils_honeyhouse"),
    ("Telegram", "@tamar_hems", "@tamar_tailorshop"),
    ("Instagram", "@zuri.pots", "@zuri.studio.ceramics"),
    ("Telegram", "@quill_rides", "@quill_courierco"),
)

# Words people add to a saved contact name, by situation.
CONTACT_TAGS = {
    "apiary": ("Bees", "Hive Co-op", "Honey"),
    "rink": ("Rink", "Zamboni", "Skate Rental"),
    "kiln": ("Kiln", "Clay Studio", "Pottery"),
    "orchard": ("Cider", "Orchard", "Press"),
    "tow": ("Tow", "Flatbed", "Impound"),
    "theater": ("Stage Mgr", "Props", "Box Office"),
    "courier": ("Courier", "Dispatch", "Bike"),
    "laundry": ("Laundromat", "Wash n Fold", "Dryer Repair"),
    "print": ("Print Shop", "Riso", "Proofs"),
    "rowing": ("Boathouse", "Rowing", "Cox"),
    "piano": ("Piano", "Movers", "Tuner"),
    "greenhouse": ("Greenhouse", "Plants", "Nursery"),
    "locksmith": ("Locks", "Keys", "Locksmith"),
    "pantry": ("Pantry", "Food Bank", "Van"),
    "tailor": ("Tailor", "Alterations", "Seams"),
    "telescope": ("Astro Club", "Dark Site", "Scope"),
}
CONTACT_TAGS_RU = {
    "apiary": ("пасека", "мёд"),
    "rink": ("каток", "прокат"),
    "kiln": ("керамика", "печь"),
    "orchard": ("сад", "сидр"),
    "tow": ("эвакуатор", "стоянка"),
    "laundry": ("прачечная", "химчистка"),
    "print": ("типография", "печать"),
    "greenhouse": ("теплица", "рассада"),
}
