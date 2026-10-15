# Baker AI changelog

One entry per meaningful change, newest first. Each entry is the handoff for that change and
answers five questions: what changed and why; where it lives (local, branch or main); what was
tested; what is open; what it affects (capabilities, privacy, performance, customer-facing
claims). Add the entry in the same PR as the change, and update `docs/PRODUCT_STATUS.md` with it.
Earlier history (PRs #1 to #43) is in git; this log starts with the 2026-10-13 build wave.

Template:

```
## YYYY-MM-DD: <change> (#PR, commit)
- Changed: <what and why>
- Where: main | branch #N (not merged) | local only
- Verified: <tests, eval numbers, runs; or "unverified">
- Open: <what is incomplete or uncertain>
- Affects: <capabilities | privacy | performance | customer-facing claims | none>
```

---

## 2026-10-15: Audit log checked on open and before every report; cut-off entries caught (#74)
- Changed: opening a case, and building or saving its report, now checks the audit log (before,
  the chain was only verified at report build, which printed the result and exported anyway, and
  at encryption). Two checks: the hash chain, and anchors: the newest entry's number and hash,
  written to `case.anchors.jsonl` beside `case.db` when a case opens and when a report is built,
  must still be in the log. Anchors catch entries cut from the end of the log, which the chain
  alone cannot. The screen checks again on every page while a case is open, and encrypting or
  changing the passphrase checks first. A failed check fails closed: Cases shows "Review
  blocked" with the reason, an open case closes (a background job on it is told to stop) and an
  encrypted one locks, no report is built, CLI commands (`report` and `encrypt` included) stop
  and write nothing; `verify-log` says why. `docs/review-screen.md` gives the
  expert's steps when a case is blocked (keep the folder, restore a whole-folder backup, or
  rebuild from the original files). (Grok Product item 5 on #70 and its follow-up on #80.)
- Where: main, with PR #74.
- Verified: 24 tests in `tests/test_chain_on_open.py` (chain, anchors: truncation, rewrite,
  unreadable or non-text file, dedupe, numbers and hashes only; CLI and screen, report and log
  page refusal, job stop, encrypt and passphrase refused, encrypted re-lock); full suite passes;
  headless-Chromium smoke (report refused after the newest entry was cut; intact report builds);
  eval unchanged (case01 1.00, 0 false supported, hostile PASS).
- Open: entries added after the newest anchor and cut before the next open or report are not
  caught, nor a change to the database and the anchor file together; a saved report's last hash
  is the anchor no one can change. Cases made before anchors are checked from their next open.
- Affects: customer-facing claims (tamper evidence enforced on open and export, truncation
  detected back to the newest anchor); a new unencrypted file per case holding entry numbers
  and hashes only (no case content, no times); one hash pass over the log per page while a case
  is open, per report and per Cases listing (2.3 ms for the 225-entry synthetic case01 log of a
  cloud bench run, this cloud container, 2026-10-15; unmeasured on a large real case).

## 2026-10-15: UFDR reader checked on public test files (#73)
- Changed: attachments linked only by file_id now resolve through taggedFiles and are hashed; a
  phone-owner UserAccount no longer takes a ProfilePicture URL as its identifier; `ufdr-check`
  mirrors both. (Grok Product item 8.)
- Where: branch `claude/project-thread-hz9jqt`, PR #73, not merged.
- Verified (as reported by the owning thread): 4 new tests; lint clean; 1860 pass, 2 known
  failures (fixed on main by #65 and #67); eval unchanged (case01 1.00, 0 false supported). Hand
  check 27 of 27 records match on autopsy-udfr `test.ufdr` (LGPL-2.1, hand-made) and IPED's UFED
  fixtures (GPL-3); neither committed, hashes in `docs/ingest/ufdr.md`. No public Cellebrite-made
  UFDR with a usable license exists; Digital Corpora and CFReDS return 403 from cloud sessions.
- Open: neither sample is Cellebrite output; 27 records, not the 50 asked for; no Reader count
  comparison; forwarded or quoted content is not read, so a forwarded message shows as written by
  the forwarder with empty text.
- Affects: capabilities (UFDR import). Customer-facing claims unchanged: UFDR and AXIOM stay
  unverified. Next: a pilot examiner makes a UFDR from a public image and runs `ufdr-check`.

## 2026-10-15: Screen and report agree; reports are repeatable (#72)
- Changed: `tests/test_report_consistency.py` checks that the screen and the report agree on
  status, verdict label and evidence ids at 7 points in a synthetic case01 review. A repeatability
  test checks that the same inputs, versions and expert decisions give a byte-identical report
  with clocks pinned, and the same SHA-256 across times once 6 documented time fields are masked.
  Bug fixed: the verdict "decided" time came from the wall clock, not the run's clock; the
  pipeline and re-decide now stamp the run's clock. Report evidence rows carry evidence-id
  anchors. `core/audit/rules.py` unchanged. (Grok Product items 6 and 7.)
- Where: branch `claude/project-thread-kq0r95`, PR #72, not merged.
- Verified (as reported by the owning thread): ruff clean; 1862 tests pass, 1 fails (the known
  test #65 fixes); eval case01 1.00, 0 false supported, hostile PASS, case02 aggregate 0.90; no
  verdict changed.
- Open: synthetic case01 only, not real exports; does not compare every rendered sentence.
- Affects: customer-facing claims (supports "reproducible audit packet", on synthetic data with
  time fields masked). No privacy or performance change.

## 2026-10-15: Quote check reads contacts as the model sees them (#76, fixes #69)
- Changed: one function now renders a contact ("Name: +1...") for retrieval, the quote check,
  `core/audit/quotes.py` and the small model's generated training items, so correct contact
  quotes are no longer discarded. The synthetic case01 affidavit PDF embeds DejaVu Sans for
  lines Helvetica can't draw ("Катя" read as boxes).
- Where: PR #76 (from the "Audit our model scoring" thread), not merged. Includes the C17 font
  fix.
- Verified (as reported by the owning thread): 2 new regression tests; suite and lint pass except
  the known #65 test; `make eval` same as main (case01 1.00, 0 false supported; case02 aggregate
  0.90), hostile run keeps 15 more labels with 0 supported. Opus replay: case01 85% to 95%,
  sheet-free 60% to 70%.
- Open: calls still render differently for the model and the check (no case01 verdict changes);
  signed guide rule 28 still writes contacts without the colon (needs Arsh); small-model run 5
  trained on colon-less contact rows (train/product mismatch).
- Affects: capabilities (more correct evidence kept, for Opus and the 14B). No privacy, network,
  performance or customer-claim change.

## 2026-10-15: Stricter reading of stated time windows (#66, 9d24024)
- Changed: "after March 3" now starts on March 4 (it started on March 3, which could produce a
  false contradicted). Offsets like "two days after", and weekdays that don't match the date, are
  refused, so those claims stay unproven. Code: `core/audit/assumption_filler.py`.
- Where: main (merged 2026-10-15 07:22Z, `6b859fe`).
- Verified: new tests in `tests/test_assumption_filler.py`; all 3 Codex findings fixed (per the
  owning thread); CI green before merge.
- Open: main still says rules 0.2.1; the 0.2.2 bump (no rule logic change) is in PR #75, not
  merged, pending Arsh's sign-off. Verdicts decided under 0.2.1 can differ after this change.
- Affects: capabilities (which claims get a time window), verdicts on time-bound claims.

## 2026-10-15: Opus fails the signed probe; quote-check bug found (issue #69)
- Changed: nothing in the product yet. Opus re-run on the signed P001-P105 set: contradicts
  precision 73% (bar 90%) in both arms, every miss a told-frame or undated denial. A grading audit
  found the quote check renders contacts and calls differently from what the model is shown.
- Where: results in `/mnt/project-files/baker/cloud-bench/2026-10-15/` (RESULTS.md,
  GRADING_AUDIT.md); signed labels on main via #64; bug is on main, open
  as issue #69 (fix in PR #76).
- Verified: preregistered run ($5.21); blind readers 12/12 with the signed labels; offline replay
  shows the #69 fix lifts Opus case01 from 85% to 95%, 0 false supported.
- Open: a signed stance prompt line for told-frame and undated denials; the #69 fix; the local
  14B has not been run on the signed set; 3 answer-key labels and 1 guide gap flagged for Arsh.
- Affects: customer-facing claims (Opus no longer passes the full cloud rule), capabilities
  (#69 loses correct contact and call evidence for every model).

## 2026-10-15: Positioning narrowed; cloud is opt-in
- Changed: Arsh agreed to position Baker as a verification layer on Cellebrite and AXIOM for
  forensic examiners, and chose "Opt-in cloud" (07:10Z): local by default, cloud AI only when the
  case allows it and the expert opts in. PRODUCT_STATUS section 12 checks each claim in the line.
- Where: decision only; #68 still a draft.
- Verified: claims 1, 2, 5 true; 3 true for absence and count findings; 4 partly true; 6 depends
  on #68.
- Open: none.
- Affects: customer-facing claims.

## 2026-10-15: Process: Grok review PR and small model run 5
- Changed: every tenth PR (#70, #80, ...) is an empty Grok Product review PR, never merged.
  Small model run 5 (more varied training wording) started on branch #50.
- Where: #70 (draft); #50 (draft).
- Verified: nothing to measure yet.
- Open: run 5 results.
- Affects: none yet.

## 2026-10-15: Source-of-truth docs (this change)
- Changed: added `docs/PRODUCT_STATUS.md`, this log, and a CLAUDE.md rule to keep both current,
  so Grok Product and coding agents read one verified description of Baker.
- Where: PR #71 (branch `claude/project-thread-d7xp9z`, not merged). CLAUDE.md wording signed by
  Arsh ("approved", 2026-10-15 07:19Z).
- Verified: facts checked against main `7a14437`, open PR branches and recorded bench runs.
  Section 12 checks the six claims in the proposed positioning line, with file:line.
- Open: entries before 2026-10-13 are summarized by git only.
- Affects: none (documentation).

## 2026-10-15: Cloud AI by per-case opt-in for stance labels (#68, 3c6c1ec)
- Changed: Baker is local by default. A case uses Opus 5.5 for stance labels only after the
  expert attests the protective order allows it, the case has no CSAM flag, and they supply their
  own Anthropic key. If the cloud fails mid-case, the audit pauses and the expert retries or
  re-runs the whole case locally, so models are never mixed within a case. Every request is
  written to the hash-chained audit log (`cloud.sent`) before it is sent. The endpoint is pinned
  to api.anthropic.com (120 s timeout, 2 retries). Claim proposal, assumption filling and the AI
  reviewer stay local. Reason: Arsh chose "Opt-in cloud" (2026-10-15 07:10Z).
- Where: branch `claude/project-thread-a2fjkc`, PR #68, draft, not merged.
- Verified (as reported by the owning thread; `cloud.sent` and the pause checked in
  `core/audit/_local_model.py` on the branch): `make check` passes, 1893 tests; gates unchanged
  (case01 1.00, 0 false supported, unreviewed 0.60, hostile PASS, case02 0.90); a simulated
  outage pauses the run with the chain intact; Codex rounds 1 to 4 clean, re-review pending. No
  real API call since this change.
- Open: Opus fails the signed probe's contradicts bar (73%, entry below), so a signed prompt fix
  should land first; the revised CLAUDE.md wording needs Arsh's "approved"; a fair 14B-vs-Opus
  test of claim proposal and assumption filling waits on Arsh; an evidence row keeps the first
  model's name when a later run gives an identical label (the per-run "Stance labels" row is
  authoritative); the key file is owner-only, not encrypted with the case keys.
- Affects: capabilities (optional cloud labels per case), privacy (only the filled stance prompt
  leaves the computer, and every request is logged), performance (about 3 s per stance call; local 22 to 43 s per call was
  measured 2026-10-09/12 on older code, and no full local case is timed on current code), customer-facing claims ("local by default; cloud AI only when your
  case allows it and you opt in"; never "no network calls" without that qualifier).

## 2026-10-15: Opus on claim proposal and assumption filling (eval only)
- Changed: nothing in the product. A preregistered check of moving two more steps to Opus.
- Where: `eval/bench/cloud_steps.py` on branch #68; results in
  `/mnt/project-files/baker/cloud-first/steps-check/RESULTS.md`.
- Verified: claim recall 80% (bar 90%); sheet-free audit 60% accuracy, 0 false supported (bar
  80%). Both failed, so both steps stay local.
- Open: none.
- Affects: performance (the 14B stays required).

## 2026-10-15: Opus 5.5 benchmark (eval only)
- Changed: nothing in the product. Probe and case01 runs for Opus at medium and high effort.
- Where: results in `/mnt/project-files/baker/cloud-bench/2026-10-14c/`.
- Verified: probe 27/27 supports, 0 wrong contradicts, 0 traps as support; case01 85%, 0 false
  supported. Cost $13.04.
- Open: only 8 gold contradicts; the signed probe follow-up is expected to cut contradicts
  precision until a prompt fix (not yet re-run).
- Affects: none until #68 merges.

## 2026-10-15: Fixes merged (#64, #65, #67)
- Changed: #65 fixes main's red test (test only). #67 fixes a flaky recovery-key test. (#66 has
  its own entry above.) #64 fixes the
  go-bar scorer and holds the probe follow-up proposal for guide v0.3.
- Where: main (merged 2026-10-15 07:21Z to 07:22Z). #65 fixes the v1.1 test that turned main red.
- Verified: CI green on each head.
- Open: none. The signed probe (105 items) is on main via #64.
- Affects: test or eval only.

## 2026-10-14: Prompt v1.1 with readable names, members line and the claim (#62, 53268d9)
- Changed: the 14B now reads people's names (from confirmed stipulations or identity links), a
  chat's members (capped at 20) and the claim for meaning, role and event assumptions. Reason:
  case01 ¶10.1 got a wrong "contradicts" from an id the model could not read.
- Where: main.
- Verified: model-free gate; v1.1 text pinned by digest. Not re-run on the Mac with the 14B.
- Open: Mac re-run of case01 to confirm ¶10.1; the AI reviewer still reads ids.
- Affects: capabilities.

## 2026-10-14: Probe scored as the product sees it (#63, 7a14437)
- Changed: the probe shows items in the product's layout; the scorer verifies quotes like the
  product. Reason: a grading audit found the probe input differed from the product's.
- Where: main. Combined with #62 it turned main's CI red (fixed on #65).
- Verified: re-scored runs in `/mnt/project-files/baker/cloud-bench/2026-10-14/`.
- Open: none beyond #65.
- Affects: benchmark numbers (earlier cloud scores are superseded).

## 2026-10-14: Stance data v0.3, signed (#59, 084a255)
- Changed: strict contradicts labels ("only when the record's own words rule the claim out"),
  Baker's own wording, 8 probe relabels (gold contradicts 16 to 8), new go bar.
- Where: main.
- Verified: blind label rounds; contamination check.
- Open: 5 disputed denials resolved by the signed follow-up, not yet applied (#64).
- Affects: benchmark numbers.

## 2026-10-14: Rules 0.2.1 (#53, af49c17)
- Changed: an unreviewed model "contradicts" cannot overrule a passing check; it only
  complicates. The sender is read from the claim.
- Where: main.
- Verified: model-free gate and rules tests.
- Open: none.
- Affects: verdicts (fewer false CONTRADICTED).

## 2026-10-14: New readers and analysis pages (#55, #56, #57, #58)
- Changed: AXIOM XML and Excel import (unverified); `baker ufdr-check`; Other explanations per
  claim; Windows code-signing path and clean-install tests.
- Where: main.
- Verified: synthetic tests, CI.
- Open: AXIOM and UFDR need real samples; installer signing needs Azure.
- Affects: capabilities, customer-facing claims (say "unverified" for AXIOM and UFDR).

## 2026-10-13: Review, identity, timeline, selection, encryption (#44 to #52)
- Changed: demo kit and Mac installer (#44); Identities page (#45); Timeline check and Gaps
  (#46); UFDR import, unverified (#47); cloud bench harness (#48); encryption at rest (#49);
  Selection audit (#52).
- Where: main.
- Verified: synthetic tests, CI, headless-Chromium UI checks.
- Open: real-data checks for UFDR.
- Affects: capabilities, privacy (encryption by default for new cases).
