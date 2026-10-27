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
  (`related_copies`, info, per type in `ufdr.related_copies_by_type`) and matched to the record
  holding it; a copy that does not match is listed for review (`related_copy_unmatched`,
  attention, on screen and in the report's Limitations) and not imported. Both reads of
  report.xml must now also count the same chat messages, and every one must be imported or
  listed as skipped, or nothing is stored.
  Matching follows what the public packages show: each copy is its holder decoded again from
  another source (Android 12: all 1,144 in-message copies equal their holder message but 21 that
  spell a recipient differently; the 674 messages of copied chats fit the holder chat's messages
  one to one). So a copied message must say what its holder says (text, time, sender,
  recipients, deleted state, attachment count and names; paths and file ids are each source's
  own reference, so not compared), and a copied chat's messages are
  matched one to one to the holder chat's, so a lone copy never hides behind a same-second twin
  (Baker Eval on #117). After Codex's review on #117: a call copy matches only with each party
  on the same side; a deleted state counts in every form the importer reads (attribute or
  field); copies are matched at any depth (copies inside copies, chats copied inside a copied
  chat); a copied chat's messages are reduced to their content key as each closes, so a long
  copied chat is never held whole; ufdr-check compares every sender and flags a copy Baker
  lists that matches there (`extra`), as well as one it fails to list. Later Codex rounds found
  fields the mappers read but the match left out, so the match now covers every field each
  mapper reads, as written: a message's app, Direction, Folder and Status, each party's
  IsPhoneOwner and parties with no sender or recipient role; a call's app, Type and Status; an
  account's name; then the order of an SMS's counterparts and of each side of a call, and a
  message's embedded messages and model type. Copies held by a message embedded in a copy are
  matched too (in an SMS or MMS as in a chat message), and a copied chat counts messages
  across fields of one name. A copy held by a message inside a copy is a message whatever its
  type is named, as at the top level. A copy recovered by carving, or with a decoding
  confidence other than High, where its holder is not (or the reverse), is listed. A message's
  embedded messages are read across all its embedded fields, in the order written, so none is
  dropped when a message has two. Copies are matched as each record is mapped and then
  dropped, so memory never grows with the number of copies in the package. A contact copy's
  deleted state must match too, and a message or call held by a copied chat is listed, as one
  held by a chat is, and so are the messages of a chat copied inside a copy of another kind.
  An unnamed attachment is compared by name as written, never by its file: on the public
  Android packages a copy's unnamed attachment names only its own file id while its holder
  names the extracted path, so comparing the file would list about 20 genuine copies per package.
  An attachment's MIME type as written is compared with its name.
  Every Labels field and every MessageExtraData field of a message is read, so a Forwarded mark
  in an earlier of two such fields marks the message forwarded (it was dropped before).
  A copy held by a top-level message (InstantMessage, Message, SMS or MMS) is matched whatever
  its type is named, as a chat message's copy is; one of a custom type was counted but never
  compared before, so it was not listed. A copied chat
  must also say what the holder chat says around its messages (app, id, name, participants),
  and copies are numbered across all of a holder's RelatedModels elements. A copy marked
  forwarded where its holder is not (or the reverse) is listed. A copied chat with fewer
  messages than its holder is not listed: every holder message is imported anyway. ufdr-check also matches copied chats against holder messages
  imported once under an earlier id, copies of embedded messages, and reads a blank
  deleted_state as the importer does. Content keys are kept only for records holding copies.
  ufdr-check 0.1.0 -> 0.2.0: copies are matched to their holder the same way, in a row of their
  own (one that does not match must be one Baker lists for review, else it is a difference),
  counted per type, and never added to a record; a
  repeated account counts as a repeat; direction from the phone's own accounts is expected by
  identifier only, as the importer links them.
  The five model types Baker does not know on these packages (AppsUsageLog, ActivitySensorData,
  FileUpload, RecognizedDevice, Activity) were already listed for review on screen and in the
  report ("model type not recognised"); a test now covers it.
  Synthetic fixture `related_package` in `eval/synthetic/ufdr.py`: chats of 60, 45 and 7
  messages (two with the same words in the same second), attachments, recipients,
  RelatedModels copies of chats, messages, calls and accounts, a repeated account, and the five
  unknown types. No Hickman or real data in the repo.
- Where: main (#117, merged 2026-10-24)
- Verified: new tests in `tests/test_ufdr.py` and `tests/test_ufdr_check.py`; `make check` and
  eval in the PR description. Run on the three public packages in a cloud container
  (2026-10-21), with report.xml only (attachment files left out); results kept in the project
  files, not yet signed off by Arsh. Arsh re-ran all three on a macOS 15.6.1 arm64 machine on
  2026-10-23, on head a7728b7 (report.xml only): 0 differences on each.
- Open: copies of types Baker does not import (locations, cookies, ...) are not counted, since
  their holders are not read. report.xml states no count per type: `ModelCount` on `project`
  did not equal the number of records, so it is not compared. A message linked to the phone's
  owner only by a name that reads like an account identifier keeps an unknown direction.
  ufdr-check verifies message copies only. Copies of calls, contacts and accounts are matched
  by the importer alone, and on the public Android packages there are hundreds of them, so an
  independent check for those kinds is the next ufdr-check change.
- Affects: capabilities (UFDR import coverage, ufdr-check). No verdict, privacy or network change.
- Status doc: applied 2026-10-27
