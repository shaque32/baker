"""The cited claims report: one self-contained HTML file an expert opens offline.

No scripts, no external fonts, styles or images. Everything shown is read from the case
database. Every cited span (government text, evidence quotes, record text) is wrapped in
<span class="q"> so the forbidden-word check can tell cited text from the tool's own words.

Display rules:
- The report shows the latest completed pipeline run. Evidence review status is shown as it is
  now; if an expert decided anything after the run, a banner says to re-run the audit.
- "Supported (expert-confirmed)" only when the verdict's supported_basis is confirmed, which
  rules.py sets only if an expert accepted every supporting item it cites (the invariants
  re-check this). Otherwise "Supported (AI-reviewed)". AI-reviewed never displays as confirmed.
- Each evidence item shows its provenance tier from contracts.display_tier: the record's tier
  (observed, derived, inferred), or ai_reviewed / confirmed from its review status.
- Device-ownership stipulations, source coverage and the meaning of each verdict are printed as
  limitations in every report.
"""

from __future__ import annotations

import html
import sqlite3
from collections import Counter
from pathlib import Path

from core import pipeline
from core.audit import invariants
from core.contracts import (
    EvidenceItem,
    Fidelity,
    Stance,
    StipulationStatus,
    SupportedBasis,
    Verdict,
    VerdictDecision,
    display_tier,
)
from core.review import audit_log

REPORT_VERSION = "0.1.0"

SUPPORTED_AI = "Supported (AI-reviewed)"
SUPPORTED_EXPERT = "Supported (expert-confirmed)"

STANCE_LABEL = {
    Stance.SUPPORTS: "supports",
    Stance.CONTRADICTS: "contradicts",
    Stance.COMPLICATES: "complicates",
    Stance.IRRELEVANT: "irrelevant",
}

CSS = """
:root { --fg:#1b1b1b; --muted:#5b5b5b; --bg:#ffffff; --line:#d9d9d9; --panel:#f6f6f4;
  --sup:#1d6b3a; --supai:#6b5a1d; --con:#9b2226; --unp:#44546a; --warn:#fff4d6; }
@media (prefers-color-scheme: dark) { :root { --fg:#e8e8e8; --muted:#a8a8a8; --bg:#161616;
  --line:#3a3a3a; --panel:#202020; --sup:#6fcf97; --supai:#e2c46b; --con:#ff8a8a;
  --unp:#9fb3cc; --warn:#3b3220; } }
body { font: 15px/1.5 Georgia, "Times New Roman", serif; color: var(--fg); background: var(--bg);
  max-width: 980px; margin: 0 auto; padding: 24px 16px 64px; }
h1, h2, h3 { font-family: Helvetica, Arial, sans-serif; line-height: 1.25; }
h1 { font-size: 26px; margin-bottom: 4px; } h2 { font-size: 20px; margin-top: 36px;
  border-bottom: 1px solid var(--line); padding-bottom: 4px; } h3 { font-size: 16px; }
.muted { color: var(--muted); } .mono { font-family: Menlo, Consolas, monospace; font-size: 12px;
  word-break: break-all; }
.banner { background: var(--warn); border: 1px solid var(--line); padding: 12px 14px;
  margin: 16px 0; font-family: Helvetica, Arial, sans-serif; }
.banner strong { font-size: 17px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
th, td { border: 1px solid var(--line); padding: 5px 7px; text-align: left; vertical-align: top; }
th { background: var(--panel); font-family: Helvetica, Arial, sans-serif; }
.claim { border: 1px solid var(--line); padding: 4px 16px 12px; margin: 18px 0; }
.verdict { display: inline-block; font: bold 13px Helvetica, Arial, sans-serif; padding: 3px 8px;
  border: 2px solid currentColor; }
.v-sup { color: var(--sup); } .v-supai { color: var(--supai); } .v-con { color: var(--con); }
.v-unp { color: var(--unp); }
blockquote { margin: 8px 0; padding: 6px 12px; border-left: 3px solid var(--line);
  background: var(--panel); }
.q { white-space: pre-wrap; }
details summary { cursor: pointer; font-family: Helvetica, Arial, sans-serif; font-size: 13px; }
@media print { .claim { break-inside: avoid; } }
"""


