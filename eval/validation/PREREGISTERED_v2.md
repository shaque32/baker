# Validation v1, run 2: amendment to the signed test plan

The signed plan (`PREREGISTERED.md`) stays as it is. It says "a change means a new version of
this file, a new tag and a new run, and every version is reported": this is that new version.

Status: DRAFT until Arsh says "approved" in thread "Real-world accuracy validation". It binds
from its merge to main, before run 2 starts.

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
- primary measures 1 to 6;
- rules for the analysis;
- scoring with `eval/validation/score_hickman.py` as merged in #134;
- limits.

## Frozen version
Git tag `validation-v1-run2` on the main commit that carries this file and #139. A run on any
other commit or model is not run 2. Machine as v1: AWS g5.xlarge (A10G), or g6.xlarge as the
fallback; `run.json` records which ran.

## Procedure
As v1, with step 3 replaced by "What changed" item 4. The run starts a new case: the driver
refuses to resume run 1's case, and `aws_run.sh` writes to a new folder and keeps run 1's
`results.zip` under another name.

Blind analysis as v1. The scorer is already on main, and run 2's `results.zip` is only copied
and hashed on arrival until it is scored with that code.

## Reporting
Run 1 (null result, with its causes) and run 2 are both reported. Run 2's numbers carry:
- this file's disclosure;
- the model-side refusals counted on their own, as a finding about the 14B assumption filler.
