## 2026-10-30: The assumption filler reads a person by the other names the expert gave them (aliases, after #181)
- Changed: `core/audit/assumption_filler.py` now reads each person the expert created by their
  name or by an alias from `person_aliases` (#181). Every place the filler read persons' names
  now goes through one reader, `_person_spans`, which uses `core/identity/aliases.person_names`.
  Those places are: the model's people answers (`_person`), the one-way and each-way count
  sides, the call parties, the no-contact sides, the recipient test, the writer of a quote, and
  "a quote that is only a name". The name keeps the surname rule ("PETROV"). An alias matches
  whole only, read by the same matcher the testability step and the Identities page use
  (`aliases.spans`, from #181). So "Big Dan" never matches a bare "Dan",
  "SUBJECT-12" is not "SUBJECT-1", and an alias two persons share matches neither.
  `core/selection/picks.case_names` and `core/timeline/check._names` also count an alias as a
  name, in any spelling the alias matcher reads alike ("Big Owen" for "Big-Owen"), so a quote
  that is only an alias is not looked up as a message. Codex reviewed four rounds; every
  finding has a test that failed before its fix.
  Why: case04's go/no-go run showed affidavit designations ("SUBJECT-1", "HAL", "DEZ") as the
  first reason the filler refused 11 claims. A person had only one name.
- Where: PR #186 (branch claude/project-thread-ds0ify), on main after #181.
- Verified: on this container, 2026-10-30.
  - 9 new filler tests and 1 alias test. The alias reads failed first; the guards are part of
    an alias, a longer name, a handle and a shared alias. `make check` passes.
  - Replay of Arsh's recorded 14B filler answers from the case04 go/no-go run
    (`case04.db`, sha256 e022beb0…; no model), with case.json's aliases added to a copy:
    "matches no person" refusals fell from 11 to 3, and one more claim gets a core assumption
    (a role, expert only). The other 7 now stop at the next refusal: a window the claim does
    not state (5), a channel, or a count. Tiers: 10 code-checked, 1 unsettled, 4 expert only
    (3 before), 5 with a failed core check, unchanged.
  - The remaining 3 are "CW-1" (no person in the case) and "DRIVER" twice (the alias entered
    is "the DRIVER", and a whole-only match does not drop "the"). Left strict on purpose: the
    affidavit defines "the DRIVER", and loosening `_person` to drop a leading "the" for this
    replay would tune to answers already seen.
  - A model-free case04 run with the signed sheet is unchanged (22 supported, 12 contradicted,
    14 unproven), since the sheet does not go through these reads.
- Open: the step's conversion on case04 with the step on is not re-measured here. #181's
  lookups change it too, so a before/after with the step on must count both.
- Affects: capabilities (claims written with an alias can now be tested by code). No privacy,
  network or verdict-rule change; no customer-facing claim.
- Status doc: pending: in section 2 "Pipeline (main)", row "5. Assumptions", append "A person
  is read by their name or by an alias the expert entered (whole only; an alias two persons
  share matches neither)."
