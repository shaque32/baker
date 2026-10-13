# Selection audit

The government's document quotes some messages and not others. The selection audit shows each
message the government picked in its own conversation, with the messages exchanged around it
that it did not pick: the reply just before a quoted message, the two messages between two
quotes, the answer right after. The expert sees what was left out and judges whether it matters.

Code does all of it; no model is involved. It never sets or changes a verdict, and it never says
why a message was not picked. Nothing is stored: it is derived from the case database each time
it is shown.

On the review screen: the **Selection** tab (`/selection`), "Open in the conversation" for 20
messages either side and related threads (`/selection/context?id=...`), a link to the **Gaps** tab
from each passage whose pauses hold a quiet stretch, and a line on each claim page whose paragraph
quotes messages. The report prints it as its **Selection audit** section, which ends with the
draft request for the full extraction (`core/report/letter.py`).

## What counts as picked (`core/selection/picks.py`)

- **Document quotes.** Words a paragraph of the government document puts in quotation marks
  (`"..."` or `“...”`). Line breaks inside the marks are read as spaces. Quoted words that are a
  name in the case (a contact, an account's identifier or display name, a thread title, a person),
  a single word, or a redaction with no letters are not looked up, and the page lists them as not
  looked up. A message whose whole text is such a quote ("tmrw") is marked "may be quoted".
- **Exhibits.** Each quoted message of an exhibit pasted on the Exhibits page, as Context Restore
  split it. An exhibit not searched there yet is named and not checked.
- **Examiner tags.** Messages a report marks with an examiner tag (bookmark). Tagged messages the
  document also quotes are covered under the document; the rest get their own section.

Quotes are looked up with the Context Restore matcher (`core/restore/match.py`: exact, then
tolerant, then transliteration; every match re-verified against the stored message body), across
every message in the case.

## Placing a quote fails closed

A quote is placed on a message only when every message its words are found in is one message:
a single record, or copies of it on different sources (the same text, at most 2 minutes apart,
as when both phones of a conversation were extracted). Otherwise the page says how often the
words were found and places nothing:

- found in two different messages: "Code cannot confirm they are one message seen on different
  phones, so it does not decide which one is meant";
- found in more than 4 messages: too many to tell;
- only the words after a colon or dash found (the matcher reads what comes before as a printed
  label): the whole quote was not found;
- not found: "This does not show that the message was never sent or received."

Every message an unplaced quote's words were found in is marked "may be quoted" wherever it is
shown, and is never counted as left out. A message counts as not quoted when no quote of the
document was found in it: a quote too far from the message's words for the matcher (spelled-out
numbers, a paraphrase in quotation marks) is listed as not found, and the message it means
counts as not quoted. The page says so next to the quotes not found.

## Exchanges and passages (`core/selection/audit.py`)

A thread's messages, in the order Context Restore and the claim pages use (UTC time, then the
source's order, untimed messages last), fall into **exchanges**: a pause longer than an hour
starts a new one. A message with no usable time is an exchange of its own.

For each paragraph, exhibit or the tags, and each exchange holding messages it picked, the page
shows a **passage**:

- the picked messages, the quoted words marked;
- every other message of the exchange: **not quoted** (the selection picked it nowhere: no
  paragraph of the same document quotes it), **quoted in ¶9** (another paragraph quotes it), or
  **may be quoted**. Only "not quoted" messages are counted as left out;
- when fewer than 3 messages of the exchange come before (or after) the picks, the nearest
  messages outside it, dimmed, with the pause shown, so a quote that opens a conversation shows
  what came before it. A pause longer than an hour is always shown as a divider;
- long runs are cut to the 8 messages nearest the picks (10 between two picks), and say how many
  are not shown; the counts include them;
- messages in the source's other conversations within an hour of the exchange, folded away.

Each passage says, in plain words computed from the rows: how many of the exchange's messages
were picked; how many were left out between, just before and just after; how many of those came
from someone other than the sender of the picked messages; the pause to the previous and next
message when the exchange opens or closes with a pick; and whether a quote is only part of its
message.

When the Gaps check (`core/timeline/gaps.py`, with the case's shortest-stretch setting) lists a
quiet stretch in the thread's pause just before or just after the exchange, on the same phone, in
the thread's app or in the thread itself, the passage names it: "In the pause after this
exchange, the Gaps check lists a quiet stretch: no messages in this app on this phone from
2026-03-25 12:51 EDT to 2026-03-28 14:15 EDT (3 days 1 h)." When a pause holds several, it gives
their number and the longest. The Gaps page has each stretch in full, with its pace and what the
other phones hold; like the Gaps check, the passage states a stretch and never explains it.

When the same picked messages are on two sources, the second passage is folded into the first if
its exchange holds the same messages; if not, both are shown and the difference is counted ("it
holds 1 message that the exchange there does not").

## What it cannot show

A message the examiner left out of a curated report is not in the case, so it cannot be shown or
counted. The section says which sources are curated reports and ends with the draft request for
the full extraction. Quoted means put in quotation marks: a paragraph may still describe a
message without quoting it, and such a paragraph is not placed.

## Tiers

Messages are observed, as the source recorded them. The phone's local time is derived from UTC
and the phone's time zone. Placements, exchanges and counts are derived by code. Everything
quoted (paragraph text, messages, senders, exhibit labels, file names) is cited text, set apart
for the forbidden-word check.

## Speed

The matcher's index of every message body is kept in memory per case database while its messages
are unchanged. The first view after the screen starts builds it: on a synthetic copy of case01
grown to 117,000 messages that took about 11 seconds when a quote had to be searched tolerantly,
then about a second per view. Naming the quiet stretches runs the Gaps check over every message
and call each time, about 2.5 seconds more at that size. The claim pages and the conversation
view do not run it.
