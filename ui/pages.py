"""Server-rendered pages of the expert review screen. Pure functions of the case database.

No JavaScript, no external fonts, styles or images: every page is one HTML document with an
inline style block (the look is in ui/theme.py; its fonts are vendored and served locally).
Cited text (government document, claim text, evidence quotes, record text) goes through q()
so the forbidden-word check can tell it from the tool's own words.

Every form carries the server's per-session token. Labels come from core/review/status.py, the
same module the report uses, so the screen and the report never disagree. An AI-accepted item
shows its tier as ai_reviewed with "AI-reviewed, not confirmed"; only an expert's acceptance
shows as confirmed.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter
from collections.abc import Iterable
from urllib.parse import quote as urlquote

from core import pipeline
from core.audit import challenge, testability
from core.audit.context import ContextLine, build_context
from core.contracts import (
    CheckOutcome,
    ClaimType,
    EvidenceItem,
    EvidenceStatus,
    ProvenanceTier,
    Stance,
    StipulationStatus,
    Verdict,
    display_tier,
)
from core.hypotheses import explain
from core.ingest import coverage as import_coverage
from core.ingest import forwarded, tested
from core.report.html import CSS as REPORT_CSS
from core.report.html import (
    STANCE_LABEL,
    audit_log_summary,
    build_label,
    claim_format_notices,
    format_notice,
    forwarded_warning,
    labelled_by,
    mixed_app_note,
    quote_check_label,
    rationale_html,
    record_line,
    review_label,
    said,
    sources,
    stand_in_banner,
)
from core.report.hypotheses import CSS as ALTERNATIVES_CSS
from core.report.hypotheses import alternatives_html
from core.report.names import plain_ids
from core.report.paired import CSS as PAIRED_CSS
from core.report.paired import claim_line
from core.report.restore import CSS as RESTORE_CSS
from core.report.selection import CSS as SELECTION_CSS
from core.report.selection import anchor as selection_anchor
from core.report.selection import claim_note
from core.review import activity, device_names
from core.review import flags as F
from core.review import withheld as W
from core.review.activity import VIEW
from core.review.status import (
    AGAINST,
    CONTRADICTION_FOUND,
    GAP_TOPICS,
    HOLDINGS,
    STALE,
    ClaimState,
    agent_fail_step,
    case_holdings,
    claim_name,
    claim_state,
    claim_states,
    queue,
)
from core.selection.audit import selection_audit
from core.selection.paired import paired_check
from ui.theme import FONT_CSS, MARK, THEME_CSS

CONTEXT_WINDOW = 10  # messages either side: about 20 messages of context

UI_CSS = """
tr.target td { font-weight: bold; background: var(--warn); }
.ctx td { font-size: 12px; }
"""


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def q(text: object) -> str:
    """Cited text, never the tool's own words."""
    return f'<span class="q">{html.escape(str(text))}</span>'


def link(path: str, **params: str) -> str:
    if not params:
        return path
    return path + "?" + "&".join(f"{k}={urlquote(v, safe='')}" for k, v in params.items())


class Page:
    """Shared page furniture: token for forms, the reviewing expert, a flash message, the open
    case's name, and a line about background work (an audit or claim proposal running)."""

    def __init__(
        self,
        token: str,
        expert: str | None,
        flash: tuple[str, bool] | None = None,
        case_name: str | None = None,
        notice: str = "",
        busy: bool = False,
        many_cases: bool = False,
        path: str = "",
        cloud: bool = False,
    ):
        self.token = token
        self.expert = expert
        self.flash = flash
        self.case_name = case_name
        self.notice = notice  # HTML from the app, shown on every page while a job runs
        self.busy = busy  # an audit is running: no re-run of the verdicts
        self.many_cases = many_cases  # the screen was started on a cases folder
        self.path = path  # the page's own path, to mark its tab
        self.cloud = cloud  # the open case sends stance questions to the cloud model

    def form(
        self, action: str, body: str, cls: str = "box", back: str = "", anchor: str = ""
    ) -> str:
        """anchor: the id of the element to come back to after the post, so a click does not
        land the expert at the top of a long page."""
        if back and anchor:
            back = f"{back}#{urlquote(anchor, safe='')}"
        return (
            f'<form method="post" action="{e(action)}" class="{cls}">'
            f'<input type="hidden" name="token" value="{e(self.token)}">'
            + (f'<input type="hidden" name="next" value="{e(back)}">' if back else "")
            + body
            + "</form>"
        )

    def wrap(
        self,
        title: str,
        body: str,
        banner: str = "",
        refresh: int | None = None,
        wide: bool = False,
    ) -> str:
        who = (
            f"Reviewing as <strong>{e(self.expert)}</strong>"
            if self.expert
            else "<strong>Enter your name on the case page before reviewing.</strong>"
        )
        flash = ""
        if self.flash:
            msg, err = self.flash
            # A toast: the page may open part-way down, at the item acted on.
            flash = f'<div class="flash toast{" err" if err else ""}" role="status">{e(msg)}</div>'
        meta = f"<meta http-equiv='refresh' content='{int(refresh)}'>" if refresh else ""
        groups = [[("/cases", "Cases")]] if self.many_cases else []
        if self.case_name is not None:
            groups += TAB_GROUPS
        groups.append([("/help", "Help")])
        links = "<span class='sep' aria-hidden='true'></span>".join(
            "".join(
                f"<a href='{href}'{' class=on' if _tab(self.path) == href else ''}>{label}</a>"
                for href, label in group
            )
            for group in groups
        )
        case = (
            f"<div class='casename'>{q(self.case_name)}<small>case open on this computer</small>"
            "</div>"
            if self.case_name is not None
            else ""
        )
        notice = f"<div class='flash'>{self.notice}</div>" if self.notice else ""
        return (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>{meta}"
            f"<title>{e(title)} · Mabillon</title>"
            f"<style>{FONT_CSS}{REPORT_CSS}{RESTORE_CSS}{SELECTION_CSS}{PAIRED_CSS}{ALTERNATIVES_CSS}{UI_CSS}{THEME_CSS}</style>"
            "</head><body>"
            "<header class='top'><div class='bar'>"
            f"<a class='brand' href='{'/' if self.case_name is not None else '/cases'}'>"
            f"{MARK}<span>Mabillon</span></a>{case}<div class='right'>"
            + (
                "<a class='pill' href='/setup#cloud'>Cloud labels on · one question at a time "
                "goes to Anthropic</a>"
                if self.cloud
                else "<span class='pill'>Offline · nothing leaves this computer</span>"
            )
            + f"<span class='who'>{who}</span></div></div>"
            f"<nav class='tabs'>{links}</nav></header>"
            f"<main{' class=wide' if wide else ''}>{notice}{flash}{banner}{body}</main>"
            "</body></html>"
        )


# the top tabs in three groups: the review itself, tools to look closer, and the case's set-up
TAB_GROUPS = [
    [("/", "Case"), ("/claims", "Claims"), ("/report", "Report")],
    [
        ("/identities", "Identities"),
        ("/exhibits", "Exhibits"),
        ("/selection", "Selection"),
        ("/timeline", "Timeline"),
        ("/gaps", "Gaps"),
    ],
    [
        ("/claim/new", "Add a claim"),
        ("/setup", "Set up and run"),
        ("/log", "Audit log"),
        ("/activity", "Activity"),
    ],
]


def _tab(path: str) -> str:
    """The tab a page sits under: a claim and its evidence under the queue."""
    if path in ("/claim", "/evidence"):
        return "/claims"
    if path in ("/exhibit", "/exhibit/match", "/request-letter"):
        return "/exhibits"
    if path == "/selection/context":
        return "/selection"
    if path == "/run":
        return "/setup"
    return path


# ---------------------------------------------------------------- banners


def run_banner(conn: sqlite3.Connection, page: Page, back: str) -> str:
    run = pipeline.view_run(conn)
    if run is None:
        return (
            "<div class='banner'><strong>No audit has run on this case.</strong> "
            "<a href='/setup'>Set up and run the audit</a>.</div>"
        )
    out = []
    if run.get("partial"):
        out.append(partial_banner(conn, run))
    if run.get("fake"):
        out.append(stand_in_banner(run))
    later = conn.execute(
        "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind = 'expert'"
        " AND decided_at_utc > ?",
        (run["started_at_utc"],),
    ).fetchone()[0]
    stips = conn.execute(
        "SELECT COUNT(*) FROM stipulations WHERE decided_at_utc > ?", (run["started_at_utc"],)
    ).fetchone()[0]
    if (later or stips) and not run.get("partial") and not page.busy:
        what = []
        if later:
            what.append(f"{later} evidence decision{'' if later == 1 else 's'}")
        if stips:
            what.append(f"{stips} stipulation change{'' if stips == 1 else 's'}")
        out.append(
            "<div class='banner'><strong>Verdicts are out of date.</strong> You made "
            f"{' and '.join(what)} after the last verdict run. Re-run the verdicts to apply them. "
            "This runs the verdict rules only; no model is called."
            + page.form(
                "/redecide",
                "<button type='submit' class='primary'>Re-run verdicts</button>",
                "",
                back,
                "verdict" if back.startswith("/claim?") else "",
            )
            + "</div>"
        )
    return "".join(out)


def partial_banner(conn: sqlite3.Connection, run: dict) -> str:
    """Says plainly that the run shown has not finished, and which run each claim comes from."""
    order = run.get("claim_order") or ()
    state = {
        "running": "is still running",
        "stopped": "was stopped",
        "failed": "stopped on an error",
    }
    older = pipeline.last_run(conn)
    hidden = (
        f" The earlier completed run <span class='mono'>{e(older['run_id'])}</span> is not "
        "shown; every verdict here comes from the run above."
        if older
        else ""
    )
    return (
        f"<div class='banner'><strong>Labeling incomplete: this audit "
        f"{state.get(run['status'], 'has not finished')}.</strong> Showing run "
        f"<span class='mono'>{e(run['run_id'])}</span>: {len(run['manifest'])} of {len(order)} "
        'claims are finished and can be reviewed. Claims marked "Labeling incomplete" have no '
        f"verdict yet. <a href='/run'>See the audit's progress</a>.{hidden}</div>"
    )


# ---------------------------------------------------------------- case overview


def overview(conn: sqlite3.Connection, page: Page) -> str:
    srcs = sources(conn)
    run = pipeline.view_run(conn)
    govdocs = list(conn.execute("SELECT id, title, doc_kind FROM govdocs ORDER BY id"))
    out = ["<h1>Case overview</h1>"]
    if not page.expert:
        out.append(
            page.form(
                "/expert",
                "<p><strong>Who is reviewing?</strong> Your name is recorded with every "
                "decision in the audit log.</p><input type='text' name='name' required "
                "maxlength='60' placeholder='Your name'> <button type='submit' class='primary'>"
                "Start reviewing</button>",
            )
        )
    else:
        out.append(
            "<details><summary>Change reviewer</summary>"
            + page.form(
                "/expert",
                "<input type='text' name='name' required maxlength='60' placeholder='Your name'>"
                " <button type='submit'>Change</button>",
            )
            + "</details>"
        )

    out.append(_format_notices(conn))
    out.append("<h2 id='audit'>Audit</h2>")
    if run is None:
        out.append("<p>No audit has run yet. <a href='/setup'>Set up and run the audit</a>.</p>")
    else:
        mode = (
            f"verdict rules re-run after expert review, from {e(run['from_run'])}"
            if run.get("mode") == "rules_only"
            else "audit not finished, labeling incomplete"
            if run.get("partial")
            else "full audit"
        )
        out.append(
            f"<p>Latest run <span class='mono'>{e(run['run_id'])}</span> ({mode}), started "
            f"{e(run['started_at_utc'])}, Mabillon {e(build_label(run))}, rule version "
            f"{e(run['rule_version'])}, quote check "
            f"{e(quote_check_label(run))}, contracts {e(run['contracts_version'])}.</p>"
        )
        states = claim_states(conn, run=run)
        tally = Counter((st.label, _vcls(st)) for st in states)
        waiting = sum(1 for st in states if needs_you(st))
        out.append(
            "<div class='casestatus'>"
            f"<a class='button primary' href='/claims'>{waiting} "
            f"{'claim needs' if waiting == 1 else 'claims need'} you</a>"
            "<ul class='findings'>"
            + "".join(
                f"<li><span class='verdict {e(css)}'>{e(label)}</span> {n}</li>"
                for (label, css), n in sorted(tally.items())
            )
            + "</ul></div>"
            "<p class='muted'>Accepting or dismissing evidence does not change a verdict until "
            "you re-run the verdicts.</p>"
        )
        out.append(_withheld_overview(states))
        if not run.get("partial") and not page.busy:
            out.append(
                page.form(
                    "/redecide",
                    "<button type='submit' class='primary'>Re-run verdicts (rules only, no model)"
                    "</button>",
                    back="/",
                    anchor="audit",
                )
            )
    out.append(
        "<p class='muted'>A full audit (new evidence search and model labels) runs from "
        "<a href='/setup'>Set up and run</a>, in the background.</p>"
    )
    out.append("<h2>Government documents</h2>")
    if govdocs:
        out.append("<ul>" + "".join(f"<li>{q(t)} ({e(k)})</li>" for _, t, k in govdocs) + "</ul>")
    else:
        out.append("<p class='muted'>None imported.</p>")

    out.append(
        "<details class='custody'><summary>Files and their SHA-256 hashes (chain of custody)"
        "</summary><h2>Sources</h2><table><thead><tr><th>File</th><th>Kind</th><th>Coverage</th>"
        "<th>Extraction</th><th>SHA-256</th><th>Tool</th><th>Imported (UTC)</th></tr></thead>"
    )
    for s in srcs:
        out.append(
            f"<tr><td>{q(s[4])}<br><span class='mono'>{e(s[0])}</span></td><td>{e(s[1])}</td>"
            f"<td>{e(s[2])}</td><td>{e(s[3])}</td><td class='mono'>{e(s[5])}</td>"
            f"<td>{e(s[6])} {e(s[7])}</td><td>{e(s[8])}</td></tr>"
        )
    out.append("</table></details>")

    out.append(_devices(conn, page, "/"))

    out.append(flags_overview(conn))
    summary = audit_log_summary(conn)
    out.append(
        f"<h2>Audit log</h2><p>{summary['entries']} entries. Hash chain "
        f"{'verified' if summary['chain_ok'] else '<strong>FAILED VERIFICATION</strong>'}. "
        "<a href='/log'>Open the log</a>.</p>"
    )
    return page.wrap("Case", "".join(out), run_banner(conn, page, "/"))


