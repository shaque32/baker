# Validation v1, run 3: amendment to the signed test plan

`PREREGISTERED.md` and `PREREGISTERED_v2.md` stay as they are. This is the new version that v2's
low-coverage rule item 4 requires for a run 3.

Status: **draft for Arsh to approve. It is not binding until he approves it in the validation
thread.** After approval this line records the date and his words, the file merges to main, and
the tag `validation-v1-run3` is made on that commit before run 3 starts. Nothing here changes
after run 3's results are seen.

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
From `git log --first-parent d478705..[run 3 tag]`. At the time of writing, main is e99c0a8.

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
| #160 | Filler guards: the addressee is never the sender; a message's words come only from quotation marks; coverage is judged after the shape check; no one-way or call counts. | filler |
| #164 | Coverage plan steps 1 to 3. Meaning comes from the claim's one quote. Every quoted message needs a sender. A call's parties come from the claim, on the app it names. `stated_sender` is wider. A phone's own accounts are found. Counts may be written in words. Review fixes in the same PR only narrow what code fills. | time check 1.0.2, filler version "2" (recorded as `code_version`) |
| [this PR] | This file, and scorer 1.3.0 (tiers and measure 5 below). | scorer 1.3.0 |
| [any later PR] | [effect and versions] | |

These stay unchanged, byte for byte, as v2 lists them: rules 0.3.0, every prompt (including
the assumptions prompt), model pins, contracts, schema and gold. Because the assumptions prompt
and model are unchanged, the model's answers should repeat run 2's.

## Disclosure: these fixes were designed after seeing runs 1 and 2
The fixes since run 2 were designed after seeing run 1's and run 2's refusals, and replays of
run 2's recorded answers on these claims. The answer key was not used to design them. Run 1's
null result and run 2's insufficient coverage (9 of 106) are reported with run 3.

## Prediction (stated before run 3)
- Replaying run 2's recorded answers through main e99c0a8 gives **35 of 106** tested: **31
  code-checked** and **4 expert only**. This is development data, in the project's
  `run-v2/replay/REPLAY.md`. The replay is re-run at the tag, and this line is updated before
  approval if anything merged since then changes it.
- If the A10G repeats run 2's answers byte for byte, run 3's k equals the replay's. Any other
  k is reported with its cause: either the A10G did not repeat its answers, or the replay
  missed a code path.
- The margin over the minimum is one claim. If the A10G answers differently on two
  code-checked claims, run 3 is "insufficient coverage" again.

## Tested, in two tiers
A claim is tested as in v2: it has a first-pass verdict and is not marked "Not tested". The
scorer (1.3.0) puts each tested claim in one tier:
1. **Code-checked:** at least one core assumption went to a deterministic check (sender, time,
   count, absence, contact entry, same account or weekday), whatever the outcome.
2. **Expert only:** every core assumption is stance-only or expert-only (meaning, event, role,
   person identity or authorship).

Both tiers are reported. Only tier 1 counts toward the minimum.

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
As v2, over tested claims only, plus:
- **5. Contradicted by a failed check, gold not contradicted: 0 expected.** Each such claim is
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
- The challenge step (#154) is off by default at main, and run 3 does not turn it on. If a
  later PR makes it default-on before the tag, the run driver must turn it off explicitly in
  that PR or this one, and `run.json`'s configuration records it. Run 3 then changes only the
  filler fixes above and stays comparable to run 2.
- The testability agent (#159), if merged, is off by default and eval only. Run 3 does not use
  it, and its repairs never count toward tested claims or the minimum.

## Frozen version
The git tag `validation-v1-run3` goes on the main commit that carries this file and the
changes above. Arsh makes the tag in GitHub Releases. The machine is as in v2: AWS g5.xlarge
(A10G), or g6.xlarge as the fallback. `run.json` records which.

## Disclosures that travel with every run 3 number
- The fixes were designed after seeing runs 1 and 2, as above. The answer key was not used.
- Run 1's null result and run 2's insufficient coverage are reported with run 3.
- Model-side refusals that remain are counted on their own.
- Determinism is measured on [Mac only / A10G too].
- Chats with messages: 128 against 109 in the independent dump. This is a lead, not a known
  bug.
