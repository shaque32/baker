# case04 signing sheet: DRAFT key and assumption sheet

About twenty minutes. Each claim: the draft verdict, its wording and hazard, the
one-line reason, and the assumption rows the pipeline runs on. Tick or correct each
line; the full reasoning and every cited row are in `ANSWER_KEY_DRAFT.md`. Nothing here
is gold until a human copies the approved lines into `eval/gold/case04/` (`gold.jsonl`,
`assumptions.jsonl`) with `labeled_by` set to the approver.

Read the affidavit first (`affidavit_draft.md`, 18 paragraphs). Its definitions:
HAL = SUBJECT-1 = HALLORAN (Item 1); the TARGET PHONE = Item 2 = FERRO = SUBJECT-2;
DEZ = the DRIVER = SUBJECT-3 = OKAFOR (Item 3); CW-1 used +17735550187; the PREPAID is
+13125550199; the BUYER is kipflips.chi; the SEARCH was on Thursday, March 26, 2026.

What to decide:

1. Is each verdict right? Absence claims are never supported on a curated report
   (reading rule 7); a meaning or role is supported only where the conversation fixes it
   (rule 8). C20, C24 and C39 are the closest calls.
2. Is each hazard a fair wrong reading, and does the sheet name only the right person,
   account, phone and window?
3. Are the assumption rows the right reading of the claim? `expected_check` is what the
   deterministic check should find; a test runs the checks against it. A dash means no
   check exists, so only expert review covers that row.

## Counts

### Claim type x draft verdict

| Type | supported | contradicted | unproven | Total |
|---|---|---|---|---|
| communication | 4 | 1 | 1 | 6 |
| identity | 4 | 1 | 1 | 6 |
| timing | 4 | 1 | 1 | 6 |
| content_meaning | 3 | 1 | 2 | 6 |
| count | 3 | 2 | 1 | 6 |
| absence | 0 | 3 | 3 | 6 |
| role | 2 | 2 | 2 | 6 |
| event | 4 | 1 | 1 | 6 |
| **all** | **24** | **12** | **12** | **48** |

### Claim type x wording

| Type | plain | affidavit |
|---|---|---|
| communication | 3 | 3 |
| identity | 3 | 3 |
| timing | 3 | 3 |
| content_meaning | 3 | 3 |
| count | 3 | 3 |
| absence | 3 | 3 |
| role | 3 | 3 |
| event | 3 | 3 |
| **all** | **24** | **24** |

### Wording x draft verdict

| Wording | supported | contradicted | unproven |
|---|---|---|---|
| plain | 12 | 7 | 5 |
| affidavit | 12 | 5 | 7 |

### Hazards by kind

| Hazard | What the wrong reading is | Claims | supported | contradicted | unproven |
|---|---|---|---|---|---|
| same_name | a second person with the same first name or nickname | 9 | 3 | 3 | 3 |
| second_number | a second number or account for the same person | 9 | 6 | 2 | 1 |
| second_phone | a second phone that could be meant | 6 | 3 | 2 | 1 |
| near_window | a near-miss window: UTC against local time across midnight, the DST change, an adjacent day, or Item 3's fixed UTC-6 print | 11 | 6 | 3 | 2 |
| contact_name | one contact name saved on two phones for two people | 3 | 1 | 0 | 2 |
| similar_quote | similar words in another thread | 8 | 4 | 2 | 2 |
| none | no wrong reading planted | 2 | 1 | 0 | 1 |

Claims with a planted wrong reading: 46 of 48.

### Claims without a sheet

None: every claim has rows in `draft_assumptions.jsonl`.

### Claims with no checkable core row

Their only core rows are ones no deterministic check tests, so only expert review
covers them:

- C39 (role)
- C42 (role)

## Claims