def _format_notices(conn: sqlite3.Connection) -> str:
    """Each evidence source's format notice (core/ingest/tested.py), as the report's Limitations
    print it."""
    notices = "".join(format_notice(c) for c in tested.all_sources(conn))
    return f"<div class='banner' id='formats'>{notices}</div>" if notices else ""


def _withheld_overview(states: list[ClaimState]) -> str:
    """The withheld rationales on the case, with the report's count (core/review/withheld.py)."""
    rows = [(st, w) for st in states for w in st.withheld]
    if not rows:
        return ""
    irrelevant = {x.id for st in states for x in st.evidence if x.stance == Stance.IRRELEVANT}
    items = "".join(
        "<li><a href='"
        + e(
            link("/evidence", id=w.evidence_id)
            if w.evidence_id in irrelevant  # listed on the claim page without its card
            else f"{link('/claim', id=st.claim.id)}#{w.evidence_id}"
        )
        + f"'>{e(st.name)}</a> <span class='mono'>{e(w.evidence_id)}</span>: "
        + ("acknowledged" if w.acknowledged else "<strong>not yet acknowledged</strong>")
        + "</li>"
        for st, w in rows
    )
    return (
        f"<div class='card' id='withheld'><div class='in'><p><strong>"
        f"{e(W.summary([w for _st, w in rows]))}</strong></p><ul>{items}</ul></div></div>"
    )


def _identities_step(conn: sqlite3.Connection) -> str:
    """One line on the set-up page: the people the document names, beyond the phone owners."""
    added = conn.execute(
        "SELECT COUNT(*) FROM persons WHERE id NOT IN (SELECT person_id FROM stipulations)"
    ).fetchone()[0]
    by = dict(conn.execute("SELECT status, COUNT(*) FROM identity_links GROUP BY status"))
    return (
        "<p><strong>Other people the document names.</strong> A claim about someone with no "
        "account in the case (a surname the document prints in capitals, or a contact name) "
        "cannot be tested "
        f"until you add the name and decide who is behind it. {added} added; "
        f"{by.get('confirmed', 0)} link(s) confirmed, {by.get('proposed', 0)} proposed. "
        "<a href='/identities'>Open Identities</a>.</p>"
    )


def _devices(conn: sqlite3.Connection, page: Page, back: str, heading: bool = True) -> str:
    devices = list(conn.execute("SELECT id, label, model, source_id FROM devices ORDER BY id"))
    stips = {s.subject_id: s for s in pipeline.load_stipulations(conn)}
    named = device_names.logged_names(conn)
    out = [
        ("<h2>Devices and stipulations</h2>" if heading else "")
        + "<p>Who used each phone is a stipulation you make, not "
        "a finding. Every report lists it as a limitation.</p>"
        "<p>If the document calls a phone something else, such as TARGET PHONE or Item 1, "
        "give that name here, as the document writes it, so the audit knows which phone a "
        "claim means. Separate names with commas. Every report lists the names you gave.</p>"
        "<table><thead><tr><th>Device</th><th>Source</th><th>Stipulated user</th>"
        "<th>Change</th><th>Document names</th></tr></thead>"
    ]
    for dev_id, label, model, source_id in devices:
        st = stips.get(dev_id)
        if st is not None and st.status == StipulationStatus.CONFIRMED:
            who = f"{q(st.statement)}<br><span class='muted'>by {e(st.decided_by)}</span>"
            change = page.form(
                "/stipulation/withdraw",
                f"<input type='hidden' name='id' value='{e(st.id)}'>"
                "<button type='submit'>Withdraw</button>",
                "inline",
                back,
                f"dev-{dev_id}",
            )
        else:
            who = "<span class='muted'>none</span>" + (
                " (withdrawn)" if st is not None and st.status == StipulationStatus.REJECTED else ""
            )
            change = ""
        change += page.form(
            "/stipulate",
            f"<input type='hidden' name='device' value='{e(dev_id)}'>"
            "<input type='text' name='person' required maxlength='120' placeholder='Person'>"
            " <button type='submit'>Stipulate</button>",
            "inline",
            back,
            f"dev-{dev_id}",
        )
        names = page.form(
            "/device/names",
            f"<input type='hidden' name='device' value='{e(dev_id)}'>"
            f"<input type='text' name='names' maxlength='400' placeholder='TARGET PHONE'"
            f" value='{e(', '.join(named.get(dev_id, [])))}'>"
            " <button type='submit'>Save names</button>",
            "inline",
            back,
            f"dev-{dev_id}",
        )
        out.append(
            f"<tr id='dev-{e(dev_id)}'><td>{q(label)} <span class='mono'>{e(dev_id)}</span><br>"
            f"{q(model or '')}</td>"
            f"<td class='mono'>{e(source_id)}</td><td>{who}</td><td>{change}</td>"
            f"<td>{names}</td></tr>"
        )
    out.append("</table>")
    if not devices:
        out.append("<p class='muted'>No devices imported.</p>")
    return "".join(out)


# ---------------------------------------------------------------- queue


def _vcls(st: ClaimState) -> str:
    """The pill's classes: the verdict's, plus its own style for a claim nothing tested."""
    return f"{st.css} v-nt" if st.untested else st.css


def _tally(states: list[ClaimState]) -> str:
    """A bar split by finding, then one chip per finding with its count."""
    if not states:
        return ""
    known = {"v-sup", "v-con", "v-unp", "v-await", "v-confirm"}
    by_label = Counter((st.label, _vcls(st)) for st in states)
    bar = "".join(
        f"<span class='{css if css in known else 'other'}' "
        f"style='width:{100 * n / len(states):.2f}%'></span>"
        for (_, css), n in sorted(by_label.items(), key=lambda kv: kv[0][1])
    )
    chips = "".join(
        f"<span class='verdict {css}'>{e(label)} <b>{n}</b></span>"
        for (label, css), n in sorted(by_label.items(), key=lambda kv: kv[0][1])
    )
    return f"<div class='tally'>{bar}</div><div class='counts'>{chips}</div>"


def _ledger(states: list[ClaimState], current: str | None = None, compact: bool = False) -> str:
    rows = []
    for st in states:
        needs = "" if compact else " ".join(t for _, t in st.needs())
        rows.append(
            f"<li{' class=on' if st.claim.id == current else ''}>"
            "<div class='row'><div class='head'><span class='meta'>"
            f"<a href='{e(link('/claim', id=st.claim.id))}'>{e(st.name)}</a> · {e(st.where)} · "
            f"{e(st.claim.claim_type.value.replace('_', ' '))}</span>"
            f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
            f"<div class='text'>{q(st.claim.text)}</div>"
            + (f"<div class='needs'>{e(needs)}</div>" if needs else "")
            + "</div></li>"
        )
    return f"<ul class='ledger'>{''.join(rows)}</ul>"


# where a claim sits on the overview: what waits on the expert first, then the findings
GROUPS = (
    ("you", "Needs you", "Waiting on your review"),
    ("con", "Contradicted", "The verdict rules or an expert decided it"),
    ("unp", "Unproven", "The claim says more than the data shows"),
    ("sup", "Supported", "An expert accepted its key evidence"),
    ("not", "Not audited", "No verdict yet"),
)
NEEDS_YOU = 4  # needs() priority at or below this waits on the expert


def needs_you(st: ClaimState) -> bool:
    """The claim waits on the expert: an urgent need, a supported verdict that rests on the AI
    reviewer rather than an expert, support the AI reviewer dismissed that no expert has seen, or
    a verdict made stale by a later change.
    The overview and the case page count the same claims."""
    if st.decision is None or st.incomplete or pipeline.RULES_PENDING_REASON in st.decision.reasons:
        return False  # no verdict was decided: Not audited, like _group()
    return (
        st.priority <= NEEDS_YOU
        or st.css == "v-supai"
        or st.ai_dismissed > 0
        or st.explain_lines() == [STALE]  # its verdict waits on a re-run
    )


def _group(st: ClaimState) -> str:
    if st.decision is None or st.incomplete or pipeline.RULES_PENDING_REASON in st.decision.reasons:
        return "not"  # no verdict was decided: not a gap in the data
    if needs_you(st):
        return "you"
    if st.css == "v-con":
        return "con"
    if st.css in ("v-sup", "v-supai"):
        return "sup"
    return "unp"


def _claim_row(st: ClaimState, group: str) -> str:
    """One claim on the overview: what it needs from the expert, or why it is unproven. The
    standing "verdict not yet confirmed" reminder is left out here; the claim page shows it."""
    note = ""
    if group == "you":
        lines = _you_lines(st)
        note = f"<div class='needs'>{e(' '.join(lines))}</div>" if lines else ""
    if group in ("you", "unp"):
        note += _gap_lines(st)
    return (
        "<li><div class='row'><div class='head'><span class='meta'>"
        f"<a href='{e(link('/claim', id=st.claim.id))}'>{e(st.name)}</a> · {e(st.where)} · "
        f"{e(st.claim.claim_type.value.replace('_', ' '))}</span>"
        f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
        f"<div class='text'>{q(st.claim.text)}</div>{note}</div></li>"
    )


def _gap_lines(st: ClaimState) -> str:
    """Why the claim is unproven apart from what waits on the expert (same words as the report)."""
    return "".join(
        f"<div class='gap'><b>{e(topic)}</b> {e(text)}</div>" for topic, text in st.explain_lines()
    )


def _you_lines(st: ClaimState) -> list[str]:
    """What the claim needs from the expert, without the standing "verdict not yet confirmed"
    reminder (priority 6) that every unreviewed verdict carries."""
    lines = [t for p, t in st.needs() if p < 6]
    if st.css == "v-supai":
        lines.insert(0, "Part of its support rests on AI review, not an expert's acceptance.")
    return lines


def _tile(group: str, name: str, sub: str, n: int) -> str:
    """A count; it links to its section when there is one (Needs you starts at the next-up card)."""
    inner = (
        f"<span class='name'>{e(name)}</span><span class='n'>{n}</span>"
        f"<span class='sub'>{e(sub)}</span>"
    )
    if not n:
        return f"<div class='tile t-{group} empty'>{inner}</div>"
    href = "#next" if group == "you" else f"#{group}"
    return f"<a class='tile t-{group}' href='{href}'>{inner}</a>"


def _next_up(st: ClaimState) -> str:
    lines = _you_lines(st)
    return (
        "<section class='nextup' id='next'><div class='head'><span class='meta'>Next up · "
        f"<a href='{e(link('/claim', id=st.claim.id))}'>{e(st.name)}</a> · {e(st.where)}</span>"
        f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
        f"<blockquote class='claimtext'>{q(st.claim.text)}</blockquote>"
        f"<p>{e(' '.join(lines))}</p>{_gap_lines(st)}"
        f"<a class='button primary' href='{e(link('/claim', id=st.claim.id))}'>Review it</a>"
        "</section>"
    )


def _group_rows(rows: list[ClaimState], g: str, folded: bool) -> str:
    """A group's claims; settled groups fold while claims still wait on the expert."""
    ul = f"<ul class='ledger'>{''.join(_claim_row(st, g) for st in rows)}</ul>"
    if not folded:
        return ul
    n = len(rows)
    show = f"Show {n} claim{'s' if n != 1 else ''}"
    return f"<details class='fold'><summary>{show}</summary>{ul}</details>"


