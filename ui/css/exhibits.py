"""Exhibits (/exhibits, /exhibit, /exhibit/match, /request-letter).

This page's own CSS, scoped to its markup (see ui/css/__init__.py). The exhibit and match pages
show fragments of the report (core/report/restore.py); they are restyled here under the page's
wrapper (.pg-exhibits, .pg-exhibit, .pg-match, .pg-letter), so the exported report keeps its own
look.
"""


def context_table_css(scope: str) -> str:
    """The conversation table (core/report/restore.py context_table) under one page wrapper.

    Words break only at spaces, never mid-word; direction and tier never wrap; the columns the
    expert reads second (as printed, direction, tier, source) are smaller and muted. Columns:
    UTC, phone's local time, as printed, sender, direction, message, tier, source."""
    t = f"{scope} table.ctx"
    return f"""
{t} {{ font-size: 13px; }}
{t} th, {t} td {{ padding: 8px 12px; }}
{t} td {{ overflow-wrap: break-word; word-break: normal; }}
{t} td.t {{ font-variant-numeric: tabular-nums; }}
{t} td:nth-child(2) {{ color: var(--ink-2); }}
{t} td:nth-child(3), {t} td:nth-child(5), {t} td:nth-child(7) {{ color: var(--muted);
  font-size: 12.5px; }}
{t} td:nth-child(5), {t} td:nth-child(7) {{ white-space: nowrap; }}
{t} td:nth-child(6) {{ min-width: 26ch; color: var(--fg); }}
{t} td.mono {{ font-size: 12px; word-break: normal; overflow-wrap: break-word; }}
{t} tr.target td {{ font-weight: 400; background: var(--accent-bg); }}
{t} tr.target td:nth-child(6) {{ font-weight: 600; }}
{t} tr.target td:first-child {{ box-shadow: inset 2px 0 0 var(--accent); }}
{scope} details.related {{ margin: 24px 0 8px; }}
{scope} details.related > summary {{ font-size: 13.5px; }}
{scope} details.related[open] > summary {{ margin-bottom: 12px; }}
{scope} details.related > p {{ max-width: 62ch; font-size: 13px; }}
"""


# A highlighted span: a navy underline on the soft yellow, not a border on a rounded box.
MARK_CSS = """
{s} mark { border-bottom: 0; border-radius: 2px; padding: 0 1px;
  text-decoration: underline 1.5px var(--await); text-underline-offset: 3px;
  text-decoration-skip-ink: none; }
{s} .piece { font: 12px/1.5 var(--mono); border: 0; border-radius: 4px; background: var(--panel);
  padding: 1px 5px; }
"""

