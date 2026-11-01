"""Help (/help).

This page's own CSS, scoped to its markup (see ui/css/__init__.py).

Three sections divided by a hairline, prose kept under ~70 characters a line. The bug report's
full text is folded under "Exactly what the file holds": every byte stays on the page.
"""

CSS = """
.pg-help { max-width: 760px; }
.pg-help h1 { margin-bottom: 8px; }
.pg-help section.hs { padding: 28px 0 4px; border-top: 1px solid var(--line); }
.pg-help h1 + section.hs { border-top: 0; padding-top: 12px; }
.pg-help section.hs h2 { margin: 0 0 10px; }
.pg-help section.hs h3 { font-size: 13.5px; margin: 20px 0 6px; }
.pg-help section.hs p, .pg-help section.hs li { max-width: 60ch; text-wrap: pretty; }
.pg-help section.hs ul { margin: 0 0 12px; padding-left: 20px; }
.pg-help section.hs li { margin: 0 0 6px; line-height: 1.55; }
.pg-help section.hs li::marker { color: var(--muted); }
.pg-help code { font: 400 12.5px var(--mono); color: var(--ink-2); background: var(--panel);
  border-radius: 4px; padding: 1px 5px; }

/* the three steps, numbered in small rings */
.pg-help ol.steps { list-style: none; counter-reset: step; margin: 16px 0 8px; padding: 0;
  display: grid; gap: 10px; }
.pg-help ol.steps li { counter-increment: step; display: flex; align-items: center;
  flex-wrap: wrap; gap: 4px 8px; margin: 0; padding-left: 34px; position: relative;
  min-height: 34px; }
.pg-help ol.steps li::before { content: counter(step); position: absolute; left: 0; top: 50%;
  transform: translateY(-50%); display: grid; place-items: center; width: 22px; height: 22px;
  border-radius: 50%; font: 500 12px/1 var(--sans); color: var(--muted); background: var(--card);
  box-shadow: inset 0 0 0 1px var(--line-strong); font-variant-numeric: tabular-nums; }
.pg-help ol.steps a.button { color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); box-shadow: 0 1px 2px rgb(20 20 20 / 0.05);
  transition: background-color 0.15s var(--ease), border-color 0.15s var(--ease); }
.pg-help ol.steps a.button:hover { background: var(--hover); border-color: var(--line-hover); }

/* the report's text, folded */
.pg-help details.filetext { margin: 8px 0 16px; }
.pg-help details.filetext > summary { font-size: 13.5px; }
.pg-help details.filetext[open] > summary { margin-bottom: 10px; }
.pg-help pre.bugreport { margin: 0; max-height: 480px; overflow: auto; padding: 14px 16px;
  font: 400 12px/1.6 var(--mono); color: var(--ink-2); background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); scrollbar-width: thin; }
.pg-help p.flash.err { max-width: 60ch; }

/* what it does and does not, side by side when there is room */
.pg-help .dodont { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 0 32px; }
.pg-help .dodont h3 { margin-top: 12px; }
.pg-help section.about p.muted { font-size: 12.5px; margin-top: 4px; }

@media (max-width: 600px) {
  .pg-help section.hs { padding-top: 22px; }
  .pg-help pre.bugreport { max-height: 360px; padding: 12px; }
}
"""
