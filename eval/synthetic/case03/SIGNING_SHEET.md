# case03 signing sheet: DRAFT key and assumption sheet

About fifteen minutes. Each claim: the draft verdict, the one-line reason, and the
assumption rows the pipeline runs on. Tick or correct each line; the full reasoning and
every cited row are in `ANSWER_KEY_DRAFT.md`. Nothing here is gold until a human copies
the approved lines into `eval/gold/case03/` (`gold.jsonl`, `assumptions.jsonl`) with
`labeled_by` set to the approver.

Read the affidavit first (`affidavit_draft.md`, 18 paragraphs). Its definitions:
TARGET PHONE = Item 1; ORLOV = SUBJECT-1 = PASHA; DIAZ = SUBJECT-2; CS-1 used
+17185550190; the SEARCH was on Saturday, March 14, 2026.

What to decide:

1. Is each verdict right? Groups 1 and 2 are unproven because the counter-evidence
   complicates the claim without ruling it out (labeling rule 2). Say if any should be
   contradicted instead (C04 and C13 are the closest calls).
2. Does each counter-record really undercut its claim, and is it fair for group 1 that a
   code direction should find it?
3. Are the assumption rows the right reading of the claim, especially for group 4?
   `expected_check` is what the deterministic check should find; a test runs the checks
   against it. A dash means no check exists, so only expert review covers it.

| Claim | Group | Draft verdict | Reason in one line | Agree? |
|---|---|---|---|---|
| C01 | 3 | **supported** | Contact 'Pasha' with +17185550111 is on Item 2. | [ ] |
| C02 | 3 | **supported** | Nine Telegram rows on Item 2, Mar 1-7 local (two are Mar 8 in UTC). | [ ] |
| C03 | 2 | **unproven** | Kirill wrote from Item 1 the evening before: 'usin pasha fone til sunday'. | [ ] |
| C04 | 1 | **unproven** | The outgoing 2-min call was 7:40 p.m. (prints 11:40 PM UTC+0); 11:39 p.m. is incoming. | [ ] |
| C05 | 3 | **supported** | Observed; Kemal's lost phone and the 'never used his phone' denial are decoys. | [ ] |
| C06 | 4 | **contradicted** | PASHA is ORLOV, but DIAZ sent the message (both phones). | [ ] |
| C07 | 4 | **supported** | Item 1 sent it to +17185550190 on Mar 15, the day after the SEARCH. | [ ] |
| C08 | 4 | **contradicted** | Two days later is Mar 17; it was sent Mar 18. | [ ] |
| C09 | 1 | **unproven** | Item 1's WhatsApp was quiet everywhere; ORLOV wrote that the app was crashing. | [ ] |
| C10 | 2 | **unproven** | Translit messages say the boxes are their mother's dishes. | [ ] |
| C11 | 1 | **unproven** | The shop account's other user names himself: 'hi its kemal from the shop'. | [ ] |
| C12 | 3 | **supported** | Friday Mar 20, 'sunday' is Mar 22; the other Sunday and Varick are decoys. | [ ] |
| C13 | 1 | **unproven** | DIAZ agreed on WhatsApp, then withdrew on Telegram that night. | [ ] |
| C14 | 3 | **supported** | The 2:04 p.m. call, 370 s; the 10:05 a.m. one that prints 2:05 PM is a decoy. | [ ] |
| C15 | 2 | **unproven** | 'the paper' fits the Civic's title ('pink slip', 'title') in DIAZ's other thread. | [ ] |
| C16 | 1 | **unproven** | DIAZ's own phone saves +16465550170 as 'Eddie P'. | [ ] |
| C17 | 1 | **unproven** | Item 2 sent 'its tito. using ruben's phone this weekend' the evening before. | [ ] |

## Assumption rows

### C01 (draft supported)

> Item 2 contains a contact saved as "Pasha" with the number +1 (718) 555-0111.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `contact_entry` | yes | device_ids: dev:item2<br>quoted_text: Pasha<br>account_ids: acct:item2:SMS:+17185550111 | pass | The contact row is observed on Item 2; 'Pasha Tires' is another entry. |

Arsh: [ ] agree  [ ] change ______  Note:

### C02 (draft supported)

> Between March 1 and March 7, 2026, Item 2 recorded 9 Telegram messages exchanged between DIAZ and ORLOV.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:diaz, person:orlov<br>channels: Telegram<br>expected_count: 9<br>count_op: eq<br>window: "Between March 1 and March 7, 2026" (America/New_York, local wall clock) | pass | Nine rows on Item 2, local dates; two of them are on Mar 8 in UTC. |

Arsh: [ ] agree  [ ] change ______  Note:

### C03 (draft unproven)

> On March 7, 2026, ORLOV texted DIAZ "can u open the bay early tmrw, got 3 to drop".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: can u open the bay early tmrw, got 3 to drop<br>person_ids: person:orlov<br>channels: SMS | pass | Outgoing from Item 1's SMS account (stipulated ORLOV's). |
| 2 | `record_time` | yes | quoted_text: can u open the bay early tmrw, got 3 to drop<br>person_ids: person:orlov, person:diaz<br>channels: SMS<br>window: "On March 7, 2026" (America/New_York, local wall clock) | pass | 10:15 a.m. EST Mar 7. |

Gap: That ORLOV himself, not another person holding Item 1, wrote the message is the device-owner stipulation, not an assumption here; the counter-evidence disputes it.

Arsh: [ ] agree  [ ] change ______  Note:

### C04 (draft unproven)

> At about 11:40 p.m. on March 9, 2026, ORLOV placed a call of about two minutes from Item 1 to DIAZ.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `record_time` | yes | person_ids: person:orlov, person:diaz<br>channels: call<br>device_ids: dev:item1<br>duration_s: 90, 150<br>window: "At about 11:40 p.m. on March 9, 2026" (America/New_York, local wall clock) | pass | Passes on the 11:39 p.m. call, which is DIAZ calling ORLOV (112 s). The outgoing two-minute call prints 11:40:12 PM(UTC+0) and was at 7:40 p.m. local. |

Gap: No template says who placed a call, so 'ORLOV placed' is untested by any check; the time check matches calls by their parties either way.

Gap: 'About' is read as eight minutes either side of 11:40 p.m. and 'about two minutes' as 90 to 150 s.

Arsh: [ ] agree  [ ] change ______  Note:

### C05 (draft supported)

> On March 11, 2026, ORLOV texted DIAZ "got 4 more, all hondas. same price?".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: got 4 more, all hondas. same price?<br>person_ids: person:orlov<br>channels: SMS | pass | Outgoing on Item 1. |
| 2 | `record_time` | yes | quoted_text: got 4 more, all hondas. same price?<br>person_ids: person:orlov, person:diaz<br>channels: SMS<br>window: "On March 11, 2026" (America/New_York, local wall clock) | pass | 3:42 p.m. EDT Mar 11, printed 7:42 PM UTC+0. |

Arsh: [ ] agree  [ ] change ______  Note:

### C06 (draft contradicted)

> On March 12, 2026, PASHA told SUBJECT-2 on Telegram "need the lift friday after 6".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: need the lift friday after 6<br>person_ids: person:orlov<br>channels: Telegram | fail | PASHA is ORLOV (paragraph 2). Both copies are sent by DIAZ's Telegram account 7101002. |
| 2 | `record_time` | yes | quoted_text: need the lift friday after 6<br>person_ids: person:orlov, person:diaz<br>channels: Telegram<br>window: "On March 12, 2026" (America/New_York, local wall clock) | pass | 5:05 p.m. EDT Mar 12. SUBJECT-2 is DIAZ. |

Arsh: [ ] agree  [ ] change ______  Note:

### C07 (draft supported)

> On the day after the SEARCH, the TARGET PHONE sent CS-1 a text message reading "not now. after the weekend".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: not now. after the weekend<br>account_ids: acct:item1:SMS:+17185550111<br>device_ids: dev:item1<br>channels: SMS | pass | The TARGET PHONE is Item 1 (paragraph 2): its own SMS account sent it. |
| 2 | `record_time` | yes | quoted_text: not now. after the weekend<br>account_ids: acct:item1:SMS:+17185550190<br>device_ids: dev:item1<br>channels: SMS<br>window: "On the day after the SEARCH (March 15, 2026)" (America/New_York, local wall clock) | pass | The SEARCH was Mar 14 (paragraph 4); CS-1 used +17185550190 (paragraph 3). 11:26 a.m. EDT Mar 15. |

Arsh: [ ] agree  [ ] change ______  Note:

### C08 (draft contradicted)

> Two days later, SUBJECT-2 texted the TARGET PHONE "all quiet here, dont come by".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: all quiet here, dont come by<br>person_ids: person:diaz<br>channels: SMS | pass | SUBJECT-2 is DIAZ (paragraph 2): outgoing on Item 2. |
| 2 | `record_time` | yes | quoted_text: all quiet here, dont come by<br>person_ids: person:diaz<br>device_ids: dev:item1<br>channels: SMS<br>window: "Two days later (March 17, 2026)" (America/New_York, local wall clock) | fail | Two days after Mar 15 (C07) is Mar 17. The TARGET PHONE received it at 9:10 a.m. EDT on Mar 18. |