def claims_queue(conn: sqlite3.Connection, page: Page) -> str:
    states = queue(conn)
    by: dict[str, list[ClaimState]] = {g: [] for g, _, _ in GROUPS}
    for st in states:
        by[_group(st)].append(st)
    you, total = len(by["you"]), len(states)
    done = total - you - len(by["not"])
    if not total:
        head = "No claims yet"
    elif you:
        head = f"{you} claim{'s' if you > 1 else ''} need{'' if you > 1 else 's'} you."
    else:
        head = "Nothing waits on you."
    out = [
        "<div class='eyebrow'>Claims</div>"
        f"<div class='overview-head'><div><h1>{e(head)}</h1><p class='muted'>Nothing becomes "
        "supported until you accept its key evidence and re-run the verdicts. AI-accepted "
        "evidence only sorts the work.</p></div>"
        + (
            f"<div class='progress'><div class='lbl'><span>Settled"
            f"</span><b>{done} of {total}</b></div><div class='track'>"
            f"<span style='width:{100 * done / total:.2f}%'></span></div></div>"
            if total
            else ""
        )
        + "</div>",
        "<nav class='tiles'>"
        + "".join(_tile(g, name, sub, len(by[g])) for g, name, sub in GROUPS if by[g] or g != "not")
        + "</nav>",
    ]
    if by["you"]:
        out.append(_next_up(by["you"][0]))
    for g, name, sub in GROUPS:
        rows = by[g][1:] if g == "you" else by[g]
        if g == "you" and not rows:
            continue
        if not by[g]:
            continue
        title = "Also waiting on you" if g == "you" else name
        extra = ""
        if g == "unp":
            kinds = Counter(k for st in rows for k in st.gaps())
            extra = "".join(
                f"<span class='stpill'>{e(GAP_TOPICS[k])} <b>{n}</b></span>"
                for k, n in kinds.most_common()
            )
            sub = "What the data does not show. Not found never means it did not happen."
        out.append(
            f"<section class='group' id='{g}'><div class='ghead'><h2>{e(title)}</h2>"
            f"<span class='muted'>{len(rows)} claim{'s' if len(rows) != 1 else ''} · {e(sub)}"
            f"</span></div>"
            + (f"<div class='kinds'>{extra}</div>" if extra else "")
            + _group_rows(rows, g, folded=g in ("con", "sup") and bool(by["you"]))
            + "</section>"
        )
    removed = [c for c in pipeline.load_claims(conn, include_removed=True) if c.status == "removed"]
    if removed:
        out.append(
            "<p class='muted'>Removed claims: "
            + ", ".join(
                f"<a href='{e(link('/claim', id=c.id))}'>"
                f"{e(claim_name(conn, c.id, c.paragraph_id))}</a>"
                for c in removed
            )
            + "</p>"
        )
    return page.wrap("Claims queue", "".join(out), run_banner(conn, page, "/claims"))


# ---------------------------------------------------------------- claim


def _tier_badge(item: EvidenceItem, last_kind: str | None) -> str:
    tier = display_tier(item)
    if tier == ProvenanceTier.AI_REVIEWED:
        return "<span class='badge b-ai'>ai_reviewed: AI-reviewed, not confirmed</span>"
    if tier == ProvenanceTier.CONFIRMED and last_kind == "expert":
        return "<span class='badge b-conf'>confirmed: accepted by an expert</span>"
    return f"<span class='badge b-open'>{e(tier.value)}</span>"


def _decide_form(page: Page, item: EvidenceItem, decided: bool, back: str) -> str:
    reopen = "<button type='submit' name='status' value='open'>Reopen</button>" if decided else ""
    return page.form(
        "/evidence/decide",
        f"<input type='hidden' name='id' value='{e(item.id)}'>"
        "<input type='text' class='wide' name='reason' required maxlength='500' "
        "placeholder='Why, in one sentence (recorded in the audit log)'><br>"
        "<button type='submit' name='status' value='accepted'>Accept</button>"
        "<button type='submit' name='status' value='dismissed'>Dismiss</button>" + reopen,
        back=back,
        anchor=item.id,
    )


def _confirm_form(page: Page, item: EvidenceItem, back: str) -> str:
    """Rule 1b's finalizing step: one click accepts the contradiction with the expert's reason
    and re-runs the verdicts, so the claim becomes contradicted at once."""
    return page.form(
        "/evidence/confirm",
        f"<input type='hidden' name='id' value='{e(item.id)}'>"
        "<input type='text' class='wide' name='reason' required maxlength='500' "
        "placeholder='Why, in one sentence (recorded in the audit log)'><br>"
        "<button type='submit' name='status' value='accepted'>Confirm contradiction</button>"
        "<button type='submit' name='status' value='dismissed'>Dismiss</button>",
        back=back,
        anchor=item.id,
    )


def _acknowledge_form(page: Page, item: EvidenceItem, back: str) -> str:
    """The expert's acknowledgment of a withheld rationale (core/review/withheld.py)."""
    return page.form(
        "/rationale/acknowledge",
        f"<input type='hidden' name='id' value='{e(item.id)}'>"
        "<button type='submit'>Acknowledge the withheld rationale</button> <span class='muted'>"
        "Recorded in the audit log with this item, the word and the rationale's SHA-256. Needed "
        "before you confirm or override the claim's verdict.</span>",
        back=back,
        anchor=item.id,
    )


def evidence_card(
    conn: sqlite3.Connection,
    page: Page,
    item: EvidenceItem,
    last_kind: str | None,
    back: str,
    found: dict[str, str] | None = None,
    claim_id: str | None = None,
    flagged: bool = False,
    run_id: str | None = None,
    confirm: bool = False,
    around: int = 0,
    threads: dict[str, list[str]] | None = None,
    challenged: frozenset[str] = frozenset(),
) -> str:
    """claim_id: the claim page shows the card; it then carries the optional label flag.
    confirm: a contradiction waiting for the expert (rule 1b), shown with the confirm step.
    around: messages shown either side of the record, as a conversation (0: the quote only).
    threads: the page's cache of thread orders, so many cards read each thread once.
    challenged: the items the challenge step stored in the audit on screen, read once a page."""
    stance_cls = "b-against" if item.stance in AGAINST else "b-open"
    flag = ""
    if claim_id is not None:
        flag = _flag_label_form(page, claim_id, item, back, run_id)
    withheld = W.for_item(conn, item)
    return (
        f"<div class='item' id='{e(item.id)}'>"
        f"<span class='badge {stance_cls}'>{e(STANCE_LABEL[item.stance])}</span>"
        f"{_tier_badge(item, last_kind)}"
        + ("<span class='badge b-flag'>flagged by you</span>" if flagged else "")
        + ("<span class='badge b-withheld'>needs expert review</span>" if withheld else "")
        + (
            f"<span class='badge b-challenge'>{e(challenge.FOUND_MARK)}</span>"
            if item.id in challenged
            else ""
        )
        + _conversation(conn, item, around, threads)
        + f"<p>{record_line(conn, item.record_id, found)}</p>"
        "<details class='more'><summary>Source and model note</summary>"
        f"<p><span class='mono'>{e(item.ref.source_id)} {e(item.ref.locator)} · "
        f"{e(item.record_id)}</span></p>"
        f"<p class='muted'>{e(labelled_by(conn, item.model_run_id))}."
        + ("" if withheld else f" {rationale_html(item, None)}")
        + "</p></details>"
        + (
            f"<p>{rationale_html(item, withheld)}</p>"
            + ("" if withheld.acknowledged else _acknowledge_form(page, item, back))
            if withheld
            else ""
        )
        + f"<p><strong>Review:</strong> {review_label(conn, item)} · "
        f"<a href='{e(link('/evidence', id=item.id))}'>See about 20 messages around it</a></p>"
        + (
            _confirm_form(page, item, back)
            if confirm
            else _decide_form(page, item, last_kind == "expert", back)
        )
        + f"{flag}</div>"
    )


def _conversation(
    conn: sqlite3.Connection,
    item: EvidenceItem,
    around: int,
    threads: dict[str, list[str]] | None = None,
) -> str:
    """The verified quote, and with around > 0 the record among its neighbours."""
    quote = f"<blockquote>{q(item.quote)}</blockquote>"
    lines = build_context(conn, item.record_id, around, threads=threads) if around else []
    if len(lines) < 2:  # no neighbours (a contact, a call): the quote says it all
        return quote
    return (
        f"<div class='thread mini'>{''.join(_msg(ln) for ln in lines)}</div>"
        f"<p class='quoted'><span class='muted'>Quoted:</span> {q(item.quote)}</p>"
    )


def _msg(ln: ContextLine) -> str:
    """One message as a chat bubble; the record under review is highlighted."""
    shown = f" (shown as {q(ln.shown_as)})" if ln.shown_as else ""
    side = " out" if ln.direction == "outgoing" else ""
    tag = "<span class='cited'>This record</span>" if ln.is_target else ""
    return (
        f"<div class='msg{side}{' target' if ln.is_target else ''}'>"
        f"<div class='who2'>{q(ln.sender)}{shown} · {e(ln.direction)}</div>"
        f"<div class='body'>{q(ln.body)}</div>"
        f"<div class='t'>{tag}{e(ln.local_time)}</div></div>"
    )


# ---------------------------------------------------------------- flags (optional feedback)

FLAG_HELP = (
    "Optional. A flag goes into your flag summary for Mabillon's error log. It changes no "
    "verdict and nothing is sent."
)


def _choices(values: Iterable[str], labels: dict[str, str]) -> str:
    return "".join(f"<option value='{e(v)}'>{e(labels.get(v, v))}</option>" for v in values)


def _flag_fields(claim_id: str, kind: str, run_id: str | None) -> str:
    """run_id: the audit this page shows; a flag sent after it changed is refused."""
    return (
        f"<input type='hidden' name='claim' value='{e(claim_id)}'>"
        f"<input type='hidden' name='kind' value='{e(kind)}'>"
        f"<input type='hidden' name='seen_run' value='{e(run_id or '')}'>"
    )


def _note_field() -> str:
    return (
        f"<input type='text' class='wide' name='note' maxlength='{F.NOTE_MAX}' "
        "placeholder='Note (optional)'><br>"
    )


def _flag_label_form(
    page: Page, claim_id: str, item: EvidenceItem, back: str, run_id: str | None
) -> str:
    labels = {**{s.value: STANCE_LABEL[s] for s in Stance}, F.NOT_SURE: "Not sure"}
    return (
        "<details class='flag'><summary>Flag this label</summary>"
        + page.form(
            "/flag/add",
            _flag_fields(claim_id, F.WRONG_LABEL, run_id)
            + f"<input type='hidden' name='evidence' value='{e(item.id)}'>"
            "It should be: <select name='should_be'>"
            + _choices(
                [
                    F.NOT_SURE,
                    *(v for v in F.STANCE_CHOICES if v not in (item.stance.value, F.NOT_SURE)),
                ],
                labels,
            )
            + "</select> "
            + _note_field()
            + f"<button type='submit'>Save flag</button> <span class='muted'>{e(FLAG_HELP)}"
            "</span>",
            back=back,
            anchor=item.id,
        )
        + "</details>"
    )


def _flag_verdict_form(conn: sqlite3.Connection, page: Page, st: ClaimState, back: str) -> str:
    labels = {v.value: v.value.capitalize() for v in Verdict} | {F.NOT_SURE: "Not sure"}
    d = st.decision
    gave = F.baker_verdict(conn, st.claim.id, st.run_id, d.verdict.value) if d else None
    return (
        "<details class='flag'><summary>Flag: I disagree with this verdict</summary>"
        + page.form(
            "/flag/add",
            _flag_fields(st.claim.id, F.VERDICT, st.run_id)
            + "It should be: <select name='should_be'>"
            + _choices(
                [F.NOT_SURE, *(v for v in F.VERDICT_CHOICES if v not in (F.NOT_SURE, gave))],
                labels,
            )
            + "</select> "
            + _note_field()
            + f"<button type='submit'>Save flag</button> <span class='muted'>{e(FLAG_HELP)}"
            "</span>",
            back=back,
            anchor="verdict",
        )
        + "</details>"
    )


def _flag_missed_form(page: Page, st: ClaimState, back: str) -> str:
    return (
        "<details class='flag' id='flag-missed'><summary>Flag a record Mabillon missed</summary>"
        + page.form(
            "/flag/add",
            _flag_fields(st.claim.id, F.MISSED_RECORD, st.run_id)
            + f"<input type='text' class='wide' name='record' maxlength='{F.RECORD_MAX}' "
            "placeholder='Where it is, for example the file and row (optional)'><br>"
            + _note_field()
            + f"<button type='submit'>Save flag</button> <span class='muted'>{e(FLAG_HELP)}"
            "</span>",
            back=back,
            anchor="flag-missed",
        )
        + "</details>"
    )


def _irrelevant_list(
    conn: sqlite3.Connection, items: list[EvidenceItem], flagged: set, withheld: set
) -> str:
    """Records the model labeled irrelevant, folded away; each opens on its own page, where a
    wrong 'irrelevant' can be flagged and a withheld rationale acknowledged. The list opens by
    itself while one of its rationales is withheld."""
    rows = "".join(
        f"<li>{q(x.quote)} · {record_line(conn, x.record_id)} · "
        f"<a href='{e(link('/evidence', id=x.id))}'>Open, or flag this label</a>"
        + (" <span class='badge b-flag'>flagged by you</span>" if x.id in flagged else "")
        + (" <span class='badge b-withheld'>needs expert review</span>" if x.id in withheld else "")
        + "</li>"
        for x in items
    )
    shown = " open" if any(x.id in withheld for x in items) else ""
    return (
        f"<details id='irrelevant'{shown}><summary>{len(items)} retrieved records were labeled "
        f"irrelevant</summary><ul>{rows}</ul></details>"
    )


