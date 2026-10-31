# case05 signing sheet: DRAFT key and assumption sheet

About twenty minutes. Each claim: the draft verdict, its wording and hazard, the
one-line reason, and the assumption rows the pipeline runs on. Tick or correct each
line; the full reasoning and every cited row are in `ANSWER_KEY_DRAFT.md`. Nothing here
is gold until a human copies the approved lines into `eval/gold/case05/` (`gold.jsonl`,
`assumptions.jsonl`) with `labeled_by` set to the approver.

Read the affidavit first (`affidavit_draft.md`, 19 paragraphs). Its
definitions: TOBY = SUBJECT-1 = MERROW (Item 1, the SAMSUNG); SUBJECT-2 = VARGA (Item 2,
the iPHONE); CAL = the COURIER = SUBJECT-3 = ODUM (Item 3, the ONEPLUS); the BURNER is
+17205550186; the FENCE used +17205550129; the LOCKER BURGLARY was the night of Saturday,
November 1, 2025, when the clocks went back; the SHOP BURGLARY was at about 9:40 p.m. on
Friday, November 14, 2025; the STOP was at 3:10 p.m. on Wednesday, November 19, 2025.

Every person, phone number, Instagram handle, Telegram name and numeric id, place, shop
and event in the reports and the affidavit is invented.

What to decide:

1. Is each verdict right? Absence claims are never supported on a curated report
   (reading rule 8); a meaning or role is supported only where the conversation fixes it
   (rule 9). C20, C24, C39, C42 and C47 are the closest calls. C04 is unproven after
   the second read (R1): that MERROW used the BURNER rests on paragraph 3 and the
   number's own 'its toby'; if you accept that tie, C04 goes to supported.
   C17, C30 and C34 read times in the hour that came twice (rule 4).
2. Is each hazard a fair wrong reading, and does the sheet name only the right person,
   account, phone and window?
3. Are the assumption rows the right reading of the claim? `expected_check` is what the
   deterministic check should find; a test runs the checks against it. A dash means no
   check exists, so only expert review covers that row.

## Second read (2026-10-31)

A second, blind reviewer read the draft key and sheet against rules 0.4.0 and the three
reports. Read this before signing. One line per finding: fixed (the key, the sheet or
the wording changed), or kept and why. Verdicts changed: C04 (supported to unproven).

| Finding | Claims | Graded | Outcome | Answer |
|---|---|---|---|---|
| R1 | C04 | weak | fixed | Now unproven: that SUBJECT-1 used the BURNER rests on paragraph 3 and the number's own 'its toby', the self-identification the key refuses for 'T.M.', with a second Toby (Rusk, +13035550139) in the data and no record from MERROW's phone tying him to it. Split now 23/12/13. If Arsh accepts paragraph 3's premise, C04 goes back to supported. |
| R2 | C08 | sheet | fixed | Gap added for signing: unproven, not contradicted, because the contact check never fails on a missing entry; 'Cal' holding 0153 does not rule out a 'Cal' entry with 0168. |
| R3 | C39 | weak | kept | Unproven kept: VARGA offered to list bikes and MERROW answered 'good to know'; who recruited whom is interpretation (reading rule 9). Listed as a close call. |
| R4 | C25, C26, C27, C30 | sheet | fixed | each_way set on all four rows, as 'exchanged' asks. The checks rerun to pass, pass, fail and pass, as before. |
| R5 | C10 | sheet | fixed | A core person_identity row now ties user id 6630402 to SUBJECT-2 (Item 2's own account; Item 2's copies added as key evidence). 'From the second week of November' is now 'From November 10, 2025', the edge the rows show. A gap says same_account passes on the account's first name seen and that no row tests the rename's timing. |
| R6 | C48 | sheet | fixed | Gap added: no_contact on calls has no direction; the fail is right because the Nov 23 call is VARGA's, logged incoming from her number on Item 3. |
| R7 | C35, C36, C48 | weak | fixed | Reworded so each window follows from the words: 'On the three days after the day of the SHOP BURGLARY' (Nov 15 to 17), 'From the day after the STOP to the end of November' (Nov 20 to 30), 'In the seven days starting the day after the STOP' (Nov 20 to 26). Sheet windows unchanged; reading rule 5 updated. |
| R8 | C36 | weak | fixed | Now 'SUBJECT-1 and the COURIER had no contact, per the SAMSUNG', a claim about contact that rests on Item 1. Still unproven: a curated report cannot show an absence. |
| R9 | C22 | weak | fixed | Narrowed to 'the battery packs': the thread fixes 'pizzas' as the batteries ('do the batteries come off those', 'on here we call them pizzas'), not what they came off. Supported kept. |
| R10 | C46 | sheet | fixed | Gap added: 'let SUBJECT-2 know' rests on the sending alone; the only copy is outgoing on Item 3, and Item 2's report does not hold it. |
| R11 | C07, C08, C09, C12, C24 | weak | fixed | Wording kept. Each alias match inside a quote is recorded (ALIAS_IN_QUOTES, shown in both drafts): TOBY points to MERROW in C07 and C09 (right) and C12 (wrong: Toby Rusk); CAL points to ODUM in C08 (right person, other number) and C24 (not fixed). C09 was found by the same scan. |
| R12 | C04, C06, C16, C22, C24, C28, C34, C36, C40, C41, C46, C47, C48 | cosmetic | kept | 'the COURIER' kept as the alias, the form every one of these claims uses; paragraph 2 prints the definition as (the "COURIER"). |
| R13 | C01, C23 | weak | fixed | The storage site and the bike shop now carry clearly invented names (Quillbarrow Self Storage, Pindlewick Cycles), in the quotes too; the four Instagram handles end in '_fict'. Hazards unchanged. The signing sheet says every name, handle and id is invented. |

