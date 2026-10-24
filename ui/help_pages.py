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
        "<div class='box'><h2>Support</h2>"
        f"<p>Email <a href='mailto:{e(SUPPORT_EMAIL)}'>{e(SUPPORT_EMAIL)}</a>{placeholder}.</p>"
        "<p>Say what you did, what you saw and what you expected. "
        "<strong>Never send case content</strong>: no case files, no case database, no "
        "screenshots of evidence, no claim or message text. Attach the bug report below "
        "instead.</p></div>"
    )
    about = (
        "<div class='box'><h2>What Mabillon does and doesn't do</h2>"
        "<p>Mabillon is a verification layer on top of Cellebrite and AXIOM. It takes the "
        "scrolling, not the judgment.</p>"
        "<h3>It does</h3><ul>"
        + "".join(f"<li>{e(x)}</li>" for x in DOES)
        + "</ul><h3>It does not</h3><ul>"
        + "".join(f"<li>{e(x)}</li>" for x in DOES_NOT)
        + "</ul><p class='muted'>The full one-page explainer is "
        "<code>docs/ONE_PAGER.md</code> in the Mabillon folder.</p></div>"
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
            "<ol><li><a href='/help/bug-report.json' download>Save the bug report</a> "
            "(a small JSON file).</li>"
            "<li>Open it and read it. It is the same text as below.</li>"
            f"<li>Attach it to an email to {e(SUPPORT_EMAIL)}.</li></ol>"
            "<h3>Left out on purpose</h3><ul>"
            + "".join(f"<li>{e(x)}</li>" for x in bug_report.WITHHELD)
            + "</ul><h3>Exactly what the file holds</h3>"
            f"<pre class='bugreport'>{e(report_text)}</pre>"
        )
    report = (
        "<div class='box'><h2>Send a bug report</h2>"
        "<p>The bug report holds Mabillon's versions, this computer's system and model setup, "
        f"the last background job and recent errors, with no case data. {e(scope)} Mabillon "
        "never sends it: you save it and send it yourself.</p>"
        f"{body}</div>"
    )
    return page.wrap("Help", "<h1>Help</h1>" + contact + report + about)
