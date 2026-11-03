## 2026-11-03: Claim page "Why" reads in plain English, rule text under Technical details (#PR)
- Changed: the claim page's "Why" fold showed the verdict rules' stored reasons as written for
  replay ("Rule 1a: check time failed on 'The message "its done" (person:dev:item1:owner ...)':
  Outside the window: msg:item1:Chats!1011 at ..."), which Arsh found hard to read. Each reason
  now gets a plain first line (new `core/report/why.py`): people and phones by the names the
  case gives them, records as links (to the claim's evidence item, else the message in its
  conversation), times in the claim's own zone, and a note when a phone prints a time in another
  offset. Example, demo C10: "Both phones record the message at 9:31 PM on March 4, 2026 (New
  York time), not "At 2:31 a.m. on March 5, 2026" as the claim states. Apple iPhone 13 (A2482)
  prints it in UTC as "3/5/2026 2:31:00 AM(UTC+0)", not in New York time." Reasons that say the
  same thing about one assumption share a line (C19's five contradicting records). The rules'
  exact text, the rule version and the run id stay on the page, folded under "Technical
  details". A reason the writer cannot place prints as the rules wrote it, ids shown by name.
  Display only: the lines read the stored reasons, assumptions, checks and evidence and decide
  nothing; `core/audit/rules.py`, the stored reasons and the exported report are unchanged (the
  report still prints every reason in full, with its key from names back to case ids).
- Where: PR #PR
- Verified: tests/test_why_lines.py makes the signed rules write each kind of reason (1a, 1a
  awaiting an expert, 1b grouped, 2 covered and not covered, unconfirmed owner, 3, 3a, 3c, 3d,
  3e) and checks every one gets a plain line with no rule text, nothing lost or reordered;
  tests/test_demo.py checks every demo claim page keeps each stored reason verbatim under
  Technical details with the rule version and run, has no case ids or forbidden words in the
  plain lines, and C10's and C19's lines. `make check` results are in the PR.
- Open: the exported report still leads with the rules' text (a plain line there needs a
  REPORT_VERSION bump; not done). Rule 3f and the AI-reviewed supported line are not reachable
  under rules 0.4.0 (AI review covers nothing) and are untested on real verdicts. Phones show by
  the expert's name for them, else the extraction's label ("Apple iPhone 13 (A2482)"), not
  "Item 1" unless the expert named it so. People the case has not added still show by id
  (person:sokolov), as elsewhere.
- Affects: customer-facing wording on the claim page; no capability, privacy, performance or
  verdict change.
- Status doc: no change
