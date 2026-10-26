## 2026-10-26: Phone time zones written the way Cellebrite writes them are read (#139)
- Changed: devices.timezone keeps the source's own text. A Cellebrite UFDR writes
  `(UTC-05:00)  New_York  (America)` and a Cellebrite Excel summary writes
  `(UTC-05:00) Eastern Time (US & Canada)`, but the assumption filler, the checks, the
  timeline, device local time and paired selection read only IANA names such as
  `America/New_York`. On the public iOS 15 phone (validation-v1 run 1) the filler refused the
  phone's zone for 16 of the 106 claims, and the other readers fell back or showed no local
  time. A new resolver, core/zones.py `resolve_zone`, turns the UFDR city and region form into
  the IANA name, and eight common Windows display names into theirs, only when the named zone
  has the stated offset in winter or summer. Anything else, including a name whose offset
  disagrees, comes back as given and is refused as before. devices.timezone still stores the
  raw text.
- Where: PR #139
- Verified: tests/test_zones.py: the exact UFDR and Excel strings, IANA pass-through, wrong
  offsets, unknown names and free text; the checks and device local time read a UFDR zone.
  tests/test_assumption_filler.py: a claim's window on a phone with the UFDR zone gets
  America/New_York; the test fails without the resolver. make check passes; synthetic eval
  numbers unchanged (their zones are already IANA names).
- Open: Only eight Windows display names are mapped (US zones and UTC); others stay unread.
  The time stamps a UFDR stores are not affected. The effect on the iOS 15 claims is not
  measured until validation run 2.
- Affects: capabilities (time-window claims on real Cellebrite exports)
- Status doc: no change