## Aliases inside quotes

An alias (case.json `aliases`) is matched whole and in any case, so it also matches
these names inside quotes. The wording stays: the match is real product behaviour.
Check where each one points.

- C07: TOBY matches the quoted contact name "Toby" and points to MERROW. Right: Item 3's 'Toby' holds MERROW's number, +17205550134.
- C08: CAL matches the quoted contact name "Cal" and points to ODUM. Right person, other number: Item 1's 'Cal' holds ODUM's work cell, +17205550153; the claim's +17205550168 is saved as 'Cal 2'.
- C09: TOBY matches the quoted Telegram name "Toby M" and points to MERROW. Right: 'Toby M' is user id 6630401, Item 1's own account. ("T.M." matches no alias.)
- C12: TOBY matches the quoted sender name "Toby" and points to MERROW. Wrong: on Item 2, 'Toby' is Toby Rusk, +13035550139. The claim's own TOBY is MERROW, rightly.
- C24: CAL matches "cal" in the quote "cal is getting nervous" and points to ODUM. Not fixed: Item 2 also saves Calla Brightwater as 'Cal' (+13035550161), and the conversation does not say which Cal is meant. The claim's own 'the COURIER' is ODUM.

## Counts

### Claim type x draft verdict

| Type | supported | contradicted | unproven | Total |
|---|---|---|---|---|
| communication | 3 | 1 | 2 | 6 |
| identity | 3 | 2 | 1 | 6 |
| timing | 4 | 1 | 1 | 6 |
| content_meaning | 3 | 1 | 2 | 6 |
| count | 4 | 1 | 1 | 6 |
| absence | 0 | 3 | 3 | 6 |
| role | 2 | 2 | 2 | 6 |
| event | 4 | 1 | 1 | 6 |
| **all** | **23** | **12** | **13** | **48** |

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
| plain | 11 | 8 | 5 |
| affidavit | 12 | 4 | 8 |

### Hazards by kind

