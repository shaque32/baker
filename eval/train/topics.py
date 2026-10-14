"""Topic words: what a line or an assumption is about, as rough word stems.

An irrelevant assumption shares no topic word with any line of its chat or any name the chat
shows (guide rule 21): "landed in Denver" never sits beside "still in denver", and "paid their
rent" never beside a line about paying anything. A Russian word counts through the glossary's
pairs, matched on its first five letters as the glossary says, so "заплатил" touches "paid".
"""

from __future__ import annotations

import re

from eval.train.glossary import PAIRS, SLANG

# Inflected forms that share no prefix with their base.
IRREGULAR = {"paid": "pay", "sold": "sell", "sent": "send", "lent": "lend", "bought": "buy",
             "brought": "bring", "made": "make", "took": "take", "came": "come", "won": "win",
             "lost": "lose", "went": "go", "gave": "give", "left": "leave", "drove": "drive",
             "flew": "fly", "spent": "spend", "kept": "keep", "ran": "run", "swam": "swim",
             "got": "get", "had": "have", "did": "do", "told": "tell", "showed": "show",
             "could": "can", "were": "be", "was": "be", "owed": "owe", "kids": "kid",
             "children": "kid", "men": "man", "people": "person", "boxes": "box",
             "taken": "take", "driven": "drive", "gone": "go", "given": "give", "swum": "swim",
             "done": "do", "gotten": "get", "been": "be", "eaten": "eat", "written": "write",
             "ridden": "ride", "seen": "see", "flown": "fly", "broken": "break",
             "stolen": "steal", "thrown": "throw", "hidden": "hide", "fallen": "fall",
             "spoken": "speak", "drunk": "drink", "known": "know", "shown": "show"}  # fmt: skip
# Words that carry no topic: function words and chat fillers, how parties, dates and messages
# are named, and times of day.
FRAME = frozenset(
    "a an the to of in on at by for and or but so if as is it its im i'm u ur i me my we us "
    "you your he she his her him our they them their be was were am are do did does not no "
    "yes yep ok k lol fr tbh rn pls thx omw that this with from were have has had been into "
    "than when while about every each also only just still again before after until over "
    "under then there here what who how why where which all any some one off up out "
    "owner contact saved account user telegram instagram whatsapp signal shown group chat "
    "message messages wrote said told texted january february march april may june july "
    "august september october november december morning afternoon evening night noon "
    "midnight today tonight tomorrow tmrw yesterday".split()
)
_WORD = re.compile(r"[^\W\d_]+")
_RU = tuple((ru, en.lower().split()) for ru, en in PAIRS + SLANG)


def stem(word: str) -> str:
    """A rough stem: irregular forms mapped, one common suffix and a final e or double letter
    dropped, at most five letters kept ("closed" and "closes" both give "clos")."""
    w = IRREGULAR.get(word, word)
    for suffix in ("ing", "ed", "es", "s"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            w = w[: -len(suffix)]
            break
    if len(w) >= 4 and w.endswith("e"):
        w = w[:-1]
    if len(w) >= 4 and w[-1] == w[-2]:
        w = w[:-1]
    return w[:5]


def topic_stems(text: str) -> set[str]:
    """The stems of the topic words of a text (frame words left out), with the English words
    the glossary gives for its Russian words."""
    low = text.lower()
    tokens = _WORD.findall(low)
    words = set(tokens)
    for ru, en in _RU:
        if " " in ru:
            hit = ru in low
        else:
            hit = any(t.startswith(ru[:5]) for t in tokens)
        if hit:
            words.update(en)
    return {stem(w) for w in words if len(w) >= 2 and w not in FRAME}
