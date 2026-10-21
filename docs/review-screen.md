# Expert review screen

`baker serve` starts a local web server on `127.0.0.1` (port 8765 by default) and the expert
works in their own browser, from a new case to the exported report, without a terminal.
Nothing leaves the computer unless the expert opts a case in to cloud AI (then that case's
stance questions go to Anthropic, docs/ARCHITECTURE.md "Local by default, cloud by opt-in"): the
server binds the loopback address only, pages contain no scripts and load nothing from outside,
and `core/`, `core/casework/`, `core/review/`, `core/report/` and `ui/` import no network client
except `core/llm/cloud.py` (tests enforce it).

- `baker serve` works on a cases folder (`--cases`, else `$BAKER_CASES`, else `~/Baker/cases`):
  the expert makes and opens cases there.
- `baker serve --db case.db` works on one existing case database, as before.

## Starting a case

**Cases** lists the cases in the folder and makes a new one. Each case is a folder:

```
<cases folder>/<case>/case.db      the case database
                      case.json    its name, when it was made, the expert's claim order
                      inputs/      read-only copies of every imported file
```

**Set up and run** walks through five steps:

1. **Files.** Upload the government document (PDF) and each Cellebrite report (Excel or PDF).
   The upload is written into `inputs/` and SHA-256 hashed as it arrives, then made read-only;
   the importer opens that copy read-only and hashes exactly the bytes it parses, and the two
   hashes must match or nothing is stored. The expert's original is never touched. The table
   shows each source's SHA-256, its coverage (curated report or full extraction) and its record
   count. The same file twice is refused, and a file that fails to import leaves nothing behind.
2. **Claims.** "Propose claims with the local model" runs `claims propose` in the background, one
   paragraph at a time (a stop keeps what is done; proposing again skips paragraphs that have
   claims). The expert accepts, edits or removes each proposal, adds their own, and moves claims
   up or down: the audit runs them in that order. The audit cannot start while a proposal is
   undecided.
3. **Who used each phone.** Stipulate each device's user before the audit, so the sender checks
   decide instead of coming back inconclusive. The expert may go on without one, after ticking
   that they accept inconclusive sender checks.
