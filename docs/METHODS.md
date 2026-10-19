# Baker: methods note

How Baker reaches each finding, for an examiner who uses it and may need to describe it. This note
describes Baker as it is on `main` (verdict rules 0.2.2, as of 2026-10-16). Every report names the
rule version, quote-check version, prompt versions and model file that produced it; read this note against those.

Baker is a tool that helps an examiner check claims. It does not replace the examiner's own review
of the source data, and nothing in a Baker report is an opinion. Any opinion is the examiner's.

This note contains no accuracy figures. Baker has been measured only on synthetic data, and no
figure will be published until it has been measured on real extractions.

## 1. What Baker does

Baker reads a government document (an affidavit or a report) and the phone extraction reports it
relies on. It splits the document into individual factual claims and tests each one against the
extraction data. Each claim the audit finishes ends **Supported**, **Contradicted** or **Unproven**,
with the records it rests on and the reasons, in words. A claim a stopped or crashed run did not
finish has no verdict and shows "Labeling incomplete" until the run resumes.

## 2. The flow: claim, assumption, check, rules

**Import.** Each input file (Cellebrite Excel, PDF or UFDR; Magnet AXIOM XML or Excel; the
government PDF) is opened read-only and SHA-256 hashed. Every record Baker stores carries a
`source_ref` pointing to where it came from in that file (a sheet and row, a page and table cell,
or an XML locator). Times are stored in UTC with the original offset and the raw value as printed.
Each phone-report import records its **coverage**: whether the source is a full extraction or an
examiner-curated report, and complete counts of what the importer skipped or could not read, with
the locations of up to 50 per reason (a longer list is cut off, and the count shows by how much).
The government PDF has no coverage record (the setup page shows "not applicable"): text the
reader drops, such as page furniture, is not counted.

**Claims.** The local language model proposes atomic claims, one paragraph at a time. The examiner
accepts, edits or removes each one and may add their own. The audit cannot start while a proposal
is undecided. The final claim list is the examiner's.

**Assumptions.** Each claim is broken into the facts that must all be true for it to hold, using
fixed templates per claim type (communication, identity, timing, content meaning, count, absence,
role, event). Each assumption has a kind: event (a message or call happened, with these words),
identity (who used an account or phone), time, completeness (the data could show an absence or a
full count), or meaning (what words meant). Values filled into a template must be tied to the
document or the case data, or the proposal is refused.

**Checks.** Deterministic code tests what can be computed: the sender, account identity, the time
(with time zones), the weekday, counts, and absence. A check passes, fails or is inconclusive, and
records what it examined. No model is involved.

**Evidence.** A claim the checks already settle (a failed check on a core assumption) skips this
step: no records are retrieved or labeled for it, and its verdict rests on the recorded checks. For
each assumption of every other claim, Baker retrieves candidate records with structured filters and
keyword ranking, with the surrounding messages and the other phone's copy where one exists. A
language model labels each (assumption, record) pair: supports, contradicts, complicates or
irrelevant, with a quote and a short rationale. **The quote must appear character for character in
the record's original text** (no normalization, whole words only) and take in at least one letter or digit of the
record's own fields, or the label is discarded and
never stored. Translations are never citable. Contacts, calls and attachments have no message
body, so Baker cites a fixed rendering of their stored fields instead (a contact's name and number;
a call's direction, app, parties and duration, with its time shown beside it but not citable; an attachment's file name). A quote from
such a record cites only those fields, each of which keeps its `source_ref`.

**Rules.** A fixed, versioned program (`core/audit/rules.py`) turns the checks, the evidence and
the examiner's decisions into a verdict. No model decides a verdict. In brief (rules 0.2.2):

- **Contradicted** if any core assumption has a failed check, or a "contradicts" label that counts.
  A model's "contradicts" on a meaning assumption counts only once the examiner accepts it, and it
  cannot overrule a check that passed on the same assumption.
- **Supported** only if every core assumption is covered (by a passed check, or by support the
  examiner accepted on an observed or derived record), the examiner accepted at least one
  supporting record that was observed directly, nothing complicating or contradicting remains open,
  and the assumption the claim turns on (for example who sent it, for a communication claim) is
  among those covered.
- **Unproven** otherwise, naming each assumption left uncovered.

**Invariants.** After the rules run, separate code re-checks every decision against the stored
records: quotes verbatim, every Supported backed by examiner-accepted evidence. If any check fails,
the claim's results are rolled back and the run stops.

## 3. The expert gate

Nothing is Supported on a model's label. Under the rules, a claim becomes Supported only after the
examiner accepts its supporting evidence. Until then the screen asks "Support found: do you agree?". An optional
local AI reviewer may sort evidence for the examiner, but in this version its acceptance covers
nothing and never makes a claim Supported. Identity links between accounts and people stay
proposed until the examiner confirms them. Every examiner action (accept, dismiss, reopen, confirm,
override) is written to the hash-chained audit log under the examiner's name, an override with its
note. The reason typed for an evidence decision is stored with the decision but is not itself
covered by the chain.

