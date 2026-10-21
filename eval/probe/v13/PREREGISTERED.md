# Stance prompt v1.3 for the local 14B: test plan, written before any item or call (2026-10-21)

Thread "Expert confirms contradicts", PR2. Arsh chose "Start PR2" on 2026-10-21 21:58Z: add
stance guide v0.3 rules 12 and 23 to the local model's prompt, test on new held-out items, and
re-probe the 14B on his Mac. Synthetic data only. The prompt change waits for Arsh's signature.

## Why
On the signed probe set the 14B (qwen3-14b-q4_k_m, sha256 500a8806...) with its own prompt,
stance v1.1, called 8 gated items "contradicts" whose gold is "complicates": P049 (an undated
denial) and P066 to P069, P092 to P094 (told frames). Contradicts precision 11 of 19 (58%), bar
90%. The cloud prompt's v1.2 sentence for rules 12 and 23 fixed Opus but none of the 8 for the
14B, and added 3 new wrong contradicts (P039, P073, P076; Mac run 2026-10-19 at eee8d15). Rules
0.3.0 (#98) already keeps a model's "contradicts" from deciding a verdict without an expert, so
this change is about the expert's queue, not the verdict path.

## The two candidates (written once, before any item below existed; not edited after answers)
- v1.3a, `eval/probe/stance_v1_3a_draft.md`: v1.1 plus a "Before you answer contradicts, make
  two checks" block (told, wrote or asked; an undated denial), placed before the "If you are
  unsure" line, where the 14B reads it as its own step rather than one more clause of the
  contradicts definition, which is where v1.2 put it.
- v1.3b, `eval/probe/stance_v1_3b_draft.md`: v1.3a plus four invented worked examples, two
  "complicates" and two "contradicts", so the checks do not teach "never contradicts".
v1.1's own text is unchanged in both (tests/test_probe_v13.py).

## Item sets (first answer scored, layout product_members, stance only, the product's quote check)
1. Signed probe set, `eval/gold/probe/probe.jsonl` (105 rows, 95 gated, 11 gold contradicts).
2. Fresh set, `eval/probe/v13/heldout.jsonl`, written for this test by a separate agent from the
   guide alone, without seeing either candidate: about 32 items in the probe's format, some
   Russian. A: told-frame replies saying the opposite (complicates). B: undated denials against
   an undated or later-dated assumption (complicates). C: controls that must stay contradicts
   (dated denials, exclusive told frames, no-contact or first-contact, other value, a correction
   naming the replacement value). D: controls that must stay supports. Three blind readers
   label every item from the guide alone; an item where a majority picks another stance is
   reported and left out of the criteria.
3. `eval/probe/v13/told_frame_24.jsonl`: the 24 items of 2026-10-15 ("new-24", sha256
   db1adc75...), T022 and T023 left out as then. The 14B has never answered them.
4. `eval/probe/v13/rules_12_23_26.jsonl`: the 26 items of 2026-10-15 ("new-26", P106 to P131,
   sha256 d7daa9ea...). The 14B has never answered them.
While writing the candidates, sets 2 to 4 had not been read (set 2 did not exist); of the
signed set, P039, P049, P066 to P069, P073, P076, P092 to P094, P098 and P101 had been read.

## Runs (Arsh's Mac, `bash eval/probe/mac_v13.sh`, one answer per item)
1. v1.1 on sets 2 to 4 (the baseline). On set 1 the baseline is the 2026-10-19 run, reused only
   if the model's SHA-256 matches and every v1.1 prompt renders byte for byte as logged (the
   script checks both; otherwise it runs v1.1 on set 1 too).
2. v1.3a on sets 1 to 4.
3. v1.3b on sets 1 to 4, only if v1.3a fails the criteria below.

## A candidate is recommended for Arsh's signature only if all hold (first answers)
1. Signed set: every Expert-confirms bar (valid output 100%, supports recall >= 90%,
   contradicts precision >= 90%, 0 gold contradicts shown as supports); contradicts recall at
   least 10 of 11; gold complicates or irrelevant items shown as supports no more than v1.1's 23.
2. Fresh set: at most 1 wrong contradicts on the A and B items; contradicts recall on C at least
   v1.1's and at least 80%; supports recall on D at least v1.1's.
3. Sets 3 and 4, each: at most 1 wrong contradicts on its told-frame and undated-denial items;
   contradicts and supports recall on its controls at least v1.1's on the same items.
If v1.3a passes it is recommended (shorter, faster); otherwise v1.3b if it passes. If neither
passes, no prompt change is proposed and every number goes to Arsh as it is.

Reported beside the criteria, never changing them: every item's answer under each prompt, the
model SHA-256, 95% Wilson intervals, mean seconds per call and prompt length, and wrong
contradicts on non-meaning assumptions. A pass here does not add any claim type to
`_AUTO_CONTRADICT` (core/audit/rules.py); that needs its own signed entry.

## Commitments
No label, criterion or candidate edit after seeing any answer. All numbers published, including
any that get worse. $0 API spend: everything runs on the Mac's local model.
