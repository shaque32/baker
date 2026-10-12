"""Server-rendered pages of the expert review screen. Pure functions of the case database.

No JavaScript, no external fonts, styles or images: every page is one HTML document with an
inline style block. Cited text (government document, claim text, evidence quotes, record text)
goes through q() so the forbidden-word check can tell it from the tool's own words.

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
from core.report.html import CSS as REPORT_CSS
from core.report.html import STANCE_LABEL, audit_log_summary, record_line, review_label, sources
from core.review.status import AGAINST, ClaimState, claim_state, claim_states, queue

CONTEXT_WINDOW = 10  # messages either side: about 20 messages of context

UI_CSS = """
nav { font: 14px Helvetica, Arial, sans-serif; border-bottom: 1px solid var(--line);
  padding-bottom: 8px; margin-bottom: 8px; display: flex; flex-wrap: wrap; gap: 14px;
  align-items: baseline; }
nav a { color: var(--fg); } nav .who { margin-left: auto; color: var(--muted); }
.flash { padding: 10px 12px; border: 1px solid var(--line); margin: 10px 0;
  font-family: Helvetica, Arial, sans-serif; }
.flash.err { border: 2px solid var(--con); }
form.inline { display: inline; }
form.box { border: 1px solid var(--line); padding: 10px 12px; margin: 10px 0;
  background: var(--panel); font-family: Helvetica, Arial, sans-serif; font-size: 13px; }
input[type=text], textarea, select { font: 14px Helvetica, Arial, sans-serif; padding: 4px;
  max-width: 100%; box-sizing: border-box; }
input[type=text].wide, textarea { width: 100%; }
button { font: 13px Helvetica, Arial, sans-serif; padding: 4px 10px; margin: 4px 4px 0 0;
  cursor: pointer; }
.item { border: 1px solid var(--line); padding: 8px 12px; margin: 10px 0; }
.badge { display: inline-block; font: bold 11px Helvetica, Arial, sans-serif; padding: 1px 6px;
  border: 1px solid currentColor; margin-right: 6px; }
.b-ai { color: var(--supai); } .b-conf { color: var(--sup); } .b-open { color: var(--unp); }
.b-against { color: var(--con); }
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
    ):
        self.token = token
        self.expert = expert
        self.flash = flash
        self.case_name = case_name
        self.notice = notice  # HTML from the app, shown on every page while a job runs
        self.busy = busy  # an audit is running: no re-run of the verdicts
        self.many_cases = many_cases  # the screen was started on a cases folder

    def form(self, action: str, body: str, cls: str = "box", back: str = "") -> str:
        return (
            f'<form method="post" action="{e(action)}" class="{cls}">'
            f'<input type="hidden" name="token" value="{e(self.token)}">'
            + (f'<input type="hidden" name="next" value="{e(back)}">' if back else "")
            + body
            + "</form>"
        )

    def wrap(self, title: str, body: str, banner: str = "", refresh: int | None = None) -> str:
        who = (
            f"Reviewing as <strong>{e(self.expert)}</strong>"
            if self.expert
            else "<strong>Enter your name on the case page before reviewing.</strong>"
        )
        flash = ""
        if self.flash:
            msg, err = self.flash
            flash = f'<div class="flash{" err" if err else ""}">{e(msg)}</div>'
        meta = f"<meta http-equiv='refresh' content='{int(refresh)}'>" if refresh else ""
        cases = "<a href='/cases'>Cases</a>" if self.many_cases else ""
        if self.case_name is None:
            links = cases
        else:
            links = (
                f"{cases}<a href='/setup'>Set up and run</a><a href='/'>Case</a>"
                "<a href='/claims'>Claims queue</a><a href='/claim/new'>Add a claim</a>"
                "<a href='/report'>Report</a><a href='/log'>Audit log</a>"
                f"<span class='muted'>{q(self.case_name)}</span>"
            )
        notice = f"<div class='flash'>{self.notice}</div>" if self.notice else ""
        return (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width, initial-scale=1'>{meta}"
            f"<title>{e(title)} · Baker</title><style>{REPORT_CSS}{UI_CSS}</style></head><body>"
            f"<nav><strong>Baker</strong>{links}<span class='who'>{who}</span></nav>"
            f"{notice}{flash}{banner}{body}</body></html>"
        )


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
        out.append(
            "<div class='banner'><strong>Test run with stand-in components.</strong> The "
            "evidence on this case came from eval stand-ins, not the real labeler. Nothing here "
            "is a finding.</div>"
        )
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
            + page.form("/redecide", "<button type='submit'>Re-run verdicts</button>", "", back)
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
                "maxlength='60' placeholder='Your name'> <button type='submit'>Start reviewing"
                "</button>",
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

    out.append("<h2>Audit</h2>")
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
                    "<button type='submit'>Re-run verdicts (rules only, no model)</button>",
                    back="/",
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
        )
        out.append(
            f"<tr><td>{q(label)} <span class='mono'>{e(dev_id)}</span><br>{q(model or '')}</td>"
            f"<td class='mono'>{e(source_id)}</td><td>{who}</td><td>{change}</td></tr>"
        )
    out.append("</table>")
    if not devices:
        out.append("<p class='muted'>No devices imported.</p>")
    return "".join(out)


