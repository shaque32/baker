# Signed labeling guide for stance data

SYNTHETIC. HUMAN-OWNED (Arsh). Agents: do not modify.

`LABELING_GUIDE.md` is the stance-data labeling guide, draft v0.4, signed by Arsh on 2026-11-01
("Sign v0.4 as written" on a decision card in the "Plan a faster, sharper audit engine" thread,
18:47 UTC), with the calls on its list of changes decided as written. It replaces v0.3, signed
on 2026-10-14, which replaced v0.2 (2026-10-12). Below its header it is the draft
`eval/stancedata/LABELING_GUIDE.md` byte for byte; a test checks that the two still match.

Signing the guide also signs the Russian-English pairs its rule 6 names. The test pins these
files by SHA-256 (the draft as signed, its header saying so; the glossaries, unchanged since
v0.2), so a change to any of them needs a new signature:

| File | SHA-256 |
|---|---|
| `eval/stancedata/LABELING_GUIDE.md` | `4dafbb8560fa862685a31320f346f1e38bab7eb00ecfe2de2f60876114f7ede1` |
| `eval/train/glossary.py` | `952496c486d00df67c8d8cb63c98e8bc0278086ec401d28e5eb6dc36dda28cf8` |
| `eval/heldout/glossary.py` | `c61327dd0b1e309892f0ec6f025cf6f35d0d4d8fb3f10761db42e4ba8a1f479c` |

- The label samples are a separate signature. Until Arsh checks the review sheet (200 training
  and 100 held-out items), held-out scores are provisional and decide nothing
  (`eval/stancedata/GO_BAR.md`).
- The guide changes only when Arsh decides a rule was wrong, never to make a model pass. Edit
  the draft, have Arsh sign the new version, then copy it here and update the pins.
