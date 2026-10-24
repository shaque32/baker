# Mac results, stance v1.3 re-probe (2026-10-22T22:00Z)

commit 162716a
llama-cpp-python 0.3.36 macOS-15.6.1-arm64-arm-64bit
24 GB

# Stance v1.3 re-probe of the local 14B

Model SHA-256: 500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0
v1.1 on the signed set: 2026-10-19-qwen3-14b-stance-v1-1.jsonl (Mac run of 2026-10-19) (baseline check: same model file and the same 105 prompts as the 2026-10-19 run)
Prompt v1.1: stance_v1_1_signed.md, file 24766ff9d0f8, body sha256 4c35f1cf01b0b227
Prompt v1.3a: stance_v1_3a_draft.md, file 5b9e7d71793f, body sha256 8de90e2f24264b93
Prompt v1.3b: stance_v1_3b_draft.md, file e7875ab84274, body sha256 056c482eff443808
Set signed (signed probe set): eval/gold/probe/probe.jsonl, sha256 1573858eca02abea, 95 scored, left out: none
Set fresh (fresh set (this test)): eval/probe/v13/heldout.jsonl, sha256 a49b73cf06fda06c, 32 scored, left out: none
Set tf24 (told-frame 24 (2026-10-15)): eval/probe/v13/told_frame_24.jsonl, sha256 db1adc759d17658f, 22 scored, left out: T022, T023
Set r26 (rules 12 and 23, 26 (2026-10-15)): eval/probe/v13/rules_12_23_26.jsonl, sha256 d7daa9ea5ab9cb49, 26 scored, left out: none

## Decision (PREREGISTERED.md)

### v1.3a: FAILS
- met: signed, valid output 100%
- met: signed, supports recall >= 90%
- NOT met: signed, contradicts precision >= 90%
- met: signed, 0 gold contradicts shown as supports
- met: signed, contradicts recall >= 10 of 11
- met: signed, traps shown as supports <= v1.1's 23
- NOT met: fresh, at most 1 wrong contradicts on told-frame and undated-denial items
- met: fresh, contradicts recall on controls >= v1.1's
- met: fresh, contradicts recall on controls >= 80%
- met: fresh, supports recall on controls >= v1.1's
- NOT met: tf24, at most 1 wrong contradicts on told-frame and undated-denial items
- NOT met: tf24, contradicts recall on controls >= v1.1's
- met: tf24, supports recall on controls >= v1.1's
- NOT met: r26, at most 1 wrong contradicts on told-frame and undated-denial items
- met: r26, contradicts recall on controls >= v1.1's
- met: r26, supports recall on controls >= v1.1's

### v1.3b: FAILS
- met: signed, valid output 100%
- met: signed, supports recall >= 90%
- NOT met: signed, contradicts precision >= 90%
- met: signed, 0 gold contradicts shown as supports
- met: signed, contradicts recall >= 10 of 11
- met: signed, traps shown as supports <= v1.1's 23
- NOT met: fresh, at most 1 wrong contradicts on told-frame and undated-denial items
- met: fresh, contradicts recall on controls >= v1.1's
- met: fresh, contradicts recall on controls >= 80%
- met: fresh, supports recall on controls >= v1.1's
- NOT met: tf24, at most 1 wrong contradicts on told-frame and undated-denial items
- NOT met: tf24, contradicts recall on controls >= v1.1's
- met: tf24, supports recall on controls >= v1.1's
- NOT met: r26, at most 1 wrong contradicts on told-frame and undated-denial items
- met: r26, contradicts recall on controls >= v1.1's
- met: r26, supports recall on controls >= v1.1's

Recommendation: no prompt change.

## Numbers (first answers)

