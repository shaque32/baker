# Validation v1 on public phone data: test plan, written before any Mabillon run (DRAFT)

Status: DRAFT, not signed. It binds once Arsh signs it in thread "Real-world accuracy
validation" and it is merged to main before any Mabillon run on the phone below. The PR that
merges it records the signature. After that,
nothing in it changes; a change means a new version of this file, a new tag and a new run,
and every version is reported.

Public data only (Josh Hickman's iOS 15.3.1 test iPhone on Digital Corpora). Never case02.
Phone content and the answer key stay outside the repo; this file records their hashes.

## Question
On a real-format extraction with an answer key nobody on the build side could tune to, how
often does a frozen Mabillon version (1) contradict a claim on its own when the claim is not
false, (2) miss a false claim or show it to the expert only as support, and (3) reach the
key's verdict once an expert accepts the right evidence?

## Answer key (signed before this file; not editable)
| File (project files `baker/validation/hickman/ios15/`) | Claims | S / C / U | SHA-256 |
|---|---|---|---|
| `gold.jsonl` (C01-C30) | 30 | 11 / 10 / 9 | 489cfaf68e272c852a982845c6a2fe424e1242e89860fce4fae0677070286d6b |
| `gold_b2.jsonl` (B01-B40) | 40 | 15 / 12 / 13 | 1ea1371184b8d4217705fa3904a8c997793455f2be82604115154f716ddd9355 |
| `gold_b3.jsonl` (D01-D36) | 36 | 6 / 15 / 15 | 83dbb11a32c0201185947d321ed7c50ed95eb34a05adce414ac96cf1732097ce |
| All | 106 | 32 / 37 / 37 | 74 not supported, 69 not contradicted |

How it was made (`PROTOCOL-draft.md`, `SIGNED.md` beside the keys): a writer agent wrote the
claims from the creator's activity log and an independent ElementTree dump of the UFDR's
report.xml, never from Mabillon output. Three blind AI readers labeled every claim (Fleiss'
kappa 1.00, 0.97, 1.00 by batch). Arsh ruled on the split and flagged items and signed all three
keys on 2026-10-22. Mabillon has never been run on this phone.

## Inputs
- UFDR: `iOS_15_Public_Image_Reader/iPhone 8/iOS_15_Public_Image.ufdr`, 30,705,362,520 bytes,
  Reader 7.48, PA 7.62.0.40. Its SHA-256 is computed on the run machine and recorded before the
  import; its report.xml must hash to
  `bf9bab624cebb7cd32d8543d0db60894b587597ae03d8ec97375862050ec7b8d`, or the run stops.
- Claims: `validation-claims-ios15.jsonl` (project files, beside the keys), the 106 claims'
  id, paragraph number, text and claim type, with no labels and no evidence, SHA-256
  `ee0f124479ce6ebe449723ed8dd1a04c81d653ba300f892feaa284fc5fc068be`. It is the only case file
  the run machine gets; the keys never leave project files. Nine batch 3 claims carry the type
  `content`, which Mabillon does not have; they run as `content_meaning`. The type only picks
  which checks run; the keys do not depend on it.
- Affidavit: one PDF with claim n's text, verbatim, as printed paragraph n (1-106), rendered
  by `eval/validation/hickman_run.py` at the tag.

## Frozen version
Git tag `validation-v1` on the main commit that carries this file once signed. Recorded with
the run: rule version (0.3.0 today), pipeline version, quote-check version, prompt SHA-256s
(`core/audit/prompts/stance.md` v1.1, `assumptions.md`), model file SHA-256 (qwen3-14b-q4_k_m,
`500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0`, n_ctx 8192, the pins in
`packaging/windows/pins.json`), llama-cpp-python 0.3.36 built for CUDA, GPU, driver, machine
and OS (`run.json` in the results). A run on any other commit or model is not a
validation-v1 run.

Machine: an AWS g5.xlarge (NVIDIA A10G, 24 GB; 4 vCPU, 16 GB RAM) on the Deep Learning Base
OSS Nvidia Driver GPU AMI (Ubuntu 24.04), set up and run by `eval/validation/aws_run.sh` at the
tag. A g6.xlarge (NVIDIA L4) is the fallback if no g5 is offered; `run.json` says which ran.
Labels from CUDA may differ from the Mac's Metal build on some items; the run reports the
machine it used and claims nothing about the other.

## Procedure (one run; the audit may be stopped and resumed, which Mabillon supports)
`eval/validation/hickman_run.py` does steps 1 to 4 with the same library calls the `baker`
commands make, and stops before importing anything if the claims file or report.xml has
another hash.
1. New case, local mode (cloud off). Import the UFDR, then the affidavit PDF.
2. Claims entered verbatim from the claims file, each on its own paragraph, by
   `expert:validation`. Claim proposal is not used (it is a separate measurement).
3. One stipulation, as the affidavit defines it: the TARGET PHONE was used by SUBJECT-1
   (by `expert:validation`). Nothing about SUBJECT-2 is stipulated.
4. The audit with the product defaults (`baker audit`): assumptions filled by the local model,
   no human edits, no AI reviewer, no `--label-all`.
5. R1, unreviewed: score the run as it stands (machine only).
6. R2, simulated expert: the eval's simulated expert (`eval/simulated_expert.py`) accepts an
   item only when its record is in the claim's signed key evidence and its label points the
   way the gold verdict does, dismisses every other item, and the rules re-run (`baker
   redecide`). This measures retrieval, checks and rules given a perfect expert.
7. R3, real examiner (later, separate report): an outside examiner reviews the R1 case blind
   to the key.
Key evidence is mapped from the dump's `source_index` to Mabillon records by content: the
record's kind, its UTC time to the second, and its text (a message's body, a call's parties
and duration, a contact's name and identifier). Mabillon's own record ids are positional and
do not keep the UFDR's model id, so content is the link both sides share. A key record with
no single match is listed. It is left out of key-evidence recall, and the simulated expert
cannot accept it, so R2 may miss that claim's support; every such claim is listed beside the
R2 numbers, and none is dropped from verdict scoring.

Blind analysis: the scoring script (R1 measures, the mapping, R2) is tested on synthetic data
and merged to main before anyone opens the run's `results.zip`. Until then the results file
is only copied and stored, and its SHA-256 is recorded on arrival.

## Primary measures (each k of n with a Wilson 95% interval, overall and by claim type)
1. **Contradicted without an expert (R1)**: claims R1 calls contradicted whose gold is not
   contradicted (n = 69). Under rules 0.3.0 only a failed deterministic check can do this.
   Expected 0. Every case is listed with the check that decided it.
2. **False claim shown only as support (R1)**: gold-contradicted claims (n = 37) where the
   expert's queue holds a "supports" item and no failed check and no "contradicts" item. This
   is the way a false claim could get past a hurried expert.
3. **Contradiction surfaced (R1)**: gold-contradicted claims (n = 37) with a failed check, or a
   "contradicts" item on a key record.
4. **R2 verdicts** (`eval/validation/card.py` at the tag): accuracy (n = 106), false supported
   (n = 74), false contradicted (n = 69), missed contradiction (n = 37), missed support (n = 32),
   and the per-check outcome table. False supported is expected 0 and, if so, bounds the rate
   at 4.9%; any false supported is reported as a defect with its cause.
5. **Key evidence**: share of key records retrieved, and surfaced to the expert.
6. **Import fidelity**: Mabillon's message, call, contact and chat counts against the
   independent dump's top-level counts (in `MANIFEST.md` beside the keys), and `baker ufdr-check`
   on the same package.

Reported beside these, never changing them: every claim's R1 and R2 verdict and reasons, stance
label counts and contradicts precision on key records, model calls and time per claim, and
every claim with no prediction (counted wrong, never false supported or false contradicted).

## Rules for the analysis
- One scoring per tag, with the code at the tag. No gold edit after any output is seen. If an
  output suggests the key is wrong, the key stays as signed for this run; a corrected key is a
  new signed file, scored separately and labeled post hoc.
- Nothing is excluded after the fact. A claim Mabillon cannot ingest or finish counts as no
  prediction.
- All numbers are published, including bad ones. No claim of an error rate outside these
  numbers, these claims and this phone.

## Model
One arm: the local 14B with stance v1.1 (the product default, and the mode recommended for
court). Arsh chose this on 2026-10-24; no cloud arm runs for validation-v1. Size estimate
from case01 (494 labels for 20 claims): about 2,600 labels. Speed on the A10G is not measured
yet (the Mac took about 34 s per label); the run records it. Known weakness from #120:
contradicts precision 58% on the signed probe set. That shows up in measures 2 and 3 and in
the expert's queue, not in R1 verdicts.

## Limits, stated now
- The claim writer and the readers are Claude models, the same family as Mabillon's optional
  cloud labeler (not used in this run), so their errors may be correlated with each other.
  Two of three batches had unanimous readers who also matched the writer: the claims may be
  easier than an affidavit's. An outside examiner's blind sample of 20% of the claims is the
  planned check.
- One phone, one extraction tool version, casual test conversations rather than the
  multi-party content real affidavits describe.
- R2's simulated expert is perfect by construction; R3 is the measure of a real one.
