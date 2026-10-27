# Pilot gates

"Pilot-ready" means every gate below passes. A pilot is the first time a defense expert runs Mabillon
on real case data. Until then Mabillon is shown only on the synthetic demo.

Each gate is pass or fail. Partial progress is "not met". A gate passes only when its evidence
exists on `main` (or, for a human step, in a recorded result someone can open). Update this file in
the same PR that changes a gate's state, along with `docs/PRODUCT_STATUS.md` section 11.

- **As of:** 2026-10-27, main `d478705` for gate 5's rows (5a and 5b); 2026-10-21, main `30d194d` for gate 1 (CI) and gate 4's row (#103); 2026-10-20, main `e8b373a` for gate 10 (signed build); the other rows were last
  checked 2026-10-19 at main `0dc55dc` (after #83, #72, #68, #74, #73, #75, #79, #85, #76, #87, #78, #82, #86, #88, #91, #89, #84
  and #81). Since `80bf0df` only gate 4's row was rechecked (for #89). Open PRs are named but not counted.
- **Result:** 14 of 19 gates met (gate 1 by 7 consecutive green CI runs on main, 2026-10-21, gate 17 by #92, gate 10 by the signed main build of 2026-10-20, gate 19 by #98, gate 2 by #76, gate 3 by #91, gate 14 by the case02 key Arsh signed, gate 6 by #72, gate 7 by #74, gate 8 by
  merging #68, gate 12 by #82, gate 13 by #86 and #88, gate 15 already in place, gate 18 by the feedback form #82 publishes). Gates 13 to 18 come from Grok's pilot-ready list
  (2026-10-16), which Arsh agreed to fold in here. Gate 19 comes from Grok's URGENT FIX on #90
  (2026-10-19). Gate 5 is split into 5a (UFDR from Cellebrite Reader 7.48, the first pilot's scope)
  and 5b (other formats, after the first pilot); it counts as one gate, met when 5a is met. Neither is
  met, so the count is unchanged. **Not pilot-ready.**

## The gates

| # | Gate | Pass when | State (2026-10-16; gate 10 2026-10-20; gates 1 and 4 2026-10-21; gate 5 2026-10-27) | Evidence or what's missing |
|---|---|---|---|---|
| 1 | CI green 3 times | The `checks` workflow (Ubuntu and Windows) passes on 3 consecutive pushes to `main`, with no re-runs | **Met** (2026-10-21) | The `checks` workflow passed on the first attempt (run_attempt 1) on 7 consecutive pushes to main, #105 to #110; the 3 most recent: runs 39607503937 (#108), 39617971260 (#109), 39629330625 (#110) |
| 2 | Quote check matches what the model sees (issue #69) | Contacts and calls render the same way for the labeler and the quote check, on main | **Met** | #76 (merged 2026-10-16, `8abaeea`): `core/audit/invariants.record_text` reads a contact and a call exactly as retrieval shows them to the labeler, so correct quotes, including contradicting ones, are no longer discarded |
| 3 | Versions stamped on every result | `RULE_VERSION` on main includes every merged rule-reading change (0.2.2, PR #75), and every report records the model file's SHA-256, seed, the Mabillon build (release and commit) that ran, the rule version and the quote-check version | **Met** (#91) | Rules 0.2.2 (#75); quote check 1.2.0 stored in every run's config (#76). #91 stores the release (`pyproject.toml`) and git commit, with an uncommitted-changes flag, as `build` in every run's config (`core/build.py`); the report's top line, versions table and Run section, the overview screen and the eval's `run.json` print it beside the pipeline, rule and quote-check versions, and each model run's SHA-256 and seed (`core/report/html.py`, `ui/pages.py`, `eval/run_pipeline.py`). A rules-only re-run also names the build its evidence came from |
| 4 | Forwarded and quoted messages | The UFDR importer stores original author, forwarder and text as separate fields with `source_ref`; the sender check never credits forwarded content to the forwarder; until then affected claims fail closed to Unproven with a visible warning | **Not met** | Fail-closed half done (#73, merged 2026-10-16): messages marked forwarded or carrying a forwarded or quoted original are listed in coverage, can neither support nor contradict, make checks resting on them inconclusive, and are warned on the claim page and in the report; SenderCheck never names the forwarder as the writer. PR #89 (merged 2026-10-19) applied the schema change Arsh signed on 2026-10-16: each forwarded record is marked, and the original author is stored as written when the UFDR names exactly one. The UFDR importer now imports the text of each embedded original (one level) as its own forwarded record at `<locator>/Embedded[n]` (PR #103). The AXIOM importer marks forwarded and quoted messages the same way and imports one level of quoted original (PR #116, field names unverified on a real export). Still open: the UFDR author and forwarder are separate records linked by locator, not fields of one record, and a second embedded level is not imported. Grok #80 item 1 |
| 5a | Real exports checked: UFDR (pilot scope) | Cellebrite UFDR packages from Cellebrite Reader 7.48 import from start to finish on the three public Hickman test-phone packages (Android 12, Android 13, iOS 15.3.1; Digital Corpora), `mabillon ufdr-check` passes on each, the imported counts agree with Cellebrite Reader's own counts, and the report matches the screen | **Not met** | main: #117 (merged 2026-10-24) reads Reader 7.48 `RelatedModels` copies as copies (UFDR importer 0.3.0); its changelog records 0 differences from `ufdr-check` on all three packages, run by Arsh on a macOS 15.6.1 arm64 machine on 2026-10-23 at #117's head `a7728b7` (report.xml only, attachment files left out). #130 (merged 2026-10-24, ufdr-check 0.3.0, importer 0.3.1) also checks call, contact and account copies; its changelog records 0 differences on all three, run in a cloud container on 2026-10-24 (report.xml only). Both runs are reported in changelog entries, not re-run here; the packages and results stay outside the repo. Missing: the counts have not been compared with Cellebrite Reader's own counts, because nobody on the project has Reader access (#130 entry, "Open"; report.xml states no per-type count), so this stays Not met until that is done or Arsh waives it in writing. The importer still records `FORMAT_SUPPORT = "unverified"` (`core/ingest/ufdr.py`). Screen and report agreement is tested on synthetic data only (gate 6) |
| 5b | Real exports checked: other formats (post-pilot) | Cellebrite Physical Analyzer Excel, UFDR from other Reader or Physical Analyzer versions, and Magnet AXIOM XML and Excel exports that are not case data import from start to finish, counts match the vendor tool, and the report matches the screen | **Not met** | main: Cellebrite Excel was run on one real-format Physical Analyzer per-category SMS export from a Pixel 3 test phone, with times in 2020 (Physical Analyzer version not recorded; believed public; not in the repo), on 2026-10-24 (#129 entry, reported only). No other Excel category, no PDF, no other UFDR version and no real AXIOM export has been imported. AXIOM field names are assumed (#116). Does not block the first pilot (pilot rule below) |
| 6 | Reproducible reports | A test shows the screen and the report agree, and the same inputs, versions and expert decisions give the same report apart from its time fields (times, run ids and the audit log's last hash, which follow from the times) | **Met** | `tests/test_report_consistency.py` (#72, merged 2026-10-15): screen and report agree at 7 points; same inputs give a byte-identical report with clocks pinned, and reports made at other times differ only in those time fields. Mabillon does not yet print a hash with the time fields masked, so an outside reader comparing two real reports must compare them field by field |
| 7 | Audit-log chain enforced | The hash chain is checked when a case opens, before a report and before export, and a broken chain blocks review | **Met** | #74 (merged 2026-10-15): checked on open, on every page, before every report and before encryption; a failure blocks review. Anchors in `case.db.anchors.jsonl` catch entries cut from the end, back to the newest anchor (`tests/test_chain_on_open.py`) |
| 8 | Cloud decision recorded | Arsh decides #68 (merge, hold or close) and the decision is on record | **Met** | #68 merged 2026-10-15 (`ed0a3a8`). With stance v1.1 Opus scored 73% contradicts precision (bar 90%), so `PROBE_PASSED` stayed empty; with the cloud prompt, stance v1.2 (#93), Opus 5.5 at medium passed on the signed set and on new items, and Arsh signed its entry on 2026-10-20, so a case the expert opts in can use it |
| 9 | Runtime measured | A full local case01 run on current main, timed with `eval/probe/time_case.py` on Arsh's 24 GB Mac (a typical examiner machine) and on the rented AWS g5 (NVIDIA A10G), with commit, hardware and date recorded | **Not met** | Last full run predates today's pipeline. Per-call figures are from 2026-10-09 and 2026-10-12 |
| 10 | Signed Windows installer | The Windows installer is code-signed (only for a Windows pilot) | **Met** | Builds of main sign with Microsoft Artifact Signing (individual identity validation, Public Trust profile `bakerpublic`). Run 39496196827 on main `e8b373a` (2026-10-20): `Baker-Setup-0.0.1+e8b373a.exe` signed by `CN=Shayan Haque`, `Get-AuthenticodeSignature` Valid, then the fresh-runner install, case01 gate and browser smoke test passed on the signed file. A new signature may still get SmartScreen's reputation warning at first (`docs/code-signing.md`) |
| 11 | Outside install test | One person outside the project installs Mabillon on a clean Mac, runs the demo and opens a case using only `docs/PILOT_ONBOARDING.md`, without help, and the result is written down | **Not met** | Needs a person. The kit exists (this PR); nobody outside the project has tried it |
| 12 | Buyer documents | Onboarding kit, methods note and security and privacy pack are on main and match the code | **Met** (#82) | `docs/PILOT_ONBOARDING.md`, `docs/METHODS.md`, `docs/SECURITY_PRIVACY.md` |
| 13 | Known integrity bugs fixed | An upload whose hash changes between copy and import leaves nothing in the case (PR #88), and the reason typed for an evidence decision is in the hash-chained audit entry (PR #86); both merged and CI green on main | **Met** (#86, #88) | #86 (merged 2026-10-19, `80bf0df`) logs and checks the reason; #88 refuses a changed upload before anything parses or stores it (`tests/test_import_changed.py`). Both found by Codex on #82. Main CI on #88's merge commit is the last check |
| 14 | Held-out error rate | The existing hidden case02 has an answer key Arsh has signed, and `make eval` scores it blind, so its error rate can be quoted as a synthetic held-out result with the date and commit | **Met** | Arsh signed case02's key and assumption sheet on 2026-10-12 (commit `99a752a`); `make eval` scores it blind and prints aggregates only: accuracy 0.90, 0 false supported (Linux, 2026-10-16, this PR's head). Synthetic data only: it is not an accuracy figure for real cases. Agents never read case02 |
| 15 | Stopped or crashed runs | A stopped or crashed audit never looks complete, and the examiner can resume it | **Met** | Stop button stores the run as stopped (`core/casework/jobs.py`); a run left running by a crash is marked stopped on next start; unfinished claims show and print "Labeling incomplete" with no verdict, and the report carries a banner; resuming reuses finished claims' stored outputs (`tests/test_start_case.py` stop and resume, `tests/test_fewer_calls.py` killed run). Starting over from scratch means a new case |
| 16 | Pilot agreement | A signed short agreement: data stays on the examiner's machine, Mabillon never sees it, deletion whenever they want, output advisory only | **Not met** | An outline for a lawyer exists (`/mnt/project-files/baker/pilot/03-pilot-agreement-outline.md`), with bracketed decisions open; no company or lawyer yet |
| 17 | One-page explainer and support | A one-page "what Mabillon does and doesn't do", a named support contact, and a way to send a bug report with no case data | **Met** | One-pager `docs/ONE_PAGER.md`, support contact support@getmabillon.com on the Help tab and in `docs/SUPPORT.md`, and a bug report with no case data (`/help/bug-report.json`, `mabillon bug-report`), all from PR #92. The methods note, limitations sheet, `mabillon verify-log`, `ufdr-check.md` and `ufdr-check.json` also hold no case content (`ufdr-check-private.md` is case content and is never sent) |
| 18 | Feedback form | A form records where Mabillon was wrong, where it saved time and what was missing | **Met** | [`docs/PILOT_FEEDBACK_FORM.md`](PILOT_FEEDBACK_FORM.md) (wrong verdicts and citations, time saved, what was missing), filled in with no case content |
| 19 | No model-only Contradicted | The local labeler meets the signed stance bars (supports recall >= 0.90, contradicts precision >= 0.90, 0 moved traps shown as supports), or CONTRADICTED requires expert acceptance | **Met** (#98) | Rules 0.3.0 (#98): a model's or the AI reviewer's "contradicts" counts only once an expert accepts it, and the screen and report say "Contradiction found, confirm to finalize" until then. The per-claim-type allow-set `_AUTO_CONTRADICT` in `core/audit/rules.py` is empty. The 14B does not meet the bars today (Mac run 2026-10-19, `eee8d15`: 58% contradicts precision on v1.1). It is met by requiring expert acceptance; automation returns per claim type only through a signed `_AUTO_CONTRADICT` entry |

**Pilot rule for gate 5.** The first pilot accepts only UFDR packages from Cellebrite Reader
7.48. Any other format or version (Physical Analyzer Excel or PDF, another Reader or Physical
Analyzer version, AXIOM) must show "not tested" on the case screen and in the report.
On main `d478705` this banner does not exist yet, so it is an open item, not a claim:
- UFDR and AXIOM imports carry a "not yet verified" notice on the case screen (import coverage,
  `ui/pages.py` `_import_coverage`) and in the report's Limitations (`core/report/html.py`), from
  `FORMAT_SUPPORT = "unverified"` (`core/ingest/ufdr.py`, `core/ingest/axiom.py`;
  `core/ingest/coverage.py` `FORMAT_UNVERIFIED`).
- Cellebrite Excel and PDF imports carry no such notice.
- The UFDR notice does not depend on the Reader version: a 7.48 package and any other version
  get the same words. The importer records the package's `reportVersion` in the import's coverage
  record (`core/ingest/ufdr.py`) but nothing reads it for the notice.
- The UFDR notice still says the reader was "tested only on synthetic packages, never on a real
  one", which has not been true since #117.

Closing these needs a code change in its own PR.

Also required on the release commit, as for every merge: `make check` passes (lint, tests, the
model-free eval with 0 false supported on case01, hostile red-team PASS).

## What the gates don't cover

- **Accuracy on real data.** No gate claims a number. Mabillon publishes no accuracy or speed figure
  until it is measured on real exports (Grok #80, Defer).
- **Paid pilots and case02.** Whether a pilot is paid, and the hidden case02 result, are business
  gates in the pilot kit's go/kill scorecard, not product gates.
- **Gate 8 is a decision, not a pass.** Arsh merged #68 with no model allowed through the gate.
  Opus 5.5 at medium, with the cloud prompt, has since passed, and Arsh signed its entry
  (2026-10-20, #101). A pilot case uses it only when the expert opts that case in; every other
  case runs local only.

## Order

Gate 4 still needs the AXIOM forwarded field names (#116) checked on a real export, the UFDR author and forwarder kept as separate fields rather than separate records linked by locator, and a second embedded level imported. Gate 16 needs Arsh and a lawyer for the agreement.
Gate 17 is writing. Gate 5a needs Cellebrite Reader's own counts compared with the import on the three public
packages (or Arsh's written waiver), and the pilot rule's "not tested" banner built; 5b needs
real exports of the other formats and waits until after the first pilot. Gates 9 and 11 need a
person: runs on the Mac and the AWS g5, and an outside tester.
Gate 12 follows from merging.