Gap: 'Two days later' is read from the sentence before it (C07). Read from the SEARCH it would be Mar 16; the message is outside both days.

Arsh: [ ] agree  [ ] change ______  Note:

### C09 (draft unproven)

> After the SEARCH, ORLOV stopped messaging DIAZ on WhatsApp from March 15 through March 18, 2026, in order to avoid detection by law enforcement.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `no_contact` | yes | person_ids: person:orlov, person:diaz<br>channels: WhatsApp<br>window: "from March 15 through March 18, 2026" (America/New_York, local wall clock) | inconclusive | No rows on either phone, but both reports are curated, so the absence cannot be shown complete. |
| 2 | `event` | yes | person_ids: person:orlov, person:diaz<br>channels: WhatsApp<br>window: "from March 15 through March 18, 2026" (America/New_York, local wall clock) | - | That ORLOV stopped, and why, is for a reader; Item 1's WhatsApp was quiet in every conversation and he wrote that the app was crashing. |

Gap: 'After the SEARCH' (Mar 14) only fixes the start; the window carries it.

Arsh: [ ] agree  [ ] change ______  Note:

### C10 (draft unproven)

> On March 17, 2026, ORLOV wrote to his brother on Telegram, in Russian, "коробки у меня, завтра отвезу" (in English: the boxes are with me, I will take them tomorrow); the boxes in that message were the stolen catalytic converters.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: коробки у меня, завтра отвезу<br>person_ids: person:orlov<br>channels: Telegram | pass | Outgoing on Item 1 to Misha. |
| 2 | `record_time` | yes | quoted_text: коробки у меня, завтра отвезу<br>person_ids: person:orlov<br>channels: Telegram<br>window: "On March 17, 2026" (America/New_York, local wall clock) | pass | 6:40 p.m. EDT Mar 17. |
| 3 | `meaning` | yes | quoted_text: коробки у меня, завтра отвезу<br>channels: Telegram | - | Whether the boxes are the converters; the thread says they are dishes. |

Gap: That the other party is ORLOV's brother is not tested (no template for kin).

Arsh: [ ] agree  [ ] change ______  Note:

### C11 (draft unproven)

