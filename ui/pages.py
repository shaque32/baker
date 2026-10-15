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
from core.audit.context import build_context
from core.contracts import (
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
from core.report.html import CSS as REPORT_CSS
from core.report.html import (
    STANCE_LABEL,
    audit_log_summary,
    labelled_by,
    record_line,
    review_label,
    said,
    sources,
    stand_in_banner,
)
from core.report.hypotheses import CSS as ALTERNATIVES_CSS
from core.report.hypotheses import alternatives_html
from core.report.restore import CSS as RESTORE_CSS
from core.report.selection import CSS as SELECTION_CSS
from core.report.selection import anchor as selection_anchor
from core.report.selection import claim_note
from core.review.status import (
    AGAINST,
    HOLDINGS,
    ClaimState,
    case_holdings,
    claim_name,
    claim_state,
    claim_states,
    queue,
)
from core.selection.audit import selection_audit
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
        tabs = [("/cases", "Cases")] if self.many_cases else []
        if self.case_name is not None:
            tabs += [
                ("/", "Case"),
                ("/claims", "Claims queue"),
                ("/claim/new", "Add a claim"),
                ("/identities", "Identities"),
                ("/exhibits", "Exhibits"),
                ("/selection", "Selection"),
                ("/timeline", "Timeline"),
                ("/gaps", "Gaps"),
                ("/report", "Report"),
                ("/log", "Audit log"),
                ("/setup", "Set up and run"),
            ]
        links = "".join(
            f"<a href='{href}'{' class=on' if _tab(self.path) == href else ''}>{label}</a>"
            for href, label in tabs
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
            f"<title>{e(title)} · Baker</title>"
            f"<style>{FONT_CSS}{REPORT_CSS}{RESTORE_CSS}{SELECTION_CSS}{ALTERNATIVES_CSS}{UI_CSS}{THEME_CSS}</style>"
            "</head><body>"
            "<header class='top'><div class='bar'>"
            f"<a class='brand' href='{'/' if self.case_name is not None else '/cases'}'>"
            f"{MARK}<span>Baker</span></a>{case}<div class='right'>"
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
            what.append(f"{later} evidence decision(s)")
        if stips:
            what.append(f"{stips} stipulation change(s)")
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

    out.append("<h2>Government documents</h2>")
    if govdocs:
        out.append("<ul>" + "".join(f"<li>{q(t)} ({e(k)})</li>" for _, t, k in govdocs) + "</ul>")
    else:
        out.append("<p class='muted'>None imported.</p>")

    out.append(
        "<h2>Sources</h2><table><thead><tr><th>File</th><th>Kind</th><th>Coverage</th>"
        "<th>Extraction</th><th>SHA-256</th><th>Tool</th><th>Imported (UTC)</th></tr></thead>"
    )
    for s in srcs:
        out.append(
            f"<tr><td>{q(s[4])}<br><span class='mono'>{e(s[0])}</span></td><td>{e(s[1])}</td>"
            f"<td>{e(s[2])}</td><td>{e(s[3])}</td><td class='mono'>{e(s[5])}</td>"
            f"<td>{e(s[6])} {e(s[7])}</td><td>{e(s[8])}</td></tr>"
        )
    out.append("</table>")

    out.append(_devices(conn, page, "/"))

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
            f"{e(run['started_at_utc'])}, rule version {e(run['rule_version'])}, contracts "
            f"{e(run['contracts_version'])}.</p>"
        )
        states = claim_states(conn, run=run)
        tally = Counter(st.label for st in states)
        out.append("<table><thead><tr><th>Finding</th><th>Claims</th></tr></thead>")
        for label, n in sorted(tally.items()):
            out.append(f"<tr><td>{e(label)}</td><td>{n}</td></tr>")
        out.append("</table>")
        waiting = sum(1 for st in states if st.needs() and st.priority <= 4)
        out.append(
            f"<p><a href='/claims'>{waiting} claim(s) need you</a>. Accepting or dismissing "
            "evidence does not change a verdict until you re-run the verdicts.</p>"
        )
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
    summary = audit_log_summary(conn)
    out.append(
        f"<h2>Audit log</h2><p>{summary['entries']} entries. Hash chain "
        f"{'verified' if summary['chain_ok'] else '<strong>FAILED VERIFICATION</strong>'}. "
        "<a href='/log'>Open the log</a>.</p>"
    )
    return page.wrap("Case", "".join(out), run_banner(conn, page, "/"))


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
    out = [
        ("<h2>Devices and stipulations</h2>" if heading else "")
        + "<p>Who used each phone is a stipulation you make, not "
        "a finding. Every report lists it as a limitation.</p>"
        "<table><thead><tr><th>Device</th><th>Source</th><th>Stipulated user</th>"
        "<th>Change</th></tr></thead>"
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
        out.append(
            f"<tr id='dev-{e(dev_id)}'><td>{q(label)} <span class='mono'>{e(dev_id)}</span><br>"
            f"{q(model or '')}</td>"
            f"<td class='mono'>{e(source_id)}</td><td>{who}</td><td>{change}</td></tr>"
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
    known = {"v-sup", "v-con", "v-unp", "v-await"}
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
            f"{e(st.claim.claim_type.value)}</span>"
            f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span></div>"
            f"<div class='text'>{q(st.claim.text)}</div>"
            + (f"<div class='needs'>{e(needs)}</div>" if needs else "")
            + "</div></li>"
        )
    return f"<ul class='ledger'>{''.join(rows)}</ul>"


def claims_queue(conn: sqlite3.Connection, page: Page) -> str:
    states = queue(conn)
    out = [
        "<div class='eyebrow'>Claims ledger</div>"
        "<h1>Claims queue</h1><p class='muted'>Sorted by what needs you most. AI-accepted "
        "evidence is a sorting aid: no claim becomes supported until you accept its key evidence "
        "and re-run the verdicts.</p>",
        _tally(states),
        _ledger(states),
    ]
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


def evidence_card(
    conn: sqlite3.Connection, page: Page, item: EvidenceItem, last_kind: str | None, back: str
) -> str:
    stance_cls = "b-against" if item.stance in AGAINST else "b-open"
    return (
        f"<div class='item' id='{e(item.id)}'>"
        f"<span class='badge {stance_cls}'>{e(STANCE_LABEL[item.stance])}</span>"
        f"{_tier_badge(item, last_kind)}"
        f"<blockquote>{q(item.quote)}</blockquote>"
        f"<p>{record_line(conn, item.record_id)}<br>"
        f"<span class='mono'>{e(item.ref.source_id)} {e(item.ref.locator)} · "
        f"{e(item.record_id)}</span></p>"
        f"<p class='muted'>{e(labelled_by(conn, item.model_run_id))}. Model rationale "
        f"(inferred): {e(item.rationale)}</p>"
        f"<p><strong>Review:</strong> {review_label(conn, item)} · "
        f"<a href='{e(link('/evidence', id=item.id))}'>See about 20 messages around it</a></p>"
        f"{_decide_form(page, item, last_kind == 'expert', back)}</div>"
    )


def _groups(st: ClaimState) -> list[tuple[str, list[EvidenceItem]]]:
    groups: dict[str, list[EvidenceItem]] = {
        "AI-accepted, awaiting your decision": [],
        "Supporting, not reviewed": [],
        "Contradicting or complicating": [],
        "Dismissed by the AI reviewer, not reviewed by you": [],
        "Decided by an expert": [],
    }
    for x in st.evidence:
        if x.stance == Stance.IRRELEVANT:
            continue
        by_expert = st.last_reviewer.get(x.id) == "expert" and x.status != EvidenceStatus.OPEN
        if by_expert:
            groups["Decided by an expert"].append(x)
        elif x.stance in AGAINST:
            groups["Contradicting or complicating"].append(x)
        elif x.status == EvidenceStatus.AI_ACCEPTED:
            groups["AI-accepted, awaiting your decision"].append(x)
        elif x.status == EvidenceStatus.DISMISSED:
            groups["Dismissed by the AI reviewer, not reviewed by you"].append(x)
        else:
            groups["Supporting, not reviewed"].append(x)
    return [(k, v) for k, v in groups.items() if v]


def _selection_note(conn: sqlite3.Connection, paragraph_id: str) -> str:
    """What the selection audit found around the quotes of the claim's paragraph, if anything."""
    audit = selection_audit(conn, paragraph_id=paragraph_id)
    units = audit.of("document")
    if not units:
        return ""
    return claim_note(units[0], f"/selection#{selection_anchor(units[0].id)}", audit.same) or ""


def claim_page(conn: sqlite3.Connection, page: Page, claim_id: str) -> str | None:
    st = claim_state(conn, claim_id)
    if st is None:
        return None
    back = link("/claim", id=claim_id)
    c, d = st.claim, st.decision
    out = [
        "<div class='claim-head'>"
        f"<h1>{e(st.name)} <span class='muted'>· {e(st.where)} · {e(c.claim_type.value)} · "
        f"claim {e(c.status.value)}"
        f"{' by the expert' if c.model_run_id is None else ' (model-proposed)'}</span></h1>"
        f"<span class='mono muted'>Claim id {e(c.id)}</span></div>",
        f"<blockquote class='claimtext'>{q(c.text)}</blockquote>",
    ]
    if st.paragraph_text:
        out.append(
            f"<details><summary>Paragraph as printed ({e(st.where)})</summary>"
            f"<blockquote>{q(st.paragraph_text)}</blockquote></details>"
        )
        out.append(_selection_note(conn, c.paragraph_id))
    out.append(
        "<div class='card' id='verdict'><div class='in'><div class='eyebrow'>Verdict</div>"
        f"<span class='verdict {_vcls(st)}'>{e(st.label)}</span>"
    )
    needs = st.needs()
    if needs:
        out.append("<ul>" + "".join(f"<li>{e(t)}</li>" for _, t in needs) + "</ul>")
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
        out.append(f"</div><div class='in'>{_verdict_forms(page, st, back)}")
    out.append("</div></div>")
    out.append(_alternatives(conn, st))

    coverage = {cv.assumption_id: cv for cv in (d.coverage if d else ())}
    if st.assumptions:
        out.append(
            "<h2>Assumptions</h2><table><thead><tr><th>Assumption</th><th>Kind</th><th>Core</th>"
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
            "<h2>Checks</h2><table><thead><tr><th>Check</th><th>Outcome</th>"
            "<th>What was searched</th><th>Detail</th></tr></thead>"
        )
        for ch in st.checks:
            out.append(
                f"<tr><td>{e(ch.check_name)} {e(ch.check_version)}</td>"
                f"<td>{e(ch.outcome.value)}</td><td>{e(ch.searched)}</td><td>{e(ch.detail)}</td>"
                "</tr>"
            )
        out.append("</table>")

    out.append("<h2>Evidence</h2>")
    if st.unlabeled:
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
    groups = _groups(st)
    if not groups:
        out.append("<p class='muted'>No relevant evidence items were stored for this claim.</p>")
    by_assumption = {a.id: a for a in st.assumptions}
    for title, group in groups:
        out.append(f"<h3>{e(title)} ({len(group)})</h3>")
        shown_on = None
        order = {a.id: i for i, a in enumerate(st.assumptions)}
        for x in sorted(group, key=lambda x: order.get(x.assumption_id, len(order))):
            a = by_assumption.get(x.assumption_id)
            if a is not None and a.id != shown_on:
                out.append(f"<p class='muted'>Assumption: {e(a.text)}</p>")
                shown_on = a.id
            out.append(evidence_card(conn, page, x, st.last_reviewer.get(x.id), back))
    hidden = sum(1 for x in st.evidence if x.stance == Stance.IRRELEVANT)
    if hidden:
        out.append(f"<p class='muted'>{hidden} retrieved records were labeled irrelevant.</p>")

    out.append(_edit_claim_form(page, st, back))
    states = claim_states(conn)
    side = (
        f"<aside class='side'><div class='eyebrow'>Claims ledger <span>{len(states)} claims"
        f"</span></div>{_tally(states)}{_ledger(states, c.id, compact=True)}</aside>"
    )
    body = f"<div class='split'>{side}<div>{''.join(out)}</div></div>"
    return page.wrap(st.name, body, run_banner(conn, page, back), wide=True)


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
    out.append(evidence_card(conn, page, item, last_kind[0] if last_kind else None, back))
    out.append("<h2>Context</h2>")
    lines = build_context(conn, item.record_id, CONTEXT_WINDOW)
    if lines:
        out.append(
            "<p class='muted'>Messages around the record, in time order. Times are the phone's "
            "local time. The record under review is highlighted.</p><div class='thread'>"
        )
        for ln in lines:
            shown = f" (shown as {q(ln.shown_as)})" if ln.shown_as else ""
            side = " out" if ln.direction == "outgoing" else ""
            tag = "<span class='cited'>UNDER REVIEW</span>" if ln.is_target else ""
            out.append(
                f"<div class='msg{side}{' target' if ln.is_target else ''}'>"
                f"<div class='who2'>{q(ln.sender)}{shown} · {e(ln.direction)}</div>"
                f"<div class='body'>{q(ln.body)}</div>"
                f"<div class='t'>{tag}{e(ln.local_time)}</div></div>"
            )
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
                f"<td>{said(reason) if kind == 'expert' else e(reason)}</td><td>{e(at)}</td></tr>"
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
            f"<p>Claim id <input type='text' name='id' required maxlength='20' value='C{n:02d}'>"
            f" Type <select name='type'>{types}</select></p>"
            f"<p>Paragraph<br><select name='paragraph'>{opts}</select></p>"
            "<p>Claim text, as the document states it<br>"
            "<textarea name='text' rows='4' required></textarea></p>"
            "<button type='submit'>Add claim</button> <span class='muted'>A new claim needs a "
            "full audit before it has a verdict.</span>",
        )
    return page.wrap("Add a claim", body)


# ---------------------------------------------------------------- audit log


def log_page(conn: sqlite3.Connection, page: Page, show_all: bool) -> str:
    summary = audit_log_summary(conn)
    rows: Iterable[tuple] = conn.execute(
        "SELECT seq, at_utc, actor, action, payload_json, hash FROM audit_log"
        " ORDER BY seq DESC LIMIT ?",
        (-1 if show_all else 200,),
    )
    status = (
        "<div class='flash'>Hash chain verified: every entry matches the hash of the one before."
        "</div>"
        if summary["chain_ok"]
        else "<div class='flash err'><strong>Hash chain FAILED VERIFICATION.</strong> The log "
        "was changed outside Baker.</div>"
    )
    out = [
        "<h1>Audit log</h1>",
        status,
        f"<p>{summary['entries']} entries. Last hash <span class='mono'>"
        f"{e(summary['last_hash'])}</span>. "
        + ("" if show_all else "Newest 200 shown. <a href='/log?all=1'>Show all</a>.")
        + "</p>",
        "<table><thead><tr><th>#</th><th>When (UTC)</th><th>Actor</th><th>Action</th>"
        "<th>Details</th></tr></thead>",
    ]
    for seq, at, actor, action, payload, _h in rows:
        out.append(
            f"<tr><td>{seq}</td><td>{e(at)}</td><td>{e(actor)}</td><td>{e(action)}</td>"
            f"<td class='mono'>{q(_short(payload))}</td></tr>"
        )
    out.append("</table>")
    return page.wrap("Audit log", "".join(out))


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
    "At least 12 characters; a few words is easiest. Baker cannot recover a lost passphrase: "
    "keep it, or the recovery key Baker shows next, somewhere safe."
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
) -> str:
    """rows: (folder name, case name, one-line state, lock state: plain | locked | open).
    single: the database path when the screen was started on one case database (`--db`),
    which has no cases folder; single_locked when that database is encrypted and locked."""
    out = ["<h1>Cases</h1>"]
    if single is not None:
        out.append(
            f"<p>This screen was started on one case database: <span class='mono'>{e(single)}"
            "</span>. Start <span class='mono'>baker serve</span> without "
            "<span class='mono'>--db</span> to make and open cases in a cases folder.</p>"
        )
        if single_locked:
            out.append(name_form(page))
            out.append(
                "<p>This case is encrypted and locked.</p>"
                + page.form("/case/open", _unlock_fields(""))
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
            "<input type='text' name='name' required maxlength='80' class='wide' "
            "placeholder='Case name, for example: United States v. Petrov (synthetic)'><br>"
            "<label><input type='checkbox' name='encrypt' value='1' checked> Encrypt this case "
            "with a passphrase (recommended)</label><br>"
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
        "<option value=''>let Baker work it out</option>"
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
                cov = e(FIDELITY.get(fidelity, fidelity)) + _import_coverage(conn, sid)
                recs = str(counts.get(sid, 0))
            out.append(
                f"<tr><td>{q(fname)}<br><span class='mono'>{e(sid)}</span></td><td>{what}</td>"
                f"<td>{cov}</td><td>{recs}</td><td class='mono'>{e(sha)}</td><td>{e(at)}</td></tr>"
            )
        out.append("</table>")
    else:
        out.append("<p class='muted'>No files yet.</p>")
    out.append(
        "<p class='muted'>Each file is copied into "
        f"<span class='mono'>{e(inputs_folder)}</span>, made read-only and SHA-256 hashed; Baker "
        "reads only the copy, and the hash of what it parsed must match the hash of what it "
        "received. Your original file is not changed.</p>"
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
            "Phone report: Cellebrite (Excel .xlsx, PDF, or UFDR package .ufdr, unverified) "
            "or Magnet AXIOM (XML or Excel export, unverified)",
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
                f"<td>{e(where)}</td><td>{e(c.claim_type.value)}</td><td>{e(c.status.value)}"
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
                "their verdict cannot change).</label></p>"
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
        f"<p><strong>{'Cloud first' if use else 'Local only'}.</strong> {e(why)}</p>",
        "<p class='muted'>With cloud AI, Baker sends one question at a time to Anthropic under "
        "your own key: the assumption being tested, one record, the messages around it, the "
        "claim, and for a group chat its member list (up to 20 accounts, with the names you "
        "confirmed for them). Never your files or the case database. The cloud model only "
        "labels evidence; the verdict rules and your review are unchanged. Any call it cannot "
        "answer goes to the local model, and each evidence item says which model labeled it."
        "</p>",
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
            "key, from your firm's Anthropic account (ask for zero data retention). It is saved "
            "only on this computer, readable by your user account, and never shown again.</span>",
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
        "now.</strong> It opens the case if the passphrase is lost. Baker shows it only this "
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
        "lock it or stop Baker.</p>"
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