def q(text: object) -> str:
    """A cited span: text from the government document or the evidence, not the tool's words."""
    return f'<span class="q">{html.escape(str(text))}</span>'


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def verdict_label(decision: VerdictDecision) -> tuple[str, str]:
    """(display text, css class)."""
    if decision.override_note is not None:
        return f"{decision.verdict.value.capitalize()} (expert override)", _css(decision.verdict)
    if decision.verdict == Verdict.SUPPORTED:
        if decision.supported_basis == SupportedBasis.CONFIRMED:
            return SUPPORTED_EXPERT, "v-sup"
        return SUPPORTED_AI, "v-supai"
    if pipeline.RULES_PENDING_REASON in decision.reasons:
        return "Unproven (rules not written yet)", "v-unp"
    return decision.verdict.value.capitalize(), _css(decision.verdict)


def _css(v: Verdict) -> str:
    return {Verdict.SUPPORTED: "v-sup", Verdict.CONTRADICTED: "v-con"}.get(v, "v-unp")


def review_label(conn: sqlite3.Connection, item: EvidenceItem) -> str:
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
        return f"{what} by {who}: {reason}"
    what = {"ai_accepted": "Accepted", "dismissed": "Dismissed"}[status]
    tail = " Not confirmed by an expert." if status == "ai_accepted" else ""
    return f"{what} by the local AI reviewer: {reason}{tail}"


# ---------------------------------------------------------------- sections


def _sources(conn: sqlite3.Connection) -> list[tuple]:
    return list(
        conn.execute(
            "SELECT id, kind, fidelity, extraction_type, file_name, sha256, tool_name,"
            " tool_version FROM sources ORDER BY id"
        )
    )


def _limitations(conn: sqlite3.Connection, sources: list[tuple]) -> str:
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
    for s in sources:
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
    items += [
        f"<li><strong>{SUPPORTED_AI}</strong> means a local AI reviewer accepted the supporting "
        "evidence. No human expert has confirmed it. "
        f"<strong>{SUPPORTED_EXPERT}</strong> means an expert accepted every supporting item "
        "the finding stands on.</li>",
        "<li>Unproven means the evidence Baker reviewed does not establish the claim. It does "
        "not mean the claim is false.</li>",
        "<li>A search that finds nothing does not show that something did not happen. Each "
        "check states what was searched and what the source covered.</li>",
        "<li>Stance labels are model output. Every quote shown was checked by code to appear "
        "verbatim in the record; labels whose quotes failed were discarded.</li>",
        "<li>Times are stored in UTC. The raw value from the report is shown beside each one, "
        "because report display offsets can differ from the phone's own time zone.</li>",
    ]
    return "<h2>Limitations</h2><ul>" + "".join(items) + "</ul>"


def _record_line(conn: sqlite3.Connection, record_id: str) -> str:
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
    return q(text) if text is not None else "record not found"