4. **The model.** "Check the model" (and every audit, first) checks that the configured model
   file is on this computer, that its SHA-256 matches the config, that this computer has enough
   memory (the file's size plus 4 GB), and that the local runtime is installed, each with a plain
   message. A passed hash is remembered for the unchanged file in `~/.baker/model-check.json`.
   `baker model-check` does the same from the command line.
5. **Run the audit.** It runs in the background, in the expert's claim order, with a rough
   upfront estimate (about 25 model calls per claim, from synthetic case01, at the seconds per
   call measured on this computer, else 43 s from a 24 GB Mac). The computer is kept awake while
   it runs (Windows: SetThreadExecutionState; macOS: caffeinate; Linux: systemd-inhibit; the page
   says if it could not). Options: the AI reviewer (a sorting aid, off by default) and labeling
   claims a failed check already decides.

**Audit progress** shows each claim's state (waiting, labeling, finished), how many of its
candidates are labeled, the new model calls it made, and its finding once finished, with time
left re-estimated from the calls measured in this run. It refreshes itself every 10 seconds
(a page refresh, not a script). "Stop" stops after the claim being labeled; the run is stored as
stopped. If the app closes or the computer loses power mid-run, the next start marks that run
stopped. "Resume" starts a new run on the same order: claims finished before reuse their stored
model outputs and take seconds.

**While the audit runs.** A claim appears for review as soon as all its candidates are labeled.
Each claim's model work runs before anything is written, and its rows are then written in one
short transaction, so the expert's decisions save at once while the model works on the next
claim. Every claim the run has not finished says **Labeling incomplete**, on the screen and in
the exported report, with a banner naming the run shown (an earlier completed run is not mixed
in). Until the run ends the screen refuses anything that would change its inputs: new files,
claim changes, stipulations and re-running the verdicts. Only a completed run is scored by the
eval or re-decided.

## What the expert does

1. **Case page.** Enter your name once; it is recorded with every decision. Check the sources
   and their SHA-256 hashes, and stipulate who used each phone (a stipulation, not a finding;
   every report lists it as a limitation).
2. **Claims queue.** Claims sorted by what needs you: AI-accepted supporting evidence first, then
   supporting evidence nobody reviewed, then contradicting or complicating items, then verdicts to
   confirm. A claim whose supporting evidence no expert has decided shows as
   **Support found: do you agree?**, never as supported. A claim with a model "contradicts" on
   a core assumption that no expert has decided shows as **Contradiction found, confirm to
   finalize** (rules 0.3.0), near the top of the queue: on the claim page, type a one-sentence
   reason and click **Confirm contradiction** (or **Dismiss**). Baker records the decision and
   its reason in the audit log and re-runs the verdicts at once, so the claim turns
   contradicted. A claim Baker could not set up
   any check for (the assumption filler refused every proposal, for example a name that is no
   person in the case) shows as **Unproven, not tested**, with the refusals, at the top of the
   queue: no record was searched for it, so the expert checks it by hand. Its claim page and
   the report list what the case holds (each imported extraction file, the devices in it, its
   kind, coverage and SHA-256), so a claim about the case's own material, such as "based on
   extraction reports for two phones", can be compared at a glance.
3. **Claim page.** The claim, its paragraph as printed, the verdict and the rules' reasons, the
   assumptions and what each check searched, and every evidence item grouped by review state.
   Accept, dismiss or reopen each item with a one-sentence reason. "See about 20 messages around
   it" shows the conversation around the record in the phone's local time.
4. **Re-run verdicts.** Decisions do not change a verdict by themselves. "Re-run verdicts" runs
   `core/audit/rules.py` and the invariants again on the stored evidence with the current review
   statuses (`core/review/redecide.py`, also `baker redecide`). No model is called, so it takes
   seconds. Claims edited or added since the audit need a full audit (Set up and run).
5. **Confirm or override** each verdict. An override needs a note and prints as an expert
   override.
6. **Selection.** Every message the government's document quotes, an exhibit quotes or the
   examiner tagged, in its own exchange with the messages around it that were not picked, and the
   quiet stretches the Gaps tab lists in the pauses around it
   ([selection-audit.md](selection-audit.md)). A claim page whose paragraph quotes messages links
   to its passages. It never changes a verdict.
7. **Timeline and Gaps.** The Timeline tab puts every date and time the government document
   states beside the phone records' own timestamps and lists the differences first; the Gaps tab
   lists stretches with no messages or calls on each phone, app and thread. Both are derived by
   code, change no verdict, and appear in the report. Their two case settings (time tolerance,
   shortest quiet stretch) are logged with your name. See [timeline.md](timeline.md).
8. **Report.** View it, save it (`Report` page, or `/report?download=1`), or print it to PDF from
   the browser; the print layout is built in. **Audit log** verifies the hash chain.
9. **Activity.** Every case page you open is written to the audit log as a page view: the
   time (UTC), your name, the page, the claim or evidence item it was opened on, the evidence
   items it listed, and for an evidence item its record and where that record sits in its source
   (source and locator), never the record's text. The Activity tab shows the trail per claim
   (times opened, first and last, time on its pages, evidence opened, your actions) and step by
   step, beside your decisions; `/activity.csv` and `baker activity --db case.db [--csv out.csv]`
   export it with each entry's hash. Time on page runs from opening a page to your next page or
   action in the same screen session. The screen runs no scripts, so it cannot tell what was on
   screen or read; a stretch over 30 minutes may include time away and is counted apart, and a
   refresh of the same page with nothing done between is one view. The report leaves the
   activity table out unless you include it for the case (off by default): the switch is on the
   Activity tab, or `baker activity --db case.db --in-report on|off --by expert:<name>`, and
   each change is in the audit log with your name. Views change no verdict. The Audit log page hides them unless you ask
   (`/log?views=1`). Code: `core/review/activity.py`.

## Rules the screen keeps

- Every change goes through `core/review/actions.py`, so the hash-chained audit log records it.
  The screen never sets a verdict; only `rules.py` does, through a full audit or a re-run.
- Opening a case, every page, form and file upload while it is open (the report and its
  download included), and encrypting it or changing its passphrase first check the audit log
  (below). A failed
  check fails closed: the case does not open, or an open one closes (a background audit or
  claim proposal on it is told to stop after the claim or paragraph in hand, and an encrypted
  case locks), no report is built, and nothing is written. The CLI refuses every command but
  `verify-log` the same way, `report` and `encrypt` included (an encrypted case's log is inside
  its database, so `passphrase` checks it after the current passphrase opens it).
- Under rules 0.2.0 no claim is supported until an expert accepts its key evidence. An item the
  local AI reviewer accepted shows its tier as `ai_reviewed` ("AI-reviewed, not confirmed"); only
  an expert's acceptance shows as `confirmed`.
- The screen and the report use the same labels (`core/review/status.py`).
- Every page passes the same forbidden-word check as the report. Cited text and the
  expert's own reasons and notes are exempt; Baker's wording and a model's are not.

## The audit log check

Three checks, all in `core/review/audit_log.py` (`require_intact`):

1. **The hash chain.** Each entry's hash covers the one before it, so changing or removing an
   entry in the middle breaks the chain from that entry on. The Cases page says "Review blocked"
   and names the first entry that does not match.
2. **The anchors.** The chain alone cannot tell that entries were cut from its end: what is left
   still verifies. So when a case opens, and when a report is built, Baker writes the newest
   entry's number and hash to `case.db.anchors.jsonl` beside `case.db` (one line each time it
   changed; entry numbers and hashes only: no case content, no times, no reasons, since the file
   stays unencrypted beside an encrypted case). Every later check requires each
   anchored entry to still be there with the same hash. A log cut back past an anchor, or
   rewritten from there on, is blocked ("the audit log has no entry N ... so entries were removed
   from the end of the log").

3. **The expert's reasons.** Each evidence decision's log entry carries the reason the expert
   typed. A reason changed in the case database after it was logged no longer matches, and the
   case is blocked ("the expert's decision or reason for evidence decision N ... was changed
   after it was logged"). The status the expert chose is compared the same way, and an expert review added
   to or removed from the database with no matching log entry is blocked too. Decisions logged
   before this check carry no reason in the log, so their reasons are not compared; their status
   and presence still are.

A case folder Baker cannot write to (read-only media, a locked-down backup) does not open or
report, since no anchor could be recorded: copy the folder somewhere writable and open the copy.

What the anchors do not catch: entries added after the newest anchor and then cut again before
the next open or report, and anyone who changes the database and the anchor file together. The
report prints the last hash; keeping a saved copy of each report gives an anchor outside the
case folder that no one can change. A case made before anchors is checked from its next open on.

### When a case is blocked

Nothing in Baker repairs a blocked case, because the record that would say what changed is the
one that no longer verifies. The expert:

1. Leaves the case folder as it is (it is evidence of what happened) and runs
   `baker verify-log --db <case folder>/case.db` to record the reason.
2. Restores the case folder from a backup made before the change, if there is one, and opens it.
   The restored log must still hold every anchored entry: restore the folder whole, its
   `case.db.anchors.jsonl` with its `case.db`. A restored log older than the anchor file beside it
   is blocked.
3. Otherwise makes a new case from the original files (the government document and the
   extraction reports), settles the claims and runs the audit again. The SHA-256 of each
   original matches the hashes in the old case's reports.
4. Keeps the blocked folder, and notes for counsel why the case was rebuilt.

## Local-server protections

Another web page open in the same browser can send requests to `127.0.0.1`, so the server
checks the Host header (blocks DNS rebinding), requires a per-session random token on every
form (in an upload, before a byte of the file is written), refuses cross-site requests, and
sends a Content-Security-Policy that forbids scripts, framing and outside loads. The
Referrer-Policy is same-origin: under no-referrer, browsers send "Origin: null" with the
screen's own forms and the Origin check refused every one of them.

## Known gaps

The expert can accept only evidence the audit retrieved. Since retrieval 0.2.0 (#26), on
synthetic case01 every key record of the 15 claims that go to labeling is retrieved, including
C01's contact row and C09's call rows (`make eval`: "key evidence never retrieved: {}"). The other
5 claims (C04, C08, C10, C11, C14) are decided contradicted by a failed core check and are not
labeled; their failed checks cite 15 of their 18 key records. "Also label claims a failed check
already decides" labels them anyway. A real case can still miss a record retrieval did not
find; then the claim cannot reach supported on the screen, and the expert can override the
verdict with a note, which prints as an expert override.

The screen runs one background job at a time, and the audit runs inside the `baker serve`
process: closing it stops the audit (finished claims are kept; resume later). Running
`baker audit` on the same case at the same time as the screen's audit is not supported.
