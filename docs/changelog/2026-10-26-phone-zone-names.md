## 2026-10-26: Phone time zones written the way Cellebrite writes them are read (#139)
- Changed: devices.timezone keeps the source's own text. A Cellebrite UFDR writes
  `(UTC-05:00)  New_York  (America)`, and a Cellebrite Excel summary can write a Windows name
  such as `(UTC-05:00) Eastern Time (US & Canada)`, but the assumption filler, the checks, the
  timeline, device local time and paired selection read only IANA names such as
  `America/New_York`. On the public iOS 15 phone (validation-v1 run 1) the filler refused the
  phone's zone for 16 of the 106 claims, and the other readers fell back or showed no local
  time. A new resolver, core/zones.py `resolve_zone`, turns the UFDR city and region form into
  the IANA name, and eight common Windows display names into theirs, only when the named zone
  has the stated offset in winter or summer. Anything else, including a name whose offset
  disagrees, comes back as given and is refused as before. devices.timezone still stores the
  raw text. The Cellebrite Excel and PDF importers (0.3.1) no longer store the report's
  display "Time zone" as the phone's zone when the summary has no Device time zone: the
  examiner's display setting is not the phone's, so the phone's zone stays unknown and time
  ranges are refused, as before this change. The display zone stays in the import coverage.
- Where: PR #139
- Verified: tests/test_zones.py: the exact UFDR and Excel strings, IANA pass-through, wrong
  offsets, unknown names and free text; the checks and device local time read a UFDR zone.
  tests/test_assumption_filler.py: a claim's window on a phone with the UFDR zone gets
  America/New_York, and the same case with the UFDR wording gets the same assumptions and
  check outcomes as with the IANA name; a UFDR zone whose offset disagrees is still refused.
  tests/test_cellebrite_excel.py: a Device time zone is stored as written and read as a zone;
  a report display zone alone leaves the phone's zone unknown. make check passes; synthetic eval
  numbers unchanged (their zones are already IANA names).
- Open: Only eight Windows display names are mapped (US zones and UTC); others stay unread.
  Before this change an Excel case with no Device time zone stored the report's zone; such a
  case keeps it until it is imported again. The timeline and paired selection read zones
  through the resolver but have no test with a UFDR or Excel string.
  The time stamps a UFDR stores are not affected. The effect on the iOS 15 claims is not
  measured until validation run 2.
- Affects: capabilities (time-window claims on real Cellebrite exports)
- Status doc: no change