> On March 19, 2026, ORLOV, using the Instagram account orlov.detailing, told the Instagram user jr.parts.nyc "come thru after 9, bring cash".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: come thru after 9, bring cash<br>person_ids: person:orlov<br>channels: Instagram | pass | orlov.detailing is an owner account of Item 1 (stipulated ORLOV's). |
| 2 | `record_time` | yes | quoted_text: come thru after 9, bring cash<br>person_ids: person:orlov<br>account_ids: acct:item1:Instagram:jr.parts.nyc<br>channels: Instagram<br>window: "On March 19, 2026" (America/New_York, local wall clock) | pass | 6:42 p.m. EDT Mar 19. |
| 3 | `authorship` | yes | quoted_text: come thru after 9, bring cash<br>person_ids: person:orlov<br>account_ids: acct:item1:Instagram:orlov.detailing<br>channels: Instagram | - | The shop account has another user, who names himself on Mar 18. |

Arsh: [ ] agree  [ ] change ______  Note:

### C12 (draft supported)

> On Friday, March 20, 2026, DIAZ wrote to ORLOV on Telegram "lot on varick, sunday 9pm", setting a meeting for Sunday, March 22, 2026.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: lot on varick, sunday 9pm<br>person_ids: person:diaz<br>channels: Telegram | pass | Outgoing on Item 2. |
| 2 | `record_time` | yes | quoted_text: lot on varick, sunday 9pm<br>person_ids: person:diaz, person:orlov<br>channels: Telegram<br>window: "On Friday, March 20, 2026" (America/New_York, local wall clock) | pass | 3:15 p.m. EDT Mar 20. |
| 3 | `weekday_date` | yes | quoted_text: lot on varick, sunday 9pm<br>channels: Telegram<br>window: "Sunday, March 22, 2026" (America/New_York, local wall clock) | pass | The next Sunday after Friday Mar 20 is Mar 22. |

Arsh: [ ] agree  [ ] change ______  Note:

### C13 (draft unproven)

> On March 21, 2026, over WhatsApp, DIAZ agreed to ORLOV's request to hold "the 6 pieces" at his shop until Tuesday, March 24, 2026.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: can u hold the 6 pieces at ur shop til tuesday<br>person_ids: person:orlov<br>channels: WhatsApp | pass | ORLOV's request, outgoing on Item 1. |
| 2 | `sender` | yes | quoted_text: ok bring them by after 8<br>person_ids: person:diaz<br>channels: WhatsApp | pass | DIAZ's reply, outgoing on Item 2. |
| 3 | `record_time` | yes | quoted_text: ok bring them by after 8<br>person_ids: person:diaz, person:orlov<br>channels: WhatsApp<br>window: "On March 21, 2026" (America/New_York, local wall clock) | pass | 1:12 p.m. EDT Mar 21. |
| 4 | `weekday_date` | yes | quoted_text: can u hold the 6 pieces at ur shop til tuesday<br>channels: WhatsApp<br>window: "Tuesday, March 24, 2026" (America/New_York, local wall clock) | pass | The next Tuesday after Saturday Mar 21 is Mar 24. |
| 5 | `meaning` | yes | quoted_text: ok bring them by after 8<br>channels: WhatsApp | - | 'ok bring them by after 8' as agreement to hold the pieces. |
| 6 | `event` | yes | person_ids: person:orlov, person:diaz<br>channels: WhatsApp<br>window: "On March 21, 2026" (America/New_York, local wall clock) | - | That the agreement was made and stood; it was withdrawn on Telegram that night. |

Gap: 'At his shop' is not tested (no template for a place).

Arsh: [ ] agree  [ ] change ______  Note:

### C14 (draft supported)

> At about 2:05 p.m. on March 23, 2026, DIAZ called ORLOV; the call lasted about six minutes.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `record_time` | yes | person_ids: person:diaz, person:orlov<br>channels: call<br>duration_s: 330, 390<br>window: "At about 2:05 p.m. on March 23, 2026" (America/New_York, local wall clock) | pass | The 2:04:30 p.m. call, 370 s, on both phones. |

Gap: No template says who placed a call; Item 2 logs it as outgoing, as the claim says.

Gap: 'About' is read as eight minutes either side; 'about six minutes' as 330 to 390 s.

Arsh: [ ] agree  [ ] change ______  Note:

### C15 (draft unproven)

> On March 24, 2026, DIAZ texted ORLOV "bring the paper tmrw", a demand that ORLOV bring cash payment for stolen catalytic converters.

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: bring the paper tmrw<br>person_ids: person:diaz<br>channels: SMS | pass | Outgoing on Item 2. |
| 2 | `record_time` | yes | quoted_text: bring the paper tmrw<br>person_ids: person:diaz, person:orlov<br>channels: SMS<br>window: "On March 24, 2026" (America/New_York, local wall clock) | pass | 2:30 p.m. EDT Mar 24. |
| 3 | `meaning` | yes | quoted_text: bring the paper tmrw<br>channels: SMS | - | 'the paper' as cash payment; DIAZ's thread with a buyer makes it the Civic's title. |

Arsh: [ ] agree  [ ] change ______  Note:

### C16 (draft unproven)

> On March 25, 2026, DIAZ, using the phone number +1 (646) 555-0170, texted ORLOV "the bushwick guy wants 6 by friday".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: the bushwick guy wants 6 by friday<br>account_ids: acct:item1:SMS:+16465550170<br>channels: SMS | pass | Incoming on Item 1 from +16465550170. |
| 2 | `record_time` | yes | quoted_text: the bushwick guy wants 6 by friday<br>person_ids: person:orlov<br>account_ids: acct:item1:SMS:+16465550170<br>channels: SMS<br>window: "On March 25, 2026" (America/New_York, local wall clock) | pass | 4:15 p.m. EDT Mar 25. |
| 3 | `authorship` | yes | quoted_text: the bushwick guy wants 6 by friday<br>person_ids: person:diaz<br>account_ids: acct:item1:SMS:+16465550170<br>channels: SMS | - | Who used +16465550170; DIAZ's own phone saves it as 'Eddie P'. |

Arsh: [ ] agree  [ ] change ______  Note:

### C17 (draft unproven)

> On March 28, 2026, DIAZ texted ORLOV "keep ur phone on tonight, might need u at 10".

| # | Template | Core | Parameters | Check | Why |
|---|---|---|---|---|---|
| 1 | `sender` | yes | quoted_text: keep ur phone on tonight, might need u at 10<br>person_ids: person:diaz<br>channels: SMS | pass | Outgoing on Item 2 (stipulated DIAZ's). |
| 2 | `record_time` | yes | quoted_text: keep ur phone on tonight, might need u at 10<br>person_ids: person:diaz, person:orlov<br>channels: SMS<br>window: "On March 28, 2026" (America/New_York, local wall clock) | pass | 4:10 p.m. EDT Mar 28. |

Gap: That DIAZ himself, not another person holding Item 2, wrote the message is the device-owner stipulation, not an assumption here; the counter-evidence disputes it.

Arsh: [ ] agree  [ ] change ______  Note:

Signed: ____________________  Date: __________
