## 2026-10-24: ufdr-check verifies call, contact and account copies (#130)
- Changed: ufdr-check 0.2.0 -> 0.3.0 now checks the RelatedModels copies of calls, contacts and
  accounts on its own, as it already checked message copies. Before, the importer alone matched
  those copies. Each copy must say what the record holding it says, field by field as the
  importer maps it:
  - a call: app, time, duration, Direction/Type/Status, each side's parties in order, deleted
    state and recovery marks;
  - a contact: name, entries, deleted state and recovery marks;
  - an account: app, identifier and name.

  A copy inside a copy must match that copy. One that does not match must be one the importer
  lists for review, else it is a difference, and one the importer lists that matches is a
  difference too. The check adds three rows: "call copies", "contact copies" and "account
  copies under RelatedModels".

  Importer 0.3.0 -> 0.3.1: a copy of another type held by a call, contact or account (a custom
  CallLog, say) was counted but never compared. It is now matched to its holder, so it is
  listed for review. Copies like this inside a copied call, contact or account are handled the
  same way. A new counter, `related_record_copies_matching_no_record`, lets ufdr-check account
  for these copies past the capped list of locators. This was Arsh's follow-up to #117
  (2026-10-23), plus Baker Merge's non-blocking item on #117.
- Where: PR #130
- Verified: tests in `tests/test_ufdr_check.py`:
  - calls (same, duration, deleted, carved, type, sides), contacts (same, name, entry,
    deleted) and accounts (same, name, identifier): each run with the importer, and with an
    importer that lists nothing;
  - a custom-typed copy held by a call or a contact, which fails before the importer fix;
  - a call copy inside a call copy.

  Public Hickman UFDRs (cloud container, report.xml only, 2026-10-24): 0 differences on all
  three, and every call, contact and account copy agrees. The copies the importer lists for
  review are unchanged. The iOS call copy that lacks its duration is now found by ufdr-check
  as well. `make check`: see the PR.
- Open: counts are still not compared with Cellebrite Reader's own counts, because Reader
  access is locked. FORMAT_SUPPORT stays unverified. A call, contact or account copy held by a
  message is checked as a message copy, as before.
- Affects: capabilities (ufdr-check coverage; UFDR import lists more copies for review). No
  verdict, privacy or network change.
- Status doc: no change
