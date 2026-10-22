# GPU test and probe

Checks whether a local model can run Baker's reviewer and stance steps well enough, on the
machine that will run Baker. Everything here is synthetic.

## Files
- `smoke_reviewer.jsonl`, `smoke_stance.jsonl`: provisional items written by Claude so the test
  can run before the signed probe set exists. Rebuild with `python -m eval.probe.build_smoke`.
  Results on them are provisional; the signed probe set (thread 3, signed by Arsh) replaces them.
- `stance_draft.md`: the old probe-only stance prompt, kept for comparison. The probe now scores
  the signed product prompt `core/audit/prompts/stance.md` (the local model's) by default
  (`--stance-prompt` picks another). The cloud bench (`eval/bench/claude_bench.py`) scores the
  cloud model's own signed prompt, `core/audit/prompts/stance_cloud.md`, by default.
- The reviewer prompt is read from `core/audit/prompts/reviewer.md` unchanged.
- `results/`: per-item answers behind a `PROBE_PASSED` entry (`core/llm/cloud.py`), one row per
  item: set, the set file's sha256 (first 16 hex), item id, gold stance, whether it counts
  (`scored`), first and second answer. Ids and labels only, no item text. `2026-10-15-opus-5-5-medium-stance-v1-2.jsonl`
  is Opus 5.5 at medium with stance v1.2 on the signed set (`eval/gold/probe/probe.jsonl`) and
  on the two new sets, from the preregistered runs of 2026-10-15.
- `stance_v1_1_draft.md`: the signed stance wording, line for line, reordered so every fixed
  instruction comes before the case data. Consecutive calls on one assumption then share the
  whole prompt up to the record, which llama.cpp does not read again. On case01 (no model) the
  text the model must read drops from 89% to 56% of the prompt text. Not used by the product
  until Arsh signs it. `bash eval/probe/mac_speed_round2.sh` scores it against the signed v1.0
  on the probe set and times both on the same claims (see "Faster calls, round 2").

## Signed probe set (thread 3)
`run_probe --probe-set <eval/probe_draft/probe_draft.jsonl>` scores the signed set directly.
Only signed, undisputed items count toward a pass bar; disputed items and drafts are scored
and reported under `not_gated` (Arsh's rule, 2026-10-07). Accuracy alone misleads: a reviewer
that dismisses everything scores about 65% on the gated set, so read the false-accept rate and
the clear-accept rate (support recall) next to it.

## Run on a Mac (Apple silicon)
1. `python3 -m venv .venv && source .venv/bin/activate`, then `pip install -e ".[dev,local]"`.
   On Apple silicon llama-cpp-python builds with Metal by default, so the model runs on the GPU.
   Xcode command line tools are needed for the build (`xcode-select --install`).
2. Pick models that fit in memory: 16 GB fits 8B models at Q4/Q5; 24 GB or more fits 14B at Q4_K_M.
3. Steps 3 to 5 below are the same. Accuracy results carry over to Windows; speed does not.

## Run on the GPU PC (Windows)
1. `python -m venv .venv` and `.venv\Scripts\activate`, then `pip install -e ".[dev]"`.
2. llama-cpp-python with CUDA. Prebuilt wheel first:
   `pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124`
   (pick the cuXXX that matches `nvidia-smi`). Otherwise build it: install VS Build Tools and the
   CUDA toolkit, `set CMAKE_ARGS=-DGGML_CUDA=on`, `pip install llama-cpp-python --no-binary :all:`.
3. Download GGUF files to a folder outside the repo. Check each model's license on its original
   model card. Only permissive licenses (Apache-2.0, MIT).
4. Copy `models.example.json` to `models.local.json` (git-ignored) and list each file.
5. `python -m eval.probe.run_probe --models eval/probe/models.local.json --repeat 2`

Output goes to `eval/out/probe/`: `summary.md`, `summary.json`, and one `<model>.calls.jsonl` per
model with every raw output, including the ones that failed to parse.

## Pass bars (wave2-consensus.md section 4)
valid output 100%, quote check >= 95%, "supports" precision >= 95% and recall >= 90%,
zero reviewer false accepts on overreach items, identical output on a repeat run.
An invalid reviewer output counts as a dismissal, and a stance whose quote is not verbatim is
dropped, so neither can turn into a false "supported".

## Cloud Claude benchmark (eval only)
Can cloud Claude be offered as a per-case opt-in? `eval/bench/claude_bench.py` runs the signed
probe set (reviewer and stance) and then synthetic case01 through the real pipeline, with the
cloud model as the stance labeler, the simulated expert and the merge-gate scoring. It reports
the Expert-confirms bars, reviewer overreach, case01 accuracy and false supported, key evidence
surfaced, and time and cost for the case, beside the local 14B's signed results.

    pip install -e ".[bench]"
    export ANTHROPIC_API_KEY=...        # or an `ant auth login` profile
    python -m eval.bench.claude_bench   # Sonnet 5.5 and Haiku 5.5, effort medium
    # writes eval/out/bench/RESULTS.md and summary.json

Only the signed probe files and case01 can go to the API; any other file, and case02, is refused
before a client is made. `--dry-run` runs everything on a stand-in client with no network.
`--skip-case` runs the probe only; `--claims C02,C05` runs part of case01 (reported, not
decided). Agreeing with Claude does not count as being right; only the signed labels score.

Decision rule, fixed 2026-10-13 before any cloud run: a model is a candidate for a per-case
opt-in only if it meets all four Expert-confirms bars on the signed undisputed items (including
zero contradicting items shown as support, which the 14B missed with 5 on the 2026-10-07
labels and meets on the v0.3 labels Arsh signed 2026-10-14) and has zero false
supported and verdict accuracy >= 0.80 on case01 after the simulated expert. Among candidates,
the cheaper per case. Reviewer overreach and repeat identity are reported, not gated. Passing
changes nothing in the product: the cloud rule in CLAUDE.md is Arsh's to change.

Probe input and scoring, from the grading audit of 2026-10-14
(cloud-bench/2026-10-14/GRADING_AUDIT.md and its 10-reader consensus): the probe shows a signed
item the way the product shows a record. The RECORD is the message text alone and the context
uses core/audit/context.py's layout (local-time header, '>>' on the record, direction)
(`--layout product`, the default). `--layout product_members` also opens the context with the
chat's members line, built from the excerpt's senders, as stance prompt v1.1's wiring will send
it; use it with v1.1. `--layout legacy` reproduces earlier runs. Quotes are checked with the
product's core/audit/quotes.verify_quote. `--stance-prompt eval/probe/stance_v1_1_signed.md`
(only prompt files in core/audit/prompts/ and eval/probe/ are accepted) scores a model on the
signed v1.1 text, which the v0.3 labels follow; a v1.0 run scored on v0.3 labels mixes two rule
sets. The bars are unchanged; `expert_confirms(...)["reported"]` adds traps shown as supports,
contradicts precision on non-meaning assumptions (rule 1b), 95% intervals and the second answer
scored alone, all reported and none gated.

## Wave 3: which model the alpha ships with (expert confirms)
Under rules 0.2.0 the expert accepts the key evidence of every SUPPORTED claim and the AI
reviewer decides nothing (the product leaves it off unless `baker audit --ai-review`). So the
model is chosen on how well its stance labels put the right evidence in front of the expert,
not on reviewer precision. `run_probe --stance-only` prints an "Expert confirms" table:

| criterion | bar | why |
|---|---|---|
| supports recall (quote verified) | >= 90% | a missed or misquoted support never reaches the expert |
| contradicts precision | >= 90% | a "contradicts" on an observed record makes the claim contradicted with no expert step (rule 1b) |
| contradicts shown as supports | 0 | the expert would see contradicting evidence offered as support |
| valid output | 100% | |

The table also reports `moved_traps_shown_as_supports`: items of the trap families stance guide
v0.3 moved from contradicts to complicates (time, sender and speaker mismatches and later
corrections; Arsh signed it on 2026-10-14) shown as supports. It decides the own-model go bar
(`eval/stancedata/GO_BAR.md`), not the rule below.

Decision rule, fixed before the 8B and 14B were re-run (2026-10-08): ship the fastest model
that meets all four on the signed, undisputed items; among those, the higher supports recall.
If none meets them, ship the one with the fewest contradictions shown as support, then the
higher supports recall, and say plainly which bar it misses. Supports precision is expert
load (items to dismiss), reported, not gated.

Result (2026-10-09, Arsh's MacBook Air M4, 24 GB, llama-cpp-python 0.3.36, n_ctx 8192):
neither model meets all four bars, so the rule picks the fewest contradictions shown as
support: **Qwen3-14B Q4_K_M**. It misses one bar (5 contradicting items shown as support,
bar 0). The 8B misses two (8 shown as support, and 99% valid output).

| | Qwen3-14B Q4_K_M | Qwen3-8B Q4_K_M |
|---|---|---|
| supports recall / contradicts precision | 100% / 100% | 100% / 100% |
| contradicts shown as supports (bar 0) | 5 | 8 |
| valid output (bar 100%) | 100% | 99% |
| contradicts recall | 50% | 31% |
| supports shown to the expert (precision) | 49 (55%) | 55 (49%) |
| seconds per stance call, case01 audit | 43.0 | 27.6 |
| labels dropped in the timed audit | 1 of 75 | 47 of 121 |
| full case01 (613 stance calls), projected | about 7.3 h | about 4.7 h |
| claim proposal recall (target 90%) | 90% | 75% |

The 14B was timed before the speed test's call count was fixed (75 calls on C02, C05 and C12
instead of 121); its seconds per call carry over. Hardware floor: a 24 GB Apple silicon Mac,
the only machine measured end to end. A full case runs in the background or overnight.
Windows/NVIDIA speed is still unmeasured.

Speed: `time_case` audits case01 on each model (cold run, then the rerun an expert triggers
after accepting evidence, which reuses stored outputs and costs no model calls), counts model
calls per claim, projects a full-case time from the measured seconds per call, and reports
how much gold key evidence was surfaced next to how much retrieval reached at all.
`time_case --dry-run` counts the calls with no model. `claim_recall` scores
`baker claims propose` against the 20 case01 gold claims (target 90%, not gating).

One command runs all three on a Mac and prints a file to paste back:

    bash eval/probe/mac_wave3.sh

On 16 GB it uses n_ctx 4096 and three claims (C02, C05, C12), projected to the whole case; on
more memory it runs the whole case at n_ctx 8192. `CLAIMS=`, `NCTX=`, `MODELS=` and
`PROBE_SET=` override; the probe set defaults to the signed `eval/gold/probe/probe.jsonl`.

## Faster calls, round 2 (Wave 4)
Same 14B, cheaper calls. `core/llm/runtime.py` has three runtimes and two chat templates:

| setting | what it does | can it change output? |
|---|---|---|
| `plain` | how every signed result so far was measured | |
| `flash` | flash attention, and 1,024 prompt tokens read per step instead of 512 | only through floating-point order (a near-tie can flip) |
| `flash-lookup` | `flash` plus prompt-lookup decoding: guesses the next tokens by copying from the prompt and keeps a guess only where the model's greedy choice agrees | as `flash`; costs about 5 GB more memory at n_ctx 8192 (llama-cpp-python keeps every token's logits) |
| `no-think` template | the model file's own template with Qwen3's `enable_thinking=False`, which adds an empty thinking block | yes: the model reads something different, so it is re-scored |

The plain runtime records the same params as before; any other setting is recorded, so it
never reuses outputs stored under another setting. The product runs on `flash`
(`PRODUCT_RUNTIME`), picked by the Mac run below, so outputs stored before it are not reused
once (a case's first rerun after the upgrade calls the model again).

One sitting on the Mac, about 6 hours for the 14B (start it in the evening), runs the stance
probe on the signed set and times C02, C05 and C12, then prints
`eval/out/speed_round2/RESULTS.md`:

    source .venv/bin/activate
    bash eval/probe/mac_speed_round2.sh

| step | stance prompt | runtime | template | runs |
|---|---|---|---|---|
| A | v1.0 (signed) | plain | gguf | probe + timed audit (before) |
| B | v1.0 | flash | gguf | probe |
| C | v1.0 | flash-lookup | gguf | probe |
| D | v1.1 draft | chosen by rule 1 | gguf | probe + timed audit (after) |
| E | v1.1 draft | chosen by rule 1 | no-think | probe |

A preflight loads each setting once and labels two items, so a setting that crashes stops the
run in minutes. A stopped run resumes: run the same command again.

Rules, fixed before the run (2026-10-12). "Holds the bars" against a baseline means: every
Expert-confirms bar the baseline meets is met, and on a bar the baseline misses (the 14B shows
5 contradicting items as support) it is no worse.
1. Runtime: the fastest of `flash` and `flash-lookup` that holds the bars against `plain` on
   v1.0, is at least 5% faster per stance call and uses at most 2 GB more peak memory;
   otherwise `plain`. Identical output is reported, not required.
2. Stance prompt v1.1 is ready to sign when it holds the bars against v1.0 on the chosen runtime.
3. The no-think template is recommended only when it holds the bars against step D and shows
   fewer contradicting items as support. Arsh decides it together with v1.1.
4. The stance output cap stays at 1,024 tokens. A valid answer may quote up to 2,000
   characters (`core/audit/stance.py`), so a lower cap would drop such a label; the run counts
   answers that reached the cap and what they cost. `MAX_RATIONALE_CHARS` is not lowered
   either: the decoder does not enforce it, so a lower limit would drop labels without
   saving time.

Result (2026-10-12, Arsh's MacBook Air M4, 24 GB, llama-cpp-python 0.3.36, Qwen3-14B Q4_K_M,
n_ctx 8192):

| step | probe s/call | audit s/call | full case01 (498 calls) | peak memory | Expert-confirms bars |
|---|---|---|---|---|---|
| A v1.0, plain | 28.3 | 56.0 | 7.75 h | 10.1 GB | 3 of 4 (5 contradicting shown as support) |
| B v1.0, flash | 22.5 | not timed | about 6.2 h (estimate) | 10.1 GB | same as A, identical output 88/88 |
| C v1.0, flash-lookup | 28.5 | not timed | | 11.0 GB | same as A, identical labels |
| D v1.1, flash | 15.1 | 42.2 | 5.83 h | 10.2 GB | contradicts precision 77% (bar 90%) |
| E v1.1, flash, no-think | 19.1 | not timed | | 10.1 GB | as D |

Decisions by the rules: runtime `flash` (rule 1). Stance prompt v1.1 is **not** signed: it
misses contradicts precision, which v1.0 meets, so it would make more claims contradicted on
a wrong model label (rule 2). No-think is not adopted (rule 3). The cap stays at 1,024; the
longest answer was 259 tokens (rule 4). The 6.2 h for flash with v1.0 is an estimate (A's
audit time scaled by B's probe speed-up), not a measured run.

## Repeat check: same question, same answer? (2026-10-20)

`bash eval/probe/mac_repeat.sh` (or `python -m eval.probe.repeat_check --models ...`) asks the
local stance model the same things again and compares the answers byte for byte and by label
(stance and quote): A, the signed probe set twice with the model loaded once; B, once more in a
fresh process; C, the first 20 items with no GPU offload; D, two case01 audits on six claims,
each on a fresh database. `--model NAME` checks any models-file entry. `--dry-run` prints the
calls per stage and a time estimate (about 3.7 hours on the 14B; unverified). A failed
generation or an answer that is not a stance object counts as failed, never as a match, and the
script exits nonzero if any stage fails. The summary records the model file's digest as the run
computed it and marks a commit with uncommitted changes.

What is known before it runs: on the 2026-10-19 Mac run (llama-cpp-python 0.3.36, flash runtime,
model loaded once, stance prompt v1.2), 104 of 105 repeated probe answers were identical; on
P104 the rationale's wording changed while the stance and quote held. Prompt v1.1 (the 14B's own)
has not been asked twice. Nothing may say local labels regenerate exactly until this passes.
