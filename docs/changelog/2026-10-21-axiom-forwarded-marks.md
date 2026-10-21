## 2026-10-21: AXIOM marks forwarded and quoted messages and imports quoted originals (pilot gate 4)
- Changed: the AXIOM importer (`core/ingest/axiom.py`, XML and Excel) now marks forwarded and
  quoted messages the way the UFDR importer does after #103, through the same
  `core/ingest/forwarded.py` reasons and signed columns. A hit whose forwarded flag field
  (`Forwarded` or `Is Forwarded`) is set is marked `forwarded = 1` and listed under `forwarded`
  in `forwarded_records`, with `forwarded_from_raw` taken as written from `Forwarded From`,
  `Original Sender` or `Original Author` only (a quoted sender wrote the quote, not the forwarded text). `No`,
  `False`, `0`, `Not forwarded` and blank mean not forwarded; any other value fails closed and
  marks it. A hit with a `Quoted Message`, `Quoted Message Body` or `Quoted Text` field is listed
  under `embedded`, and the quoted text is imported verbatim, one level deep, as its own message
  at `<locator>/Embedded[1]` in the parent's thread: no time, no stated direction, its own sender
  as written (`Quoted Message Sender`, `Quoted Message Author` or `Quoted Sender`, with
  `Quoted Message Sender Name` or `Quoted Sender Name`), marked forwarded with that sender as
  `forwarded_from_raw` when exactly one is named, and listed under `embedded_copy`. The flags and
  counters are the UFDR ones (`forwarded`, `embedded_message_imported_separately`,
  `embedded_original_imported`, `embedded_messages_imported`); table `rows_imported` counts the
  export's own hits only. All field names are assumed from public descriptions, not a real
  export, and are documented in the code and `docs/ingest/axiom.md`. Downstream nothing changed:
  the stance downgrade, the inconclusive checks, `NOT_COPY`, the sender check that never
  credits the forwarder, and the claim page and report warnings already read these marks.
  `IMPORTER_VERSION` 0.1.0 -> 0.2.0 (pinned in `tests/test_axiom.py`, and shown in the report's
  Versions table). No check version changed, since no check's behaviour did. No schema or
  contract change. Why: gate 4 needs AXIOM to read forwarded marks.
- Where: PR #116
- Verified: `tests/test_axiom.py` (XML and Excel: forwarded mark with author as written; flag
  values that mean no; unknown value fails closed; quoted copy verbatim at its own locator, no
  time, not outgoing, own sender, same thread, no extra thread, exact copy note with and without
  a sender; coverage codes and row counts; sender check PASS without the mark and INCONCLUSIVE
  with it, never naming the forwarder; a sender check on the quoted words rests on the copy, is
  inconclusive and the claim warning says it cannot support or contradict; importer 0.2.0 in the
  report). `make check` passed on 2026-10-21 (Linux). Synthetic exports only.
- Open: gate 4 stays not met: UFDR still keeps the original author and the forwarder as
  separate records linked only by locator, and a second embedded level is not imported. For
  AXIOM, nested forwards beyond one level and the original's own timestamp are out of scope and
  not imported. The AXIOM field names are unverified on a real export, and AXIOM format support
  stays unverified.
- Affects: capabilities (AXIOM reads forwarded marks and quoted text); customer-facing claims
  (gate 4 evidence). Privacy: none. Performance: none measured.
- Status doc: pending: in `docs/PRODUCT_STATUS.md` section 3 item 3, after the sentence about
  the UFDR importer importing embedded originals (#103's pending edit), replace "AXIOM does
  not." with "The AXIOM importer (0.2.0, assumed field names, unverified) marks forwarded hits
  and imports a quoted message's text, one level, the same way (branch
  claude/axiom-forwarded-marks)." In `docs/PILOT_GATES.md` gate 4 evidence, replace "Still
  open: AXIOM does not read forwarded marks, and a second embedded level is not imported." (as
  #103's pending edit leaves it) with "The AXIOM importer marks forwarded hits and imports quoted
  originals the same way, on assumed field names (branch claude/axiom-forwarded-marks). Still
  open: the original author and the forwarder are separate records linked only by locator, not
  separate fields on one record, and a second embedded level is not imported." and in its
  closing paragraph replace "Gate 4 waits on AXIOM reading forwarded marks" with "Gate 4 waits
  on the original author and forwarder as fields of one record and a second embedded level";
  gate 4 stays Not met.
