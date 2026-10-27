## 2026-10-27: Synthetic case03 draft for measuring a challenge step (branch)
- Changed: new synthetic case03 to measure a forthcoming challenge step (a search for
  counter-evidence on claims close to supported). Seventeen claims in a mock affidavit over two
  Cellebrite-style reports (iPhone printed in UTC+0, Galaxy in local time; 1,265 messages,
  English and Russian), in four groups: 6 claims whose counter-record sits out of the fixed
  retrieval's reach where an explain.py direction finds it (clock C04, app_quiet C09,
  other_user C11, C16 and C17, other_app C13); 3 whose counter-record only a word-variant search
  finds (misspelled hand-off C03, transliteration C10, slang C15); 5 clean supported claims with
  near-miss decoys (C01, C02, C05, C12, C14); 3 written with defined terms, an alias or a
  relative date (C06, C07, C08). Generated deterministically (seed 20260327) by
  `eval/synthetic/case03_generate.py` from `case03_story.py` and `case03_key.py`. The DRAFT key
  (`draft_gold.jsonl`, labeled_by "DRAFT (case03 builder, not signed by Arsh)"), the DRAFT
  assumption sheet (`draft_assumptions.jsonl`), `ANSWER_KEY_DRAFT.md` and `SIGNING_SHEET.md`
  are under `eval/synthetic/case03/`; nothing under `eval/gold/`. `eval/synthetic/case03_reach.py`
  reports, per claim, whether the fixed retrieval returns each counter-record and decoy and which
  explain.py directions list it (a builder's report, not a test). `eval/run_pipeline.py` gains a
  case03 entry in DRAFT_GOLD and case03 branches for the reports and the affidavit PDF. Not wired
  into `make eval` or any gate; the challenge-step code was not read or used.
- Where: branch `claude/project-thread-6i2msb-case03`
- Verified: `tests/test_synthetic_case03.py` (synthetic only): the generator gives the same
  bytes twice (reports included); the committed drafts match a fresh build; every key-evidence,
  counter and decoy record exists after the real Cellebrite Excel importer reads both reports;
  every sheet row fits its template and each deterministic check gives the sheet's expected
  outcome; quotes are verbatim in cited records; the affidavit PDF reads back paragraph by
  paragraph; background chatter uses no reserved word. `case03_reach.py`: 0 problems (all 16
  planted counter-records unretrieved; each group 1 counter listed by its direction; no group 2
  counter listed by any direction). Model-free run on the draft key and sheet (cloud container,
  2026-10-27), information only: 17 claims, verdicts 6 supported, 2 contradicted, 9 unproven,
  accuracy 1.00 and 0 false supported against the draft key (by construction: the simulated
  expert reads that key); unreviewed run 0.65 (0 supported by design); key-evidence recall
  57% (27/47), the 16 counter-records never retrieved, C06 and C08 decided by failed checks
  that cite their 4 key records. `make check` passed.
- Open: the key and the sheet are drafts until Arsh signs them; C04 and C13 are the closest
  calls between unproven and contradicted. Group 1 rests on explain.py VERSION 1.0.0 and
  retrieval 0.2.0 as they are; a change to either can move a plant, which `case03_reach.py`
  shows. explain.py lists known noise on clean claims (ORLOV's "Pasha" saved names, C02's day
  boundary, C14's printed-UTC call), listed in the answer key.
- Affects: none (eval data draft)
- Status doc: no change