def _claim_block(conn: sqlite3.Connection, claim_id: str, run: dict | None) -> tuple[str, str]:
    claim = next(c for c in pipeline.load_claims(conn, include_removed=True) if c.id == claim_id)
    para = conn.execute(
        "SELECT page, para_no, label FROM govdoc_paragraphs WHERE id = ?", (claim.paragraph_id,)
    ).fetchone()
    where = (
        f"page {para[0]}, paragraph {e(para[2]) if para[2] else '#' + str(para[1])}"
        if para
        else "paragraph not found"
    )
    items = (run or {}).get("manifest", {}).get(claim.id)
    decision = pipeline.load_verdict(conn, claim.id, run["run_id"]) if run and items else None
    items = items or {"assumptions": [], "checks": [], "evidence": []}
    assumptions = pipeline.load_assumptions(conn, items["assumptions"])
    checks = pipeline.load_checks(conn, items["checks"])
    evidence = pipeline.load_evidence(conn, items["evidence"])

    label, css = verdict_label(decision) if decision else ("Not audited", "v-unp")
    out = [f'<div class="claim" id="{e(claim.id)}">']
    out.append(
        f"<h3>{e(claim.id)} <span class='muted'>· {where} · {e(claim.claim_type.value)} · "
        f"claim {e(claim.status.value)}"
        f"{' by the expert' if claim.model_run_id is None else ' (model-proposed)'}</span></h3>"
    )
    out.append(f"<blockquote>{q(claim.text)}</blockquote>")
    out.append(f'<p><span class="verdict {css}">{e(label)}</span></p>')
    if decision is not None:
        out.append("<ul>" + "".join(f"<li>{e(r)}</li>" for r in decision.reasons) + "</ul>")
        out.append(
            f"<p class='muted'>Rule version {e(decision.rule_version)}, decided "
            f"{e(pipeline.iso(decision.decided_at_utc))} in {e(decision.pipeline_run_id)}.</p>"
        )
        if decision.confirmed_by:
            note = f" Note: {e(decision.override_note)}" if decision.override_note else ""
            out.append(f"<p>Verdict reviewed by {e(decision.confirmed_by)}.{note}</p>")
    coverage = {cv.assumption_id: cv for cv in (decision.coverage if decision else ())}

    if assumptions:
        out.append(
            "<table><tr><th>Assumption</th><th>Kind</th><th>Core</th><th>Tier at creation</th>"
            "<th>Covered (computed by the rules)</th></tr>"
        )
        for a in assumptions:
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
    if checks:
        out.append(
            "<table><tr><th>Check</th><th>Outcome</th><th>What was searched</th><th>Detail</th>"
            "</tr>"
        )
        for c in checks:
            out.append(
                f"<tr><td>{e(c.check_name)} {e(c.check_version)}</td><td>{e(c.outcome.value)}"
                f"</td><td>{e(c.searched)}</td><td>{e(c.detail)}</td></tr>"
            )
        out.append("</table>")

    shown = [x for x in evidence if x.stance != Stance.IRRELEVANT]
    hidden = len(evidence) - len(shown)
    if shown:
        out.append(
            "<table><tr><th>Evidence</th><th>Stance</th><th>Tier</th><th>Review</th>"
            "<th>Source</th></tr>"
        )
        for x in shown:
            out.append(
                f"<tr><td><blockquote>{q(x.quote)}</blockquote>{_record_line(conn, x.record_id)}"
                f"<br><span class='muted'>Model rationale (inferred): {e(x.rationale)}</span>"
                f"</td><td>{STANCE_LABEL[x.stance]}</td><td>{display_tier(x).value}</td>"
                f"<td>{e(review_label(conn, x))}</td>"
                f"<td class='mono'>{e(x.ref.source_id)} {e(x.ref.locator)}<br>{e(x.record_id)}"
                "</td></tr>"
            )
        out.append("</table>")
    else:
        out.append("<p class='muted'>No relevant evidence items were stored for this claim.</p>")
    if hidden:
        out.append(f"<p class='muted'>{hidden} retrieved records were labeled irrelevant.</p>")
    out.append("</div>")
    return label, "".join(out)


