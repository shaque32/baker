## 2026-11-03: case05 testability go/no-go: NO-GO on conversion, every other bar passed
- Changed: no code change. This records the result of record for the testability step's
  go/no-go on case05, the held-out set built blind after case04's NO-GO (#188, signed in #189).
  Arsh ran it on his Mac with the local model, the signed prompt, cap 2, the rubber-stamp expert
  and a repeat, on main c41882d (core and eval code as in 41d9c1e, after #189, #190 and #192).
  Decision: **NO-GO**. Conversion was 5 of 33 sheet-testable claims the filler left untested
  (15%, Wilson 95% 7% to 31%), against the 40% bar. Every other bar passed:
  - 0 tries named a different person, phone or window than the signed sheet;
  - 0 false supported on the 5 claims the agent changed (2 in the whole run, for information);
  - 0 invalid outputs of 62 calls;
  - the repeat was byte-identical (110 calls compared);
  - 1.88 calls and 71.2 s per claim.
  case05 is now spent as held-out data and is not re-run. The testability step stays off.
- Where: branch `claude/project-thread-6i2msb-case05-result`
- Verified: Arsh's run on a MacBook Air M4, 24 GB, macOS 15.6.1 arm64, from 2026-11-02 20:38Z
  until the go/no-go was written at 2026-11-03 08:46Z. It used filler code version 3, rules
  0.4.0, and qwen3-14b-q4_k_m (SHA-256 500a8806e85e) for assumptions, stance and testability,
  seed 1234. The record is the uploaded log and zip (`go_no_go.json`), read in the cloud
  container on 2026-11-03 with no new model run.
- Open: why conversion failed, from the step's refusals, by the first try's blocking reason.
  - 11 of the 28 claims that did not convert were stopped by names code cannot resolve:
    - 8 claims name phones or a number by the affidavit's designations (the SAMSUNG, the
      iPHONE, the ONEPLUS, the BURNER), and only people can have aliases (#181);
    - 3 claims name "COURIER" where the recorded alias is "the COURIER".
  - 7 claims failed on quoted words that are not in quotation marks in the claim.
  - 4 claims failed on a wrong channel or direction.
  - 6 failed on accounts, windows, a template rule or a sheet mismatch.
  A claim can have more than one blocker, so how many would convert after a fix is not
  measured.
  Under the rubber-stamp expert, 3 of the 5 converted claims (C22, C25, C33) ended contradicted
  against the key. In each, the agent's assumption matched the sheet, and the verdict came from
  stance "contradicts" labels on other messages that the rubber-stamp expert accepts unread.
  Bar 3 counts only false supported, so this is not a bar. Other hardware is not measured.
- Affects: performance (the testability step's measured readiness for pilots). No capability,
  privacy, network, model or verdict change; nothing is claimed to customers.
- Status doc: pending: section 8 item 2 ("Audit"), in the testability go/no-go line that
  2026-10-29-testability-go-no-go-evaluator.md adds, replace "none has been run yet" with "two
  have been run with the local model on the M4 Air, both NO-GO, so the step stays off: case04
  (2026-10-30; conversion 2 of 34, and 4 tries named another person, phone or window) and
  case05 (2026-11-03; conversion 5 of 33, 15%, every other bar passed)".