The examiner can also override any verdict directly, including to Supported. An override bypasses
the rule prerequisites above: it needs a note, and the screen and report show it as the examiner's
own decision with that note, not as a rule outcome.

## 4. What each verdict means, and doesn't

| Verdict | Means | Does not mean |
|---|---|---|
| **Supported** | From the rules: every core assumption is covered by a passed check or by evidence the examiner accepted, and nothing open complicates or contradicts it | That the claim is true beyond the data imported, that the data is complete, or that Baker formed an opinion. An examiner override to Supported is the examiner's decision and is labeled as one |
| **Contradicted** | A deterministic check failed, or a counting "contradicts" label stands on an observed or derived record, as cited | That the person did not do something, or any conclusion about guilt. A model-labeled contradiction the examiner has not reviewed should be reviewed before it is relied on |
| **Unproven** | Baker could not cover every core assumption with the data it had; the uncovered ones are named | That the claim is false, or that the event did not happen |

**"Not found" never means "did not happen."** An absence finding states what was searched and what
the source could show. An examiner-curated report can never establish that something is absent: it
can show records that are present (which can contradict an absence claim), never that none exist.

Baker is built not to use the words guilty, innocent, leader or deleted in its own text, and the
report's own text is checked for them (`core/audit/invariants.py`). When a count includes records
the source flags as deleted, the count check says they "carry the source's deletion flag" (#83).
Text quoted from a source or typed by the examiner appears as written.

## 5. Provenance and hashing

Every source record, evidence item, assumption and identity link carries one provenance tier.
Check results and claims carry none; a check result names the records it searched instead.

| Tier | Meaning |
|---|---|
| observed | Present in the source file as imported |
| derived | Computed deterministically from observed data (for example, local time from UTC and offset) |
| inferred | Produced by a model; shown with its uncertainty and never treated as observed |
| ai_reviewed | Accepted by the local AI reviewer; never shown or exported as confirmed |
| confirmed | Accepted by the examiner, with their name in the audit log |

An inference never becomes observed because another step used it.

**Hashes and versions.** Each report lists every source file's SHA-256, the rule version, the
prompt versions, and each model run with the model file's SHA-256, parameters and seed. The local
model file is checked against its pinned SHA-256 before it loads. Model outputs are stored, not
regenerated, so re-running the rules on the same case reproduces the same verdicts.

**Audit log.** An append-only log in the case database where each entry includes the hash of the
entry before it. Editing or removing an entry in the middle breaks the chain, and the report prints
whether the chain verified and its last hash. Baker also keeps the newest entry's number and hash
in a file beside the database (`case.db.anchors.jsonl`) and checks both when a case opens and
before every report; a failed check blocks review and reports. This catches entries cut from the
end back to the newest anchor. It does not catch entries added after the newest anchor and cut
before the next check, or the database and the anchor file changed together. Keep the last hash
from each report you deliver: that is the anchor no one can change.

## 6. Known limitations

1. **Unverified formats.** The UFDR and AXIOM readers were built from vendor documentation and
   synthetic samples and have not been checked against a real export. The screen and the report
   mark these sources "unverified". The Cellebrite Excel and PDF readers have also been tested only
   on synthetic reports.
2. **Forwarded and quoted messages** fail closed. A message the UFDR or Excel report marks as
   forwarded, or that carries a forwarded or quoted original, can neither support nor contradict a
   claim, checks resting on it are inconclusive, and the claim page and report warn. Its sender
   field still shows the forwarder, and the embedded original is not imported.
3. **Quote check on older runs.** Since #76 (quote check 1.2.0) the check reads contacts and calls
   exactly as the model is shown them. An audit run before that may have discarded correct
   labels on contacts and calls, including contradicting ones; run a new full audit on such a case.
4. **Evidence recall is limited.** Retrieval is keyword and filter based, with no embeddings.
   Baker can miss a relevant record. The examiner should search beyond what Baker surfaces.
5. **Model labels can be wrong.** Each label is checked for a verbatim quote, but not for
   correctness. That is why Supported requires the examiner, and why model-labeled contradictions
   should be reviewed.
6. **No translation.** Non-Latin text is quoted in the original and flagged for a human reader.
7. **What was never imported cannot be seen.** Messages an examiner left out of a curated report
   are not in the case.
8. **Runtime** on current code is not measured.

## 7. Where this is enforced in code

| Statement | Code |
|---|---|
| Only rules set verdicts | `core/audit/rules.py` (`decide_verdict`, `RULE_VERSION`) |
| Quotes verified verbatim | `core/audit/quotes.py`, re-checked in `core/audit/invariants.py` |
| Supported needs the examiner | `core/audit/rules.py` rule 3(c), `core/audit/invariants.py` |
| Absence states what was searched | `core/audit/checks/absence.py` |
| Hash-chained log | `core/review/audit_log.py` |
| Hashes and versions in the report | `core/report/html.py` |
