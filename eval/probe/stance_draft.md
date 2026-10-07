# Stance prompt (DRAFT for the GPU test only)

This is a probe-only draft. The product stance prompt is human-owned and lives in
core/audit/prompts/ once Arsh writes it. Do not wire this file into core/.

You label one message against one assumption. You do not decide whether the claim is true.

Assumption:
{assumption}

Message (the record you are labeling):
{record}

Surrounding messages:
{context}

Pick one stance:
- supports: the message, read in its context, plainly states what the assumption says.
- contradicts: the message plainly states the opposite, or rules the assumption out.
- complicates: the message is related but the meaning depends on slang, a code word, an
  unresolved pronoun, sarcasm, a joke, a hypothetical, or a later correction.
- irrelevant: the message is about something else.

The quote must be copied exactly, character for character, from the message. Do not paraphrase,
fix spelling, or translate.

Answer with JSON only:
{"stance": "supports" | "contradicts" | "complicates" | "irrelevant", "quote": "<exact text from the message>", "rationale": "<one sentence>"}
