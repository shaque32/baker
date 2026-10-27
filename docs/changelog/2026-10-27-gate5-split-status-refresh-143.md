## 2026-10-27: Pilot gate 5 split into 5a (UFDR Reader 7.48) and 5b (other formats); status refresh after #143
- Changed: `docs/PILOT_GATES.md` gate 5 is split, from Baker Product's docs-only spec on #100.
  5a, the first pilot's scope: Cellebrite Reader 7.48 UFDR packages import on the three public
  Hickman test phones, `mabillon ufdr-check` passes, the counts agree with Cellebrite Reader's own
  and the report matches the screen. It cites #117 and #130 (0 differences on all three, as their
  entries report) and stays Not met because Reader's own counts have not been compared. 5b,
  after the first pilot: Physical Analyzer Excel, other UFDR versions and AXIOM; Not met. Gate 5
  counts as one gate, met when 5a is met, so the count stays 14 of 19. A pilot rule says every
  format or version other than UFDR Reader 7.48 must show "not tested" on screen and in the
  report; that banner does not exist on main (Excel and PDF show no notice, and the UFDR notice
  is the same for every Reader version and still says "synthetic packages only"), so it is listed
  as open, not claimed. `docs/PRODUCT_STATUS.md` now matches main `d478705` (through #143): it
  applies the pending edits of #92, #104, #111, #113, #116 (already present on main), #117, #118,
  #119, #121, #123, #127, #128, #129, #131, #132, #133, #136, #138 and #139, marks them applied,
  and sets `Where:` to main on every entry that still named a PR. It also records report 0.17.0,
  importers (UFDR and Cellebrite Excel/PDF 0.3.1, AXIOM 0.2.0), ufdr-check 0.3.0, identity
  proposer 1.1.0, count check 1.0.3, bundle 1.2.0, and the validation work: run 1 a null result
  (0 of 106 tested), the run 2 plan (#140, #141) with its 30-claim minimum, and scorer 1.2.0
  (#142, #143). Each fact is labelled main, open PR or reported. No accuracy or runtime figure
  is added.
- Where: PR #144
- Verified: every version read from code at `d478705`; merge dates from main's first-parent
  history; `python tools/changelog.py pending` lists nothing; the banner check read
  `core/ingest/coverage.py`, `core/ingest/ufdr.py`, `core/ingest/axiom.py`,
  `core/ingest/cellebrite_common.py`, `core/report/html.py` and `ui/pages.py`; no
  `validation-v1-run2` tag on GitHub (`git ls-remote --tags`). `make check` in the PR.
- Open: gate 5's new criteria need Arsh's approval. The spec's cloud line ("cloud AI only for a
  case you opt in") is not used: the status doc keeps the wording Arsh chose on 2026-10-15 and
  every customer document uses. The "not tested" banner needs a code PR. Gate 5a's 0-difference
  runs and run 1's null result are reported in changelog entries and the run 2 plan, not re-run.
- Affects: customer-facing claims (gate 5 criteria and pilot scope; status doc refreshed). No
  capability, privacy or performance change.
- Status doc: no change
