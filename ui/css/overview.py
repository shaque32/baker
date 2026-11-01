"""Case overview (/).

This page's own CSS, scoped to its markup (see ui/css/__init__.py): the notices (.ov-notices),
then the page body (.pg-overview). One column, as wide as the status strip, so the notices, the
status, the set-up rows and the record line up on one left and one right edge. The status strip
is the only box; the set-up and the record are hairline rows, like the site's .facts and .rows,
and the record is smaller and muted, so the run ids, versions and hashes stay present but quiet.
"""

CSS = """
/* the notices: one quiet panel, a row each, in place of a box each with a side stripe */
.ov-notices { box-sizing: border-box; max-width: 880px; margin: 0 0 24px; background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); }
.ov-notices > .banner, main .ov-notices > .banner { max-width: none; margin: 0; border: 0;
  border-radius: 0; box-shadow: none; background: none; padding: 11px 16px; }
.ov-notices > .banner + .banner { margin-top: 0; border-top: 1px solid var(--line); }
.ov-notices > #formats.banner { border: 0; background: none; padding: 11px 16px; }
.ov-notices > .banner + #formats.banner { border-top: 1px solid var(--line); }
.ov-notices .banner details > summary { color: var(--fg); font-weight: 400; }
.ov-notices .banner details > summary strong { font-weight: 500; }
.ov-notices .banner details[open] > summary { margin-bottom: 8px; }
.ov-notices .banner details > p, .ov-notices .banner details > p.format-notice {
  max-width: 76ch; margin-left: 18px; }
.ov-notices .banner details > p { color: var(--muted); }
.ov-notices .banner form { margin: 10px 0 0; }

.pg-overview h1 { max-width: 880px; margin-bottom: 16px; }

/* what waits on you: the one box on the page; the button, then the counts past a thin rule */
.pg-overview .casestatus { box-sizing: border-box; max-width: 880px; padding: 16px 20px;
  gap: 12px 24px; margin-bottom: 16px; }
.pg-overview .casestatus .findings { gap: 8px 20px; padding-left: 24px;
  border-left: 1px solid var(--line); min-height: 24px; align-items: center; }
.pg-overview #withheld { box-sizing: border-box; max-width: 880px; margin: 0 0 16px; }
.pg-overview #withheld ul { margin: 6px 0 0; font-size: 13px; }
.pg-overview form.box { box-sizing: border-box; max-width: 880px; }

/* case setup and the record: hairline rows with the label on the left */
.pg-overview h2 { margin: 44px 0 10px; }
.pg-overview ul.setuplist { max-width: 880px; margin: 0 0 10px; background: none; border: 0;
  border-radius: 0; border-top: 1px solid var(--line); }
.pg-overview ul.setuplist li { display: grid; grid-template-columns: 240px minmax(0, 1fr);
  gap: 2px 24px; align-items: baseline; padding: 12px 0; border-top: 0;
  border-bottom: 1px solid var(--line); }
.pg-overview .ov-dev { min-width: 0; }
.pg-overview .ov-dev b { font-weight: 600; }
.pg-overview .ov-dev .mono { display: block; margin-top: 1px; }
.pg-overview .ov-dev:not(:has(b)) { font-weight: 600; }
.pg-overview .ov-who { min-width: 0; color: var(--ink-2); }
.pg-overview .ov-none { display: inline-block; font-size: 12px; line-height: 1.5;
  padding: 1px 9px; border-radius: 999px; background: var(--panel); color: var(--muted); }
.pg-overview p.ov-note { max-width: 72ch; font-size: 13px; margin: 0 0 12px; }

.pg-overview .ov-record { margin-top: 52px; }
.pg-overview .ov-record h2 { margin-top: 0; font-size: 14px; }
.pg-overview dl.record { max-width: 880px; grid-template-columns: 240px minmax(0, 1fr);
  gap: 0 24px; margin: 0 0 4px; font-size: 13px; border-top: 1px solid var(--line); }
.pg-overview dl.record dt, .pg-overview dl.record dd { padding: 8px 0;
  border-bottom: 1px solid var(--line); }
.pg-overview dl.record dt { color: var(--muted); font-weight: 500; }
.pg-overview dl.record dd { max-width: none; color: var(--muted); }
.pg-overview dl.record dd .mono { font-size: 12px; }

/* the folds under the record: chain of custody and the reviewer, small and muted */
.pg-overview details.custody { max-width: 880px; margin: 0; padding: 10px 0;
  border-bottom: 1px solid var(--line); }
.pg-overview details.custody[open] { max-width: none; }
.pg-overview details.custody > summary { font-size: 13px; }
.pg-overview details.custody h2 { font-size: 13px; color: var(--muted); font-weight: 500;
  margin: 14px 0 6px; }
.pg-overview details.custody table { margin: 0 0 6px; font-size: 13px; }
.pg-overview details.custody th, .pg-overview details.custody td { padding: 8px 12px; }
.pg-overview details.custody td { overflow-wrap: normal; }
.pg-overview details.custody td:nth-child(2), .pg-overview details.custody td:nth-child(3),
.pg-overview details.custody td:nth-child(4), .pg-overview details.custody td:nth-child(7) {
  white-space: nowrap; }
.pg-overview details.custody td:nth-child(7) { color: var(--muted); font-size: 12.5px; }
.pg-overview details.custody td.mono { font-size: 11.5px; min-width: 16ch;
  overflow-wrap: anywhere; }
.pg-overview details.custody form.box { background: none; border: 0; padding: 0;
  margin: 10px 0 4px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pg-overview details.custody form.box input[type=text] { max-width: 280px; }

@media (max-width: 640px) {
  .pg-overview .casestatus .findings { padding-left: 0; border-left: 0; }
  .pg-overview ul.setuplist li { grid-template-columns: minmax(0, 1fr); }
  .pg-overview dl.record { grid-template-columns: minmax(0, 1fr); }
  .pg-overview dl.record dt { border-bottom: 0; padding-bottom: 0; }
  .pg-overview dl.record dd { margin: 0; padding-top: 2px; }
  .pg-overview details.custody { overflow-x: auto; }
}
"""