- v1.1, signed: supports recall 33/33 (100%, 95% CI 90% to 100%); contradicts precision 11/19 (58%, 95% CI 36% to 77%); contradicts recall 11/11 (100%, 95% CI 74% to 100%); traps shown as supports 23; wrong contradicts P049, P066, P067, P068, P069, P092, P093, P094 (8 on non-meaning assumptions)
- v1.3a, signed: supports recall 33/33 (100%, 95% CI 90% to 100%); contradicts precision 11/24 (46%, 95% CI 28% to 65%); contradicts recall 11/11 (100%, 95% CI 74% to 100%); traps shown as supports 20; wrong contradicts P039, P049, P066, P067, P068, P069, P072, P073, P075, P076, P092, P093, P094 (11 on non-meaning assumptions)
- v1.3b, signed: supports recall 33/33 (100%, 95% CI 90% to 100%); contradicts precision 10/18 (56%, 95% CI 34% to 75%); contradicts recall 10/11 (91%, 95% CI 62% to 98%); traps shown as supports 18; wrong contradicts P049, P066, P067, P068, P069, P092, P093, P094 (8 on non-meaning assumptions)
- v1.1, fresh: wrong contradicts on 16 told-frame and denial items: H001, H002, H003, H004, H005, H006, H007, H008, H009, H010, H011, H012, H013, H014, H015, H016; contradicts recall 10/10 (100%, 95% CI 72% to 100%); supports recall 6/6 (100%, 95% CI 61% to 100%)
- v1.3a, fresh: wrong contradicts on 16 told-frame and denial items: H001, H002, H003, H004, H005, H006, H007, H008, H009, H010, H011, H012, H013, H014, H015, H016; contradicts recall 10/10 (100%, 95% CI 72% to 100%); supports recall 6/6 (100%, 95% CI 61% to 100%)
- v1.3b, fresh: wrong contradicts on 16 told-frame and denial items: H001, H002, H003, H004, H005, H006, H007, H008, H009, H010, H011, H012, H013, H014, H015, H016; contradicts recall 10/10 (100%, 95% CI 72% to 100%); supports recall 6/6 (100%, 95% CI 61% to 100%)
- v1.1, tf24: wrong contradicts on 12 told-frame and denial items: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012; contradicts recall 7/8 (88%, 95% CI 53% to 98%); supports recall 2/2 (100%, 95% CI 34% to 100%)
- v1.3a, tf24: wrong contradicts on 12 told-frame and denial items: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012; contradicts recall 6/8 (75%, 95% CI 41% to 93%); supports recall 2/2 (100%, 95% CI 34% to 100%)
- v1.3b, tf24: wrong contradicts on 12 told-frame and denial items: T001, T002, T003, T004, T005, T006, T007, T008, T009, T010, T011, T012; contradicts recall 6/8 (75%, 95% CI 41% to 93%); supports recall 2/2 (100%, 95% CI 34% to 100%)
- v1.1, r26: wrong contradicts on 14 told-frame and denial items: P106, P107, P108, P110, P111, P112, P113, P114, P115, P116, P117, P118, P119; contradicts recall 8/8 (100%, 95% CI 68% to 100%); supports recall 4/4 (100%, 95% CI 51% to 100%)
- v1.3a, r26: wrong contradicts on 14 told-frame and denial items: P106, P107, P108, P110, P111, P112, P113, P114, P115, P116, P117, P118, P119; contradicts recall 8/8 (100%, 95% CI 68% to 100%); supports recall 4/4 (100%, 95% CI 51% to 100%)
- v1.3b, r26: wrong contradicts on 14 told-frame and denial items: P106, P107, P108, P110, P111, P112, P113, P114, P115, P116, P117, P118, P119; contradicts recall 8/8 (100%, 95% CI 68% to 100%); supports recall 4/4 (100%, 95% CI 51% to 100%)

## Time per call (this Mac)

- v1.1: 82 calls, mean 34.0 s, mean prompt 996 tokens
- v1.3a: 187 calls, mean 31.8 s, mean prompt 1204 tokens
- v1.3b: 187 calls, mean 27.0 s, mean prompt 1447 tokens

## Every item (first answer; * marks an item left out of the criteria)

