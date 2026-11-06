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

import json
import re
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
    VerdictDecision,
    display_tier,
)
from core.hypotheses import explain
from core.ingest import coverage as import_coverage
from core.ingest import forwarded, tested
from core.report import why
from core.report.fmt import e, q
from core.report.html import (
    COVERAGE,
    EXTRACTION,
    SOURCE_KIND,
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
from core.report.html import CSS as REPORT_CSS
from core.report.hypotheses import CSS as ALTERNATIVES_CSS
from core.report.hypotheses import alternatives_html
from core.report.names import Names, plain_ids
from core.report.paired import CSS as PAIRED_CSS
from core.report.paired import claim_line
from core.report.restore import CSS as RESTORE_CSS
from core.report.selection import CSS as SELECTION_CSS
from core.report.selection import anchor as selection_anchor
from core.report.selection import claim_note, sender_words
from core.report.timeline import CSS as TIMELINE_CSS
from core.review import activity, device_names
from core.review import flags as F
from core.review import withheld as W
from core.review.activity import VIEW
from core.review.status import (
    AGAINST,
    AGENT_STEP,
    CONTRADICTION_FOUND,
    GAP_TOPICS,
    STALE,
    ClaimState,
    _agent,
    agent_fail_step,
    case_holdings,
    claim_name,
    claim_state,
    claim_states,
    queue,
    signoff,
)
from core.selection.audit import selection_audit
from core.selection.paired import paired_check
from ui.css import PAGE_CSS
from ui.theme import FONT_CSS, MARK, THEME_CSS

CONTEXT_WINDOW = 10  # messages either side: about 20 messages of context

UI_CSS = """
tr.target td { font-weight: bold; background: var(--warn); }
.ctx td { font-size: 12px; }
"""


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
        case_key: str = "",
    ):
        self.token = token
        self.case_key = case_key  # names the open case in every form, so a stale tab's post
        # for another case is refused (ui/app.py, App._stale_case)
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
            + self.case_field()
            + (f'<input type="hidden" name="next" value="{e(back)}">' if back else "")
            + body
            + "</form>"
        )

    def case_field(self) -> str:
        """The hidden field naming the case this page was drawn for, or nothing with no case."""
        if not self.case_key:
            return ""
        return f'<input type="hidden" name="for_case" value="{e(self.case_key)}">'

    def wrap(
        self,
        title: str,
        body: str,
        banner: str = "",
        refresh: int | None = None,
        wide: bool = False,
    ) -> str:
        who = (
            f"<span class='who' title='Your name goes with every decision'>{e(self.expert)}</span>"
            if self.expert
            else "<a class='who' href='/'>Enter your name</a>"
        )
        flash = ""
        if self.flash:
            msg, err = self.flash
            # A toast: the page may open part-way down, at the item acted on.
            flash = f'<div class="flash toast{" err" if err else ""}" role="status">{e(msg)}</div>'
        meta = f"<meta http-equiv='refresh' content='{int(refresh)}'>" if refresh else ""
        groups = TAB_GROUPS if self.case_name is not None else []
        if self.many_cases and self.case_name is None:
            groups = [[("/cases", "Cases")]]
        links = "<span class='sep' aria-hidden='true'></span>".join(
            "".join(
                f"<a href='{href}'{' class=on' if _tab(self.path) == href else ''}>{label}</a>"
                for href, label in group
            )
            for group in groups
        )
        case = ""
        if self.case_name is not None:  # the case's name; with a cases folder, a way back to it
            tag, href = (
                ("a", " href='/cases' title='All cases'") if self.many_cases else ("div", "")
            )
            on = " on" if self.path == "/cases" else ""
            case = f"<{tag} class='casename{on}'{href}>{q(self.case_name)}</{tag}>"
        notice = f"<div class='flash'>{self.notice}</div>" if self.notice else ""
        return (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>{meta}"
            f"<title>{e(title)} · Mabillon</title>"
            f"<style>{FONT_CSS}{REPORT_CSS}{RESTORE_CSS}{SELECTION_CSS}{TIMELINE_CSS}{PAIRED_CSS}{ALTERNATIVES_CSS}{UI_CSS}{THEME_CSS}{PAGE_CSS}</style>"
            "</head><body>"
            "<header class='top'><div class='bar'>"
            f"<a class='brand' href='{'/' if self.case_name is not None else '/cases'}'>"
            f"{MARK}<span>Mabillon</span></a>{case}<div class='right'>"
            + (
                "<a class='pill' href='/setup#cloud' title='One question at a time goes to "
                "Anthropic'>Cloud labels on</a>"
                if self.cloud
                else "<span class='pill' title='Nothing leaves this computer'>Offline</span>"
            )
            + f"{who}<a href='/help' class='help'>Help</a></div></div>"
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
        ("/setup", "Set up and run"),
        ("/log", "Audit log"),
        ("/activity", "Activity"),
    ],
    [("/cases", "All cases")],  # switching case is the most common move between sessions
]


def _tab(path: str) -> str:
    """The tab a page sits under: a claim and its evidence under the queue."""
    if path in ("/claim", "/evidence", "/claim/new"):
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
        out.append(_folded(stand_in_banner(run)))  # every word stays, under its first sentence
    later = conn.execute(
        "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind = 'expert'"
        " AND decided_at_utc > ?",
        (run["started_at_utc"],),
    ).fetchone()[0]
    stips = conn.execute(
        "SELECT COUNT(*) FROM stipulations WHERE decided_at_utc > ?", (run["started_at_utc"],)
    ).fetchone()[0]
    # a confirmed failed check, or a rejection that undoes one, the claim page marks stale
    agent = len(_agent(conn, run).confirmed_after)
    if (later or stips or agent) and not run.get("partial") and not page.busy:
        what = []
        if later:
            what.append(f"{later} evidence decision{'' if later == 1 else 's'}")
        if stips:
            what.append(f"{stips} stipulation change{'' if stips == 1 else 's'}")
        if agent:
            what.append(f"a failed-check decision on {agent} claim{'' if agent == 1 else 's'}")
        out.append(
            "<div class='banner'><strong>Verdicts are out of date.</strong> You made "
            f"{' and '.join(what)} after the last verdict run. Re-run the verdicts to apply them. "
            "This runs the verdict rules only; no model is called."
            + page.form(
                "/redecide",
                "<button type='submit' class='primary'>Re-run verdicts</button>",
                "",
                back,
                "verdict" if back.startswith("/claim?") else "audit" if back == "/" else "",
            )
            + "</div>"
        )
    return "".join(out)


def _folded(banner: str) -> str:
    """A notice banner folded to its bold first sentence; the rest opens under it. Every word
    stays on the page. The first sentence reads as the fold's title, so it drops its period."""
    head, rest = banner.split("</strong>", 1)
    head = head.replace("<div class='banner'>", "", 1).removesuffix(".")
    rest = rest.removesuffix("</div>")
    return (
        f"<div class='banner'><details><summary>{head}</strong></summary>"
        f"<p>{rest.strip()}</p></details></div>"
    )


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
    """The case at a glance: what waits on the expert first, then how the case is set up, then
    the record of runs, versions and the audit log, kept quiet."""
    run = pipeline.view_run(conn)
    summary = audit_log_summary(conn)
    # the case name is the expert's own text, so it is cited, not Mabillon's words
    out = [f"<h1>{q(page.case_name) if page.case_name else 'Case overview'}</h1>"]
    if not summary["chain_ok"]:
        out.append(
            "<div class='flash err'><strong>Audit log hash chain FAILED VERIFICATION.</strong> "
            "The log was changed outside Mabillon. <a href='/log'>Open the log</a>.</div>"
        )
    if not page.expert:
        out.append(
            page.form(
                "/expert",
                "<p><strong>Your name</strong></p><input type='text' name='name' required "
                "maxlength='60' placeholder='Your name'> <button type='submit' class='primary'>"
                "Start reviewing</button>",
            )
        )
    out.append("<section id='audit'>")
    if run is None:
        out.append("<p>No audit has run yet. <a href='/setup'>Set up and run the audit</a>.</p>")
        states: list[ClaimState] = []
    else:
        states = claim_states(conn, run=run)
        out.append(_case_status(states))
        out.append(_withheld_overview(states))
    out.append("</section>")
    out.append(_case_setup(conn))
    out.append(_record(conn, page, run, summary))
    # the notices sit together above the title, as the other pages show their banners, in one
    # quiet panel (ui/css/overview.py) rather than a box each
    notices = run_banner(conn, page, "/") + _format_notices(conn)
    if notices:
        notices = f"<div class='ov-notices'>{notices}</div>"
    return page.wrap("Case", f"<div class='pg-overview'>{''.join(out)}</div>", notices)


def _case_status(states: list[ClaimState]) -> str:
    """One action (the claims waiting on the expert), then the counts grouped as the Claims
    screen groups them, each linking to its section there."""
    by = Counter(_group(st) for st in states)
    waiting = by["you"]
    action = (
        f"{waiting} {'claim needs' if waiting == 1 else 'claims need'} you"
        if waiting
        else "Open the claims"
    )
    counts = "".join(
        f"<li><a href='/claims#{g}'><span class='name t-{g}'>{e(name)}</span> "
        f"<b>{by[g]}</b></a></li>"
        for g, name in GROUPS
        if g != "you" and (by[g] or g != "not")
    )
    return (
        "<div class='casestatus'>"
        f"<a class='button primary' href='/claims'>{e(action)}</a>"
        f"<ul class='findings'>{counts}</ul></div>"
    )


def _case_setup(conn: sqlite3.Connection) -> str:
    """The devices, who used each one and the document's names for it, read-only: they change on
    Set up and run. Then the government documents."""
    devices = list(conn.execute("SELECT id, label, model, source_id FROM devices ORDER BY id"))
    stips = {s.subject_id: s for s in pipeline.load_stipulations(conn)}
    named = device_names.logged_names(conn)
    rows = []
    for dev_id, label, _model, source_id in devices:
        st = stips.get(dev_id)
        # the stipulation in words: the device's id is in its name's hover title, not the text
        who = (
            f"<span title='{e(dev_id)}'>Stipulated: "
            f"{q(st.statement.replace(f' ({dev_id})', ''))}</span>"
            if st is not None and st.status == StipulationStatus.CONFIRMED
            else "<span class='ov-none'>no stipulated user</span>"
        )
        names = named.get(dev_id, [])
        called = f" · the document calls it {q(', '.join(names))}" if names else ""
        # the device on the left, with its source id under it; who used it on the right
        rows.append(
            f"<li id='dev-{e(dev_id)}'><span class='ov-dev'><b>{q(label)}</b> "
            f"<span class='src'>From {e(source_id)}</span></span>"
            f"<span class='ov-who'>{who}{called}</span></li>"
        )
    if not rows:
        rows.append("<li class='muted'>No devices imported.</li>")
    govdocs = list(conn.execute("SELECT title, doc_kind FROM govdocs ORDER BY id"))
    docs = (
        "; ".join(f"{q(t)} ({e(k)})" for t, k in govdocs)
        if govdocs
        else "<span class='muted'>none imported</span>"
    )
    return (
        "<div class='ov-head'><h2 id='setup'>Case setup</h2><a href='/setup'>Change</a></div>"
        "<ul class='setuplist'>"
        + "".join(rows)
        + "<li><span class='ov-dev'>Government documents</span>"
        f"<span class='ov-who'>{docs}</span></li></ul>"
    )


