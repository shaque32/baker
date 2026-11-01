"""Timeline (/timeline) and Gaps (/gaps).

This page's own CSS, scoped to its markup (see ui/css/__init__.py). Both pages render the
report's own fragments (core/report/timeline.py); the report keeps its look, and only the screen
is restyled here, under .pg-timeline and .pg-gaps. The shared "report modules shown inside the
app" rules in ui/theme.py stay; these override them where the screen needs it.

Timeline: the stated times read as one ledger (rows split by hairlines, not a stack of cards),
each row the document's words, the phone records on a quiet rail, and one status.
Gaps: one panel per phone, the day strip on top and its quiet stretches below it.
"""

CSS = """
/* Page head: the lede, then the explanation and the settings folded side by side */
.pg-timeline > .lede, .pg-gaps > .lede, .pg-gaps > .caveat, .pg-timeline > .tl-summary {
  max-width: 62ch; text-wrap: pretty; }
.pg-timeline > .lede, .pg-gaps > .lede { margin: 0 0 8px; }
.pg-gaps > .caveat { margin: 0 0 4px; color: var(--fg); font-weight: 500; }
.pg-timeline > .tl-summary { margin: 16px 0 0; padding: 12px 16px; font-size: 13.5px;
  background: var(--panel); border-radius: var(--radius); }
.tl-folds { display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 6px 28px; margin: 14px 0 0; }
.tl-folds > details, .tl-folds > details.case-settings { margin: 0; }
.tl-folds > details[open] { flex-basis: 100%; }
.tl-folds > details > summary { font-size: 13px; font-weight: 500; color: var(--muted);
  text-wrap: pretty; transition: color 0.15s var(--ease); }
.tl-folds > details > summary:hover, .tl-folds > details[open] > summary { color: var(--fg); }
.tl-folds > details[open] > summary { margin-bottom: 10px; }
.tl-folds > details.more > p { max-width: 62ch; margin: 0 0 6px; font-size: 13.5px;
  color: var(--muted); text-wrap: pretty; }
.tl-folds form.settings { max-width: 720px; padding: 18px 20px; }
.pg-timeline h2 .n, .pg-gaps h2 .n { margin-left: 6px; font-weight: 500; color: var(--muted);
  font-variant-numeric: tabular-nums; }

/* Timeline: one ledger per section */
.pg-timeline .tl { margin: 0; background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); overflow: hidden; }
.pg-timeline .tl > li, .pg-timeline .tl > li.flag { margin: 0; padding: 16px 20px;
  background: none; border: 0; border-top: 1px solid var(--line); border-radius: 0;
  box-shadow: none; gap: 8px 32px; scroll-margin-top: 16px;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr) 120px;
  transition: background-color 0.2s var(--ease); }
.pg-timeline .tl > li:first-child { border-top: 0; }
.pg-timeline .tl > li:target { background: var(--accent-bg); }
.pg-timeline .tl .meta { font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.pg-timeline .tl .said { margin: 2px 0 6px; font-size: 15px; font-weight: 500;
  line-height: 1.4; }
.pg-timeline .tl details { margin: 0 0 6px; }
.pg-timeline .tl details > summary { font-size: 12.5px; font-weight: 500; color: var(--muted); }
.pg-timeline .tl details > summary:hover, .pg-timeline .tl details[open] > summary {
  color: var(--fg); }
.pg-timeline .tl details[open] > summary { margin-bottom: 6px; }
.pg-timeline .tl li > div > details > .q { display: block; max-width: 72ch; padding: 8px 12px;
  font-size: 13.5px; background: var(--panel); border-radius: 6px; }
.pg-timeline .tl .recs { display: grid; gap: 6px; align-content: start; font-size: 13.5px;
  text-wrap: pretty; }
.pg-timeline .tl .recs ul { list-style: none; margin: 6px 0 0; padding: 0; }
.pg-timeline .tl .recs li { margin: 0 0 8px; padding: 0 0 0 12px; font-size: 13px;
  line-height: 1.5; border-left: 1px solid var(--line-strong); }
.pg-timeline .tl .recs li:last-child { margin-bottom: 0; }
.pg-timeline .tl .recs details ul { margin-top: 0; }
.pg-timeline .tl .st { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.pg-timeline .tl .notes { list-style: none; margin: 2px 0 0; padding: 0; font-size: 12.5px;
  text-wrap: pretty; }
.pg-timeline .tl .notes li + li { margin-top: 2px; }

/* Gaps: one panel per phone; the day strip heads it, its stretches follow under hairlines */
.pg-gaps .strips { margin: 0 0 12px; padding: 14px 20px; border-color: var(--line); }
.pg-gaps .strips:has(+ .gap) { margin-bottom: 0; border-bottom-left-radius: 0;
  border-bottom-right-radius: 0; }
.pg-gaps .strips > div:first-child { margin: 0 0 8px; font-size: 12.5px; }
/* The phone's name is the heading just above; screen readers still hear it here. */
.pg-gaps .strips > div:first-child > strong { position: absolute; width: 1px; height: 1px;
  overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
.pg-gaps .gap { margin: 0; padding: 16px 20px; border-top: 0; border-radius: 0; }
.pg-gaps h2 + .gap, .pg-gaps details > summary + .gap { border-top: 1px solid var(--line);
  border-top-left-radius: var(--radius); border-top-right-radius: var(--radius); }
.pg-gaps .gap:not(:has(+ .gap)) { margin-bottom: 12px; border-bottom-left-radius: var(--radius);
  border-bottom-right-radius: var(--radius); }
.pg-gaps .gap .stmt { margin: 2px 0 10px; font-size: 14.5px; text-wrap: pretty; }
.pg-gaps .gap dl { grid-template-columns: 104px minmax(0, 1fr); gap: 6px 20px; margin: 0; }
.pg-gaps .gap dd { max-width: 84ch; text-wrap: pretty; overflow-wrap: anywhere; }
.pg-gaps .gap dd ul { display: flex; flex-wrap: wrap; gap: 4px 6px; margin: 6px 0 2px;
  padding: 0; list-style: none; }
.pg-gaps .gap dd li { padding: 1px 8px; font-size: 12.5px; background: var(--panel);
  border-radius: 4px; }
.pg-gaps > details { margin: 4px 0 8px; }
.pg-gaps > details > summary { font-size: 13px; font-weight: 500; }
.pg-gaps > details[open] > summary { margin-bottom: 10px; }

@media (prefers-reduced-motion: reduce) {
  .tl-folds > details > summary, .pg-timeline .tl > li { transition: none; }
}
@media (max-width: 760px) {
  .pg-timeline .tl > li, .pg-timeline .tl > li.flag { grid-template-columns: minmax(0, 1fr);
    padding: 14px 16px; }
  .pg-timeline .tl .st { order: -1; flex-direction: row; align-items: baseline; gap: 8px; }
  .pg-gaps .strips, .pg-gaps .gap { padding: 14px 16px; }
}
@media (max-width: 600px) {
  .pg-gaps .gap dl { grid-template-columns: minmax(0, 1fr); gap: 2px 0; }
  .pg-gaps .gap dd { margin-bottom: 6px; }
}
"""