def render_report(conn: sqlite3.Connection) -> str:
    sources = _sources(conn)
    run = pipeline.last_run(conn)
    govdocs = [r[0] for r in conn.execute("SELECT title FROM govdocs ORDER BY id")]

    claims = pipeline.load_claims(conn)
    blocks = [_claim_block(conn, c.id, run) for c in claims]
    tally = Counter(label for label, _ in blocks)

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Baker claims report</title>"
        f"<style>{CSS}</style></head><body>",
        "<h1>Baker claims report</h1>",
        "<p class='muted'>"
        + (" · ".join(q(t) for t in govdocs) or "No government document imported")
        + f" · report {REPORT_VERSION}</p>",
    ]
    if run is None:
        parts.append("<div class='banner'><strong>No audit has run on this case.</strong></div>")
    else:
        if run.get("fake"):
            parts.append(
                "<div class='banner'><strong>Test run with stand-in components.</strong> Some "
                "steps of this run used fakes from the eval harness, not the real labeler, "
                "reviewer or checks. Nothing here is a finding.</div>"
            )
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
                "them yet. Re-run the audit.</div>"
            )

    parts.append("<h2>Summary</h2><table><tr><th>Finding</th><th>Claims</th></tr>")
    for label, n in sorted(tally.items()):
        parts.append(f"<tr><td>{e(label)}</td><td>{n}</td></tr>")
    parts.append("</table>")

    parts.append(_limitations(conn, sources))
    parts.append("<h2>Claims</h2>")
    parts += [b for _, b in blocks]

    parts.append(
        "<h2>Sources</h2><table><tr><th>File</th><th>Kind</th><th>Coverage</th>"
        "<th>Extraction</th><th>SHA-256</th><th>Tool</th></tr>"
    )
    for s in sources:
        parts.append(
            f"<tr><td>{q(s[4])}<br><span class='mono'>{e(s[0])}</span></td><td>{e(s[1])}</td>"
            f"<td>{e(s[2])}</td><td>{e(s[3])}</td><td class='mono'>{e(s[5])}</td>"
            f"<td>{e(s[6])} {e(s[7])}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>Run</h2>")
    if run:
        parts.append(
            f"<p>Run {e(run['run_id'])}, started {e(run['started_at_utc'])}. Baker "
            f"{e(run['baker_version'])}, contracts {e(run['contracts_version'])}, rule version "
            f"{e(run['rule_version'])}. "
            f"{e(run['stored_items'])} evidence items stored; {e(run['dropped_labels'])} labels "
            f"discarded; {e(run['reviewer_failures'])} reviewer failures counted as dismissals."
            "</p><table><tr><th>Step</th><th>Component</th></tr>"
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
            "<h3>Model runs</h3><table><tr><th>Id</th><th>Purpose</th><th>Model</th>"
            "<th>Model SHA-256</th><th>Prompt</th><th>Parameters</th><th>Seed</th></tr>"
        )
        for m in model_runs:
            parts.append("<tr>" + "".join(f"<td class='mono'>{e(v)}</td>" for v in m) + "</tr>")
        parts.append("</table>")

    n_log = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    head = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    chain_ok = audit_log.verify_chain(conn)
    parts.append(
        f"<h2>Audit log</h2><p>{n_log} entries. Hash chain "
        f"{'verified' if chain_ok else '<strong>FAILED VERIFICATION</strong>'}. "
        f"Last hash <span class='mono'>{e(head[0] if head else '')}</span>.</p>"
    )
    expert_rows = list(
        conn.execute(
            "SELECT seq, at_utc, actor, action, payload_json FROM audit_log"
            " WHERE actor LIKE 'expert:%' ORDER BY seq"
        )
    )
    if expert_rows:
        parts.append(
            "<table><tr><th>#</th><th>When (UTC)</th><th>Expert</th><th>Action</th>"
            "<th>Details</th></tr>"
        )
        for r in expert_rows:
            parts.append(
                f"<tr><td>{r[0]}</td><td>{e(r[1])}</td><td>{e(r[2])}</td><td>{e(r[3])}</td>"
                f"<td>{q(r[4])}</td></tr>"
            )
        parts.append("</table>")
    parts.append("</body></html>")
    return "".join(parts)


def write_report(conn: sqlite3.Connection, path: Path) -> Path:
    """Render, check the tool's own wording, then write. Raises InvariantViolation on a bad word."""
    text = render_report(conn)
    invariants.check_report_text(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
