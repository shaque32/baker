# Context Restore

The expert pastes the messages a government exhibit quotes. Baker finds each one in the imported
extraction and shows it in its own conversation. Code finds and verifies every match; no model
decides one. Screenshot OCR is not part of this version: the expert types or pastes the text.

On the review screen: **Exhibits** (`/exhibits`) to add one, then open it to see each quoted
message, and **Open in context** for the conversation around a match.

## How a quoted message is found (`core/restore/match.py`, matcher 1.0.0)

1. The exhibit is split into quoted messages: one per line, or one per paragraph (blank line
   between messages) when a message runs over several lines.
2. For each, Baker searches the text of every imported message:
   - the quote as pasted; if nothing matches, the text after a label the exhibit printed in front
     of it (`3/12/2026 4:15 PM PETROV: ...`), at least two words; then the same without a closing
     period or comma. Wrapping quotation marks are set aside;
   - exact (character for character), then tolerant (letter case, spacing and line breaks,
     quote and dash styles, Unicode form), then Cyrillic-Latin transliteration, which counts only
     when one side is written in Cyrillic. The first that finds anything decides.
   - An ellipsis means the exhibit left words out. Each piece must be found, in order, in the
     same message, and the screen shows the words that were left out.
3. Every match is checked again from the stored message body before it is stored: the paired
   spans must agree under the method's own rule and start and end on word boundaries. A match
   that fails is dropped and counted in the audit log, never shown.

Every match shows how it was found, what the tolerant step set aside, the exhibit text that was
not compared (a printed time or sender), the words the exhibit left out, and whether the message
continues past the quoted words. All matches are listed, up to 25; text found more often than that
is too common to place on its own.

## What is shown

- The matched message with about 20 messages either side in the same thread. Each line has the
  UTC time (observed), the phone's local time (derived from UTC and the phone's time zone, never
  from the offset a report printed), the time exactly as the report printed it, the sender, the
  direction and the tier. The match itself is tier derived.
- Related threads between the same participants, on any phone: identifiers compared as the
  sources show them (phone numbers by their digits), plus identity links an expert confirmed. A
  thread on another phone needs two shared identifiers, so the other phone's owner alone does not
  make every thread there related. Their messages from the same period are shown.

## Not found

A quoted message that is not found says what was searched: each source, its coverage (curated
report or full extraction), its message count and dates, and the methods tried. It never says the
message does not exist. Only message text is searched, not translations, attachments, call logs,
contacts or images.

## Request for the full extraction (`core/report/letter.py`)

The selection audit ([selection-audit.md](selection-audit.md)) shows each quoted message of an
exhibit in its own exchange, with the messages around it the exhibit left out.

When any evidence source is a curated report or of unknown coverage, the report's Selection audit
section ends with, and the screen's **Request letter** page carries, a draft request for each
phone's full extraction, the extraction summary, how the report was produced from it, and the
examiner's notes. It lists each report with its device, extraction type, tool, extraction date
and SHA-256, and any exhibit whose quoted messages were not located. Bracketed fields are for
counsel. It is a draft, not legal advice, and Baker never sends it anywhere.

## Storage

`exhibits` keeps the pasted text exactly, with its SHA-256; adding or removing one is an expert
action in the audit log. `exhibit_excerpts` and `exhibit_matches` are derived and rewritten when
the expert searches again (the screen says when a new import or matcher version makes them out of
date). Context Restore never touches claims, evidence or verdicts.
