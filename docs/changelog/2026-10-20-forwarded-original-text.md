## 2026-10-20: UFDR imports the text of forwarded and quoted originals (pilot gate 4)
- Changed: the UFDR importer (`core/ingest/ufdr.py`) now imports each EmbeddedInstantMessage
  (the forwarded or quoted original carried inside a chat message or a standalone
  InstantMessage) as a `messages` row of its own in the same thread, at the parent's locator
  plus `/Embedded[n]` (1-based), so its `source_ref` leads back to the artifact. Its body is the
  embedded text exactly as written; its sender is the embedded message's own From party as
  written; its time only the embedded model's own; its direction is never taken from the
  parent or a stated field, so the shared mapper sets it (unknown, unless the embedded sender
  is the phone's owner). Every such row is marked forwarded (`forwarded = 1`,
  `forwarded_from_raw` = its own sender when it names exactly one and is not itself marked
  forwarded) and listed under `forwarded` in `forwarded_records`, so it fails closed: it cannot
  support or contradict a claim. An embedded message whose model id an earlier record already
  had is not imported twice; an embedded copy never claims a model id, so a standalone record
  that comes later still imports normally (the words then appear twice, the embedded copy
  marked forwarded). One level only: a message nested inside an embedded one is still
  not imported and is flagged `embedded_message_not_imported`. The parent keeps the `embedded`
  reason, now flagged `embedded_message_imported_separately`; the new flag
  `embedded_original_imported` and the info counters `embedded_messages_imported` and
  `embedded_messages_already_imported` (`core/ingest/coverage.py`) count embedded rows apart
  from the extraction's own records, so table totals still match the vendor's message count.
  `baker ufdr-check` (`core/ingest/ufdr_check.py`) leaves embedded rows out of its record
  comparison. `RECORD_NOTE["embedded"]` (`core/ingest/forwarded.py`) says the original is
  imported separately. No schema or contract change. Why: gate 4 requires the original text.
- Where: branch `claude/forwarded-original-text`, not merged.
- Verified: `tests/test_ufdr.py` (verbatim body, own locator, forwarded mark, author as
  written, never the forwarder or the phone owner, same thread, nested level not imported,
  dedupe by model id), `tests/test_ufdr_check.py`; `make check` passed on 2026-10-20 (eval
  numbers in the PR description). Synthetic packages only; no real UFDR checked.
- Open: gate 4 is still not met: AXIOM does not read forwarded marks or embedded originals.
  The forwarder and the original author are not separate fields on one record; the original is
  a separate record linked only by locator. A second embedded level is not imported. The
  sender check and the fail-closed path treat the embedded row as forwarded, so its words
  cannot support a claim even when its author is named. UFDR format support stays unverified.
- Affects: capabilities (UFDR imports more message text); customer-facing claims (gate 4
  evidence). Privacy: none. Performance: none measured.
- Status doc: pending: in `docs/PRODUCT_STATUS.md` section 3 item 3, replace "the sender field
  still shows the forwarder, and originals' text is not imported." with "the sender field
  still shows the forwarder. The UFDR importer imports each embedded forwarded or quoted
  original (one level) as its own record at `<locator>/Embedded[n]`, marked forwarded with its
  own sender as written, so it fails closed too (branch `claude/forwarded-original-text`);
  AXIOM does not." In `docs/PILOT_GATES.md` gate 4, replace "Still open: the original text is
  not imported, and AXIOM does not read forwarded marks." with "The UFDR importer now imports
  the text of each embedded original (one level) as its own forwarded record at
  `<locator>/Embedded[n]` (branch `claude/forwarded-original-text`). Still open: AXIOM does not
  read forwarded marks, and a second embedded level is not imported." and in its closing
  paragraph replace "Gate 4 waits on importing the original text and on AXIOM reading
  forwarded marks" with "Gate 4 waits on AXIOM reading forwarded marks"; gate 4 stays Not met.
