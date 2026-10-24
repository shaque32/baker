## 2026-10-20: UFDR imports the text of forwarded and quoted originals (pilot gate 4) (#103)
- Changed: the UFDR importer (`core/ingest/ufdr.py`) now imports each EmbeddedInstantMessage
  (the forwarded or quoted original carried inside a chat message or a standalone
  InstantMessage) as a `messages` row of its own in the same thread, at the parent's locator
  plus `/Embedded[n]` (1-based), so its `source_ref` leads back to the artifact. Its body is the
  embedded text exactly as written; its sender is the embedded message's own From party as
  written; no time (ts and the raw value stay empty, so the copy never sits on the timeline at the
  original's time); its direction is never taken from the
  parent or a stated field, so the shared mapper sets it (unknown, unless the embedded sender
  is the phone's owner). Every such row is marked forwarded (`forwarded = 1`,
  `forwarded_from_raw` = its own sender when it names exactly one and is not itself marked
  forwarded) and listed under a third reason, `embedded_copy`, in `forwarded_records`
  (`core/ingest/forwarded.py`; a locator containing `/Embedded[` wins over the forwarded
  mark), so it fails closed like a forward: it cannot
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
  imported separately. The copy's note is its own and true: it cites the carrying record's id, the
  sender the extraction names for the embedded message (or says it names none) and the
  carrying message's sender, and never says "shown as sent by whoever forwarded it"
  (`forwarded.record_note`, rendered by `core/report/html.record_line` on the claim page and in
  the report). The claim warning words a mix of forwards and copies correctly. The
  conversation view (`core/report/restore.context_table`) and the timeline label a copy as
  carried inside its parent. Deterministic checks (count, absence, timing, sender, handle
  resolution) leave embedded copies out of their inputs (`core/audit/checks/_common.NOT_COPY`),
  so a copy is never counted beside the message it copies or its standalone record, and a
  check's outcome on a case is the same with or without them. An embedded copy never claims a
  model id, so a later standalone record still imports. `IMPORTER_VERSION` 0.1.1 -> 0.2.0;
  report 0.9.0 adds an "Importer for <source>" row to Versions. No schema or contract change.
  Why: gate 4 requires the original text.
- Where: main (#103, merged 2026-10-20)
- Verified: `tests/test_ufdr.py` (verbatim body, own locator, forwarded mark, author as
  written, never the forwarder or the phone owner, same thread, nested level not imported,
  dedupe by model id both orders, exact notes with and without a named sender, mixed claim
  warning, conversation label, importer version in the report), `tests/checks/test_unit.py`
  (count, absence, timing and sender outcomes and wording unchanged by embedded copies),
  `tests/test_report_consistency.py` (same copy note on screen and in the report),
  `tests/test_ufdr_check.py`; `make check` passed on 2026-10-20 (eval
  numbers in the PR description). Synthetic packages only; no real UFDR checked.
- Open: gate 4 is still not met: AXIOM does not read forwarded marks or embedded originals.
  The forwarder and the original author are not separate fields on one record; the original is
  a separate record linked only by locator. A second embedded level is not imported. An
  embedded copy's words cannot support a claim even when its author is named, and checks
  never see it. The original's own time is not kept anywhere on the record. UFDR format support stays unverified.
- Affects: capabilities (UFDR imports more message text); customer-facing claims (gate 4
  evidence). Privacy: none. Performance: none measured.
- Status doc: applied 2026-10-21
