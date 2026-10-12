# Signed labeling guide for stance data

SYNTHETIC. HUMAN-OWNED (Arsh). Agents: do not modify.

`LABELING_GUIDE.md` is the stance-data labeling guide, draft v0.2, signed by Arsh on 2026-10-12
("approved" in the "Custom model for Baker" thread, 03:28 UTC), with questions 1 to 6 decided as
proposed. Below its header it is the draft `eval/stancedata/LABELING_GUIDE.md` byte for byte; a
test checks that the two still match.

Signing the guide also signs the Russian-English pairs its rule 6 names. The test pins these
files at commit 0f298d6 by SHA-256, so a change to any of them needs a new signature:

| File | SHA-256 |
|---|---|
| `eval/stancedata/LABELING_GUIDE.md` | `38a381894a0478d21e57b48f36a489f6188dd3d6e718b98356b50018df2b09d0` |
| `eval/train/glossary.py` | `952496c486d00df67c8d8cb63c98e8bc0278086ec401d28e5eb6dc36dda28cf8` |
| `eval/heldout/glossary.py` | `c61327dd0b1e309892f0ec6f025cf6f35d0d4d8fb3f10761db42e4ba8a1f479c` |

- The label samples are a separate signature. Until Arsh checks the review sheet (200 training
  and 100 held-out items), held-out scores are provisional and decide nothing
  (`eval/stancedata/GO_BAR.md`).
- The guide changes only when Arsh decides a rule was wrong, never to make a model pass. Edit
  the draft, have Arsh sign the new version, then copy it here and update the pins.
