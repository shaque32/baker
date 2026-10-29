# Validation v1, run 3: amendment to the signed test plan

`PREREGISTERED.md` and `PREREGISTERED_v2.md` stay as they are. This is the new version that v2's
low-coverage rule item 4 requires for a run 3.

Status: **draft, not binding.** It merges to main as a draft so the coverage steps can build on
it. It binds only when a later PR fills the prediction from the replay at the commit Arsh names
and this line records the date and his words of approval in the validation thread. Baker Product
then publishes the tag `validation-v1-run3` on that commit before run 3 starts. Nothing here
changes after run 3's results are seen.

## What run 3 is, and is not
- Run 3 reruns the same 106 signed iOS 15 claims, on the same phone, with the same answer keys.
- These claims are now **development data**. The fixes since run 2 were designed from replays
  of run 2's recorded model answers on these claims. So run 3 is a **coverage check only**.
  Whatever k is, no accuracy figure from run 3 is quoted outside the validation write-up: not
  on the site, the one-pager, the validation card or any customer material.
- A quotable accuracy number needs held-out claims. They must be fresh claims on a second phone
  (Android 14, or iOS 16 or 17), written by someone who has not seen these fixes and signed by
  Arsh, with code frozen at a tag before the claims are opened. That is a separate plan (v4),
  not this file.

## Every change since run 2's code
From `git log --first-parent d478705..validation-v1-run3`. At the time of writing, main is 00ccc9d.

| PR | What changed | Versions |
| --- | --- | --- |
| #144 | Pilot gate 5 split into 5a and 5b; status refresh. | none |
| #145 | A "Not tested" notice per format and version. | UFDR importer 0.3.2, report 0.18.0 |
| #146, #156, #157, #158 | Website only. | none |
| #147 | `pilot_link --check` explains a failure to reach R2. | none |
| #148 | Key-evidence loss report (eval only). | none |
| #149 | App, report and installer look. | report 0.20.0 |
| #150 | The filler reads real affidavit times, written time zones and export app names. | filler |
| #151 | Synthetic case03 (eval only). | none |
| #152 | The filler finds accounts written another way: numbers, person names, display names. | filler |
| #153 | The filler reads call lengths with halves, two parts and bounds. | filler |
| #154 | Challenge step behind a flag, off by default; simulated experts (eval only). | none in this run |
| #155 | A claim on Native Messages says it holds iMessages and SMS together. | report 0.19.0 |
| #159 | Testability agent behind a flag, off by default, eval only. Run 3 does not use it. | none in this run |
| #160 | Filler guards: the addressee is never the sender; a message's words come only from quotation marks; coverage is judged after the shape check; no one-way or call counts. | filler |
| #164 | Coverage plan steps 1 to 3. Meaning comes from the claim's one quote. Every quoted message needs a sender. A call's parties come from the claim, on the app it names. `stated_sender` is wider. A phone's own accounts are found. Counts may be written in words. Review fixes in the same PR only narrow what code fills. | time check 1.0.2, filler version "2" (recorded as `code_version`) |
| #165 | This file, and scorer 1.3.0 (tiers and measure 7 below). The checks' text match reads curly quotes as straight and runs of spaces as one; quote verification stays exact. | scorer 1.3.0; sender 1.0.2, weekday 1.0.2, time 1.0.3 |
| #162 | Challenge step on by default. The run driver turns it off for run 3 (see Agents). | none in this run |
| #163 | Testability agent: claim-only check, the examiner's accept card, and the scripted demo. Still off by default; run 3 does not use it. | none in this run |
| #169 | Coverage steps after Arsh's rulings R1, R4, R5, R6 and fills a to g: native calls by number, one number written two ways as one party, open no-contact ranges to the extraction's edges, writers from "instructed ..., writing", part-day ranges, call counts, and code-made assumptions marked "Filled from the claim's wording." The run driver links a defined number's accounts (R4) and turns the challenge step off. | filler; count 1.1.0; run driver |
| R2/R3 PR | Arsh's rulings R2 and R3 (signed contracts fields `sent_by`, `each_way`): a message count of what one side sent, and "exchanged" messages as at least one each way, never failed on one side's silence. Code sets them only from the claim's words. Assumption ids change once (the id hashes the new default fields). | count 1.2.0; filler; AssumptionParams fields |

Any PR that merges after #165 and before the tag is added to this table before approval.

These stay unchanged, byte for byte, as v2 lists them: rules 0.3.0, every prompt (including
the assumptions prompt), model pins, contracts, schema and gold. Because the assumptions prompt
and model are unchanged, the model's answers should repeat run 2's.

## Disclosure: these fixes were designed after seeing runs 1 and 2
The fixes since run 2 were designed after seeing run 1's and run 2's refusals, and replays of
run 2's recorded answers on these claims. The answer key was not used to design them. Run 1's
null result and run 2's insufficient coverage (9 of 106) are reported with run 3.

