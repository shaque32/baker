"""The cited claims report: one self-contained HTML file an expert opens offline or prints to PDF.

No scripts, no external fonts, styles or images. Everything shown is read from the case
database. Every cited span (government text, evidence quotes, record text) is wrapped in
<span class="q"> so the forbidden-word check can tell cited text from the tool's own words. A
reason or note an expert typed is wrapped in <span class="said">, which the check also leaves as
written: it is the expert's own wording, shown next to their name. A model's stance rationale
that uses a forbidden word is not printed: a notice stands in for it, naming the word in
<span class="withheld-word"> (core/review/withheld.py).

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
  "Support found: do you agree?", Mabillon's finding put to the expert; its verdict is unproven.
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
- The report carries source hashes, Mabillon, contract, rule, report and model versions, and an
  audit-log summary with the hash-chain result.
- Each decided claim traces its verdict ("How this verdict was reached"): per core assumption,
  each evidence item, check or stipulation the rules relied on, or, for one not covered, what
  was found and not relied on; who proposed each (a named model, code, or the expert) and the
  expert's step. A model's label shows as model proposed until an expert accepts it.
- "What can be checked again" says the verdicts re-derive from the recorded labels and expert
  decisions, names each model whose labels they are, and says a hosted model's labels cannot be
  regenerated exactly (HOSTED). It never claims a local re-run gives identical labels.
- Each evidence row carries the evidence item's id (<tr id=...>), the same id the review screen
  gives its evidence card, so the two can be compared item by item.
- A stance rationale that uses a forbidden word is withheld, not printed: its row says
  "Rationale withheld", names the word and marks the item as needing expert review, and the
  "Withheld model rationales" section lists every such item (irrelevant ones too) with the
  rationale's SHA-256 and whether the expert acknowledged it. The case overview shows the same
  count (core/review/withheld.summary). Mabillon's own text is still checked whole: a forbidden
  word in it refuses the report.

Reproducible: the same case inputs, versions and expert decisions, made at the same clock
times, render byte-identical HTML (tests/test_report_consistency.py). Made at other times, the
report differs only in these fields, which the reproducibility test masks before hashing:
- a verdict's decision time ("decided <time> in <run>"),
- pipeline run ids, which are named for the run's start time ("run:20261007T000000Z"),
- the Run section's start time,
- the audit log's first and last entry times, its last hash (the hash chain covers each
  entry's time) and the When column of the expert actions,
- when each device-owner stipulation was made and each identity link confirmed (Limitations),
- the Examiner activity section's times and time on page, when the case includes it, which
  come from when pages were opened.
"""

from __future__ import annotations

import html
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core import build, pipeline
from core.audit import invariants, rules
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
from core.ingest import forwarded
from core.llm.cloud import is_cloud_sha
from core.report import hypotheses as alternatives_html
from core.report import paired as paired_html
from core.report import restore as restore_html
from core.report import selection as selection_html
from core.report import timeline as timeline_html
from core.review import activity, audit_log
from core.review.status import (
    AWAITING_EXPERT,
    CONFIRM_STEP,
    CONTRADICTION_FOUND,
    HOLDINGS,
    SUPPORTED_AI,
    SUPPORTED_EXPERT,
    ClaimState,
    case_holdings,
    claim_states,
)
from core.review.status import verdict_label as _verdict_label
from core.review.withheld import Withheld
from core.review.withheld import summary as withheld_summary

# 0.4.0 (#76): a "Quote check" row in Versions and the run line, and a call's UTC and printed
# time beside its line (the review screen shows the same line, through record_line).
# 0.5.0 (#91): the top line names the Mabillon release and git commit, the pipeline, rule and
# quote-check versions; Versions gives the build and each model's seed beside its SHA-256.
# 0.6.0 (#89): a forwarded record's warning names its original author, as a cited span, when the
# extraction names one.
# 0.7.0: Versions says whether forwarded marks are on the record or, in a case made before
# contracts 0.4.0, only in the coverage list (no original author is named there).
# 0.8.0 (rules 0.3.0): a claim whose model contradiction waits for the expert prints
# "Contradiction found, confirm to finalize", like the screen; Versions names the claim types
# whose model contradictions count without an expert, and the probe run that qualified each.
# 0.9.0: Versions names each source's importer and its version; a forwarded or quoted copy
# imported from inside another message gets its own note (core/ingest/forwarded.record_note),
# and the conversation and timeline label it as a copy.
# 0.10.0: an unproven claim the expert has not overridden says why in plain words, one line per
# kind of core assumption not covered, or a pointer to the other rule that holds it
# (core/review/status.ClaimState.explain_lines), the same lines as the screen; any verdict a later
# change made stale says "Not current".
# 0.11.0 (#104): a scoped reproducibility bundle's report says what the bundle left out, counts
# the items left out under each claim, and leaves out the sections that read the whole phone.
# 0.12.0 (#111): an Examiner activity section (page views per claim, core/review/activity.py),
# its table opt-in per case and off by default; page views are left out of the expert-actions
# table and counts.
# 0.13.0: the product is named Mabillon (formerly Baker) in the title, top line, Versions and
# every sentence that names the tool. Nothing else changed.
# 0.14.0: each decided claim traces its verdict ("How this verdict was reached": per core
# assumption, the evidence, check or stipulation relied on, who proposed it and what the expert
# did), and a "What can be checked again" section says what can and cannot be regenerated,
# naming any hosted model whose labels cannot be regenerated exactly.
# 0.15.0: for a local model file and stance prompt that passed the repeat check (REPEAT_TESTED),
# "What can be checked again" states that measured result and its limits instead of making no
# claim.
# 0.16.0: a stance rationale that uses a forbidden word no longer refuses the whole report: it is
# withheld from its row, which names the word and marks the item as needing expert review, and
# a "Withheld model rationales" section lists each one with its SHA-256 and the expert's
# acknowledgment (core/review/withheld.py). Also counts #137's change: import coverage says
# "record state" for related copies.
REPORT_VERSION = "0.16.0"