def _flag_target(f: F.Flag) -> str:
    if f.kind == F.WRONG_LABEL:
        was = e(f.at_flag.get("stance") or "?")
        return (
            f"label {was} on <a href='#{e(f.evidence_id)}'>this item</a>, should be "
            f"{e(f.should_be)}"
        )
    if f.kind == F.VERDICT:
        return f"verdict {e(f.at_flag.get('verdict') or 'none')}, should be {e(f.should_be)}"
    return f"record: {said(f.record)}" if f.record else "a record (place not given)"


def _flags_section(page: Page, items: list[F.Flag], back: str, run_id: str | None) -> str:
    if not items:
        return ""
    rows = []
    for f in items:
        note = f" Note: {said(f.note)}" if f.note else ""
        rows.append(
            f"<li><strong>{e(F.KINDS[f.kind])}</strong>: "
            + _flag_target(f)
            + f".{note} <span class='muted'>{e(f.actor)}, {e(f.at_utc)}"
            + (", made on an earlier run" if f.at_flag.get("run_id") != run_id else "")
            + "</span>"
            + page.form(
                "/flag/withdraw",
                f"<input type='hidden' name='flag' value='{e(f.id)}'>"
                "<button type='submit'>Withdraw</button>",
                cls="inline",
                back=back,
                anchor="flags",
            )
            + "</li>"
        )
    return (
        f"<h2 id='flags'>Your flags on this claim ({len(items)})</h2>"
        f"<p class='muted'>{e(FLAG_HELP)}</p><ul class='flags'>{''.join(rows)}</ul>"
    )


def flags_overview(conn: sqlite3.Connection) -> str:
    """The case page's flag line and the redacted summary download."""
    active = F.active_flags(conn)
    by_kind = Counter(f.kind for f in active)
    counts = ", ".join(f"{F.KINDS[k].lower()} {n}" for k, n in sorted(by_kind.items()))
    return (
        "<h2 id='flags'>Flags for Mabillon's error log</h2>"
        f"<p>{len(active)} flag(s){': ' + e(counts) if counts else ''}. Flag a wrong label, a "
        "missed record or a verdict you disagree with on any claim page.</p>"
        "<form method='get' action='/flags/summary.json' class='box'>"
        "<input type='text' name='pilot' maxlength='60' placeholder='Pilot name (optional)'> "
        "<button type='submit'>Download the redacted summary</button>"
        "<p class='muted'>Nothing is sent. The file holds counts, labels and versions only: no "
        "claim text, quotes, notes, names, record references or ids. Read it before you share "
        "it.</p></form>"
    )


def _groups(st: ClaimState) -> list[tuple[str, list[EvidenceItem]]]:
    groups: dict[str, list[EvidenceItem]] = {
        CONTRADICTION_FOUND: [],
        "AI-accepted, awaiting your decision": [],
        "Supporting, not reviewed": [],
        "Contradicting or complicating": [],
        "Dismissed by the AI reviewer, not reviewed by you": [],
        "Evidence the expert already decided": [],
    }
    for x in st.evidence:
        if x.stance == Stance.IRRELEVANT:
            continue
        by_expert = st.last_reviewer.get(x.id) == "expert" and x.status != EvidenceStatus.OPEN
        if by_expert:
            groups["Evidence the expert already decided"].append(x)
        elif st.contradiction_found and st.to_confirm(x):
            groups[CONTRADICTION_FOUND].append(x)
        elif x.stance in AGAINST:
            groups["Contradicting or complicating"].append(x)
        elif x.status == EvidenceStatus.AI_ACCEPTED:
            groups["AI-accepted, awaiting your decision"].append(x)
        elif x.status == EvidenceStatus.DISMISSED:
            groups["Dismissed by the AI reviewer, not reviewed by you"].append(x)
        else:
            groups["Supporting, not reviewed"].append(x)
    return [(k, v) for k, v in groups.items() if v]


def _selection_note(conn: sqlite3.Connection, st: ClaimState) -> str:
    """What the selection audit found around the quotes of the claim's paragraph, and what a
    larger source of the same phone holds near the claim's records that a curated report does
    not, if anything."""
    audit = selection_audit(conn, paragraph_id=st.claim.paragraph_id)
    # The Selection tab lists the claims that are not removed, so a removed claim has no list
    # to link to.
    paired = (
        ""
        if st.claim.status.value == "removed"
        else claim_line(
            paired_check(conn, [st], audit),
            st.claim.id,
            "/selection",
        )
    )
    units = audit.of("document")
    if not units:
        return paired
    note = claim_note(units[0], f"/selection#{selection_anchor(units[0].id)}", audit.same)
    return (note or "") + paired


def claim_page(conn: sqlite3.Connection, page: Page, claim_id: str) -> str | None:
    st = claim_state(conn, claim_id)
    if st is None:
        return None
    back = link("/claim", id=claim_id)
    c, d = st.claim, st.decision
    out = [
        "<div class='claim-head'>"
        f"<h1>{e(st.name)} <span class='muted'>· {e(st.where)} · "
        f"{e(c.claim_type.value.replace('_', ' '))} · wording {e(c.status.value)}"
        f"{' by the expert' if c.model_run_id is None else ' (model-proposed)'}</span></h1>"
        + (f"<span class='mono muted'>Claim id {e(c.id)}</span>" if st.name != c.id else "")
        + "</div>",
        f"<blockquote class='claimtext'>{q(c.text)}</blockquote>",
    ]
    if st.paragraph_text:
        out.append(
            f"<details><summary>Paragraph as printed ({e(st.where)})</summary>"
            f"<blockquote>{q(st.paragraph_text)}</blockquote></details>"
        )
        out.append(_selection_note(conn, st))
    out.append(
        "<div class='card' id='verdict'><div class='in'><div class='eyebrow'>Verdict</div>"
        f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span>"
    )
    needs = st.needs()
    if needs:
        out.append("<ul>" + "".join(f"<li>{e(t)}</li>" for _, t in needs) + "</ul>")
    out.append(_gap_lines(st))  # the same lines as the overview and the report
    out.append(claim_format_notices(conn, st))  # the same notices as the report's claim
    out.append(forwarded_warning(conn, st))
    out.append(mixed_app_note(conn, st))
    if d is not None:
        out.append(
            "<details><summary>Why (reasons from the verdict rules)</summary><ul>"
            + "".join(f"<li>{e(r)}</li>" for r in d.reasons)
            + f"</ul><p class='muted'>Rule version {e(d.rule_version)}, run "
            f"{e(d.pipeline_run_id)}.</p></details>"
        )
        if d.confirmed_by:
            note = f" Note: {said(d.override_note)}" if d.override_note else ""
            kind = "overrode" if d.override_note is not None else "confirmed"
            out.append(f"<p>{e(d.confirmed_by)} {kind} this verdict.{note}</p>")
        out.append(
            f"</div><div class='in'>{_verdict_forms(page, st, back)}"
            f"{_flag_verdict_form(conn, page, st, back)}"
        )
    out.append("</div></div>")
    out.append(_must_be_true(conn, st, testability.used_repairs(conn, pipeline.view_run(conn))))
    out.append(_alternatives(conn, st))
    if st.agent_fails:
        proposed = testability.proposals(conn, pipeline.view_run(conn)).get(c.id)
        out.append(_agent_fail_card(page, conn, st, proposed, back))

    out.append("<h2 id='evidence'>Evidence</h2>")
    claim_flags = F.active_flags(conn, c.id)
    flagged = {f.evidence_id for f in claim_flags if f.evidence_id}
    d0 = st.decision
    if st.unlabeled and d0 is not None and d0.verdict is Verdict.CONTRADICTED and not st.stale:
        # The run's own note (pipeline.unlabeled_reason) stays in the report; here, plainly,
        # and only while the verdict the rules gave is the contradiction that note leads to.
        out.append(
            "<p class='muted'>A check on the phone records failed on a core part of this claim, "
            "so the verdict rules contradict it whatever the evidence says. The records that "
            "check cites are the evidence; the model was not asked to label any.</p>"
        )
    elif st.unlabeled:
        out.append(f"<p class='muted'>{e(st.unlabeled)}</p>")
    if st.untested:
        out.append(f"<p><strong>{e(st.not_tested or '')}</strong></p>")
        if "matches no person" in (st.not_tested or ""):
            out.append(
                "<p>A name in this claim is not a person in the case yet. Add it on "
                "<a href='/identities'>Identities</a> and decide who is behind it; the next "
                "audit run can then test the claim.</p>"
            )
        out.append(_holdings(conn))
        out.append(
            _agent_card(
                page, conn, testability.proposals(conn, pipeline.view_run(conn)).get(c.id), back
            )
        )
    groups = _groups(st)
    if not groups:
        out.append("<p class='muted'>No relevant evidence items were stored for this claim.</p>")
    by_assumption = {a.id: a for a in st.assumptions}
    found = forwarded.affected(conn)
    threads: dict[str, list[str]] = {}  # each thread read once for the page's cards
    challenged = challenge.found_items(conn, pipeline.view_run(conn))
    for title, group in groups:
        out.append(f"<h3>{e(title)} ({len(group)})</h3>")
        shown_on = None
        order = {a.id: i for i, a in enumerate(st.assumptions)}
        for x in sorted(group, key=lambda x: order.get(x.assumption_id, len(order))):
            a = by_assumption.get(x.assumption_id)
            if a is not None and a.id != shown_on:
                out.append(f"<p class='muted'>Assumption: {plain_ids(conn, a.text)}</p>")
                shown_on = a.id
            out.append(
                evidence_card(
                    conn,
                    page,
                    x,
                    st.last_reviewer.get(x.id),
                    back,
                    found,
                    claim_id=c.id,
                    flagged=x.id in flagged,
                    run_id=st.run_id,
                    confirm=title == CONTRADICTION_FOUND,
                    around=AROUND,
                    threads=threads,
                    challenged=challenged,
                )
            )
    hidden = [x for x in st.evidence if x.stance == Stance.IRRELEVANT]
    if hidden:
        out.append(_irrelevant_list(conn, hidden, flagged, {w.evidence_id for w in st.withheld}))
    out.append(_working(st))
    if d is not None:  # a flag is about an audited claim
        out.append(_flag_missed_form(page, st, back))
    out.append(_flags_section(page, claim_flags, back, st.run_id))

    out.append(_edit_claim_form(page, st, back))
    states = claim_states(conn)
    side = (
        f"<aside class='side'><div class='eyebrow'>Claims ledger <span>{len(states)} claims"
        f"</span></div>{_tally(states)}{_ledger(states, c.id, compact=True)}</aside>"
    )
    body = f"<div class='split'>{side}<div>{''.join(out)}</div></div>"
    return page.wrap(st.name, body, run_banner(conn, page, back), wide=True)


AROUND = 1  # messages either side of each evidence record on the claim page


AGENT_CHECKED = (
    "Code checked this answer before showing it to you, with no model: every value is written "
    "in the claim or its paragraph, and each name, phone and account resolves to exactly one in "
    "the case (the assumption filler's own checks); every person, phone and account is one the "
    "claim's own words name, not only its paragraph; apps, quoted words and time ranges are read "
    "from the claim's text. It did not decide whether the claim is true."
)


def _agent_card(
    page: Page, conn: sqlite3.Connection, x: testability.Proposed | None, back: str
) -> str:
    """The testability step's proposal for a claim the filler left untested, for the examiner
    to accept or reject. Nothing in it is used until accepted, and then only from the next
    audit on. One card per claim; there is no accept-all."""
    if x is None:
        return ""
    rows = "".join(f"<li>{plain_ids(conn, str(a.get('text', '')))}</li>" for a in x.assumptions)
    found = "".join(
        f"<li>&ldquo;{e(str(f.get('written', '')))}&rdquo;: {e(str(f.get('means', '')))}</li>"
        for f in x.lookups
    )
    sheet = (
        " The case's signed assumption sheet names the same people, phones and time ranges."
        if x.check == testability.SHEET_CHECK
        else ""
    )
    fields = (
        f"<input type='hidden' name='claim' value='{e(x.claim_id)}'>"
        f"<input type='hidden' name='run' value='{e(x.run_id)}'>"
        f"<input type='hidden' name='attempt' value='{x.attempt}'>"
        "<input type='text' class='wide' name='reason' required maxlength='500' "
        "placeholder='Why, in one sentence (recorded in the audit log)'><br>"
    )
    accept = (
        "<button type='submit' name='decision' value='accept'>Accept these assumptions</button>"
    )
    reject = "<button type='submit' name='decision' value='reject'>Reject</button>"
    if x.decided is None:
        state = (
            "<p><strong>Waiting for you.</strong> Nothing here is used until you accept it. "
            "Accepting puts these assumptions in the case from the next audit on, if the agent "
            "gives them again for this claim's text. The claim's text never changes.</p>"
        )
        form = page.form("/testability/decide", fields + accept + reject, back=back, anchor="agent")
    else:
        action, actor = x.decided
        who = e(actor.removeprefix("expert:"))
        if action == testability.ACCEPT_ACTION:
            state = (
                f"<p><strong>Accepted by {who}.</strong> The next audit tests the claim with "
                "these assumptions, if the agent gives them again for this claim's text.</p>"
            )
            other = reject
        else:
            state = f"<p><strong>Rejected by {who}.</strong> No audit uses them.</p>"
            other = accept
        form = (
            "<details><summary>Change this decision</summary>"
            + page.form("/testability/decide", fields + other, back=back, anchor="agent")
            + "</details>"
        )
    return (
        "<section class='agent' id='agent'>"
        f"<h2><span class='badge b-agent'>{e(testability.PROPOSED_MARK)}</span> Assumptions that "
        "would make this claim testable</h2>"
        "<p class='muted'>The testability step asked the local model again, with the reasons "
        "code refused the first try. It only proposes.</p>"
        f"<ul class='proposed'>{rows}</ul>"
        f"<details class='more'><summary>What code checked</summary><p>{e(AGENT_CHECKED)}{sheet}"
        "</p><p>What the claim and its paragraph name in the case, by code's lookups (the "
        "agent was shown these; only those in the claim's own words count):</p>"
        f"<ul>{found or '<li>nothing</li>'}</ul></details>{state}{form}</section>"
    )


