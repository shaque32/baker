"""The Help page: the support contact, what Mabillon does and doesn't do, and the bug report.

The bug report (core/support/bug_report.py) is shown in full before it is saved, so the
examiner reads exactly what would leave the computer. Mabillon sends nothing itself.
"""

from __future__ import annotations

from core.support import bug_report
from core.support.contact import SUPPORT_EMAIL, SUPPORT_IS_PLACEHOLDER
from ui.pages import Page, e

DOES = (
    "Reads the government's document and the phone extraction reports you already have "
    "(Cellebrite and Magnet AXIOM exports; the UFDR and AXIOM readers are not yet checked on "
    "real exports), and splits the document into claims.",
    "Checks each claim against the extraction and shows the records it rests on, so you do "
    "the reading of the evidence, not the scrolling.",
    "Marks each claim supported, contradicted or unproven from fixed, versioned rules. "
    "Nothing is supported until you accept its evidence.",
    "Runs on this computer. Cloud AI is used only when your case allows it and you opt in.",
)
DOES_NOT = (
    "Decide anything for you, or give an opinion. Any opinion is yours.",
    "Extract phones, recover data, or replace Cellebrite, AXIOM or your own review.",
    "Treat “not found” as “did not happen”. Each search says what it covered.",
    "Publish any speed or accuracy figure. It has been tested on synthetic cases only.",
)


def help_page(page: Page, report_text: str | None, withheld: str | None, case_open: bool) -> str:
    placeholder = (
        " <span class='muted'>(placeholder: the Mabillon team sets the real address before any "
        "pilot)</span>"
        if SUPPORT_IS_PLACEHOLDER
        else ""
    )
    contact = (
        "<section class='hs support'><h2>Support</h2>"
        f"<p>Email <a href='mailto:{e(SUPPORT_EMAIL)}'>{e(SUPPORT_EMAIL)}</a>{placeholder}.</p>"
        "<p>Say what you did, what you saw and what you expected. "
        "<strong>Never send case content</strong>: no case files, no case database, no "
        "screenshots of evidence, no claim or message text. Attach the bug report below "
        "instead.</p></section>"
    )
    about = (
        "<section class='hs about'><h2>What Mabillon does and doesn't do</h2>"
        "<p>Mabillon is a verification layer on top of Cellebrite and AXIOM.</p>"
        "<div class='dodont'><div><h3>It does</h3><ul>"
        + "".join(f"<li>{e(x)}</li>" for x in DOES)
        + "</ul></div><div><h3>It does not</h3><ul>"
        + "".join(f"<li>{e(x)}</li>" for x in DOES_NOT)
        + "</ul></div></div></section>"
    )
    scope = (
        "It describes this Mabillon install and the case open now (counts and states only)."
        if case_open
        else "No case is open, so it describes this Mabillon install only."
    )
    if report_text is None:
        body = (
            "<p class='flash err'>The bug report was withheld: "
            f"{e(withheld or 'it could not be made')}. Nothing was saved. Tell support that "
            "the bug report was withheld, without sending case content.</p>"
        )
    else:
        body = (
            "<ol class='steps'><li><a class='button' href='/help/bug-report.json' download>"
            "Save the bug report</a></li>"
            "<li>Read it. It is the text below.</li>"
            f"<li>Attach it to an email to {e(SUPPORT_EMAIL)}.</li></ol>"
            "<h3>Left out on purpose</h3><ul>"
            + "".join(f"<li>{e(x)}</li>" for x in bug_report.WITHHELD)
            + "</ul><details class='filetext'><summary>Exactly what the file holds</summary>"
            f"<pre class='bugreport'>{e(report_text)}</pre></details>"
        )
    report = (
        "<section class='hs report'><h2>Send a bug report</h2>"
        "<p>Versions, this computer's system and model setup, the last background job and "
        f"recent errors, with no case data. {e(scope)} You send it yourself.</p>"
        f"{body}</section>"
    )
    return page.wrap(
        "Help",
        "<div class='pg-help'><h1>Help</h1>" + contact + report + about + WORDS + "</div>",
    )


# The screen's own words, defined once (first-time-user review, 2026-11-04). Definitions follow
# the verdict rules (core/audit/rules.py) and the provenance tiers in CLAUDE.md.
_VERDICTS = (
    (
        "Supported",
        "Every core part of the claim is covered and an expert accepted the records "
        "that support it.",
    ),
    (
        "Contradicted",
        "The phone records contradict a core part of the claim: a check on the "
        "records failed, or an expert accepted records that contradict it.",
    ),
    ("Unproven", "Not established either way. It does not mean the claim is false."),
    (
        "Support found: do you agree?",
        "Unproven until you accept the records Mabillon read as support.",
    ),
    ("Unproven, not tested", "Mabillon could not set up what to check, so no record was searched."),
)
_TIERS = (
    ("observed", "Read straight from the extraction."),
    ("derived", "Worked out by code from observed records, such as a local time."),
    ("inferred", "A model's reading, such as a label on a record."),
    ("ai_reviewed", "Accepted by the local AI reviewer. It never counts as confirmed."),
    ("confirmed", "Accepted by a human expert."),
)
_TERMS = (
    (
        "supports, contradicts, complicates, irrelevant",
        "How one record bears on one thing the "
        "claim needs. Each is a proposal until an expert accepts or dismisses it.",
    ),
    ("core", "A part the claim cannot be true without."),
    (
        "Stipulated",
        "A fact the expert sets once for the case, such as who used each phone. "
        "The report lists each one as a limitation. It is not a concession by either side.",
    ),
    (
        "Untested export format",
        "Mabillon has not been tested on this export format or version. "
        "Check results against the source tool.",
    ),
)


def _dl(rows: tuple[tuple[str, str], ...]) -> str:
    return "<dl>" + "".join(f"<dt>{e(t)}</dt><dd>{e(d)}</dd>" for t, d in rows) + "</dl>"


WORDS = (
    "<section class='hs words' id='words'><h2>Words on the screen</h2>"
    "<h3>Verdicts</h3>" + _dl(_VERDICTS)
    + "<h3>Where an item comes from</h3>" + _dl(_TIERS)
    + "<h3>Other words</h3>" + _dl(_TERMS)
    + "</section>"
)  # fmt: skip
