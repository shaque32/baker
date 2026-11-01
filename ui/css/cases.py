"""Cases (/cases), the enter-your-name form and the error page.

This page's own CSS, scoped to its markup (see ui/css/__init__.py).

The cases page is the first screen after install: a calm list of cases (still a <table>, which
packaging/smoke_ui.py selects on), the cases folder as one muted line, then one card to make a
case whose "Make the case" is the page's only navy button. The two passphrase fields fold away
when "Encrypt this case" is unchecked (CSS :has(), no script; the server still checks them).
"""

CSS = """
/* Cases: the list */
.pg-cases { max-width: 880px; }
.pg-cases h1 { margin-bottom: 20px; }
.pg-cases .lede { max-width: 68ch; }
.pg-cases .vh { position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip-path: inset(50%); white-space: nowrap; }
/* Each row reads like the site's ledger: the case name, one small line of facts (state and
   encryption), and its action at the right. Still a <table>; the header row stays for screen
   readers and is hidden on screen, since each fact already says what it is. */
.pg-cases table.caselist, .pg-cases .caselist tbody { display: block; }
.pg-cases table.caselist { margin: 0 0 12px; border-radius: 12px; overflow: hidden; }
.pg-cases .caselist thead { position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip-path: inset(50%); }
.pg-cases .caselist tbody tr { display: grid; align-items: center; gap: 4px 16px;
  grid-template-columns: auto auto minmax(0, 1fr) auto; padding: 16px 20px;
  border-bottom: 1px solid var(--line); transition: background-color 0.15s var(--ease); }
.pg-cases .caselist tbody tr:last-child { border-bottom: 0; }
.pg-cases .caselist tbody tr:hover { background: var(--hover); }
.pg-cases .caselist tbody tr:hover td { background: none; }
.pg-cases .caselist td { display: block; padding: 0; border: 0; overflow-wrap: normal; }
.pg-cases .caselist td.name { grid-column: 1 / 4; font-weight: 600; font-size: 14.5px;
  line-height: 1.4; }
.pg-cases .caselist td.name .mono { display: block; margin-top: 2px; font-size: 12px;
  font-weight: 400; word-break: normal; overflow-wrap: anywhere; }
.pg-cases .caselist td.state, .pg-cases .caselist td.lock { grid-row: 2; font-size: 12.5px;
  color: var(--muted); }
.pg-cases .caselist td.state { grid-column: 1; }
.pg-cases .caselist td.lock { grid-column: 2; white-space: nowrap; }
.pg-cases .caselist td.lock::before { content: ""; display: inline-block; width: 6px;
  height: 6px; margin: 0 7px 1px 0; border-radius: 50%; vertical-align: middle;
  background: var(--card); box-shadow: inset 0 0 0 1.5px var(--line-strong); }
.pg-cases .caselist td.lock-open::before, .pg-cases .caselist td.lock-locked::before {
  background: var(--accent); box-shadow: none; }
.pg-cases .caselist td.go { grid-column: 4; grid-row: 1 / span 2; white-space: nowrap; }
.pg-cases .caselist td.go button { margin: 0; min-height: 32px; padding: 0 14px;
  font-size: 13px; }
.pg-cases .unlock { display: inline-flex; align-items: center; gap: 8px; }
.pg-cases .unlock input[type=password] { margin: 0; min-width: 0; width: 220px; height: 32px;
  font-size: 13px; }
.pg-cases .unlock button { margin: 0; }
.pg-cases p.empty { margin: 0 0 12px; padding: 20px; color: var(--muted);
  background: var(--card); border: 1px dashed var(--line-strong); border-radius: 12px; }
.pg-cases p.where { font-size: 12.5px; color: var(--muted); max-width: 78ch; margin: 0; }
.pg-cases p.where .mono { font-size: 12px; word-break: normal; overflow-wrap: anywhere; }
@media (prefers-reduced-motion: reduce) { .pg-cases .caselist tbody tr { transition: none; } }

/* Cases: making a new case, one card with the page's one primary button */
.pg-cases section.newcase { margin-top: 44px; }
.pg-cases section.newcase h2 { margin: 0 0 12px; }
.pg-cases section.newcase form.box { padding: 22px 24px; margin: 0; border-radius: 12px; }
.pg-cases section.newcase label:has(> input.wide) { max-width: 520px; }
.pg-cases section.newcase p { margin: 0 0 16px; }
.pg-cases section.newcase label:has(> input[type=checkbox]) { margin: 0; }
.pg-cases .pass { margin: 0 0 20px; padding-left: 26px; }
.pg-cases .pass .passfields { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.pg-cases .pass .passfields input { margin: 0; flex: 1 1 200px; max-width: 247px;
  min-width: 0; }
.pg-cases .pass p.muted { margin: 0; max-width: 62ch; line-height: 1.5; }
.pg-cases form.box:has(input[name=encrypt]:not(:checked)) .pass { display: none; }
.pg-cases section.newcase button.primary { margin: 0; min-height: 36px; padding: 0 18px; }

/* The enter-your-name form, here and on the set-up page */
form.nameform { display: grid; gap: 12px; max-width: 640px; padding: 18px 20px;
  border-radius: 12px; margin: 0 0 28px; }
form.nameform p { margin: 0; color: var(--muted); max-width: 66ch; }
form.nameform p strong { display: block; margin-bottom: 2px; font-size: 14.5px;
  color: var(--fg); }
form.nameform .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
form.nameform .row input { flex: 1 1 220px; max-width: 320px; margin: 0; }
form.nameform .row button { margin: 0; }
.pg-cases form.nameform { max-width: none; }

/* The error page: what went wrong, and one way back */
.pg-error { max-width: 560px; padding-top: 56px; }
.pg-error h1 { font: 500 13px/1.4 var(--sans); color: var(--muted); margin: 0 0 6px;
  font-variant-numeric: tabular-nums; }
.pg-error p.lede { font: 600 22px/1.35 var(--sans); color: var(--fg); letter-spacing: -0.01em;
  margin: 0 0 24px; }
.pg-error p.lede::first-letter { text-transform: uppercase; }
.pg-error .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 20px;
  margin: 0; }
.pg-error a.button { color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); box-shadow: 0 1px 2px rgb(20 20 20 / 0.05);
  transition: background-color 0.15s var(--ease), border-color 0.15s var(--ease); }
.pg-error a.button:hover { background: var(--hover); border-color: var(--line-hover); }
.pg-error .actions > a:not(.button) { font-size: 13.5px; }

@media (max-width: 600px) {
  .pg-cases h1 { margin-bottom: 16px; }
  .pg-cases .caselist tbody tr { padding: 14px 16px; gap: 2px 12px;
    grid-template-columns: minmax(0, 1fr) auto; }
  .pg-cases .caselist td.name { grid-column: 1 / -1; margin-bottom: 4px; }
  .pg-cases .caselist td.state { grid-column: 1; grid-row: 2; }
  .pg-cases .caselist td.lock { grid-column: 1; grid-row: 3; }
  .pg-cases .caselist td.go { grid-column: 2; grid-row: 2 / span 2; }
  .pg-cases .caselist tr:has(.unlock) td.go { grid-column: 1 / -1; grid-row: 4;
    margin-top: 10px; }
  .pg-cases .unlock { display: flex; width: 100%; }
  .pg-cases .unlock input[type=password] { flex: 1; width: auto; }
  .pg-cases section.newcase { margin-top: 36px; }
  .pg-cases section.newcase form.box { padding: 18px 16px; }
  .pg-cases .pass { padding-left: 0; }
  .pg-cases .pass .passfields input { max-width: none; }
  .pg-error { padding-top: 24px; }
}
"""