def _agent_fail_card(
    page: Page,
    conn: sqlite3.Connection,
    st: ClaimState,
    x: testability.Proposed | None,
    back: str,
) -> str:
    """Rules 0.4.0: each failed check on an assumption the testability agent proposed and an
    examiner accepted, waiting for the expert. A confirmed failure counts (the verdicts re-run at
    once), or the expert rejects the proposal and the next audit does not use it. One form per
    failure; there is no confirm-all."""
    texts = {a.id: a.text for a in st.assumptions}
    reason = (
        "<input type='text' class='wide' name='reason' required maxlength='500' "
        "placeholder='Why, in one sentence (recorded in the audit log)'><br>"
    )
    rows = []
    for c in st.agent_fails:
        fields = (
            f"<input type='hidden' name='claim' value='{e(st.claim.id)}'>"
            f"<input type='hidden' name='check' value='{e(c.id)}'>"
            # the failure as shown, with its claim text and proposal: a later audit's other
            # failure, or the same failure after a claim edit, is not confirmed with it
            f"<input type='hidden' name='seen' value='{st.agent_seen[c.id]}'>{reason}"
        )
        rows.append(
            f"<li><div><strong>{plain_ids(conn, texts.get(c.assumption_id, c.assumption_id))}"
            f"</strong></div><div class='muted'>Check {e(c.check_name)} failed: "
            f"{plain_ids(conn, c.detail)}</div>"
            f"<div class='muted'>Searched: {plain_ids(conn, c.searched)}</div>"
            + page.form(
                "/testability/confirm",
                fields + "<button type='submit'>Confirm this failure</button>",
                back=back,
                anchor="agent-fail",
            )
            + "</li>"
        )
    reject = ""
    if x is not None:
        fields = (
            f"<input type='hidden' name='claim' value='{e(x.claim_id)}'>"
            f"<input type='hidden' name='run' value='{e(x.run_id)}'>"
            f"<input type='hidden' name='attempt' value='{x.attempt}'>{reason}"
        )
        reject = (
            "<details><summary>Or reject the agent's proposal</summary>"
            + page.form(
                "/testability/decide",
                fields + "<button type='submit' name='decision' value='reject'>Reject</button>",
                back=back,
                anchor="agent-fail",
            )
            + "</details>"
        )
    return (
        "<section class='agent' id='agent-fail'>"
        f"<h2><span class='badge b-agent'>{e(testability.PROPOSED_MARK)}</span> "
        f"{e(CONTRADICTION_FOUND)}</h2>"
        f"<p>{e(agent_fail_step(len(st.agent_fails)))}</p>"
        f"<ul class='proposed'>{''.join(rows)}</ul>{reject}</section>"
    )


def _must_be_true(
    conn: sqlite3.Connection,
    st: ClaimState,
    repaired: dict[str, testability.Used] | None = None,
) -> str:
    """What has to be true for the claim, one line per assumption, core ones first, with what the
    verdict rules found. Read from the stored coverage; it decides nothing. `repaired`: the
    assumptions the shown audit took from the testability step under an examiner's acceptance
    (testability.used_repairs, as the report reads it)."""
    repaired = repaired or {}
    if not st.assumptions:
        return ""
    d = st.decision
    coverage = {cv.assumption_id: cv for cv in (d.coverage if d else ())}
    current = d is not None and not st.stale
    # a failed check marks its assumption contradicted only when the verdict cites it, so the
    # mark follows what the rules decided (a check the rules leave to the expert is not cited)
    cited = set(d.cited_check_ids) if d is not None else set()
    failed = {
        r.assumption_id for r in st.checks if r.outcome is CheckOutcome.FAIL and r.id in cited
    }
    # rules 0.4.0: a failed check on an agent's assumption counts only once an expert confirms it
    awaiting = {c.assumption_id for c in st.agent_fails}
    rows = []
    for a in sorted(st.assumptions, key=lambda a: not a.is_core):
        cv = coverage.get(a.id) if current else None
        if cv is None:
            mark, said_ = "na", "Not current" if d is not None and st.stale else "Not computed"
        elif cv.covered:
            tier = cv.tier.value if cv.tier else "?"
            mark, said_ = "ok", f"Records found ({tier.replace('_', ' ')})"
        elif a.id in failed:
            mark, said_ = "con", "Contradicted by the records"
        elif a.id in awaiting:
            mark, said_ = "no", "A check failed: waiting for you to confirm"
        else:
            mark, said_ = "no", "Not established"
        role = "core" if a.is_core else "context, not needed for the verdict"
        if a.id in repaired:
            role += f" · {repaired[a.id].mark()}"
        rows.append(
            f"<li class='{mark}'><span class='mark'></span>"
            f"<div><div>{plain_ids(conn, a.text)}</div>"
            f"<div class='meta'>{e(GAP_TOPICS[a.kind])} · {e(role)}</div></div>"
            f"<span class='said'>{e(said_)}</span></li>"
        )
    return (
        "<section class='truths'><h2>What has to be true</h2>"
        "<p class='muted'>Each part of the claim the records would have to show, and what the "
        f"verdict rules found.</p><ul class='checklist'>{''.join(rows)}</ul></section>"
    )


def _working(st: ClaimState) -> str:
    """The rules' working: the assumption and check tables, folded."""
    d = st.decision
    out: list[str] = []
    coverage = {cv.assumption_id: cv for cv in (d.coverage if d else ())}
    if st.assumptions:
        out.append(
            "<h3>Assumptions</h3><table><thead><tr><th>Assumption</th><th>Kind</th><th>Core</th>"
            "<th>Covered (computed by the rules)</th></tr></thead>"
        )
        for a in st.assumptions:
            cv = coverage.get(a.id)
            cov = (
                "not computed"
                if cv is None
                else f"yes, at {cv.tier.value if cv.tier else '?'}"
                if cv.covered
                else "no"
            )
            out.append(
                f"<tr><td>{e(a.text)}</td><td>{e(a.kind.value)}</td>"
                f"<td>{'yes' if a.is_core else 'no'}</td><td>{e(cov)}</td></tr>"
            )
        out.append("</table>")
    if st.checks:
        out.append(
            "<h3>Checks</h3><table><thead><tr><th>Check</th><th>Outcome</th>"
            "<th>What was searched</th><th>Detail</th></tr></thead>"
        )
        for ch in st.checks:
            out.append(
                f"<tr><td>{e(ch.check_name)} {e(ch.check_version)}</td>"
                f"<td>{e(ch.outcome.value)}</td><td>{e(ch.searched)}</td><td>{e(ch.detail)}</td>"
                "</tr>"
            )
        out.append("</table>")

    if not out:
        return ""
    return (
        "<details class='working'><summary>Show the rules' working: assumptions, checks and "
        "what was searched"
        f"</summary>{''.join(out)}</details>"
    )


def _context_link(f: explain.Fit) -> str | None:
    return link("/selection/context", id=f.record_id) if f.record_id.startswith("msg:") else None


def _alternatives(conn: sqlite3.Connection, st: ClaimState) -> str:
    """Other explanations the records raise (core/hypotheses/); never part of the verdict."""
    if st.incomplete or not st.assumptions:
        return ""
    if st.edited_after_run:
        return (
            "<p class='muted'>Other explanations are worked out from the audited claim. The claim "
            "text changed after this audit, so they show again after a re-run.</p>"
        )
    alts = explain.alternatives(explain.load(conn), st.assumptions)
    if not alts:
        return ""
    return (
        f"<h2 id='alternatives'>Other explanations to check ({len(alts)})</h2>"
        + alternatives_html(alts, _context_link)
    )


def _verdict_forms(page: Page, st: ClaimState, back: str) -> str:
    cid = e(st.claim.id)
    options = "".join(f"<option value='{v.value}'>{v.value}</option>" for v in Verdict)
    return (
        "<details><summary>Confirm or override the verdict</summary>"
        + page.form(
            "/verdict",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<input type='hidden' name='action' value='confirm'>"
            "<input type='text' class='wide' name='note' maxlength='500' "
            "placeholder='Note (optional)'><br><button type='submit'>Confirm this verdict</button>",
            back=back,
            anchor="verdict",
        )
        + page.form(
            "/verdict",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<input type='hidden' name='action' value='override'>"
            f"Your own verdict: <select name='verdict'>{options}</select> "
            "<input type='text' class='wide' name='note' required maxlength='1000' "
            "placeholder='Why (required; the report prints it as an expert override)'><br>"
            "<button type='submit'>Override the verdict</button>",
            back=back,
            anchor="verdict",
        )
        + "<p class='muted'>A confirmation or override applies to this run's verdict. After "
        "re-running the verdicts, confirm again.</p></details>"
    )


def _holdings(conn: sqlite3.Connection) -> str:
    held = case_holdings(conn)
    items = "".join(f"<li>{e(h)}</li>" for h in held) or "<li>No extraction imported.</li>"
    return f"<p>{e(HOLDINGS)}</p><ul>{items}</ul>"


def _edit_claim_form(page: Page, st: ClaimState, back: str) -> str:
    cid = e(st.claim.id)
    return (
        "<h2 id='edit'>Edit this claim</h2>"
        + page.form(
            "/claim/edit",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<input type='hidden' name='status' value='edited'>"
            f"<textarea name='text' rows='3' required>{e(st.claim.text)}</textarea><br>"
            "<button type='submit'>Save new wording</button> <span class='muted'>A changed "
            "claim needs a full audit.</span>",
            back=back,
            anchor="edit",
        )
        + page.form(
            "/claim/edit",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<button type='submit' name='status' value='accepted'>Accept as written</button>"
            "<button type='submit' name='status' value='removed'>Remove this claim</button>",
            back=back,
            anchor="edit",
        )
    )


# ---------------------------------------------------------------- one evidence item


def evidence_page(conn: sqlite3.Connection, page: Page, evidence_id: str) -> str | None:
    items = pipeline.load_evidence(conn, [evidence_id])
    if not items:
        return None
    item = items[0]
    claim_id = conn.execute(
        "SELECT a.claim_id, a.text FROM assumptions a WHERE a.id = ?", (item.assumption_id,)
    ).fetchone()
    back = link("/evidence", id=evidence_id)
    history = list(
        conn.execute(
            "SELECT seq, reviewer_kind, reviewer, status, reason, decided_at_utc"
            " FROM evidence_reviews"
            " WHERE evidence_id = ? ORDER BY seq",
            (evidence_id,),
        )
    )
    last_kind = conn.execute(
        "SELECT reviewer_kind FROM evidence_reviews WHERE evidence_id = ? ORDER BY seq DESC"
        " LIMIT 1",
        (evidence_id,),
    ).fetchone()
    out = ["<h1>Evidence item</h1>"]
    if claim_id:
        out.append(
            f"<p>Claim <a href='{e(link('/claim', id=claim_id[0]))}'>{e(claim_id[0])}</a>. "
            f"Assumption: {e(claim_id[1])}</p>"
        )
    flagged = any(f.evidence_id == item.id for f in F.active_flags(conn))
    # Flag only an item in the audit on screen; one an older run dropped is not counted.
    st = claim_state(conn, claim_id[0]) if claim_id else None
    on_screen = (
        st is not None and st.decision is not None and item.id in {x.id for x in st.evidence}
    )
    out.append(
        evidence_card(
            conn,
            page,
            item,
            last_kind[0] if last_kind else None,
            back,
            claim_id=claim_id[0] if on_screen else None,
            flagged=flagged,
            run_id=st.run_id if on_screen else None,
            challenged=(
                challenge.found_items(conn, pipeline.view_run(conn)) if on_screen else frozenset()
            ),
        )
    )
    out.append("<h2>Context</h2>")
    lines = build_context(conn, item.record_id, CONTEXT_WINDOW)
    if lines:
        out.append(
            "<p class='muted'>Messages around the record, in time order. Times are the phone's "
            "local time. The record under review is highlighted.</p><div class='thread'>"
        )
        out.extend(_msg(ln) for ln in lines)
        out.append("</div>")
    else:
        out.append("<p class='muted'>No surrounding messages for this kind of record.</p>")
    out.append("<h2>Review history</h2>")
    if history:
        out.append(
            "<table><thead><tr><th>#</th><th>Reviewer</th><th>Status</th><th>Reason</th>"
            "<th>When (UTC)</th></tr></thead>"
            + "".join(
                f"<tr><td>{s}</td><td>{e(who)}</td><td>{e(status)}</td>"
                f"<td>{said(reason) if kind == 'expert' else e(reason)}</td>"
                f"<td class='when'>{e(at)}</td></tr>"
                for s, kind, who, status, reason, at in history
            )
            + "</table>"
        )
    else:
        out.append("<p class='muted'>Not reviewed yet.</p>")
    return page.wrap("Evidence", "".join(out), run_banner(conn, page, back))