CSS = (
    """
/* the group's shared bits: a quiet back link, prose at a readable measure */
.pg-exhibits > p:not(.warn), .pg-exhibit > p, .pg-match > p, .pg-letter p { max-width: 64ch;
  text-wrap: pretty; }
.pg-exhibit p.back, .pg-match p.back { margin: 0 0 14px; font-size: 13px; }
.pg-exhibit p.back a, .pg-match p.back a { color: var(--muted); }
.pg-exhibit p.back a:hover, .pg-match p.back a:hover { color: var(--fg); }

/* Exhibits: the list, then one form with one primary action */
.pg-exhibits table.exhibits td.n { white-space: nowrap; }
.pg-exhibits table.exhibits td.meta { color: var(--muted); font-size: 12.5px; }
.pg-exhibits form.box { max-width: 760px; padding: 20px 22px; }
.pg-exhibits form.box .fields { display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr); gap: 0 16px; }
.pg-exhibits form.box .fields label { display: grid; margin: 0; }
.pg-exhibits form.box .fields input, .pg-exhibits form.box .fields select { width: 100%;
  min-width: 0; margin: 0; }
.pg-exhibits form.box .hint { font-weight: 400; font-size: 12.5px; color: var(--muted);
  margin-top: -4px; }
.pg-exhibits form.box textarea { margin: 0; }
.pg-exhibits form.box fieldset.msgsplit .muted { font-size: 12.5px; }
.pg-exhibits form.box button.primary { margin-top: 2px; }
@media (max-width: 640px) {
  .pg-exhibits form.box { padding: 16px; }
  .pg-exhibits form.box .fields { grid-template-columns: minmax(0, 1fr); }
}

/* One exhibit: the name is the page heading; each quoted message is a ruled section and each
   match the one card inside it */
.pg-exhibit h1 { margin-bottom: 4px; }
.pg-exhibit .exhibit { border: 0; border-radius: 0; background: none; padding: 0; margin: 0; }
.pg-exhibit .exhibit > h3 { display: none; }
.pg-exhibit .exhibit > p { max-width: 62ch; }
.pg-exhibit .exhibit > p.muted { font-size: 12.5px; }
.pg-exhibit .exhibit > p.muted .mono { font-size: 12px; }
.pg-exhibit .exhibit > p:nth-of-type(2) { font-weight: 500; color: var(--fg); margin: 12px 0 0; }
.pg-exhibit .exhibit > h4 { font: 600 15px/1.4 var(--sans); margin: 32px 0 10px;
  padding-top: 24px; border-top: 1px solid var(--line); }
.pg-exhibit .exhibit > blockquote { background: none; border: 0;
  border-left: 2px solid var(--line-strong); border-radius: 0; padding: 2px 0 2px 14px;
  margin: 0 0 12px; font-size: 15px; max-width: 64ch; }
.pg-exhibit .exhibit > h4 + blockquote + p:not(.muted) { font-size: 13.5px; }
.pg-exhibit .item { padding: 14px 18px; margin: 10px 0; }
.pg-exhibit .item > p:first-child { font-size: 12.5px; color: var(--muted); margin: 0 0 10px;
  line-height: 1.55; }
.pg-exhibit .item > p:first-child .mono { font-size: 12px; word-break: normal;
  overflow-wrap: anywhere; }
.pg-exhibit .item blockquote { font-size: 15px; margin: 0 0 10px; padding: 0 0 0 12px; }
.pg-exhibit .item ul { margin: 0; padding-left: 18px; font-size: 13px; color: var(--ink-2);
  max-width: 62ch; }
.pg-exhibit .item li { margin: 3px 0; }
.pg-exhibit .exhibit .nf { color: var(--fg); }
.pg-exhibit details.pasted { margin: 32px 0 0; padding-top: 20px;
  border-top: 1px solid var(--line); }
.pg-exhibit details.pasted > summary { font-size: 13.5px; }
.pg-exhibit pre.exhibit-text { background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 12px 14px; margin: 10px 0 0; font-size: 12.5px; }
.pg-exhibit .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 32px;
  margin: 24px 0 0; }
.pg-exhibit form.act { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 10px;
  margin: 0; font-size: 12.5px; color: var(--muted); }
.pg-exhibit form.act button { margin: 0; }
.pg-exhibit form.remove button { color: var(--con); }
.pg-exhibit form.remove button:hover { background: var(--con-bg); border-color: var(--con-line); }

/* A match in context: what the exhibit prints, how it matched, then the conversation */
.pg-match p.prints { margin: 16px 0 6px; font-size: 13px; }
.pg-match > blockquote { background: none; border: 0; border-left: 2px solid var(--line-strong);
  border-radius: 0; padding: 2px 0 2px 14px; margin: 0 0 12px; font-size: 15px;
  max-width: 64ch; }
.pg-match ul.notes { margin: 0 0 12px; padding-left: 18px; font-size: 13px; color: var(--ink-2);
  max-width: 62ch; }
.pg-match ul.notes li { margin: 3px 0; }
.pg-match p.tiers { font-size: 12.5px; margin: 0 0 28px; }
.pg-match > p:not([class]) { font-size: 13px; color: var(--ink-2); }

/* The request letter: one sheet at a letter's measure, the download beside the heading */
.pg-letter .letter-head { display: flex; flex-wrap: wrap; align-items: flex-end;
  justify-content: space-between; gap: 12px 32px; max-width: 840px; }
.pg-letter .letter-head > div { flex: 1 1 420px; }
.pg-letter .letter-head p { margin: 0; }
.pg-letter a.button { flex: none; color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); }
.pg-letter a.button:hover { background: var(--hover); border-color: var(--line-hover); }
.pg-letter pre.letter { box-sizing: border-box; max-width: 840px; margin: 24px 0 0;
  padding: 32px 36px; background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); color: var(--fg); font: 12.5px/1.65 var(--mono);
  overflow-wrap: anywhere; }
@media (max-width: 600px) {
  .pg-letter pre.letter { padding: 20px 16px; font-size: 12px; }
}
"""
    + context_table_css(".pg-match")
    + MARK_CSS.replace("{s}", ".pg-exhibit")
    + MARK_CSS.replace("{s}", ".pg-match")
)
