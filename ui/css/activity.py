"""Activity (/activity).

This page's own CSS, scoped to its markup (see ui/css/__init__.py). The intro reads at a
comfortable measure, what was seen sits on one line with the CSV download, the report switch is
one row (its state on the left, its button on the right), and the two tables are compact:
numbers right-aligned, times muted and unwrapped, claims never opened quieter than the rest.
On a phone the trail stacks each step into short lines.
"""

CSS = """
.pg-activity .lede { max-width: 58ch; }
.pg-activity details.howcounted { margin: 4px 0 20px; max-width: 72ch; }
.pg-activity details.howcounted summary { font-size: 13px; }
.pg-activity details.howcounted p { margin: 8px 0 0 16px; font-size: 13px; }

/* What was seen and the download, then the report switch */
.pg-activity .actbar { display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: 8px 24px; margin: 0 0 10px; }
.pg-activity .actbar p { margin: 0; font-size: 13.5px; max-width: 60ch; }
.pg-activity .actbar .t { white-space: nowrap; font-variant-numeric: tabular-nums;
  color: var(--muted); }
.pg-activity a.dl { display: inline-flex; align-items: center; min-height: 34px;
  padding: 0 14px; font-size: 13.5px; font-weight: 500; color: var(--fg);
  text-decoration: none; background: var(--card); border: 1px solid var(--line-strong);
  border-radius: var(--ctl-radius); box-shadow: 0 1px 2px rgb(20 20 20 / 0.05);
  transition: background-color 0.15s var(--ease), border-color 0.15s var(--ease); }
.pg-activity a.dl:hover { background: var(--hover); border-color: var(--line-hover); }
.pg-activity form.reportswitch { display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: 10px 24px; margin: 0; padding: 12px 16px;
  background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); }
.pg-activity form.reportswitch p { flex: 1 1 40ch; margin: 0; max-width: 60ch;
  font-size: 13.5px; }
.pg-activity form.reportswitch p .muted { font-size: 13px; }
.pg-activity form.reportswitch button { flex: none; margin: 0; }
@media (prefers-reduced-motion: reduce) { .pg-activity a.dl { transition: none; } }

/* Tables */
.pg-activity table { font-size: 13px; }
.pg-activity th, .pg-activity td { padding: 8px 14px; vertical-align: top; }
.pg-activity th.n { text-align: right; }
.pg-activity td.when { font-size: 12.5px; }
.pg-activity .byclaim td:nth-child(2), .pg-activity .byclaim td:nth-child(n+5),
.pg-activity .byclaim td:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.pg-activity .byclaim td:first-child { width: 1%; white-space: nowrap; font-weight: 500; }
.pg-activity .byclaim tr.unopened td { color: var(--muted); }
.pg-activity .trail td:first-child, .pg-activity .trail th:first-child { width: 1%;
  padding-right: 4px; text-align: right; white-space: nowrap; color: var(--muted);
  font-variant-numeric: tabular-nums; }
.pg-activity .trail td.when { width: 1%; }
.pg-activity .trail td:nth-child(4) { white-space: nowrap; font-weight: 500; }
.pg-activity .trail td:last-child { width: 18ch; text-align: right; color: var(--muted); }
.pg-activity .trail td .mono { display: inline; margin: 0; font-size: 12px; }
.pg-activity .trailbar { display: flex; flex-wrap: wrap; align-items: baseline;
  gap: 6px 16px; margin: -4px 0 12px; font-size: 13px; }

@media (max-width: 600px) {
  .pg-activity .byclaim td, .pg-activity .byclaim th { white-space: nowrap;
    overflow-wrap: normal; }
  .pg-activity table.trail { display: block; overflow: visible; }
  .pg-activity .trail thead { position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip-path: inset(50%); white-space: nowrap; }
  .pg-activity .trail tbody { display: block; }
  .pg-activity .trail tr { display: grid; grid-template-columns: auto minmax(0, 1fr) auto;
    column-gap: 10px; padding: 10px 12px; border-bottom: 1px solid var(--line); }
  .pg-activity .trail tr:last-child { border-bottom: 0; }
  .pg-activity .trail td, .pg-activity .trail td:nth-child(n) { display: block; width: auto;
    padding: 0; border: 0; text-align: left; background: none; }
  .pg-activity .trail td:nth-child(1) { grid-area: 1 / 1; }
  .pg-activity .trail td.when { grid-area: 1 / 2; }
  .pg-activity .trail td:nth-child(6) { grid-area: 1 / 3; text-align: right; }
  .pg-activity .trail td:nth-child(4) { grid-area: 2 / 1 / 3 / 4; white-space: normal; }
  .pg-activity .trail td:nth-child(3) { grid-area: 3 / 1 / 4 / 4; color: var(--muted);
    font-size: 12.5px; }
  .pg-activity .trail td:nth-child(5) { grid-area: 4 / 1 / 5 / 4; }
  .pg-activity .trail td:nth-child(5):empty { display: none; }
}
"""
