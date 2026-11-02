## 2026-11-02: Pages stay where the examiner acted: the claim ledger, Identities, and a Safari check (#204)
- Changed: clicking a claim in the claim page's side ledger (say C10) opened it but the ledger
  scrolled back to C01, because every click loads a new page. Each ledger row now has an id
  (`lg-<claim id>`) and each ledger link lands on it, so the ledger scrolls to the opened claim
  while the window stays at the top of the new claim (CSS only; the page policy still forbids
  scripts). In Chrome and Edge, `scroll-initial-target` also centres the open claim on any load
  without that anchor, such as after a form or from the Claims overview. The ledger list uses
  `overflow: clip` instead of `hidden` on this page so it is not itself a scroll box.
  Identities: "Link an account yourself" now comes back to its own form instead of the top of
  the page. Code: `ui/pages.py` (`_ledger`), `ui/css/claim.py`, `ui/identity_pages.py`.
  CI: the Mac clean-install job drives Safari through safaridriver on the demo case
  (`packaging/safari_scroll.py`), report only for now.
- Where: PR #204
- Verified: new test in `tests/test_review_screen.py`. Headless Chromium 153 on the scripted
  demo: every form on every page except Set up and run's audit, case and key forms (about 360
  posts) lands on its anchor or stays near the top it started at; before this change only the
  Identities link form went to the top. Safari 27.2 on GitHub's macos-15 runner (2026-11-02):
  typing in the testability card does not move the page, accepting lands on the card, confirming
  a verdict lands on the verdict, and opening C10 from the side ledger shows C10 in the ledger.
- Open: Safari has no `scroll-initial-target`, so after a form on a claim page (or arriving
  from the Claims overview) Safari's side ledger starts at C01 again; the page itself lands
  right. Firefox not run. The Safari CI step does not fail the job yet.
- Affects: none (review screen navigation only)
- Status doc: no change
