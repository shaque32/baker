"""Near-miss quote attacks on the verbatim quote check. SYNTHETIC.

CLAUDE.md: any quote attributed to evidence must be verified verbatim by code before it is
stored. A labeler that paraphrases, splices, or swaps a lookalike character must be caught,
because a quote that passes becomes "verified" evidence the reviewer then reads as fact.

Each attack is (quote, record_text, must_verify, why). Controls (must_verify=True) keep a
verifier that rejects everything from passing. tests/adversarial/test_quote_red_team.py runs
them against core/audit/quotes.py once it exists.
"""

from __future__ import annotations

from typing import NamedTuple


class QuoteAttack(NamedTuple):
    aid: str
    quote: str
    record_text: str
    must_verify: bool
    why: str


R1 = "need 2 more by friday"
R2 = "dont text me about it, use telegram"
R3 = "я волнуюсь за Маркуса"
R4 = "got the tickets. 4 of them"
R5 = "lets meet monday 8pm. lot behind kings plaza"

QUOTE_ATTACKS: tuple[QuoteAttack, ...] = (
    # ---- controls
    QuoteAttack("Q01", R1, R1, True, "exact whole message"),
    QuoteAttack("Q02", "use telegram", R2, True, "exact substring"),
    QuoteAttack("Q03", R3, R3, True, "exact Cyrillic text"),
    # ---- attacks
    QuoteAttack("Q10", "", R1, False, "empty quote is a substring of everything"),
    QuoteAttack("Q11", "   ", R1 + "   ", False, "whitespace-only quote cites nothing"),
    QuoteAttack("Q12", "Need 2 more by Friday", R1, False, "case changed"),
    QuoteAttack("Q13", "need two more by friday", R1, False, "digit spelled out"),
    QuoteAttack("Q14", "need 2 more by friday.", R1, False, "punctuation added"),
    QuoteAttack("Q15", "don't text me about it", R2, False, "apostrophe added to dont"),
    QuoteAttack("Q16", "dont text me about it, use telegram!", R2, False, "trailing character"),
    QuoteAttack(
        "Q17",
        "text me about it",
        "dont " + "text me about it",
        True,
        "control: a true substring passes even though it drops the negation",
    ),
    QuoteAttack("Q18", "need 2 ... friday", R1, False, "ellipsis splice"),
    QuoteAttack(
        "Q19",
        "need 2 more by friday",
        "need 2 more\nby friday",
        False,
        "line break in the record replaced by a space",
    ),
    QuoteAttack(
        "Q20",
        "need 2 more by friday",
        "need 2  more by friday",
        False,
        "double space in the record collapsed",
    ),
    QuoteAttack(
        "Q21", "need 2 mоre by friday", R1, False, "Cyrillic o (U+043E) in place of Latin o"
    ),
    QuoteAttack("Q22", "need 2 more​ by friday", R1, False, "zero-width space inserted"),
    QuoteAttack(
        "Q23",
        "need 2 more by friday",
        "need 2 more by friday",
        False,
        "record has a no-break space; quote has a plain space",
    ),
    QuoteAttack(
        "Q24",
        "I am worried about Marcus",
        R3,
        False,
        "English translation cited as if it were the Russian original",
    ),
    QuoteAttack("Q25", "я волнуюсь за Маркусa", R3, False, "Latin a (U+0061) in Cyrillic word"),
    QuoteAttack("Q26", "got the tickets. 5 of them", R4, False, "number changed"),
    QuoteAttack(
        "Q27",
        "lets meet monday 8pm. lot behind kings plaza. ok works",
        R5,
        False,
        "quote runs past the record into the next message",
    ),
    QuoteAttack("Q28", "“need 2 more by friday”", R1, False, "wrapped in curly quotes"),
    QuoteAttack("Q29", "need 2 more by friday", "", False, "record text is empty"),
    QuoteAttack("Q30", "the packag", "the package will be at marcs", False, "quote stops mid-word"),
    QuoteAttack("Q31", "...", "dont know yet...", False, "punctuation only: cites no words"),
)