# ---------------------------------------------------------------- queue


def claims_queue(conn: sqlite3.Connection, page: Page) -> str:
    states = queue(conn)
    out = [
        "<h1>Claims queue</h1><p>Sorted by what needs you most. AI-accepted evidence is a "
        "sorting aid: no claim becomes supported until you accept its key evidence and re-run "
        "the verdicts.</p>",
        "<table><thead><tr><th>Claim</th><th>Where</th><th>Type</th><th>Finding</th>"
        "<th>What it needs</th></tr></thead>",
    ]
    for st in states:
        needs = st.needs()
        what = "<br>".join(e(t) for _, t in needs) or "<span class='muted'>Nothing. Done.</span>"
        out.append(
            f"<tr><td><a href='{e(link('/claim', id=st.claim.id))}'>{e(st.claim.id)}</a></td>"
            f"<td>{e(st.where)}</td><td>{e(st.claim.claim_type.value)}</td>"
            f"<td><span class='verdict {st.css}'>{e(st.label)}</span></td><td>{what}</td></tr>"
        )
    out.append("</table>")
    removed = [c for c in pipeline.load_claims(conn, include_removed=True) if c.status == "removed"]
    if removed:
        out.append(
            "<p class='muted'>Removed claims: "
            + ", ".join(f"<a href='{e(link('/claim', id=c.id))}'>{e(c.id)}</a>" for c in removed)
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
        f"<p class='muted'>Model rationale (inferred): {e(item.rationale)}</p>"
        f"<p><strong>Review:</strong> {e(review_label(conn, item))} · "
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


def claim_page(conn: sqlite3.Connection, page: Page, claim_id: str) -> str | None:
    st = claim_state(conn, claim_id)
    if st is None:
        return None
    back = link("/claim", id=claim_id)
    c, d = st.claim, st.decision
    out = [
        f"<h1>{e(c.id)} <span class='muted'>· {e(st.where)} · {e(c.claim_type.value)} · "
        f"claim {e(c.status.value)}"
        f"{' by the expert' if c.model_run_id is None else ' (model-proposed)'}</span></h1>",
        f"<blockquote>{q(c.text)}</blockquote>",
    ]
    if st.paragraph_text:
        out.append(
            f"<details><summary>Paragraph as printed ({e(st.where)})</summary>"
            f"<blockquote>{q(st.paragraph_text)}</blockquote></details>"
        )
    out.append(f"<p><span class='verdict {st.css}'>{e(st.label)}</span></p>")
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
            note = f" Note: {e(d.override_note)}" if d.override_note else ""
            kind = "overrode" if d.override_note is not None else "confirmed"
            out.append(f"<p>{e(d.confirmed_by)} {kind} this verdict.{note}</p>")
        out.append(_verdict_forms(page, st, back))

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
    return page.wrap(c.id, "".join(out), run_banner(conn, page, back))


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
        )
        + "<p class='muted'>A confirmation or override applies to this run's verdict. After "
        "re-running the verdicts, confirm again.</p></details>"
    )


