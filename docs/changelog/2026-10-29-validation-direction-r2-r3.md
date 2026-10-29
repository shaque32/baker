## 2026-10-29: Message counts can say which side sent them, or that messages went each way (validation rulings R2, R3)
- Changed: two new assumption fields, signed by Arsh on 2026-10-29 in the validation thread
  (the core/contracts.py diff in PROPOSED_CHANGES.md, applied word for word).
  - R2, `sent_by`: "SUBJECT-2 sent SUBJECT-1 exactly three Signal messages" is a count of the
    messages one side sent. The count check (1.2.0) counts only rows whose recorded sender is
    that side's account. Before, any one-way count was refused (#160). The filler sets it only
    for the plain form "<sender> sent <count> ..." with the other side written after "sent":
    the sender is one person, by name or as the exact owner of a phone the claim writes, or
    the accounts by identifier. "Received", the passive ("were sent by"), a second one-way word,
    or a sender written on both sides stay refused.
  - R3, `each_way`: "exchanged ... messages" passes only when each side sent at least one
    counted message in the window. With no stated number it is "at least two"; a stated number
    is still compared. One side's silence never fails the claim: the check says "Not finding a
    message each way does not mean one was never sent" and stays inconclusive. A message with
    no recorded sender is never counted between two parties, as before.
  - A count of calls takes neither field: a call log's direction is not read here, so the
    template refuses them with 'call' among the channels.
  - When the model names no phone for a message count and the claim writes exactly one, that
    phone is the one counted.
  - The assumption text says "counting only messages X sent" or "with at least one message
    each way", and ends "Filled from the claim's wording." when code set the field.
  Why: run 3 of the Hickman iOS 15 validation needs as many code-checked claims as the data
  allows; one-way and "exchanged" counts were refused only for want of a field.
- Where: branch claude/project-thread-ds0ify (the R2/R3 PR)
- Verified: on this container, 2026-10-29. New tests in tests/checks/test_unit.py (one side's
  count passes and fails, each way passes and never fails on silence, refused directions, the
  contract validators) and tests/test_assumption_filler.py (synthetic case01: one side's count,
  "exchanged" with and without a number, the written phone, and the refused wordings); the
  tests that exercise new behaviour fail without it. Replaying run 2's recorded model answers
  through this code on run 2's case database (development data, project files only): 34
  code-checked, 15 check unsettled, 3 expert only (52 tested), up from 33, 14 and 3 at #169;
  11 with a failed core check, unchanged. `make check`: see the PR.
- Open: the version bump (CONTRACTS_VERSION 0.5.0, schema.sql header) was not in the signed
  diff and is proposed in PROPOSED_CHANGES.md. Every assumption id changes once, since the id
  hashes params with their defaults: a case re-run under this code gets new ids and an expert
  decision on an old id does not carry over (no pilot case exists yet). TEMPLATES_VERSION stays
  1.0.0 (the gold pins it; existing assumptions render as before). Claims writing "iMessage"
  still need fill e to be read as Native Messages. Rules 0.3.0 are unchanged, so a failed
  one-way count contradicts without an expert, as any failed check does.
- Affects: capabilities (one-way and "exchanged" message counts; count check 1.2.0); no privacy
  change; no customer-facing claim change
- Status doc: pending: in the count check's capabilities, add "counts one side's messages
  ('X sent Y three messages') and 'exchanged' messages (at least one each way, never failed on
  one side's silence)"
