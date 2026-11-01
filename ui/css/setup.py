"""Set up and run (/setup, /run).

This page's own CSS, scoped to its markup (see ui/css/__init__.py).
"""

CSS = """
/* Set up's tables: words stay whole (a cell wraps only between words), controls sit on one
   row, and the claims table's wording column takes the room. */
table.tidy td { overflow-wrap: break-word; }
table.tidy td.nowrap { white-space: nowrap; }
table.tidy td .mono { white-space: nowrap; word-break: normal; overflow-wrap: normal; }
table.tidy td.controls { width: 1%; white-space: nowrap; }
table.tidy .row-actions { display: flex; flex-wrap: nowrap; gap: 6px; align-items: center; }
table.tidy .row-actions form.inline { display: flex; gap: 6px; align-items: center; }
table.tidy .row-actions input[type=text] { min-width: 0; width: 170px; margin: 0; }
table.tidy .row-actions button { margin: 0; }
table.tidy td.controls details { margin-top: 6px; }
table.tidy td.controls details > summary { font-size: 13px; }
table.tidy td.controls details[open] > summary { margin-bottom: 6px; }
table.claim-order td.brief { padding-right: 8px; }
table.claim-order td .where, table.claim-order td .kind { display: block;
  white-space: nowrap; color: var(--muted); font-size: 12.5px; }
table.claim-order td .where { margin-top: 2px; }
table.claim-order td.decide { width: 1%; white-space: nowrap; overflow-wrap: normal; }
table.claim-order .claim-actions { display: flex; flex-wrap: nowrap; gap: 6px;
  align-items: center; }
table.claim-order .claim-actions form.inline { display: flex; gap: 6px; }
table.claim-order .claim-actions button { margin: 0; }
/* Quiet controls on every row: the arrows and Remove show a border only on hover or focus */
table.claim-order .claim-actions button:not([value=accepted]) { background: transparent;
  border-color: transparent; box-shadow: none; }
table.claim-order .claim-actions button:not([value=accepted]):hover,
table.claim-order .claim-actions button:not([value=accepted]):focus-visible {
  border-color: var(--line-strong); background: var(--card); }
table.claim-order .claim-actions button[name=delta] { min-width: 30px; padding: 0 6px;
  font-size: 15px; color: var(--muted); }
table.claim-order td.decide details > summary { color: var(--muted); }
/* Remove stays apart from the reorder buttons, so a slip on Down does not land on it */
table.claim-order .claim-actions form:last-child { margin-left: 14px; }
table.claim-order td.decide details { margin-top: 6px; white-space: normal; }
table.claim-order td.decide details > summary { white-space: nowrap; font-size: 13px; }
table.claim-order td.decide textarea { width: 100%; min-width: 260px; margin: 6px 0; }

/* Set up and run: a step strip, one row of actions per step, long text folded away */
ol.steps { list-style: none; display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0 8px;
  padding: 0; counter-reset: none; }
ol.steps li { margin: 0; }
ol.steps a { display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px 6px 6px;
  border: 1px solid var(--line); border-radius: 999px; background: var(--card);
  color: var(--fg); text-decoration: none; font-size: 13px; }
ol.steps a:hover { border-color: var(--line-strong); }
ol.steps .n { display: inline-grid; place-items: center; width: 22px; height: 22px;
  border-radius: 50%; background: var(--panel); color: var(--muted); font-size: 12px;
  font-weight: 600; font-variant-numeric: tabular-nums; }
ol.steps .ok .n { background: var(--accent); color: var(--card); }
ol.steps .todo .n { box-shadow: inset 0 0 0 1.5px var(--accent); background: var(--card);
  color: var(--accent); }
ol.steps .state { color: var(--muted); font-size: 12px; }
ol.steps .todo .state { color: var(--accent); font-weight: 500; }
.inline-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
  margin: 0 0 8px; }
.inline-actions button, .inline-actions input { margin: 0; }
.inline-actions .muted { font-size: 12.5px; flex: 1 1 260px; }
.inline-actions a.button { border: 1px solid var(--line-strong); background: var(--card);
  color: var(--fg); }
.inline-actions a.button:hover { border-color: var(--muted); }
form.plain { margin: 8px 0 16px; }
form.plain > p.muted { font-size: 12.5px; max-width: 78ch; }
table.files .coverage { color: var(--muted); font-size: 12.5px; margin-top: 4px; }
table.files .coverage ul { margin: 4px 0 0; padding-left: 18px; }
table.hashes td.hash { white-space: normal; overflow-wrap: anywhere; font-size: 12px; }
details.add-files { margin: 4px 0 8px; }
details.add-files > summary { font-size: 13.5px; cursor: pointer; }
details.add-files[open] > summary { margin-bottom: 10px; }
.uploads { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
.uploads form.box { margin: 0; }
.uploads form.box p .muted { display: block; margin-top: 6px; font-size: 12.5px; }
.uploads form.box label:has(> select) { margin: 0; }
details.fold > p { max-width: 78ch; }
.removed ul { list-style: none; display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 12px;
  padding: 0; }
.removed li { display: inline-flex; align-items: center; gap: 8px; padding: 2px 4px 2px 10px;
  border: 1px solid var(--line); border-radius: var(--radius); background: var(--card); }
.removed li form.inline button { margin: 0; }
ul.ready { list-style: none; margin: 0 0 14px; padding: 0; max-width: 78ch; }
ul.ready li { position: relative; padding: 3px 0 3px 24px; }
ul.ready li::before { content: ""; position: absolute; left: 3px; top: 9px; width: 10px;
  height: 10px; border-radius: 50%; box-shadow: inset 0 0 0 1.5px var(--line-strong); }
ul.ready li.ok::before { background: var(--accent); box-shadow: none; }
ul.ready li.todo::before { box-shadow: inset 0 0 0 1.5px var(--accent); }
.checks { display: grid; gap: 10px; margin: 0 0 14px; }
.checks label { display: flex; align-items: flex-start; gap: 10px; margin: 0; font-weight: 400;
  line-height: 1.5; cursor: pointer; }
.checks input[type=checkbox] { margin: 3px 0 0; flex: none; }
details.options { margin: 0 0 14px; }
details.options > summary { font-size: 13px; color: var(--muted); cursor: pointer; }
details.options[open] > summary { margin-bottom: 10px; }
"""
