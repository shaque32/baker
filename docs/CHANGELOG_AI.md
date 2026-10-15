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

## 2026-10-15: Count check no longer says "deleted" (#83)
- Changed: the count check's detail now reads "N of them carry the source's deletion flag"
  instead of "N of them are flagged deleted"; check version 1.0.0 to 1.0.1. The old text broke
  the CLAUDE.md rule against Baker saying "deleted", and the report's forbidden-words check would
  stop the report build whenever a counted message had the source's deletion flag. Found by Codex
  on #82. A grep of core/ and ui/ found no other Baker-authored prose with a forbidden word;
  `baker ufdr-check` output names the package's own `deleted_state` field and was left as is.
- Where: branch `claude/fix-count-deleted-wording-oxal24`, PR #83, not merged.
- Verified: new unit test (fails on main, passes here) checks the detail and search text against
  FORBIDDEN_WORDS and `check_report_text`. `make check` passed 2026-10-15 in a Linux cloud
  container: 1884 passed, 6 skipped; case01 model-free accuracy 1.00, 0 false supported.
- Open: none known.
- Affects: customer-facing text on the review screen and report (wording only); no verdict,
  privacy or performance change.

## 2026-10-15: Audit-log chain verified when a case opens (#74)
- Changed: opening a case now verifies the audit-log hash chain (before, only at report build or
  encryption). A broken chain fails closed: Cases shows "Review blocked" with the first entry
  that doesn't match, an encrypted case locks again, CLI review commands stop and write nothing.
  `verify-log` and report still read the case. (Grok Product item 5.)
- Where: branch `claude/project-thread-fjea4m`, PR #74, not merged.
- Verified (as reported by the owning thread): 11 new tests, 9 fail on main; 1868 pass, only the
  known test #65 fixes; headless-Chromium smoke passed; eval unchanged (case01 1.00, 0 false
  supported, hostile PASS).
- Open: removing the newest entries is still not detected (a truncated chain verifies); this
  predates the PR.
- Affects: customer-facing claims (tamper evidence enforced on open, not only shown in the
  report); small performance cost on open; no privacy change.

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
  with clocks pinned, and the same SHA-256 across times once the time fields documented in
  `core/report/html.py` are masked (8, including stipulation and identity-link times; Codex).
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

## 2026-10-15: Quote check reads contacts and calls as the model sees them (#76, fixes #69)
- Changed: the quote check (`core/audit/invariants.record_text`) now reads a contact
  ("Name: +1...") and a call ("outgoing Phone call from +1... to +1..., duration 84 s") exactly
  as retrieval shows them to the labeler (`core.enrich.records`), so correct quotes are no longer
  discarded. Why it matters: the check drops a label before its stance is used, so a dropped
  "contradicts" or "complicates" could let a claim with other accepted support go SUPPORTED.
  The report still shows a call's time beside its line. Evidence stored before #76 still passes
  the stored-quote re-check in the contact or call text of its day, so an older case re-decides.
  The small model's generated contact rows follow the product too. The synthetic case01 affidavit PDF embeds DejaVu Sans for lines
  Helvetica can't draw ("Катя" read as boxes).
  Grok review on #80, item 3: the quote check now has a version. `core/audit/quotes.VERSION`
  1.1.0 -> 1.2.0 is stored in every audit run's config (a rules-only re-run carries its evidence
  run's; a run with another quote verifier, such as the eval's stand-ins, names it) and printed
  in the report beside the rule version; a test pins the check's answers to it, so a change
  without a bump fails. A quote now verifies only if it takes in a letter or digit of the
  record's own fields: at a word-aligned place in the pipeline, whatever verifier a run is
  given (`cites_record`), and at any place in the stored re-check
  (`core/audit/invariants.quote_is_verbatim`), which holds evidence stored before #76 to the
  check of its day. "(no name)", "unknown" or "call from" alone fail; "(no name): +1..." passes. `core/audit/quotes.record_text`, which still said calls had no
  citable text, now reads every record as the labeler sees it, as the pipeline already did.
- Where: main once PR #76 merges (branch `claude/project-thread-01fybj`, from the "Audit our
  model scoring" thread). Includes the C17 font fix.
- Verified: new regression tests (each fails without its fix), among them a contact and a call
  labeled "contradicts" and quoted as shown: before, the label was dropped and C01 went
  SUPPORTED; now CONTRADICTED. A test checks every case01 record reads the same for the labeler
  and the check. `make check` green on the branch with main at 3b33820 merged in (1929 passed, lint clean); `make eval` same as
  main (case01 1.00, 0 false supported; case02 aggregate 0.90); hostile run keeps 494 items and
  drops 4 labels (main 462 and 36), 0 supported. Offline, on stored answers: Opus case01 85% to
  95% (signed sheet), 60% to 70% (no sheet), 0 false supported; replayed through the new check,
  every Opus supports, contradicts and complicates label of the no-sheet run passes (108), and
  Sonnet and Haiku (2026-10-14) each lose 2, all on a message whose whole body is "?".
- Open: a label whose quote is not verbatim, has no letter or digit, or takes in only Baker's
  words or a placeholder is still dropped whatever its stance, and the report shows only a count
  of dropped labels. Runs from before #76 show "not recorded (1.1.0 or earlier)" for the quote
  check; re-running only their verdicts does not bring back labels the old check dropped, a
  full audit does (it reuses stored model answers). Generated call rows
  for the small model still print the report's time (signed guide rule 28), unlike the product;
  aligning them is for the "Custom model for Baker" thread. The guide's contact rows lack the
  colon (proposed for Arsh in PROPOSED_CHANGES.md); small-model run 5 trained on the old rows.
- Affects: capabilities (more correct evidence kept, for Opus and the 14B); closes, for contacts
  and calls, a path where a dropped "contradicts" or "complicates" let a claim go SUPPORTED.
  Report: a call's line shows its UTC and printed time, and the versions show the quote check.
  No privacy, network, performance or customer-claim change.

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