def _edit_claim_form(page: Page, st: ClaimState, back: str) -> str:
    cid = e(st.claim.id)
    return (
        "<h2>Edit this claim</h2>"
        + page.form(
            "/claim/edit",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<input type='hidden' name='status' value='edited'>"
            f"<textarea name='text' rows='3' required>{e(st.claim.text)}</textarea><br>"
            "<button type='submit'>Save new wording</button> <span class='muted'>A changed "
            "claim needs a full audit.</span>",
            back=back,
        )
        + page.form(
            "/claim/edit",
            f"<input type='hidden' name='claim' value='{cid}'>"
            "<button type='submit' name='status' value='accepted'>Accept as written</button>"
            "<button type='submit' name='status' value='removed'>Remove this claim</button>",
            back=back,
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
            "SELECT seq, reviewer, status, reason, decided_at_utc FROM evidence_reviews"
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
            "local time. The record under review is in bold.</p><table class='ctx'><thead><tr>"
            "<th>Local time</th><th>Sender</th><th>Direction</th><th>Text</th></tr></thead>"
        )
        for ln in lines:
            shown = f"<br>shown as {q(ln.shown_as)}" if ln.shown_as else ""
            out.append(
                f"<tr{' class=target' if ln.is_target else ''}><td>{e(ln.local_time)}</td>"
                f"<td>{q(ln.sender)}{shown}</td><td>{e(ln.direction)}</td><td>{q(ln.body)}</td>"
                "</tr>"
            )
        out.append("</table>")
    else:
        out.append("<p class='muted'>No surrounding messages for this kind of record.</p>")
    out.append("<h2>Review history</h2>")
    if history:
        out.append(
            "<table><thead><tr><th>#</th><th>Reviewer</th><th>Status</th><th>Reason</th>"
            "<th>When (UTC)</th></tr></thead>"
            + "".join(
                f"<tr><td>{s}</td><td>{e(who)}</td><td>{e(status)}</td><td>{e(reason)}</td>"
                f"<td>{e(at)}</td></tr>"
                for s, who, status, reason, at in history
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


def cases_page(
    page: Page, home: object, rows: list[tuple[str, str, str]], single: str | None
) -> str:
    """rows: (folder name, case name, one-line state). single: the database path when the screen
    was started on one case database (`--db`), which has no cases folder."""
    out = ["<h1>Cases</h1>"]
    if single is not None:
        out.append(
            f"<p>This screen was started on one case database: <span class='mono'>{e(single)}"
            "</span>. Start <span class='mono'>baker serve</span> without "
            "<span class='mono'>--db</span> to make and open cases in a cases folder.</p>"
        )
        return page.wrap("Cases", "".join(out))
    out.append(name_form(page))
    out.append(
        f"<p>Cases folder: <span class='mono'>{e(home)}</span>. Each case is a folder with its "
        "own database and read-only copies of its files.</p>"
    )
    if rows:
        out.append("<table><thead><tr><th>Case</th><th>State</th><th></th></tr></thead>")
        for slug, name, state in rows:
            out.append(
                f"<tr><td>{q(name)}<br><span class='mono'>{e(slug)}</span></td><td>{e(state)}</td>"
                "<td>"
                + page.form(
                    "/case/open",
                    f"<input type='hidden' name='case' value='{e(slug)}'>"
                    "<button type='submit'>Open</button>",
                    "inline",
                )
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
            "<button type='submit'>Make the case</button>",
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
    "unknown": "not stated",
}


def _upload_form(page: Page, kind: str, label: str, accept: str, disabled: bool) -> str:
    """multipart form; the token comes before the file so the server checks it first."""
    off = " disabled" if disabled else ""
    return (
        "<form method='post' action='/case/import' enctype='multipart/form-data' class='box'>"
        f"<input type='hidden' name='token' value='{e(page.token)}'>"
        f"<input type='hidden' name='kind' value='{e(kind)}'>"
        f"<p><strong>{e(label)}</strong></p>"
        f"<input type='file' name='file' accept='{e(accept)}' required{off}> "
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
) -> str:
    busy = job_kind is not None
    audit_busy = job_kind == "audit"
    out = ["<h1>Set up and run</h1>", name_form(page)]
    out.append(
        "<p>Four steps: import the files, settle the claims, confirm who used each phone, then "
        "run the audit. It runs in the background; you can review each claim as soon as it is "
        "labeled.</p>"
    )

    # 1. files
    out.append("<h2>1. Files</h2>")
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
                cov = e(FIDELITY.get(fidelity, fidelity))
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
        + _upload_form(page, "report", "Cellebrite report (Excel .xlsx or PDF)", ".xlsx,.pdf", busy)
    )

    # 2. claims
    out.append("<h2>2. Claims</h2>")
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
                f"<tr><td>{n}</td><td><a href='{e(link('/claim', id=cid))}'>{e(cid)}</a></td>"
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
                    f"<a href='{e(link('/claim', id=c.id))}'>{e(c.id)}</a>" for c in removed
                )
                + ". Open one to accept it again.</p>"
            )

    # 3. owners
    out.append("<h2>3. Who used each phone</h2>")
    out.append(_devices(conn, page, "/setup", heading=False))

    # 4. model and run
    out.append("<h2>4. The model</h2>")
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
            "<button type='submit'" + (" disabled" if busy else "") + ">Check the model now"
            "</button> <span class='muted'>Finds the model file, checks its SHA-256 against the "
            "config and checks this computer's memory. The audit also does this first.</span>",
            back="/setup",
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
                f"<button type='submit'{off}>{start}</button> <span class='muted'>Keeps this "
                "computer awake while it runs. You can stop it; finished claims are kept.</span>",
                back="/run",
            )
        )
    return page.wrap("Set up and run", "".join(out), refresh=10 if busy else None)


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
        page.form(
            "/claim/edit",
            hidden + accept + "<button type='submit' name='status' value='removed'>Remove</button>",
            "inline",
            "/setup",
        )
        + page.form(
            "/claims/move",
            hidden + "<button type='submit' name='delta' value='-1'>Up</button>"
            "<button type='submit' name='delta' value='1'>Down</button>",
            "inline",
            "/setup",
        )
        + "<details><summary>Edit the wording</summary>"
        + page.form(
            "/claim/edit",
            hidden + "<input type='hidden' name='status' value='edited'>"
            f"<textarea name='text' rows='3' required>{e(text)}</textarea><br>"
            "<button type='submit'>Save</button>",
            back="/setup",
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
    for pos, cid, state, total, labeled, calls in rows:
        st = labels.get(cid)
        if state == "done" and st is not None and not st.incomplete:
            finding = f"<span class='verdict {st.css}'>{e(st.label)}</span>"
        elif state == "done":
            finding = "<span class='muted'>Finished; shown once it is the run on screen</span>"
        else:
            finding = "<span class='verdict v-unp'>Labeling incomplete</span>"
        cands = "" if total is None else f"{labeled} of {total}"
        out.append(
            f"<tr><td>{pos}</td><td><a href='{e(link('/claim', id=cid))}'>{e(cid)}</a></td>"
            f"<td>{e(STATE_TEXT.get(state, state))}</td><td>{cands}</td><td>{calls}</td>"
            f"<td>{finding}</td></tr>"
        )
    out.append("</table>")
    return page.wrap("Audit progress", "".join(out), refresh=10 if running else None)
