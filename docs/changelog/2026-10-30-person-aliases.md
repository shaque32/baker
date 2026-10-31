## 2026-10-30: Person aliases, the other names the expert gives a person (schema 0.6.0) (#181)
- Changed: the expert can record the other names the government document uses for a person,
  such as a designation ("SUBJECT-1", "CW-1", "the DRIVER") or a nickname ("HAL"). Why: on
  case04's testability go/no-go (Arsh's Mac run, 2026-10-30, NO-GO), 11 of the 32 claims the
  agent did not convert named a person by an affidavit designation. A person in Mabillon had one
  name, so code matched only the whole name or the surname (`plans/testability-no-go.md`).
  Real affidavits use designations like these all the time.
  - New table `person_aliases` (`core/schema.sql` 0.6.0, `CONTRACTS_VERSION` 0.6.0), signed by
    Arsh on 2026-10-30 (PROPOSED_CHANGES.md). Only an expert enters an alias, never a model: the
    action refuses any other actor, and the schema checks that `created_by` is an expert.
  - `core/review/actions.set_aliases` replaces a person's list, and an empty list clears it. Each
    alias added or removed is its own audit-log entry (`person.alias.add`, `person.alias.remove`).
    It refuses an alias with no letter or digit, one that is how the person's own name is
    already matched, and one that would also match another person (their whole name, surname or
    an alias of theirs). `add_person` now also refuses a name, or a surname, that another
    person's alias uses. `remove_person` removes the person's aliases and names them in its log
    entry.
  - One reader, `core/identity/aliases.person_names(conn) -> {person_id: (name, [aliases])}`. It
    keeps the name and the aliases apart, so the surname rule applies to the name only, and an
    alias is matched whole ("Big Owen" never matches a bare "Owen"). An alias two persons share
    is left out for both, so it matches neither. A case database made before 0.6.0 reads as
    having no aliases.
  - One matcher, `aliases.written(alias, text)`, used by the testability step and the
    Identities page alike. An alias is found whole, in any case, with the spacing and
    punctuation between its words not counting: "Subject 1" is "SUBJECT-1", and "the DRIVER's"
    holds "the DRIVER". "SUBJECT-12", "Subject-1A" and the handle "@subject-1" are not
    "SUBJECT-1". Letters in any script count ("Дима"), and both sides are casefolded alike, so
    "GROSS" finds "Groß" (Codex on #181). `aliases.spans` gives every place, for the filler.
  - The refusal compares every form a reader matches a name by: the whole name, the filler's
    surname ("Brown-Smith" for "John Brown-Smith") and the Identities page's last name word
    ("Smith"), so "Smith" may not be another person's alias (Codex on #181).
  - The testability step's person lookups (`core/audit/testability.py`) find a person by an
    alias the claim writes, whole only ("SUBJECT-12" is not "SUBJECT-1"). The Identities page
    (`core/identity/links.py`, `ui/identity_pages.py`) resolves names by alias. It lists a
    claim that uses an alias under that person, and it no longer offers a name an alias places.
    Each person's card has an "Also called in the document" field, and each name no person
    matches has "Add as another name" beside "Add as a person". Suggested names keep a
    designation's number ("SUBJECT-1", not "SUBJECT").
  - The report lists each alias in Limitations as an expert statement, with who gave it and
    when (report 0.29.0). The bundle carries the table like every other. An alias added or
    removed after an audit changes what the testability step's tries looked up, so
    `verify-bundle` notes those tries as not re-run, as it does after a person is added
    (Codex on #181). `verify-bundle` also holds each stored alias to the expert's logged
    actions (added, not since removed, as written, by that expert at that time), and fails a
    row the log does not account for or a logged alias that is missing, since the report names
    the expert and the time from these rows (Codex on #181).
  - The eval's case setup records each phone owner's aliases from the case's `case.json`.
    case04 gets the affidavit's definitions: SUBJECT-1 and HAL for Halloran, SUBJECT-2 for Ferro,
    and SUBJECT-3, DEZ and the DRIVER for Okafor. No other case has aliases, so `make eval` is
    unchanged.
  - Not in this PR: the assumption filler does not match aliases yet. Its `_name_spans` (claim
    text) and `_person` (a model answer's people) still read one name. That is the validation
    thread's PR, after this one, through `person_names` and `aliases.written`. Until it lands,
    with the testability step off (the default) no claim is filled, checked or decided
    differently. With the step on (the eval), its lookups give the model the person an alias
    names, and its check accepts that person as the claim's own, so the step's conversion on
    case04 can change with this PR alone. That is unmeasured. No verdict rule changes.
- Where: PR #181 (branch `claude/project-thread-6i2msb-aliases`)
- Verified: new `tests/test_person_aliases.py`, 31 tests:
  - recording, replacing and clearing aliases, each logged;
  - every refusal: another person's whole name, surname or alias; the person's own surname;
    no letter or digit; too long; a non-expert actor; an unknown person; the schema's CHECK and
    foreign key;
  - `add_person` refused on another person's alias or its surname, and `remove_person` removes
    and logs aliases;
  - a shared alias matches neither person;
  - an alias is matched whole, never by its last word, and near misses: "Subject 1" and the
    possessive match, "SUBJECT-12", "Subject-1A", "SUBJECT1" and "@subject-1" do not; an
    everyday alias ("the DRIVER") matches in any case; an alias in another script; "Groß"
    and "GROSS" folded alike;
  - `verify-bundle`'s alias check: a forged expert, an unlogged row and a missing logged alias
    each fail; a person's removal accounts for their aliases;
  - an alias another person's last name word matches ("Smith" for "John Brown-Smith") refused;
  - a database without the table;
  - on case01: the testability step's lookups by alias ("Subject 1" too, and not
    "SUBJECT-12"), the Identities page placing a designation and naming its claims while
    CW-1 and SUBJECT-12 stay offered, the report's limitation line, and the page's forms
    through the app.
  - `tests/test_testability.py`: an alias given after the audit makes `verify-bundle` note the
    tries as not re-run, with no failure. Without the fix the same test fails.
  - `tests/contract/test_contracts_v03.py` now expects 0.6.0.
  - `make check` passes; its eval numbers are in the PR and unchanged from main.
  - case04 regenerated: its `case.json` gains only the three `aliases` lists. No case04 run was
    made, so the effect on conversion is not measured.
- Open: the filler's matching (validation thread). An identity-link search by alias (a contact
  saved as "Hal") is not proposed, and an alias is not compared with phone names or contact
  display names, so an alias that equals one is not refused. An everyday alias such as "the
  DRIVER" matches those words in any claim, in any case: it is the expert's statement, so the
  expert should give the document's defined term. CW-1 and the BUYER are people the expert
  would add, not aliases, and the eval's case setup does not add them. Whether aliases raise
  the testability step's conversion is unmeasured until case05.
- Affects: capabilities (a new expert input, with its own limitation line in every report)
- Status doc: pending: section 8 item 5 ("Case safety and delivery"), after "...as the expert's
  statement (#139).": add "The expert can also record the document's other names for a person
  (SUBJECT-1, HAL) on the Identities page; each is matched whole, an alias that could match two
  people is refused, and every report lists them as the expert's statement (schema 0.6.0, #181).
  The testability step's lookups use them; the assumption filler does not yet."