## Prediction (stated before run 3)
- Replaying run 2's recorded answers through this PR's code, and running the deterministic
  checks on run 2's case database, gives **35 of 106** tested: **18 code-checked**, **13 check
  unsettled** and **4 expert only**. At main e99c0a8, before the text fold, it was 7, 24 and 4.
  This is development data, in the project's `run-v2/replay/REPLAY.md`. The replay is re-run at
  the tag, and this line is updated before approval if anything merged since then changes it.
- What still leaves checks unsettled: the other party is tied to no account, a display name
  two accounts share, records only outside the claimed window, one number stored as two
  accounts, and quoted words that are not on the phone. The last is the right outcome.
- If the A10G repeats run 2's answers byte for byte, run 3's k and tiers equal the replay's.
  Any other result is reported with its cause: either the A10G did not repeat its answers, or
  the replay missed a code path.

## When run 3 runs
Run 3 runs only when the replay at the tag predicts at least 30 code-checked claims. Until then
the remaining coverage steps (native calls recorded under app "unknown", message direction,
call and one-way counts) come first, each replayed the same way. Each step that changes code is
added to the change table above. This file's Status line changes to approved only after that
replay, with its numbers in the prediction above.

## Tested, in three tiers
A claim is tested as in v2: it has a first-pass verdict and is not marked "Not tested". The
scorer (1.3.0) puts each tested claim in one tier:
1. **Code-checked:** a deterministic check (sender, time, count, absence, contact entry, same
   account or weekday) on a core assumption passed or failed.
2. **Check unsettled:** checks ran on a core assumption, but every one was inconclusive, for
   example none found, or a party tied to no account. The pipeline writes a check result only
   for a check that applies, so these checks did run on the phone's records.
3. **Expert only:** no check ran on a core assumption; every core assumption is stance-only or
   expert-only (meaning, event, role, person identity or authorship).

All three tiers are reported. Only tier 1 counts toward the minimum.

## Assumption fidelity audit (before scoring)
Before the scorer runs, every tested claim's assumptions are read against the claim text, with
the answer key closed. Each assumption must name the claim's own person, phone, time range and
app, and quote only the claim's quoted words. The audit records one line per claim.
- An agent does the audit, working only from the claims file and the run's assumptions. It
  never opens the answer keys. Arsh spot-checks 5 claims it passed.
- Bar: **0** assumptions that name a wrong person, phone, window or app, or that use non-quote
  words as a quote.
- Any failure is reported as a defect with its claim, and run 3's numbers carry it.

## Measures
As v2, over tested claims only, plus a new measure numbered after v1's six:
- **7. Contradicted by a failed check, gold not contradicted: 0 expected.** Only the failed
  checks the Contradicted verdict cites count (rule 1a: checks on core assumptions); a failed
  check on a non-core assumption beside a stance contradiction does not. Each such claim is
  listed with its check and records.
- False Supported: 0, as before.
- Coverage: k of 106, split by tier, with every refusal kind and its count.
- Gold gets no "testable from this phone" marking for run 3.

## Minimum
**30 code-checked claims (tier 1).** Below that, run 3 is reported as "insufficient coverage",
as in v2. At or above it, run 3 is still development data (see above). It shows only that the
coverage fixes work on a real export.

## Determinism
A second run 3 runs on the same A10G type, at the same tag, with stored-output reuse off for
the assumptions and stance passes. It reports how many model answers match byte for byte, and
whether any verdict differs. Determinism on AWS stays unmeasured until this is done. The Mac
result (14B on GPU, 105 of 105) does not carry over.

## Agents
- The challenge step (#154) is on by default since #162, so the run driver
  (`eval/validation/hickman_run.py`) turns it off, and `run.json` records `"challenge": false`
  (the audit's stored configuration has no challenge entry). Run 3 then changes only the
  filler fixes and checks above and stays comparable to run 2.
- The testability agent (#159) is off by default and eval only. Run 3 does not use
  it, and its repairs never count toward tested claims or the minimum.

## Frozen version
The git tag `validation-v1-run3` goes on the main commit that carries this file and the
changes above. Arsh names the commit, and Baker Product publishes the tag on it. The machine is as in v2: AWS g5.xlarge
(A10G), or g6.xlarge as the fallback. `run.json` records which.

## Disclosures that travel with every run 3 number
- The fixes were designed after seeing runs 1 and 2, as above. The answer key was not used.
- Run 1's null result and run 2's insufficient coverage are reported with run 3.
- Model-side refusals that remain are counted on their own.
- Determinism is measured on the A10G if the second run above is done, and is otherwise
  stated as measured on the Mac only (14B on GPU, 2026-10-24), not on AWS.
- Chats with messages: 128 against 109 in the independent dump. This is a lead, not a known
  bug.