| Claim | Type | Wording | Hazard | Draft verdict | Reason in one line | Agree? |
|---|---|---|---|---|---|---|
| C01 | communication | plain | near_window | **supported** | Sent 8:12 p.m. CST Feb 18; Item 1 prints Feb 19 (UTC+0). | [ ] |
| C02 | communication | plain | none | **supported** | Observed on Items 2 and 3, Mar 4. | [ ] |
| C03 | communication | plain | same_name | **contradicted** | Sent by Item 2's 'Dez' (FERRO's cousin, +17735550164), not OKAFOR. | [ ] |
| C04 | communication | affidavit | second_number | **supported** | The PREPAID's text on Item 3, 7:15 p.m. Mar 6. | [ ] |
| C05 | communication | affidavit | second_phone | **supported** | Item 2 (the TARGET PHONE) received it at 1:47 a.m. CST Mar 8. | [ ] |
| C06 | communication | affidavit | similar_quote | **unproven** | No such text anywhere; the foreman got 'stay off the roof till tuesday'. | [ ] |
| C07 | identity | plain | contact_name | **supported** | Item 1's 'Rocco' holds +17735550187; Item 3's 'Rocco' is another number. | [ ] |
| C08 | identity | plain | second_number | **supported** | Item 2's 'Hal 2' holds +13125550199. | [ ] |
| C09 | identity | plain | second_number | **unproven** | Item 3's 'Hal' holds 0141; 0199 is saved as 'H'. Not shown (contact lists edit). | [ ] |
| C10 | identity | affidavit | same_name | **supported** | One Telegram id, 8204103, renamed 'dez' -> 'D.O.' on Mar 15. | [ ] |
| C11 | identity | affidavit | second_phone | **supported** | Item 2's 'Desmond O' holds +17735550176. | [ ] |
| C12 | identity | affidavit | second_number | **contradicted** | kip.flips.chi and kipflips.chi are two accounts. | [ ] |
| C13 | timing | plain | near_window | **supported** | 3:21 a.m. CDT, 245 s; Item 3 prints 2:21 AM(UTC-6). | [ ] |
| C14 | timing | plain | near_window | **supported** | 10:41 p.m. CDT, 58 s; the 9:41 p.m. call is a decoy. | [ ] |
| C15 | timing | plain | near_window | **contradicted** | Sent 7:15 p.m. Mar 18; 12:15 AM is the printed UTC value. | [ ] |
| C16 | timing | affidavit | second_number | **supported** | 10:58 p.m., 165 s, to the PREPAID (Item 3). | [ ] |
| C17 | timing | affidavit | near_window | **supported** | 11:46 p.m. Mar 25; Item 1 prints Mar 26. | [ ] |
| C18 | timing | affidavit | contact_name | **unproven** | No CW-1 call; the 10:36 p.m. call is to Item 3's 'Rocco' (Vitale). | [ ] |
| C19 | content_meaning | plain | similar_quote | **supported** | 'the copper ones?' / 'ya the copper, all 9' fix the meaning. | [ ] |
| C20 | content_meaning | plain | same_name | **unproven** | Observed; 'heavy ones' is not fixed (and two generators, not three). | [ ] |
| C21 | content_meaning | plain | similar_quote | **contradicted** | FERRO sent it, not OKAFOR. | [ ] |
| C22 | content_meaning | affidavit | similar_quote | **supported** | Mar 8: 'wrap the spools in the moving blankets' fixes 'blankets'. | [ ] |
| C23 | content_meaning | affidavit | second_number | **supported** | 'lot is 4 spools ...' and '1800 works' fix '1.8'. | [ ] |
| C24 | content_meaning | affidavit | same_name | **unproven** | Two Owens on Item 2; 'the stuff' not fixed. | [ ] |
| C25 | count | plain | near_window | **supported** | 8 on Chicago dates; printed dates give 9. | [ ] |
| C26 | count | plain | second_phone | **supported** | 6 on Item 3; Item 1 has 7. | [ ] |
| C27 | count | plain | near_window | **contradicted** | 5 on Mar 21 local; a UTC day gives 3. | [ ] |
| C28 | count | affidavit | second_number | **supported** | 11 PREPAID-DRIVER texts Mar 2-6 on Item 3. | [ ] |
| C29 | count | affidavit | second_phone | **contradicted** | 6 on Item 2; Item 1 shows 4. | [ ] |
| C30 | count | affidavit | near_window | **unproven** | 9 in 11 p.m.-3 a.m. (three hours, DST); 12 only if the jump is forgotten. | [ ] |
| C31 | absence | plain | near_window | **contradicted** | 9:30 p.m. CDT Mar 14 text; Item 1 prints Mar 15. | [ ] |
| C32 | absence | plain | second_number | **contradicted** | The PREPAID wrote to FERRO on Mar 28. | [ ] |
| C33 | absence | plain | contact_name | **unproven** | No CW-1 record; Item 3's 'Rocco' is Vitale. Curated, so not shown. | [ ] |
| C34 | absence | affidavit | near_window | **unproven** | None 3-4 a.m. CDT; Item 3 prints the 4:12 call as 3:12. | [ ] |
| C35 | absence | affidavit | same_name | **contradicted** | FERRO-OKAFOR WhatsApp on Mar 23 and 24. | [ ] |
| C36 | absence | affidavit | second_phone | **unproven** | None on Item 1 (curated); Item 3 holds a Mar 29 text. | [ ] |
| C37 | role | plain | second_number | **supported** | ferro.finds set the terms and accepted the offer. | [ ] |
| C38 | role | plain | same_name | **contradicted** | FERRO sent 'pickup 10:15, not before'. | [ ] |
| C39 | role | plain | none | **unproven** | OKAFOR offered himself; recruitment is interpretation. | [ ] |
| C40 | role | affidavit | same_name | **supported** | His own text: 'driving for nadia tonight, back late'. | [ ] |
| C41 | role | affidavit | similar_quote | **contradicted** | HALLORAN wrote 'the unit on pulaski', not FERRO. | [ ] |
| C42 | role | affidavit | similar_quote | **unproven** | 'site is clear' went to his foreman; no lookout shown. | [ ] |
| C43 | event | plain | similar_quote | **supported** | Proposal and 'ok' on Mar 3; Thursday is Mar 5. | [ ] |
| C44 | event | plain | same_name | **supported** | Request and 'ok ill grab it tonight' on Mar 23. | [ ] |
| C45 | event | plain | same_name | **unproven** | Only a 45 s call; the 10-minute call is the cousin's. | [ ] |
| C46 | event | affidavit | near_window | **supported** | 4:48 a.m. CDT; Item 3 prints 3:48 AM(UTC-6). | [ ] |
| C47 | event | affidavit | similar_quote | **supported** | Message and 'got it, thx' on Mar 23. | [ ] |
| C48 | event | affidavit | second_phone | **contradicted** | FERRO's Mar 28 WhatsApp, on Item 3 only. | [ ] |

