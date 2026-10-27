# Validation v1, run 2: amendment to the signed test plan

The signed plan (`PREREGISTERED.md`) stays as it is. It says "a change means a new version of
this file, a new tag and a new run, and every version is reported": this is that new version.

Status: Approved by Arsh on 2026-10-26 at 23:03 UTC ("ok approved", in the project chat, in
reply to a request for "approved, minimum 30"). That approval covers this file as merged in
#140 (924f3d4) and the change list and low-coverage rule added in #141. It binds before run 2
starts.

## What happened in run 1 (reported as a null result)
- Run 1 ran on AWS (A10G) with the local 14B. It ran at commit 30fcf4d, not at tag
  `validation-v1` (2e3bc92). Its report step stopped twice on the "deleted state" wording,
  which #137 fixed. The rerun at 30fcf4d reused all 106 model outputs.
- No claim was tested. All 106 came out unproven, "Not tested", because the assumption
  filler refused every proposal. There were 0 stance calls and 0 evidence items.
- Run 1's zero error rates are vacuous. They are reported as a null result with these causes
  and never quoted as an error rate.
- Import fidelity was measured: messages, calls and contacts match the independent dump
  exactly. Chats with messages are 128 against 109; this is a lead, not a known bug.
- Causes, counted as claims with at least one refusal of each kind:
  - phone named "TARGET PHONE" not resolved: 33;
  - UFDR time-zone format not read: 16;
  - SUBJECT-2 never set up as a person: 13;
  - account not found: 11;
  - model-side refusals: 43.

## What changed for run 2 (PR #139, merged to main on 2026-10-26)
1. Phone time zones in Cellebrite's format are read when the stated offset matches. A report's
   display zone is never taken as the phone's zone.
2. The expert can record the document's names for a phone ("TARGET PHONE"). The filler
   matches them, and every report lists them as the expert's statement.
3. Numbered people (SUBJECT-1, SUBJECT-2) can both exist. Before, adding SUBJECT-2 was refused.
4. The run driver sets the case up as the affidavit defines it, replacing v1 procedure step 3:
   - the phone is named TARGET PHONE;
   - SUBJECT-1 used it, as a stipulation by `expert:validation`;
   - every other SUBJECT-<n> the claims text names is added as a person, with no stipulation
     and no identity link.

   The list comes from the claims text by that rule alone, never from the answers. Nothing
   about SUBJECT-2 is stipulated or linked, as in v1.

## Every change since run 1's code
Generated from `git log --first-parent 30fcf4d..main` (30fcf4d is the commit run 1 ran). Nothing
outside this list changed between run 1's code and the commit tagged for run 2. In particular,
`core/audit/rules.py` (rules 0.3.0), every prompt under `core/audit/prompts/`, the model pins in
`packaging/windows/pins.json`, `core/contracts.py`, `core/schema.sql`, everything under
`eval/gold/` and `eval/validation/score_hickman.py` are byte-identical to 30fcf4d, except as
the scorer entry below says.

| PR | Effect | Versions |
| --- | --- | --- |
| #138 | A stance rationale containing a forbidden word (guilty, innocent, leader, deleted) is withheld from that item instead of refusing the whole report; the expert must acknowledge it (audit-log `rationale.acknowledge`) before confirming or overriding that claim's verdict. Stance labels, quotes and verdict rules are unchanged. | report 0.16.0 |
| #139 | Phone time zones in Cellebrite's UFDR and Windows display forms resolve to IANA names when the stated offset matches; the Cellebrite Excel/PDF importer never stores the report's display zone as the phone's zone; the expert can give a phone the document's names (audit-log `device.names`), which the assumption filler matches and the report lists; name words keep a designation's number (SUBJECT-2); a name change marks verdicts out of date; the run driver names the phone TARGET PHONE and adds each other SUBJECT-<n> as a person, and never resumes run 1's case. | report 0.17.0, Cellebrite importer 0.3.1, identity proposer 1.1.0 |
| #140 | This file (first version), the run-2 tag named in `aws_run.sh`, and a test of name words. | none |
| #141 | This file: approval date, this change list and the low-coverage rule. | none |
| #142 | `score_hickman.py` reports what the low-coverage rule below requires (k tested, each refusal reason and its count, measures over tested claims). It adds outputs and changes no existing measure. It merges before the tag, so before run 2's results exist. | none |
| #THIS_PR | Scorer fix before the tag: a claim is tested only when it has a first-pass verdict and is not marked "Not tested"; a claim with neither is untested ("no verdict recorded") and never scored; coverage must account for every gold claim or the scorer stops; refusal kinds match whole refusal phrases, so a bare word such as "range" is unclassified. It changes no existing measure over all claims. | scorer 1.2.0 |

## Disclosure: these fixes were designed after seeing run 1
The fixes come from run 1's refusal reasons on this phone. Only the filler's refusals and the
import counts were looked at. The answer key was not used to design them: run 1 had no
verdicts to compare, so its score carried no verdict information. No gold label, claim text,
prompt, rule, model or threshold changed. All four fixes are general product behaviour,
tested on synthetic data. The report on run 2 states this disclosure next to its numbers.

## Unchanged from v1
These stay exactly as signed:
- answer keys and their hashes;
- claims file and its hash;
- UFDR and report.xml hash;
- model file, its pins and stance prompt v1.1;
- rules 0.3.0, one arm (local 14B), no AI reviewer, no `--label-all`;
- primary measures 1 to 6 as defined, reported under the low-coverage rule below;
- rules for the analysis;
- scoring with `eval/validation/score_hickman.py` as merged in #134, plus only the additions
  the low-coverage rule needs, merged before the tag;
- limits.

## Frozen version
Git tag `validation-v1-run2` on the main commit that carries this file, #139 and the scorer
additions. A run on any other commit or model is not run 2. Machine as v1: AWS g5.xlarge
(A10G), or g6.xlarge as the fallback; `run.json` records which ran.

## Procedure
As v1, with step 3 replaced by "What changed" item 4. The run starts a new case: the driver
refuses to resume run 1's case, and `aws_run.sh` writes to a new folder and keeps run 1's
`results.zip` under another name.

Blind analysis as v1. The scorer is already on main, and run 2's `results.zip` is only copied
and hashed on arrival until it is scored with that code.

## Low-coverage rule (stated before run 2)
Run 1's 43 model-side refusals are not fixed, so run 2 may again test only part of the 106.
A claim is **tested** when the run did not mark it "Not tested", that is, it got at least one
core assumption (`not_tested` in the run's record). Every other claim is **untested**.
1. Always report k, the number of tested claims out of 106, next to any other number, with each
   refusal reason that left a claim untested and its count, as the scorer prints them.
2. Report each verdict measure (primary measures 1 to 4) only over tested claims: k of n, with
   a Wilson 95% interval, where n counts the tested claims in that measure's base. Never report
   one as a share of 106, or of a base that includes untested claims. Untested claims are
   listed by id with their reason, never counted correct or wrong. Measures 5 and 6 (key
   evidence and import fidelity) are reported as in v1.
3. The minimum is **30** tested claims. If k is below it, run 2 is reported
   as "insufficient coverage, no accuracy claim". Its counts appear only in the validation
   write-up, with this rule, and no site, one-pager, validation card or customer material
   quotes a number from it.
4. A run 3 that fixes refusals needs a new version of this plan, written and signed before
   that run. Nothing in this plan changes after run 2's results are seen.

## Reporting
Run 1 (null result, with its causes) and run 2 are both reported. Run 2's numbers carry:
- this file's disclosure;
- the model-side refusals counted on their own, as a finding about the 14B assumption filler.
