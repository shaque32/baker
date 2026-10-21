## 2026-10-21: UFDR import and ufdr-check read Reader 7.48 RelatedModels copies (#117)
- Changed: Baker Eval ran `baker ufdr-check` on three public Cellebrite Reader 7.48 UFDRs (Josh
  Hickman's images on Digital Corpora) and it reported chat messages missing partway through
  chats, plus smaller gaps in recipients, attachments and the phone's own accounts (Grok
  Product memo on #100). The cause is not a dropped message: Reader 7.48 ends many models with a
  `RelatedModels` element holding copies of other records (new ids, same content). The importer
  already skipped them, but silently; ufdr-check counted the copies as the holder's own messages,
  attachments and recipients. Every missing message on the three packages is an exact copy of a
  message Baker imported. The "missing" accounts were second UserAccounts with the same app and
  identifier, which Baker keeps as one account.
  Importer `ufdr` 0.2.0 -> 0.3.0: a RelatedModels element is never read as part of its holder;
  every copied message (also inside a copied chat), call, contact and account is counted
  (`related_copies`, info, per type in `ufdr.related_copies_by_type`) and matched by content to
  the records read; a copy that matches none is listed for review (`related_copy_unmatched`,
  attention, on screen and in the report's Limitations) and not imported. Both reads of
  report.xml must now also count the same chat messages, and every one must be imported or
  listed as skipped, or nothing is stored.
  ufdr-check 0.1.0 -> 0.2.0: copies are matched to imported messages in a row of their own
  (one matching none is a difference), counted per type, and never added to a record; a
  repeated account counts as a repeat; direction from the phone's own accounts is expected by
  identifier only, as the importer links them.
  The five model types Baker does not know on these packages (AppsUsageLog, ActivitySensorData,
  FileUpload, RecognizedDevice, Activity) were already listed for review on screen and in the
  report ("model type not recognised"); a test now covers it.
  Synthetic fixture `related_package` in `eval/synthetic/ufdr.py`: chats of 60, 45 and 5
  messages, attachments, recipients, RelatedModels copies of chats, messages, calls and
  accounts, a repeated account, and the five unknown types. No Hickman or real data in the repo.
- Where: PR #117
- Verified: new tests in `tests/test_ufdr.py` and `tests/test_ufdr_check.py`; `make check` and
  eval in the PR description. Run on the three public packages in a cloud container
  (2026-10-21), with report.xml only (attachment files left out); results kept in the project
  files, not yet signed off by Arsh. Baker Eval re-runs them before merge.
- Open: copies of types Baker does not import (locations, cookies, ...) are not counted, since
  their holders are not read. report.xml states no count per type: `ModelCount` on `project`
  did not equal the number of records, so it is not compared. A message linked to the phone's
  owner only by a name that reads like an account identifier keeps an unknown direction.
- Affects: capabilities (UFDR import coverage, ufdr-check). No verdict, privacy or network change.
- Status doc: pending: §8 item 1, after "Cellebrite UFDR (unverified on real samples)" add
  "(importer 0.3.0 counts Reader 7.48 RelatedModels copies and lists any that match no record,
  #117)".
