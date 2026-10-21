## 2026-10-21: Status refresh after #110 (#103, #106 to #110; pilot gate 1 met)
- Changed: `docs/PRODUCT_STATUS.md` now matches main `30d194d`. It applies the pending edits of
  #103 (UFDR imports embedded originals; also gate 4's row and order note in
  `docs/PILOT_GATES.md`, gate 4 stays Not met), #106 (signed Windows installer), #108 (claims
  overview, gap lines, report 0.10.0), #109 (claim page checklist and conversation view) and
  #110 (tab groups and case page), marks them applied and sets their `Where:` to main. It also
  records #107's check versions (count 1.0.2, the others 1.0.1) and the importer version 0.2.0,
  and corrects `Where:` on #102's and #105's entries. Pilot gate 1 (CI green 3 times) is met:
  the `checks` workflow passed on the first attempt on 7 consecutive pushes to main (runs
  39503538565, 39510733327, 39513830950, 39520824524, 39607503937, 39617971260, 39629330625),
  so 13 of 19 gates are met.
- Where: branch `claude/project-thread-5u7u3u`, not merged
- Verified: each applied phrase matched exactly once; report 0.10.0, importer 0.2.0, check
  versions and the new screen text checked in `core/` and `ui/pages.py` on main; `make test` and
  `ruff check .` (Linux, 2026-10-21). CI run ids taken from the coordinator's record, not
  re-queried here.
- Open: the feature entries' screenshots and eval numbers are copied, not re-run.
- Affects: customer-facing claims (gate count 13 of 19; signed installer stated). No capability,
  privacy or performance change.
- Status doc: no change