| Hazard | What the wrong reading is | Claims | supported | contradicted | unproven |
|---|---|---|---|---|---|
| same_name | a second person with the same first name or nickname | 6 | 1 | 2 | 3 |
| second_number | a second number or account for the same person | 8 | 4 | 2 | 2 |
| second_phone | a second phone that could be meant | 7 | 4 | 1 | 2 |
| near_window | a near-miss window: UTC against local time across midnight, the hour that came twice when the clocks went back, an adjacent day, or Item 3's fixed UTC-7 print | 11 | 6 | 4 | 1 |
| contact_name | one contact name saved on two phones for two people | 5 | 2 | 1 | 2 |
| similar_quote | similar words in another thread | 9 | 5 | 2 | 2 |
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
| C01 | communication | plain | near_window | **supported** | Sent 7:25 p.m. MDT Oct 9; Item 2 prints Oct 10 (UTC+0). | [ ] |
| C02 | communication | plain | none | **supported** | Observed on Items 2 and 3, Oct 21. | [ ] |
| C03 | communication | plain | same_name | **contradicted** | Sent by Item 2's 'Cal' (WhatsApp 13035550161), not ODUM's 17205550168. | [ ] |
| C04 | communication | affidavit | second_number | **unproven** | The BURNER's text on Item 3, 6:50 p.m. Oct 30; MERROW as its user rests on the number's self-identification only. | [ ] |
| C05 | communication | affidavit | second_phone | **supported** | Item 3 (the ONEPLUS) received it at 3:40 a.m. MST Nov 2; Item 2 lacks it. | [ ] |
| C06 | communication | affidavit | similar_quote | **unproven** | No such text anywhere; 'Arlo' got 'nobody rides the quad till december'. | [ ] |
| C07 | identity | plain | contact_name | **supported** | Item 3's 'Toby' holds +17205550134; Item 2's 'Toby' is another number. | [ ] |
| C08 | identity | plain | second_number | **unproven** | Item 1's 'Cal' holds 0153; 0168 is saved as 'Cal 2'. Not shown (contact lists edit). | [ ] |
| C09 | identity | plain | second_number | **contradicted** | Two Telegram ids: 'Toby M' 6630401, 'T.M.' 6630488. | [ ] |
| C10 | identity | affidavit | second_number | **supported** | One Telegram id, 6630402 (Item 2's own); Item 3 shows 'Ines V' to Nov 8, 'vee.rides' from Nov 10. | [ ] |
| C11 | identity | affidavit | contact_name | **supported** | Item 2's 'T2' holds +17205550186; she wrote 'saved as T2'. | [ ] |
| C12 | identity | affidavit | contact_name | **contradicted** | Item 2's 'Toby' (+13035550139) sent it, not MERROW's +17205550134. | [ ] |
| C13 | timing | plain | near_window | **supported** | 9:31 p.m. MDT, 288 s; Item 3 prints 8:31 PM(UTC-7), and 9:30 PM for a 41 s call. | [ ] |
| C14 | timing | plain | near_window | **supported** | 11:52 p.m. MST, 128 s; Item 2 prints 11:50 PM for a 4:50 p.m. call of 305 s. | [ ] |
| C15 | timing | plain | near_window | **contradicted** | Sent 7:45 p.m. MDT Oct 24; 6:45 PM is Item 3's UTC-7 print. | [ ] |
| C16 | timing | affidavit | second_number | **supported** | 10:07 p.m., 92 s, from the BURNER (Item 3). | [ ] |
| C17 | timing | affidavit | near_window | **supported** | 1:34 a.m. MST, the second 1 a.m. hour. | [ ] |
| C18 | timing | affidavit | contact_name | **unproven** | No FENCE call; the 3:22 p.m. call is to Item 3's 'Jory', +17205550181. | [ ] |
| C19 | content_meaning | plain | similar_quote | **supported** | 'the emtbs?' / 'ya electric mountain bikes, all 6' fix the meaning. | [ ] |
| C20 | content_meaning | plain | similar_quote | **unproven** | Observed; 'the cold ones' is not fixed (and the same words went to 'Arlo' about drinks). | [ ] |
| C21 | content_meaning | plain | similar_quote | **contradicted** | VARGA sent it, not ODUM. | [ ] |
| C22 | content_meaning | affidavit | similar_quote | **supported** | Nov 3: 'on here we call them pizzas' after 'do the batteries come off' fixes it. | [ ] |
| C23 | content_meaning | affidavit | second_number | **supported** | 'the pindlewick road bikes?' / 'ya the carbon ones from friday, all 4' fix it. | [ ] |
| C24 | content_meaning | affidavit | same_name | **unproven** | Two Cals on Item 2; which one is not fixed. | [ ] |
| C25 | count | plain | near_window | **supported** | 7 on Denver dates; printed dates give 8. | [ ] |
| C26 | count | plain | second_phone | **supported** | 5 on Item 3; Item 2 has 6. | [ ] |
| C27 | count | plain | near_window | **contradicted** | 6 on Nov 14 local; a UTC day gives 4. | [ ] |
| C28 | count | affidavit | second_number | **supported** | 5 texts ODUM to the BURNER, Oct 27-31 on Item 3. | [ ] |
| C29 | count | affidavit | second_phone | **unproven** | 3 on Item 1 (curated); Item 3 holds 5. | [ ] |
| C30 | count | affidavit | near_window | **supported** | 12 in 11 p.m.-3 a.m. (five hours, DST ended); a four-hour window gives 10 or 9. | [ ] |
| C31 | absence | plain | near_window | **contradicted** | 12:30 a.m. MDT Oct 23 text; Item 3 prints Oct 22. | [ ] |
| C32 | absence | plain | second_number | **contradicted** | Signal exchange on Nov 23. | [ ] |
| C33 | absence | plain | contact_name | **unproven** | No record with 0129; Item 3's 'Jory' is 0181. Curated, so not shown. | [ ] |
| C34 | absence | affidavit | near_window | **unproven** | None 1-2 a.m. MST; the 1:25 a.m. WhatsApp is in the first (MDT) hour. | [ ] |
| C35 | absence | affidavit | same_name | **contradicted** | VARGA-ODUM WhatsApp on Nov 15 and 16. | [ ] |
| C36 | absence | affidavit | second_phone | **unproven** | None on Item 1 (curated); Item 3 holds a Nov 22 text. | [ ] |
| C37 | role | plain | similar_quote | **supported** | ODUM asked the price, VARGA set it, he took it. | [ ] |
| C38 | role | plain | similar_quote | **contradicted** | MERROW sent 'friday 9:30, back door'. | [ ] |
| C39 | role | plain | none | **unproven** | VARGA offered herself; recruitment is interpretation. | [ ] |
| C40 | role | affidavit | second_phone | **supported** | Her assignment and his 'ok i got marketplace', on Item 3 only. | [ ] |
| C41 | role | affidavit | near_window | **contradicted** | Sent 11:20 p.m. Friday Oct 31; Item 2 prints Saturday 5:20 AM. | [ ] |
| C42 | role | affidavit | same_name | **unproven** | 'staff all gone' went to Item 2's 'Cal'; no watch shown. | [ ] |
| C43 | event | plain | similar_quote | **supported** | Proposal and 'bet' on Oct 28; Thursday is Oct 30. | [ ] |
| C44 | event | plain | same_name | **supported** | Request and 'ok ill move them tonight' on Nov 18. | [ ] |
| C45 | event | plain | same_name | **unproven** | Only a 50 s call; the eight-minute call is with Item 2's 'Cal'. | [ ] |
| C46 | event | affidavit | second_phone | **supported** | 5:48 a.m. MST Nov 2, on Item 3 only. | [ ] |
| C47 | event | affidavit | similar_quote | **supported** | Message and 'got the 400, thx' on Nov 16; 'paid' rests on reading those words. | [ ] |
| C48 | event | affidavit | second_phone | **contradicted** | VARGA called ODUM on Nov 23, on Item 3's log only. | [ ] |

## Assumption rows

One table for the whole sheet; the claim texts are in `affidavit_draft.md` and
`ANSWER_KEY_DRAFT.md`. Gaps (what the rows leave to the expert) follow the table.

| Claim | Template | Core | Parameters | Check | Why | Agree? |
|---|---|---|---|---|---|---|
| C01 | `sender` | yes | quoted_text: back row at quillbarrow has no cameras<br>person_ids: person:merrow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: back row at quillbarrow has no cameras<br>person_ids: person:merrow, person:varga<br>channels: SMS<br>window: "On October 9, 2025" (America/Denver, local wall clock) | pass | 7:25 p.m. MDT Oct 9; Item 2 prints 10/10 1:25:10 AM(UTC+0). |  |
| C02 | `sender` | yes | quoted_text: unit 41, code is 7719<br>person_ids: person:varga<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: unit 41, code is 7719<br>person_ids: person:varga, person:odum<br>channels: WhatsApp<br>window: "On October 21, 2025" (America/Denver, local wall clock) | pass | 2:05 p.m. MDT Oct 21. |  |
| C03 | `sender` | yes | quoted_text: the blue ones fit in my hatchback<br>person_ids: person:odum<br>channels: WhatsApp | fail | The one copy came from WhatsApp 13035550161, Item 2's 'Cal', not from ODUM's 17205550168. | [ ] |
|  | `record_time` | yes | quoted_text: the blue ones fit in my hatchback<br>channels: WhatsApp<br>device_ids: dev:item2<br>window: "On November 6, 2025" (America/Denver, local wall clock) | pass | 10:15 a.m. MST Nov 6, on Item 2. |  |
| C04 | `sender` | yes | quoted_text: gate code is 2291, use the side lane<br>account_ids: acct:item3:SMS:+17205550186<br>channels: SMS | pass | Incoming on Item 3 from the BURNER (paragraph 3). | [ ] |
|  | `record_time` | yes | quoted_text: gate code is 2291, use the side lane<br>person_ids: person:odum<br>account_ids: acct:item3:SMS:+17205550186<br>channels: SMS<br>window: "Two days before the LOCKER BURGLARY (Thursday, October 30, 2025)" (America/Denver, local wall clock) | pass | 6:50 p.m. MDT Oct 30 (printed 5:50:40 PM(UTC-7)). |  |
|  | `authorship` | yes | quoted_text: gate code is 2291, use the side lane<br>person_ids: person:merrow<br>account_ids: acct:item3:SMS:+17205550186<br>channels: SMS | - | That MERROW used the BURNER: paragraph 3, and the number's own 'its toby. new number, use this one for work stuff' (Item 3 saves it as 'Toby work'). Core: the expert decides it. |  |
| C05 | `sender` | yes | quoted_text: park it behind the feed store till light<br>person_ids: person:varga<br>channels: Telegram | pass | SUBJECT-2 is VARGA; her Telegram (6630402) sent it. | [ ] |
|  | `record_time` | yes | quoted_text: park it behind the feed store till light<br>person_ids: person:varga, person:odum<br>device_ids: dev:item3<br>channels: Telegram<br>window: "In the early hours of November 2, 2025 (midnight to 6 a.m.)" (America/Denver, local wall clock) | pass | The ONEPLUS is Item 3 (paragraph 2). 3:40 a.m. MST Nov 2. |  |
| C06 | `sender` | yes | quoted_text: nobody rides them till december<br>person_ids: person:merrow<br>channels: SMS | inconclusive | No message with these words on any phone. | [ ] |
|  | `record_time` | yes | quoted_text: nobody rides them till december<br>person_ids: person:merrow, person:odum<br>channels: SMS<br>window: "On the Tuesday after the LOCKER BURGLARY (November 4, 2025)" (America/Denver, local wall clock) | inconclusive | The Tuesday after the Saturday-night burglary is Nov 4. Not found. |  |
| C07 | `contact_entry` | yes | device_ids: dev:item3<br>quoted_text: Toby<br>account_ids: acct:item3:SMS:+17205550134 | pass | Item 3's 'Toby' holds +17205550134. | [ ] |
| C08 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Cal<br>account_ids: acct:item1:SMS:+17205550168 | inconclusive | Item 1's 'Cal' holds +17205550153; a missing entry is never a fail. | [ ] |
| C09 | `same_account` | yes | channels: Telegram<br>handles: Toby M, T.M.<br>device_ids: dev:item3 | fail | 'Toby M' resolves to user id 6630401 and 'T.M.' to 6630488. | [ ] |
| C10 | `same_account` | yes | channels: Telegram<br>handles: Ines V, vee.rides<br>device_ids: dev:item3 | pass | Both names resolve to Telegram user id 6630402 (Item 2's own account). The check resolves names on every phone, not only Item 3; on Telegram only Item 3 shows her account. | [ ] |
|  | `person_identity` | yes | person_ids: person:varga<br>account_ids: acct:item2:Telegram:6630402, acct:item3:Telegram:6630402<br>channels: Telegram | - | That user id 6630402 is SUBJECT-2's: it is Item 2's own Telegram account (its User Accounts sheet, and the outgoing copies on Item 2), and Item 2 is VARGA's phone (the shared device attribution). Core: the expert decides it. |  |
| C11 | `contact_entry` | yes | device_ids: dev:item2<br>quoted_text: T2<br>account_ids: acct:item2:SMS:+17205550186 | pass | The iPHONE is Item 2. | [ ] |
| C12 | `sender` | yes | quoted_text: left the key under the blue pot<br>person_ids: person:merrow<br>channels: SMS | fail | The one copy came from +13035550139, Item 2's 'Toby', not from MERROW. | [ ] |
|  | `record_time` | yes | quoted_text: left the key under the blue pot<br>channels: SMS<br>device_ids: dev:item2<br>window: "on November 11, 2025" (America/Denver, local wall clock) | pass | 9:40 a.m. MST Nov 11, on Item 2. |  |
| C13 | `record_time` | yes | person_ids: person:merrow, person:odum<br>channels: call<br>duration_s: 240, 360<br>window: "At about 9:30 p.m. on October 17, 2025" (America/Denver, local wall clock) | pass | 9:31:05 p.m. MDT, 288 s. Item 3 prints 8:31:05 PM(UTC-7). | [ ] |
| C14 | `record_time` | yes | person_ids: person:varga, person:odum<br>channels: call<br>duration_s: 90, 150<br>window: "At about 11:50 p.m. on November 14, 2025" (America/Denver, local wall clock) | pass | 11:52:10 p.m. MST, 128 s. The 4:50 p.m. call (305 s) is outside. | [ ] |
| C15 | `sender` | yes | quoted_text: need u next saturday, bring the trailer<br>person_ids: person:merrow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: need u next saturday, bring the trailer<br>person_ids: person:merrow, person:odum<br>channels: SMS<br>window: "At 6:45 p.m. on October 24, 2025" (America/Denver, local wall clock) | fail | Sent 7:45:30 p.m. MDT Oct 24; 6:45:30 PM is Item 3's UTC-7 print. |  |
| C16 | `record_time` | yes | person_ids: person:odum<br>account_ids: acct:item3:SMS:+17205550186<br>channels: call<br>duration_s: 70, 110<br>window: "Within an hour after the SHOP BURGLARY (9:40 to 10:40 p.m., November 14, 2025)" (America/Denver, local wall clock) | pass | 10:07:15 p.m. MST, 92 s, from +17205550186. | [ ] |
| C17 | `sender` | yes | quoted_text: last two are in the van<br>person_ids: person:merrow<br>channels: Signal | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: last two are in the van<br>person_ids: person:merrow, person:varga<br>channels: Signal<br>window: "In the hour after the clocks went back that night (1 to 2 a.m. MST, November 2, 2025)" (America/Denver, local wall clock) | pass | 1:34:50 a.m. MST (08:34:50 UTC); the first 1 a.m. hour is 07:00 to 08:00 UTC. |  |
| C18 | `record_time` | yes | person_ids: person:odum<br>account_ids: acct:item2:SMS:+17205550129<br>channels: call<br>window: "Within half an hour after the STOP (3:10 to 3:40 p.m., November 19, 2025)" (America/Denver, local wall clock) | inconclusive | No call with the FENCE's number; the 3:22 p.m. call is to Item 3's 'Jory', +17205550181. | [ ] |
| C19 | `sender` | yes | quoted_text: found 6 tall ones in the back row<br>person_ids: person:merrow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: found 6 tall ones in the back row<br>person_ids: person:merrow, person:varga<br>channels: SMS<br>window: "On October 14, 2025" (America/Denver, local wall clock) | pass | 12:40 p.m. MDT Oct 14. |  |
|  | `meaning` | yes | quoted_text: found 6 tall ones in the back row<br>person_ids: person:merrow, person:varga<br>channels: SMS<br>window: "On October 14, 2025" (America/Denver, local wall clock) | - | 'the emtbs?' / 'ya electric mountain bikes, all 6' in the same exchange. |  |
| C20 | `sender` | yes | quoted_text: the cold ones are in the garage<br>person_ids: person:merrow<br>channels: SMS | pass | Both copies of the words (to VARGA and to 'Arlo') came from MERROW. | [ ] |
|  | `record_time` | yes | quoted_text: the cold ones are in the garage<br>person_ids: person:merrow, person:varga<br>channels: SMS<br>window: "On November 3, 2025" (America/Denver, local wall clock) | pass | 8:30 p.m. MST Nov 3; Item 2 prints 11/4 3:30:25 AM(UTC+0). |  |
|  | `meaning` | yes | quoted_text: the cold ones are in the garage<br>person_ids: person:merrow, person:varga<br>channels: SMS<br>window: "On November 3, 2025" (America/Denver, local wall clock) | - | Whether 'the cold ones' are e-bikes without batteries; nothing fixes it. |  |
| C21 | `sender` | yes | quoted_text: the shop on larch closes at 9 on fridays<br>person_ids: person:odum<br>channels: SMS | fail | VARGA sent it to ODUM. | [ ] |
|  | `record_time` | yes | quoted_text: the shop on larch closes at 9 on fridays<br>channels: SMS<br>window: "On November 12, 2025" (America/Denver, local wall clock) | pass | 5:10 p.m. MST Nov 12. |  |
|  | `meaning` | yes | quoted_text: the shop on larch closes at 9 on fridays<br>channels: SMS | - | That the words tell when the BIKE SHOP would be empty. |  |
| C22 | `sender` | yes | quoted_text: grab the pizzas from the container<br>person_ids: person:merrow<br>channels: Telegram | pass | TOBY is MERROW; outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: grab the pizzas from the container<br>person_ids: person:merrow, person:odum<br>channels: Telegram<br>window: "The next evening (November 4, 2025, 5 p.m. to midnight)" (America/Denver, local wall clock) | pass | 'The next evening' follows C20's November 3. 6:40 p.m. MST Nov 4. |  |
|  | `meaning` | yes | quoted_text: grab the pizzas from the container<br>person_ids: person:merrow, person:odum<br>channels: Telegram | - | The Nov 3 'on here we call them pizzas' fixes 'pizzas'. |  |
| C23 | `sender` | yes | quoted_text: the 4 skinnies are at the dock<br>account_ids: acct:item2:SMS:+17205550186<br>channels: SMS | pass | Incoming on Item 2 from the BURNER (paragraph 3). | [ ] |
|  | `record_time` | yes | quoted_text: the 4 skinnies are at the dock<br>person_ids: person:varga<br>account_ids: acct:item2:SMS:+17205550186<br>channels: SMS<br>window: "Three days before the STOP (November 16, 2025)" (America/Denver, local wall clock) | pass | 11:05 a.m. MST Nov 16. |  |
|  | `meaning` | yes | quoted_text: the 4 skinnies are at the dock<br>person_ids: person:varga<br>account_ids: acct:item2:SMS:+17205550186<br>channels: SMS<br>window: "Three days before the STOP (November 16, 2025)" (America/Denver, local wall clock) | - | 'the pindlewick road bikes?' / 'ya the carbon ones from friday, all 4' after it fix the meaning. |  |
| C24 | `sender` | yes | quoted_text: cal is getting nervous<br>person_ids: person:varga<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: cal is getting nervous<br>person_ids: person:varga, person:merrow<br>channels: SMS<br>window: "Two days after the STOP (November 21, 2025)" (America/Denver, local wall clock) | pass | 8:20 p.m. MST Nov 21. |  |
|  | `meaning` | yes | quoted_text: cal is getting nervous<br>person_ids: person:varga, person:merrow<br>channels: SMS | - | Which Cal; not fixed. |  |
| C25 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:merrow, person:varga<br>channels: Signal<br>expected_count: 7<br>count_op: eq<br>each_way: True<br>window: "Between October 13 and October 19, 2025" (America/Denver, local wall clock) | pass | Seven on Denver dates; printed dates give eight. | [ ] |
| C26 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:odum, person:varga<br>channels: Telegram<br>expected_count: 5<br>count_op: eq<br>each_way: True<br>window: "From November 3 through November 9, 2025" (America/Denver, local wall clock) | pass | Five on Item 3; Item 2 holds six. | [ ] |
| C27 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:merrow, person:varga<br>channels: SMS<br>expected_count: 4<br>count_op: eq<br>each_way: True<br>window: "On November 14, 2025" (America/Denver, local wall clock) | fail | Six on the Denver day. | [ ] |
| C28 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:odum<br>account_ids: acct:item3:SMS:+17205550186<br>channels: SMS<br>expected_count: 5<br>count_op: eq<br>sent_by: person:odum<br>window: "In the five days before the LOCKER BURGLARY (Monday, October 27 to Friday, October 31, 2025)" (America/Denver, local wall clock) | pass | Five from ODUM to the BURNER on Item 3 (the ONEPLUS). | [ ] |
| C29 | `message_count` | yes | device_ids: dev:item1<br>person_ids: person:merrow, person:odum<br>channels: Telegram<br>expected_count: 5<br>count_op: ge<br>window: "Between November 10 and November 13, 2025" (America/Denver, local wall clock) | inconclusive | Three on the SAMSUNG (Item 1); fewer than claimed is never a fail. | [ ] |
| C30 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:merrow, person:varga<br>channels: Signal<br>expected_count: 12<br>count_op: ge<br>each_way: True<br>window: "On the night of the LOCKER BURGLARY, between 11 p.m. and 3 a.m." (America/Denver, local wall clock) | pass | Twelve in the five real hours (05:00 to 10:00 UTC) on the iPHONE. | [ ] |
| C31 | `no_contact` | yes | person_ids: person:merrow, person:odum<br>window: "on October 23, 2025" (America/Denver, local wall clock) | fail | The 12:30 and 12:40 a.m. MDT texts. | [ ] |
| C32 | `no_contact` | yes | person_ids: person:varga, person:merrow<br>window: "between November 22 and November 24, 2025" (America/Denver, local wall clock) | fail | The Nov 23 Signal exchange. No channel: the claim says any kind. | [ ] |
| C33 | `no_contact` | yes | person_ids: person:odum<br>account_ids: acct:item2:SMS:+17205550129<br>window: "between November 1 and November 30, 2025" (America/Denver, local wall clock) | inconclusive | None found; curated reports. Item 3's 'Jory' is another number. | [ ] |
| C34 | `no_contact` | yes | person_ids: person:odum, person:varga<br>window: "Once the clocks had gone back that night, for the next hour (1 to 2 a.m. MST, November 2, 2025)" (America/Denver, local wall clock) | inconclusive | None in the hour; the 1:25 a.m. WhatsApp is in the first, MDT, hour. | [ ] |
| C35 | `no_contact` | yes | person_ids: person:varga, person:odum<br>window: "On the three days after the day of the SHOP BURGLARY (November 15 to 17, 2025)" (America/Denver, local wall clock) | fail | CAL is ODUM (paragraph 2). WhatsApp on Nov 15 and 16. | [ ] |
| C36 | `no_contact` | yes | person_ids: person:merrow, person:odum<br>device_ids: dev:item1<br>window: "From the day after the STOP to the end of November (November 20 to 30, 2025)" (America/Denver, local wall clock) | inconclusive | None on Item 1 (the SAMSUNG); curated. Item 3 holds a Nov 22 text. | [ ] |
| C37 | `sender` | yes | quoted_text: 1400 each, dont go under 1200<br>person_ids: person:varga<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: 1400 each, dont go under 1200<br>person_ids: person:varga, person:odum<br>channels: WhatsApp<br>window: "On November 5, 2025" (America/Denver, local wall clock) | pass | 1:06 p.m. MST Nov 5. |  |
|  | `role` | yes | person_ids: person:varga, person:odum<br>channels: WhatsApp | - | That VARGA set the asking price: ODUM asked her what to ask and took her figure. |  |
| C38 | `sender` | yes | quoted_text: friday 9:30, back door<br>person_ids: person:odum<br>channels: SMS | fail | MERROW sent it. | [ ] |
|  | `record_time` | yes | quoted_text: friday 9:30, back door<br>channels: SMS<br>window: "On November 13, 2025" (America/Denver, local wall clock) | pass | 7:40 p.m. MST Nov 13. |  |
|  | `role` | yes | person_ids: person:odum | - | That ODUM set the time. |  |
| C39 | `role` | yes | person_ids: person:merrow, person:varga | - | That MERROW recruited VARGA; VARGA offered herself. | [ ] |
| C40 | `sender` | yes | quoted_text: u handle marketplace, i do insta<br>person_ids: person:varga<br>channels: WhatsApp | pass | SUBJECT-2 is VARGA; the only copy is incoming on Item 3. No phone named. | [ ] |
|  | `role` | yes | person_ids: person:varga, person:odum<br>quoted_text: u handle marketplace, i do insta<br>channels: WhatsApp | - | That VARGA gave ODUM the marketplace listings: her assignment and his 'ok i got marketplace'. |  |
| C41 | `sender` | yes | quoted_text: start with 12 and 14, then the cage<br>person_ids: person:varga<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: start with 12 and 14, then the cage<br>person_ids: person:varga, person:odum<br>channels: WhatsApp<br>window: "On the Saturday morning before the LOCKER BURGLARY (November 1, 2025, 5 a.m. to noon)" (America/Denver, local wall clock) | fail | Sent 11:20:30 p.m. MDT Friday Oct 31; Item 2 prints 11/1 5:20:30 AM(UTC+0). |  |
|  | `role` | yes | person_ids: person:varga | - | That VARGA chose the lockers. |  |
| C42 | `role` | yes | person_ids: person:varga<br>window: "In the hour before the SHOP BURGLARY (8:40 to 9:40 p.m., November 14, 2025)" (America/Denver, local wall clock) | - | That VARGA kept watch and reported to ODUM; the only 'staff all gone' text went to Item 2's 'Cal'. | [ ] |
| C43 | `sender` | yes | quoted_text: grain elevator lot thursday 7pm<br>person_ids: person:merrow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: grain elevator lot thursday 7pm<br>person_ids: person:merrow, person:odum<br>channels: SMS<br>window: "On October 28, 2025" (America/Denver, local wall clock) | pass | 12:05 p.m. MDT Oct 28. |  |
|  | `weekday_date` | yes | quoted_text: grain elevator lot thursday 7pm<br>channels: SMS<br>window: "Thursday, October 30, 2025" (America/Denver, local wall clock) | pass | 'thursday' sent on Tuesday Oct 28 is Oct 30. |  |
|  | `event` | yes | person_ids: person:merrow, person:odum<br>channels: SMS<br>window: "On October 28, 2025" (America/Denver, local wall clock) | - | That they arranged it: ODUM's 'bet'. |  |
| C44 | `sender` | yes | quoted_text: need the road bikes out of unit 41 by thurs<br>person_ids: person:varga<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `sender` | yes | quoted_text: ok ill move them tonight<br>person_ids: person:merrow<br>channels: SMS | pass | MERROW's answer, outgoing on Item 1. |  |
|  | `record_time` | yes | quoted_text: need the road bikes out of unit 41 by thurs<br>person_ids: person:varga, person:merrow<br>channels: SMS<br>window: "On November 18, 2025" (America/Denver, local wall clock) | pass | 10:30 a.m. MST Nov 18. |  |
| C45 | `record_time` | yes | person_ids: person:varga, person:odum<br>channels: call<br>duration_s: 420, 540<br>window: "On November 4, 2025" (America/Denver, local wall clock) | inconclusive | Their only call that day lasted 50 s; the 482 s call is with Item 2's 'Cal'. | [ ] |
| C46 | `sender` | yes | quoted_text: back at the yard<br>person_ids: person:odum<br>channels: WhatsApp | pass | The COURIER's WhatsApp, outgoing on Item 3. No phone named. | [ ] |
|  | `record_time` | yes | quoted_text: back at the yard<br>person_ids: person:odum, person:varga<br>channels: WhatsApp<br>window: "Shortly before 6 a.m. that morning (November 2, 2025, 5:30 to 6 a.m.)" (America/Denver, local wall clock) | pass | 5:48:20 a.m. MST; 'that morning' follows C05's November 2. |  |
| C47 | `sender` | yes | quoted_text: sent u 400 for friday, check ur bank<br>person_ids: person:merrow<br>channels: Telegram | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: sent u 400 for friday, check ur bank<br>person_ids: person:merrow, person:odum<br>channels: Telegram<br>window: "Two days after the SHOP BURGLARY (November 16, 2025)" (America/Denver, local wall clock) | pass | 2:20 p.m. MST Nov 16. |  |
|  | `event` | yes | person_ids: person:merrow, person:odum<br>channels: Telegram<br>window: "Two days after the SHOP BURGLARY (November 16, 2025)" (America/Denver, local wall clock) | - | That he was paid: reading 'sent u 400 for friday' as money sent to him and 'got the 400, thx' as receipt. |  |
| C48 | `no_contact` | yes | person_ids: person:varga, person:odum<br>channels: call<br>window: "In the seven days starting the day after the STOP (November 20 to 26, 2025)" (America/Denver, local wall clock) | fail | VARGA's Nov 23 call, held on Item 3's log only. | [ ] |

Gaps:

- C03: That VARGA received it is shown by the time row's phone (Item 2), not by a party.
- C08: Unproven, not contradicted: the contact check never fails on a missing entry (contact lists are edited, and a curated report may leave entries out), so Item 1's 'Cal' holding +17205550153 does not rule out an entry 'Cal' with +17205550168.
- C10: same_account passes because the account's display name is the first name it shows ('Ines V'), and later rows' sender cells show 'vee.rides'. No row tests when the name changed: 'from November 10' rests on the printed rows (last 'Ines V' 7:30 p.m. Nov 8, first 'vee.rides' 4:45 p.m. Nov 10).
- C12: That the sender was shown as 'Toby' is in the claim's words; the sender row tests the account, not the saved name.
- C13: No template says who placed a call; Item 1 logs it as outgoing, as the claim says.
- C14: No template says who placed a call; Item 2 logs it as outgoing, as the claim says.
- C16: No template says who placed a call; Item 3 logs it as incoming from the BURNER, as the claim says.
- C39: The claim quotes nothing and names no time, so no check applies; only the expert can decide it.
- C40: The claim names no time, so no time row; the exchange is on Nov 3.
- C42: The claim paraphrases a text without quoting it; no check applies.
- C43: 'The lot by the grain elevator' is tested only as words inside the quote, which the sender check matches verbatim; whether anyone met there is not tested.
- C46: 'Let SUBJECT-2 know' rests on the sending alone: the only copy is outgoing on Item 3, and Item 2's report does not hold it, so no record shows she received it.
- C48: The no_contact row on calls has no direction, so any call between them fails it. 'Stopped phoning' is about calls SUBJECT-2 placed; the fail is right because the Nov 23 call is VARGA's, logged on Item 3 as incoming from her number. No template says who placed a call.

Signed: ____________________  Date: __________
