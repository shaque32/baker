# case06 signing sheet: DRAFT key and assumption sheet

About twenty minutes. Each claim: the draft verdict, its wording and hazard, the
one-line reason, and the assumption rows the pipeline runs on. Tick or correct each
line; the full reasoning and every cited row are in `ANSWER_KEY_DRAFT.md`. Nothing here
is gold until a human copies the approved lines into `eval/gold/case06/` (`gold.jsonl`,
`assumptions.jsonl`) with `labeled_by` set to the approver.

Read the affidavit first (`affidavit_draft.md`, 20 paragraphs). Its
definitions: SKIP = CC-1 = VARLOW (Item 1, the GALAXY); CC-2 = COYLE (Item 2,
no defined name); DUKE = the HAULER = CC-3 = PELLOQUIN (Item 3, the KYOCERA); the
SPARE LINE is +13605550163 (VARLOW's); the WORK NUMBER is +13605550192 (PELLOQUIN's);
the BROKER used +12535550148 and the KELPWISE ACCOUNT (Telegram user id 8820450); the
HARBOR THEFT was the night of Friday, February 28 into March 1, 2025; the TRANSFER was
the night of Saturday, March 8 into March 9, 2025, when the clocks went forward; the
KITTIWAKE THEFT was at about 11:15 p.m. on Thursday, March 13, 2025; the SURVEILLANCE
ran from Monday, March 17 through Wednesday, March 19, 2025; the RECOVERY was at 10:40
a.m. on Tuesday, March 25, 2025.

Every person, phone number, Instagram handle, Telegram name and numeric id, place,
business and event in the reports and the affidavit is invented.

What to decide:

1. Is each verdict right? Absence claims are never supported on a curated report
   (reading rule 9); a meaning or role is supported only where the conversation fixes it
   (rule 10). C05, C20, C24, C39, C42 and C47 are the closest calls. C05 is supported on
   VARLOW's own number giving the HAULER the SPARE LINE as his new number (an authorship
   row you decide); if you do not accept that tie, C05 goes to unproven. C06, C14, C30,
   C34 and C46 read times around the hour that never came (rule 5).
2. Is each hazard a fair wrong reading, and does the sheet name only the right person,
   account, phone and window?
3. Are the assumption rows the right reading of the claim? `expected_check` is what the
   deterministic check should find; a test runs the checks against it. A dash means no
   check exists, so only expert review covers that row.
4. Are the six windows that follow no convention (listed below) the ones a careful
   examiner would give?
5. Do case.json's defined names and events match the affidavit (listed below)?

## Windows that follow no convention

Every other window follows the brief's conventions (reading rule 2), and
`tests/test_synthetic_case06.py` recomputes each one from the claim's words. These are
the careful examiner's windows instead; the row's note gives the same reasoning. C30
is not listed: it is the 'between' convention (11 p.m. through the whole 4:00 a.m.
minute) on the night the TRANSFER began, March 8 into 9.

| Claim | Template | Window as written | UTC | Reasoning |
|---|---|---|---|---|
| C16 | `record_time` | Within an hour after the KITTIWAKE THEFT (11:15 p.m. on March 13 to 12:15 a.m. on March 14, 2025) | 2025-03-14T06:15:00Z to 2025-03-14T07:14:59.999999Z | 'Within an hour after' the KITTIWAKE THEFT, which paragraph 6 puts at about 11:15 p.m. on March 13: the hour from 11:15 p.m. to 12:15 a.m. The 'about' in the event's time is not widened; the theft's stated time is the anchor. |
| C18 | `record_time` | Within half an hour after the RECOVERY (10:40 to 11:10 a.m., March 25, 2025) | 2025-03-25T17:40:00Z to 2025-03-25T18:09:59.999999Z | 'Within half an hour after' the RECOVERY, which paragraph 7 puts at 10:40 a.m. on March 25: 10:40 to 11:10 a.m. |
| C22 | `record_time` | The next morning (March 4, 2025, 5 a.m. to noon) | 2025-03-04T13:00:00Z to 2025-03-04T19:59:59.999999Z | 'The next morning' after March 3 (the sentence before, C20): March 4, morning read as 5 a.m. to noon. |
| C22 | `meaning` | The next morning (March 4, 2025, 5 a.m. to noon) | 2025-03-04T13:00:00Z to 2025-03-04T19:59:59.999999Z | 'The next morning' after March 3 (the sentence before, C20): March 4, morning read as 5 a.m. to noon. |
| C34 | `no_contact` | In the hour before the clocks went forward that night (1 to 2 a.m. PST, March 9, 2025) | 2025-03-09T09:00:00Z to 2025-03-09T09:59:59.999999Z | 'The hour before the clocks went forward that night' (the night of the TRANSFER): the clocks jumped from 2 to 3 a.m. on March 9, so the hour is 1 to 2 a.m. PST, 09:00 to 10:00 UTC (written as 1 a.m. to 3 a.m. wall clock, the same instants). |
| C41 | `record_time` | On the night of the KITTIWAKE THEFT (6 p.m. on March 13 to 6 a.m. on March 14, 2025) | 2025-03-14T01:00:00Z to 2025-03-14T12:59:59.999999Z | 'The night of' the KITTIWAKE THEFT (Thursday, March 13): 6 p.m. on March 13 to 6 a.m. on March 14. |
| C48 | `no_contact` | After the SURVEILLANCE ended (from midnight on March 20, 2025, until the RECOVERY at 10:40 a.m. on March 25, 2025) | 2025-03-20T07:00:00Z to 2025-03-25T17:39:59.999999Z | 'After the SURVEILLANCE ended' (its last day is Wednesday, March 19) 'until the RECOVERY' (10:40 a.m. on March 25): midnight starting March 20 to 10:40 a.m. on March 25. |

