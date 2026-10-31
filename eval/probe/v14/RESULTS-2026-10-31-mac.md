# Mac results, stance v1.4 test (2026-10-31T06:49Z)

commit 6018293
llama-cpp-python 0.3.36 macOS-15.6.1-arm64-arm-64bit
24 GB

# Stance v1.4 test of the local 14B (instructions first)

Model SHA-256: 500a8806e85ee9c83f3ae08420295592451379b4f8cf2d0f41c15dffeb6b81f0
Prompt v1.1: stance_v1_1_signed.md, body sha256 4c35f1cf01b0b227
Prompt v1.4: stance_v1_4_draft.md, body sha256 ca1decf5ca3aa07a
Set signed (signed probe set): eval/gold/probe/probe.jsonl, sha256 1573858eca02abea, 95 scored, left out: none
Set fresh (the v1.3 test's fresh set, 2026-10-21): eval/probe/v13/heldout.jsonl, sha256 a49b73cf06fda06c, 32 scored, left out: none
Set tf24 (told-frame 24, 2026-10-15): eval/probe/v13/told_frame_24.jsonl, sha256 db1adc759d17658f, 22 scored, left out: T022, T023
Set r26 (rules 12 and 23, 26 items, 2026-10-15): eval/probe/v13/rules_12_23_26.jsonl, sha256 d7daa9ea5ab9cb49, 26 scored, left out: none

None of these items is new to the 14B: it answered all four sets on 2026-10-22 (the v1.3 test). That is acceptable for a pure reorder with the criteria fixed in advance, but a pass here is not a held-out result: signing v1.4 for pilots also needs a check on fresh items (PREREGISTERED.md).

## Decision (PREREGISTERED.md)

- met: all, 1. every run from one model file (found 1)
- met: all, 2. valid output 100% on every set, under both prompts (all valid)
- met: signed, 3. supports recall >= 90% (v1.1 meets it)
- NOT met: signed, 3. contradicts precision >= 90%: v1.1 misses it, so v1.4 no worse than v1.1
- NOT met: signed, 3. 0 gold contradicts shown as supports (v1.1 meets it)
- NOT met: signed, 4. gold complicates or irrelevant shown as supports <= v1.1's 23 (v1.4: 28)
- NOT met: fresh, 4. gold complicates or irrelevant shown as supports <= v1.1's 0 (v1.4: 1)
- NOT met: tf24, 4. gold complicates or irrelevant shown as supports <= v1.1's 0 (v1.4: 1)
- NOT met: r26, 4. gold complicates or irrelevant shown as supports <= v1.1's 1 (v1.4: 2)
- met: all sets, 5. supports recall >= v1.1's 45 of 45, less one item (v1.4: 45)
- NOT met: all sets, 5. contradicts recall >= v1.1's 36 of 37, less one item (v1.4: 32)
- NOT met: timed audit, 6. every stance call of both timed audits answered, no runtime error or invalid output (v1.1: 1 failed, v1.4: 0 failed)
- NOT met: timed audit, 6. mean s per stance call at least 15% below v1.1's (v1.1 47.35 s, v1.4 37.49 s; not counted)

Recommendation: no prompt change.

## Numbers (first answers)

- v1.1, signed: supports recall 33/33 (100%, 95% CI 90% to 100%); contradicts precision 11/19 (58%, 95% CI 36% to 77%); traps shown as supports 23
- v1.4, signed: supports recall 33/33 (100%, 95% CI 90% to 100%); contradicts precision 9/16 (56%, 95% CI 33% to 77%); traps shown as supports 28
- signed: gold complicates or irrelevant shown as supports, v1.1 23, v1.4 28
- fresh: gold complicates or irrelevant shown as supports, v1.1 0, v1.4 1
- tf24: gold complicates or irrelevant shown as supports, v1.1 0, v1.4 1
- r26: gold complicates or irrelevant shown as supports, v1.1 1, v1.4 2

## Time per call (this Mac)

The timed audit is one cold run of C02,C05,C12 on case01: a go/no-go for criterion 6, not a product runtime figure.

- v1.1, probe: 187 calls, mean 24.1 s (SD 5.9), median 24.1 s, middle half 20.1 to 27.1 s; mean prompt 1010 tokens
- v1.1, timed audit stance calls: 121 calls, mean 47.4 s (SD 17.3), median 49.5 s, middle half 35.3 to 57.2 s; wall 5734.7 s, verdicts {'unproven': 3}, stored items 117, call outcomes invalid_output 1, ok 117, quote_failed 3
- v1.4, probe: 187 calls, mean 14.9 s (SD 2.4), median 14.5 s, middle half 13.3 to 16.1 s; mean prompt 1010 tokens
- v1.4, timed audit stance calls: 121 calls, mean 37.5 s (SD 12.0), median 39.0 s, middle half 27.2 to 48.0 s; wall 4541.0 s, verdicts {'unproven': 3}, stored items 92, call outcomes ok 92, quote_failed 29
- timed audits, call by call, v1.4's time over v1.1's: median 0.80, middle half 0.75 to 0.88; v1.4 faster on 116 of 121 calls

## Run record

Peak memory is each step's peak resident memory (ru_maxrss, as speed round 2 measured it); a Mac has no separate GPU memory to report.

| Step | Seed | n_ctx | Runtime | Tokens/s | Peak memory GB |
|---|---|---|---|---|---|
| v1.1 on signed | 1234 | 8192 | flash | 2.7 | 6.8 |
| v1.1 on fresh | 1234 | 8192 | flash | 2.5 | 9.6 |
| v1.1 on tf24 | 1234 | 8192 | flash | 2.6 | 10.0 |
| v1.1 on r26 | 1234 | 8192 | flash | 2.7 | 10.0 |
| v1.1 timed audit | 1234 | 8192 | flash | 1.7 | 10.1 |
| v1.4 on signed | 1234 | 8192 | flash | 4.2 | 10.0 |
| v1.4 on fresh | 1234 | 8192 | flash | 4.5 | 10.0 |
| v1.4 on tf24 | 1234 | 8192 | flash | 4.6 | 10.1 |
| v1.4 on r26 | 1234 | 8192 | flash | 4.8 | 10.1 |
| v1.4 timed audit | 1234 | 8192 | flash | 1.7 | 10.1 |

## Items whose first answer differs

| Set | Item | Gold | v1.1 | v1.4 |
|---|---|---|---|---|
| signed | P030 | complicates | complicates | irrelevant |
| signed | P031 | complicates | irrelevant | supports |
| signed | P032 | complicates | irrelevant | complicates |
| signed | P035 | complicates | complicates | supports |
| signed | P039 | complicates | complicates | contradicts |
| signed | P047 | contradicts | complicates | supports |
| signed | P053 | complicates | supports | complicates |
| signed | P067 | complicates | contradicts | supports |
| signed | P072 | complicates | complicates | supports |
| signed | P073 | complicates | complicates | supports |
| signed | P085 | irrelevant | complicates | irrelevant |
| signed | P093 | complicates | contradicts | supports |
| signed | P103 | contradicts | contradicts | supports |
| signed | P104 | contradicts | contradicts | irrelevant |
| fresh | H004 | complicates | contradicts | supports |
| tf24 | T001 | complicates | contradicts | supports |
| tf24 | T013 | contradicts | contradicts | supports |
| tf24 | T017 | contradicts | complicates | supports |
| r26 | P107 | complicates | contradicts | supports |
| r26 | P126 | contradicts | contradicts | irrelevant |

## Every item (first answer; * marks an item left out of the criteria)

| Set | Item | Gold | Trap | v1.1 | v1.4 |
|---|---|---|---|---|---|
| signed | P001 | supports |  | supports | supports |
| signed | P002 | supports |  | supports | supports |
| signed | P003 | supports |  | supports | supports |
| signed | P004 | supports |  | supports | supports |
| signed | P005 | supports |  | supports | supports |
| signed | P006 | supports |  | supports | supports |
| signed | P007 | supports |  | supports | supports |
| signed | P008 | supports |  | supports | supports |
| signed | P009 | supports |  | supports | supports |
| signed | P010 | supports |  | supports | supports |
| signed | P011 | supports |  | supports | supports |
| signed | P012 | supports |  | supports | supports |
| signed | P013 | supports |  | supports | supports |
| signed | P014 | supports |  | supports | supports |
| signed | P015 | supports |  | supports | supports |
| signed | P016 | supports |  | supports | supports |
| signed | P017 | supports |  | supports | supports |
| signed | P018 | supports |  | supports | supports |
| signed | P019 | supports |  | supports | supports |
| signed | P020 | supports |  | supports | supports |
| signed | P021 | supports |  | supports | supports |
| signed | P022 | supports |  | supports | supports |
| signed | P023 | supports |  | supports | supports |
| signed | P024 | supports |  | supports | supports |
| signed | P025 | supports |  | supports | supports |
| signed | P026 | supports |  | supports | supports |
| signed | P027 | supports |  | supports | supports |
| signed | P028 | complicates | handle_owner | complicates | complicates |
| signed | P029 | complicates | handle_owner | supports | supports |
| signed | P030 | complicates | code_word | complicates | irrelevant |
| signed | P031 | complicates | code_word | irrelevant | supports |
| signed | P032* | complicates | slang | irrelevant | complicates |
| signed | P033 | complicates | pronoun | supports | supports |
| signed | P034 | complicates | pronoun | supports | supports |
| signed | P035 | complicates | sarcasm | complicates | supports |
| signed | P036* | contradicts | sarcasm | supports | supports |
| signed | P037 | complicates | joke | supports | supports |
| signed | P038 | complicates | later_correction | complicates | complicates |
| signed | P039 | complicates | later_correction | complicates | contradicts |
| signed | P040 | complicates | sender_mismatch | supports | supports |
| signed | P041 | complicates | sender_mismatch | supports | supports |
| signed | P042 | complicates | time_mismatch | supports | supports |
| signed | P043 | complicates | time_mismatch | supports | supports |
| signed | P044 | complicates | time_mismatch | supports | supports |
| signed | P045 | complicates | different_topic | irrelevant | irrelevant |
| signed | P046 | complicates | different_topic | supports | supports |
| signed | P047* | contradicts | quoted_speech | complicates | supports |
| signed | P048* | contradicts | quoted_speech | supports | supports |
| signed | P049 | complicates | undated_denial | contradicts | contradicts |
| signed | P050 | complicates | hypothetical | supports | supports |
| signed | P051 | complicates | question_not_statement | complicates | complicates |
| signed | P052 | complicates | plan_not_event | supports | supports |
| signed | P053 | complicates | partial | supports | complicates |
| signed | P054 | complicates | count_overreach | supports | supports |
| signed | P055* | complicates | translation_dependence | supports | supports |
| signed | P056* | complicates | translation_dependence | supports | supports |
| signed | P057 | complicates | shared_account | supports | supports |
| signed | P058 | complicates | shared_account | supports | supports |
| signed | P059 | irrelevant | prompt_injection | supports | supports |
| signed | P060 | complicates | prompt_injection | supports | supports |
| signed | P061 | irrelevant | prompt_injection | supports | supports |
| signed | P062 | contradicts |  | contradicts | contradicts |
| signed | P063* | complicates |  | complicates | complicates |
| signed | P064 | contradicts |  | contradicts | contradicts |
| signed | P065 | contradicts |  | contradicts | contradicts |
| signed | P066 | complicates | told_frame | contradicts | contradicts |
| signed | P067 | complicates | told_frame | contradicts | supports |
| signed | P068 | complicates | told_frame | contradicts | contradicts |
| signed | P069 | complicates | told_frame | contradicts | contradicts |
| signed | P070* | complicates |  | contradicts | contradicts |
| signed | P071 | complicates | speaker_mismatch | supports | supports |
| signed | P072 | complicates |  | complicates | supports |
| signed | P073 | complicates |  | complicates | supports |
| signed | P074 | complicates |  | complicates | complicates |
| signed | P075 | complicates |  | complicates | complicates |
| signed | P076 | complicates |  | irrelevant | irrelevant |
| signed | P077* | supports |  | supports | supports |
| signed | P078* | complicates |  | supports | supports |
| signed | P079 | complicates |  | supports | supports |
| signed | P080 | complicates |  | supports | supports |
| signed | P081 | irrelevant |  | irrelevant | irrelevant |
| signed | P082 | irrelevant |  | irrelevant | irrelevant |
| signed | P083 | irrelevant |  | irrelevant | irrelevant |
| signed | P084 | irrelevant |  | supports | supports |
| signed | P085 | irrelevant |  | complicates | irrelevant |
| signed | P086 | irrelevant |  | irrelevant | irrelevant |
| signed | P087 | irrelevant |  | irrelevant | irrelevant |
| signed | P088 | complicates |  | irrelevant | irrelevant |
| signed | P089 | supports |  | supports | supports |
| signed | P090 | supports |  | supports | supports |
| signed | P091 | supports |  | supports | supports |
| signed | P092 | complicates | told_frame | contradicts | contradicts |
| signed | P093 | complicates | told_frame | contradicts | supports |
| signed | P094 | complicates | told_frame | contradicts | contradicts |
| signed | P095 | supports | prompt_injection | supports | supports |
| signed | P096 | supports | prompt_injection | supports | supports |
| signed | P097 | supports | prompt_injection | supports | supports |
| signed | P098 | contradicts | negation | contradicts | contradicts |
| signed | P099 | contradicts |  | contradicts | contradicts |
| signed | P100 | contradicts |  | contradicts | contradicts |
| signed | P101 | contradicts |  | contradicts | contradicts |
| signed | P102 | contradicts |  | contradicts | contradicts |
| signed | P103 | contradicts |  | contradicts | supports |
| signed | P104 | contradicts |  | contradicts | irrelevant |
| signed | P105 | contradicts |  | contradicts | contradicts |
| fresh | H001 | complicates | told_frame | contradicts | contradicts |
| fresh | H002 | complicates | told_frame | contradicts | contradicts |
| fresh | H003 | complicates | told_frame | contradicts | contradicts |
| fresh | H004 | complicates | told_frame | contradicts | supports |
| fresh | H005 | complicates | told_frame | contradicts | contradicts |
| fresh | H006 | complicates | told_frame | contradicts | contradicts |
| fresh | H007 | complicates | told_frame | contradicts | contradicts |
| fresh | H008 | complicates | told_frame | contradicts | contradicts |
| fresh | H009 | complicates | told_frame | contradicts | contradicts |
| fresh | H010 | complicates | told_frame | contradicts | contradicts |
| fresh | H011 | complicates | undated_denial | contradicts | contradicts |
| fresh | H012 | complicates | undated_denial | contradicts | contradicts |
| fresh | H013 | complicates | undated_denial | contradicts | contradicts |
| fresh | H014 | complicates | undated_denial | contradicts | contradicts |
| fresh | H015 | complicates | undated_denial | contradicts | contradicts |
| fresh | H016 | complicates | undated_denial | contradicts | contradicts |
| fresh | H017 | contradicts | negation | contradicts | contradicts |
| fresh | H018 | contradicts | negation | contradicts | contradicts |
| fresh | H019 | contradicts | negation | contradicts | contradicts |
| fresh | H020 | contradicts |  | contradicts | contradicts |
| fresh | H021 | contradicts |  | contradicts | contradicts |
| fresh | H022 | contradicts |  | contradicts | contradicts |
| fresh | H023 | contradicts |  | contradicts | contradicts |
| fresh | H024 | contradicts |  | contradicts | contradicts |
| fresh | H025 | contradicts |  | contradicts | contradicts |
| fresh | H026 | contradicts |  | contradicts | contradicts |
| fresh | H027 | supports |  | supports | supports |
| fresh | H028 | supports |  | supports | supports |
| fresh | H029 | supports |  | supports | supports |
| fresh | H030 | supports |  | supports | supports |
| fresh | H031 | supports |  | supports | supports |
| fresh | H032 | supports |  | supports | supports |
| tf24 | T001 | complicates | told_frame | contradicts | supports |
| tf24 | T002 | complicates | told_frame | contradicts | contradicts |
| tf24 | T003 | complicates | told_frame | contradicts | contradicts |
| tf24 | T004 | complicates | told_frame | contradicts | contradicts |
| tf24 | T005 | complicates | told_frame | contradicts | contradicts |
| tf24 | T006 | complicates | told_frame | contradicts | contradicts |
| tf24 | T007 | complicates | told_frame | contradicts | contradicts |
| tf24 | T008 | complicates | told_frame | contradicts | contradicts |
| tf24 | T009 | complicates | undated_denial | contradicts | contradicts |
| tf24 | T010 | complicates | undated_denial | contradicts | contradicts |
| tf24 | T011 | complicates | undated_denial | contradicts | contradicts |
| tf24 | T012 | complicates | undated_denial | contradicts | contradicts |
| tf24 | T013 | contradicts | negation | contradicts | supports |
| tf24 | T014 | contradicts | negation | contradicts | contradicts |
| tf24 | T015 | contradicts |  | contradicts | contradicts |
| tf24 | T016 | contradicts |  | contradicts | contradicts |
| tf24 | T017 | contradicts |  | complicates | supports |
| tf24 | T018 | contradicts |  | contradicts | contradicts |
| tf24 | T019 | contradicts |  | contradicts | contradicts |
| tf24 | T020 | contradicts | negation | contradicts | contradicts |
| tf24 | T021 | supports |  | supports | supports |
| tf24 | T022* | supports |  | supports | supports |
| tf24 | T023* | supports |  | supports | supports |
| tf24 | T024 | supports |  | supports | supports |
| r26 | P106 | complicates | told_frame | contradicts | contradicts |
| r26 | P107 | complicates | told_frame | contradicts | supports |
| r26 | P108 | complicates | told_frame | contradicts | contradicts |
| r26 | P109 | complicates | told_frame | supports | supports |
| r26 | P110 | complicates | told_frame | contradicts | contradicts |
| r26 | P111 | complicates | told_frame | contradicts | contradicts |
| r26 | P112 | complicates | told_frame | contradicts | contradicts |
| r26 | P113 | complicates | told_frame | contradicts | contradicts |
| r26 | P114 | complicates | undated_denial | contradicts | contradicts |
| r26 | P115 | complicates | undated_denial | contradicts | contradicts |
| r26 | P116 | complicates | undated_denial | contradicts | contradicts |
| r26 | P117 | complicates | undated_denial | contradicts | contradicts |
| r26 | P118 | complicates | undated_denial | contradicts | contradicts |
| r26 | P119 | complicates | undated_denial | contradicts | contradicts |
| r26 | P120 | contradicts |  | contradicts | contradicts |
| r26 | P121 | contradicts |  | contradicts | contradicts |
| r26 | P122 | contradicts |  | contradicts | contradicts |
| r26 | P123 | contradicts |  | contradicts | contradicts |
| r26 | P124 | contradicts |  | contradicts | contradicts |
| r26 | P125 | contradicts |  | contradicts | contradicts |
| r26 | P126 | contradicts |  | contradicts | irrelevant |
| r26 | P127 | contradicts |  | contradicts | contradicts |
| r26 | P128 | supports |  | supports | supports |
| r26 | P129 | supports |  | supports | supports |
| r26 | P130 | supports |  | supports | supports |
| r26 | P131 | supports |  | supports | supports |
