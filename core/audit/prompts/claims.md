# Claim extraction prompt (HUMAN-OWNED, Arsh)

v1.0, signed by Arsh on 2026-10-07 from the docs/prompts/claims.md draft v0.1.
Arsh edits this wording; agents only wire it to the local model.
Only the text after the next line is sent to the model.

<!-- prompt starts -->
You split one paragraph of a government document (an affidavit or a police or forensic report)
into atomic factual claims about phone evidence, so each can be checked against the data.

Paragraph:
{paragraph}

An atomic claim states one checkable fact: one communication, one identity link, one time,
one count, one absence, one role or one event. Split sentences that join several facts.
Keep the document's own names, numbers, dates and times exactly as written. Do not add facts,
resolve who a handle belongs to, or judge whether a claim is true. Leave out legal conclusions,
the officer's background and statements that make no claim about the phone evidence.

For each claim give:
- "text": the claim in one plain sentence, faithful to the paragraph.
- "claim_type": one of "communication", "identity", "timing", "content_meaning", "count",
  "absence", "role", "event". Use "content_meaning" when the claim says what a message meant,
  and "absence" when it says something was not found or did not happen.
- "span": the exact words of the paragraph the claim comes from, copied character for character.

If the paragraph makes no claim about phone evidence, return an empty list.

Answer with JSON only:
{"claims": [{"text": "<one sentence>", "claim_type": "<type>", "span": "<exact words from the paragraph>"}]}
