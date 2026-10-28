## 2026-10-28: The assumption filler refuses assumptions that misstate the claim (#160)
- Changed: Replays of recorded 14B answers through main's filler, with no model, found claims
  counted as tested on assumptions that misstate them. All four cases now refuse, in
  core/audit/assumption_filler.py:
  - A sender party the claim writes only as the one a message went to ("wrote to the Discord
    user Y", "X's iMessage to N", "told Y") is refused (`only_addressed`). A failed sender
    check on the wrong person would contradict a true claim without an expert.
  - A message's quoted words (sender, record_time, meaning) must sit inside quotation marks in
    the claim. A quoted name the proposal also gives as a party is not a message.
  - Each proposal's shape is validated (`parse_params`) before `coverage_gap` and before a
    sender's parties go into a code-made time range. A sender naming two parties, which the
    builder drops, no longer counts as testing who sent the message.
  - `count_op` refuses a count of calls or "times", and a count of messages one side sent or
    received, because the count check counts messages in both directions.

  Nothing is loosened, and no frozen file changes.
- Where: PR #160
- Verified: on this container, 2026-10-28.
  - New tests in tests/test_assumption_filler.py cover each guard and the count refusals.
  - tests/test_filler_replay.py (synthetic case01, Mac-run answers): 10 → 8 tested, 12 → 10
    with the added name. Both claims removed rested on a dropped two-party sender or a
    paraphrase.
  - `make lint eval` passes (case01 model-free accuracy 1.00, false supported 0; hostile pass;
    case02 aggregate accuracy 0.90, false supported 0).
  - The model-free eval uses the signed sheet, not the filler, so it is not expected to move.
- Open: three limits.
  - A content claim that quotes a message without a verb of saying can still be tested with
    its writer unchecked. Extending the sender rule to every claim type is left for the code
    fills, where advisors measured it together.
  - `only_addressed` reads fixed English wording; a new phrasing for an addressee is not
    caught.
  - Validation run 2's recorded answers also lose tested claims under these guards. Those
    counts stay in the project's validation write-up (PREREGISTERED_v2).
- Affects: capabilities (fewer claims tested, none on a misstated assumption); no privacy or
  customer-facing claim change
- Status doc: pending: in "2. Pipeline (main)", row "5. Assumptions", append to the description:
  "A message's quoted words must sit inside quotation marks; a party the claim writes only as
  the one written to is never the sender; counts of calls, "times" or one side's messages are
  refused; coverage is judged only on proposals that fit their template (#160)".
