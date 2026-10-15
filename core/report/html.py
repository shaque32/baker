"""The cited claims report: one self-contained HTML file an expert opens offline or prints to PDF.

No scripts, no external fonts, styles or images. Everything shown is read from the case
database. Every cited span (government text, evidence quotes, record text) is wrapped in
<span class="q"> so the forbidden-word check can tell cited text from the tool's own words. A
reason or note an expert typed is wrapped in <span class="said">, which the check also leaves as
written: it is the expert's own wording, shown next to their name.

Display rules:
- The report shows pipeline.view_run(): the latest completed pipeline run (a full audit, or a
  rules-only re-decide after expert review; core/review/redecide.py), or a newer audit that has
  not finished yet. Then a banner says so, and every claim it has not finished prints as
  "Labeling incomplete" with no verdict and no evidence. Evidence review status is shown as it
  is now; if an expert decided anything after the run, a banner says to re-run the verdicts.
- Verdict labels come from core/review/status.py, which the review screen uses too.
  "Supported (expert-confirmed)" only when the verdict's supported_basis is confirmed, which
  rules.py sets only if an expert accepted every supporting item it cites (the invariants
  re-check this). Otherwise "Supported (AI-reviewed)". AI-reviewed never displays as confirmed.
  An unproven claim whose supporting evidence no expert has decided yet shows as
  "Support found: do you agree?", Baker's finding put to the expert; its verdict is unproven.
- Each evidence item shows its provenance tier from contracts.display_tier: the record's tier
  (observed, derived, inferred), or ai_reviewed / confirmed from its review status.
- Device-ownership stipulations, expert-confirmed identity links, source coverage, what each
  search covered and the meaning of each verdict are printed as limitations in every report.
- The Selection audit section (core/report/selection.py) shows each message the document quotes,
  an exhibit quotes or the examiner tagged in its own exchange, with the messages around it that
  were not picked. It never changes a verdict.
- Each claim lists the other explanations its records raise (core/hypotheses/, rendered by
  core/report/hypotheses.py, the same fragment as the claim page), with the records that fit
  each. Found by code, shown as leads for the expert; they never change a verdict.
- The report carries source hashes, Baker, contract, rule, report and model versions, and an
  audit-log summary with the hash-chain result.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter
from pathlib import Path

from core import pipeline
from core.audit import invariants
from core.contracts import (
    AssumptionKind,
    EvidenceItem,
    Fidelity,
    Stance,
    StipulationStatus,
    VerdictDecision,
    display_tier,
)
from core.hypotheses import explain
from core.ingest import coverage as import_coverage
from core.report import hypotheses as alternatives_html
from core.report import restore as restore_html
from core.report import selection as selection_html
from core.report import timeline as timeline_html
from core.review import audit_log
from core.review.status import (
    AWAITING_EXPERT,
    HOLDINGS,
    SUPPORTED_AI,
    SUPPORTED_EXPERT,
    ClaimState,
    case_holdings,
    claim_states,
)
from core.review.status import verdict_label as _verdict_label

REPORT_VERSION = "0.3.0"

__all__ = [
    "AWAITING_EXPERT",
    "SUPPORTED_AI",
    "SUPPORTED_EXPERT",
    "render_report",
    "write_report",
]

STANCE_LABEL = {
    Stance.SUPPORTS: "supports",
    Stance.CONTRADICTS: "contradicts",
    Stance.COMPLICATES: "complicates",
    Stance.IRRELEVANT: "irrelevant",
}

CSS = """
:root { --fg:#141414; --muted:#57534b; --bg:#f7f5f0; --card:#fdfcfa; --line:#e4e0d8;
  --line-strong:#cfc9bd; --panel:#efece5; --accent:#1d3557;
  --sup:#2f5d43; --sup-bg:#e6eee8; --sup-line:#bcd0c2; --supai:#5c5a1f;
  --con:#9a3a2c; --con-bg:#f4e5e1; --con-line:#e2c0b8;
  --unp:#7f5a12; --unp-bg:#f5ecd6; --unp-line:#e3d2a8; --await:#7f5a12; --warn:#f5ecd6;
  --sans: Inter, "Inter Variable", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica,
    Arial, sans-serif;
  --serif: "Instrument Serif", "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
  --mono: "JetBrains Mono", ui-monospace, Menlo, Consolas, monospace; }
