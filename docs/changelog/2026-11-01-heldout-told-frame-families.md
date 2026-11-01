## 2026-11-01: Told frames, undated denials and "never told" in the held-out stance set (#202)
- Changed: the held-out generator (`eval.heldout` 1.4.0) writes the three families signed stance
  labeling guide v0.4 added, from the signed guide alone (rules 12 and 23, the three family
  rows, the list of changes from v0.3), in new writers (`eval/heldout/writers_c.py`) over the
  held-out set's own record tables: `ovr_told_frame` (complicates trap: "X told the owner that
  ..." in the supports frames, with no time or the record's local date, against X's own denial
  or other value; 40 test, 20 dev), `ovr_undated_denial` (complicates trap: a past-tense denial
  whose record, question and act name no time, against the act with no time or dated after the
  message; 30 and 15) and `con_never_told` (contradicts: "never told", "at no point", or "did
  not tell" on the record's date, in its month or in a span around it, against a plain
  statement from X; the quote is the whole message; 40 and 20). The test split goes from 1,846
  to 1,956 items (1,260 plain, 696 in Baker's wording) and the dev split from 923 to 978; gold
  contradicts in the test split go from 522 to 562. The three cases the guide keeps out stay
  out. Two smaller changes came with the version bump: the Baker-wording items now key their
  random streams to their place in their own block (`bk_generate.STREAM_BASE`), so the new
  plain families move their ids but not their content (byte-identical to 1.3.0 apart from ids,
  pinned by a test), and `ovr_question` no longer gives the asker a "cant talk now, in a
  meeting" line beside their own question, a rule the regenerated chats had started to break.
  Why: the go bar already counts told frames and undated denials as moved traps (`GO_BAR.md`
  bars 2 and 3), and a fine-tuned model must be scored on held-out ones written apart from the
  training side (#199).
- Where: PR #202 (built on #199; merge after #199)
- Verified: on a Linux container, 2026-11-01. 80 held-out generator tests pass: the existing ones
  with the new counts and plain-file pins, plus 5 new (records drawn from denials, values and
  statements, never a corrected one; told frames in the supports frames, never "the message"
  or a clock time, any date the record's own; undated denials and their questions name no
  time, any date falls after the message; "never told" times hold the record, the sender is
  the record's, the report adds nothing the record lacks; Baker-wording content unchanged).
  New files: test sha256 `7d806fbc7ea0ea64...`, dev `96872f15b2911bd2...`. Overlap check with
  `eval.stancedata.contamination`'s own functions, without case02 (this work may not read it):
  held-out against the signed and draft probe sets, the smoke and v13 sets and case01, 0
  flagged; held-out against seed 1 of #199's training generator (sha256 `284a90d7405a91df`),
  1 flagged, the chance match #199 already recorded (training T004763 against an unchanged
  Baker-wording item, now id D000802 instead of D000747), so nothing new. `make check` on
  #199's branch (0dd2876) with this change: lint clean, 3,620 tests passed, 9 skipped (the
  changelog test then failed only on this entry's placeholder `Where:` line, fixed and
  re-run: 21 passed); eval gate unchanged: case01 model-free 1.00 with 0 false supported
  (PASS), hostile PASS, case02 aggregate 0.90 with 0 false supported.
- Open: the full overlap check with case02 has not run on the new files; Arsh's 100-item
  held-out sample is still unchecked, so held-out scores stay provisional. Every plain
  held-out item changed with the version bump (ids, chats and records), so earlier dev-split
  scores do not carry over; the test split had no logged scoring (`TEST_LOG.md` is empty), so
  no candidate is affected. No model trained or scored, no Mac run.
- Affects: none (synthetic test data only; no product code, prompt, model or verdict path)
- Status doc: no change