## Names and events the affidavit defines (case.json)

The eval's case setup enters these as an expert would. Each is defined once in the
affidavit, and no name equals another or a phone owner's name, with or without 'the'.
The BROKER is a person who owns no seized phone, so it is in no list.

| Kind | For | Names |
|---|---|---|
| aliases | Item 1 owner, Emmett Varlow | CC-1, SKIP |
| aliases | Item 2 owner, Renata Coyle | CC-2 |
| aliases | Item 3 owner, Duncan Pelloquin | CC-3, DUKE, the HAULER |
| phone names | Item 1 | the GALAXY |
| phone names | Item 2 | none |
| phone names | Item 3 | the KYOCERA |
| number names | +1 (360) 555-0163 | the SPARE LINE |
| number names | +1 (360) 555-0192 | the WORK NUMBER |
| number names | 8820450 | the KELPWISE ACCOUNT |
| event | 2025-02-28 to 2025-03-01 | HARBOR THEFT: "four outboard motors and two chartplotters were taken from boats moored at Sculpin Harbor Marina on Tidewrack Road" |
| event | 2025-03-08 to 2025-03-09 | TRANSFER: "VARLOW and PELLOQUIN moved the motors from COYLE's boathouse on Halyard Point to a barn on Gannet Lane" |
| event | 2025-03-13 | KITTIWAKE THEFT: "two outboard motors and a pallet of marine batteries were taken from the fenced yard of Kittiwake Marine Supply on Ferrule Street" |
| event | 2025-03-17 to 2025-03-19 | SURVEILLANCE: "deputies watched COYLE's boathouse on Halyard Point" |
| event | 2025-03-25 | RECOVERY: "deputies opened unit 17 at Port Wendle Mini Storage and recovered three of the outboard motors" |

## Second read (pending)

No second read yet. Before signing, a second, blind reviewer reads the draft key and
sheet against rules 0.4.0 and the three reports; their findings go here, one line
each: fixed (the key, the sheet or the wording changed), or kept and why.

## Aliases inside quotes

An alias (case.json `aliases`) is matched whole and in any case, so it also matches
these names inside quotes. The wording stays: the match is real product behaviour.
Check where each one points.

- C08: DUKE matches the quoted contact name "Duke" and points to PELLOQUIN. Right person, other number: Item 1's 'Duke' holds PELLOQUIN's own +13605550138; the claim's +13605550192 is saved as 'Duke work'.
- C09: SKIP matches the quoted Telegram name "Skip" and points to VARLOW. Wrong: on Item 3, Telegram 'Skip' is Skip Tennant, user id 8820484. ("Em V" matches no alias.)
- C12: DUKE matches the quoted sender name "Duke" and points to PELLOQUIN. Wrong: on Item 2, 'Duke' is Duke Marchetti, +12535550151. The claim's own 'the HAULER' is PELLOQUIN, rightly.
- C24: DUKE matches "duke" in the quote "duke wants out" and points to PELLOQUIN. Not fixed: Item 2 also saves Duke Marchetti as 'Duke' (+12535550151), and the conversation does not say which Duke is meant. The claim's own 'the HAULER' is PELLOQUIN.

## Counts

### Claim type x draft verdict

| Type | supported | contradicted | unproven | Total |
|---|---|---|---|---|
| communication | 4 | 1 | 1 | 6 |
| identity | 3 | 2 | 1 | 6 |
| timing | 3 | 2 | 1 | 6 |
| content_meaning | 3 | 1 | 2 | 6 |
| count | 4 | 1 | 1 | 6 |
| absence | 0 | 3 | 3 | 6 |
| role | 3 | 1 | 2 | 6 |
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
| plain | 11 | 8 | 5 |
| affidavit | 13 | 4 | 7 |

### Hazards by kind

| Hazard | What the wrong reading is | Claims | supported | contradicted | unproven |
|---|---|---|---|---|---|
| same_name | a second person with the same first name or nickname | 6 | 1 | 2 | 3 |
| second_number | a second number or account for the same person | 8 | 6 | 1 | 1 |
| second_phone | a second phone that could be meant | 8 | 4 | 1 | 3 |
| near_window | a near-miss window: UTC against local time across midnight, the hour that never came when the clocks went forward, an adjacent day, or Item 3's fixed UTC-8 print | 12 | 5 | 6 | 1 |
| contact_name | one contact name saved on two phones for two people | 5 | 2 | 1 | 2 |
| similar_quote | similar words in another thread | 8 | 5 | 1 | 2 |
| none | no wrong reading planted | 1 | 1 | 0 | 0 |

Claims with a planted wrong reading: 47 of 48.

### Claims without a sheet

None: every claim has rows in `draft_assumptions.jsonl`.

### Claims with no checkable core row

Their only core rows are ones no deterministic check tests, so only expert review
covers them:

- C39 (role)

## Claims

