"""One claim (/claim) and one evidence item (/evidence).

This page's own CSS, scoped to its markup (see ui/css/__init__.py): `.pg-claim` wraps the claim
page's split (ledger and main column), `.pg-evidence` the evidence item page.

The claim reads like the site's walk panel (site/index.html `.walk`): the claim, its rows of
facts each with one tag and one small detail line, and one status. Forms sit flat inside their
card (no box in a box), with the reason field and its buttons on one line. Settled evidence,
the rules' working, the other explanations and the secondary forms fold; every word stays.
"""

CSS = """
/* ---- one claim: a readable main column beside the ledger */
.pg-claim .claim-main { min-width: 0; max-width: 820px; }
.pg-claim .claim-main p, .pg-claim .claim-main li { max-width: 70ch; text-wrap: pretty; }
.pg-claim .claim-main h2 { margin: 36px 0 10px; }
.pg-claim blockquote.claimtext { margin: 12px 0 12px; }

/* where the claim comes from: the printed paragraph and the selection notes, as small lines */
.pg-claim .claim-src { display: grid; gap: 6px; margin: 0 0 24px; font-size: 13px; }
.pg-claim .claim-src details > summary { font-size: 13px; }
.pg-claim .claim-src details[open] > summary { margin-bottom: 6px; }
.pg-claim .claim-src p.caution { position: relative; margin: 0; padding: 0 0 0 16px;
  background: none; border: 0; border-radius: 0; color: var(--muted); font-size: 13px;
  line-height: 1.5; }
.pg-claim .claim-src p.caution::before { content: ""; position: absolute; left: 2px;
  top: 0.55em; width: 6px; height: 6px; border-radius: 50%; background: var(--line-strong); }

/* the verdict: one status, what it waits on, then its two folded actions on one line */
.pg-claim #verdict { margin: 0 0 8px; }
.pg-claim #verdict > .in { padding: 18px 22px; }
.pg-claim .vhead { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  margin: 0 0 12px; }
.pg-claim .claim-main .vhead h2 { margin: 0; font-size: 15px; }
.pg-claim #verdict .vhead .verdict { margin: 0; padding: 3px 10px; font-size: 13.5px;
  font-weight: 600; border-radius: 6px; }
.pg-claim ul.needs { list-style: none; margin: 0 0 10px; padding: 0; display: grid; gap: 4px; }
.pg-claim ul.needs li { position: relative; padding-left: 16px; }
.pg-claim ul.needs li::before { content: ""; position: absolute; left: 2px; top: 0.6em;
  width: 6px; height: 6px; border-radius: 50%; background: var(--line-strong); }
.pg-claim #verdict .gap { margin: 8px 0; padding: 0; border: 0; border-radius: 0;
  background: none; font-size: 13px; }
.pg-claim #verdict p.format-notice { margin: 8px 0; }
.pg-claim #verdict p.format-notice strong { font-weight: 500; }
.pg-claim #verdict .in > details { margin-top: 10px; }
.pg-claim #verdict .in > details > summary { font-size: 13px; }
.pg-claim #verdict > .in.vacts { display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 6px 28px; padding: 12px 22px; background: var(--card); }
.pg-claim .vacts > details { margin: 0; }
.pg-claim .vacts > details[open] { flex-basis: 100%; }
.pg-claim .vacts > details > summary { font-size: 13px; }
.pg-claim .vacts > details.flag > summary { color: var(--muted); }

/* what has to be true: the walk's rows, one tag each, one small detail line */
.pg-claim .truths .checklist { background: none; border: 0; border-radius: 0;
  border-top: 1px solid var(--line); margin: 8px 0 8px; }
.pg-claim .checklist li { grid-template-columns: minmax(0, 1fr) auto; gap: 2px 16px;
  align-items: start; padding: 12px 2px; border-top: 0; border-bottom: 1px solid var(--line);
  max-width: none; }
.pg-claim .checklist .mark { display: none; }
.pg-claim .checklist .meta { font-size: 12.5px; margin-top: 3px; }
.pg-claim .checklist .said { padding: 2px 10px; border-radius: 999px;
  font: 500 12px/1.5 var(--sans); color: var(--unp); background: var(--unp-bg);
  white-space: nowrap; }
.pg-claim .checklist li.ok .said { color: var(--sup); background: var(--sup-bg); }
.pg-claim .checklist li.ok[data-tier=ai_reviewed] .said { color: var(--muted);
  background: var(--panel); }
.pg-claim .checklist li.con .said { color: var(--con); background: var(--con-bg); }
.pg-claim .checklist li.no .said { color: var(--unp); background: var(--unp-bg);
  box-shadow: inset 0 0 0 1px var(--unp-line); }

/* other explanations: one line per lead, the records behind them folded */
.pg-claim details.alts-fold { margin: 24px 0 8px; }
.pg-claim details.alts-fold > summary { display: grid; grid-template-columns: auto minmax(0, 1fr);
  align-items: baseline; color: var(--fg); }
.pg-claim details.alts-fold > summary::before { align-self: center; }
.pg-claim .claim-main details.alts-fold h2 { margin: 0; font-size: 16px; }
.pg-claim .alt-titles { grid-column: 2; display: grid; gap: 2px; margin: 4px 0 0; }
.pg-claim .alt-titles span { font: 400 13.5px/1.5 var(--sans); color: var(--ink-2); }
.pg-claim details.alts-fold[open] .alt-titles { display: none; }
.pg-claim details.alts-fold[open] > summary { margin-bottom: 4px; }
.pg-claim .alts { margin: 4px 0 0; }
.pg-claim .alt { background: none; border: 0; border-top: 1px solid var(--line); border-radius: 0;
  padding: 12px 0; margin: 0; }
.pg-claim .alt h3 { margin: 4px 0 4px; font-size: 14px; }
.pg-claim .alt .fam { font-size: 12.5px; }

/* the evidence */
.pg-claim h3.ev-group { margin: 28px 0 6px; font-size: 14px; }
.pg-claim h3.ev-group span { font-weight: 400; color: var(--muted); }
.pg-claim p.ev-asm { margin: 14px 0 6px; font-size: 13px; color: var(--muted); }
.pg-claim p.warn { max-width: 70ch; }
.pg-claim p.warn strong { font-weight: 500; }
.pg-claim .holdings { font-size: 13px; color: var(--ink-2); }
.pg-claim .holdings p { margin: 0 0 4px; }
.pg-claim .holdings ul { margin: 0 0 16px; padding-left: 18px; }
.pg-claim .holdings li { margin: 2px 0; overflow-wrap: anywhere; }

/* one piece of evidence: its tags, the record, one review line, one decision line */
.pg-claim .item, .pg-evidence .item { padding: 16px 20px 14px; margin: 8px 0 14px; }
.pg-claim .ev-tags, .pg-evidence .ev-tags { display: flex; flex-wrap: wrap; gap: 6px;
  margin: 0 0 12px; }
.pg-claim .ev-tags .badge, .pg-evidence .ev-tags .badge { margin: 0; }
.pg-claim .item blockquote, .pg-evidence .item blockquote { margin: 0 0 6px;
  padding: 1px 0 1px 14px; font-size: 15px; }
.pg-claim .item p.quoted { margin: 8px 0 2px; font-size: 13.5px; }
.pg-claim p.ev-rec, .pg-evidence p.ev-rec { margin: 2px 0 0; font-size: 12.5px;
  color: var(--muted); overflow-wrap: anywhere; }
.pg-claim p.ev-review, .pg-evidence p.ev-review { margin: 12px 0 0; padding-top: 12px;
  border-top: 1px solid var(--line); font-size: 13px; max-width: none; }
.pg-claim p.ev-review strong, .pg-evidence p.ev-review strong { font-weight: 600; }
.pg-claim .ev-foot details.ev-change > summary { color: var(--accent); }
.pg-claim .ev-foot details.ev-thread[open] > summary { margin-bottom: 8px; }
.pg-claim .ev-foot details.ev-change form.box { font-size: 13.5px; }
.pg-claim .ev-foot, .pg-evidence .ev-foot { display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 4px 22px; margin: 12px 0 0; font-size: 12.5px; }
.pg-claim .ev-foot > details, .pg-evidence .ev-foot > details { margin: 0; }
.pg-claim .ev-foot > details[open], .pg-evidence .ev-foot > details[open] { flex-basis: 100%; }
.pg-claim .ev-foot summary, .pg-evidence .ev-foot summary { font-size: 12.5px;
  color: var(--muted); }
.pg-claim .ev-foot summary:hover, .pg-evidence .ev-foot summary:hover { color: var(--fg); }
.pg-claim .ev-foot details p, .pg-evidence .ev-foot details p { margin: 6px 0; }
.pg-claim .ev-foot .ev-around { margin-left: auto; }

/* forms sit flat in their card: the reason field and its buttons on one line */
.pg-claim form.box, .pg-evidence form.box { display: flex; flex-wrap: wrap; align-items: center;
  gap: 8px; margin: 10px 0 0; padding: 0; background: none; border: 0; border-radius: 0; }
.pg-claim form.box br, .pg-evidence form.box br { display: none; }
.pg-claim form.box input[type=text].wide, .pg-evidence form.box input[type=text].wide {
  flex: 1 1 260px; width: auto; min-width: 0; margin: 0; }
.pg-claim form.box textarea { flex: 1 1 100%; margin: 0; }
.pg-claim form.box select, .pg-evidence form.box select { margin: 0; }
.pg-claim form.box button, .pg-evidence form.box button { margin: 0; }
.pg-claim form.box > .muted, .pg-claim form.box > p,
.pg-evidence form.box > .muted, .pg-evidence form.box > p { flex: 1 1 100%; margin: 0;
  font-size: 12.5px; }
.pg-claim form.box button + .muted, .pg-evidence form.box button + .muted { flex: 1 1 200px; }
.pg-claim .vacts form.box + form.box { margin-top: 16px; padding-top: 14px;
  border-top: 1px solid var(--line); }
.pg-claim .vacts details > p.muted { margin: 12px 0 0; font-size: 12.5px; }

/* the agent's proposal: one card, its form flat inside */
.pg-claim section.agent { padding: 18px 22px; }
.pg-claim .claim-main section.agent h2 { display: flex; flex-wrap: wrap; align-items: center;
  gap: 6px 10px; margin: 0 0 8px; font-size: 15px; }
.pg-claim section.agent h2 .badge { margin: 0; }
.pg-claim section.agent details { margin: 8px 0; }
.pg-claim section.agent details > summary { font-size: 13px; }
.pg-claim section.agent ul.proposed li > div { margin: 0 0 2px; }
.pg-claim section.agent ul.proposed li { margin: 0 0 14px; }

/* the rest of the claim, folded: irrelevant records, the rules' working, a missed record */
.pg-claim .claim-more { display: grid; gap: 10px; margin: 28px 0 0; padding-top: 16px;
  border-top: 1px solid var(--line); }
.pg-claim .claim-more:empty { display: none; }
.pg-claim .claim-more > details { margin: 0; }
.pg-claim .claim-more > details > summary { font-size: 13px; color: var(--muted); }
.pg-claim .claim-more > details > summary:hover { color: var(--fg); }
.pg-claim .claim-more > details[open] > summary { margin-bottom: 8px; }
.pg-claim #irrelevant ul { margin: 0; padding-left: 18px; font-size: 13px; }
.pg-claim #irrelevant li { margin: 0 0 8px; }
.pg-claim details.working h3 { margin: 12px 0 6px; font-size: 13.5px; }

/* the claim's wording: accept or remove on one line, a new wording folded */
.pg-claim section.wording { margin: 36px 0 0; padding-top: 4px; }
.pg-claim .claim-main section.wording h2 { margin: 0 0 4px; }
.pg-claim form.wording-acts { margin: 8px 0 12px; }
.pg-claim form.wording-acts.done button[value=accepted] { color: var(--fg); font-weight: 500;
  background: var(--card); border-color: var(--line-strong); box-shadow: none; }
.pg-claim form.wording-acts.done button[value=accepted]:hover { background: var(--hover);
  border-color: var(--line-hover); }
.pg-claim details.edit-text > summary { font-size: 13px; }
.pg-claim details.edit-text form.box { margin-top: 10px; }

/* ---- the conversation around a record: quiet bubbles, sender and time on one line */
.pg-claim .thread.mini { background: none; border: 0; border-radius: 0; padding: 0;
  margin: 0 0 4px; gap: 6px; }
.pg-claim .msg, .pg-evidence .msg { display: grid; grid-template-columns: minmax(0, 1fr) auto;
  column-gap: 14px; row-gap: 1px; border: 0; border-radius: 10px; padding: 7px 12px;
  background: var(--panel); }
.pg-claim .msg.out, .pg-evidence .msg.out { background: var(--accent-bg); }
.pg-claim .msg .who2, .pg-evidence .msg .who2 { grid-column: 1; font-size: 12px; }
.pg-claim .msg .t, .pg-evidence .msg .t { grid-column: 2; grid-row: 1; margin: 0;
  font-size: 12px; white-space: nowrap; }
.pg-claim .msg .body, .pg-evidence .msg .body { grid-column: 1 / -1; }
.pg-claim .msg.target, .pg-evidence .msg.target { border: 0; box-shadow: none;
  outline: 1.5px solid var(--accent); outline-offset: 0; }
.pg-claim .msg .cited, .pg-evidence .msg .cited { font-size: 12px; }

/* the side ledger keeps the open claim in view. A ledger link lands on that claim's row
   (#lg-<id>), which scrolls the ledger to it, a third of the way down; the window stays at
   the top of the new claim (the padding below is only set while a ledger row is the target).
   scroll-initial-target centres the open claim on any load, after a form or from the
   overview, where the browser supports it (Chrome, Edge). No script: the page's policy
   forbids it. */
.pg-claim aside.side .ledger { overflow: clip; } /* not a scroll box, so the aside is "nearest" */
.pg-claim aside.side .ledger li { scroll-margin-top: 30vh; }
.pg-claim aside.side .ledger li.on { scroll-initial-target: nearest; scroll-snap-align: center; }
html:has(.pg-claim aside.side .ledger li:target) { scroll-padding-top: 100vh; }

/* ---- one evidence item */
.pg-evidence { max-width: 820px; }
.pg-evidence p.ev-of { color: var(--muted); max-width: 70ch; }
.pg-evidence h2 { margin: 36px 0 6px; }
.pg-evidence h2 + p.muted { margin-bottom: 12px; }
.pg-evidence .thread { padding: 14px; gap: 6px; background: var(--card); }

@media (max-width: 960px) {
  .pg-claim .claim-main { max-width: none; }
  /* the ledger sits below the claim here: opening a claim stays at the top of the page */
  .pg-claim aside.side .ledger li { scroll-margin-top: 100000px; }
}
@media (max-width: 600px) {
  .pg-claim #verdict > .in, .pg-claim #verdict > .in.vacts { padding-left: 16px;
    padding-right: 16px; }
  .pg-claim .item, .pg-evidence .item { padding: 14px 14px 12px; }
  .pg-claim .msg, .pg-evidence .msg { grid-template-columns: minmax(0, 1fr); }
  .pg-claim .msg .t, .pg-evidence .msg .t { grid-column: 1; grid-row: auto; text-align: left;
    white-space: normal; }
  .pg-claim .checklist li { grid-template-columns: minmax(0, 1fr); }
  .pg-claim .checklist .said { justify-self: start; margin-top: 4px; }
  .pg-claim .ev-foot .ev-around { margin-left: 0; }
}
"""