# ---------------------------------------------------------------- add a claim


def new_claim_page(conn: sqlite3.Connection, page: Page) -> str:
    paras = list(
        conn.execute(
            "SELECT p.id, p.page, p.para_no, p.label, p.text, g.title FROM govdoc_paragraphs p"
            " JOIN govdocs g ON g.id = p.govdoc_id ORDER BY g.id, p.para_no"
        )
    )
    ids = [c.id for c in pipeline.load_claims(conn, include_removed=True)]
    n = 1
    while f"C{n:02d}" in ids:
        n += 1
    opts = "".join(
        f"<option value='{e(pid)}'>{e(title[:40])}: page {pg}, paragraph "
        f"{e(label or '#' + str(no))}: {e(text[:70])}</option>"
        for pid, pg, no, label, text, title in paras
    )
    types = "".join(f"<option value='{t.value}'>{t.value}</option>" for t in ClaimType)
    body = "<h1>Add a claim</h1>"
    if not paras:
        body += "<p>Import the government document first.</p>"
    else:
        body += page.form(
            "/claim/add",
            "<p><label>Claim id <input type='text' name='id' required maxlength='20' "
            f"value='C{n:02d}'></label>"
            f" <label>Type <select name='type'>{types}</select></label></p>"
            f"<p><label>Paragraph <select name='paragraph'>{opts}</select></label></p>"
            "<p><label>Claim text, as the document states it "
            "<textarea name='text' rows='4' required></textarea></label></p>"
            "<button type='submit' class='primary'>Add claim</button> <span class='muted'>A new "
            "claim needs a "
            "full audit before it has a verdict.</span>",
        )
    return page.wrap("Add a claim", body)


# ---------------------------------------------------------------- audit log


def log_page(conn: sqlite3.Connection, page: Page, show_all: bool, show_views: bool = False) -> str:
    """The audit log, newest first. Page views (action `view`) are left out unless asked for;
    the Activity page shows them with the expert's actions."""
    summary = audit_log_summary(conn)
    views = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?", (VIEW,)).fetchone()[0]
    rows: Iterable[tuple] = conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json, hash FROM audit_log"
        " WHERE ? OR action != ? ORDER BY seq DESC LIMIT ?",
        (show_views, VIEW, -1 if show_all else 200),
    )
    status = (
        "<div class='flash'>Hash chain verified: every entry matches the hash of the one before."
        "</div>"
        if summary["chain_ok"]
        else "<div class='flash err'><strong>Hash chain FAILED VERIFICATION.</strong> The log "
        "was changed outside Mabillon.</div>"
    )
    params = {"all": "1"} if show_all else {}
    if show_views:
        views_line = (
            f"Page views shown ({views}). "
            f"<a href='{e(link('/log', **params))}'>Hide page views</a>. "
        )
    else:
        views_line = (
            f"{views} page views not shown: "
            f"<a href='{e(link('/log', **params, views='1'))}'>show them here</a>, or see "
            "<a href='/activity'>Activity</a>. "
            if views
            else ""
        )
    more = {"views": "1"} if show_views else {}
    out = [
        "<h1>Audit log</h1>",
        status,
        f"<p>{summary['entries']} entries. Last hash <span class='mono'>"
        f"{e(summary['last_hash'])}</span>. "
        + views_line
        + (
            ""
            if show_all
            else f"Newest 200 shown. <a href='{e(link('/log', all='1', **more))}'>Show all</a>."
        )
        + "</p>",
        "<table><thead><tr><th>#</th><th>When (UTC)</th><th>Actor</th><th>Action</th>"
        "<th>Details</th></tr></thead>",
    ]
    for seq, at, actor, action, payload, _h in rows:
        out.append(
            f"<tr><td>{seq}</td><td class='when'>{e(at)}</td><td>{e(actor)}</td>"
            f"<td>{e(action)}</td>"
            f"<td class='mono'>{q(_short(payload))}</td></tr>"
        )
    out.append("</table>")
    return page.wrap("Audit log", "".join(out))


# ---------------------------------------------------------------- activity

ACTIVITY_NEWEST = 500


def _step_item(s: activity.Step) -> str:
    p = s.payload
    if not s.is_view:
        return e(s.evidence_id or s.claim_id or "")
    bits = []
    ident = p.get("id")
    # ids, locators and query values come from the address or the case, not Mabillon's own words,
    # so they are shown as cited text (q), which the forbidden-word check leaves alone
    if p.get("page") == "/claim" and ident:
        bits.append(f"<a href='{e(link('/claim', id=str(ident)))}'>{q(str(ident))}</a>")
    elif p.get("page") == "/evidence" and ident:
        bits.append(f"<a href='{e(link('/evidence', id=str(ident)))}'>{q(str(ident))}</a>")
        if p.get("record_id"):
            bits.append(
                f"record {q(str(p['record_id']))} at {q(str(p.get('source_id', '')))} "
                f"{q(str(p.get('locator', '')))}"
            )
    elif ident:
        bits.append(q(str(ident)))
    listed = len(p.get("listed", [])) + int(p.get("listed_left_out", 0) or 0)
    if listed:
        bits.append(f"listed {listed} evidence item{'s' if listed != 1 else ''}")
    for k, v in (p.get("query") or {}).items():
        bits.append(f"{e(k)}={q(str(v))}")
    return "; ".join(bits)


def _report_switch(conn: sqlite3.Connection, page: Page) -> str:
    """The per-case switch for the report's Examiner activity table (off by default)."""
    on = activity.in_report(conn)
    state = (
        "<strong>In the report: included.</strong> The report shows this case's activity per "
        "claim, with time on its pages."
        if on
        else "<strong>In the report: left out</strong> (the default). The report says it is "
        "not included; the audit log keeps every page view."
    )
    return page.form(
        "/activity/report",
        f"<p>{state} The choice is yours for this case, and the audit log records each change "
        "with your name.</p>"
        f"<input type='hidden' name='include' value='{'0' if on else '1'}'>"
        "<button type='submit'>"
        + ("Leave activity out of the report" if on else "Include activity in the report")
        + "</button>",
        back="/activity",
    )


