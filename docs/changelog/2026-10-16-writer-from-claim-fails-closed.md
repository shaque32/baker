## 2026-10-16: Writer read from the claim fails closed when the quote is handed on (#77)
- Changed: `stated_sender` (from #53) fills a sender assumption the 14B left without a person by
  reading the writer before the quote. It took the nearest writing verb's subject even when the
  quote belonged to someone else ("PETROV texted REYES, who responded 'ok'", "PETROV replied to
  REYES's message 'ok'", "PETROV messaged REYES. REYES: 'ok'"), so the sender check tested the
  wrong person. Now a sentence break, "who/whose/which", "and/but/then", or a possessive
  between the verb and the quote names no writer (times like "2:31 p.m.", "before midnight" or
  a second recipient "and SMITH" do not count); so does a name after "of", "for", "posing as"
  and the like; and "answered", "responded", "replies" and similar now count as quote verbs.
  Every word between the verb and the quote must also be on a short allowlist (names, "@"
  handles, titles, numbers, times, "to", "and", "that", "two texts" and the like), so a
  phrasing the guard does not know names no writer. Found by the independent review on #57.
  No signed file touched.
- Where: main (PR #77, merge 9a33351, 2026-10-19).
- Verified: 76 new cases in `tests/test_assumption_filler.py`, 50 fail on main; make check
  passes; eval unchanged (case01 1.00, 0 false supported; hostile PASS; case02
  aggregate 0.90, 0 false supported).
- Open: a phrasing-based guard with an allowlist, not a parser; a new phrasing built only from
  allowed words could still slip through. Some plain phrasings now fail closed ("from his
  brother's phone", an all-caps recipient who is not a person the expert created). It only
  matters when the 14B leaves the sender's person out (seen on the Mac run, ¶6.1). Fails closed:
  the cost is a claim refused (UNPROVEN) rather than a wrong person checked.
- Affects: verdict inputs, only on claims with these phrasings: no wrong person checked, so no
  wrong CONTRADICTED or wrong pass from it (inferred, not measured).
  No privacy, performance or customer-facing claim change.
- Status doc: applied 2026-10-19
