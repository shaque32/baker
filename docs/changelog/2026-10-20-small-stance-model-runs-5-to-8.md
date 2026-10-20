## 2026-10-20: Small stance model, runs 5 to 8: no-go on the probe set, parked (#50)
- Changed: four more training runs of the eval-only small stance model (mDeBERTa-v3-base,
  `eval/stancemodel/`), each on new synthetic training data: run 5 from scratch (train sha256
  `00ceae8f…`), then runs 6, 7 and 8, each 1 more epoch on more varied sender and time traps
  (`6637a9ef…`, `3e40b3b3…`, `226374eb…`). `eval/stancemodel/tune.py` now also requires 0 moved
  traps shown as supports, the bar guide v0.3 added to GO_BAR.md; the rule predated it. The
  change only rejects more policies. Run 8 was the last cheap try agreed with Arsh, and the small
  model is now parked. These entries were in the archive on this branch before the per-PR rule;
  they move here as one entry.
- Where: PR #50 (branch `claude/train-small-model-i04typ`), not merged. Weights are not in git.
- Verified: overlap check, 0 flags on every training file. Dev split (913 undisputed items,
  cloud CPU, 2026-10-15 to 16), default policy: moved traps shown as supports fell from 17 (run 5)
  to 9, 4 and 1; supports recall 0.94 to 0.97, contradicts precision 0.97 to 0.99, 1 contradicts
  shown as supports in each run. Run 8 at its tuned policy (supports p >= 0.98) met tune.py's
  pre-set margin (recall 0.96, precision 0.99, 0 and 0), so it was the first candidate (model
  sha256 `6f3eb176…`). The signed probe set, scored once (95 gated items, 2026-10-16): valid
  output 100%, supports recall 0.82 and contradicts precision 0.67 (bars 0.90), 0 contradicts and
  7 moved traps shown as supports (6 told-frame, 1 time). Go bar condition 2 fails, so it is a
  no-go. The test split and case02 were not scored, and TEST_LOG.md is empty.
- Open: dev overstates the model because it comes from the same generators as the training data.
  Training data has no told-frame items. A filter-only use (skip records the model is sure are
  irrelevant, the 14B labels the rest) was checked on 2026-10-20 and fails: on case01's 498 real
  stance pairs, at a cut fixed in advance, run 8 skips 36% (not the 60% needed), and 7 of the 12
  relevant records it skips are signed key evidence. Speed on the Mac is unmeasured.
- Affects: none in the product (eval only; the 14B stays the local stance model).
- Status doc: pending: section 3, mDeBERTa row, Status cell becomes "branch #50 (draft), parked:
  no-go on the go bar. Run 8 (2026-10-16, cloud CPU, model `6f3eb176…`) cleared the dev bars
  with the pre-set margin, then failed the signed probe set, scored once: supports recall 0.82
  and contradicts precision 0.67 (bars 0.90), 7 moved traps shown as supports, 0 contradicts
  shown as supports. Test split and case02 not scored; speed on the Mac unmeasured".