def _record(conn: sqlite3.Connection, page: Page, run: dict | None, summary: dict) -> str:
    """The run, its versions, the audit log, flags and the files' hashes: the record behind the
    verdicts, kept quiet."""
    rows: list[tuple[str, str]] = []
    if run is not None:
        mode = (
            f"verdict rules re-run after expert review, from {e(run['from_run'])}"
            if run.get("mode") == "rules_only"
            else "audit not finished, labeling incomplete"
            if run.get("partial")
            else "full audit"
        )
        rows += [
            (
                "Latest run",
                f"<span class='mono'>{e(run['run_id'])}</span> ({mode}) · "
                "<a href='/run'>its claims, one by one</a>",
            ),
            ("Started (UTC)", e(run["started_at_utc"])),
            (
                "Versions",
                f"Mabillon {e(build_label(run))}, rule version {e(run['rule_version'])}, quote "
                f"check {e(quote_check_label(run))}, contracts {e(run['contracts_version'])}",
            ),
        ]
    rows.append(
        (
            "Audit log",
            f"<a href='/log'>{summary['entries']} entries</a>, hash chain "
            f"{'verified' if summary['chain_ok'] else '<strong>FAILED VERIFICATION</strong>'}",
        )
    )
    active = F.active_flags(conn)
    rows.append(("Flags", f"<a href='/log#flags'>{len(active)}</a>"))
    out = [
        "<section class='ov-record'><h2 id='record'>Record</h2><dl class='record'>"
        + "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in rows)
        + "</dl>"
    ]
    srcs = sources(conn)
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
    if page.expert:
        out.append(
            "<details class='custody'><summary>Change reviewer</summary>"
            + page.form(
                "/expert",
                "<input type='text' name='name' required maxlength='60' placeholder='Your name'>"
                " <button type='submit'>Change</button>",
            )
            + "</details>"
        )
    out.append("</section>")
    return "".join(out)


def _format_notices(conn: sqlite3.Connection) -> str:
    """Each evidence source's format notice (core/ingest/tested.py), as the report's Limitations
    print it, folded under one line that counts the untested ones."""
    checks = tested.all_sources(conn)
    if not checks:
        return ""
    untested = sum(1 for c in checks if not c.tested)
    n = len(checks)
    head = (
        f"{untested} of {n} file{'' if n == 1 else 's'} come from an export version not tested "
        "with Mabillon. Check results against the source tool."
        if untested
        else f"Format notices for {n} file{'' if n == 1 else 's'}"
    )
    notices = "".join(format_notice(c) for c in checks)
    return (
        f"<div class='banner' id='formats'><details><summary><strong>{e(head)}</strong>"
        f"</summary>{notices}</details></div>"
    )


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
        f"<p><strong>Other people the document names:</strong> {added} added; "
        f"{by.get('confirmed', 0)} link(s) confirmed, {by.get('proposed', 0)} proposed. "
        "<a href='/identities'>Open Identities</a></p>"
    )