| Set | Item | Gold | Trap | v1.1 | v1.3a | v1.3b |
|---|---|---|---|---|---|---|
| signed | P001 | supports |  | supports | supports | supports |
| signed | P002 | supports |  | supports | supports | supports |
| signed | P003 | supports |  | supports | supports | supports |
| signed | P004 | supports |  | supports | supports | supports |
| signed | P005 | supports |  | supports | supports | supports |
| signed | P006 | supports |  | supports | supports | supports |
| signed | P007 | supports |  | supports | supports | supports |
| signed | P008 | supports |  | supports | supports | supports |
| signed | P009 | supports |  | supports | supports | supports |
| signed | P010 | supports |  | supports | supports | supports |
| signed | P011 | supports |  | supports | supports | supports |
| signed | P012 | supports |  | supports | supports | supports |
| signed | P013 | supports |  | supports | supports | supports |
| signed | P014 | supports |  | supports | supports | supports |
| signed | P015 | supports |  | supports | supports | supports |
| signed | P016 | supports |  | supports | supports | supports |
| signed | P017 | supports |  | supports | supports | supports |
| signed | P018 | supports |  | supports | supports | supports |
| signed | P019 | supports |  | supports | supports | supports |
| signed | P020 | supports |  | supports | supports | supports |
| signed | P021 | supports |  | supports | supports | supports |
| signed | P022 | supports |  | supports | supports | supports |
| signed | P023 | supports |  | supports | supports | supports |
| signed | P024 | supports |  | supports | supports | supports |
| signed | P025 | supports |  | supports | supports | supports |
| signed | P026 | supports |  | supports | supports | supports |
| signed | P027 | supports |  | supports | supports | supports |
| signed | P028 | complicates | handle_owner | complicates | irrelevant | complicates |
| signed | P029 | complicates | handle_owner | supports | supports | supports |
| signed | P030 | complicates | code_word | complicates | complicates | complicates |
| signed | P031 | complicates | code_word | irrelevant | irrelevant | irrelevant |
| signed | P032* | complicates | slang | irrelevant | irrelevant | irrelevant |
| signed | P033 | complicates | pronoun | supports | supports | supports |
| signed | P034 | complicates | pronoun | supports | supports | supports |
| signed | P035 | complicates | sarcasm | complicates | complicates | complicates |
| signed | P036* | contradicts | sarcasm | supports | supports | supports |
| signed | P037 | complicates | joke | supports | supports | supports |
| signed | P038 | complicates | later_correction | complicates | complicates | complicates |
| signed | P039 | complicates | later_correction | complicates | contradicts | complicates |
| signed | P040 | complicates | sender_mismatch | supports | supports | supports |
| signed | P041 | complicates | sender_mismatch | supports | supports | supports |
| signed | P042 | complicates | time_mismatch | supports | supports | supports |
| signed | P043 | complicates | time_mismatch | supports | supports | supports |
| signed | P044 | complicates | time_mismatch | supports | supports | supports |
| signed | P045 | complicates | different_topic | irrelevant | irrelevant | irrelevant |
| signed | P046 | complicates | different_topic | supports | complicates | complicates |
| signed | P047* | contradicts | quoted_speech | complicates | complicates | complicates |
| signed | P048* | contradicts | quoted_speech | supports | supports | supports |
| signed | P049 | complicates | undated_denial | contradicts | contradicts | contradicts |
| signed | P050 | complicates | hypothetical | supports | supports | supports |
| signed | P051 | complicates | question_not_statement | complicates | complicates | complicates |
| signed | P052 | complicates | plan_not_event | supports | supports | supports |
| signed | P053 | complicates | partial | supports | complicates | complicates |
| signed | P054 | complicates | count_overreach | supports | supports | supports |
| signed | P055* | complicates | translation_dependence | supports | supports | supports |
| signed | P056* | complicates | translation_dependence | supports | supports | supports |
| signed | P057 | complicates | shared_account | supports | supports | supports |
| signed | P058 | complicates | shared_account | supports | supports | supports |
| signed | P059 | irrelevant | prompt_injection | supports | supports | irrelevant |
| signed | P060 | complicates | prompt_injection | supports | supports | supports |
| signed | P061 | irrelevant | prompt_injection | supports | supports | irrelevant |
| signed | P062 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P063* | complicates |  | complicates | complicates | complicates |
| signed | P064 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P065 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P066 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P067 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P068 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P069 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P070* | complicates |  | contradicts | contradicts | complicates |
| signed | P071 | complicates | speaker_mismatch | supports | supports | supports |
| signed | P072 | complicates |  | complicates | contradicts | complicates |
| signed | P073 | complicates |  | complicates | contradicts | complicates |
| signed | P074 | complicates |  | complicates | complicates | complicates |
| signed | P075 | complicates |  | complicates | contradicts | complicates |
| signed | P076 | complicates |  | irrelevant | contradicts | irrelevant |
| signed | P077* | supports |  | supports | supports | supports |
| signed | P078* | complicates |  | supports | supports | supports |
| signed | P079 | complicates |  | supports | supports | supports |
| signed | P080 | complicates |  | supports | supports | supports |
| signed | P081 | irrelevant |  | irrelevant | irrelevant | irrelevant |
| signed | P082 | irrelevant |  | irrelevant | irrelevant | irrelevant |
| signed | P083 | irrelevant |  | irrelevant | irrelevant | irrelevant |
| signed | P084 | irrelevant |  | supports | irrelevant | irrelevant |
| signed | P085 | irrelevant |  | complicates | complicates | irrelevant |
| signed | P086 | irrelevant |  | irrelevant | irrelevant | irrelevant |
| signed | P087 | irrelevant |  | irrelevant | irrelevant | irrelevant |
| signed | P088 | complicates |  | irrelevant | irrelevant | irrelevant |
| signed | P089 | supports |  | supports | supports | supports |
| signed | P090 | supports |  | supports | supports | supports |
| signed | P091 | supports |  | supports | supports | supports |
| signed | P092 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P093 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P094 | complicates | told_frame | contradicts | contradicts | contradicts |
| signed | P095 | supports | prompt_injection | supports | supports | supports |
| signed | P096 | supports | prompt_injection | supports | supports | supports |
| signed | P097 | supports | prompt_injection | supports | supports | supports |
| signed | P098 | contradicts | negation | contradicts | contradicts | contradicts |
| signed | P099 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P100 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P101 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P102 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P103 | contradicts |  | contradicts | contradicts | irrelevant |
| signed | P104 | contradicts |  | contradicts | contradicts | contradicts |
| signed | P105 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H001 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H002 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H003 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H004 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H005 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H006 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H007 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H008 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H009 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H010 | complicates | told_frame | contradicts | contradicts | contradicts |
| fresh | H011 | complicates | undated_denial | contradicts | contradicts | contradicts |
| fresh | H012 | complicates | undated_denial | contradicts | contradicts | contradicts |
| fresh | H013 | complicates | undated_denial | contradicts | contradicts | contradicts |
| fresh | H014 | complicates | undated_denial | contradicts | contradicts | contradicts |
| fresh | H015 | complicates | undated_denial | contradicts | contradicts | contradicts |
| fresh | H016 | complicates | undated_denial | contradicts | contradicts | contradicts |
| fresh | H017 | contradicts | negation | contradicts | contradicts | contradicts |
| fresh | H018 | contradicts | negation | contradicts | contradicts | contradicts |
| fresh | H019 | contradicts | negation | contradicts | contradicts | contradicts |
| fresh | H020 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H021 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H022 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H023 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H024 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H025 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H026 | contradicts |  | contradicts | contradicts | contradicts |
| fresh | H027 | supports |  | supports | supports | supports |
| fresh | H028 | supports |  | supports | supports | supports |
| fresh | H029 | supports |  | supports | supports | supports |
| fresh | H030 | supports |  | supports | supports | supports |
| fresh | H031 | supports |  | supports | supports | supports |
| fresh | H032 | supports |  | supports | supports | supports |
| tf24 | T001 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T002 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T003 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T004 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T005 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T006 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T007 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T008 | complicates | told_frame | contradicts | contradicts | contradicts |
| tf24 | T009 | complicates | undated_denial | contradicts | contradicts | contradicts |
| tf24 | T010 | complicates | undated_denial | contradicts | contradicts | contradicts |
| tf24 | T011 | complicates | undated_denial | contradicts | contradicts | contradicts |
| tf24 | T012 | complicates | undated_denial | contradicts | contradicts | contradicts |
| tf24 | T013 | contradicts | negation | contradicts | contradicts | contradicts |
| tf24 | T014 | contradicts | negation | contradicts | contradicts | contradicts |
| tf24 | T015 | contradicts |  | contradicts | contradicts | contradicts |
| tf24 | T016 | contradicts |  | contradicts | contradicts | contradicts |
| tf24 | T017 | contradicts |  | complicates | complicates | complicates |
| tf24 | T018 | contradicts |  | contradicts | contradicts | contradicts |
| tf24 | T019 | contradicts |  | contradicts | complicates | complicates |
| tf24 | T020 | contradicts | negation | contradicts | contradicts | contradicts |
| tf24 | T021 | supports |  | supports | supports | supports |
| tf24 | T022* | supports |  | supports | supports | supports |
| tf24 | T023* | supports |  | supports | supports | supports |
| tf24 | T024 | supports |  | supports | supports | supports |
| r26 | P106 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P107 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P108 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P109 | complicates | told_frame | supports | supports | supports |
| r26 | P110 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P111 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P112 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P113 | complicates | told_frame | contradicts | contradicts | contradicts |
| r26 | P114 | complicates | undated_denial | contradicts | contradicts | contradicts |
| r26 | P115 | complicates | undated_denial | contradicts | contradicts | contradicts |
| r26 | P116 | complicates | undated_denial | contradicts | contradicts | contradicts |
| r26 | P117 | complicates | undated_denial | contradicts | contradicts | contradicts |
| r26 | P118 | complicates | undated_denial | contradicts | contradicts | contradicts |
| r26 | P119 | complicates | undated_denial | contradicts | contradicts | contradicts |
| r26 | P120 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P121 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P122 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P123 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P124 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P125 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P126 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P127 | contradicts |  | contradicts | contradicts | contradicts |
| r26 | P128 | supports |  | supports | supports | supports |
| r26 | P129 | supports |  | supports | supports | supports |
| r26 | P130 | supports |  | supports | supports | supports |
| r26 | P131 | supports |  | supports | supports | supports |