| Claim | Type | Wording | Hazard | Draft verdict | Reason in one line | Agree? |
|---|---|---|---|---|---|---|
| C01 | communication | plain | near_window | **supported** | Sent 8:15 p.m. PST Feb 19; Item 1 prints Feb 20 (UTC+0). | [ ] |
| C02 | communication | plain | none | **supported** | Observed on Items 2 and 3, Mar 4. | [ ] |
| C03 | communication | plain | similar_quote | **contradicted** | Sent by VARLOW, not COYLE; her 'white cowls' text went to Item 2's 'Duke'. | [ ] |
| C04 | communication | affidavit | similar_quote | **unproven** | No such text; VARLOW wrote 'keep the motors wrapped till the paint cures' to his foreman. | [ ] |
| C05 | communication | affidavit | second_number | **supported** | The SPARE LINE's text on Item 3, 7:15 p.m. Feb 26; VARLOW's own number gave the HAULER that number on Feb 20. | [ ] |
| C06 | communication | affidavit | second_phone | **supported** | Item 3 (the KYOCERA) received it at 3:41 a.m. PDT Mar 9; Item 2 lacks it. | [ ] |
| C07 | identity | plain | contact_name | **supported** | Item 1's 'Lars' holds +12535550148; Item 3's 'Lars' is another number. | [ ] |
| C08 | identity | plain | second_number | **unproven** | Item 1's 'Duke' holds 0138; 0192 is saved as 'Duke work'. Not shown (contact lists edit). | [ ] |
| C09 | identity | plain | same_name | **contradicted** | Two Telegram ids: 'Skip' 8820484 (Skip Tennant), 'Em V' 8820411. | [ ] |
| C10 | identity | affidavit | contact_name | **supported** | Item 2's 'Captain' holds +13605550163; she wrote 'saved u as captain lol'. | [ ] |
| C11 | identity | affidavit | second_number | **supported** | One Telegram id, 8820422 (Item 2's own); Item 3 shows 'Ren C' to Mar 11, 'harborlights' from Mar 12. | [ ] |
| C12 | identity | affidavit | contact_name | **contradicted** | Item 2's 'Duke' (+12535550151) sent it, not PELLOQUIN's +13605550138. | [ ] |
| C13 | timing | plain | near_window | **supported** | 9:12 p.m. PST, 236 s; Item 1 prints 9:09 PM(UTC+0) for a 1:09 p.m. call of 38 s. | [ ] |
| C14 | timing | plain | near_window | **supported** | 3:14 a.m. PDT, 118 s; Item 3 prints 2:14 AM(UTC-8), and 3:12 AM for a 31 s call. | [ ] |
| C15 | timing | plain | near_window | **contradicted** | Sent 9:40 p.m. PDT Mar 12; 8:40 PM is Item 3's UTC-8 print. | [ ] |
| C16 | timing | affidavit | second_number | **supported** | 11:48 p.m., 68 s, from the WORK NUMBER (Item 1). | [ ] |
| C17 | timing | affidavit | near_window | **contradicted** | Sent 4:31 p.m. PDT Mar 15; 11:31 PM is Item 1's UTC print. | [ ] |
| C18 | timing | affidavit | second_phone | **unproven** | No call on Item 1; the 10:55 a.m. call is on Item 3's log only. | [ ] |
| C19 | content_meaning | plain | similar_quote | **supported** | 'the outboards?' / 'ya 4 outboards, two are 150s' fix the meaning. | [ ] |
| C20 | content_meaning | plain | similar_quote | **unproven** | Observed; 'the sleeping bags' is not fixed (and she wrote the same words to her mother). | [ ] |
| C21 | content_meaning | plain | near_window | **contradicted** | Sent 6:05 p.m. PDT Mar 18; Item 1 prints Mar 19 (UTC+0). | [ ] |
| C22 | content_meaning | affidavit | similar_quote | **supported** | Mar 4 morning; 'ya the soup cans. all 6 fuel tanks' the evening before fixes it. | [ ] |
| C23 | content_meaning | affidavit | second_number | **supported** | 'the 150s?' / 'ya both 150s, locked up' fix it. | [ ] |
| C24 | content_meaning | affidavit | same_name | **unproven** | Observed; which Duke is not fixed (Item 2's 'Duke' wanted out that morning). | [ ] |
| C25 | count | plain | near_window | **supported** | 8 on Pacific dates; printed (UTC) dates give 9. | [ ] |
| C26 | count | plain | second_phone | **supported** | 6 on Item 3; Item 2 has 7. | [ ] |
| C27 | count | plain | near_window | **contradicted** | 6 on Mar 12 Pacific; Item 3's printed Mar 12 gives 4. | [ ] |
| C28 | count | affidavit | second_number | **supported** | 7 texts HAULER to the SPARE LINE, Mar 17-19 on Item 3. | [ ] |
| C29 | count | affidavit | second_phone | **unproven** | 4 on Item 1 (curated); Item 3 holds 6. | [ ] |
| C30 | count | affidavit | near_window | **supported** | 11 in 11 p.m.-4 a.m. (four real hours, DST began); five hours at one offset gives 13. | [ ] |
| C31 | absence | plain | near_window | **contradicted** | 6:25 p.m. PST Feb 18 text; Item 1 prints Feb 19. | [ ] |
| C32 | absence | plain | second_number | **contradicted** | WhatsApp exchange on Mar 27. | [ ] |
| C33 | absence | plain | contact_name | **unproven** | No record with 0148; Item 3's 'Lars' is 0173. Curated, so not shown. | [ ] |
| C34 | absence | affidavit | near_window | **unproven** | None 1-2 a.m. PST; WhatsApps at 12:52 a.m. PST and 3:05 a.m. PDT. | [ ] |
| C35 | absence | affidavit | same_name | **contradicted** | COYLE-PELLOQUIN texts on Mar 26. | [ ] |
| C36 | absence | affidavit | second_phone | **unproven** | None on Item 1 (curated); Item 3 holds a Mar 28 WhatsApp. | [ ] |
| C37 | role | plain | similar_quote | **supported** | He asked the price, COYLE set it, he took it. | [ ] |
| C38 | role | plain | near_window | **contradicted** | Sent 6:15 p.m. PDT Mar 21; Item 1 prints Mar 22 (UTC+0). | [ ] |
| C39 | role | plain | same_name | **unproven** | PELLOQUIN offered himself to VARLOW; COYLE asked Item 2's 'Duke'. | [ ] |
| C40 | role | affidavit | second_phone | **supported** | His instruction and 'got it, nobody else', on Item 3 only. | [ ] |
| C41 | role | affidavit | similar_quote | **supported** | 'ill watch the road', 'patrol car just passed, wait', 'clear, go' on Signal. | [ ] |
| C42 | role | affidavit | contact_name | **unproven** | Sent to Item 3's 'Lars' (his cousin), not the BROKER; no sale shown. | [ ] |
| C43 | event | plain | similar_quote | **supported** | Proposal and 'ok' on Mar 18; Thursday is Mar 20. | [ ] |
| C44 | event | plain | same_name | **supported** | Request and 'ok ill clear it friday' on Mar 4. | [ ] |
| C45 | event | plain | same_name | **unproven** | Only a 45 s call; the ten-minute call is with Item 2's 'Duke'. | [ ] |
| C46 | event | affidavit | second_phone | **supported** | 4:47 a.m. PDT Mar 9, on Item 3 only. | [ ] |
| C47 | event | affidavit | second_number | **supported** | Offer, 'deal, 3k for both, cash' and 'ok 3k' with Telegram 8820450 on Mar 3. | [ ] |
| C48 | event | affidavit | second_phone | **contradicted** | COYLE called PELLOQUIN on Mar 22, on Item 3's log only. | [ ] |

## Assumption rows

One table for the whole sheet; the claim texts are in `affidavit_draft.md` and
`ANSWER_KEY_DRAFT.md`. Gaps (what the rows leave to the expert) follow the table.

| Claim | Template | Core | Parameters | Check | Why | Agree? |
|---|---|---|---|---|---|---|
| C01 | `sender` | yes | quoted_text: check the dinghy dock after 9, its quiet<br>person_ids: person:varlow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: check the dinghy dock after 9, its quiet<br>person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On February 19, 2025" (America/Los_Angeles, local wall clock) | pass | 8:15 p.m. PST Feb 19; Item 1 prints 2/20 4:15:40 AM(UTC+0). |  |
| C02 | `sender` | yes | quoted_text: hitch key is on the nail in the shed<br>person_ids: person:coyle<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: hitch key is on the nail in the shed<br>person_ids: person:coyle, person:pelloquin<br>channels: WhatsApp<br>window: "On March 4, 2025" (America/Los_Angeles, local wall clock) | pass | 4:10 p.m. PST Mar 4. |  |
| C03 | `sender` | yes | quoted_text: the white cowls are off, come see tonight<br>person_ids: person:coyle<br>channels: SMS | fail | Both copies came from VARLOW's +13605550114, not from COYLE. | [ ] |
|  | `record_time` | yes | quoted_text: the white cowls are off, come see tonight<br>person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On March 6, 2025" (America/Los_Angeles, local wall clock) | pass | 11:45 a.m. PST Mar 6, between their numbers. |  |
| C04 | `sender` | yes | quoted_text: the motors stay wrapped till the heat dies down<br>person_ids: person:varlow<br>channels: SMS | inconclusive | No message with these words on any phone. | [ ] |
|  | `record_time` | yes | quoted_text: the motors stay wrapped till the heat dies down<br>person_ids: person:varlow, person:pelloquin<br>channels: SMS<br>window: "The day after the TRANSFER (Monday, March 10, 2025)" (America/Los_Angeles, local wall clock) | inconclusive | The TRANSFER ended on March 9, so the day after is March 10. Not found. |  |
| C05 | `sender` | yes | quoted_text: bring the long straps and the dolly<br>account_ids: acct:item3:SMS:+13605550163<br>channels: SMS | pass | Incoming on Item 3 from the SPARE LINE (paragraph 3). | [ ] |
|  | `record_time` | yes | quoted_text: bring the long straps and the dolly<br>person_ids: person:pelloquin<br>account_ids: acct:item3:SMS:+13605550163<br>channels: SMS<br>window: "Two days before the HARBOR THEFT (Wednesday, February 26, 2025)" (America/Los_Angeles, local wall clock) | pass | The HARBOR THEFT began on February 28. 7:15 p.m. PST Feb 26. |  |
|  | `authorship` | yes | quoted_text: bring the long straps and the dolly<br>person_ids: person:varlow<br>account_ids: acct:item3:SMS:+13605550163<br>channels: SMS | - | That VARLOW used the SPARE LINE: paragraph 3, and his own number's 'new number for boat stuff is 360 555 0163. this one stays personal' to the HAULER (Items 1 and 3). Core: the expert decides it. |  |
| C06 | `sender` | yes | quoted_text: leave the trailer at the barn, not the boathouse<br>person_ids: person:coyle<br>channels: Telegram | pass | CC-2 is COYLE; her Telegram (8820422) sent it. | [ ] |
|  | `record_time` | yes | quoted_text: leave the trailer at the barn, not the boathouse<br>person_ids: person:coyle, person:pelloquin<br>device_ids: dev:item3<br>channels: Telegram<br>window: "At about 3:40 a.m. on March 9, 2025" (America/Los_Angeles, local wall clock) | pass | The KYOCERA is Item 3 (paragraph 2). 3:41 a.m. PDT Mar 9 (printed 2:41:30 AM(UTC-8)). |  |
| C07 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Lars<br>account_ids: acct:item1:SMS:+12535550148 | pass | Item 1's 'Lars' holds +12535550148. | [ ] |
| C08 | `contact_entry` | yes | device_ids: dev:item1<br>quoted_text: Duke<br>account_ids: acct:item1:SMS:+13605550192 | inconclusive | Item 1's 'Duke' holds +13605550138; a missing entry is never a fail. | [ ] |
| C09 | `same_account` | yes | channels: Telegram<br>handles: Skip, Em V<br>device_ids: dev:item3 | fail | 'Skip' resolves to user id 8820484 and 'Em V' to 8820411. | [ ] |
| C10 | `contact_entry` | yes | device_ids: dev:item2<br>quoted_text: Captain<br>account_ids: acct:item2:SMS:+13605550163 | pass | 'Her phone' is Item 2 (CC-2 is COYLE). | [ ] |
| C11 | `same_account` | yes | channels: Telegram<br>handles: Ren C, harborlights<br>device_ids: dev:item3 | pass | Both names resolve to Telegram user id 8820422 (Item 2's own account). The check resolves names on every phone, not only Item 3; on Telegram only Item 3 shows her account to someone else. | [ ] |
|  | `person_identity` | yes | person_ids: person:coyle<br>account_ids: acct:item2:Telegram:8820422, acct:item3:Telegram:8820422<br>channels: Telegram | - | That user id 8820422 is CC-2's: it is Item 2's own Telegram account (its User Accounts sheet, and the outgoing copies on Item 2), and Item 2 is COYLE's phone (the shared device attribution). Core: the expert decides it. |  |
| C12 | `sender` | yes | quoted_text: the lower unit is shot<br>person_ids: person:pelloquin<br>channels: SMS | fail | The one copy came from +12535550151, Item 2's 'Duke', not from PELLOQUIN. | [ ] |
|  | `record_time` | yes | quoted_text: the lower unit is shot<br>channels: SMS<br>device_ids: dev:item2<br>window: "on March 11, 2025" (America/Los_Angeles, local wall clock) | pass | 9:40 a.m. PDT Mar 11, on Item 2. |  |
| C13 | `record_time` | yes | person_ids: person:varlow, person:pelloquin<br>channels: call<br>duration_s: 180, 300<br>window: "At about 9:10 p.m. on February 21, 2025" (America/Los_Angeles, local wall clock) | pass | 9:12:40 p.m. PST, 236 s. 'About four minutes' is 180 to 300 s. | [ ] |
| C14 | `record_time` | yes | person_ids: person:varlow, person:pelloquin<br>channels: call<br>duration_s: 90, 150<br>window: "At about 3:15 a.m. on March 9, 2025" (America/Los_Angeles, local wall clock) | pass | 3:14:20 a.m. PDT, 118 s. 3:07 to 3:23 a.m. is after the jump, all PDT. | [ ] |
| C15 | `sender` | yes | quoted_text: barn code is 4417 now, dont lose it<br>person_ids: person:pelloquin<br>channels: SMS | pass | Outgoing on Item 3. | [ ] |
|  | `record_time` | yes | quoted_text: barn code is 4417 now, dont lose it<br>person_ids: person:pelloquin, person:varlow<br>channels: SMS<br>window: "At 8:40 p.m. on March 12, 2025" (America/Los_Angeles, local wall clock) | fail | Sent 9:40:15 p.m. PDT; Item 3 prints 8:40:15 PM(UTC-8). |  |
| C16 | `record_time` | yes | person_ids: person:varlow<br>account_ids: acct:item1:SMS:+13605550192<br>channels: call<br>duration_s: 45, 75<br>window: "Within an hour after the KITTIWAKE THEFT (11:15 p.m. on March 13 to 12:15 a.m. on March 14, 2025)" (America/Los_Angeles, local wall clock) | pass | Examiner's window: 'Within an hour after' the KITTIWAKE THEFT, which paragraph 6 puts at about 11:15 p.m. on March 13: the hour from 11:15 p.m. to 12:15 a.m. The 'about' in the event's time is not widened; the theft's stated time is the anchor. 11:48:10 p.m. PDT, 68 s. | [ ] |
| C17 | `sender` | yes | quoted_text: move the trailer behind the barn tonight<br>person_ids: person:varlow<br>channels: WhatsApp | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: move the trailer behind the barn tonight<br>person_ids: person:varlow, person:pelloquin<br>channels: WhatsApp<br>window: "Two days before the SURVEILLANCE began, at about 11:30 p.m. (March 15, 2025)" (America/Los_Angeles, local wall clock) | fail | The SURVEILLANCE began March 17. Sent 4:31 p.m. PDT Mar 15; Item 1 prints 11:31:20 PM(UTC+0). |  |
| C18 | `record_time` | yes | person_ids: person:varlow, person:pelloquin<br>device_ids: dev:item1<br>channels: call<br>window: "Within half an hour after the RECOVERY (10:40 to 11:10 a.m., March 25, 2025)" (America/Los_Angeles, local wall clock) | inconclusive | Examiner's window: 'Within half an hour after' the RECOVERY, which paragraph 7 puts at 10:40 a.m. on March 25: 10:40 to 11:10 a.m. The GALAXY is Item 1; no call there. Item 3 holds one at 10:55 a.m. | [ ] |
| C19 | `sender` | yes | quoted_text: spotted 4 big fish on the north float<br>person_ids: person:varlow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: spotted 4 big fish on the north float<br>person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On February 24, 2025" (America/Los_Angeles, local wall clock) | pass | 11:20 a.m. PST Feb 24. |  |
|  | `meaning` | yes | quoted_text: spotted 4 big fish on the north float<br>person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On February 24, 2025" (America/Los_Angeles, local wall clock) | - | 'the outboards?' / 'ya 4 outboards, two are 150s' in the same exchange. |  |
| C20 | `sender` | yes | quoted_text: keep the sleeping bags dry<br>person_ids: person:coyle<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: keep the sleeping bags dry<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "On March 3, 2025" (America/Los_Angeles, local wall clock) | pass | 2:15 p.m. PST Mar 3. |  |
|  | `meaning` | yes | quoted_text: keep the sleeping bags dry<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "On March 3, 2025" (America/Los_Angeles, local wall clock) | - | Not fixed: VARLOW answered only 'will do'. |  |
| C21 | `sender` | yes | quoted_text: the guard naps after 2, every night<br>person_ids: person:coyle<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: the guard naps after 2, every night<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "On March 19, 2025" (America/Los_Angeles, local wall clock) | fail | Sent 6:05 p.m. PDT Mar 18; Item 1 prints 3/19 1:05:20 AM(UTC+0). |  |
|  | `meaning` | yes | quoted_text: the guard naps after 2, every night<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "On March 19, 2025" (America/Los_Angeles, local wall clock) | - | That the words told him when the yard was unwatched. |  |
| C22 | `sender` | yes | quoted_text: bring the soup cans to the boathouse<br>person_ids: person:varlow<br>channels: Telegram | pass | SKIP is VARLOW; outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: bring the soup cans to the boathouse<br>person_ids: person:varlow, person:pelloquin<br>channels: Telegram<br>window: "The next morning (March 4, 2025, 5 a.m. to noon)" (America/Los_Angeles, local wall clock) | pass | Examiner's window: 'The next morning' after March 3 (the sentence before, C20): March 4, morning read as 5 a.m. to noon. 9:20 a.m. PST Mar 4. |  |
|  | `meaning` | yes | quoted_text: bring the soup cans to the boathouse<br>person_ids: person:varlow, person:pelloquin<br>channels: Telegram<br>window: "The next morning (March 4, 2025, 5 a.m. to noon)" (America/Los_Angeles, local wall clock) | - | 'ya the soup cans. all 6 fuel tanks' (Mar 3) and 'all 6 tanks ya' in the thread. Examiner's window: 'The next morning' after March 3 (the sentence before, C20): March 4, morning read as 5 a.m. to noon. |  |
| C23 | `sender` | yes | quoted_text: the twins are in 17<br>account_ids: acct:item2:SMS:+13605550163<br>channels: SMS | pass | Incoming on Item 2 from the SPARE LINE. | [ ] |
|  | `record_time` | yes | quoted_text: the twins are in 17<br>person_ids: person:coyle<br>account_ids: acct:item2:SMS:+13605550163<br>channels: SMS<br>window: "Three days before the RECOVERY (Saturday, March 22, 2025)" (America/Los_Angeles, local wall clock) | pass | The RECOVERY was March 25. 11:40 a.m. PDT Mar 22. |  |
|  | `meaning` | yes | quoted_text: the twins are in 17<br>person_ids: person:coyle<br>account_ids: acct:item2:SMS:+13605550163<br>channels: SMS<br>window: "Three days before the RECOVERY (Saturday, March 22, 2025)" (America/Los_Angeles, local wall clock) | - | 'the 150s?' / 'ya both 150s, locked up' in the same exchange. |  |
| C24 | `sender` | yes | quoted_text: duke wants out<br>person_ids: person:coyle<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: duke wants out<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "Two days after the KITTIWAKE THEFT (Saturday, March 15, 2025)" (America/Los_Angeles, local wall clock) | pass | The KITTIWAKE THEFT was March 13. 7:10 p.m. PDT Mar 15 (Item 1 prints Mar 16). |  |
|  | `meaning` | yes | quoted_text: duke wants out<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "Two days after the KITTIWAKE THEFT (Saturday, March 15, 2025)" (America/Los_Angeles, local wall clock) | - | Not fixed: which Duke. |  |
| C25 | `message_count` | yes | device_ids: dev:item1<br>person_ids: person:varlow, person:coyle<br>channels: Signal<br>expected_count: 8<br>count_op: eq<br>each_way: True<br>window: "Between February 17 and February 23, 2025" (America/Los_Angeles, local wall clock) | pass | Eight on Pacific dates; printed (UTC) dates give nine. | [ ] |
| C26 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:pelloquin, person:coyle<br>channels: WhatsApp<br>expected_count: 6<br>count_op: eq<br>each_way: True<br>window: "From March 10 through March 14, 2025" (America/Los_Angeles, local wall clock) | pass | Six on Item 3; Item 2 holds seven. | [ ] |
| C27 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:pelloquin, person:varlow<br>channels: SMS<br>expected_count: 4<br>count_op: eq<br>each_way: True<br>window: "On March 12, 2025" (America/Los_Angeles, local wall clock) | fail | Six on the Pacific day; Item 3's printed Mar 12 holds four. | [ ] |
| C28 | `message_count` | yes | device_ids: dev:item3<br>person_ids: person:pelloquin<br>account_ids: acct:item3:SMS:+13605550163<br>channels: SMS<br>expected_count: 7<br>count_op: eq<br>sent_by: person:pelloquin<br>window: "During the SURVEILLANCE (Monday, March 17 to Wednesday, March 19, 2025)" (America/Los_Angeles, local wall clock) | pass | Seven from PELLOQUIN to the SPARE LINE on Item 3 (the KYOCERA). | [ ] |
| C29 | `message_count` | yes | device_ids: dev:item1<br>person_ids: person:varlow, person:pelloquin<br>channels: WhatsApp<br>expected_count: 6<br>count_op: ge<br>window: "Between March 3 and March 7, 2025" (America/Los_Angeles, local wall clock) | inconclusive | Four on the GALAXY (Item 1); fewer than claimed is never a fail. | [ ] |
| C30 | `message_count` | yes | device_ids: dev:item2<br>person_ids: person:varlow, person:coyle<br>channels: Signal<br>expected_count: 11<br>count_op: eq<br>each_way: True<br>window: "On the night of the TRANSFER, between 11 p.m. and 4 a.m. (11 p.m. PST on March 8 to 4:00:59 a.m. PDT on March 9, 2025)" (America/Los_Angeles, local wall clock) | pass | The 'between' convention on the night the TRANSFER began (March 8 into 9): 07:00:00 to 11:00:59.999999 UTC, four real hours and a minute. Eleven on Item 2. | [ ] |
| C31 | `no_contact` | yes | person_ids: person:varlow, person:pelloquin<br>window: "on February 18, 2025" (America/Los_Angeles, local wall clock) | fail | The 6:25 and 6:31 p.m. PST texts. | [ ] |
| C32 | `no_contact` | yes | person_ids: person:coyle, person:varlow<br>window: "between March 26 and March 28, 2025" (America/Los_Angeles, local wall clock) | fail | The Mar 27 WhatsApp exchange. No channel: the claim says any kind. | [ ] |
| C33 | `no_contact` | yes | person_ids: person:pelloquin<br>account_ids: acct:item1:SMS:+12535550148<br>window: "between March 1 and March 31, 2025" (America/Los_Angeles, local wall clock) | inconclusive | None found; curated reports. Item 3's 'Lars' is another number. | [ ] |
| C34 | `no_contact` | yes | person_ids: person:pelloquin, person:coyle<br>window: "In the hour before the clocks went forward that night (1 to 2 a.m. PST, March 9, 2025)" (America/Los_Angeles, local wall clock) | inconclusive | Examiner's window: 'The hour before the clocks went forward that night' (the night of the TRANSFER): the clocks jumped from 2 to 3 a.m. on March 9, so the hour is 1 to 2 a.m. PST, 09:00 to 10:00 UTC (written as 1 a.m. to 3 a.m. wall clock, the same instants). None in the hour; the WhatsApps at 12:52 a.m. PST and 3:05 a.m. PDT fall either side. | [ ] |
| C35 | `no_contact` | yes | person_ids: person:coyle, person:pelloquin<br>window: "On the two days after the RECOVERY (March 26 and 27, 2025)" (America/Los_Angeles, local wall clock) | fail | DUKE is PELLOQUIN (paragraph 2). Texts on Mar 26. | [ ] |
| C36 | `no_contact` | yes | person_ids: person:varlow, person:pelloquin<br>device_ids: dev:item1<br>window: "From the day after the RECOVERY through March 31, 2025" (America/Los_Angeles, local wall clock) | inconclusive | None on Item 1 (the GALAXY); curated. Item 3 holds a Mar 28 WhatsApp. | [ ] |
| C37 | `sender` | yes | quoted_text: 2200 for the big ones, 900 for the kickers<br>person_ids: person:coyle<br>channels: WhatsApp | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: 2200 for the big ones, 900 for the kickers<br>person_ids: person:coyle, person:pelloquin<br>channels: WhatsApp<br>window: "On March 14, 2025" (America/Los_Angeles, local wall clock) | pass | 1:06 p.m. PDT Mar 14. |  |
|  | `role` | yes | person_ids: person:coyle | - | That COYLE set the price: he asked, she named it, he took it. |  |
| C38 | `sender` | yes | quoted_text: put them in 17, not the boathouse<br>person_ids: person:varlow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: put them in 17, not the boathouse<br>person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On March 22, 2025" (America/Los_Angeles, local wall clock) | fail | Sent 6:15 p.m. PDT Mar 21; Item 1 prints 3/22 1:15:10 AM(UTC+0). |  |
|  | `role` | yes | person_ids: person:varlow | - | That VARLOW decided where they were stored. |  |
| C39 | `role` | yes | person_ids: person:coyle, person:pelloquin | - | That COYLE recruited PELLOQUIN. | [ ] |
| C40 | `sender` | yes | quoted_text: keys stay with u, nobody else drives it<br>person_ids: person:varlow<br>channels: WhatsApp | pass | CC-1 is VARLOW; his WhatsApp sent it (on Item 3 only). | [ ] |
|  | `role` | yes | person_ids: person:varlow, person:pelloquin | - | That VARLOW put him in charge of the keys: his instruction, 'got it, nobody else'. |  |
| C41 | `sender` | yes | quoted_text: patrol car just passed<br>person_ids: person:coyle<br>channels: Signal | pass | Outgoing on Item 2. | [ ] |
|  | `record_time` | yes | quoted_text: patrol car just passed<br>person_ids: person:coyle, person:varlow<br>channels: Signal<br>window: "On the night of the KITTIWAKE THEFT (6 p.m. on March 13 to 6 a.m. on March 14, 2025)" (America/Los_Angeles, local wall clock) | pass | Examiner's window: 'The night of' the KITTIWAKE THEFT (Thursday, March 13): 6 p.m. on March 13 to 6 a.m. on March 14. 11:09 p.m. PDT Mar 13. |  |
|  | `role` | yes | person_ids: person:coyle | - | That COYLE kept lookout: her thread that night. |  |
| C42 | `sender` | yes | quoted_text: the two yamahas are ready<br>person_ids: person:pelloquin<br>channels: SMS | pass | CC-3 is PELLOQUIN; outgoing on Item 3, to Item 3's 'Lars'. | [ ] |
|  | `role` | yes | person_ids: person:pelloquin<br>account_ids: acct:item1:SMS:+12535550148 | - | That PELLOQUIN arranged a sale to the BROKER (+12535550148): not shown. |  |
| C43 | `sender` | yes | quoted_text: fuel dock thursday 6pm<br>person_ids: person:varlow<br>channels: SMS | pass | Outgoing on Item 1. | [ ] |
|  | `record_time` | yes | quoted_text: fuel dock thursday 6pm<br>person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On March 18, 2025" (America/Los_Angeles, local wall clock) | pass | 10:15 a.m. PDT Mar 18. |  |
|  | `weekday_date` | yes | quoted_text: fuel dock thursday 6pm<br>channels: SMS<br>window: "Thursday, March 20, 2025" (America/Los_Angeles, local wall clock) | pass | 'thursday' sent on Tuesday Mar 18 is Mar 20. |  |
|  | `event` | yes | person_ids: person:varlow, person:coyle<br>channels: SMS<br>window: "On March 18, 2025" (America/Los_Angeles, local wall clock) | - | That they arranged it: COYLE's 'ok'. |  |
| C44 | `sender` | yes | quoted_text: need the motors out of the boathouse by sat<br>person_ids: person:coyle<br>channels: SMS | pass | Outgoing on Item 2. | [ ] |
|  | `sender` | yes | quoted_text: ok ill clear it friday<br>person_ids: person:varlow<br>channels: SMS | pass | Outgoing on Item 1. |  |
|  | `record_time` | yes | quoted_text: need the motors out of the boathouse by sat<br>person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "On March 4, 2025" (America/Los_Angeles, local wall clock) | pass | 9:30 a.m. PST Mar 4. |  |
|  | `event` | yes | person_ids: person:coyle, person:varlow<br>channels: SMS<br>window: "On March 4, 2025" (America/Los_Angeles, local wall clock) | - | That the request and the agreement are what the claim states. |  |
| C45 | `record_time` | yes | person_ids: person:coyle, person:pelloquin<br>channels: call<br>duration_s: 540, 660<br>window: "On March 16, 2025" (America/Los_Angeles, local wall clock) | inconclusive | Their only call that day is 45 s; 'about ten minutes' is 540 to 660 s. | [ ] |
| C46 | `sender` | yes | quoted_text: back in the barn<br>person_ids: person:pelloquin<br>channels: Telegram | pass | The HAULER is PELLOQUIN; outgoing on Item 3. | [ ] |
|  | `record_time` | yes | quoted_text: back in the barn<br>person_ids: person:pelloquin, person:varlow<br>channels: Telegram<br>window: "At about 4:50 a.m. that morning (March 9, 2025)" (America/Los_Angeles, local wall clock) | pass | 'That morning' is March 9 (the sentence before, C06). 4:47 a.m. PDT (Item 3 prints 3:47:10 AM(UTC-8)). |  |
|  | `event` | yes | person_ids: person:pelloquin, person:varlow<br>channels: Telegram<br>window: "At about 4:50 a.m. that morning (March 9, 2025)" (America/Los_Angeles, local wall clock) | - | That the trailer was back: 'all unloaded. trailer is back in the barn'. |  |
| C47 | `sender` | yes | quoted_text: deal, 3k for both, cash<br>account_ids: acct:item2:Telegram:8820450<br>channels: Telegram | pass | Incoming on Item 2 from the KELPWISE ACCOUNT (paragraph 3). | [ ] |
|  | `record_time` | yes | quoted_text: deal, 3k for both, cash<br>person_ids: person:coyle<br>account_ids: acct:item2:Telegram:8820450<br>channels: Telegram<br>window: "On the Monday after the HARBOR THEFT (March 3, 2025)" (America/Los_Angeles, local wall clock) | pass | The HARBOR THEFT ended Saturday, March 1. 10:40 a.m. PST Mar 3. |  |
|  | `event` | yes | person_ids: person:coyle<br>account_ids: acct:item2:Telegram:8820450<br>channels: Telegram<br>window: "On the Monday after the HARBOR THEFT (March 3, 2025)" (America/Los_Angeles, local wall clock) | - | That she offered two outboard motors: '2 outboards, 90s, both run. 3500 for the pair'. |  |
| C48 | `no_contact` | yes | person_ids: person:coyle, person:pelloquin<br>channels: call<br>window: "After the SURVEILLANCE ended (from midnight on March 20, 2025, until the RECOVERY at 10:40 a.m. on March 25, 2025)" (America/Los_Angeles, local wall clock) | fail | Examiner's window: 'After the SURVEILLANCE ended' (its last day is Wednesday, March 19) 'until the RECOVERY' (10:40 a.m. on March 25): midnight starting March 20 to 10:40 a.m. on March 25. COYLE's 8:05 p.m. Mar 22 call, on Item 3's log. | [ ] |

Gaps:

- C08: Unproven, not contradicted: the contact check never fails on a missing entry (contact lists are edited, and a curated report may leave entries out), so Item 1's 'Duke' holding +13605550138 does not rule out an entry 'Duke' with +13605550192.
- C11: same_account passes because the account's display name is the first name Item 3 shows ('Ren C'), and the thread title and later rows' sender cells show 'harborlights'. No row tests when the name changed: 'until March 12' rests on the printed rows (last 'Ren C' 8:41 p.m. Mar 11, first 'harborlights' 4:45 p.m. Mar 12).
- C12: That CC-2 received it is shown by the time row's phone (Item 2), not by a party.
- C39: Role only: no check tests recruitment. PELLOQUIN offered himself to VARLOW (Feb 14); COYLE's request for a driver went to Item 2's 'Duke', who said no.
- C43: 'At the fuel dock' and '6 p.m.' are tested only as words inside the quote, which the sender check matches verbatim; whether anyone met there is not tested.
- C48: The row tests any call between them; the claim says CC-2 placed it, which the one call found (outgoing from her number) also shows.

Signed: ____________________  Date: __________
