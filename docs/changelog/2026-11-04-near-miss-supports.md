## 2026-11-04: Only the quoted message can support a one-message assumption
- Changed: A model's "supports" label on a record that is not the message an assumption
  quotes ("The message X was sent by Y", "... was sent on Z") is no longer stored as support.
  Code compares the record's words with the quote as the checks do (curly quotes and runs of
  spaces fold). A record whose words come close to the quote without being it (difflib ratio
  0.7 or more over a run of as many words, give or take one) is stored as "complicates", so
  the expert sees the near miss and it blocks Supported until dismissed. Any other record is
  stored as "irrelevant". Each rewrite puts a note before the model's rationale, and the model
  call log keeps the raw label. This mirrors the existing rule that only the quoted message
  can contradict such an assumption. Runs record `subject_stance: "2"` in their config; the
  bundle check accepts both rewrites. Why: on a validation run on a public test phone, the
  local stance model labelled near misses as support ("Dominant" for a quoted "Dominion",
  "trashed" for "deleted"), so a false claim showed the expert support alone.
- Where: branch claude/project-thread-ds0ify (Arsh chose "near-miss complicates, rest
  irrelevant" in the validation thread on 2026-11-04)
- Verified: New tests in `tests/test_stance.py` (five records: folded exact match, two near
  misses, two unrelated), `tests/test_bundle.py` (the bundle check accepts both rewrites and
  refuses others) and `tests/test_withheld_rationale.py` (the notes hold no forbidden word);
  they fail without the change. Three tests updated for the new stored stances
  (`test_bundle.py` scoped bundle, `test_cloud.py` relabel, `test_probe_replay.py`). Replaying
  the rewrite on the public-phone run's stored labels: 62 supports became irrelevant and 7
  became complicates; the scorer's false-claim-shown-only-as-support count fell from 4 to 2
  (development data, designed after seeing that run; not a quotable number). make check (see the PR). Eval: case01
  reviewed 1.00 with 0 false supported, hostile PASS, case02 aggregate 0.90 with 0 false
  supported, all as main. One eval number got worse: case01 key evidence surfaced to the expert
  fell from 72% to 70% (one record of 71, C16's "its ilya btw" message). The model-free eval
  labels every record "supports", and that record is not the quoted message, so it is now
  irrelevant on the sender and time assumptions. A real model would label it complicates or
  contradicts there, which this change keeps.
- Open: A meaning assumption's support is not rewritten (a record that is not the quoted
  message may still be read as supporting its meaning). A call's direction is still not
  tested by any assumption. The 0.7 ratio is set from a handful of examples.
- Affects: capabilities (what evidence counts as support for an expert to accept)
- Status doc: pending: in section 2, Pipeline, row "8. Stance", add to the job column: "Code
  stores a label on a record that is not the quoted message of a one-message assumption as
  complicates (a near miss) or irrelevant, never supports or contradicts."
