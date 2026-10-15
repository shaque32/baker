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

## 2026-10-15: Quote check reads contacts as the model sees them (fixes #69; PR not open yet)
- Changed: one function now renders a contact ("Name: +1...") for retrieval, the quote check,
  `core/audit/quotes.py` and the small model's generated training items, so correct contact
  quotes are no longer discarded. The synthetic case01 affidavit PDF embeds DejaVu Sans for
  lines Helvetica can't draw ("Катя" read as boxes).
- Where: local only, committed in the "Audit our model scoring" thread, not pushed; expected as
  its own PR (number not yet assigned; #71 is this docs PR). Not checked in the repo by this doc's owner.
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
- Where: branch #66, not merged.
- Verified: new tests in `tests/test_assumption_filler.py`; all 3 Codex findings fixed (per the
  owning thread); CI pending on the latest push.
- Open: the owning thread proposes rules version 0.2.2 (no rule logic change), pending Arsh's
  sign-off; the branch still says 0.2.1. Verdicts decided under 0.2.1 can differ after this.
- Affects: capabilities (which claims get a time window), verdicts on time-bound claims.

## 2026-10-15: Opus fails the signed probe; quote-check bug found (issue #69)
- Changed: nothing in the product yet. Opus re-run on the signed P001-P105 set: contradicts
  precision 73% (bar 90%) in both arms, every miss a told-frame or undated denial. A grading audit
  found the quote check renders contacts and calls differently from what the model is shown.
- Where: results in `/mnt/project-files/baker/cloud-bench/2026-10-15/` (RESULTS.md,
  GRADING_AUDIT.md); signed labels on branch #64 (`737a0ce`, not merged); bug is on main, open
  as issue #69 (no fix PR yet).
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

## 2026-10-15: Opt-in cloud stance labels, local by default (#68, 24eda3e)
- Changed: Opus 5.5 (medium) labels stance only for cases where the expert attests the
  protective order allows cloud AI and opts in, on the expert's own Anthropic key; the local
  Qwen3-14B labels every other case and catches every failed cloud call. Reason: Opus is the
  first model to pass the full cloud bench rule. Arsh chose "Opt-in cloud" as the positioning
  (2026-10-15 07:10Z), replacing the earlier "cloud first" wording.
- Where: branch #68, draft, not merged.
- Verified: CI green on 24eda3e (Ubuntu, Windows, installer, Mac clean install). 25 new tests in
  `tests/test_cloud.py`. Model-free gate unchanged (the gate does not exercise the cloud path).
  Opus case01: 85%, 0 false supported, 26 min, $7.83.
- Open: Opus failed the signed probe's contradicts bar (entry above), so a signed prompt fix
  should land first; CLAUDE.md wording in `PROPOSED_CHANGES.md` awaits application on the branch; the key file
  is not encrypted with the case keys; no real-case cost measured (tens of dollars, inferred).
- Affects: capabilities, privacy (case records leave the computer for opted-in cases),
  performance (26 min vs hours locally), customer-facing claims ("fully offline" is no longer
  true for opted-in cases once merged).

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

## 2026-10-15: Fixes waiting to merge (#64, #65, #67)
- Changed: #65 fixes main's red test (test only). #67 fixes a flaky recovery-key test. (#66 has
  its own entry above.) #64 fixes the
  go-bar scorer and holds the probe follow-up proposal for guide v0.3.
- Where: branches, not merged. All CI green.
- Verified: CI green on each head.
- Open: #64's signed probe relabels are not yet applied to `eval/gold/probe/`.
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