## Assumption rows

One table for the whole sheet; the claim texts are in `affidavit_draft.md` and
`ANSWER_KEY_DRAFT.md`. Gaps (what the rows leave to the expert) follow the table.

| Claim | Template | Core | Parameters | Check | Why | Agree? |
|---|---|---|---|---|---|---|
| C01 | `sender` | yes | quoted_text: need the big van sat, 6am<br>person_ids: person:halloran<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: need the big van sat, 6am<br>person_ids: person:halloran, person:ferro<br>channels: SMS<br>window: "On February 18, 2026" (America/Chicago, local wall clock) | pass | 8:12 p.m. CST Feb 18; Item 1 prints 2/19 2:12:40 AM(UTC+0). |  |
| C02 | `sender` | yes | quoted_text: address is 2210 n kildare, side gate<br>person_ids: person:ferro<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: address is 2210 n kildare, side gate<br>person_ids: person:ferro, person:okafor<br>channels: WhatsApp<br>window: "On March 4, 2026" (America/Chicago, local wall clock) | pass | 2:40 p.m. CST Mar 4. |  |
| C03 | `sender` | yes | quoted_text: the yellow ones are in my garage<br>person_ids: person:okafor<br>channels: SMS | fail | The one copy came from +17735550164, Item 2's 'Dez' (FERRO's cousin), not from OKAFOR's +17735550176. | [ ] |
|  | `record_time` | yes | quoted_text: the yellow ones are in my garage<br>channels: SMS<br>device_ids: dev:item2<br>window: "On March 10, 2026" (America/Chicago, local wall clock) | pass | 11:05 a.m. CDT Mar 10, on Item 2. |  |
| C04 | `sender` | yes | quoted_text: bring the long ladder and both dollies<br>account_ids: acct:item3:SMS:+13125550199<br>channels: SMS | pass | Incoming on Item 3 from the PREPAID (paragraph 3). | [ ] |
|  | `record_time` | yes | quoted_text: bring the long ladder and both dollies<br>person_ids: person:okafor<br>account_ids: acct:item3:SMS:+13125550199<br>channels: SMS<br>window: "On the evening before the BELMONT SITE theft (March 6, 2026, 5 p.m. to midnight)" (America/Chicago, local wall clock) | pass | 7:15 p.m. CST Mar 6 (printed 7:15:22 PM(UTC-6)). |  |
|  | `authorship` | no | quoted_text: bring the long ladder and both dollies<br>person_ids: person:halloran<br>account_ids: acct:item3:SMS:+13125550199<br>channels: SMS | - | That HALLORAN typed it rests on paragraph 3's PREPAID; tested as a contact in C08. |  |
| C05 | `sender` | yes | quoted_text: all 9 at the unit. go to bed<br>person_ids: person:halloran<br>channels: Telegram | pass | SUBJECT-1 is HALLORAN; his Telegram sent it. | [ ] |
|  | `record_time` | yes | quoted_text: all 9 at the unit. go to bed<br>person_ids: person:halloran, person:ferro<br>device_ids: dev:item2<br>channels: Telegram<br>window: "In the early hours after the theft (March 8, 2026, midnight to 6 a.m.)" (America/Chicago, local wall clock) | pass | The TARGET PHONE is Item 2 (paragraph 2). 1:47 a.m. CST Mar 8. |  |
| C06 | `sender` | yes | quoted_text: stay off the phone till tuesday<br>person_ids: person:halloran<br>channels: SMS | inconclusive | No message with these words on any phone. | [ ] |
|  | `record_time` | yes | quoted_text: stay off the phone till tuesday<br>person_ids: person:halloran, person:okafor<br>channels: SMS<br>window: "The next day (Sunday, March 15, 2026)" (America/Chicago, local wall clock) | inconclusive | 'The next day' follows C31's March 14. Not found. |  |
| C07 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Rocco<br>account_ids: acct:item1:SMS:+17735550187 | pass | Item 1's 'Rocco' holds +17735550187. | [ ] |
| C08 | `contact_entry` | yes | device_ids: dev:item2<br>quoted_text: Hal 2<br>account_ids: acct:item2:SMS:+13125550199 | pass | Item 2's 'Hal 2' holds +13125550199. | [ ] |
| C09 | `contact_entry` | yes | device_ids: dev:item3<br>quoted_text: Hal<br>account_ids: acct:item3:SMS:+13125550199 | inconclusive | Item 3's 'Hal' holds +13125550141; a missing entry is never a fail. | [ ] |
| C10 | `same_account` | yes | channels: Telegram<br>handles: dez, D.O.<br>device_ids: dev:item2 | pass | Both names resolve to Telegram user id 8204103 (OKAFOR's own account on Item 3). | [ ] |
| C11 | `contact_entry` | yes | device_ids: dev:item2<br>quoted_text: Desmond O<br>account_ids: acct:item2:SMS:+17735550176 | pass | The TARGET PHONE is Item 2. | [ ] |
| C12 | `same_account` | yes | channels: Instagram<br>handles: kip.flips.chi, kipflips.chi<br>device_ids: dev:item2 | fail | Two usernames, two accounts. | [ ] |
| C13 | `record_time` | yes | person_ids: person:okafor, person:halloran<br>channels: call<br>duration_s: 210, 270<br>window: "At about 3:20 a.m. on March 8, 2026" (America/Chicago, local wall clock) | pass | 3:21:30 a.m. CDT, 245 s. Item 3 prints 2:21:30 AM(UTC-6). | [ ] |
| C14 | `record_time` | yes | person_ids: person:ferro, person:okafor<br>channels: call<br>duration_s: 40, 80<br>window: "At about 10:40 p.m. on March 21, 2026" (America/Chicago, local wall clock) | pass | 10:41:05 p.m. CDT, 58 s. The 9:41 p.m. call (75 s) is outside. | [ ] |
| C15 | `sender` | yes | quoted_text: need u at 6 tmrw, bring gloves<br>person_ids: person:halloran<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: need u at 6 tmrw, bring gloves<br>person_ids: person:halloran, person:okafor<br>channels: SMS<br>window: "At 12:15 a.m. on March 19, 2026" (America/Chicago, local wall clock) | fail | Sent 7:15:40 p.m. CDT Mar 18; 12:15:40 AM is Item 1's UTC+0 print. |  |
| C16 | `record_time` | yes | person_ids: person:okafor<br>account_ids: acct:item3:SMS:+13125550199<br>channels: call<br>duration_s: 150, 179<br>window: "Within half an hour after the KEDZIE YARD theft (10:30 to 11 p.m., March 21, 2026)" (America/Chicago, local wall clock) | pass | 10:58:10 p.m. CDT, 165 s, to +13125550199. | [ ] |
| C17 | `sender` | yes | quoted_text: they might come tmrw. clean the van<br>person_ids: person:ferro<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: they might come tmrw. clean the van<br>person_ids: person:ferro, person:halloran<br>channels: WhatsApp<br>window: "At about a quarter to midnight on the night before the SEARCH (March 25, 2026)" (America/Chicago, local wall clock) | pass | 11:46:12 p.m. CDT Mar 25; Item 1 prints 3/26 4:46:12 AM(UTC+0). |  |
| C18 | `record_time` | yes | person_ids: person:okafor<br>account_ids: acct:item1:SMS:+17735550187<br>channels: call<br>window: "Within fifteen minutes of the KEDZIE YARD theft (10:15 to 10:45 p.m., March 21, 2026)" (America/Chicago, local wall clock) | inconclusive | No call with CW-1's number; the 10:36 p.m. call is to Item 3's 'Rocco', +17735550133. | [ ] |
| C19 | `sender` | yes | quoted_text: the coils are under the blue tarp<br>person_ids: person:halloran<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: the coils are under the blue tarp<br>person_ids: person:halloran, person:ferro<br>channels: SMS<br>window: "On March 9, 2026" (America/Chicago, local wall clock) | pass | 10:30 a.m. CDT Mar 9. |  |
|  | `meaning` | yes | quoted_text: the coils are under the blue tarp<br>person_ids: person:halloran, person:ferro<br>channels: SMS<br>window: "On March 9, 2026" (America/Chicago, local wall clock) | - | 'the copper ones?' / 'ya the copper, all 9' in the same exchange. |  |
| C20 | `sender` | yes | quoted_text: bring the 3 heavy ones fri<br>person_ids: person:ferro<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: bring the 3 heavy ones fri<br>person_ids: person:ferro, person:halloran<br>channels: SMS<br>window: "On March 13, 2026" (America/Chicago, local wall clock) | pass | 4:20 p.m. CDT Mar 13. |  |
|  | `meaning` | yes | quoted_text: bring the 3 heavy ones fri<br>person_ids: person:ferro, person:halloran<br>channels: SMS<br>window: "On March 13, 2026" (America/Chicago, local wall clock) | - | Whether 'the 3 heavy ones' are the BELMONT SITE generators; nothing fixes it. |  |
| C21 | `sender` | yes | quoted_text: that welder guy talks too much<br>person_ids: person:okafor<br>channels: SMS | fail | FERRO sent it to OKAFOR. | [ ] |
|  | `record_time` | yes | quoted_text: that welder guy talks too much<br>channels: SMS<br>window: "On March 16, 2026" (America/Chicago, local wall clock) | pass | 4:10 p.m. CDT Mar 16. |  |
|  | `meaning` | yes | quoted_text: that welder guy talks too much<br>channels: SMS | - | That the words warn of a buyer working with police. |  |
| C22 | `sender` | yes | quoted_text: the 9 blankets are at the unit<br>person_ids: person:halloran<br>channels: Telegram | pass | HAL is HALLORAN; outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: the 9 blankets are at the unit<br>person_ids: person:halloran, person:okafor<br>channels: Telegram<br>window: "Two days later (March 11, 2026)" (America/Chicago, local wall clock) | pass | 'Two days later' follows C19's March 9. 9:20 p.m. CDT Mar 11. |  |
|  | `meaning` | yes | quoted_text: the 9 blankets are at the unit<br>person_ids: person:halloran, person:okafor<br>channels: Telegram | - | The Mar 8 'wrap the spools in the moving blankets' fixes 'blankets'. |  |
| C23 | `sender` | yes | quoted_text: 1.8 for the lot<br>account_ids: acct:item2:Instagram:kipflips.chi<br>channels: Instagram | pass | The BUYER is kipflips.chi (paragraph 3). | [ ] |
|  | `record_time` | yes | quoted_text: 1.8 for the lot<br>person_ids: person:ferro<br>account_ids: acct:item2:Instagram:kipflips.chi<br>channels: Instagram<br>window: "Two days before the SEARCH (March 24, 2026)" (America/Chicago, local wall clock) | pass | 3:05 p.m. CDT Mar 24. |  |
|  | `meaning` | yes | quoted_text: 1.8 for the lot<br>person_ids: person:ferro<br>account_ids: acct:item2:Instagram:kipflips.chi<br>channels: Instagram<br>window: "Two days before the SEARCH (March 24, 2026)" (America/Chicago, local wall clock) | - | 'lot is 4 spools ...' before and '1800 works. sat' after fix the meaning. |  |
| C24 | `sender` | yes | quoted_text: owen dropped off the stuff<br>account_ids: acct:item2:WhatsApp:13125550107@s.whatsapp.net<br>channels: WhatsApp | pass | FERRO's sister ('Mari') sent it. | [ ] |
|  | `record_time` | yes | quoted_text: owen dropped off the stuff<br>person_ids: person:ferro<br>account_ids: acct:item2:WhatsApp:13125550107@s.whatsapp.net<br>channels: WhatsApp<br>window: "On St. Patrick's Day (March 17, 2026)" (America/Chicago, local wall clock) | pass | 6:20 p.m. CDT Mar 17. |  |
|  | `meaning` | yes | quoted_text: owen dropped off the stuff<br>channels: WhatsApp | - | Which Owen, and what stuff; not fixed. |  |
| C25 | `message_count` | yes | device_ids: dev:item1<br>person_ids: person:halloran, person:ferro<br>channels: WhatsApp<br>expected_count: 8<br>count_op: eq<br>window: "Between February 23 and March 1, 2026" (America/Chicago, local wall clock) | pass | Eight on Chicago dates; printed dates give nine. | [ ] |
| C26 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:okafor, person:halloran<br>channels: Telegram<br>expected_count: 6<br>count_op: eq<br>window: "From March 9 through March 14, 2026" (America/Chicago, local wall clock) | pass | Six on Item 3; Item 1 holds seven. | [ ] |
| C27 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:ferro, person:okafor<br>channels: SMS<br>expected_count: 3<br>count_op: eq<br>window: "On March 21, 2026" (America/Chicago, local wall clock) | fail | Five on the Chicago day. | [ ] |
| C28 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:okafor<br>account_ids: acct:item3:SMS:+13125550199<br>channels: SMS<br>expected_count: 11<br>count_op: eq<br>window: "During the work week before the BELMONT SITE theft, Monday through Friday (March 2 to 6, 2026)" (America/Chicago, local wall clock) | pass | Eleven between the PREPAID and OKAFOR on Item 3 (SUBJECT-3's phone). | [ ] |
| C29 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:ferro, person:halloran<br>channels: Telegram<br>expected_count: 4<br>count_op: eq<br>window: "Between March 16 and March 20, 2026" (America/Chicago, local wall clock) | fail | Six on the TARGET PHONE (Item 2). | [ ] |
| C30 | `message_count` | yes | device_ids: dev:item1<br>person_ids: person:halloran, person:ferro<br>channels: SMS<br>expected_count: 12<br>count_op: ge<br>window: "On the night of the BELMONT SITE theft, between 11 p.m. and 3 a.m." (America/Chicago, local wall clock) | inconclusive | Nine in the three real hours; fewer than claimed is never a fail. | [ ] |
| C31 | `no_contact` | yes | person_ids: person:halloran, person:okafor<br>window: "on March 14, 2026" (America/Chicago, local wall clock) | fail | The 9:30 p.m. CDT text. | [ ] |
| C32 | `no_contact` | yes | person_ids: person:ferro, person:halloran<br>window: "between March 27 and March 29, 2026" (America/Chicago, local wall clock) | inconclusive | None with HALLORAN's phone accounts; curated reports. | [ ] |
|  | `no_contact` | yes | person_ids: person:ferro<br>account_ids: acct:item2:SMS:+13125550199<br>window: "between March 27 and March 29, 2026" (America/Chicago, local wall clock) | fail | The PREPAID (HALLORAN's, paragraph 3) wrote to FERRO on Mar 28. |  |
| C33 | `no_contact` | yes | person_ids: person:okafor<br>account_ids: acct:item1:SMS:+17735550187<br>window: "between March 1 and March 31, 2026" (America/Chicago, local wall clock) | inconclusive | None found; curated reports. Item 3's 'Rocco' is another number. | [ ] |
| C34 | `no_contact` | yes | person_ids: person:okafor, person:ferro<br>window: "In the first hour after the clocks went forward that night (3 to 4 a.m. CDT, March 8, 2026)" (America/Chicago, local wall clock) | inconclusive | None in the hour; the 4:12 a.m. call prints 3:12 AM(UTC-6) on Item 3. | [ ] |
| C35 | `no_contact` | yes | person_ids: person:ferro, person:okafor<br>window: "In the days leading up to the SEARCH, from Monday through Wednesday (March 23 to 25, 2026)" (America/Chicago, local wall clock) | fail | DEZ is OKAFOR (paragraph 2). WhatsApp on Mar 23 and 24. | [ ] |
| C36 | `no_contact` | yes | person_ids: person:halloran, person:okafor<br>device_ids: dev:item1<br>window: "After the SEARCH, for the rest of March (March 27 to 31, 2026)" (America/Chicago, local wall clock) | inconclusive | None on Item 1 (SUBJECT-1's phone); curated. Item 3 holds a Mar 29 text. | [ ] |
| C37 | `sender` | yes | quoted_text: lot is 4 spools 12 gauge copper, 250 ft each<br>person_ids: person:ferro<br>channels: Instagram | pass | ferro.finds is an owner account of Item 2. | [ ] |
|  | `sender` | yes | quoted_text: 1800 works. sat<br>person_ids: person:ferro<br>channels: Instagram | pass | The acceptance, from ferro.finds. |  |
|  | `role` | yes | person_ids: person:ferro<br>account_ids: acct:item2:Instagram:kipflips.chi<br>channels: Instagram | - | That FERRO handled the sale; the conversation shows her account setting terms. |  |
| C38 | `sender` | yes | quoted_text: pickup 10:15, not before<br>person_ids: person:okafor<br>channels: SMS | fail | FERRO sent it. | [ ] |
|  | `record_time` | yes | quoted_text: pickup 10:15, not before<br>channels: SMS<br>window: "On March 20, 2026" (America/Chicago, local wall clock) | pass | 2:00 p.m. CDT Mar 20. |  |
|  | `role` | yes | person_ids: person:okafor | - | That OKAFOR set the time. |  |
| C39 | `role` | yes | person_ids: person:halloran, person:okafor | - | That HALLORAN recruited OKAFOR; OKAFOR offered himself. | [ ] |
| C40 | `sender` | yes | quoted_text: driving for nadia tonight<br>person_ids: person:okafor<br>channels: SMS | pass | DEZ is OKAFOR; outgoing on Item 3. | [ ] |
|  | `record_time` | yes | quoted_text: driving for nadia tonight<br>person_ids: person:okafor<br>account_ids: acct:item3:SMS:+17735550145<br>channels: SMS<br>window: "that evening (March 21, 2026, 5 p.m. to midnight)" (America/Chicago, local wall clock) | pass | 7:40 p.m. CDT Mar 21, to 'Tash'. |  |
|  | `role` | yes | person_ids: person:okafor<br>quoted_text: driving for nadia tonight<br>window: "On the night of the KEDZIE YARD theft" (America/Chicago, local wall clock) | - | That OKAFOR drove that night; his own words. |  |
| C41 | `sender` | yes | quoted_text: the unit on pulaski<br>person_ids: person:ferro<br>channels: SMS | fail | HALLORAN wrote it, to FERRO. | [ ] |
|  | `role` | yes | person_ids: person:ferro | - | That FERRO chose where the spools went. |  |
| C42 | `role` | yes | person_ids: person:halloran<br>window: "In the hours before the BELMONT SITE theft (March 7, 2026, 6 to 11 p.m.)" (America/Chicago, local wall clock) | - | That HALLORAN acted as a lookout; the only 'site is clear' text went to his foreman. | [ ] |
| C43 | `sender` | yes | quoted_text: meet behind the laundromat on fullerton thursday 8pm<br>person_ids: person:halloran<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: meet behind the laundromat on fullerton thursday 8pm<br>person_ids: person:halloran, person:okafor<br>channels: SMS<br>window: "On March 3, 2026" (America/Chicago, local wall clock) | pass | 12:10 p.m. CST Mar 3. |  |
|  | `weekday_date` | yes | quoted_text: meet behind the laundromat on fullerton thursday 8pm<br>channels: SMS<br>window: "Thursday, March 5, 2026" (America/Chicago, local wall clock) | pass | 'thursday' sent on Tuesday Mar 3 is Mar 5. |  |
|  | `event` | yes | person_ids: person:halloran, person:okafor<br>channels: SMS<br>window: "On March 3, 2026" (America/Chicago, local wall clock) | - | That they arranged it: OKAFOR's 'ok'. |  |
| C44 | `sender` | yes | quoted_text: need the welder out of my garage by tmrw<br>person_ids: person:ferro<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `sender` | yes | quoted_text: ok ill grab it tonight<br>person_ids: person:halloran<br>channels: SMS | pass | HALLORAN's answer, outgoing on Item 1. |  |
|  | `record_time` | yes | quoted_text: need the welder out of my garage by tmrw<br>person_ids: person:ferro, person:halloran<br>channels: SMS<br>window: "On March 23, 2026" (America/Chicago, local wall clock) | pass | 11:00 a.m. CDT Mar 23. |  |
| C45 | `record_time` | yes | person_ids: person:ferro, person:okafor<br>channels: call<br>duration_s: 540, 660<br>window: "On March 12, 2026" (America/Chicago, local wall clock) | inconclusive | Their only call that day lasted 45 s; the 612 s call is with Item 2's 'Dez'. | [ ] |
| C46 | `sender` | yes | quoted_text: back at gus<br>person_ids: person:okafor<br>channels: Telegram | pass | The DRIVER's Telegram, outgoing on Item 3. | [ ] |
|  | `record_time` | yes | quoted_text: back at gus<br>person_ids: person:okafor, person:ferro<br>channels: Telegram<br>window: "Shortly before 5 a.m. the morning after the theft (March 8, 2026, 4:30 to 5 a.m.)" (America/Chicago, local wall clock) | pass | 4:48:26 a.m. CDT; Item 3 prints 3:48:26 AM(UTC-6). |  |
| C47 | `sender` | yes | quoted_text: ur 600 is in the envelope under the mat<br>person_ids: person:ferro<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: ur 600 is in the envelope under the mat<br>person_ids: person:ferro, person:okafor<br>channels: WhatsApp<br>window: "Two days after the KEDZIE YARD theft (March 23, 2026)" (America/Chicago, local wall clock) | pass | 8:30 p.m. CDT Mar 23. |  |
|  | `event` | yes | person_ids: person:ferro, person:okafor<br>channels: WhatsApp<br>window: "Two days after the KEDZIE YARD theft (March 23, 2026)" (America/Chicago, local wall clock) | - | That he was paid: his 'got it, thx'. |  |
| C48 | `no_contact` | yes | person_ids: person:ferro, person:okafor<br>window: "After the SEARCH, for the rest of March (March 27 to 31, 2026)" (America/Chicago, local wall clock) | fail | FERRO's Mar 28 WhatsApp, held on Item 3 only. | [ ] |

Gaps:

- C03: That FERRO received it is shown by the time row's phone (Item 2), not by a party.
- C13: No template says who placed a call; Item 3 logs it as outgoing, as the claim says.
- C14: No template says who placed a call; Item 2 logs it as outgoing, as the claim says.
- C16: No template says who placed a call; Item 3 logs it as outgoing, as the claim says.
- C24: That the sister is Marisol Ferro is the contact name 'Mari', not tested.
- C39: The claim quotes nothing and names no time, so no check applies; only the expert can decide it.
- C40: That 'Tash' is his girlfriend is not tested (no template for kin).
- C42: The claim paraphrases a report without quoting it; no check applies.
- C43: 'Behind the laundromat on Fullerton' is not tested (no template for a place).

Signed: ____________________  Date: __________