def activity_page(conn: sqlite3.Connection, page: Page, claim: str, show_all: bool) -> str:
    """The examiner's activity trail: page views and logged actions, per claim and in order."""
    trail = activity.steps(conn)
    total = activity.summary(trail)
    per = activity.by_claim(trail)
    claims = [
        cid
        for (cid,) in conn.execute("SELECT id FROM claims WHERE status != 'removed' ORDER BY id")
    ]
    idle = int(activity.IDLE.total_seconds() // 60)
    out = [
        "<h1>Activity</h1>",
        "<p>Every page opened in this case is recorded in its audit log, with the time, the "
        "examiner's name, the page and the evidence it listed, beside the examiner's decisions. "
        "The hash chain covers these entries like every other. Nothing here leaves this "
        "computer.</p>",
        "<p class='muted'>Time on page runs from opening a page to the next page opened. "
        "The screen runs no scripts, so Mabillon cannot tell what was on screen or read; a "
        f"stretch over {idle} minutes may include time away, and a page whose end was not "
        "recorded (the screen closed, or the next step came from elsewhere) is not timed; both "
        "are counted apart from totals. "
        "\u201cListed\u201d means the page linked to the item, not that it was opened.</p>",
        "<p><a href='/activity.csv'>Download the trail (CSV)</a></p>",
        _report_switch(conn, page),
    ]
    if total["views"]:
        out.append(
            f"<p>{total['views']} page views in {total['sessions']} screen session"
            f"{'s' if total['sessions'] != 1 else ''}, by {e(', '.join(total['examiners']))}, "
            f"from {e(total['first_at'])} to {e(total['last_at'])} (UTC).</p>"
        )
    else:
        out.append("<p>No page views are recorded for this case yet.</p>")
    out.append(
        "<h2>By claim</h2><table><thead><tr><th>Claim</th><th>Times opened</th>"
        "<th>First opened (UTC)</th><th>Last opened (UTC)</th><th>Time on its pages</th>"
        "<th>Evidence items opened</th><th>Evidence items listed</th><th>Actions</th>"
        "</tr></thead>"
    )
    for cid in claims:
        a = per.get(cid)
        if a is None or not (a.opened or a.evidence_opened):
            out.append(
                f"<tr><td><a href='{e(link('/activity', claim=cid))}'>{e(cid)}</a></td>"
                "<td>0</td><td colspan='5' class='muted'>not opened</td>"
                f"<td>{a.actions if a else 0}</td></tr>"
            )
            continue
        out.append(
            f"<tr><td><a href='{e(link('/activity', claim=cid))}'>{e(cid)}</a></td>"
            f"<td>{a.opened}</td><td>{e(a.first_at or '')}</td><td>{e(a.last_at or '')}</td>"
            f"<td>{e(activity.time_on_pages(a))}</td>"
            f"<td>{len(a.evidence_opened)}</td><td>{e(activity.listed_count(a))}</td>"
            f"<td>{a.actions}</td></tr>"
        )
    out.append("</table>")
    shown = [s for s in trail if not claim or s.claim_id == claim]
    cut = 0 if show_all else max(0, len(shown) - ACTIVITY_NEWEST)
    known = claim in claims  # an id typed into the address is shown as cited text, never linked
    head = f"Trail for claim {e(claim) if known else q(claim)}" if claim else "Trail"
    out.append(f"<h2>{head}</h2>")
    if claim:
        out.append("<p><a href='/activity'>Show every claim</a>. ")
        if known:
            out.append(f"<a href='{e(link('/claim', id=claim))}'>Open claim {e(claim)}</a>.")
        else:
            out.append("There is no such claim in this case.")
        out.append("</p>")
    if cut:
        more = {"claim": claim} if known else {}
        out.append(
            f"<p>Newest {ACTIVITY_NEWEST} of {len(shown)} shown. "
            f"<a href='{e(link('/activity', all='1', **more))}'>Show all</a>.</p>"
        )
    out.append(
        "<table><thead><tr><th>#</th><th>When (UTC)</th><th>Examiner</th><th>Page or action"
        "</th><th>Item</th><th>Time on page</th></tr></thead>"
    )
    for s in shown[cut:]:
        when = activity.duration(s.seconds, s.away) if s.is_view else ""
        out.append(
            f"<tr><td>{s.seq}</td><td class='when'>{e(s.at_utc)}</td><td>{e(s.examiner)}</td>"
            f"<td>{e(s.where)}</td><td>{_step_item(s)}</td><td>{e(when)}</td></tr>"
        )
    out.append("</table>")
    return page.wrap("Activity", "".join(out), wide=True)


def _short(payload_json: str, limit: int = 400) -> str:
    try:
        p = json.loads(payload_json)
    except ValueError:
        return payload_json[:limit]
    if isinstance(p, dict) and "manifest" in p:
        p = {**p, "manifest": f"{len(p['manifest'])} claims"}
    text = json.dumps(p, ensure_ascii=False)
    return text if len(text) <= limit else text[:limit] + " ..."


def error_page(page: Page, status: int, message: str) -> str:
    return page.wrap("Error", f"<h1>{status}</h1><p>{e(message)}</p><p><a href='/'>Case</a></p>")


# ---------------------------------------------------------------- cases


PASSPHRASE_HINT = (
    "At least 12 characters; a few words is easiest. Mabillon cannot recover a lost passphrase: "
    "keep it, or the recovery key Mabillon shows next, somewhere safe."
)
LOCK_LABEL = {"plain": "Not encrypted", "locked": "Encrypted, locked", "open": "Encrypted"}


def _unlock_fields(slug: str) -> str:
    return (
        f"<input type='hidden' name='case' value='{e(slug)}'>"
        "<input type='password' name='passphrase' required size='30' "
        "autocomplete='current-password' placeholder='Passphrase or recovery key' "
        "aria-label='Passphrase or recovery key'> "
        "<button type='submit'>Unlock and open</button>"
    )


def cases_page(
    page: Page,
    home: object,
    rows: list[tuple[str, str, str, str]],
    single: str | None,
    single_locked: bool = False,
    single_blocked: str | None = None,
) -> str:
    """rows: (folder name, case name, one-line state, lock state: plain | locked | open).
    single: the database path when the screen was started on one case database (`--db`),
    which has no cases folder; single_locked when that database is encrypted and locked;
    single_blocked: why that database cannot be opened for review (a broken audit log)."""
    out = ["<h1>Cases</h1>"]
    if single is not None:
        out.append(
            f"<p>This screen was started on one case database: <span class='mono'>{e(single)}"
            "</span>. Start <span class='mono'>mabillon serve</span> without "
            "<span class='mono'>--db</span> to make and open cases in a cases folder.</p>"
        )
        if single_locked:
            out.append(name_form(page))
            out.append(
                "<p>This case is encrypted and locked.</p>"
                + page.form("/case/open", _unlock_fields(""))
            )
        if single_blocked:
            out.append(
                f"<div class='flash err'><strong>Review blocked.</strong> {e(single_blocked)}</div>"
            )
        return page.wrap("Cases", "".join(out))
    out.append(name_form(page))
    out.append(
        f"<p>Cases folder: <span class='mono'>{e(home)}</span>. Each case is a folder with its "
        "own database and read-only copies of its files.</p>"
    )
    if rows:
        out.append(
            "<table><thead><tr><th>Case</th><th>State</th><th>Encryption</th><th></th></tr></thead>"
        )
        for slug, name, state, lock in rows:
            fields = (
                _unlock_fields(slug)
                if lock == "locked"
                else f"<input type='hidden' name='case' value='{e(slug)}'>"
                "<button type='submit'>Open</button>"
            )
            out.append(
                f"<tr><td>{q(name)}<br><span class='mono'>{e(slug)}</span></td><td>{e(state)}</td>"
                f"<td>{e(LOCK_LABEL.get(lock, lock))}</td><td>"
                + page.form("/case/open", fields, "inline")
                + "</td></tr>"
            )
        out.append("</table>")
    else:
        out.append("<p class='muted'>No cases yet.</p>")
    out.append(
        "<h2>New case</h2>"
        + page.form(
            "/case/new",
            "<p><label>Case name <input type='text' name='name' required maxlength='80' "
            "class='wide' placeholder='For example: United States v. Petrov (synthetic)'>"
            "</label></p>"
            "<p><label><input type='checkbox' name='encrypt' value='1' checked> Encrypt this case "
            "with a passphrase (recommended)</label></p>"
            "<input type='password' name='passphrase' autocomplete='new-password' minlength='12' "
            "placeholder='Passphrase' aria-label='Passphrase'> "
            "<input type='password' name='passphrase2' autocomplete='new-password' "
            "placeholder='The passphrase again' aria-label='The passphrase again'>"
            f"<p class='muted'>{e(PASSPHRASE_HINT)} The case name stays readable in this list."
            "</p>"
            "<button type='submit' class='primary'>Make the case</button>",
        )
    )
    return page.wrap("Cases", "".join(out))


def name_form(page: Page) -> str:
    if page.expert:
        return ""
    return page.form(
        "/expert",
        "<p><strong>Who is working on this case?</strong> Your name is recorded with every "
        "decision in the audit log.</p><input type='text' name='name' required "
        "maxlength='60' placeholder='Your name'> <button type='submit'>Continue</button>",
    )


# ---------------------------------------------------------------- set up and run

FIDELITY = {
    "curated_report": "curated report (examiner-selected; cannot show absence)",
    "full_extraction": "full extraction",
    "unknown": "not known (cannot show absence)",
}


def _import_coverage(conn: sqlite3.Connection, source_id: str) -> str:
    """What the import read and what it did not (core/ingest/coverage.py): the headline, then
    the items to review. Text from the report goes through q()."""
    s = import_coverage.summary(conn, source_id)
    if s is None:
        return ""
    out = f"<br>{e(s.headline)}"
    if s.attention:
        lis = "".join(f"<li>{import_coverage.render(i, q, e)}</li>" for i in s.attention)
        out += f"<ul>{lis}</ul>"
    return out


def _date_order_choice(off: str) -> str:
    return (
        f"<p><label>Date order <select name='date_order'{off}>"
        "<option value=''>let Mabillon work it out</option>"
        "<option value='mdy'>month first (3/4 is 4 March)</option>"
        "<option value='dmy'>day first (3/4 is 3 April)</option>"
        "</select></label> <span class='muted'>Dates like 3/4/2026 that nothing in the report "
        "decides are left unread unless you state the order.</span></p>"
    )


def _upload_form(page: Page, kind: str, label: str, accept: str, disabled: bool) -> str:
    """multipart form; the token comes before the file so the server checks it first."""
    off = " disabled" if disabled else ""
    return (
        "<form method='post' action='/case/import' enctype='multipart/form-data' class='box'>"
        f"<input type='hidden' name='token' value='{e(page.token)}'>"
        f"<input type='hidden' name='kind' value='{e(kind)}'>"
        f"<p><strong>{e(label)}</strong></p>"
        + (_date_order_choice(off) if kind == "report" else "")
        + f"<input type='file' name='file' accept='{e(accept)}' required{off}> "
        f"<button type='submit'{off}>Import</button></form>"
    )


def setup_page(
    conn: sqlite3.Connection,
    page: Page,
    *,
    inputs_folder: str,
    order: list[str],
    ready: list,  # core.casework.cases.Ready
    counts: dict[str, int],
    model_lines: list[tuple[str, str]] | None,
    model_note: str,
    estimate: str,
    job_kind: str | None,
    resumable: str | None,
    protection: str = "plain",  # core.casework.protect.state
    recovery_key: str | None = None,
    cloud: object | None = None,  # core.casework.cloud.CloudChoice
    cloud_case: dict | None = None,  # the case's saved cloud settings
    cloud_key: str | None = "",  # None: a key is set up; else why not
) -> str:
    busy = job_kind is not None
    audit_busy = job_kind == "audit"
    out = ["<h1>Set up and run</h1>", recovery_box(page, recovery_key), name_form(page)]
    out.append(
        "<p>Four steps: import the files, settle the claims, confirm who used each phone, then "
        "run the audit. It runs in the background; you can review each claim as soon as it is "
        "labeled.</p>"
    )

    # 1. files
    out.append("<h2 id='files'>1. Files</h2>")
    srcs = sources(conn)
    govdocs = {r[0]: r for r in conn.execute("SELECT source_id, title, doc_kind FROM govdocs")}
    if srcs:
        out.append(
            "<table><thead><tr><th>File</th><th>What it is</th><th>Coverage</th>"
            "<th>Records</th><th>SHA-256</th><th>Imported (UTC)</th></tr></thead>"
        )
        for sid, kind, fidelity, extraction, fname, sha, tool, tver, at in srcs:
            if sid in govdocs:
                what = f"government document: {q(govdocs[sid][1])} ({e(govdocs[sid][2])})"
                cov = "not applicable"
                n = conn.execute(
                    "SELECT COUNT(*) FROM govdoc_paragraphs p JOIN govdocs g ON g.id = p.govdoc_id"
                    " WHERE g.source_id = ?",
                    (sid,),
                ).fetchone()[0]
                recs = f"{n} paragraphs"
            else:
                what = f"{e(kind)}, {e(extraction)} extraction, {e(tool)} {e(tver or '')}"
                fc = tested.for_source(conn, sid)
                what += format_notice(fc) if fc is not None else ""
                cov = e(FIDELITY.get(fidelity, fidelity)) + _import_coverage(conn, sid)
                recs = str(counts.get(sid, 0))
            out.append(
                f"<tr><td>{q(fname)}<br><span class='mono'>{e(sid)}</span></td><td>{what}</td>"
                f"<td>{cov}</td><td>{recs}</td><td class='mono'>{e(sha)}</td>"
                f"<td class='when'>{e(at)}</td></tr>"
            )
        out.append("</table>")
    else:
        out.append("<p class='muted'>No files yet.</p>")
    out.append(
        "<p class='muted'>Each file is copied into "
        f"<span class='mono'>{e(inputs_folder)}</span>, made read-only and SHA-256 hashed; "
        "Mabillon reads only the copy, and the hash of what it parsed must match the hash of what "
        "it received. Your original file is not changed.</p>"
    )
    out.append(
        _upload_form(
            page,
            "govdoc",
            "Government document (PDF): affidavit, police or forensic report",
            ".pdf",
            busy,
        )
        + _upload_form(
            page,
            "report",
            "Phone report: Cellebrite (UFDR package .ufdr, Excel .xlsx or PDF) or Magnet AXIOM "
            "(XML or Excel export). Only a UFDR stating report version 7.48 has been tested; "
            "every other format or version shows a not-tested notice",
            ".xlsx,.pdf,.ufdr,.zip,.xml",
            busy,
        )
    )

    # 2. claims
    out.append("<h2 id='claims'>2. Claims</h2>")
    claims = {c.id: c for c in pipeline.load_claims(conn, include_removed=True)}
    has_paras = conn.execute("SELECT 1 FROM govdoc_paragraphs LIMIT 1").fetchone() is not None
    if not has_paras:
        out.append("<p class='muted'>Import the government document first.</p>")
    else:
        out.append(
            page.form(
                "/claims/propose",
                "<button type='submit'" + (" disabled" if busy else "") + ">Propose claims with "
                "the local model</button> <span class='muted'>The model reads each paragraph "
                "that has no claims yet and proposes claims, each quoting its paragraph. Nothing "
                "is audited until you accept, edit or remove each one. Or "
                "<a href='/claim/new'>add a claim yourself</a>.</span>",
                back="/setup",
                anchor="claims",
            )
        )
    if order or any(c.status.value == "removed" for c in claims.values()):
        out.append(
            "<p>Claims run in this order. Move the ones you want first to the top.</p>"
            "<table><thead><tr><th>#</th><th>Claim</th><th>Where</th><th>Type</th><th>Status</th>"
            "<th>Text</th><th>Decide</th></tr></thead>"
        )
        for n, cid in enumerate(order, 1):
            c = claims[cid]
            where = _where_short(conn, c.paragraph_id)
            out.append(
                f"<tr id='claim-{e(cid)}'><td>{n}</td><td><a href='{e(link('/claim', id=cid))}'>"
                f"{e(claim_name(conn, cid, c.paragraph_id))}</a></td>"
                f"<td>{e(where)}</td><td>{e(c.claim_type.value.replace('_', ' '))}</td>"
                f"<td>{e(c.status.value)}"
                f"{'' if c.model_run_id is None else ' (model)'}</td><td>{q(c.text)}</td>"
                f"<td>{_claim_buttons(page, cid, c.status.value, c.text, audit_busy)}</td></tr>"
            )
        out.append("</table>")
        removed = [c for c in claims.values() if c.status.value == "removed"]
        if removed:
            out.append(
                "<p class='muted'>Removed (not audited): "
                + ", ".join(
                    f"<a href='{e(link('/claim', id=c.id))}'>"
                    f"{e(claim_name(conn, c.id, c.paragraph_id))}</a>"
                    for c in removed
                )
                + ". Open one to accept it again.</p>"
            )

    # 3. owners, then the other people the document names
    out.append("<h2 id='owners'>3. Who used each phone</h2>")
    out.append(_devices(conn, page, "/setup", heading=False))
    out.append(_identities_step(conn))

    # 4. model and run
    out.append("<h2 id='model'>4. The model</h2>")
    if model_lines:
        out.append(
            "<ul>"
            + "".join(
                f"<li>{'' if lvl == 'ok' else '<strong>'}{e(msg)}"
                f"{'' if lvl == 'ok' else '</strong>'}</li>"
                for lvl, msg in model_lines
            )
            + "</ul>"
        )
    if cloud is not None:
        out.append(cloud_section(page, cloud, cloud_case or {}, cloud_key, job_kind == "audit"))
        out.append("<h3>The local model</h3>")
    out.append(f"<p class='muted'>{e(model_note)}</p>")
    out.append(
        page.form(
            "/model/check",
            "<button type='submit'" + (" disabled" if busy else "") + ">Check the model now"
            "</button> <span class='muted'>Finds the model file, checks its SHA-256 against the "
            "config and checks this computer's memory. The audit also does this first.</span>",
            back="/setup",
            anchor="model",
        )
    )

    out.append("<h2>5. Run the audit</h2>")
    blocking = [r for r in ready if not r.ok and r.blocks and r.acknowledge is None]
    out.append(
        "<ul>"
        + "".join(
            f"<li>{'Done' if r.ok else '<strong>To do</strong>'}: {e(r.text)}</li>" for r in ready
        )
        + "</ul>"
    )
    if resumable:
        out.append(f"<p><strong>{e(resumable)}</strong></p>")
    out.append(f"<p>{e(estimate)}</p>")
    acks = "".join(
        f"<p><label><input type='checkbox' name='{e(r.acknowledge)}' value='1'> Run without it: "
        "I accept that checks on who sent a message may come back inconclusive.</label></p>"
        for r in ready
        if not r.ok and r.acknowledge
    )
    if audit_busy:
        out.append("<p><a href='/run'>The audit is running. See its progress.</a></p>")
    else:
        start = "Resume the audit" if resumable else "Start the audit"
        off = " disabled" if (busy or blocking) else ""
        out.append(
            page.form(
                "/audit/start",
                acks
                + "<p><label><input type='checkbox' name='ai_review' value='1'> Also run the AI "
                "reviewer: a sorting aid that decides nothing and costs one more model call per "
                "supporting item.</label><br><label><input type='checkbox' name='label_all' "
                "value='1'> Also label claims a failed check already decides (more model calls; "
                "their verdict cannot change).</label><br><label><input type='checkbox' "
                "name='no_challenge' value='1'> Skip the challenge step: code's searches for "
                "what undercuts a claim close to supported. It only adds doubt; skipping it "
                "saves model calls.</label></p>"
                f"<button type='submit' class='primary'{off}>{start}</button> "
                "<span class='muted'>Keeps this "
                "computer awake while it runs. You can stop it; finished claims are kept.</span>",
                back="/run",
            )
        )
    out.append(encryption_section(page, protection, busy))
    # No refresh while the recovery key is on screen: it must not vanish mid-copy.
    refresh = 10 if busy and recovery_key is None else None
    return page.wrap("Set up and run", "".join(out), refresh=refresh)


def cloud_section(
    page: Page, choice: object, saved: dict, key_problem: str | None, busy: bool
) -> str:
    """Step 4's cloud part: which model labels this case, the per-case attestation, the key."""
    from core.casework.cloud import ATTESTATION, CSAM_NOTE

    use = bool(getattr(choice, "use", False))
    why = str(getattr(choice, "why", ""))
    off = " disabled" if busy else ""
    allowed = saved.get("allowed") is True
    csam = saved.get("csam") is True
    out = [
        "<div id='cloud'><h3>Cloud AI for this case</h3>",
        f"<p><strong>{'Cloud AI on for this case' if use else 'Local only'}.</strong> {e(why)}</p>",
        "<p class='muted'>Off by default: everything runs on this computer unless you opt in "
        "for this case below.</p>",
        "<p class='muted'>With cloud AI, Mabillon sends one question at a time to Anthropic under "
        "your own key: the assumption being tested, one record, the messages around it, the "
        "claim, and for a group chat its member list (up to 20 accounts, with the names you "
        "confirmed for them). Never your files or the case database. The cloud model only "
        "labels evidence; the verdict rules and your review are unchanged. A case's labels never "
        "mix models: if the cloud model stops answering, the audit pauses and you choose to "
        "retry it or turn cloud AI off here and run the whole case locally. Every request is "
        "recorded in the case's audit log, with its time, before it is sent. How long Anthropic "
        "keeps API data: <a href='https://privacy.claude.com/en/articles/7996866-how-long-do-you-"
        "store-my-organization-s-data' rel='noreferrer'>Anthropic's commercial retention "
        "policy</a>.</p>",
        page.form(
            "/cloud/case",
            "<p><label><input type='checkbox' name='allowed' value='1'"
            f"{' checked' if allowed else ''}> {e(ATTESTATION)}</label></p>"
            "<p><label><input type='checkbox' name='csam' value='1'"
            f"{' checked' if csam else ''}> {e(CSAM_NOTE)} This case then never uses cloud AI."
            "</label></p>"
            f"<button type='submit'{off}>Save the cloud choice</button> <span class='muted'>"
            "Recorded in the case's audit log under your name.</span>",
            back="/setup",
            anchor="cloud",
        ),
    ]
    from core.llm.cloud import key_env_in_use, key_from_environment

    if key_problem is None and key_from_environment():
        out.append(
            "<p>The Anthropic key in use comes from "
            f"<span class='mono'>{e(key_env_in_use())}</span>. "
            "Change or unset it there; a key saved here would not be used.</p></div>"
        )
        return "".join(out)
    if key_problem is None:
        out.append(
            "<p>An Anthropic key is set up on this computer. Replace it below if you need to.</p>"
        )
    else:
        out.append(f"<p><strong>No cloud key yet</strong> ({e(key_problem)}).</p>")
    out.append(
        page.form(
            "/cloud/key",
            "<input type='password' name='api_key' required autocomplete='off' "
            "placeholder='sk-ant-...' aria-label='Your Anthropic API key'> "
            f"<button type='submit'{off}>Save the key</button> <span class='muted'>Your own "
            "key, from your firm's Anthropic account (ask for zero data retention). In an "
            "encrypted case it is saved in the case, encrypted with the case's key; otherwise only "
            "on this "
            "computer, readable by your user account. It is never shown again.</span>",
            back="/setup",
            anchor="cloud",
        )
    )
    out.append("</div>")
    return "".join(out)


def recovery_box(page: Page, key: str | None) -> str:
    if key is None:
        return ""
    return (
        "<div class='flash' id='recovery'><p><strong>Write down this case's recovery key "
        "now.</strong> It opens the case if the passphrase is lost. Mabillon shows it only this "
        "once and keeps no copy anywhere; keep it away from this computer (on paper, or in your "
        "password manager).</p>"
        f"<p class='mono' style='font-size:1.25em'>{e(key)}</p>"
        + page.form(
            "/case/recovery/done",
            "<button type='submit'>I have written it down</button>",
            "inline",
            back="/setup",
        )
        + "</div>"
    )


def encryption_section(page: Page, protection: str, busy: bool) -> str:
    out = ["<h2 id='encryption'>Encryption</h2>"]
    off = " disabled" if busy else ""
    wait = "<p class='muted'>Wait until the background work finishes.</p>" if busy else ""
    if protection == "plain":
        out.append(
            "<p>This case is <strong>not encrypted</strong>. Anyone who can read its folder "
            "can read its database and the copies of its files. Encrypting locks both with a "
            "passphrase (AES-256). It is a one-way step, it does not change any finding, and "
            "large reports can take a few minutes; keep this page open.</p>"
            + wait
            + page.form(
                "/case/encrypt",
                "<input type='password' name='passphrase' required minlength='12' "
                "autocomplete='new-password' placeholder='Passphrase' aria-label='Passphrase'> "
                "<input type='password' name='passphrase2' required autocomplete='new-password' "
                "placeholder='The passphrase again' aria-label='The passphrase again'>"
                f"<p class='muted'>{e(PASSPHRASE_HINT)}</p>"
                f"<button type='submit'{off}>Encrypt this case</button>",
                back="/setup",
                anchor="encryption",
            )
        )
        return "".join(out)
    if protection == "partial":
        out.append(
            "<p><strong>Encryption did not finish.</strong> Part of this case is still not "
            "encrypted. Enter the passphrase chosen when it started (or the recovery key) to "
            "finish; nothing is lost either way.</p>"
            + wait
            + page.form(
                "/case/encrypt",
                "<input type='password' name='passphrase' required size='30' "
                "autocomplete='current-password' placeholder='Passphrase or recovery key' "
                "aria-label='Passphrase or recovery key'> "
                f"<button type='submit'{off}>Finish encrypting</button>",
                back="/setup",
                anchor="encryption",
            )
        )
        return "".join(out)
    out.append(
        "<p>This case is <strong>encrypted</strong>: its database and the copies of its files "
        "cannot be read without the passphrase or the recovery key. It stays unlocked until you "
        "lock it or stop Mabillon.</p>"
        + wait
        + page.form(
            "/case/lock",
            f"<button type='submit'{off}>Lock this case now</button>",
            back="/cases",
        )
        + "<h3>Change the passphrase</h3>"
        + page.form(
            "/case/passphrase",
            "<input type='password' name='current' required size='34' "
            "autocomplete='current-password' "
            "placeholder='Current passphrase or recovery key' "
            "aria-label='Current passphrase or recovery key'><br>"
            "<input type='password' name='new' required minlength='12' "
            "autocomplete='new-password' placeholder='New passphrase' "
            "aria-label='New passphrase'> "
            "<input type='password' name='new2' required autocomplete='new-password' "
            "placeholder='The new passphrase again' aria-label='The new passphrase again'><br>"
            "<button type='submit'>Change the passphrase</button> <span class='muted'>The "
            "recovery key stays the same.</span>",
            back="/setup",
            anchor="encryption",
        )
    )
    return "".join(out)


def _where_short(conn: sqlite3.Connection, paragraph_id: str) -> str:
    r = conn.execute(
        "SELECT page, para_no, label FROM govdoc_paragraphs WHERE id = ?", (paragraph_id,)
    ).fetchone()
    if r is None:
        return "paragraph not found"
    return f"p. {r[0]}, para {r[2] if r[2] else '#' + str(r[1])}"


def _claim_buttons(page: Page, cid: str, status: str, text: str, locked: bool) -> str:
    if locked:
        return "<span class='muted'>Locked while the audit runs.</span>"
    hidden = f"<input type='hidden' name='claim' value='{e(cid)}'>"
    accept = (
        ""
        if status in ("accepted", "edited")
        else "<button type='submit' name='status' value='accepted'>Accept</button>"
    )
    return (
        (
            page.form("/claim/edit", hidden + accept, "inline", "/setup", f"claim-{cid}")
            if accept
            else ""
        )
        # A removed claim leaves the table, so its form comes back to the section instead.
        + page.form(
            "/claim/edit",
            hidden + "<button type='submit' name='status' value='removed'>Remove</button>",
            "inline",
            "/setup",
            "claims",
        )
        + page.form(
            "/claims/move",
            hidden + "<button type='submit' name='delta' value='-1'>Up</button>"
            "<button type='submit' name='delta' value='1'>Down</button>",
            "inline",
            "/setup",
            f"claim-{cid}",
        )
        + "<details><summary>Edit the wording</summary>"
        + page.form(
            "/claim/edit",
            hidden + "<input type='hidden' name='status' value='edited'>"
            f"<textarea name='text' rows='3' required>{e(text)}</textarea><br>"
            "<button type='submit'>Save</button>",
            back="/setup",
            anchor=f"claim-{cid}",
        )
        + "</details>"
    )


# ---------------------------------------------------------------- audit progress

STATE_TEXT = {
    "queued": "Waiting",
    "labeling": "Labeling now",
    "done": "Finished",
    "failed": "Stopped here; its work was rolled back",
}


def run_page(
    conn: sqlite3.Connection,
    page: Page,
    *,
    run: dict | None,  # pipeline_runs row of the latest full audit, as a dict
    rows: list[tuple],  # run_claims rows: position, claim_id, state, total, labeled, calls
    job: object | None,  # core.casework.jobs.Job of kind audit, if this screen started one
    left: str,
) -> str:
    running = job is not None and getattr(job, "running", False)
    out = ["<h1>Audit progress</h1>"]
    if job is not None:
        if running:
            out.append(
                f"<p><strong>Running: {getattr(job, 'done', 0)} of {getattr(job, 'total', 0)} "
                f"claims finished.</strong> {e(getattr(job, 'message', ''))} {e(left)}</p>"
            )
            hashed = getattr(job, "hashed", None)
            if hashed and getattr(job, "components", None) is None:
                out.append(
                    f"<p>Checking the model file's SHA-256: {hashed[0] * 100 // max(hashed[1], 1)}"
                    "%.</p>"
                )
            if getattr(job, "awake", ""):
                out.append(f"<p class='muted'>{e(job.awake)}</p>")  # type: ignore[attr-defined]
            out.append(
                page.form(
                    "/audit/stop",
                    "<button type='submit'>Stop after the current claim</button> <span "
                    "class='muted'>The claim being labeled finishes first; every finished claim "
                    "is kept and a resumed audit reuses its model outputs.</span>",
                    back="/run",
                )
            )
        else:
            cls = "flash" if getattr(job, "state", "") == "done" else "flash err"
            out.append(f"<div class='{cls}'>{e(getattr(job, 'message', ''))}</div>")
            check = getattr(job, "check", None)
            if check is not None and not check.ok:
                out.append("<ul>" + "".join(f"<li>{e(m)}</li>" for _, m in check.lines) + "</ul>")
    if run is None:
        out.append("<p>No audit has run on this case. <a href='/setup'>Set up and run</a>.</p>")
        return page.wrap("Audit progress", "".join(out), refresh=5 if running else None)
    out.append(
        f"<p>Run <span class='mono'>{e(run['id'])}</span>, started {e(run['started_at_utc'])}, "
        f"status <strong>{e(run['status'])}</strong>"
        + (f": {e(run['note'])}" if run.get("note") else "")
        + ".</p>"
    )
    if not running and run["status"] != "completed":
        out.append(
            "<p>This audit did not finish. Finished claims can be reviewed now. "
            "<a href='/setup'>Resume it from Set up and run</a>; finished claims reuse their "
            "stored model outputs and take seconds.</p>"
        )
    view = pipeline.view_run(conn)
    labels = {}
    if view is not None and view["run_id"] == run["id"]:
        labels = {st.claim.id: st for st in claim_states(conn, run=view)}
    out.append(
        "<table><thead><tr><th>#</th><th>Claim</th><th>State</th><th>Candidates labeled</th>"
        "<th>New model calls</th><th>Finding</th></tr></thead>"
    )
    paragraphs = dict(conn.execute("SELECT id, paragraph_id FROM claims"))
    for pos, cid, state, total, labeled, calls in rows:
        st = labels.get(cid)
        if state == "done" and st is not None and not st.incomplete:
            finding = f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span>"
        elif state == "done":
            finding = "<span class='muted'>Finished; shown once it is the run on screen</span>"
        else:
            finding = "<span class='verdict v-unp'>Labeling incomplete</span>"
        cands = "" if total is None else f"{labeled} of {total}"
        out.append(
            f"<tr><td>{pos}</td><td><a href='{e(link('/claim', id=cid))}'>"
            f"{e(claim_name(conn, cid, paragraphs.get(cid, '')))}</a></td>"
            f"<td>{e(STATE_TEXT.get(state, state))}</td><td>{cands}</td><td>{calls}</td>"
            f"<td>{finding}</td></tr>"
        )
    out.append("</table>")
    return page.wrap("Audit progress", "".join(out), refresh=10 if running else None)
