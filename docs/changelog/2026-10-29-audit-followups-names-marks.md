## 2026-10-29: Claim page marks follow the rules; same-name ids; count words only in the filler's wording (#174)
- Changed: follow-ups from the #167 stand-in audit. A failed check marks its assumption
  "Contradicted by the records", and the claim page says the rules contradict the claim, only
  when the verdict cites that check, so the screen follows what the rules decided under rules
  0.4.0 (#166); an assumption whose failed check an agent proposed and no expert has confirmed
  yet says "A check failed: waiting for you to confirm". Two people or phones the case names
  alike keep their ids beside the name, on the screen and in the report. Only the filler's own
  count wording ("holds eq 13") becomes words, so quoted text stays verbatim. Report 0.27.0
  (after #166's 0.26.0). Display only: no verdict, rule, stored text or log changed.
- Where: PR #174
- Verified: make check (lint; 3334 passed, 9 skipped; case01 model-free PASS accuracy 1.00,
  false-supported 0; hostile PASS; case02 aggregate 0.90, false-supported 0); the demo's five
  claims decided on a failed check (C04, C08, C10, C11, C14) still show the mark and sentence.
- Open: the report's assumption table does not yet say "Contradicted by the records" beside a
  failed check the verdict cites (the check row says fail); wording parity left for a report
  pass.
- Affects: none
- Status doc: no change