body { font: 15px/1.55 var(--sans); color: var(--fg); background: var(--bg);
  max-width: 980px; margin: 0 auto; padding: 32px 20px 72px;
  -webkit-font-smoothing: antialiased; }
::selection { background: #d9e1ec; }
a { color: var(--accent); text-underline-offset: 2px; }
h1, h2, h3 { line-height: 1.2; color: var(--fg); }
h1 { font: 400 40px/1.1 var(--serif); letter-spacing: -0.02em; margin: 8px 0 6px; }
h2 { font-size: 17px; font-weight: 600; margin: 40px 0 10px; padding-bottom: 6px;
  border-bottom: 1px solid var(--line); }
h3 { font-size: 15px; font-weight: 600; }
.muted { color: var(--muted); }
.mono { font-family: var(--mono); font-size: 11.5px; word-break: break-all; }
.banner { background: var(--unp-bg); border: 1px solid var(--unp-line); border-radius: 10px;
  padding: 12px 16px; margin: 16px 0; color: #4a3608; }
.banner strong { font-size: 15px; }
table { border-collapse: separate; border-spacing: 0; width: 100%; margin: 10px 0;
  font-size: 13px; background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  overflow: hidden; }
th, td { border-bottom: 1px solid var(--line); padding: 8px 10px; text-align: left;
  vertical-align: top; }
tr:last-child td { border-bottom: 0; }
th { background: var(--panel); font: 500 10.5px var(--mono); letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--muted); }
.claim { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 6px 22px 16px; margin: 20px 0;
  box-shadow: 0 1px 2px rgb(20 20 20 / 0.04), 0 6px 18px -10px rgb(20 20 20 / 0.12); }
.claim > blockquote { font: 400 24px/1.25 var(--serif); letter-spacing: -0.01em;
  background: none; border-left: 2px solid var(--fg); border-radius: 0; padding: 2px 0 2px 18px; }
.verdict { display: inline-flex; align-items: center; gap: 6px; font: 500 13px var(--sans);
  padding: 3px 11px 3px 8px; border: 1px solid var(--line-strong); border-radius: 999px;
  background: var(--panel); color: var(--muted); white-space: nowrap; }
.verdict::before { content: "•"; display: inline-flex; align-items: center;
  justify-content: center; width: 15px; height: 15px; border: 1.5px solid currentColor;
  border-radius: 50%; font-size: 10px; font-weight: 700; line-height: 1; box-sizing: border-box; }
.v-sup { color: var(--sup); background: var(--sup-bg); border-color: var(--sup-line); }
.v-sup::before { content: "✓"; }
.v-supai { color: var(--supai); background: var(--sup-bg); border: 1px dashed var(--sup-line); }
.v-supai::before { content: "✓"; }
.v-con { color: var(--con); background: var(--con-bg); border-color: var(--con-line); }
.v-con::before { content: "✕"; }
.v-unp { color: var(--unp); background: var(--unp-bg); border-color: var(--unp-line); }
.v-unp::before { content: "?"; }
.v-await { color: var(--await); background: var(--unp-bg); border: 1px dashed var(--await); }
.v-await::before { content: "?"; }
.verdict.v-nt { color: var(--muted); background: var(--panel); border: 1px dashed var(--muted); }
.v-nt::before { content: "–"; }
blockquote { margin: 10px 0; padding: 8px 14px; border-left: 2px solid var(--line-strong);
  background: var(--panel); border-radius: 0 8px 8px 0; }
.q { white-space: pre-wrap; }
details { margin: 8px 0; }
details summary { cursor: pointer; font-size: 13px; font-weight: 500; color: var(--accent); }
@page { margin: 16mm 14mm; }
@media print {
  :root { --fg:#000; --muted:#444; --bg:#fff; --card:#fff; --line:#999; --panel:#f2f2f2;
    --sup:#000; --supai:#000; --con:#000; --unp:#000; --await:#000; --warn:#fff;
    --sup-bg:#fff; --con-bg:#fff; --unp-bg:#fff; }
  body { max-width: none; padding: 0; font-size: 10.5pt; }
  h2 { break-after: avoid; } h3 { break-after: avoid; }
  .claim { break-inside: avoid; box-shadow: none; } tr { break-inside: avoid; }
  thead { display: table-header-group; }
  table { width: calc(100% - 2px); }
  .claim { margin-right: 2px; }
  .verdict { border: 1.5px solid #000; }
  .banner { border: 2px solid #000; color: #000; }
  .noprint { display: none; }
}
"""


def q(text: object) -> str:
    """A cited span: text from the government document or the evidence, not the tool's words."""
    return f'<span class="q">{html.escape(str(text))}</span>'


def said(text: object) -> str:
    """A reason or note an expert typed, as they wrote it. Never for Baker's or a model's text."""
    return f'<span class="said">{html.escape(str(text))}</span>'


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def verdict_label(decision: VerdictDecision, awaiting: bool = False) -> tuple[str, str]:
    """(display text, css class). Kept here for callers of the report module."""
    return _verdict_label(decision, awaiting)


def review_label(conn: sqlite3.Connection, item: EvidenceItem) -> str:
    """The latest review of an item, as HTML: the expert's reason in their own words."""
    r = conn.execute(
        "SELECT reviewer_kind, reviewer, status, reason FROM evidence_reviews"
        " WHERE evidence_id = ? ORDER BY seq DESC LIMIT 1",
        (item.id,),
    ).fetchone()
    if r is None:
        return "Not reviewed"
    kind, who, status, reason = r
    if kind == "expert":
        what = {"accepted": "Accepted", "dismissed": "Dismissed", "open": "Reopened"}[status]
        return f"{what} by {e(who)}: {said(reason)}"
    what = {"ai_accepted": "Accepted", "dismissed": "Dismissed"}[status]
    tail = " Not confirmed by an expert." if status == "ai_accepted" else ""
    return f"{what} by the local AI reviewer: {e(reason)}{tail}"


# ---------------------------------------------------------------- sections


def sources(conn: sqlite3.Connection) -> list[tuple]:
    return list(
        conn.execute(
            "SELECT id, kind, fidelity, extraction_type, file_name, sha256, tool_name,"
            " tool_version, imported_at_utc FROM sources ORDER BY id"
        )
    )


def _limitations(conn: sqlite3.Connection, srcs: list[tuple]) -> str:
    items: list[str] = []
    stips = [
        st for st in pipeline.load_stipulations(conn) if st.status == StipulationStatus.CONFIRMED
    ]
    if stips:
        for st in stips:
            items.append(
                "<li><strong>Device ownership is a stipulation, not a finding.</strong> "
                f"{e(st.decided_by)} stipulated on {e(pipeline.iso(st.decided_at_utc))}: "
                f"{q(st.statement)} Baker did not verify who used the phone. Every finding that "
                "names this person rests on the stipulation.</li>"
            )
    else:
        items.append(
            "<li><strong>No device-ownership stipulation was recorded.</strong> Findings that "
            "name a person do not establish who used each phone.</li>"
        )
    for app, ident, person, by, at in conn.execute(
        "SELECT a.app, a.identifier, p.name, l.decided_by, l.decided_at_utc"
        " FROM identity_links l JOIN accounts a ON a.id = l.account_id"
        " JOIN persons p ON p.id = l.person_id WHERE l.status = 'confirmed' ORDER BY l.id"
    ):
        items.append(
            "<li><strong>Who uses an account is an expert decision, not a finding.</strong> "
            f"{e(by)} confirmed on {e(at)} that {q(f'{app} {ident}')} is used by {q(person)}. "
            "Baker did not verify it. Every check that ties this person to that account rests "
            "on it.</li>"
        )
    for s in srcs:
        if s[2] == Fidelity.CURATED_REPORT.value:
            items.append(
                f"<li>{q(s[4])} is an examiner-curated report. Records the examiner left out "
                "were not available to Baker, so no absence finding can rest on it.</li>"
            )
        elif s[2] == Fidelity.UNKNOWN.value and s[1] != "govdoc":
            items.append(
                f"<li>The coverage of {q(s[4])} is not known, so no absence finding can rest "
                "on it.</li>"
            )
    for cov in import_coverage.summaries(conn):
        if cov.format_unverified and cov.importer == "axiom":
            items.append(
                f"<li><strong>{q(cov.file_name)} was read with Baker's Magnet AXIOM reader, which "
                "is not yet verified against a real AXIOM export.</strong> It was built from "
                "public descriptions of AXIOM's report exports and tested on synthetic exports "
                "only. Each record cited from this file should be compared with the same record "
                "in AXIOM Examine before it is relied on.</li>"
            )
        elif cov.format_unverified:
            items.append(
                f"<li><strong>{q(cov.file_name)} was read with Baker's UFDR reader, which is not "
                "yet verified against a real UFDR.</strong> It was built from Cellebrite's public "
                "descriptions of the format and tested on synthetic packages only. Each record "
                "cited from this file should be compared with the same record in Cellebrite "
                "Reader before it is relied on.</li>"
            )
        attention = [i for i in cov.attention if i.code != "format_unverified"]
        if attention:
            lis = "".join(f"<li>{import_coverage.render(i, q, e)}</li>" for i in attention)
            items.append(
                f"<li>Baker did not read all of {q(cov.file_name)}: {e(cov.headline)} Records "
                "in the parts listed here are not in the evidence Baker reviewed, and times it "
                f"could not read are not used.<ul>{lis}</ul></li>"
            )
    items += [
        f"<li><strong>{SUPPORTED_EXPERT}</strong> means an expert accepted every supporting "
        "item the finding stands on. "
        f"<strong>{SUPPORTED_AI}</strong> would mean a local AI reviewer accepted the "
        "supporting evidence and no human expert has confirmed it; under the current rules no "
        "claim reaches supported on AI review alone.</li>",
        f"<li><strong>{AWAITING_EXPERT}</strong> means Baker found records it reads as "
        "supporting the claim and no expert has accepted or dismissed them yet. Until an expert "
        "does, the verdict is unproven. The labels are model output and can be wrong, so the "
        "expert checks each item. The local AI reviewer's acceptances only sort evidence for "
        "the expert; they never make a claim supported.</li>",
        "<li>Unproven means the evidence Baker reviewed does not establish the claim. It does "
        "not mean the claim is false.</li>",
        "<li>A search that finds nothing does not show that something did not happen. Each "
        "check states what was searched and what the source covered (see Searches and "
        "coverage).</li>",
        "<li>Stance labels are model output. Every quote shown was checked by code to appear "
        "verbatim in the record; labels whose quotes failed were discarded.</li>",
        "<li>Times are stored in UTC. The raw value from the report is shown beside each one, "
        "because report display offsets can differ from the phone's own time zone.</li>",
    ]
    return "<h2>Limitations</h2><ul>" + "".join(items) + "</ul>"


def record_line(conn: sqlite3.Connection, record_id: str) -> str:
    if record_id.startswith("msg:"):
        r = conn.execute(
            "SELECT m.ts_utc, m.ts_raw, a.identifier, a.display_name, t.app, t.title"
            " FROM messages m LEFT JOIN accounts a ON a.id = m.sender_account_id"
            " LEFT JOIN threads t ON t.id = m.thread_id WHERE m.id = ?",
            (record_id,),
        ).fetchone()
        if r:
            sender = " ".join(x for x in (r[2], f"({r[3]})" if r[3] else None) if x)
            return (
                f"{e(r[4])} message from {q(sender or 'unknown sender')} in thread "
                f"{q(r[5] or '(untitled)')}; UTC {e(r[0] or 'not given')}, "
                f"as printed {q(r[1] or 'not given')}"
            )
    text = invariants.record_text(conn, record_id)
    if text is not None and record_id.startswith("call:"):
        r = conn.execute("SELECT ts_utc, ts_raw FROM calls WHERE id = ?", (record_id,)).fetchone()
        return f"{q(text)}; UTC {e(r[0] or 'not given')}, as printed {q(r[1] or 'not given')}"
    return q(text) if text is not None else "record not found"


def _claim_block(conn: sqlite3.Connection, st: ClaimState, case: explain.Case) -> str:
    claim, decision = st.claim, st.decision
    out = [f'<div class="claim" id="{e(claim.id)}">']
    out.append(
        f"<h3>{e(st.name)} <span class='muted'>· {e(st.where)} · {e(claim.claim_type.value)} · "
        f"claim {e(claim.status.value)}"
        f"{' by the expert' if claim.model_run_id is None else ' (model-proposed)'}</span></h3>"
    )
    out.append(f"<blockquote>{q(claim.text)}</blockquote>")
    out.append(f"<p class='muted'>Claim id <span class='mono'>{e(claim.id)}</span></p>")
    nt = " v-nt" if st.untested else ""
    out.append(f'<p><span class="verdict {st.css}{nt}">{e(st.label)}</span></p>')
    if st.awaiting_expert:
        out.append(
            f"<p>Baker found supporting evidence: {st.ai_accepted} item(s) accepted by the local "
            f"AI reviewer and {st.open_support} not reviewed, waiting for an expert to agree or "
            "disagree. Until an expert accepts the key evidence, the claim stays unproven.</p>"
        )
    if st.edited_after_run:
        out.append("<p><strong>The claim text changed after this audit.</strong> Re-run it.</p>")
    if decision is not None:
        out.append("<ul>" + "".join(f"<li>{e(r)}</li>" for r in decision.reasons) + "</ul>")
        out.append(
            f"<p class='muted'>Rule version {e(decision.rule_version)}, decided "
            f"{e(pipeline.iso(decision.decided_at_utc))} in {e(decision.pipeline_run_id)}.</p>"
        )
        if decision.confirmed_by:
            note = f" Note: {said(decision.override_note)}" if decision.override_note else ""
            out.append(f"<p>Verdict reviewed by {e(decision.confirmed_by)}.{note}</p>")
    coverage = {cv.assumption_id: cv for cv in (decision.coverage if decision else ())}

    if st.assumptions:
        out.append(
            "<table><thead><tr><th>Assumption</th><th>Kind</th><th>Core</th>"
            "<th>Tier at creation</th><th>Covered (computed by the rules)</th></tr></thead>"
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
                f"<td>{'yes' if a.is_core else 'no'}</td><td>{e(a.tier.value)}</td>"
                f"<td>{e(cov)}</td></tr>"
            )
        out.append("</table>")
    if st.checks:
        out.append(
            "<table><thead><tr><th>Check</th><th>Outcome</th><th>What was searched</th>"
            "<th>Detail</th></tr></thead>"
        )
        for c in st.checks:
            out.append(
                f"<tr><td>{e(c.check_name)} {e(c.check_version)}</td><td>{e(c.outcome.value)}"
                f"</td><td>{e(c.searched)}</td><td>{e(c.detail)}</td></tr>"
            )
        out.append("</table>")
    if st.unlabeled:
        out.append(f"<p class='muted'>{e(st.unlabeled)}</p>")
    if st.untested:
        out.append(f"<p><strong>{e(st.not_tested or '')}</strong></p>")
        held = "".join(f"<li>{e(h)}</li>" for h in case_holdings(conn))
        out.append(f"<p>{e(HOLDINGS)}</p><ul>{held or '<li>No extraction imported.</li>'}</ul>")

    shown = [x for x in st.evidence if x.stance != Stance.IRRELEVANT]
    hidden = len(st.evidence) - len(shown)
    if shown:
        out.append(
            "<table><thead><tr><th>Evidence</th><th>Stance</th><th>Tier</th><th>Review</th>"
            "<th>Source</th></tr></thead>"
        )
        for x in shown:
            out.append(
                f"<tr><td><blockquote>{q(x.quote)}</blockquote>{record_line(conn, x.record_id)}"
                f"<br><span class='muted'>Model rationale (inferred): {e(x.rationale)}</span>"
                f"</td><td>{STANCE_LABEL[x.stance]}</td><td>{display_tier(x).value}</td>"
                f"<td>{review_label(conn, x)}</td>"
                f"<td class='mono'>{e(x.ref.source_id)} {e(x.ref.locator)}<br>{e(x.record_id)}"
                "</td></tr>"
            )
        out.append("</table>")
    elif decision is not None:
        out.append("<p class='muted'>No relevant evidence items were stored for this claim.</p>")
    if hidden:
        out.append(f"<p class='muted'>{hidden} retrieved records were labeled irrelevant.</p>")
    # Leads are worked out from the run's assumptions; after an edit they would describe the old
    # claim, so they wait for a re-run (the claim already says to re-run it).
    if st.assumptions and not st.incomplete and not st.edited_after_run:
        alts = explain.alternatives(case, st.assumptions)
        if alts:
            out.append("<h4>Other explanations to check</h4>")
            out.append(alternatives_html.alternatives_html(alts))
    out.append("</div>")
    return "".join(out)


def searches_section(states: list[ClaimState], srcs: list[tuple]) -> str:
    """What each completeness (absence or count) check searched, and the sources' coverage."""
    fidelity = {s[0]: (s[4], s[2]) for s in srcs}
    rows: list[str] = []
    for st in states:
        kinds = {a.id: a for a in st.assumptions}
        for c in st.checks:
            a = kinds.get(c.assumption_id)
            if a is None or a.kind != AssumptionKind.COMPLETENESS:
                continue
            searched_sources = (
                "; ".join(
                    f"{fidelity[s][0]} ({fidelity[s][1]})" if s in fidelity else s
                    for s in c.source_ids
                )
                or "none named"
            )
            rows.append(
                f"<tr><td>{e(st.name)}</td><td>{e(a.text)}</td>"
                f"<td>{e(c.check_name)} {e(c.check_version)}</td><td>{e(c.outcome.value)}</td>"
                f"<td>{e(c.searched)}</td><td>{e(searched_sources)}</td></tr>"
            )
    out = [
        "<h2>Searches and coverage</h2><p>Absence and count findings rest on searches. A search "
        "that finds nothing shows only that the searched records do not contain it; records a "
        "source never held, or that an examiner left out of a curated report, were not "
        "searched.</p>"
    ]
    if rows:
        out.append(
            "<table><thead><tr><th>Claim</th><th>Assumption</th><th>Check</th><th>Outcome</th>"
            "<th>What was searched</th><th>Sources (coverage)</th></tr></thead>"
            + "".join(rows)
            + "</table>"
        )
    else:
        out.append("<p class='muted'>No absence or count check ran in this audit.</p>")
    return "".join(out)


def audit_log_summary(conn: sqlite3.Connection) -> dict:
    n = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    first = conn.execute("SELECT at_utc FROM audit_log ORDER BY seq LIMIT 1").fetchone()
    last = conn.execute("SELECT at_utc, hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    by_action = Counter(
        a for (a,) in conn.execute("SELECT action FROM audit_log WHERE actor LIKE 'expert:%'")
    )
    experts = sorted(
        {a for (a,) in conn.execute("SELECT actor FROM audit_log WHERE actor LIKE 'expert:%'")}
    )
    runs = Counter(s for (s,) in conn.execute("SELECT status FROM pipeline_runs"))
    return {
        "entries": n,
        "first_at": first[0] if first else None,
        "last_at": last[0] if last else None,
        "last_hash": last[1] if last else "",
        "chain_ok": audit_log.verify_chain(conn),
        "expert_actions": dict(sorted(by_action.items())),
        "experts": experts,
        "runs": dict(sorted(runs.items())),
    }


def _quote_check(run: dict) -> str:
    """The quote check the run's evidence passed (core.audit.quotes.VERSION). Runs before 1.2.0
    did not record it."""
    return (run.get("config") or {}).get("quote_check") or "not recorded (1.1.0 or earlier)"


def _versions(conn: sqlite3.Connection, run: dict | None) -> str:
    rows = [("Report", REPORT_VERSION), ("Other explanations (code)", explain.VERSION)]
    if run:
        rows += [
            ("Baker pipeline", run["baker_version"]),
            ("Contracts", run["contracts_version"]),
            ("Verdict rules", run["rule_version"]),
            ("Quote check", _quote_check(run)),
        ]
    model_rows = list(
        conn.execute(
            "SELECT purpose, model_name, model_sha256, prompt_version FROM model_runs"
            " ORDER BY purpose, id"
        )
    )
    out = ["<table><thead><tr><th>Part</th><th>Version</th></tr></thead>"]
    out += [f"<tr><td>{e(k)}</td><td class='mono'>{e(v)}</td></tr>" for k, v in rows]
    for purpose, name, sha, prompt in model_rows:
        out.append(
            f"<tr><td>Model for {e(purpose)}</td><td class='mono'>{e(name)}, prompt "
            f"{e(prompt)}, SHA-256 {e(sha)}</td></tr>"
        )
    if not model_rows:
        out.append("<tr><td>Models</td><td>No model run is recorded.</td></tr>")
    out.append("</table>")
    return "".join(out)


def render_report(conn: sqlite3.Connection, timeline: timeline_html.Settings | None = None) -> str:
    """timeline: the case's timeline settings (core/timeline/settings.py); defaults if None."""
    srcs = sources(conn)
    run = pipeline.view_run(conn)
    govdocs = [r[0] for r in conn.execute("SELECT title FROM govdocs ORDER BY id")]

    states = claim_states(conn, run=run)
    tally = Counter(st.label for st in states)

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Baker claims report</title>"
        f"<style>{CSS}{restore_html.CSS}{timeline_html.CSS}{selection_html.CSS}"
        f"{alternatives_html.CSS}</style>"
        "</head><body>",
        "<h1>Baker claims report</h1>",
        "<p class='muted'>"
        + (" · ".join(q(t) for t in govdocs) or "No government document imported")
        + f" · report {REPORT_VERSION}"
        + (f" · rules {e(run['rule_version'])}" if run else "")
        + "</p>",
    ]
    if run is None:
        parts.append("<div class='banner'><strong>No audit has run on this case.</strong></div>")
    else:
        if run.get("partial"):
            incomplete = sum(1 for st in states if st.incomplete)
            parts.append(
                "<div class='banner'><strong>Labeling incomplete: this audit has not finished."
                f"</strong> It finished {len(run['manifest'])} of {len(run['claim_order'] or ())}"
                f' claims. The other {incomplete} claim(s) print as "Labeling incomplete": '
                "their evidence was not fully labeled, so they have no verdict.</div>"
            )
        if run.get("fake"):
            parts.append(stand_in_banner(run))
        if run.get("rules_pending"):
            parts.append(
                "<div class='banner'><strong>Verdict rules are not written yet.</strong> Every "
                "claim is shown as unproven because no verdict was decided.</div>"
            )
        later = conn.execute(
            "SELECT COUNT(*) FROM evidence_reviews WHERE reviewer_kind = 'expert'"
            " AND decided_at_utc > ?",
            (run["started_at_utc"],),
        ).fetchone()[0]
        if later:
            parts.append(
                f"<div class='banner'><strong>{later} expert evidence decisions were made after "
                "this run.</strong> The review column shows them, but the verdicts do not reflect "
                "them yet. Re-run the verdicts.</div>"
            )
        awaiting = sum(1 for st in states if st.awaiting_expert)
        if awaiting:
            parts.append(
                f"<div class='banner'><strong>{awaiting} claim(s): support found, waiting for "
                "the expert to agree.</strong> They stay unproven until an expert accepts their "
                "key evidence.</div>"
            )

    parts.append("<h2>Summary</h2><table><thead><tr><th>Finding</th><th>Claims</th></tr></thead>")
    for label, n in sorted(tally.items()):
        parts.append(f"<tr><td>{e(label)}</td><td>{n}</td></tr>")
    parts.append("</table>")

    parts.append(_limitations(conn, srcs))
    parts.append("<h2>Claims</h2>")
    case = explain.load(conn)
    parts += [_claim_block(conn, st, case) for st in states]

    parts.append(searches_section(states, srcs))
    timeline = timeline or timeline_html.Settings()
    parts.append(timeline_html.report_section(conn, timeline))
    parts.append(restore_html.restore_section(conn))
    parts.append(selection_html.selection_section(conn, states, timeline))

    parts.append(
        "<h2>Sources</h2><table><thead><tr><th>File</th><th>Kind</th><th>Coverage</th>"
        "<th>Extraction</th><th>SHA-256</th><th>Tool</th></tr></thead>"
    )
    for s in srcs:
        parts.append(
            f"<tr><td>{q(s[4])}<br><span class='mono'>{e(s[0])}</span></td><td>{e(s[1])}</td>"
            f"<td>{e(s[2])}</td><td>{e(s[3])}</td><td class='mono'>{e(s[5])}</td>"
            f"<td>{e(s[6])} {e(s[7])}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Versions</h2>")
    parts.append(_versions(conn, run))

    parts.append("<h2>Run</h2>")
    if run:
        mode = ""
        if run.get("mode") == "rules_only":
            mode = (
                f" This run re-decided the verdicts with the rules only, after expert review, "
                f"from {e(run['from_run'])}; its evidence came from {e(run['evidence_from_run'])}"
                f" and no model was called. Requested by {e(run.get('requested_by'))}."
            )
            skipped = run.get("skipped") or {}
            if skipped:
                mode += (
                    " Not re-decided: "
                    + "; ".join(f"{e(k)} ({e(v)})" for k, v in sorted(skipped.items()))
                    + "."
                )
        parts.append(
            f"<p>Run {e(run['run_id'])}, started {e(run['started_at_utc'])}. Baker "
            f"{e(run['baker_version'])}, contracts {e(run['contracts_version'])}, rule version "
            f"{e(run['rule_version'])}, quote check {e(_quote_check(run))}. "
            f"{e(run['stored_items'])} evidence items stored; {e(run['dropped_labels'])} labels "
            f"discarded; {e(run['reviewer_failures'])} reviewer failures counted as dismissals."
            f"{mode}</p><table><thead><tr><th>Step</th><th>Component</th></tr></thead>"
        )
        comps = run["components"]
        assert isinstance(comps, dict)  # noqa: S101 - written by pipeline.run_audit
        for k, v in comps.items():
            parts.append(f"<tr><td>{e(k)}</td><td class='mono'>{e(v)}</td></tr>")
        parts.append("</table>")
    model_runs = list(
        conn.execute(
            "SELECT id, purpose, model_name, model_sha256, prompt_version, params_json, seed"
            " FROM model_runs ORDER BY id"
        )
    )
    if model_runs:
        parts.append(
            "<h3>Model runs</h3><table><thead><tr><th>Id</th><th>Purpose</th><th>Model</th>"
            "<th>Model SHA-256</th><th>Prompt</th><th>Parameters</th><th>Seed</th></tr></thead>"
        )
        for m in model_runs:
            parts.append("<tr>" + "".join(f"<td class='mono'>{e(v)}</td>" for v in m) + "</tr>")
        parts.append("</table>")

    summary = audit_log_summary(conn)
    actions_done = ", ".join(f"{k} {v}" for k, v in summary["expert_actions"].items()) or "none"
    parts.append(
        f"<h2>Audit log</h2><p>{summary['entries']} entries from {e(summary['first_at'])} to "
        f"{e(summary['last_at'])}. Hash chain "
        f"{'verified' if summary['chain_ok'] else '<strong>FAILED VERIFICATION</strong>'}. "
        f"Last hash <span class='mono'>{e(summary['last_hash'])}</span>.</p>"
        f"<p>Experts: {e(', '.join(summary['experts']) or 'none')}. Expert actions: "
        f"{e(actions_done)}. Pipeline runs: "
        f"{e(', '.join(f'{k} {v}' for k, v in summary['runs'].items()) or 'none')}.</p>"
    )
    expert_rows = list(
        conn.execute(
            "SELECT seq, at_utc, actor, action, payload_json FROM audit_log"
            " WHERE actor LIKE 'expert:%' ORDER BY seq"
        )
    )
    if expert_rows:
        parts.append(
            "<table><thead><tr><th>#</th><th>When (UTC)</th><th>Expert</th><th>Action</th>"
            "<th>Details</th></tr></thead>"
        )
        for r in expert_rows:
            parts.append(
                f"<tr><td>{r[0]}</td><td>{e(r[1])}</td><td>{e(r[2])}</td><td>{e(r[3])}</td>"
                f"<td>{q(_compact(r[4]))}</td></tr>"
            )
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def _compact(payload_json: str) -> str:
    try:
        p = json.loads(payload_json)
    except ValueError:
        return payload_json
    return "; ".join(f"{k}: {v}" for k, v in p.items() if v not in (None, ""))


def stand_in_banner(run: dict) -> str:
    """The banner for a run that used eval stand-ins. The demo case (eval/demo.py) says
    exactly what was scripted; any other stand-in run is a test run."""
    if pipeline.scripted_demo(run):
        return (
            "<div class='banner'><strong>Demo case: synthetic data, scripted labels.</strong> "
            "Every name and message here is fictional. So the demo opens in seconds, no model "
            "ran: the evidence labels and most expert decisions were scripted from the signed "
            "answer key. The checks, quote checks and verdict rules are Baker's own. On a real "
            "case the local model labels the evidence and the expert decides every item.</div>"
        )
    return (
        "<div class='banner'><strong>Test run with stand-in components.</strong> Some "
        "steps of this run used fakes from the eval harness, not the real labeler, "
        "reviewer or checks. Nothing here is a finding.</div>"
    )


def write_report(
    conn: sqlite3.Connection, path: Path, timeline: timeline_html.Settings | None = None
) -> Path:
    """Render, check the tool's own wording, then write. Raises InvariantViolation on a bad word."""
    text = render_report(conn, timeline)
    invariants.check_report_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