@dataclass(frozen=True)
class BundleScope:
    """What a scoped reproducibility bundle (core/bundle/export.py) left out, so the report
    rendered from its rows says so. `included`: the opt-in parts it holds (export.PARTS);
    `left_out`: rows left out, by table; `withheld_log`: the audit-log entries left out, by
    seq, each with its time, actor, action, prev_hash and hash (their payloads stay out)."""

    included: tuple[str, ...]
    left_out: dict[str, int]
    withheld_log: dict[int, dict[str, str]]

    @property
    def whole_phone(self) -> bool:
        return "records" in self.included


__all__ = [
    "AWAITING_EXPERT",
    "CONTRADICTION_FOUND",
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
p.warn { background: var(--unp-bg); border: 1px solid var(--unp-line); border-radius: 10px;
  padding: 10px 14px; color: #4a3608; }
strong.warn { color: var(--unp); }
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
.v-confirm { color: var(--con); background: var(--con-bg); border: 1px dashed var(--con); }
.v-confirm::before { content: "✕"; }
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
    """A reason or note an expert typed, as they wrote it. Never for Mabillon's or a model's
    text."""
    return f'<span class="said">{html.escape(str(text))}</span>'


def e(text: object) -> str:
    return html.escape("" if text is None else str(text))


def withheld_word(word: str) -> str:
    """The forbidden word a withheld rationale used, named in the notice in its place. The word
    check (invariants.WITHHELD_WORD) passes this element only around one forbidden word."""
    return f'<span class="withheld-word">{html.escape(word)}</span>'


def rationale_html(item: EvidenceItem, withheld: Withheld | None) -> str:
    """The model's rationale as the report and the screen show it, or, when it uses a forbidden
    word (core/review/withheld.py), the notice that stands in for it."""
    if withheld is None:
        return f"Model rationale (inferred): {e(forwarded.shown_rationale(item.rationale))}"
    ack = (
        f"Acknowledged by {e(withheld.acknowledged_by)} (audit log entry "
        f"{withheld.acknowledged_seq})."
        if withheld.acknowledged
        else "Not yet acknowledged by the expert."
    )
    return (
        "<strong>Rationale withheld; needs expert review.</strong> The model's rationale uses "
        f"the word {withheld_word(withheld.word)}, which Mabillon does not print, so it is not "
        "shown. Read the record and the quote yourself. The stance, the quote and its check are "
        "as stored, and no verdict rule reads a rationale. Rationale SHA-256 "
        f"<span class='mono'>{e(withheld.sha256)}</span>. {ack}"
    )


def withheld_section(states: list[ClaimState]) -> str:
    """Every withheld rationale in the report, under the claim it belongs to, irrelevant items
    included; the same count as the case overview."""
    rows = [(st, w) for st in states for w in st.withheld]
    if not rows:
        return ""
    stance = {x.id: x.stance for st in states for x in st.evidence}
    out = [
        "<h2>Withheld model rationales</h2>",
        f"<p>{e(withheld_summary([w for _st, w in rows]))} The expert acknowledges each one "
        "before confirming or overriding the claim's verdict; each acknowledgment is an audit-log "
        "entry naming the item, the word and the SHA-256 of the rationale, never its text.</p>",
        "<table><thead><tr><th>Claim</th><th>Evidence item</th><th>Stance</th><th>Word</th>"
        "<th>Rationale SHA-256</th><th>Acknowledged</th></tr></thead>",
    ]
    for st, w in rows:
        ack = (
            f"by {e(w.acknowledged_by)} (audit log entry {w.acknowledged_seq})"
            if w.acknowledged
            else "not yet"
        )
        out.append(
            f"<tr><td>{e(st.name)}</td><td class='mono'>{e(w.evidence_id)}</td>"
            f"<td>{STANCE_LABEL[stance[w.evidence_id]]}</td><td>{withheld_word(w.word)}</td>"
            f"<td class='mono'>{e(w.sha256)}</td><td>{ack}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


def verdict_label(
    decision: VerdictDecision, awaiting: bool = False, contradiction: bool = False
) -> tuple[str, str]:
    """(display text, css class). Kept here for callers of the report module."""
    return _verdict_label(decision, awaiting, contradiction)


HOSTED = (
    "Labels from a hosted model ({vendor}, {model}). They cannot be regenerated exactly; the "
    "recorded labels and rules are reproducible."
)


def labelled_by(conn: sqlite3.Connection, model_run_id: str | None) -> str:
    """Which model labeled an evidence item, in plain words: its name, cloud or local."""
    if not model_run_id:
        return "Labeled without a model"
    row = conn.execute(
        "SELECT model_name, model_sha256 FROM model_runs WHERE id = ?", (model_run_id,)
    ).fetchone()
    if row is None:
        return "Labeled by an unrecorded model run"
    where = "cloud" if is_cloud_sha(row[1]) else "local"
    return f"Labeled by {row[0]} ({where})"


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


def _latest_review(conn: sqlite3.Connection, evidence_id: str) -> tuple | None:
    return conn.execute(
        "SELECT reviewer_kind, reviewer, status, reason, decided_at_utc FROM evidence_reviews"
        " WHERE evidence_id = ? ORDER BY seq DESC LIMIT 1",
        (evidence_id,),
    ).fetchone()


def _expert_step(conn: sqlite3.Connection, x: EvidenceItem, decided_at: datetime) -> str:
    """What happened to a model's label after it was proposed, as the trace says it."""
    r = _latest_review(conn, x.id)
    if r is None:
        return "Not reviewed: model proposed, no expert has decided it"
    kind, who, status, _reason, at = r
    at = datetime.fromisoformat(at.replace("Z", "+00:00"))
    later = " (after this verdict was decided)" if at > decided_at else ""
    if kind == "expert":
        what = {
            "accepted": "Expert confirmed",
            "dismissed": "Expert dismissed",
            "open": "Expert reopened",
        }[status]
        return f"{what}: {e(who)}{later}"
    if status == "ai_accepted":
        return f"Local AI reviewer accepted; not confirmed by an expert{later}"
    return f"Local AI reviewer dismissed; no expert has decided it{later}"


def verdict_trace(conn: sqlite3.Connection, st: ClaimState) -> str:
    """How a decided claim's verdict was reached, per core assumption: each evidence item, check
    or stipulation the rules relied on, or, for an assumption not covered, what was found for it
    and not relied on; with who proposed each and what the expert did. Read from the verdict's
    coverage and cited ids (rules.py); review status is as it is now."""
    decision = st.decision
    if decision is None:
        return ""
    evidence = {x.id: x for x in st.evidence}
    checks = {c.id: c for c in st.checks}
    stips = {s.id: s for s in pipeline.load_stipulations(conn)}
    assumptions = {a.id: a for a in st.assumptions}

    def row(label: str, cited: str, relied: bool = True) -> str:
        if cited in evidence:
            x = evidence[cited]
            what = (
                f"Evidence <a href='#{e(x.id)}' class='mono'>{e(x.id)}</a>: "
                f"{STANCE_LABEL[x.stance]}, record <span class='mono'>{e(x.record_id)}</span>"
            )
            who = f"{e(labelled_by(conn, x.model_run_id))}: model proposed"
            step = _expert_step(conn, x, decision.decided_at_utc)
        elif cited in checks:
            c = checks[cited]
            what = f"Check {e(c.check_name)} {e(c.check_version)}: {e(c.outcome.value)}"
            who = "Code (deterministic, no model)"
            step = "None needed: a code result anyone can re-run"
        elif cited in stips:
            s = stips[cited]
            what = f"Stipulation: {q(s.statement)}"
            who = "The expert"
            step = f"Expert {e(s.status.value)}: {e(s.decided_by or 'not decided')}"
        else:
            what, who, step = f"<span class='mono'>{e(cited)}</span>", "not recorded", ""
        lead = "Relied on" if relied else "Found, not relied on"
        return (
            f"<tr><td>{label}</td><td>{lead}</td><td>{what}</td><td>{who}</td><td>{step}</td></tr>"
        )

    def found_for(assumption_id: str) -> list[str]:
        """What the run found for an assumption, in id order: its checks, then its evidence
        items not labeled irrelevant."""
        ids = [c.id for c in st.checks if c.assumption_id == assumption_id]
        return ids + [
            x.id
            for x in st.evidence
            if x.assumption_id == assumption_id and x.stance != Stance.IRRELEVANT
        ]

    cited_by_verdict = set(
        decision.cited_evidence_ids + decision.cited_check_ids + decision.cited_stipulation_ids
    )
    rows: list[str] = []
    listed: set[str] = set()
    for cv in decision.coverage:
        a = assumptions.get(cv.assumption_id)
        label = e(a.text) if a else f"<span class='mono'>{e(cv.assumption_id)}</span>"
        tier = cv.tier.value if cv.tier else "?"
        covered = f"covered at {e(tier)}" if cv.covered else "not covered"
        label += f"<br><span class='muted'>{covered}</span>"
        for cited in cv.cited_ids:
            rows.append(row(label, cited))
            listed.add(cited)
        if not cv.covered:
            found = [i for i in found_for(cv.assumption_id) if i not in listed]
            # a failed check or a confirmed contradiction the verdict cites (rule 1) was relied on
            rows.extend(row(label, i, relied=i in cited_by_verdict) for i in found)
            listed.update(found)
            if not cv.cited_ids and not found:
                rows.append(
                    f"<tr><td>{label}</td><td>Nothing found</td><td></td><td></td><td></td></tr>"
                )
    others = decision.cited_evidence_ids + decision.cited_check_ids + decision.cited_stipulation_ids
    for cited in others:
        if cited in listed:
            continue
        listed.add(cited)
        x = evidence.get(cited)
        c = checks.get(cited)
        aid = x.assumption_id if x else c.assumption_id if c else None
        a = assumptions.get(aid) if aid else None
        rows.append(row(e(a.text) if a else "Cited by the verdict", cited))
    out = [
        "<h4>How this verdict was reached</h4>",
        "<p class='muted'>Models propose labels; the verdict rules decide (rules "
        f"{e(decision.rule_version)}); an expert confirms. Review status is shown as it is "
        "now.</p>",
    ]
    if decision.override_note:
        out.append(
            "<p class='muted'>The expert set this verdict by override, with the note above. The "
            "rows show what the rules found.</p>"
        )
    if not rows:
        out.append("<p class='muted'>The verdict relies on no evidence, check or stipulation.</p>")
        return "".join(out)
    out.append(
        "<table><thead><tr><th>Core assumption</th><th></th><th>Evidence, check or stipulation"
        "</th><th>Proposed by</th><th>Expert step</th></tr></thead>" + "".join(rows) + "</table>"
    )
    return "".join(out)


# Local stance runs that passed the repeat check (eval/probe/repeat_check.py), by model file
# SHA-256 and stance prompt SHA-256 as model runs record them. Only these get a statement about
# re-runs; the run itself is in eval/probe/results/.
REPEAT_TESTED = {
    (
        "500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0",  # Qwen3-14B Q4_K_M
        "4c35f1cf01b0b2277135bafe52d996f903f3bca3fc5a37c8e8996aedc35a2034",  # stance v1.1
    ): (
        "In Mabillon's repeat test of this model file with this stance prompt (2026-10-24, one "
        "MacBook Air M4, macOS 15.6.1, llama-cpp-python 0.3.36), asking again, loading the model "
        "afresh and auditing a synthetic case a second time gave byte-identical answers on the "
        "GPU. With the GPU off, every stance and quote was the same but 7 of 20 rationales were "
        "worded differently. Other machines and runtime versions have not been tested."
    ),
}


def regeneration(conn: sqlite3.Connection, run: dict | None) -> str:
    """What a reader can regenerate from this case and what they cannot: the verdicts re-derive
    from the record; a hosted model's labels cannot be regenerated exactly."""
    out = ["<h2>What can be checked again</h2><ul>"]
    if run:
        out.append(
            f"<li>Every verdict re-derives from the recorded labels, check results and expert "
            f"decisions under rules {e(run['rule_version'])}. A reproducibility bundle "
            "(made with <span class='mono'>export-bundle</span>, checked with "
            "<span class='mono'>verify-bundle</span>) lets another examiner check that "
            "offline.</li>"
        )
    seen: set[tuple[str, str, str | None]] = set()
    for purpose, name, sha, prompt_sha, params_json, seed in conn.execute(
        "SELECT purpose, model_name, model_sha256, prompt_sha256, params_json, seed"
        " FROM model_runs ORDER BY purpose, id"
    ):
        params = json.loads(params_json or "{}")
        tested = REPEAT_TESTED.get((sha, prompt_sha)) if purpose == "stance" else None
        key = (purpose, sha, tested)
        if key in seen:
            continue
        seen.add(key)
        if is_cloud_sha(sha):
            model = str(params.get("api_model") or name)
            text = HOSTED.format(vendor="Anthropic", model=model)
            out.append(f"<li><strong>{e(purpose.capitalize())}:</strong> {e(text)}</li>")
        elif params.get("stand_in"):
            out.append(
                f"<li><strong>{e(purpose.capitalize())}:</strong> labels from a stand-in "
                f"({e(name)}), not a model. They are not findings.</li>"
            )
        else:
            out.append(
                f"<li><strong>{e(purpose.capitalize())}:</strong> labels from the local model "
                f"{e(name)} (file SHA-256 <span class='mono'>{e(sha)}</span>, seed "
                f"{e(seed) if seed is not None else 'not recorded'}; settings under Model runs)."
                " Anyone with the same file can run it again. "
                + (
                    f"{e(tested)} The verdicts rest on the recorded labels.</li>"
                    if tested
                    else "No claim is made that a re-run gives identical labels; the verdicts "
                    "rest on the recorded labels.</li>"
                )
            )
    if len(out) == 1:
        out.append("<li>No audit has run and no model run is recorded.</li>")
    out.append("</ul>")
    return "".join(out)


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
                f"{q(st.statement)} Mabillon did not verify who used the phone. Every finding that "
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
            "Mabillon did not verify it. Every check that ties this person to that account rests "
            "on it.</li>"
        )
    for s in srcs:
        if s[2] == Fidelity.CURATED_REPORT.value:
            items.append(
                f"<li>{q(s[4])} is an examiner-curated report. Records the examiner left out "
                "were not available to Mabillon, so no absence finding can rest on it.</li>"
            )
        elif s[2] == Fidelity.UNKNOWN.value and s[1] != "govdoc":
            items.append(
                f"<li>The coverage of {q(s[4])} is not known, so no absence finding can rest "
                "on it.</li>"
            )
    for cov in import_coverage.summaries(conn):
        if cov.format_unverified and cov.importer == "axiom":
            items.append(
                f"<li><strong>{q(cov.file_name)} was read with Mabillon's Magnet AXIOM reader, "
                "which is not yet verified against a real AXIOM export.</strong> It was built from "
                "public descriptions of AXIOM's report exports and tested on synthetic exports "
                "only. Each record cited from this file should be compared with the same record "
                "in AXIOM Examine before it is relied on.</li>"
            )
        elif cov.format_unverified:
            items.append(
                f"<li><strong>{q(cov.file_name)} was read with Mabillon's UFDR reader, which is "
                "not yet verified against a real UFDR.</strong> It was built from Cellebrite's "
                "public descriptions of the format and tested on synthetic packages only. Each "
                "record cited from this file should be compared with the same record in "
                "Cellebrite Reader before it is relied on.</li>"
            )
        attention = [i for i in cov.attention if i.code != "format_unverified"]
        if attention:
            lis = "".join(f"<li>{import_coverage.render(i, q, e)}</li>" for i in attention)
            items.append(
                f"<li>Mabillon did not read all of {q(cov.file_name)}: {e(cov.headline)} Records "
                "in the parts listed here are not in the evidence Mabillon reviewed, and times it "
                f"could not read are not used.<ul>{lis}</ul></li>"
            )
    items += [
        f"<li><strong>{SUPPORTED_EXPERT}</strong> means an expert accepted every supporting "
        "item the finding stands on. "
        f"<strong>{SUPPORTED_AI}</strong> would mean a local AI reviewer accepted the "
        "supporting evidence and no human expert has confirmed it; under the current rules no "
        "claim reaches supported on AI review alone.</li>",
        f"<li><strong>{AWAITING_EXPERT}</strong> means Mabillon found records it reads as "
        "supporting the claim and no expert has accepted or dismissed them yet. Until an expert "
        "does, the verdict is unproven. The labels are model output and can be wrong, so the "
        "expert checks each item. The local AI reviewer's acceptances only sort evidence for "
        "the expert; they never make a claim supported.</li>",
        f"<li><strong>{CONTRADICTION_FOUND}</strong> means Mabillon found records it reads as "
        "contradicting a core assumption of the claim. A contradiction found by the stance "
        "labeler counts once an expert confirms it, with a reason recorded in the audit log; "
        "until then the verdict is unproven. A failed deterministic check contradicts a claim "
        "without this step.</li>",
        "<li>Unproven means the evidence Mabillon reviewed does not establish the claim. It does "
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


def claim_record_ids(st: ClaimState) -> list[str]:
    """The records a claim's shown evidence and its checks rest on."""
    ids = [x.record_id for x in st.evidence if x.stance != Stance.IRRELEVANT]
    return ids + [r for c in st.checks for r in c.record_ids]


def forwarded_warning(conn: sqlite3.Connection, st: ClaimState) -> str:
    """A warning when the claim rests on forwarded messages (core/ingest/forwarded.py)."""
    text = forwarded.claim_warning(forwarded.affected(conn), claim_record_ids(st))
    return f"<p class='warn'><strong>Forwarded messages.</strong> {e(text)}</p>" if text else ""


def record_line(
    conn: sqlite3.Connection, record_id: str, found: dict[str, str] | None = None
) -> str:
    note = (found or {}).get(record_id)
    if note:
        # cited parts are the source's text (a sender or author as written)
        parts = forwarded.record_note(conn, record_id, note)
        warning = "".join(q(t) if cited else e(t) for t, cited in parts)
        return f"{record_line(conn, record_id)}<br><strong class='warn'>{warning}</strong>"
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


def _claim_block(
    conn: sqlite3.Connection,
    st: ClaimState,
    case: explain.Case | None,
    left_out: int = 0,
) -> str:
    """One claim. `case` is None in a scoped bundle's report that holds only the records the
    verdicts cite, so the parts that read the whole phone are left out; `left_out` counts the
    claim's evidence items that bundle left out."""
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
    out.extend(
        f"<p class='gap'><strong>{e(topic)}:</strong> {e(text)}</p>"
        for topic, text in st.explain_lines()
    )
    out.append(forwarded_warning(conn, st))
    found = forwarded.affected(conn)
    if st.awaiting_expert:
        out.append(
            f"<p>Mabillon found supporting evidence: {st.ai_accepted} item(s) accepted by the "
            f"local AI reviewer and {st.open_support} not reviewed, waiting for an expert to agree "
            "or disagree. Until an expert accepts the key evidence, the claim stays unproven.</p>"
        )
    if st.contradiction_found:
        out.append(f"<p>{e(CONFIRM_STEP.format(n=st.open_contradicts))}</p>")
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
        if case is not None:
            held = "".join(f"<li>{e(h)}</li>" for h in case_holdings(conn))
            out.append(f"<p>{e(HOLDINGS)}</p><ul>{held or '<li>No extraction imported.</li>'}</ul>")

    shown = [x for x in st.evidence if x.stance != Stance.IRRELEVANT]
    hidden = len(st.evidence) - len(shown)
    if shown:
        out.append(
            "<table><thead><tr><th>Evidence</th><th>Stance</th><th>Tier</th><th>Review</th>"
            "<th>Source</th></tr></thead>"
        )
        withheld = {w.evidence_id: w for w in st.withheld}
        for x in shown:
            out.append(
                f"<tr id='{e(x.id)}'><td><blockquote>{q(x.quote)}</blockquote>"
                f"{record_line(conn, x.record_id, found)}"
                f"<br><span class='muted'>{e(labelled_by(conn, x.model_run_id))}. "
                f"{rationale_html(x, withheld.get(x.id))}</span>"
                f"</td><td>{STANCE_LABEL[x.stance]}</td><td>{display_tier(x).value}</td>"
                f"<td>{review_label(conn, x)}</td>"
                f"<td class='mono'>{e(x.ref.source_id)} {e(x.ref.locator)}<br>{e(x.record_id)}"
                "</td></tr>"
            )
        out.append("</table>")
    elif decision is not None:
        out.append("<p class='muted'>No relevant evidence items were stored for this claim.</p>")
    out.append(verdict_trace(conn, st))
    if hidden:
        out.append(f"<p class='muted'>{hidden} retrieved records were labeled irrelevant.</p>")
    if left_out:
        out.append(
            f"<p class='muted'>{left_out} evidence items (dismissed, or labeled irrelevant) are "
            "left out of this bundle by its scope. No verdict rests on them; the audit log's "
            "digest still names each one by its hash.</p>"
        )
    # Leads are worked out from the run's assumptions; after an edit they would describe the old
    # claim, so they wait for a re-run (the claim already says to re-run it).
    if case is not None and st.assumptions and not st.incomplete and not st.edited_after_run:
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


def audit_log_summary(
    conn: sqlite3.Connection, withheld: dict[int, dict[str, str]] | None = None
) -> dict:
    """The log in numbers. `withheld`: entries a scoped bundle left out (BundleScope), counted
    by their time, actor and action, as the bundle lists them."""
    withheld = withheld or {}
    rows = [
        (seq, at, actor, action, h)
        for seq, at, actor, action, h in conn.execute(
            "SELECT seq, at_utc, actor, action, hash FROM audit_log"
        )
    ]
    rows += [
        (seq, w.get("at_utc"), w.get("actor"), w.get("action"), w.get("hash"))
        for seq, w in withheld.items()
    ]
    rows.sort(key=lambda r: r[0])
    expert = [r for r in rows if str(r[2]).startswith("expert:") and r[3] != activity.VIEW]
    runs = Counter(s for (s,) in conn.execute("SELECT status FROM pipeline_runs"))
    return {
        "entries": len(rows),
        "first_at": rows[0][1] if rows else None,
        "last_at": rows[-1][1] if rows else None,
        "last_hash": rows[-1][4] if rows else "",
        "chain_ok": audit_log.verify_chain(conn, withheld),
        "expert_actions": dict(sorted(Counter(r[3] for r in expert).items())),
        "experts": sorted({r[2] for r in expert}),
        "runs": dict(sorted(runs.items())),
        "withheld": dict(sorted(Counter(str(w.get("action")) for w in withheld.values()).items())),
        "page_views": sum(1 for r in rows if r[3] == activity.VIEW),
    }


def quote_check_label(run: dict) -> str:
    """The quote check the run's evidence passed (core.audit.quotes.VERSION). Runs before 1.2.0
    did not record it."""
    return (run.get("config") or {}).get("quote_check") or "not recorded (1.1.0 or earlier)"


def build_label(run: dict) -> str:
    """The Mabillon release and git commit the run used (core.build). Runs before #91 did not
    record them; their "Mabillon pipeline" version alone cannot tell two builds apart. A rules-only
    re-run also names the build its evidence came from, when that differs."""
    return build.run_label(run.get("config") or {})


def forwarded_label(conn: sqlite3.Connection) -> str:
    """Where the case keeps forwarded marks. A case made before contracts 0.4.0 has no forwarded
    columns: forwarded messages its imports listed still fail closed, from the coverage list, but
    no original author is named. An import made before that list existed (#73) recorded no list,
    and nothing tells it apart from an import that found no forwarded messages, so the label
    says so rather than promise the fail-closed path."""
    if forwarded.has_columns(conn):
        return "on the record, with the original author when the extraction names one"
    return (
        "coverage list only (case made before contracts 0.4.0): listed forwarded messages fail "
        "closed, but no original author is named. A source imported before Mabillon listed "
        "forwarded messages (#73) has no list, so its forwarded messages are not marked; "
        "re-import it to check"
    )


def auto_contradict_label(run: dict | None) -> str:
    """Which claim types a model's contradiction marks contradicted with no expert (rule 1b),
    and the probe run that qualified each, under the current rules."""
    auto = rules.auto_contradict()
    if auto:
        types = sorted(auto, key=lambda t: t.value)
        text = "; ".join(f"{t.value} claims (qualified by {auto[t]})" for t in types)
    else:
        text = "none: every model contradiction counts once an expert confirms it"
    text = f"{text} (rules {rules.RULE_VERSION})"
    if run and run.get("rule_version") != rules.RULE_VERSION:
        text += (
            f". This audit was decided under rules {run.get('rule_version')}; re-run the verdicts "
            "to apply the current rules"
        )
    return text


def _versions(conn: sqlite3.Connection, run: dict | None) -> str:
    rows = [("Report", REPORT_VERSION), ("Other explanations (code)", explain.VERSION)]
    if run:
        rows += [
            ("Mabillon build", build_label(run)),
            ("Mabillon pipeline", run["baker_version"]),
            ("Contracts", run["contracts_version"]),
            ("Verdict rules", run["rule_version"]),
            ("Quote check", quote_check_label(run)),
        ]
        cloud = (run.get("config") or {}).get("cloud")
        if isinstance(cloud, dict):
            rows.append(("Stance labels", str(cloud.get("why", ""))))
    for sid, name, version in conn.execute(
        "SELECT source_id, importer, importer_version FROM source_coverage ORDER BY source_id"
    ):
        rows.append((f"Importer for {sid}", f"{name} {version}"))
    rows.append(("Forwarded marks", forwarded_label(conn)))
    rows.append(("Model contradictions without an expert", auto_contradict_label(run)))
    model_rows = list(
        conn.execute(
            "SELECT purpose, model_name, model_sha256, prompt_version, seed FROM model_runs"
            " ORDER BY purpose, id"
        )
    )
    out = ["<table><thead><tr><th>Part</th><th>Version</th></tr></thead>"]
    out += [f"<tr><td>{e(k)}</td><td class='mono'>{e(v)}</td></tr>" for k, v in rows]
    for purpose, name, sha, prompt, seed in model_rows:
        out.append(
            f"<tr><td>Model for {e(purpose)}</td><td class='mono'>{e(name)}, prompt "
            f"{e(prompt)}, SHA-256 {e(sha)}, seed "
            f"{e(seed) if seed is not None else 'not recorded'}</td></tr>"
        )
    if not model_rows:
        out.append("<tr><td>Models</td><td>No model run is recorded.</td></tr>")
    out.append("</table>")
    return "".join(out)


def render_report(
    conn: sqlite3.Connection,
    timeline: timeline_html.Settings | None = None,
    scope: BundleScope | None = None,
) -> str:
    """timeline: the case's timeline settings (core/timeline/settings.py); defaults if None.
    scope: set when rendering a scoped reproducibility bundle's rows (core/bundle/export.py)."""
    srcs = sources(conn)
    run = pipeline.view_run(conn)
    govdocs = [r[0] for r in conn.execute("SELECT title FROM govdocs ORDER BY id")]

    states = claim_states(conn, run=run)
    tally = Counter(st.label for st in states)

    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Mabillon claims report</title>"
        f"<style>{CSS}{restore_html.CSS}{timeline_html.CSS}{selection_html.CSS}{paired_html.CSS}"
        f"{alternatives_html.CSS}</style>"
        "</head><body>",
        "<h1>Mabillon claims report</h1>",
        "<p class='muted'>"
        + (" · ".join(q(t) for t in govdocs) or "No government document imported")
        + f" · report {REPORT_VERSION}"
        + (
            f" · Mabillon {e(build_label(run))} · pipeline {e(run['baker_version'])}"
            f" · rules {e(run['rule_version'])}"
            f" · quote check {e(quote_check_label(run))}"
            if run
            else ""
        )
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
        found = sum(1 for st in states if st.contradiction_found)
        if found:
            parts.append(
                f"<div class='banner'><strong>{found} claim(s): {e(CONTRADICTION_FOUND)}."
                "</strong> Each becomes contradicted once an expert confirms the contradicting "
                "record.</div>"
            )
        waiting = sum(st.withheld_waiting for st in states)
        if waiting:
            parts.append(
                f"<div class='banner'><strong>{waiting} model rationale(s) withheld and not yet "
                "acknowledged by the expert.</strong> Each uses a word Mabillon does not print; "
                "the items are listed under Withheld model rationales.</div>"
            )

    if scope is not None:
        parts.append(scope_banner(scope))
    parts.append("<h2>Summary</h2><table><thead><tr><th>Finding</th><th>Claims</th></tr></thead>")
    for label, n in sorted(tally.items()):
        parts.append(f"<tr><td>{e(label)}</td><td>{n}</td></tr>")
    parts.append("</table>")
    parts.append(withheld_section(states))

    parts.append(_limitations(conn, srcs))
    parts.append("<h2>Claims</h2>")
    whole = scope is None or scope.whole_phone
    case = explain.load(conn) if whole else None
    manifest = (run or {}).get("manifest", {})
    for st in states:
        named = len(set((manifest.get(st.claim.id) or {}).get("evidence", [])))
        left = max(named - len(st.evidence), 0) if scope is not None and st.decision else 0
        parts.append(_claim_block(conn, st, case, left))

    parts.append(searches_section(states, srcs))
    timeline = timeline or timeline_html.Settings()
    if whole:
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

    parts.append(regeneration(conn, run))
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
            f"<p>Run {e(run['run_id'])}, started {e(run['started_at_utc'])}. Mabillon "
            f"{e(build_label(run))}, pipeline {e(run['baker_version'])}, contracts "
            f"{e(run['contracts_version'])}, rule version "
            f"{e(run['rule_version'])}, quote check {e(quote_check_label(run))}. "
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

    summary = audit_log_summary(conn, scope.withheld_log if scope else None)
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
    if summary["withheld"]:
        parts.append(
            "<p>Left out of this bundle by its scope, kept in the chain by their hashes: "
            + e(", ".join(f"{k} {v}" for k, v in summary["withheld"].items()))
            + ". The expert actions below are the ones the bundle holds.</p>"
        )
    expert_rows = list(
        conn.execute(
            "SELECT seq, at_utc, actor, action, payload_json FROM audit_log"
            " WHERE actor LIKE 'expert:%' AND action != ? ORDER BY seq",
            (activity.VIEW,),
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
                f"<td>{q(_compact(r[4], r[3]))}</td></tr>"
            )
        parts.append("</table>")
    parts.append(activity_section(conn, scope))
    parts.append("</body></html>")
    return "".join(parts)


def activity_section(conn: sqlite3.Connection, scope: BundleScope | None = None) -> str:
    """The examiner's activity per claim, from the page views in the audit log
    (core/review/activity.py): how often each claim and its evidence were opened, when, and time
    on those pages, when the case includes it (activity.in_report, off by default). Read from
    the audit log alone, so a bundle's report renders it from the rows it ships."""
    out = ["<h2>Examiner activity</h2>"]
    if not activity.in_report(conn):
        out.append(
            "<p>Not included. This case leaves examiner activity (pages opened and time on "
            "them) out of the report, as Mabillon does unless the expert includes it. The audit "
            "log keeps every page view.</p>"
        )
        return "".join(out)
    if scope is not None and "activity" not in scope.included:
        out.append(
            "<p>The case includes examiner activity in its report, but this bundle leaves out "
            "the page views (the activity part), so it is not shown here.</p>"
        )
        return "".join(out)
    trail = activity.steps(conn)
    total = activity.summary(trail)
    idle = int(activity.IDLE.total_seconds() // 60)
    if not total["views"]:
        out.append(
            "<p>No page views are recorded for this case: it was reviewed before Mabillon recorded "
            "them, or only from the command line.</p>"
        )
        return "".join(out)
    out.append(
        f"<p>{total['views']} page views in {total['sessions']} screen session"
        f"{'s' if total['sessions'] != 1 else ''} by {e(', '.join(total['examiners']))}, from "
        f"{e(total['first_at'])} to {e(total['last_at'])}, recorded in the audit log above. "
        "Time on page runs from opening a page to the next page opened on the same screen; the "
        "screen runs no scripts, so it does not show what was read. Stretches over "
        f"{idle} minutes may include time away, and pages whose end was not recorded are not "
        "timed; both are counted apart. The full trail is the "
        "review screen's Activity page and its CSV download.</p>"
    )
    per = activity.by_claim(trail)
    claims = [
        cid
        for (cid,) in conn.execute("SELECT id FROM claims WHERE status != 'removed' ORDER BY id")
    ]
    out.append(
        "<table><thead><tr><th>Claim</th><th>Times opened</th><th>First opened (UTC)</th>"
        "<th>Last opened (UTC)</th><th>Time on its pages</th><th>Evidence items opened</th>"
        "<th>Expert actions</th></tr></thead>"
    )
    for cid in claims:
        a = per.get(cid)
        if a is None or not (a.opened or a.evidence_opened):
            out.append(
                f"<tr><td>{e(cid)}</td><td>0</td><td colspan='4'>not opened</td>"
                f"<td>{a.actions if a else 0}</td></tr>"
            )
            continue
        out.append(
            f"<tr><td>{e(cid)}</td><td>{a.opened}</td><td>{e(a.first_at or '')}</td>"
            f"<td>{e(a.last_at or '')}</td><td>{e(activity.time_on_pages(a))}</td>"
            f"<td>{len(a.evidence_opened)}</td><td>{a.actions}</td></tr>"
        )
    out.append("</table>")
    return "".join(out)


# Expert flags (core/review/flags.py) are feedback about Mabillon, not findings: the report names
# each one but leaves out the expert's note, the record they named and the snapshot.
FLAG_FIELDS_IN_REPORT = ("flag_id", "claim_id", "kind", "evidence_id", "should_be")


def _compact(payload_json: str, action: str = "") -> str:
    try:
        p = json.loads(payload_json)
    except ValueError:
        return payload_json
    if action.startswith("flag.") and isinstance(p, dict):
        p = {k: p[k] for k in FLAG_FIELDS_IN_REPORT if k in p}
    return "; ".join(f"{k}: {v}" for k, v in p.items() if v not in (None, ""))


SCOPE_PARTS = {
    "dismissed": "evidence items dismissed when their verdict was decided, with their reviews",
    "irrelevant": "evidence items the model labeled irrelevant",
    "prompts": "model prompts and answers no shown evidence item or AI review rests on",
    "records": "the rest of the phone: records no verdict cites",
    "history": "earlier audit runs' rows",
    "feedback": "the expert's flags about Mabillon",
    "activity": "the examiner's page views",
}


def scope_banner(scope: BundleScope) -> str:
    """What a scoped bundle holds and leaves out, at the top of its report."""
    out = [k for k in SCOPE_PARTS if k not in scope.included]
    rows = ", ".join(f"{t} {n}" for t, n in sorted(scope.left_out.items()) if n)
    return (
        "<div class='banner'><strong>Scoped reproducibility bundle.</strong> This report is "
        "rendered from the bundle's rows, which hold what the verdicts rest on. Left out by the "
        "examiner's choice of scope: "
        + e("; ".join(SCOPE_PARTS[k] for k in out) or "nothing")
        + (f" (rows: {e(rows)})" if rows else "")
        + (
            ". The timeline, restore, selection, holdings and other-explanations sections read "
            "the whole phone, so they are not shown"
            if not scope.whole_phone
            else ""
        )
        + ".</div>"
    )


def stand_in_banner(run: dict) -> str:
    """The banner for a run that used eval stand-ins. The demo case (eval/demo.py) says
    exactly what was scripted; any other stand-in run is a test run."""
    if pipeline.scripted_demo(run):
        return (
            "<div class='banner'><strong>Demo case: synthetic data, scripted labels.</strong> "
            "Every name and message here is fictional. So the demo opens in seconds, no model "
            "ran: the evidence labels and most expert decisions were scripted from the signed "
            "answer key. The checks, quote checks and verdict rules are Mabillon's own. On a real "
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
