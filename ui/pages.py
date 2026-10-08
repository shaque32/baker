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
    """Shared page furniture: token for forms, the reviewing expert, a flash message."""

    def __init__(self, token: str, expert: str | None, flash: tuple[str, bool] | None = None):
        self.token = token
        self.expert = expert
        self.flash = flash

    def form(self, action: str, body: str, cls: str = "box", back: str = "") -> str:
        return (
            f'<form method="post" action="{e(action)}" class="{cls}">'
            f'<input type="hidden" name="token" value="{e(self.token)}">'
            + (f'<input type="hidden" name="next" value="{e(back)}">' if back else "")
            + body
            + "</form>"
        )

    def wrap(self, title: str, body: str, banner: str = "") -> str:
        who = (
            f"Reviewing as <strong>{e(self.expert)}</strong>"
            if self.expert
            else "<strong>Enter your name on the case page before reviewing.</strong>"
        )
        flash = ""
        if self.flash:
            msg, err = self.flash
            flash = f'<div class="flash{" err" if err else ""}">{e(msg)}</div>'
        return (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            f"<title>{e(title)} · Baker</title><style>{REPORT_CSS}{UI_CSS}</style></head><body>"
            "<nav><strong>Baker</strong><a href='/'>Case</a><a href='/claims'>Claims queue</a>"
            "<a href='/claim/new'>Add a claim</a><a href='/report'>Report</a>"
            f"<a href='/log'>Audit log</a><span class='who'>{who}</span></nav>"
            f"{flash}{banner}{body}</body></html>"
        )


# ---------------------------------------------------------------- banners


def run_banner(conn: sqlite3.Connection, page: Page, back: str) -> str:
    run = pipeline.last_run(conn)
    if run is None:
        return (
            "<div class='banner'><strong>No audit has run on this case.</strong> Run "
            "<span class='mono'>baker audit --db &lt;case.db&gt;</span> first.</div>"
        )
    out = []
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
    if later or stips:
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


# ---------------------------------------------------------------- case overview


def overview(conn: sqlite3.Connection, page: Page) -> str:
    srcs = sources(conn)
    run = pipeline.last_run(conn)
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

    out.append(_devices(conn, page))

    out.append("<h2>Audit</h2>")
    if run is None:
        out.append("<p>No audit has run yet.</p>")
    else:
        mode = (
            f"verdict rules re-run after expert review, from {e(run['from_run'])}"
            if run.get("mode") == "rules_only"
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
        out.append(
            page.form(
                "/redecide",
                "<button type='submit'>Re-run verdicts (rules only, no model)</button>",
                back="/",
            )
        )
    out.append(
        "<p class='muted'>A full audit (new evidence search and model labels) runs from the "
        "command line: <span class='mono'>baker audit --db &lt;case.db&gt;</span>.</p>"
    )
    summary = audit_log_summary(conn)
    out.append(
        f"<h2>Audit log</h2><p>{summary['entries']} entries. Hash chain "
        f"{'verified' if summary['chain_ok'] else '<strong>FAILED VERIFICATION</strong>'}. "
        "<a href='/log'>Open the log</a>.</p>"
    )
    return page.wrap("Case", "".join(out), run_banner(conn, page, "/"))


def _devices(conn: sqlite3.Connection, page: Page) -> str:
    devices = list(conn.execute("SELECT id, label, model, source_id FROM devices ORDER BY id"))
    stips = {s.subject_id: s for s in pipeline.load_stipulations(conn)}
    out = [
        "<h2>Devices and stipulations</h2><p>Who used each phone is a stipulation you make, not "
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
                "/",
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
            "/",
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
