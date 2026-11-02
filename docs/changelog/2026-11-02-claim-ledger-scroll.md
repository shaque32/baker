## 2026-11-02: The claim page's side ledger stays on the claim you opened (#PR)
- Changed: clicking a claim in the claim page's side ledger (say C10) opened it but the ledger
  scrolled back to C01, because every click loads a new page. Each ledger row now has an id
  (`lg-<claim id>`) and each ledger link lands on it, so the ledger scrolls to the opened claim
  while the window stays at the top of the new claim (CSS only; the page policy still forbids
  scripts). In Chrome and Edge, `scroll-initial-target` also centres the open claim on any load
  without that anchor, such as after a form or from the Claims overview. The ledger list uses
  `overflow: clip` instead of `hidden` on this page so it is not itself a scroll box.
  Code: `ui/pages.py` (`_ledger`), `ui/css/claim.py`.
- Where: PR #PR
- Verified: new test in `tests/test_review_screen.py`; checked in headless Chromium 153 on the
  scripted demo (1440 and 800 px wide): after clicking C10, C10 sits a third of the way down the
  ledger and the window stays at the top; with `scroll-initial-target` turned off (as in
  browsers without it) the anchor alone does the same; narrow layout (ledger below the claim)
  keeps the window at the top.
- Open: Safari and Firefox not run (they lack `scroll-initial-target`, so after a form or from
  the overview their ledger still opens at C01; ledger clicks use the anchor and should work,
  unverified there).
- Affects: none (review screen navigation only)
- Status doc: no change
