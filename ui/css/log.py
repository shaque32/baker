"""Audit log (/log).

This page's own CSS, scoped to its markup (see ui/css/__init__.py). A long technical table made
scannable: the chain status as one line with a dot, the flags tool as one quiet panel, the
filters as a row of segmented links, then the entries with the sequence number, time and action
on one line each and the payload folded to a short monospace preview. On a phone each entry
stacks into a few short lines instead of squeezing five columns.
"""

CSS = """
.pg-log > p, .pg-log .chain { max-width: 78ch; }
.pg-log p.chain.ok { display: flex; align-items: baseline; gap: 9px; margin: 4px 0 2px;
  font-size: 13.5px; color: var(--fg); }
.pg-log p.chain.ok::before { content: ""; flex: none; width: 7px; height: 7px;
  border-radius: 50%; background: var(--sup); transform: translateY(-1px); }
.pg-log .flash.chain { margin: 4px 0 8px; }
.pg-log p.chainmeta { margin: 0 0 0 16px; font-size: 12.5px; color: var(--muted); }
.pg-log p.chainmeta .mono { font-size: 11.5px; }

/* The flags tool: count and how to flag, then the download on one line with its note */
.pg-log .logflags { margin: 28px 0 0; padding: 14px 18px 16px; background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); }
.pg-log .logflags h2 { margin: 0 0 2px; font-size: 14px; }
.pg-log .logflags > p { margin: 0 0 12px; font-size: 13px; color: var(--muted);
  max-width: 80ch; }
.pg-log .logflags > p strong { color: var(--fg); font-weight: 600; }
.pg-log form.flagform { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin: 0; }
.pg-log form.flagform input[type=text] { width: 260px; min-width: 0; height: 34px; margin: 0; }
.pg-log form.flagform button { margin: 0; }
.pg-log form.flagform p.muted { flex-basis: 100%; margin: 2px 0 0; font-size: 12px;
  max-width: 80ch; }

/* Filters: segmented links; the current choice is a raised chip, not a link */
.pg-log .logbar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px;
  margin: 0 0 12px; font-size: 13px; }
.pg-log .seg { display: inline-flex; align-items: center; gap: 2px; padding: 2px;
  background: var(--panel); border-radius: var(--ctl-radius); }
.pg-log .seg .seglabel { padding: 0 6px 0 8px; font-size: 12.5px; color: var(--muted); }
.pg-log .seg a, .pg-log .seg .on { padding: 3px 10px; border-radius: 6px; line-height: 1.5;
  color: var(--ink-2); text-decoration: none; }
.pg-log .seg a { transition: background-color 0.15s var(--ease), color 0.15s var(--ease); }
.pg-log .seg a:hover { background: var(--hover); color: var(--fg); }
.pg-log .seg .on { background: var(--card); color: var(--fg); font-weight: 500;
  box-shadow: 0 0 0 1px var(--line), 0 1px 2px rgb(20 20 20 / 0.05); }
.pg-log .logbar > .muted { font-size: 12.5px; }

/* Entries: number, time and action never wrap; ids and payloads are the only monospace */
.pg-log table.logtable { font-size: 13px; }
.pg-log .logtable th, .pg-log .logtable td { padding: 8px 14px; vertical-align: top; }
.pg-log .logtable th:first-child, .pg-log .logtable td:first-child { width: 1%;
  padding-right: 4px; text-align: right; white-space: nowrap; color: var(--muted);
  font-variant-numeric: tabular-nums; }
.pg-log .logtable td.when { width: 1%; font-size: 12.5px; }
.pg-log .logtable td:nth-child(3) { width: 22%; }
.pg-log .logtable .kind { color: var(--muted); }
.pg-log .logtable td:nth-child(4) { width: 1%; white-space: nowrap; font-weight: 500; }
.pg-log .logtable td.payload { overflow-wrap: anywhere; }
.pg-log .logtable td.payload > .mono { display: block; margin: 1px 0 0; font-size: 11.5px;
  line-height: 1.55; }
.pg-log .logtable td.payload details { margin-top: 2px; }
.pg-log .logtable td.payload summary { font-size: 12px; }
.pg-log .logtable td.payload details .mono { display: block; margin: 6px 0 2px;
  padding: 8px 10px; background: var(--panel); border-radius: 6px; font-size: 11.5px; }
@media (prefers-reduced-motion: reduce) { .pg-log .seg a { transition: none; } }

@media (max-width: 600px) {
  .pg-log p.chainmeta { margin-left: 0; }
  .pg-log form.flagform input[type=text] { width: 100%; }
  .pg-log table.logtable { display: block; overflow: visible; }
  .pg-log .logtable thead { position: absolute; width: 1px; height: 1px; overflow: hidden;
    clip-path: inset(50%); white-space: nowrap; }
  .pg-log .logtable tbody { display: block; }
  .pg-log .logtable tr { display: grid; grid-template-columns: auto minmax(0, 1fr);
    column-gap: 10px; padding: 10px 12px; border-bottom: 1px solid var(--line); }
  .pg-log .logtable tr:last-child { border-bottom: 0; }
  .pg-log .logtable td, .pg-log .logtable td:nth-child(n) { display: block; width: auto;
    padding: 0; border: 0; text-align: left; background: none; }
  .pg-log .logtable td:nth-child(1) { grid-area: 1 / 1; }
  .pg-log .logtable td.when { grid-area: 1 / 2; }
  .pg-log .logtable td:nth-child(4) { grid-area: 2 / 1 / 3 / 3; white-space: normal; }
  .pg-log .logtable td:nth-child(3) { grid-area: 3 / 1 / 4 / 3; color: var(--muted);
    font-size: 12.5px; }
  .pg-log .logtable td.payload { grid-area: 4 / 1 / 5 / 3; margin-top: 4px; }
}
"""
