"""Selection (/selection, /selection/context).

This page's own CSS, scoped to its markup (see ui/css/__init__.py). Both pages show fragments of
the report (core/report/selection.py, paired.py, restore.py); they are restyled here under the
page's wrapper (.pg-selection, .pg-context), so the exported report keeps its own look.
"""

from ui.css.exhibits import MARK_CSS, context_table_css

CSS = (
    """
.pg-selection > p, .pg-context > p { max-width: 64ch; text-wrap: pretty; }
.pg-context p.back { margin: 0 0 14px; font-size: 13px; }
.pg-context p.back a { color: var(--muted); }
.pg-context p.back a:hover { color: var(--fg); }
.pg-context p.picked { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.pg-context p.tiers { font-size: 12.5px; margin: 0 0 24px; }
.pg-context > p:not([class]) { font-size: 13px; color: var(--ink-2); }

/* the opening: one paragraph, the definitions and the coverage notice folded, then what was
   found as ledger rows (the site's mock panel), not a bulleted wall */
.pg-selection details.terms { margin: -4px 0 16px; }
.pg-selection details.terms > summary { font-size: 13px; }
.pg-selection details.terms[open] > summary { margin-bottom: 8px; }
.pg-selection details.terms > p { max-width: 64ch; font-size: 13px; }
.pg-selection > .banner { max-width: 64ch; }
.pg-selection > ul { list-style: none; padding: 0; margin: 4px 0 8px; max-width: 860px;
  background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); }
.pg-selection > ul > li { padding: 10px 16px; border-top: 1px solid var(--line);
  font-size: 13.5px; line-height: 1.5; }
.pg-selection > ul > li:first-child { border-top: 0; }

/* section headings read as headings, not small labels */
.pg-selection > h3.eyebrow, .pg-selection > h3#paired-audit { font: 600 18px/1.35 var(--sans);
  letter-spacing: -0.005em; color: var(--fg); margin: 56px 0 8px; padding-top: 24px;
  border-top: 1px solid var(--line); }
.pg-selection > h4 { font: 600 15px/1.4 var(--sans); margin: 36px 0 8px; }

/* one paragraph, exhibit or tag set */
.pg-selection .sel-unit { margin: 32px 0 44px; }
.pg-selection .sel-unit > h3 { font-size: 17px; }
.pg-selection .sel-n { height: 20px; padding: 0 7px; border: 0; border-radius: 4px;
  font: 500 12px var(--sans); }
.pg-selection .sel-unit > blockquote { background: none; border: 0;
  border-left: 2px solid var(--line-strong); border-radius: 0; padding: 2px 0 2px 16px;
  margin: 10px 0 12px; font-size: 15px; line-height: 1.6; max-width: 64ch; }
.pg-selection ul.sel-quotes li { font-size: 13px; color: var(--ink-2); max-width: 62ch; }

/* a passage: the summary, the exchange as a conversation, then what else is near */
.pg-selection .sel-passage { border-radius: var(--radius); margin: 16px 0; }
.pg-selection .sel-passage > .in { padding: 14px 18px; }
.pg-selection .sel-passage .where { margin-bottom: 4px; }
.pg-selection .sel-passage ul.sum { font-size: 13px; }
.pg-selection .sel-passage > .foot { font-size: 13px; }
.pg-selection .sel-passage > .foot > p { margin: 8px 0 0; }
.pg-selection .sel-convo { background: var(--panel); gap: 6px; padding: 16px 18px; }
/* a copy of the exchange on another source: a ruled section, not a card in the card */
.pg-selection .sel-passage .sel-passage { border: 0; border-top: 1px solid var(--line);
  border-radius: 0; background: none; margin: 14px 0 0; overflow: visible; }
.pg-selection .sel-passage .sel-passage > .in { padding: 14px 0 12px; }
.pg-selection .sel-passage .sel-passage > .sel-convo { border-top: 0;
  border-radius: var(--radius); }
.pg-selection .sel-passage .sel-passage > .foot { border-top: 0; padding: 8px 0 0; }

/* messages: flat tinted shapes. The chip text names each state; the ring only repeats it.
   A picked message keeps the report's soft yellow fill. */
.pg-selection .bub { border: 0; border-radius: 12px; padding: 8px 12px; box-shadow: none; }
.pg-selection .bub:not(.pick) { background: var(--card); }
.pg-selection .bub.out:not(.pick) { background: var(--accent-bg); }
.pg-selection .bub.dim:not(.pick) { background: transparent;
  box-shadow: inset 0 0 0 1px var(--line-strong); }
.pg-selection .bub.dim .body { color: var(--ink-2); }
.pg-selection .bub.pick { border: 0; box-shadow: inset 0 0 0 1.5px var(--amber); }
.pg-selection .bub.left { border: 0; outline: 1.5px dashed var(--con); outline-offset: -1.5px; }
.pg-selection .bub .who2 { font-size: 12px; }
.pg-selection .bub .body { font-size: 14px; line-height: 1.5; margin: 1px 0 2px; }
.pg-selection .bub .t { font-size: 12px; gap: 4px 8px; }
.pg-selection .tag { border-radius: 4px; padding: 2px 7px; font-weight: 500; font-size: 12px; }
.pg-selection .divider { border: 0; background: var(--card); padding: 2px 10px;
  border-radius: 999px; font-size: 12px; }

/* the paired check: a ruled section, its tables keep their own frame */
.pg-selection .pair { background: none; border: 0; border-top: 1px solid var(--line);
  border-radius: 0; padding: 20px 0 0; margin: 24px 0; }
.pg-selection .pair > p, .pg-selection .pair-claim > p { max-width: 62ch; }
.pg-selection .pair h4 { font: 600 15px/1.4 var(--sans); margin: 4px 0 6px; }
.pg-selection .pair > h4:not(:first-child) { margin-top: 28px; }
.pg-selection .pair > h4 + p.where { margin-bottom: 12px; }
.pg-selection .pair-claim { padding: 14px 0 4px; }
.pg-selection .pair-claim tr.thr td { font-size: 12.5px; }
.pg-selection .pair td.mono { font-size: 12px; word-break: normal; overflow-wrap: break-word;
  white-space: nowrap; }
.pg-selection p.letter-link { margin-top: 32px; }
@media (max-width: 600px) {
  .pg-selection .sel-passage > .in { padding: 12px 14px; }
  .pg-selection .sel-convo { padding: 12px 10px; }
  .pg-selection > ul > li { padding: 10px 12px; }
}
"""
    + context_table_css(".pg-context")
    + context_table_css(".pg-selection")
    + MARK_CSS.replace("{s}", ".pg-selection")
    + MARK_CSS.replace("{s}", ".pg-context")
)