def _devices(conn: sqlite3.Connection, page: Page, back: str, heading: bool = True) -> str:
    devices = list(conn.execute("SELECT id, label, model, source_id FROM devices ORDER BY id"))
    stips = {s.subject_id: s for s in pipeline.load_stipulations(conn)}
    named = device_names.logged_names(conn)
    out = [
        ("<h2>Devices and stipulations</h2>" if heading else "")
        + "<p class='muted'>A stipulation you make, not a finding. Every report lists it as a "
        "limitation.</p>"
        "<table class='tidy'><thead><tr><th>Device</th><th>Source</th><th>Stipulated user</th>"
        "<th>Change</th><th>Document names</th></tr></thead>"
    ]
    for dev_id, label, model, source_id in devices:
        st = stips.get(dev_id)
        if st is not None and st.status == StipulationStatus.CONFIRMED:
            by = e(st.decided_by.removeprefix("expert:"))
            who = f"{q(st.statement)}<br><span class='muted'>Stipulated by {by}</span>"
            withdraw = page.form(
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
            withdraw = ""
        stipulate = page.form(
            "/stipulate",
            f"<input type='hidden' name='device' value='{e(dev_id)}'>"
            "<input type='text' name='person' required maxlength='120' placeholder='Person'>"
            "<button type='submit'>Stipulate</button>",
            "inline",
            back,
            f"dev-{dev_id}",
        )
        # With a stipulation in place, Withdraw comes first and naming someone else folds away.
        change = (
            f"<div class='row-actions'>{withdraw}</div>"
            f"<details><summary>Name someone else</summary>"
            f"<div class='row-actions'>{stipulate}</div></details>"
            if withdraw
            else f"<div class='row-actions'>{stipulate}</div>"
        )
        names = page.form(
            "/device/names",
            f"<input type='hidden' name='device' value='{e(dev_id)}'>"
            f"<input type='text' name='names' maxlength='400' placeholder='TARGET PHONE'"
            f" value='{e(', '.join(named.get(dev_id, [])))}'>"
            "<button type='submit'>Save names</button>",
            "inline",
            back,
            f"dev-{dev_id}",
        )
        # The model line is left out when the label already is the model.
        shown_model = "" if not model or model == label else f"<br>{q(model)}"
        out.append(
            f"<tr id='dev-{e(dev_id)}'><td>{q(label)}{shown_model}<br>"
            f"<span class='mono muted'>{e(dev_id)}</span></td>"
            f"<td class='mono'>{e(source_id)}</td><td>{who}</td>"
            f"<td class='controls'>{change}</td>"
            f"<td class='controls'><div class='row-actions'>{names}</div></td></tr>"
        )
    out.append("</table>")
    if not devices:
        out.append("<p class='muted'>No devices imported.</p>")
    out.append(_device_notes(conn))
    return "".join(out)


def _digits(number: str) -> str:
    """A phone number compared by its last ten digits (+1 212 555 0111 and 2125550111 match)."""
    d = re.sub(r"\D", "", number)
    return d[-10:] if len(d) >= 10 else ""


def _device_notes(conn: sqlite3.Connection) -> str:
    """Two cheap checks on the phones, as notes, never merges: two reports that list the same
    number as the phone's own (the same handset in two formats, or two handsets that shared a
    SIM), and a document whose phone numbers match none of the phones' own numbers."""
    own: dict[str, set[str]] = {}
    files = dict(
        conn.execute("SELECT d.id, s.file_name FROM devices d JOIN sources s ON s.id = d.source_id")
    )
    for dev, ident in conn.execute(
        "SELECT device_id, identifier FROM accounts WHERE device_id IS NOT NULL"
    ):
        d = _digits(ident or "")
        if d:
            own.setdefault(dev, set()).add(d)
    notes = []
    devs = sorted(own)
    for i, a in enumerate(devs):
        for b in devs[i + 1 :]:
            if own[a] & own[b]:
                notes.append(
                    f"The phones in {q(files.get(a, a))} and {q(files.get(b, b))} list the same "
                    "number as their own. They may be one handset in two report formats (or two "
                    "handsets that shared a SIM). Mabillon keeps them apart: stipulate each, "
                    "the same way if they are one phone."
                )
    numbers = {
        _digits(m)
        for (text,) in conn.execute("SELECT text FROM govdoc_paragraphs")
        for m in re.findall(r"\+?\(?\d[\d\s().-]{8,}\d", text or "")
    } - {""}
    mine = set().union(*own.values()) if own else set()
    if numbers and mine and not numbers & mine:
        notes.append(
            "The government document gives phone numbers, and none of them is a number these "
            "phones list as their own. Check that the reports belong to this case (a number "
            "can also be missing from a report's own accounts)."
        )
    return "".join(f"<p class='note device-note'>{n}</p>" for n in notes)


# ---------------------------------------------------------------- queue


def _vcls(st: ClaimState) -> str:
    """The pill's classes: the verdict's, plus its own style for a claim nothing tested."""
    return f"{st.css} v-nt" if st.untested else st.css


def _ledger_anchor(claim_id: str) -> str:
    """The id of a claim's row in the side ledger. A ledger link lands on it, so the browser
    scrolls the ledger to the claim just opened instead of back to the first claim."""
    return "lg-" + urlquote(claim_id, safe="")


def _ledger(states: list[ClaimState], current: str | None = None) -> str:
    """The claims beside a claim page: each claim's name and status, then its text."""
    rows = []
    for st in states:
        anchor = _ledger_anchor(st.claim.id)
        rows.append(
            f"<li id='{e(anchor)}'{' class=on' if st.claim.id == current else ''}>"
            "<div class='row'><div class='head'><span class='meta'>"
            f"<a href='{e(link('/claim', id=st.claim.id))}#{e(anchor)}'>{e(st.name)}</a></span>"
            f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
            f"<div class='text'>{q(st.claim.text)}</div></div></li>"
        )
    return f"<ul class='ledger'>{''.join(rows)}</ul>"


# where a claim sits on the overview: what waits on the expert first, then the findings
GROUPS = (
    ("you", "Needs you"),
    ("con", "Contradicted"),
    ("unp", "Unproven"),
    ("sup", "Supported"),
    ("not", "Not audited"),
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
    """One claim on the overview, laid out like the site's ledger: its name, the claim, its status
    at the right, then small lines saying where it is, the one thing it needs from the expert and
    the topics that leave it unproven. A status that repeats its group's heading word for word is
    left to the heading. The standing "verdict not yet confirmed" reminder is left out here; the
    claim page shows it."""
    note = ""
    if group == "you":  # why it waits on the expert: the most urgent need, in its words
        lines = _you_lines(st)
        note = f"<div class='needs'>{e(lines[0])}</div>" if lines else ""
    if group in ("you", "unp"):  # why it is unproven: the topics; the claim page says the rest
        note += "".join(f"<span class='gap'>{e(topic)}</span>" for topic, _ in st.explain_lines())
    # a status that repeats its group's heading word for word is left to the heading
    same = group != "you" and st.label == dict(GROUPS)[group]
    pill = f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span>"
    return (
        "<li><div class='row'><span class='cid'>"
        f"<a href='{e(link('/claim', id=st.claim.id))}'>{e(st.name)}</a></span>"
        f"<div class='text'>{q(st.claim.text)}</div>"
        # the heading says it on screen; the words stay for a screen reader and for tools
        + (f"<span class='vh'>{pill}</span>" if same else pill)
        + f"<div class='sub'><span class='meta'>{e(st.where)} · "
        f"{e(st.claim.claim_type.value.replace('_', ' '))}</span>{note}</div></div></li>"
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


def _tile(group: str, name: str, n: int) -> str:
    """A count; it links to its section when there is one (Needs you starts at the next-up card)."""
    inner = f"<span class='name'>{e(name)}</span><span class='n'>{n}</span>"
    if not n:
        return f"<div class='tile t-{group} empty'>{inner}</div>"
    href = "#next" if group == "you" else f"#{group}"
    return f"<a class='tile t-{group}' href='{href}'>{inner}</a>"


def _next_up(st: ClaimState) -> str:
    """The first claim waiting on the expert, with each thing it needs on its own line."""
    lines = "".join(f"<p>{e(t)}</p>" for t in _you_lines(st))
    return (
        "<section class='nextup' id='next'><div class='head'><span class='meta'>Next up · "
        f"<a href='{e(link('/claim', id=st.claim.id))}'>{e(st.name)}</a> · {e(st.where)}</span>"
        f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
        f"<blockquote class='claimtext'>{q(st.claim.text)}</blockquote>"
        f"<div class='todo'>{lines}{_gap_lines(st)}</div>"
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


def claims_queue(conn: sqlite3.Connection, page: Page, next_step: str | None = None) -> str:
    """next_step: before the first audit, the setup step that comes next (the overview then
    says so instead of "Nothing waits on you")."""
    states = queue(conn)
    by: dict[str, list[ClaimState]] = {g: [] for g, _ in GROUPS}
    for st in states:
        by[_group(st)].append(st)
    you, total = len(by["you"]), len(states)
    proposed = conn.execute("SELECT COUNT(*) FROM claims WHERE status = 'proposed'").fetchone()[0]
    if not total:
        head = "No claims yet"
    elif you:
        head = f"{you} claim{'s' if you > 1 else ''} need{'' if you > 1 else 's'} you"
    elif proposed:
        head = f"{proposed} proposed claim{'s' if proposed != 1 else ''} wait for your decision"
    elif next_step:
        head = "Not audited yet"
    else:
        head = "Nothing waits on you"
    lede = ""
    if proposed:
        lede = (
            f"<p class='lede'>{proposed} claim{'s' if proposed != 1 else ''} the local model "
            "proposed wait for you to accept, edit or remove them. Nothing is audited until you "
            "accept it. <a href='/setup#claims'>Decide on Set up and run</a>.</p>"
        )
    elif next_step and not you:
        lede = f"<p class='lede'>Next: {e(next_step)} <a href='/setup'>Set up and run</a>.</p>"
    out = [
        "<div class='pg-claims'>"
        f"<div class='overview-head'><h1>{e(head)}</h1>"
        "<a class='button' href='/claim/new'>Add a claim</a></div>" + lede,
        "<nav class='tiles' aria-label='Claims by finding'>"
        + "".join(_tile(g, name, len(by[g])) for g, name in GROUPS if by[g] or g != "not")
        + "</nav>",
    ]
    if by["you"]:
        out.append(_next_up(by["you"][0]))
    for g, name in GROUPS:
        rows = by[g][1:] if g == "you" else by[g]
        if g == "you" and not rows:
            continue
        if not by[g]:
            continue
        title = "Also waiting on you" if g == "you" else name
        folded = g in ("con", "sup") and bool(by["you"])
        # the heading keeps only the count; a folded group leaves it to its "Show N claims" line
        count = "" if folded else f"{len(rows)} claim{'s' if len(rows) != 1 else ''}"
        out.append(
            f"<section class='group' id='{g}'><div class='ghead'><h2>{e(title)}</h2>"
            + (f"<span class='muted'>{count}</span>" if count else "")
            + "</div>"
            + _group_rows(rows, g, folded=folded)
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
    out.append("</div>")
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
        "placeholder='Reason' aria-label='Reason'><br>"
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
        "placeholder='Reason' aria-label='Reason'><br>"
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
    around_link: bool = True,
    same_as: str | None = None,
) -> str:
    """claim_id: the claim page shows the card; it then carries the optional label flag.
    same_as: the card above on the page for the same record (another assumption's item); this
    card then shows the verified quote and points up, rather than drawing the messages again.
    confirm: a contradiction waiting for the expert (rule 1b), shown with the confirm step.
    around: messages shown either side of the record, as a conversation (0: the quote only).
    threads: the page's cache of thread orders, so many cards read each thread once.
    challenged: the items the challenge step stored in the audit on screen, read once a page.
    around_link: the link to the item's own page (that page leaves it out).
    Once the expert has decided an item, its conversation and its decision form fold."""
    stance_cls = "b-against" if item.stance in AGAINST else "b-open"
    flag = ""
    if claim_id is not None:
        flag = _flag_label_form(page, claim_id, item, back, run_id)
    withheld = W.for_item(conn, item)
    settled = last_kind == "expert" and item.status != EvidenceStatus.OPEN and not confirm
    form = (
        _confirm_form(page, item, back)
        if confirm
        else _decide_form(page, item, last_kind == "expert", back)
    )
    shown, thread = _conversation(conn, item, 0 if same_as else around, threads, folded=settled)
    if same_as:
        shown += (
            f"<p class='ev-same'>The same message as <a href='#{e(same_as)}'>the item above</a>, "
            "judged here for this assumption.</p>"
        )
    folds = ""  # a settled item's disclosures open on the card's last line
    if settled:
        folds = (
            thread
            + f"<details class='ev-change'><summary>Change your decision</summary>{form}</details>"
        )
        form = ""
    around_a = (
        f"<a class='ev-around' href='{e(link('/evidence', id=item.id))}'>Messages around it</a>"
        if around_link
        else ""
    )
    return (
        f"<div class='item' id='{e(item.id)}'>"
        "<div class='ev-tags'>"
        f"<span class='badge {stance_cls}'>{e(STANCE_LABEL[item.stance])}</span>"
        f"{_tier_badge(item, last_kind)}"
        + ("<span class='badge b-flag'>flagged by you</span>" if flagged else "")
        + ("<span class='badge b-withheld'>needs expert review</span>" if withheld else "")
        + (
            f"<span class='badge b-challenge'>{e(challenge.FOUND_MARK)}</span>"
            if item.id in challenged
            else ""
        )
        + "</div>"
        + shown
        + f"<p class='ev-rec'>{record_line(conn, item.record_id, found)}</p>"
        + f"<p class='ev-src muted'>{source_line(conn, item.ref.source_id, item.ref.locator)}</p>"
        + (
            f"<p>{rationale_html(item, withheld)}</p>"
            + ("" if withheld.acknowledged else _acknowledge_form(page, item, back))
            if withheld
            else ""
        )
        + f"<p class='ev-review'><strong>Review:</strong> {review_label(conn, item)}</p>"
        + form
        + f"<div class='ev-foot'>{folds}"
        "<details class='more'><summary>Source and model note</summary>"
        f"<p><span class='mono'>{e(item.ref.source_id)} {e(item.ref.locator)} · "
        f"{e(item.record_id)}</span></p>"
        f"<p class='muted'>{e(labelled_by(conn, item.model_run_id))}."
        + ("" if withheld else f" {rationale_html(item, None)}")
        + "</p></details>"
        + f"{flag}{around_a}</div></div>"
    )


def _records_note(conn: sqlite3.Connection, source_id: str, records: int) -> str:
    """Why Records differs from the rows the coverage line says were imported: rows kept as
    accounts are not records, and one row can hold several records (a contact's two numbers)."""
    row = conn.execute(
        "SELECT payload_json FROM source_coverage WHERE source_id = ?", (source_id,)
    ).fetchone()
    try:
        tables = json.loads(row[0]).get("tables", []) if row else []
    except (ValueError, AttributeError):
        return ""
    imported = sum(int(t.get("rows_imported") or 0) for t in tables)
    if not imported or imported == records:
        return ""
    accounts = sum(int(t.get("rows_imported") or 0) for t in tables if t.get("kind") == "accounts")
    parts = []
    if accounts:
        parts.append(f"{accounts} account row{'s' if accounts != 1 else ''} kept as accounts")
    extra = records - (imported - accounts)
    if extra > 0:
        parts.append(f"{extra} more from rows that hold two or more records (a contact's numbers)")
    elif extra < 0:
        parts.append(f"{-extra} row{'s' if extra != -1 else ''} not stored as records")
    return f"<span class='muted rec-note'>{e('; '.join(parts))}</span>" if parts else ""


_EXCEL_ROW = re.compile(r"^(?P<sheet>.+)!(?P<row>\d+)$")


def source_line(conn: sqlite3.Connection, source_id: str, locator: str) -> str:
    """Where a record is in the original file, unfolded on every card: the file, then the sheet
    and spreadsheet row for an Excel report. The row is the spreadsheet's own row number, which
    is not the report's "#" column (a header row and title rows come before the first record)."""
    row = conn.execute("SELECT file_name, kind FROM sources WHERE id = ?", (source_id,)).fetchone()
    name, kind = (row[0], row[1]) if row else (source_id, "")
    m = _EXCEL_ROW.match(locator)
    if kind == "cellebrite_excel" and m:
        return (
            f"From {q(name)}, {q(m['sheet'])} sheet, spreadsheet row {e(m['row'])} "
            "(Excel's row number, not the report's # column)"
        )
    return f"From {q(name)}, at {e(locator)}"


def _conversation(
    conn: sqlite3.Connection,
    item: EvidenceItem,
    around: int,
    threads: dict[str, list[str]] | None = None,
    folded: bool = False,
) -> tuple[str, str]:
    """The verified quote, and with around > 0 the record among its neighbours: (shown, fold).
    folded: the expert has decided the item, so the neighbours come back as a disclosure (fold)
    for the card's last line, and only the quote shows."""
    quote = f"<blockquote>{q(item.quote)}</blockquote>"
    lines = build_context(conn, item.record_id, around, threads=threads) if around else []
    if len(lines) < 2:  # no neighbours (a contact, a call): the quote says it all
        return quote, ""
    thread = f"<div class='thread mini'>{_msgs(lines)}</div>"
    whole = any(ln.is_target and ln.body.strip() == item.quote.strip() for ln in lines)
    # the quote is the whole highlighted message: the bubble already shows it, word for word
    quoted = (
        "" if whole else f"<p class='quoted'><span class='muted'>Quoted:</span> {q(item.quote)}</p>"
    )
    if folded:
        quoted = quoted or quote  # the neighbours fold away; the quote itself stays in view
        return quoted, (
            f"<details class='ev-thread'><summary>The messages around it ({len(lines)})"
            f"</summary>{thread}</details>"
        )
    return thread + quoted, ""


def _msgs(lines: list[ContextLine]) -> str:
    """Messages as chat bubbles. As a chat app does, a sender is named again only when the
    account on that side of the conversation changes, and always on the record under review;
    the bubble's side gives the direction, which also sits in the sender's hover title."""
    others = {ln.sender for ln in lines if ln.direction != "outgoing"}
    out: list[str] = []
    last: dict[str, tuple[str, str | None, str]] = {}
    for ln in lines:
        # an outgoing message to the one account seen answering here needs no "to"
        to = "" if others == {ln.to} else ln.to
        key = (ln.sender, ln.shown_as, to)
        out.append(_msg(ln, to, same=last.get(ln.direction) == key and not ln.is_target))
        last[ln.direction] = key
    return "".join(out)


def _msg(ln: ContextLine, to: str, same: bool = False) -> str:
    """One message as a chat bubble; the record under review is highlighted. same: the last
    bubble on this side has the same sender, so this one leaves the sender line off. to: the
    recipients, when the conversation shown does not already make them plain."""
    side = " out" if ln.direction == "outgoing" else ""
    tag = "<span class='cited'>This record</span>" if ln.is_target else ""
    who = (
        ""
        if same
        else f"<div class='who2' title='{e(ln.direction)}'>"
        + sender_words(ln.sender, ln.shown_as)
        + (f" to {q(to)}" if to else "")
        + "</div>"
    )
    return (
        f"<div class='msg{side}{' target' if ln.is_target else ''}{' cont' if same else ''}'>"
        + who
        + f"<div class='body'>{q(ln.body)}</div>"
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
            + "<button type='submit'>Save flag</button>",
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
        "<details class='flag'><summary>Flag this verdict</summary>"
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
            + "<button type='submit'>Save flag</button>",
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
            + "<button type='submit'>Save flag</button>",
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
    """The audit log page's flag count and the redacted summary download."""
    active = F.active_flags(conn)
    by_kind = Counter(f.kind for f in active)
    counts = ", ".join(f"{F.KINDS[k].lower()} {n}" for k, n in sorted(by_kind.items()))
    n = len(active)
    # one quiet panel: the count, how to flag, and the download on one line with its note
    return (
        "<section class='logflags'>"
        "<h2 id='flags'>Flags</h2>"
        f"<p><strong>{n} flag{'' if n == 1 else 's'}</strong>{': ' + e(counts) if counts else ''}"
        "</p>"
        "<form method='get' action='/flags/summary.json' class='flagform'>"
        "<input type='text' name='pilot' maxlength='60' placeholder='Pilot name (optional)' "
        "aria-label='Pilot name (optional)'> "
        "<button type='submit'>Download the redacted summary</button>"
        "<p class='muted'>Counts, labels and versions only: no case text, names or ids. Nothing "
        "is sent.</p></form></section>"
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
            "<div class='claim-src'>"
            f"<details><summary>Paragraph as printed ({e(st.where)})</summary>"
            f"<blockquote>{q(st.paragraph_text)}</blockquote></details>"
            f"{_selection_note(conn, st)}</div>"
        )
    out.append(
        "<div class='card' id='verdict'><div class='in'><div class='vhead'><h2>Verdict</h2>"
        f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
    )
    # the standing "not yet confirmed" reminder is the Confirm fold's job; an untested claim's
    # why and the agent's proposal each show in full under Evidence
    needs = [
        t
        for t in _you_lines(st)
        if not (st.untested and (t.startswith("Not tested:") or t == AGENT_STEP))
    ]
    if needs:
        out.append("<ul class='needs'>" + "".join(f"<li>{e(t)}</li>" for t in needs) + "</ul>")
    out.append(_gap_lines(st))  # the same lines as the report
    out.append(_claim_notices(conn, st))
    out.append(forwarded_warning(conn, st))
    out.append(mixed_app_note(conn, st))
    if d is not None:
        out.append(_why(conn, st, d))
        signed = signoff(conn, d)
        if signed:
            note = f" Note: {said(d.override_note)}" if d.override_note else ""
            out.append(f"<p class='signoff'><strong>{e(signed)}</strong>{note}</p>")
        out.append(
            f"</div><div class='in vacts'>{_verdict_forms(page, st, back)}"
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
        out.append(f"<p class='warn'><strong>{e(st.not_tested or '')}</strong></p>")
        if "matches no person" in (st.not_tested or ""):
            out.append(
                "<p><a href='/identities'>Add the name on Identities</a>; the next audit can then "
                "test the claim.</p>"
            )
        out.append(_holdings(conn))
        out.append(
            _agent_card(
                page, conn, testability.proposals(conn, pipeline.view_run(conn)).get(c.id), back
            )
        )
    groups = _groups(st)
    if not groups and not st.untested:  # an untested claim searched nothing, as it says above
        out.append("<p class='muted'>No relevant evidence items.</p>")
    by_assumption = {a.id: a for a in st.assumptions}
    found = forwarded.affected(conn)
    threads: dict[str, list[str]] = {}  # each thread read once for the page's cards
    challenged = challenge.found_items(conn, pipeline.view_run(conn))
    drawn: dict[str, str] = {}  # record id -> the first card on the page that draws it
    for title, group in groups:
        out.append(f"<h3 class='ev-group'>{e(title)} <span>({len(group)})</span></h3>")
        shown_on = None
        order = {a.id: i for i, a in enumerate(st.assumptions)}
        for x in sorted(group, key=lambda x: order.get(x.assumption_id, len(order))):
            a = by_assumption.get(x.assumption_id)
            if a is not None and a.id != shown_on:
                out.append(f"<p class='ev-asm'>Assumption: {plain_ids(conn, a.text)}</p>")
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
                    same_as=drawn.get(x.record_id),
                )
            )
            drawn.setdefault(x.record_id, x.id)
    hidden = [x for x in st.evidence if x.stance == Stance.IRRELEVANT]
    out.append("<div class='claim-more'>")
    if hidden:
        out.append(_irrelevant_list(conn, hidden, flagged, {w.evidence_id for w in st.withheld}))
    out.append(_working(st, Names(conn).for_claim(st.claim.text)))
    if d is not None:  # a flag is about an audited claim
        out.append(_flag_missed_form(page, st, back))
    out.append("</div>")
    out.append(_flags_section(page, claim_flags, back, st.run_id))

    out.append(_edit_claim_form(page, st, back))
    states = claim_states(conn)
    side = f"<aside class='side'>{_ledger(states, c.id)}</aside>"
    # The run banner sits in the claim's column, so the ledger starts at the top of the page and
    # fits the window: its last rows, and the open claim's row pinned to its edge, stay on screen.
    main = run_banner(conn, page, back) + "".join(out)
    body = f"<div class='split pg-claim'>{side}<div class='claim-main'>{main}</div></div>"
    return page.wrap(st.name, body, wide=True)


AROUND = 1  # messages either side of each evidence record on the claim page


def _why(conn: sqlite3.Connection, st: ClaimState, d: VerdictDecision) -> str:
    """Why the verdict: one plain line per reason (core/report/why.py), then the reasons exactly
    as the rules stored them, with the rule version and run, folded as Technical details."""

    def href(rid: str, assumption: str | None, stance: Stance | None) -> str | None:
        """A record's link: its evidence item on this claim for the line's assumption (the one
        read with the line's stance first), else the message in its thread."""
        items = [
            x for x in st.evidence if x.record_id == rid and assumption in (None, x.assumption_id)
        ]
        items.sort(key=lambda x: x.stance is not stance)
        if items:
            return link("/evidence", id=items[0].id)
        return link("/selection/context", id=rid) if rid.startswith("msg:") else None

    names = Names(conn).for_claim(st.claim.text)
    plain = why.lines(
        conn, d.reasons, st.assumptions, st.checks, st.evidence, names=names, href=href
    )
    return (
        "<details class='why'><summary>Why</summary><ul class='why-lines'>"
        + "".join(f"<li>{ln.html}</li>" for ln in plain)
        + "</ul><details class='why-tech'><summary>Technical details</summary><ul>"
        + "".join(f"<li>{names.cite(r)}</li>" for r in d.reasons)
        + f"</ul><p class='muted'>Rule version {e(d.rule_version)}, run "
        f"{e(d.pipeline_run_id)}.</p></details></details>"
    )


def _claim_notices(conn: sqlite3.Connection, st: ClaimState) -> str:
    """The report's format notices for the claim's sources (claim_format_notices); two or more
    fold under one line that counts the untested ones, as the case page does. Every word stays."""
    notices = claim_format_notices(conn, st)
    n = notices.count("<p class='format-notice")
    if n < 2:
        return notices
    untested = notices.count("<p class='format-notice warn'")
    head = (
        f"{untested} of {n} files come from an export version not tested with Mabillon"
        if untested
        else f"Format notices for {n} files"
    )
    return f"<details class='fmt'><summary><strong>{e(head)}</strong></summary>{notices}</details>"


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
        "placeholder='Reason' aria-label='Reason'><br>"
    )
    accept = (
        "<button type='submit' name='decision' value='accept'>Accept these assumptions</button>"
    )
    reject = "<button type='submit' name='decision' value='reject'>Reject</button>"
    if x.decided is None:
        state = "<p><strong>Waiting for you.</strong> Nothing here is used until you accept it.</p>"
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
        "placeholder='Reason' aria-label='Reason'><br>"
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
        tier_attr = ""
        if cv is None:
            mark, said_ = "na", "Not current" if d is not None and st.stale else "Not computed"
        elif cv.covered:
            tier = cv.tier.value if cv.tier else "?"
            mark, said_ = "ok", f"Records found ({tier.replace('_', ' ')})"
            tier_attr = f" data-tier='{e(tier)}'"  # an ai_reviewed tier never tags as confirmed
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
            f"<li class='{mark}'{tier_attr}><span class='mark'></span>"
            f"<div><div>{plain_ids(conn, a.text)}</div>"
            f"<div class='meta'>{e(GAP_TOPICS[a.kind])} · {e(role)}</div></div>"
            f"<span class='said'>{e(said_)}</span></li>"
        )
    return (
        "<section class='truths'><h2>What has to be true</h2>"
        f"<ul class='checklist'>{''.join(rows)}</ul></section>"
    )


def _working(st: ClaimState, names: Names) -> str:
    """The rules' working: the assumption and check tables, folded, as stored (ids stay ids),
    with the claim's own quoted words marked as cited."""
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
                f"<tr><td>{names.cite(a.text)}</td><td>{e(a.kind.value)}</td>"
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
                f"<td>{e(ch.outcome.value)}</td><td>{names.cite(ch.searched)}</td>"
                f"<td>{names.cite(ch.detail)}</td>"
                "</tr>"
            )
        out.append("</table>")

    if not out:
        return ""
    return f"<details class='working'><summary>Rules' working</summary>{''.join(out)}</details>"


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
    # Folded under one line per lead; the report's fragment is shown whole when opened, its
    # headings one level under this section's.
    titles = "".join(f"<span>{e(a.title)}</span>" for a in alts)
    full = alternatives_html(alts, _context_link).replace("<h4>", "<h3>").replace("</h4>", "</h3>")
    return (
        "<details class='alts-fold' id='alternatives'><summary>"
        f"<h2>Other explanations to check ({len(alts)})</h2>"
        f"<span class='alt-titles'>{titles}</span></summary>{full}</details>"
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
    return f"<div class='holdings'><p>Sources in this case</p><ul>{items}</ul></div>"


def _edit_claim_form(page: Page, st: ClaimState, back: str) -> str:
    """The claim's wording: accept or remove it on one line, the new wording folded. Once the
    wording is accepted, Accept as written stays as a quiet button, not the page's main one."""
    cid = e(st.claim.id)
    done = " done" if st.claim.status.value == "accepted" else ""
    return (
        "<section class='wording'><h2 id='edit'>Edit this claim</h2>"
        + page.form(
            "/claim/edit",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<button type='submit' name='status' value='accepted'>Accept as written</button>"
            "<button type='submit' name='status' value='removed'>Remove this claim</button>",
            cls=f"box wording-acts{done}",
            back=back,
            anchor="edit",
        )
        + "<details class='edit-text'><summary>Change the wording</summary>"
        + page.form(
            "/claim/edit",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<input type='hidden' name='status' value='edited'>"
            f"<textarea name='text' rows='3' required>{e(st.claim.text)}</textarea><br>"
            "<button type='submit'>Save new wording</button>",
            back=back,
            anchor="edit",
        )
        + "</details></section>"
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
    out = ["<div class='pg-evidence'><h1>Evidence item</h1>"]
    if claim_id:
        out.append(
            f"<p class='ev-of'>Claim <a href='{e(link('/claim', id=claim_id[0]))}'>"
            f"{e(claim_id[0])}</a>. Assumption: {plain_ids(conn, claim_id[1])}</p>"
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
            around_link=False,
        )
    )
    out.append("<h2>Context</h2>")
    lines = build_context(conn, item.record_id, CONTEXT_WINDOW)
    if lines:
        out.append("<div class='thread'>")
        out.append(_msgs(lines))
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
    out.append("</div>")
    return page.wrap("Evidence", "".join(out), run_banner(conn, page, back))


# ---------------------------------------------------------------- add a claim


def new_claim_page(
    conn: sqlite3.Connection, page: Page, draft: dict[str, str] | None = None
) -> str:
    """Add a claim: each paragraph shown in full to pick from (a short preview hid which
    paragraph was which). `draft` refills the form after a refused add."""
    draft = draft or {}
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
    chosen = draft.get("paragraph") or (paras[0][0] if paras else "")
    groups: dict[str, list[str]] = {}
    for pid, pg, no, label, text, title in paras:
        groups.setdefault(title or "", []).append(
            f"<label class='para-pick'><input type='radio' name='paragraph' value='{e(pid)}'"
            + (" checked" if pid == chosen else "")
            + f" required><span class='where'>Page {pg}, paragraph "
            f"{e(label or '#' + str(no))}</span><span class='text'>{q(text)}</span></label>"
        )
    opts = "".join(
        f"<fieldset class='paras'><legend>{e(title or 'The document')}</legend>"
        f"{''.join(items)}</fieldset>"
        for title, items in groups.items()
    )
    types = "".join(
        f"<option value='{t.value}'"
        + (" selected" if draft.get("type") == t.value else "")
        + f">{e(t.value.replace('_', ' '))}</option>"
        for t in ClaimType
    )
    body = "<h1>Add a claim</h1>"
    if not paras:
        body += "<p>Import the government document first.</p>"
    else:
        body += page.form(
            "/claim/add",
            "<p>Pick the paragraph the claim comes from.</p>"
            f"<div class='para-list'>{opts}</div>"
            "<p><label>Claim text <textarea name='text' rows='4' required>"
            f"{e(draft.get('text', ''))}</textarea></label></p>"
            "<p><label>Claim id <input type='text' name='id' required maxlength='20' "
            f"value='{e(draft.get('id') or f'C{n:02d}')}'></label>"
            f" <label>Type <select name='type'>{types}</select></label></p>"
            "<p class='act'><button type='submit' class='primary'>Add claim</button>"
            "<span class='muted'>Set up lists it as added by the expert, not the model.</span></p>",
        )
    return page.wrap("Add a claim", f"<div class='pg-newclaim'>{body}</div>")


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
        "<p class='chain ok'>Hash chain verified</p>"
        if summary["chain_ok"]
        else "<div class='flash err chain'><strong>Hash chain failed verification.</strong> The "
        "log was changed outside Mabillon.</div>"
    )

    def seg(label: str, options: list[tuple[str, str, bool]]) -> str:
        """A row of links that read as one control; the current choice is marked, not linked."""
        return (
            f"<span class='seg' role='group' aria-label='{e(label)}'>"
            f"<span class='seglabel'>{e(label)}</span>"
            + "".join(
                f"<span class='on' aria-current='true'>{text}</span>"
                if on
                else f"<a href='{e(href)}'>{text}</a>"
                for text, href, on in options
            )
            + "</span>"
        )

    views_p = {"views": "1"} if show_views else {}
    all_p = {"all": "1"} if show_all else {}
    controls = [
        seg(
            "Show",
            [
                ("Newest 200", link("/log", **views_p), not show_all),
                ("All", link("/log", all="1", **views_p), show_all),
            ],
        )
    ]
    if views or show_views:
        controls.append(
            seg(
                "Page views",
                [
                    ("Hidden", link("/log", **all_p), not show_views),
                    (f"Shown ({views})", link("/log", **all_p, views="1"), show_views),
                ],
            )
        )
    out = [
        "<div class='pg-log'>",
        "<h1>Audit log</h1>",
        status,
        f"<p class='chainmeta'>{summary['entries']} entries · last hash <span class='mono'>"
        f"{e(summary['last_hash'])}</span></p>",
        flags_overview(conn),
        "<h2>Entries</h2>",
        f"<div class='logbar'>{''.join(controls)}</div>",
        "<table class='logtable'><thead><tr><th>#</th><th>When (UTC)</th><th>Actor</th>"
        "<th>Action</th><th>Details</th></tr></thead>",
    ]
    for seq, at, actor, action, payload, _h in rows:
        kind, sep, name = str(actor).partition(":")
        who = f"<span class='kind'>{e(kind + sep)}</span>{e(name)}" if sep else e(actor)
        out.append(
            f"<tr><td>{seq}</td><td class='when'>{e(at)}</td><td>{who}</td>"
            f"<td>{e(action)}</td>"
            f"<td class='payload'><span class='mono'>{q(_short(payload, 120))}</span>"
            + (
                "<details><summary>Full entry</summary>"
                f"<div class='mono'>{q(payload)}</div></details>"
                if len(payload) > 120
                else ""
            )
            + "</td></tr>"
        )
    out.append("</table></div>")
    return page.wrap("Audit log", "".join(out))


# ---------------------------------------------------------------- activity

ACTIVITY_NEWEST = 500


def _step_item(s: activity.Step) -> str:
    p = s.payload
    if not s.is_view:
        item = s.evidence_id or s.claim_id
        return f"<span class='mono'>{e(item)}</span>" if item else ""
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
        "<strong>In the report: included.</strong>"
        if on
        else "<strong>In the report: left out.</strong>"
    )
    return page.form(
        "/activity/report",
        f"<p>{state}</p>"
        f"<input type='hidden' name='include' value='{'0' if on else '1'}'>"
        "<button type='submit'>"
        + ("Leave activity out of the report" if on else "Include activity in the report")
        + "</button>",
        "reportswitch",
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
    if total["views"]:
        seen = (
            f"{total['views']} page views in {total['sessions']} screen session"
            f"{'s' if total['sessions'] != 1 else ''}, by {e(', '.join(total['examiners']))}, "
            f"from <span class='t'>{e(total['first_at'])}</span> to "
            f"<span class='t'>{e(total['last_at'])}</span> (UTC)."
        )
    else:
        seen = "No page views are recorded for this case yet."
    out = [
        "<div class='pg-activity'>",
        "<h1>Activity</h1>",
        "<details class='howcounted'><summary>How time on page is counted</summary>"
        "<p class='muted'>Time on page runs from opening a page to the next page opened. "
        "The screen runs no scripts, so Mabillon cannot tell what was on screen or read; a "
        f"stretch over {idle} minutes may include time away, and a page whose end was not "
        "recorded (the screen closed, or the next step came from elsewhere) is not timed; both "
        "are counted apart from totals. "
        "\u201cListed\u201d means the page linked to the item, not that it was opened.</p>"
        "</details>",
        # what was seen and the download on one line; the report switch under it
        f"<div class='actbar'><p>{seen}</p>"
        "<a class='dl' href='/activity.csv'>Download the trail (CSV)</a></div>",
        _report_switch(conn, page),
    ]
    out.append(
        "<h2>By claim</h2><table class='byclaim'><thead><tr><th>Claim</th>"
        "<th class='n'>Times opened</th><th>First opened (UTC)</th><th>Last opened (UTC)</th>"
        "<th class='n'>Time on its pages</th><th class='n'>Evidence items opened</th>"
        "<th class='n'>Evidence items listed</th><th class='n'>Actions</th></tr></thead>"
    )
    for cid in claims:
        a = per.get(cid)
        if a is None or not (a.opened or a.evidence_opened):
            out.append(
                f"<tr class='unopened'><td><a href='{e(link('/activity', claim=cid))}'>"
                f"{e(cid)}</a></td>"
                "<td>0</td><td colspan='5' class='muted'>not opened</td>"
                f"<td>{a.actions if a else 0}</td></tr>"
            )
            continue
        out.append(
            f"<tr><td><a href='{e(link('/activity', claim=cid))}'>{e(cid)}</a></td>"
            f"<td>{a.opened}</td><td class='when'>{e(a.first_at or '')}</td>"
            f"<td class='when'>{e(a.last_at or '')}</td>"
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
    bar = []  # the trail's filter and paging links, as one row of controls
    if claim:
        bar.append("<a href='/activity'>Show every claim</a>")
        if known:
            bar.append(f"<a href='{e(link('/claim', id=claim))}'>Open claim {e(claim)}</a>")
        else:
            bar.append("<span class='muted'>No such claim in this case.</span>")
    if cut:
        more = {"claim": claim} if known else {}
        bar.append(
            f"<span class='muted'>Newest {ACTIVITY_NEWEST} of {len(shown)} shown.</span>"
            f"<a href='{e(link('/activity', all='1', **more))}'>Show all</a>"
        )
    if bar:
        out.append(f"<div class='trailbar'>{''.join(bar)}</div>")
    out.append(
        "<table class='trail'><thead><tr><th>#</th><th>When (UTC)</th><th>Examiner</th>"
        "<th>Page or action</th><th>Item</th><th class='n'>Time on page</th></tr></thead>"
    )
    for s in shown[cut:]:
        when = activity.duration(s.seconds, s.away) if s.is_view else ""
        out.append(
            f"<tr><td>{s.seq}</td><td class='when'>{e(s.at_utc)}</td><td>{e(s.examiner)}</td>"
            f"<td>{e(s.where)}</td><td>{_step_item(s)}</td><td>{e(when)}</td></tr>"
        )
    out.append("</table></div>")
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
    back = (
        "<a class='button' href='/'>Go to the case</a>"
        if page.case_name is not None
        else "<a class='button' href='/cases'>Go to the case list</a>"
    )
    return page.wrap(
        "Error",
        f"<div class='pg-error'><h1>{status}</h1><p class='lede'>{e(message)}</p>"
        f"<p class='actions'>{back}<a href='/help'>Help</a></p></div>",
    )


# ---------------------------------------------------------------- cases


PASSPHRASE_HINT = "At least 12 characters. Mabillon cannot recover a lost passphrase."
LOCK_LABEL = {
    "plain": "Not encrypted",
    "locked": "Encrypted, locked",
    "open": "Encrypted",
    "partial": "Encryption not finished: part of this case is still readable on disk",
    "partial-locked": "Encryption not finished: part of this case is still readable on disk",
}


def _unlock_fields(slug: str) -> str:
    return (
        f"<input type='hidden' name='case' value='{e(slug)}'>"
        "<span class='unlock'><input type='password' name='passphrase' required size='30' "
        "autocomplete='current-password' placeholder='Passphrase or recovery key' "
        "aria-label='Passphrase or recovery key'> "
        "<button type='submit'>Unlock and open</button></span>"
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
    single_blocked: why that database cannot be opened for review (a broken audit log).

    The first screen after install: the case list, then one card to make a case, whose
    "Make the case" is the page's only primary button. The cases folder is one muted line."""
    out = ["<div class='pg-cases'><h1>Cases</h1>"]
    if single is not None:
        out.append(
            f"<p class='lede'>This screen was started on one case database: <span class='mono'>"
            f"{e(single)}</span>. Start <span class='mono'>mabillon serve</span> without "
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
        out.append("</div>")
        return page.wrap("Cases", "".join(out))
    out.append(name_form(page))
    if rows:
        out.append(
            "<table class='caselist'><thead><tr><th>Case</th><th>State</th><th>Encryption</th>"
            "<th><span class='vh'>Open</span></th></tr></thead><tbody>"
        )
        for slug, name, state, lock in rows:
            fields = (
                _unlock_fields(slug)
                if lock in ("locked", "partial-locked")
                else f"<input type='hidden' name='case' value='{e(slug)}'>"
                "<button type='submit'>Open</button>"
            )
            out.append(
                f"<tr><td class='name'>{q(name)}<span class='mono'>{e(slug)}</span></td>"
                f"<td class='state'>{e(state)}</td>"
                f"<td class='lock lock-{e(lock)}'>{e(LOCK_LABEL.get(lock, lock))}</td>"
                "<td class='go'>" + page.form("/case/open", fields, "inline") + "</td></tr>"
            )
        out.append("</tbody></table>")
    else:
        out.append("<p class='empty'>No cases yet.</p>")
    out.append(f"<p class='where'>Cases folder: <span class='mono'>{e(home)}</span></p>")
    out.append(
        "<section class='newcase'><h2>New case</h2>"
        + page.form(
            "/case/new",
            "<p><label>Case name <input type='text' name='name' required maxlength='80' "
            "class='wide'></label></p>"
            "<p><label><input type='checkbox' name='encrypt' value='1' checked> Encrypt with a "
            "passphrase</label></p>"
            "<div class='pass'><div class='passfields'>"
            "<input type='password' name='passphrase' autocomplete='new-password' minlength='12' "
            "placeholder='Passphrase' aria-label='Passphrase'> "
            "<input type='password' name='passphrase2' autocomplete='new-password' "
            "placeholder='The passphrase again' aria-label='The passphrase again'></div>"
            f"<p class='muted'>{e(PASSPHRASE_HINT)} The case name is not encrypted.</p></div>"
            "<button type='submit' class='primary'>Make the case</button>",
        )
        + "</section></div>"
    )
    return page.wrap("Cases", "".join(out))


def name_form(page: Page) -> str:
    if page.expert:
        return ""
    return page.form(
        "/expert",
        "<p><strong>Your name</strong></p><div class='row'><input type='text' name='name' required "
        "maxlength='60' placeholder='Your name' aria-label='Your name'> "
        "<button type='submit'>Continue</button></div>",
        "box nameform",
    )


# ---------------------------------------------------------------- set up and run


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
        "</select></label></p>"
    )


def _upload_form(
    page: Page, kind: str, label: str, accept: str, disabled: bool, hint: str = ""
) -> str:
    """multipart form; the token comes before the file so the server checks it first."""
    off = " disabled" if disabled else ""
    return (
        "<form method='post' action='/case/import' enctype='multipart/form-data' class='box'>"
        f"<input type='hidden' name='token' value='{e(page.token)}'>"
        + page.case_field()
        + f"<input type='hidden' name='kind' value='{e(kind)}'>"
        f"<p><strong>{e(label)}</strong>"
        + (f"<br><span class='muted'>{e(hint)}</span>" if hint else "")
        + "</p>"
        + (_date_order_choice(off) if kind == "report" else "")
        + f"<input type='file' name='file' accept='{e(accept)}' required{off}> "
        f"<button type='submit'{off}>Import</button></form>"
    )


def _step_strip(ready: list, audit_busy: bool, model_ok: bool | None = None) -> str:
    """The five steps as one row of links, each marked done or to do from the readiness checks
    (core.casework.cases.readiness: document, reports, claims, then phone owners if any)."""
    oks = [r.ok for r in ready]
    files = all(oks[:2]) if len(oks) >= 2 else False
    claims = oks[2] if len(oks) >= 3 else False
    people = oks[3] if len(oks) >= 4 else None
    steps = [
        ("files", "Files", files),
        ("claims", "Claims", claims),
        ("owners", "Who used each phone", people),
        ("model", "The model", model_ok),
        ("run", "Run", True if audit_busy else None),
    ]
    items = []
    for n, (anchor, name, ok) in enumerate(steps, 1):
        state = "" if ok is None else (" ok" if ok else " todo")
        note = "" if ok is None else ("Done" if ok else "To do")
        if anchor == "run" and audit_busy:
            note = "Running"
        items.append(
            f"<li class='step{state}'><a href='#{anchor}'><span class='n'>{n}</span>"
            f"<span class='name'>{e(name)}</span>"
            + (f"<span class='state'>{note}</span>" if note else "")
            + "</a></li>"
        )
    return f"<ol class='steps' aria-label='Steps'>{''.join(items)}</ol>"


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
    recovery_unconfirmed: bool = False,
    cloud: object | None = None,  # core.casework.cloud.CloudChoice
    cloud_case: dict | None = None,  # the case's saved cloud settings
    cloud_key: str | None = "",  # None: a key is set up; else why not
    cloud_key_from: str | None = None,  # core.llm.cloud.key_source
    model_ok: bool | None = None,  # the last model check passed, failed, or none ran
    audited: str | None = None,  # the date of the last finished audit, if one finished
) -> str:
    busy = job_kind is not None
    audit_busy = job_kind == "audit"
    out = [
        "<h1>Set up and run</h1>",
        recovery_box(page, recovery_key, recovery_unconfirmed),
        name_form(page),
    ]
    out.append(_step_strip(ready, audit_busy, model_ok))

    # 1. files
    out.append("<h2 id='files'>Files</h2>")
    srcs = sources(conn)
    hashes: list[str] = []
    govdocs = {r[0]: r for r in conn.execute("SELECT source_id, title, doc_kind FROM govdocs")}
    if srcs:
        out.append(
            "<table class='tidy files'><thead><tr><th>File</th><th>What it is</th>"
            "<th>Records</th><th>Imported (UTC)</th></tr></thead>"
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
                ext = {"unknown": ", extraction type not known", "not_applicable": ""}.get(
                    extraction, f", {EXTRACTION.get(extraction, extraction).lower()} extraction"
                )
                what = (
                    f"{e(SOURCE_KIND.get(kind, kind))}{e(ext)}"
                    f"<div class='coverage made-by' title='{e(kind)}, {e(extraction)}'>Made by "
                    f"{e(tool)} {e(tver or '')}</div>"
                )
                fc = tested.for_source(conn, sid)
                what += format_notice(fc) if fc is not None else ""
                cov = e(COVERAGE.get(fidelity, fidelity)) + _import_coverage(conn, sid)
                recs = str(counts.get(sid, 0)) + _records_note(conn, sid, counts.get(sid, 0))
            out.append(
                f"<tr><td>{q(fname)}<br><span class='mono'>{e(sid)}</span></td>"
                f"<td>{what}<div class='coverage'>{cov}</div></td>"
                f"<td class='nowrap'>{recs}</td>"
                f"<td class='when' title='{e(at)}'>{e(at[:19].replace('T', ' '))}</td></tr>"
            )
            hashes.append(f"<tr><td>{q(fname)}</td><td class='mono hash'>{e(sha)}</td></tr>")
        out.append("</table>")
    else:
        out.append("<p class='muted'>No files yet.</p>")
    out.append(
        "<details class='fold'><summary>Hashes and where the copies are kept</summary>"
        "<p class='muted'>Read-only copies in "
        f"<span class='mono'>{e(inputs_folder)}</span>. Your original files are not changed."
        "</p>"
        + (
            "<table class='tidy hashes'><thead><tr><th>File</th><th>SHA-256</th></tr></thead>"
            + "".join(hashes)
            + "</table>"
            if hashes
            else ""
        )
        + "</details>"
    )
    audited = conn.execute("SELECT 1 FROM pipeline_runs LIMIT 1").fetchone() is not None
    if srcs and not audited:
        options = "".join(
            f"<option value='{e(s[0])}'>{e(s[4])}</option>" for s in srcs
        )  # s = (id, kind, fidelity, extraction, file name, ...)
        out.append(
            "<details class='fold' id='remove-file'><summary>Remove a wrongly imported file"
            "</summary><p class='muted'>Only before the first audit. Mabillon's copy and its "
            "records go; your original file is not touched, and the audit log keeps the "
            "removal with the file's SHA-256.</p>"
            + page.form(
                "/case/remove_file",
                f"<label>File <select name='source'>{options}</select></label> "
                "<input type='text' name='reason' required maxlength='500' size='40' "
                "placeholder='Why, in one sentence' aria-label='Why the file is removed'> "
                f"<button type='submit'{' disabled' if busy else ''}>Remove the file</button>",
                back="/setup",
                anchor="files",
            )
            + "</details>"
        )
    has_report = any(s[0] not in govdocs for s in srcs)
    out.append(
        f"<details class='add-files'{'' if has_report else ' open'}><summary>Add a file"
        "</summary><div class='uploads'>"
    )
    out.append(
        _upload_form(
            page,
            "govdoc",
            "Government document (PDF)",
            ".pdf",
            busy,
        )
        + _upload_form(
            page,
            "report",
            "Phone report",
            ".xlsx,.pdf,.ufdr,.zip,.xml",
            busy,
            hint="Cellebrite or Magnet AXIOM. Tested: UFDR report version 7.48 only.",
        )
        + "</div></details>"
    )

    # 2. claims
    out.append("<h2 id='claims'>Claims</h2>")
    claims = {c.id: c for c in pipeline.load_claims(conn, include_removed=True)}
    has_paras = conn.execute("SELECT 1 FROM govdoc_paragraphs LIMIT 1").fetchone() is not None
    if not has_paras:
        out.append("<p class='muted'>Import the government document first.</p>")
    else:
        out.append(
            page.form(
                "/claims/propose",
                "<div class='inline-actions'><button type='submit'"
                + (" disabled" if busy else "")
                + ">"
                "Propose claims with the local model</button>"
                "<a class='button' href='/claim/new'>Add a claim yourself</a></div>"
                "<p class='muted'>Nothing is audited until you accept it.</p>",
                "plain",
                back="/setup",
                anchor="claims",
            )
        )
    if order or any(c.status.value == "removed" for c in claims.values()):
        out.append(
            "<table class='tidy claim-order'><thead><tr><th>#</th><th>Claim</th>"
            "<th>Status</th><th>Text</th><th>Decide</th></tr></thead>"
        )
        for n, cid in enumerate(order, 1):
            c = claims[cid]
            where = _where_short(conn, c.paragraph_id)
            out.append(
                f"<tr id='claim-{e(cid)}'><td class='brief'>{n}</td><td class='brief'>"
                f"<a href='{e(link('/claim', id=cid))}'>"
                f"{e(claim_name(conn, cid, c.paragraph_id))}</a>"
                f"<span class='where'>{e(where)}</span>"
                f"<span class='kind'>{e(c.claim_type.value.replace('_', ' '))}</span></td>"
                f"<td class='brief'>{e(c.status.value)}"
                f"{' (added by the expert)' if c.model_run_id is None else ' (model)'}</td>"
                f"<td>{q(c.text)}</td>"
                f"<td class='decide'>"
                f"{_claim_buttons(page, cid, c.status.value, c.text, audit_busy)}</td></tr>"
            )
        out.append("</table>")
        waiting = [cid for cid in order if claims[cid].status.value == "proposed"]
        if waiting and not audit_busy:
            n_w = len(waiting)
            out.append(
                page.form(
                    "/claims/accept_all",
                    f"<input type='hidden' name='claims' value='{e(','.join(waiting))}'>"
                    "<div class='inline-actions'><button type='submit'>Accept all "
                    f"{n_w} proposed claim{'s' if n_w != 1 else ''} as written</button>"
                    "<span class='muted'>Read them first. Each acceptance is logged under your "
                    "name.</span></div>",
                    "plain",
                    back="/setup",
                    anchor="claims",
                )
            )
        removed = [c for c in claims.values() if c.status.value == "removed"]
        if removed:
            out.append(
                "<div class='removed'><p class='muted'>Removed, not audited.</p><ul>"
                + "".join(
                    f"<li><a href='{e(link('/claim', id=c.id))}'>"
                    f"{e(claim_name(conn, c.id, c.paragraph_id))}</a>"
                    + (
                        ""
                        if audit_busy
                        else page.form(
                            "/claim/edit",
                            f"<input type='hidden' name='claim' value='{e(c.id)}'>"
                            "<button type='submit' name='status' value='accepted'>Put back"
                            "</button>",
                            "inline",
                            "/setup",
                            "claims",
                        )
                    )
                    + "</li>"
                    for c in removed
                )
                + "</ul></div>"
            )

    if has_paras:
        out.append(_events_box(conn, page, audit_busy))

    # 3. owners, then the other people the document names
    out.append("<h2 id='owners'>Who used each phone</h2>")
    out.append(_devices(conn, page, "/setup", heading=False))
    out.append(_identities_step(conn))

    # 4. model and run: the local model first, since every case needs it
    out.append("<h2 id='model'>The model</h2>")
    if cloud is not None:
        out.append("<h3>The local model</h3>")
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
    out.append(f"<p class='muted'>{e(model_note)}</p>")
    out.append(
        page.form(
            "/model/check",
            "<div class='inline-actions'><button type='submit'"
            + (" disabled" if busy else "")
            + ">Check the model now</button></div>",
            "plain",
            back="/setup",
            anchor="model",
        )
    )
    if cloud is not None:
        out.append(
            cloud_section(
                page,
                cloud,
                cloud_case or {},
                cloud_key,
                job_kind == "audit",
                key_from=cloud_key_from,
                encrypted=protection != "plain",
            )
        )
        out.append(
            "<p class='muted'>The local model is still needed with cloud AI: it proposes "
            "claims and fills in assumptions on this computer. Only stance questions go to "
            "the cloud.</p>"
        )

    out.append("<h2 id='run'>Run the audit</h2>")
    blocking = [r for r in ready if not r.ok and r.blocks and r.acknowledge is None]
    out.append(
        "<ul class='ready'>"
        + "".join(
            f"<li class='{'ok' if r.ok else 'todo'}'>"
            f"{'Done' if r.ok else '<strong>To do</strong>'}: {e(r.text)}</li>"
            for r in ready
        )
        + (
            ""
            if model_ok is None
            else "<li class='ok'>Done: the model passed its check.</li>"
            if model_ok
            else "<li class='todo'><strong>To do</strong>: the model failed its check. "
            "See step 4.</li>"
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
        again = ""
        if audited and not resumable:
            start = "Run the full audit again"
            again = (
                f"<p class='muted'>This case was audited on {e(audited)}. Running it again "
                "sends every claim through the model again, for hours; your evidence decisions "
                "are kept. To apply decisions you made since, use Re-run verdicts in the "
                "Verdicts are out of date banner instead (rules only, no model).</p>"
            )
        off = " disabled" if (busy or blocking) else ""
        out.append(
            page.form(
                "/audit/start",
                acks + "<details class='options'><summary>More options</summary>"
                "<div class='checks'><label><input type='checkbox' name='ai_review' value='1'> "
                "Also run the AI reviewer. It sorts evidence and decides nothing.</label>"
                "<label><input type='checkbox' name='label_all' value='1'> Also label claims a "
                "failed check already decides. Their verdict cannot change.</label><label><input "
                "type='checkbox' name='no_challenge' value='1'> Skip the challenge step, code's "
                "search for what undercuts a claim close to supported.</label></div></details>"
                + again
                + "<div class='inline-actions'>"
                f"<button type='submit' class='primary'{off}>{start}</button>"
                "</div>",
                back="/run",
            )
        )
    out.append(encryption_section(page, protection, busy, recovery_key is not None))
    # No refresh while the recovery key is on screen: it must not vanish mid-copy.
    refresh = 10 if busy and recovery_key is None else None
    return page.wrap("Set up and run", "".join(out), refresh=refresh)


def cloud_section(
    page: Page,
    choice: object,
    saved: dict,
    key_problem: str | None,
    busy: bool,
    key_from: str | None = None,
    encrypted: bool = False,
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
        "<details class='fold'><summary>What cloud AI sends, and what it never sends</summary>"
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
        "policy</a>.</p></details>",
        page.form(
            "/cloud/case",
            "<div class='checks'><label><input type='checkbox' name='allowed' value='1'"
            f"{' checked' if allowed else ''}> {e(ATTESTATION)}</label>"
            "<label><input type='checkbox' name='csam' value='1'"
            f"{' checked' if csam else ''}> {e(CSAM_NOTE)} This case then never uses cloud AI."
            "</label></div>"
            f"<div class='inline-actions'><button type='submit'{off}>Save the cloud choice"
            "</button></div>",
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
    # The key form folds away until the case opts in: a local-only case does not need it.
    out.append(f"<details class='fold'{' open' if allowed else ''}><summary>")
    if key_problem is None and key_from == "case":
        out.append(
            "An Anthropic key is saved in this case, encrypted with the case's key.</summary>"
        )
    elif key_problem is None:
        out.append(
            "An Anthropic key is saved on this computer, not encrypted.</summary><p "
            "class='muted'>Every case without a key of its own uses it."
            + (" Save a key below to seal one in this case instead." if encrypted else "")
            + "</p>"
        )
    elif key_problem.startswith("no Anthropic key"):
        out.append(
            "No cloud key yet</summary><p class='muted'>Paste your firm's Anthropic key below.</p>"
        )
    else:
        out.append(f"No usable cloud key</summary><p class='muted'>{e(key_problem)}.</p>")
    out.append(
        page.form(
            "/cloud/key",
            "<div class='inline-actions'><input type='password' name='api_key' required "
            "autocomplete='off' placeholder='sk-ant-...' aria-label='Your Anthropic API key'>"
            f"<button type='submit'{off}>Save the key</button></div><p class='muted'>Your own "
            "key, from your firm's Anthropic account (ask for zero data retention). In an "
            "encrypted case it is saved in the case, encrypted with the case's key; otherwise only "
            "on this "
            "computer, readable by your user account. It is never shown again.</p>",
            back="/setup",
            anchor="cloud",
        )
    )
    if key_problem is None and key_from in ("case", "file"):
        out.append(
            page.form(
                "/cloud/key/remove",
                f"<button type='submit'{off}>Remove the saved key</button>",
                "inline",
                back="/setup",
                anchor="cloud",
            )
        )
    out.append("</details></div>")
    return "".join(out)


def recovery_box(page: Page, key: str | None, unconfirmed: bool = False) -> str:
    if key is None:
        if not unconfirmed:
            return ""
        return (
            "<div class='flash err recovery' id='recovery' role='alert'><p><strong>This case "
            "may have no usable recovery key.</strong> One was made, but Mabillon stopped or the "
            "case was locked before anyone said it was written down. If you did not write it "
            "down, make a new one now: without it, a lost passphrase loses the case. "
            "<a href='/setup#encryption'>Make a new recovery key</a></p></div>"
        )
    return (
        "<div class='flash recovery' id='recovery' role='alert'><h2>Recovery key</h2>"
        "<p><strong>Write down this case's recovery key now.</strong> It opens the case if the "
        "passphrase is lost. Mabillon keeps no copy anywhere: once you press the button below, "
        "it cannot be shown again. Keep it away from this computer (on paper, or in your "
        "password manager). Until then, this case cannot be locked.</p>"
        f"<p class='mono' style='font-size:1.25em'>{e(key)}</p>"
        + page.form(
            "/case/recovery/done",
            "<button type='submit'>I have written it down</button>",
            "inline",
            back="/setup",
        )
        + "</div>"
    )


def encryption_section(page: Page, protection: str, busy: bool, key_shown: bool = False) -> str:
    out = ["<h2 id='encryption'>Encryption</h2>"]
    off = " disabled" if busy else ""
    wait = "<p class='muted'>Wait until the background work finishes.</p>" if busy else ""
    if protection == "plain":
        out.append(
            "<p>This case is <strong>not encrypted</strong>.</p>"
            "<details class='fold'><summary>Encrypt this case</summary>"
            "<p class='muted'>Locks the database and the file copies with a passphrase "
            "(AES-256). One way; it can take a few minutes, so keep this page open.</p>"
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
            + "</details>"
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
        "<p>This case is <strong>encrypted</strong>. It stays unlocked until you lock it or stop "
        "Mabillon.</p>"
        + wait
        + (
            "<p class='muted'>Write down the recovery key at the top of this page before you "
            "lock the case.</p>"
            if key_shown
            else page.form(
                "/case/lock",
                f"<button type='submit'{off}>Lock this case now</button>",
                back="/cases",
            )
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
        + "<h3>Make a new recovery key</h3>"
        + page.form(
            "/case/recovery/new",
            "<p class='muted'>For a lost or never written down recovery key. The new key is "
            "shown once at the top of this page; the old one stops opening the case.</p>"
            "<input type='password' name='passphrase' required size='34' "
            "autocomplete='current-password' placeholder='Passphrase' aria-label='Passphrase'> "
            f"<button type='submit'{off}>Make a new recovery key</button>",
            back="/setup",
            anchor="recovery",
        )
    )
    return "".join(out)


def _events_box(conn: sqlite3.Connection, page: Page, locked: bool) -> str:
    """The events the document defines and claims are dated by ("the SEARCH"), as the expert
    entered them, with a form to add one (core/review/actions.add_event)."""
    from core.audit import case_events

    events = case_events.stored(conn)
    out = [
        # folded, as the page's other optional steps are: most cases need no events
        "<details class='fold' id='events'><summary>Events the document defines"
        f"{f' ({len(events)})' if events else ''}</summary>",
        "<p class='muted'>When the document defines an event and dates later claims by it "
        "(\u201ctwo days before the SEARCH\u201d), enter the event, its day and the words that "
        "define it. The audit reads only a whole day tied to a one-day event: the day of, the "
        "day before or after, or a number of days before or after. Every report lists the "
        "events you entered.</p>",
    ]
    if events:
        out.append(
            "<table><thead><tr><th>Event</th><th>Days</th><th>Where</th><th>Defined as</th>"
            "<th></th></tr></thead>"
        )
        for ev in events:
            days = ev.first_day.isoformat() + (
                "" if ev.one_day else f" to {ev.last_day.isoformat()}"
            )
            remove = (
                "<span class='muted'>Locked while the audit runs.</span>"
                if locked
                else page.form(
                    "/event/remove",
                    f"<input type='hidden' name='name' value='{e(ev.name)}'>"
                    "<button type='submit'>Remove</button>",
                    "inline",
                    "/setup",
                    anchor="events",
                )
            )
            out.append(
                f"<tr><td>{q(ev.name)}</td><td>{e(days)}</td>"
                f"<td>{e(_where_short(conn, ev.paragraph_id))}</td><td>{q(ev.defined_as)}</td>"
                f"<td>{remove}</td></tr>"
            )
        out.append("</table>")
    if locked:
        return "".join(out) + "</details>"
    opts = "".join(
        f"<option value='{e(pid)}'>{e(_where_short(conn, pid))}</option>"
        for (pid,) in conn.execute("SELECT id FROM govdoc_paragraphs ORDER BY page, para_no")
    )
    out.append(
        page.form(
            "/event/add",
            "<label>Event, as the document writes it <input type='text' name='name' "
            "maxlength='120' placeholder='SEARCH' required></label> "
            "<label>First day <input type='date' name='first_day' required></label> "
            "<label>Last day <input type='date' name='last_day'></label> "
            f"<label>Paragraph <select name='paragraph'>{opts}</select></label> "
            "<label>Words that define it, as the paragraph writes them "
            "<textarea name='defined_as' maxlength='2000' rows='2' required></textarea></label> "
            "<button type='submit'>Add event</button>",
            "box",
            "/setup",
            anchor="events",
        )
    )
    return "".join(out) + "</details>"


def _where_short(conn: sqlite3.Connection, paragraph_id: str) -> str:
    r = conn.execute(
        "SELECT page, para_no, label FROM govdoc_paragraphs WHERE id = ?", (paragraph_id,)
    ).fetchone()
    if r is None:
        return "paragraph not found"
    return f"p. {r[0]}, para {r[2] if r[2] else '#' + str(r[1])}"


def _claim_buttons(page: Page, cid: str, status: str, text: str, locked: bool) -> str:
    """Accept, move up, move down and Remove sit on one row; Edit the wording opens below."""
    if locked:
        return "<span class='muted'>Locked while the audit runs.</span>"
    hidden = f"<input type='hidden' name='claim' value='{e(cid)}'>"
    accept = (
        ""
        if status in ("accepted", "edited")
        else "<button type='submit' name='status' value='accepted'>Accept</button>"
    )
    return (
        "<div class='claim-actions'>"
        + (
            page.form("/claim/edit", hidden + accept, "inline", "/setup", f"claim-{cid}")
            if accept
            else ""
        )
        + page.form(
            "/claims/move",
            hidden + "<button type='submit' name='delta' value='-1' aria-label='Move up' "
            "title='Move up'>↑</button>"
            "<button type='submit' name='delta' value='1' aria-label='Move down' "
            "title='Move down'>↓</button>",
            "inline",
            "/setup",
            f"claim-{cid}",
        )
        # A removed claim leaves the table, so its form comes back to the section instead.
        + page.form(
            "/claim/edit",
            hidden + "<button type='submit' name='status' value='removed'>Remove</button>",
            "inline",
            "/setup",
            "claims",
        )
        + "</div><details><summary>Edit the wording</summary>"
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
    check_failed = False  # the job's model check failed: its lines already say what to do
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
                    "<button type='submit'>Stop after the current claim</button>",
                    back="/run",
                )
            )
        else:
            cls = "flash" if getattr(job, "state", "") == "done" else "flash err"
            check = getattr(job, "check", None)
            if check is not None and not check.ok:
                # One message: the check's own lines say what failed and what to do.
                check_failed = True
                out.append(
                    f"<div class='{cls}'>The audit did not start: the model failed its check. "
                    "Nothing was labeled.</div><ul>"
                    + "".join(
                        f"<li>{'<strong>' if lvl == 'fail' else ''}{e(m)}"
                        f"{'</strong>' if lvl == 'fail' else ''}</li>"
                        for lvl, m in check.lines
                    )
                    + "</ul><p><a href='/setup#model'>Check the model again on Set up</a> once "
                    "it is fixed, then start the audit.</p>"
                )
            else:
                out.append(f"<div class='{cls}'>{e(getattr(job, 'message', ''))}</div>")
    if run is None:
        if not running and not check_failed:
            out.append("<p>No audit has run on this case. <a href='/setup'>Set up and run</a>.</p>")
        return page.wrap("Audit progress", "".join(out), refresh=5 if running else None)
    out.append(
        f"<p>Run <span class='mono'>{e(run['id'])}</span>, started {e(run['started_at_utc'])}, "
        f"status <strong>{e(run['status'])}</strong>."
        + (f" <span class='muted'>Note: {e(run['note'])}.</span>" if run.get("note") else "")
        + "</p>"
    )
    if not running and run["status"] != "completed":
        out.append(
            "<p>This audit did not finish. Finished claims are kept. "
            "<a href='/setup'>Resume it</a></p>"
        )
    view = pipeline.view_run(conn)
    labels = {}
    if view is not None and view["run_id"] == run["id"]:
        labels = {st.claim.id: st for st in claim_states(conn, run=view)}
    if not labels:
        out.append(
            "<p class='muted'>Findings show here and on Claims once this run is the one on "
            "screen.</p>"
        )
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
            finding = ""
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
