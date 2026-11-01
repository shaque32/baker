## 2026-11-01: Told frames, undated denials and "never told" in the stance training data (#199)
- Changed: stance labeling guide v0.4 (`eval/stancedata/LABELING_GUIDE.md`), signed by Arsh on
  2026-11-01 and copied with its pins to `eval/gold/stancedata/` and
  `tests/test_gold_stancedata.py`, adds three families with a fixed answer, 69 in all:
  `ovr_told_frame`, a complicates trap ("X told the owner that they paid Ruiz $2,000" against
  X's own "never paid ruiz" or "paid ruiz 1,500": the record does not show the report, and one
  record cannot show that no other message said it); `ovr_undated_denial`, a complicates trap
  (a denial that names no time, against the act with no time or dated after the message); and
  `con_never_told`, its contradicts control ("X never told the owner that ..." or "did not tell
  the owner on <the record's date> that ...", against a record from X that says it). Rules 12
  and 23 say so, and the review sheet prints a line on reports and undated denials. The
  training generator (`eval.train` 1.6.0; the Baker-wording part, `eval.train.baker`, is
  unchanged) writes each one beside the same record's supports and contradicts items, drawn
  apart from each scene's own siblings so the other families keep their odds within a scene; a
  told frame beside a denial always comes with the report of the denial itself (supports), so
  the two differ only in what is reported. A told frame's time fits the record without naming
  its minute. Why: the signed probe set has read told frames and undated denials as
  complicates since the 2026-10-15 relabel, and `GO_BAR.md` bars 2 and 3 already count both as
  moved traps, but the training data had none; run 8's small model (2026-10-16) showed 6 of
  the probe set's told frames as supports. Step 2 of the fine-tune in the faster-engine plan
  (Arsh, 2026-10-30). The speed rule from that plan holds: nothing here can ship a model; any
  candidate still needs 0 contradicting records and 0 moved traps shown as supports on both
  test sets.
- Where: PR #199
- Verified: on a Linux container, 2026-11-01. 98 training generator tests pass, 3 of them new,
  one per family's shape (a told frame's report frame, never the message as the subject or the
  record's minute, beside the record's denial or other value; an undated denial's record,
  earlier questions and act name no time, and a dated act falls after the record; a "never
  told" names no time or one that holds the record, in every shape a supports item's time
  takes). Held-out generator tests unchanged and passing. The 12,000 plain items of seed 1
  (`make stancedata`'s file, sha256 `284a90d7405a91df...` with its 7,250 Baker-wording items)
  hold 479 told frames, 238 undated denials and 200 "never told"; the label mix moves from
  supports 28.8%, complicates 38.6%, contradicts 23.3%, irrelevant 9.4% (eval.train 1.5.0) to
  27.5%, 41.4%, 23.5% and 7.6%. The new families take 7.6% of the plain items, so the older
  ones fall in count: summed over seeds 1 to 3 (36,000 plain items), time traps 2,471 to 2,184
  and sender traps 1,570 to 1,422, about 10% each (seed 1 alone: 824 to 735 and 496 to 490).
  The overlap check, run here without case02 (this work may not read it), with the module's own
  functions: training against the signed and draft probe sets, the smoke sets and case01, 0
  flagged; training against both held-out files, 1 chance match (training item T004763, a
  `sup_contact` window with the same frame, times and date as held-out dev D000747), to be
  dropped from the delivered file as earlier data drops were (#87). The signature pins in
  `tests/test_gold_stancedata.py` pass on the signed copy. `make check` with main at 41d9c1e
  merged: lint clean, 3,616 tests passed, 9 skipped; eval gate unchanged from main: case01
  model-free 1.00 with 0 false supported (PASS), hostile PASS.
- Open: the held-out generator does not write the three families yet: a separate author adds
  them from the signed guide alone. The full overlap check with case02 has not run on these
  files, the label review sheet is not checked, and no model was trained. Left out until Arsh
  decides: a told frame at the record's own minute, a report of a record that a later message
  corrects, and a "never told" whose time misses the record.
- Affects: none (synthetic training data only; no product code, prompt, model or verdict path)
- Status doc: no change
