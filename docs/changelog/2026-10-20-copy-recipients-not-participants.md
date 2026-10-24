## 2026-10-20: Copy recipients are not thread participants (#107)
- Changed: when a handle is matched to a thread titled with it, the recipients of an embedded
  copy inside that thread no longer count as its participants (the copy's own addressee was
  never in that conversation). This follows up #103. On a case with embedded copies, a handle
  that was unresolved (inconclusive) can now resolve to one account, so the checks that resolve
  handles record new versions: identity, sender, timing, weekday and absence 1.0.1, count 1.0.2.
- Where: main (#107, merged 2026-10-20)
- Verified: `tests/checks/test_unit.py` (the copy's recipient is left out; versions recorded);
  `make check` on Linux, 2026-10-20: case01 1.00 with 0 false supported, hostile PASS, case02
  aggregate 0.90 with 0 false supported. case01 and case02 hold no embedded copies.
- Open: none.
- Affects: capabilities (handle matching on UFDR cases with forwarded or quoted copies).
- Status doc: no change
