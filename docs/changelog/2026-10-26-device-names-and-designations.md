## 2026-10-26: The expert names a phone as the document does; SUBJECT-1 and SUBJECT-2 are two people (#139)
- Changed: Affidavits call a phone "TARGET PHONE" or "Item 1", but the assumption filler matched
  a phone only to a device's id, source id or label, and a UFDR's label is the model name
  ("Apple D201AP"). Validation-v1 run 1 refused the phone for 33 of the 106 claims. The expert
  can now give a device the document's names: on the case screen (Devices, "Document names"),
  with `mabillon name-device --device … --name "TARGET PHONE" --by expert:<name>`, or
  `core/review/actions.name_device`. Each change is a hash-chained audit-log entry
  `device.names` (the device's whole list; empty clears it), read back by
  core/review/device_names.py. No schema change. The filler matches these names too, still one
  device only, and a name that would also reach another device is refused. Report 0.17.0 lists
  each name under Limitations as the expert's statement, with who gave it and when.
  Also: an expert could not add SUBJECT-2 once SUBJECT-1 existed, because person names were
  compared without their numbers. Name words now keep a designation's number ("subject-2"),
  so numbered people stay apart for the add-person check, the identity screen and link
  proposals. The validation run driver (eval/validation/hickman_run.py) now sets the case up
  as the affidavit defines it: the phone is named TARGET PHONE, and every other SUBJECT-<n>
  the claims text names is added as a person, with no stipulation or link.
- Where: PR #139
- Verified: tests/test_device_names.py (filler resolves "TARGET PHONE" only after the expert
  names the device; replace and clear; refusals for another device's id, source id or name,
  empty and long names, non-experts, unknown devices; the report line passes the word check).
  tests/test_review_screen.py (the screen form), tests/test_identity.py (SUBJECT-1 and
  SUBJECT-2 are two people and resolve apart), tests/test_validation_run.py (the driver's
  setup). make check passes; synthetic eval numbers unchanged.
- Open: The effect on the iOS 15 claims is not measured until validation run 2. Link
  proposals now treat "subject-1" and "subject-12" as a possible short form of each other;
  they stay proposals for the expert. Bundle verification checks the device.names entries'
  hash chain but does not replay them.
- Affects: capabilities (claims that name a phone the way the document does; numbered people)
- Status doc: pending: under the case setup capabilities, add "The expert can record the
  document's names for each phone (TARGET PHONE, Item 1); the audit matches claims that use
  them, and every report lists them as the expert's statement."
