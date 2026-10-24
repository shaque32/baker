# What Baker does and doesn't do

One page for forensic examiners. Baker is alpha software, tested on synthetic cases only.

## In one line

Baker is a verification layer on top of Cellebrite and AXIOM. It checks the government's specific
claims about phone evidence against the extraction you already have. It takes the scrolling, not
the judgment.

## What it does

1. **Reads what you already have.** The government's document (an affidavit or report, as a PDF)
   and the phone extraction reports: Cellebrite Excel, PDF and UFDR, and Magnet AXIOM XML and
   Excel. Each file is opened read-only and its SHA-256 recorded. The UFDR reader is tested on
   real-format Cellebrite UFDR exports from public test phones (Reader 7.48). Other
   Cellebrite versions are not yet tested. The Cellebrite Excel and AXIOM readers are not yet
   tested on real exports.
2. **Splits the document into claims.** A local model proposes one claim at a time; you accept,
   edit or remove each one and add your own. The claim list is yours.
3. **Tests each claim.** Code checks what can be computed (sender, account, time and time zone,
   weekday, counts, what a source can and cannot show). A language model labels individual
   records as supporting, contradicting or neither, and every quote it gives must appear word for
   word in the record or it is thrown away.
4. **Gives each claim a status from fixed, versioned rules:** supported, contradicted or unproven,
   with the records and reasons. **The model never decides a verdict.** Nothing is supported
   until you accept its evidence, and a model's "contradicts" label counts only after you confirm
   it (until then the claim shows "Contradiction found, confirm to finalize"). A code check that
   fails, such as a wrong sender or a time outside the stated window, contradicts a claim
   directly, with the failed check shown.
5. **Shows you where to look.** The records behind each claim, the messages around each quote,
   gaps in the timeline, and what the document left out around a quote.
6. **Keeps a record.** Every decision goes into a hash-chained audit log under your name. The
   report lists source hashes, the rule version, the model file and prompt versions, and the
   log's last hash.

## What it doesn't do

1. **It doesn't decide for you.** No opinion, no conclusion about any person. Any opinion is
   yours, and you can override any status.
2. **It doesn't replace your tools.** It does not extract phones, recover data, or replace
   Cellebrite, AXIOM or your own review of the source data.
3. **It doesn't treat "not found" as "did not happen".** Each search says what it covered. A
   curated report (the examiner's selection) can never show that something is absent.
4. **It doesn't link identities on its own.** Links between a number, a handle and a person stay
   proposed until you confirm them.
5. **It makes no speed or accuracy claim.** There is no accuracy figure for real cases: Baker has
   been measured on synthetic cases only, and no figure is published until it is measured on real
   extractions. UFDR is tested only on Cellebrite
   Reader 7.48 exports of public test phones; Cellebrite Excel and AXIOM are not yet tested on
   real exports.

## Where your data goes

Local by default; cloud AI only when your case allows it and you opt in. Baker runs on your own
computer and its screen answers only that computer. A case uses cloud AI only when you attest at
setup that its protective order allows it and set up your own key, and never for a case marked
as possibly containing CSAM. Only a cloud model setup that passed Baker's stance test can be
used; the report says which model labelled the case. Cases can be encrypted with a passphrase.

## Getting help

- **Support:** support@getmabillon.com. It is also on the **Help** tab in the app.
- **Bug report:** on the Help tab, save the bug report and attach it to your email. It holds
  Baker's versions, your computer's system and model setup and recent errors, with no case data:
  no case or file names, no text from the case, no hashes. Read it before you send it
  (`docs/SUPPORT.md`).
- **Never send case content:** no case files, case database or screenshots of evidence.

More detail: `docs/METHODS.md` (how each finding is reached), `docs/PILOT_ONBOARDING.md` (install
and first case), `docs/SECURITY_PRIVACY.md` (data flow).
