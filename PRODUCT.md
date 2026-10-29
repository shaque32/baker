# Product

<!-- impeccable:product-schema 1 -->

Design context for the Impeccable skill (`.claude/skills/impeccable/`). The product facts here
come from `CLAUDE.md`, `docs/ARCHITECTURE.md` and `docs/PRODUCT_STATUS.md`; where they differ,
those files win. This file is not the product status doc.

## Platform

web

## Users

Defense digital forensics experts and the criminal defense lawyers who hire them. The expert
reviews a government affidavit's claims about phone evidence against the extraction reports
(Cellebrite, AXIOM) on their own computer, decides each piece of evidence, and exports a report
that may be shown to a court.

## Product Purpose

Mabillon audits government claims about phone evidence. Each claim ends up supported,
contradicted or unproven, with cited evidence. Correctness is the product: one wrong "supported"
in front of an expert destroys trust. Success is an expert who trusts every line on screen
because each one shows where it came from.

## Positioning

A verification layer on top of Cellebrite and AXIOM, not a replacement. "Takes the scrolling, not
the judgment." Verifiable: every step is logged, replayable and cited.

## Operating Context

- A local web app (`mabillon serve`, `mabillon demo`) on the expert's Mac or Windows machine,
  served from 127.0.0.1. Long review sessions over dense evidence tables.
- The exported HTML report (`core/report/html.py`) is read by lawyers and may be printed.
- The marketing site (`site/`) is a separate surface.

## Capabilities and Constraints

- Verdicts come from `core/audit/rules.py`, never from a model. Nothing displays as supported
  until a human expert accepts its evidence.
- Verdict and status display names are signed by the owner. Do not rename "Supported",
  "Contradicted", "Unproven" or the review-state labels in `core/review/status.py`.
- Every displayed item keeps its provenance tier: observed, derived, inferred, ai_reviewed or
  confirmed. ai_reviewed never looks like confirmed.
- The app's Content-Security-Policy (`ui/app.py`) allows no scripts, no images and nothing from
  outside the machine. Do not change it, and do not use `/impeccable live`, which injects a script.
- Fonts are vendored in `ui/static/fonts/`. No CDN fonts, scripts or stylesheets.
- The look lives in the CSS layer in `ui/theme.py`. Keep the markup that tests and
  `packaging/smoke_ui.py` select on.
- Signed files (`core/contracts.py`, `core/schema.sql`, `core/audit/rules.py`,
  `core/audit/prompts/`, `eval/gold/`, `CLAUDE.md`) are never edited.
- The site's pipeline scroll animation (`site/main.js` and its CSS) is never touched.
- A report look change bumps `REPORT_VERSION` in `core/report/html.py`, with a note above it.

## Brand Commitments

- Name: Mabillon. Never "Counterproof". "Baker" stays only in format ids, the `baker_version`
  field and the `baker` command alias.
- Voice: plain, precise sentences. No uppercase labels.
- The tool never says guilty, innocent, leader or deleted.
- "Not found" never reads as "did not happen": absence lines state what was searched.
- No claims of "validated", accuracy, speed or "court-ready" until real-export validation is done.

## Evidence on Hand

- Synthetic demo case only (`mabillon demo`, case01). Never real case data, and never case02.
- Current screens: `docs/review-screen.md`, `docs/demo.md`.
- No testimonials, customers or measured accuracy figures exist to show.

## Product Principles

- Correctness over speed: never let design make an unconfirmed item look confirmed.
- Show where every line came from.
- Calm and dense: the expert scans a lot of evidence, so hierarchy beats decoration.
- The expert decides; the screen proposes.

## Accessibility & Inclusion

Verdicts never rely on color alone: each always shows its text label.
