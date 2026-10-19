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
- Where: PR #77
- Verified: 71 new cases in `tests/test_assumption_filler.py`, 46 fail on main; make check
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
- Status doc: pending: section 9 (known limitations), add an item after 5: "**Writer read from
  the claim's words (fixed in #77).** When the 14B leaves a sender assumption without a person,
  code reads the writer from the claim (`stated_sender`, `core/audit/assumption_filler.py`,
  from #53). Before #77 it named the wrong person when the quote was handed on after the verb
  ("PETROV texted REYES, who responded 'ok'" gave PETROV), so the sender check tested the wrong
  person (inferred, not measured). #77 fails closed on these phrasings: the claim stays without
  a writer and is refused (UNPROVEN). It is a phrasing guard with an allowlist, not a parser. The eval did not
  move (case01 has no such phrasing)." Renumber the items after it.
