"""The review screen's look: app chrome, ledger, cards and chat-style context on top of the
report's base styles (core/report/html.py CSS).

A quiet working dashboard (Stripe-style): sidebar navigation, light gray page, white cards.
IBM Plex Sans for all text as on getmabillon.com, Instrument Serif only for the wordmark, IBM
Plex Mono only for ids and hashes. Fully offline. The fonts (SIL
Open Font License) are vendored in ui/static/fonts and served by this screen at /static/fonts/;
the font stacks fall back to system fonts. The Mabillon mark is inline SVG, so no image request
is ever made.
"""

from __future__ import annotations

from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"
FONT_FILES = frozenset(p.name for p in FONT_DIR.glob("*.woff2"))

_LATIN = (
    "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,"
    "U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
)
_CYRILLIC = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"


def _face(family: str, file: str, weight: str, rng: str, style: str = "normal") -> str:
    return (
        f"@font-face {{ font-family: '{family}'; font-style: {style}; font-weight: {weight}; "
        f"font-display: swap; src: url('/static/fonts/{file}') format('woff2'); "
        f"unicode-range: {rng}; }}\n"
    )


FONT_CSS = (
    _face("IBM Plex Sans", "ibm-plex-sans-latin-wght-normal.woff2", "100 700", _LATIN)
    + _face("IBM Plex Sans", "ibm-plex-sans-cyrillic-wght-normal.woff2", "100 700", _CYRILLIC)
    + _face("Instrument Serif", "instrument-serif-latin-400-normal.woff2", "400", _LATIN)
    + _face("Instrument Serif", "instrument-serif-latin-400-italic.woff2", "400", _LATIN, "italic")
    + _face("IBM Plex Mono", "ibm-plex-mono-latin-400-normal.woff2", "400", _LATIN)
    + _face("IBM Plex Mono", "ibm-plex-mono-cyrillic-400-normal.woff2", "400", _CYRILLIC)
)

# A ledger page split into "for" and "against".
MARK = (
    "<svg class='mark' viewBox='0 0 24 24' width='24' height='24' aria-hidden='true' fill='none'>"
    "<rect x='2.75' y='2.75' width='18.5' height='18.5' rx='5' fill='#141414'/>"
    "<path d='M12 6.5v11' stroke='#f7f5f0' stroke-width='1.5' stroke-linecap='round'/>"
    "<path d='M6.75 9h2.5M6.75 12h2.5M6.75 15h2.5' stroke='#f7f5f0' stroke-width='1.5' "
    "stroke-linecap='round' opacity='0.9'/>"
    "<path d='M14.75 9h2.5M14.75 12h1.25' stroke='#f7f5f0' stroke-width='1.5' "
    "stroke-linecap='round' opacity='0.55'/></svg>"
)

THEME_CSS = """
/* Design tokens. A quiet working dashboard: white pages, a light sidebar, gray lines, one navy
   accent, and the verdict colors only as small text badges. One text face, IBM Plex Sans, for
   everything but the wordmark (Instrument Serif); IBM Plex Mono only for ids and hashes
   (.mono), so they compare by eye. Labels are never monospace or uppercase. The report keeps
   its own paper palette (core/report/html.py). */
:root { --fg: #1a2233; --bg: #f6f7f9; --card: #fff; --side: #f6f7f9; --panel: #f0f2f5;
  --line: #e3e6eb; --line-strong: #cfd4dc; --muted: #5f6878; --hover: #f9fafb;
  --serif: var(--sans); --wordmark: "Instrument Serif", Georgia, serif;
  --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace;
  --ring: rgb(29 53 87 / 0.16); --accent-bg: #ebf0f7; --unp: #5f6878; --unp-bg: #f0f2f5;
  --unp-line: #d9dde4; --await: #1d3557;
  --field: #fff; --amber: #b7862c; --radius: 8px; --sidebar: 232px; }
body { max-width: none; padding: 0 0 0 var(--sidebar); font-size: 14px; line-height: 1.55;
  background: var(--bg); }
main { max-width: 1120px; margin: 0; padding: 32px 48px 96px; }
main.wide { max-width: 1360px; }
p { margin: 0 0 12px; }
main > p, section > p, main > ul:not([class]), section > ul:not([class]), .lede {
  max-width: 78ch; }

/* Type: one sans face; sizes and weight, not a second font, make the hierarchy */
h1 { font: 600 24px/1.3 var(--sans); letter-spacing: -0.01em; margin: 0 0 8px;
  text-wrap: balance; }
h1 + p, .lede { color: var(--muted); }
h2 { font: 600 16px/1.4 var(--sans); letter-spacing: 0; margin: 40px 0 12px;
  padding: 0; border: 0; }
h3 { font: 600 14px/1.4 var(--sans); margin: 24px 0 8px; }
.eyebrow { font: 500 12.5px/1.4 var(--sans); letter-spacing: 0; text-transform: none;
  color: var(--muted); margin-bottom: 4px; }
.mono { font: 400 12px/1.5 var(--mono);
  color: var(--muted); letter-spacing: 0; word-break: break-all; }
.muted { color: var(--muted); }
a { color: var(--accent); text-decoration-color: rgb(29 53 87 / 0.3);
  text-underline-offset: 3px; }
a:hover { text-decoration-color: currentColor; }

/* Sidebar: the wordmark, the open case, the pages in three groups, and the offline line */
header.top { position: fixed; inset: 0 auto 0 0; z-index: 5; width: var(--sidebar);
  display: flex; flex-direction: column; background: var(--side);
  overflow-y: auto; scrollbar-width: thin; }
.bar { display: contents; }
.brand { display: flex; align-items: center; gap: 9px; text-decoration: none;
  color: var(--fg); padding: 20px 20px 0; }
.brand span { font: 400 22px/1 var(--wordmark); letter-spacing: -0.01em; }
.casename { display: flex; flex-direction: column; gap: 2px; font-weight: 600;
  font-size: 13px; line-height: 1.35; margin: 18px 12px 4px; padding: 10px 12px;
  background: var(--card); border: 1px solid var(--line); border-radius: var(--radius); }
.casename small { font: 400 12px var(--sans); color: var(--muted); letter-spacing: 0; }
.bar .right { order: 3; margin-top: auto; display: flex; flex-direction: column;
  align-items: flex-start; gap: 6px; padding: 16px 20px 20px; border-top: 1px solid var(--line); }
.pill { display: inline-flex; align-items: center; gap: 7px; border: 0; padding: 0;
  font: 500 12px/1.4 var(--sans); color: var(--muted); background: none;
  text-decoration: none; }
.pill::before { content: ""; flex: none; width: 6px; height: 6px; border-radius: 50%;
  background: var(--sup); }
a.pill::before { background: var(--accent); }
a.pill:hover { color: var(--fg); }
.who { font-size: 12px; color: var(--muted); } .who strong { color: var(--fg); font-weight: 600; }
nav.tabs { order: 2; display: flex; flex-direction: column; gap: 1px; padding: 12px 12px 16px;
  font-size: 13.5px; }
nav.tabs a { color: #3c4555; text-decoration: none; padding: 6px 10px; border-radius: 6px;
  white-space: nowrap; }
nav.tabs a:hover { color: var(--fg); background: rgb(20 20 20 / 0.045); }
nav.tabs a.on { color: var(--accent); font-weight: 600; background: var(--card);
  box-shadow: 0 0 0 1px var(--line), 0 1px 2px rgb(26 34 51 / 0.05); }
nav.tabs .sep { flex: none; height: 1px; margin: 8px 10px; background: var(--line); }
.casestatus { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 20px;
  background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 14px 18px; margin: 0 0 12px; }
.casestatus .findings { display: flex; flex-wrap: wrap; gap: 8px 16px; list-style: none;
  padding: 0; margin: 0; }
.casestatus .verdict { margin: 0 2px 0 0; }
details.custody { margin: 16px 0; }
details.custody > summary { font-size: 13.5px; color: var(--muted); }

/* Notices: a gray note, not a colored box. The demo and "not tested" notices stay visible. */
.banner, p.warn { background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 10px 14px 10px 16px; margin: 0 0 20px; color: #3c4555; font-size: 13px;
  line-height: 1.55; max-width: none; box-shadow: inset 3px 0 0 var(--line-strong); }
.banner strong, p.warn strong { font-size: inherit; font-weight: 600; color: var(--fg); }
.banner .banner { background: var(--card); margin: 8px 0 0;
  box-shadow: inset 2px 0 0 var(--amber); }
.caution { border: 0; border-left: 2px solid var(--amber); background: var(--panel);
  padding: 8px 12px; border-radius: 0 6px 6px 0; font-size: 13px; }
.flash { padding: 10px 14px; margin: 0 0 16px; border: 1px solid var(--line);
  border-radius: var(--radius); background: var(--card); font-size: 13.5px; }
.flash.err { border-color: var(--con-line); background: var(--con-bg); color: var(--con); }
.flash.toast { position: fixed; right: 24px; bottom: 24px; z-index: 10; margin: 0;
  max-width: min(420px, calc(100vw - 48px)); background: var(--fg); color: #fff;
  border-color: var(--fg); box-shadow: 0 8px 24px -12px rgb(20 20 20 / 0.4);
  animation: toast-out 0.3s ease 7s forwards; }
.flash.toast.err { animation: none; background: var(--con-bg); color: var(--con);
  border-color: var(--con-line); }
@keyframes toast-out { to { opacity: 0; visibility: hidden; } }
@media (prefers-reduced-motion: reduce) { .flash.toast { animation: none; } }

/* A source's format notice: one line with a small amber dot */
p.format-notice { position: relative; background: none; border: 0; border-radius: 0;
  box-shadow: none;
  padding: 0 0 0 16px; margin: 6px 0; font-size: 13px; line-height: 1.5; color: var(--fg); }
p.format-notice::before { content: ""; position: absolute; left: 2px; top: 0.55em; width: 6px;
  height: 6px; border-radius: 50%; background: var(--sup); }
p.format-notice.warn::before { background: var(--amber); }
p.format-notice strong { font-weight: 500; color: var(--fg); }
#formats.banner { background: var(--card); border: 1px solid var(--line); padding: 10px 16px; }
td p.format-notice { font-size: 12.5px; margin: 6px 0 0; }

/* coming back to the item a form acted on: mark it briefly */
[id] { scroll-margin-top: 24px; }
.item:target, .card:target, tr:target td { outline: 2px solid var(--accent); outline-offset: 2px; }
tr:target td { outline: 0; background: var(--accent-bg); }

/* Tables: flat, gray column names, thin row lines, numbers in tabular figures */
table { border-collapse: separate; border-spacing: 0; width: 100%; margin: 8px 0 20px;
  font-size: 13.5px; line-height: 1.5; background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); overflow: hidden; font-variant-numeric: tabular-nums; }
th, td { padding: 10px 16px; border-bottom: 1px solid var(--line); text-align: left;
  vertical-align: top; }
th { background: transparent; font: 500 12px/1.4 var(--sans); letter-spacing: 0;
  text-transform: none; color: var(--muted); padding-top: 8px; padding-bottom: 8px;
  white-space: nowrap; background: var(--hover); }
tr:last-child td { border-bottom: 0; }
tbody tr:hover td, table > tr:hover td { background: var(--hover); }
td .mono { display: inline-block; margin-top: 2px; }
td form.inline button { margin: 0; }
td input[type=text], td input[type=password] { min-width: 0; width: 100%; max-width: 260px;
  height: 32px; font-size: 13.5px; }
td button { min-height: 30px; padding: 0 10px; font-size: 13px; margin: 2px 6px 2px 0; }
.ctx td { font-size: 13px; }
td { overflow-wrap: anywhere; }
td.when { white-space: nowrap; font-variant-numeric: tabular-nums; color: var(--muted);
  font-size: 12.5px; }
td:has(> form.inline):not(:has(input[type=text])) { white-space: nowrap; }
td:has(> form.inline) details { white-space: normal; margin-top: 4px; }
td form.inline button { min-height: 28px; padding: 0 9px; font-size: 12.5px;
  margin: 2px 4px 2px 0; }
tr.target td { font-weight: 600; background: var(--accent-bg); }

/* Forms: labels above fields, 36px controls, one clear focus ring */
form.inline { display: inline; }
form.box { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 18px 20px; margin: 12px 0 20px; font-size: 13.5px; }
form.box > :last-child { margin-bottom: 0; }
form.box p { margin: 0 0 14px; }
form.box p.muted, form.box .muted { font-size: 12.5px; }
form.box > strong + label { margin-left: 10px; }
label { font-size: 13.5px; }
label:has(> input[type=text], > input[type=password], > select, > textarea) {
  display: inline-grid; gap: 6px; font-weight: 500; font-size: 13px;
  color: var(--fg); vertical-align: top; margin: 0 12px 4px 0; }
label:has(> input[type=number]) { display: inline-flex; align-items: center; gap: 8px;
  font-weight: 500; font-size: 13px; margin: 0 12px 4px 0; }
label:has(> input[type=number]) input { margin: 0; }
label:has(> textarea[name]), label:has(> input[type=text].wide) { display: grid;
  margin-right: 0; }
label:has(> input[type=checkbox], > input[type=radio]) { display: inline-flex;
  align-items: center; gap: 8px; margin: 0 16px 6px 0; cursor: pointer; }
input[type=text], input[type=password], input[type=number], input[type=search], select {
  height: 36px; }
input[type=text], input[type=password], input[type=number], input[type=search],
input[type=file], textarea, select {
  font: 400 14px/1.4 var(--sans); color: var(--fg); background: var(--field);
  border: 1px solid var(--line-strong); border-radius: 6px; padding: 0 10px;
  max-width: 100%; box-sizing: border-box; margin: 0 6px 6px 0;
  box-shadow: 0 1px 1px rgb(20 20 20 / 0.03); }
input[type=text], input[type=password] { min-width: min(280px, 100%); }
textarea { padding: 8px 10px; line-height: 1.55; min-height: 96px; resize: vertical; }
input[type=file] { height: auto; padding: 8px; background: var(--side); border-style: dashed;
  box-shadow: none; }
input[type=file]::file-selector-button { font: 500 13px var(--sans); color: var(--fg);
  background: var(--card); border: 1px solid var(--line-strong); border-radius: 6px;
  padding: 5px 10px; margin-right: 12px; cursor: pointer; }
select { appearance: none; -webkit-appearance: none; padding-right: 32px; cursor: pointer;
  background-image: linear-gradient(45deg, transparent 50%, var(--muted) 50%),
    linear-gradient(135deg, var(--muted) 50%, transparent 50%);
  background-position: calc(100% - 17px) 52%, calc(100% - 12px) 52%;
  background-size: 5px 5px; background-repeat: no-repeat; }
input::placeholder, textarea::placeholder { color: #9b978f; }
input[type=text]:hover, input[type=password]:hover, input[type=number]:hover, textarea:hover,
select:hover { border-color: #bdb9b0; }
input[type=text]:focus, input[type=password]:focus, input[type=number]:focus,
input[type=search]:focus, textarea:focus, select:focus {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--ring); }
input[type=checkbox], input[type=radio] { width: 15px; height: 15px; margin: 0;
  accent-color: var(--accent); cursor: pointer; }
input[type=text].wide, textarea { width: 100%; margin-right: 0; }
input:disabled, select:disabled, textarea:disabled { opacity: 0.55; cursor: not-allowed; }

/* A settings card: title and note, fields side by side with the unit inside the field */
form.settings { display: grid; gap: 16px; }
form.settings .settings-head h3 { margin: 0 0 2px; }
form.settings .settings-head p { margin: 0; font-size: 12.5px; }
form.settings .fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px 24px; max-width: 640px; }
form.settings label.field { display: grid; align-content: start; gap: 6px; margin: 0;
  font-weight: 500;
  font-size: 13px; }
form.settings small { font-weight: 400; font-size: 12px; color: var(--muted);
  line-height: 1.45; }
.unit-input { display: flex; align-items: center; height: 36px; max-width: 200px;
  border: 1px solid var(--line-strong); border-radius: 6px; background: var(--field);
  box-shadow: 0 1px 1px rgb(20 20 20 / 0.03); }
.unit-input:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--ring); }
.unit-input input[type=number] { flex: 1; min-width: 0; height: 34px; margin: 0; border: 0;
  box-shadow: none; background: transparent; font-variant-numeric: tabular-nums;
  -moz-appearance: textfield; appearance: textfield; }
.unit-input input[type=number]:focus { box-shadow: none; }
.unit-input input::-webkit-outer-spin-button,
.unit-input input::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.unit-input .unit { padding: 0 12px 0 4px; font-size: 13px; color: var(--muted); }
form.settings .actions { display: flex; }
form.settings .actions button { margin: 0; }

/* Buttons: quiet by default, navy for the one main action */
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  min-height: 32px; font: 500 13.5px/1 var(--sans); color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); border-radius: 6px; padding: 0 12px;
  margin: 6px 8px 0 0; cursor: pointer; box-shadow: 0 1px 1px rgb(20 20 20 / 0.04);
  vertical-align: middle; }
button:hover { background: var(--hover); border-color: #bdb9b0; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button.primary, button[value=accepted] { background: var(--accent); border-color: var(--accent);
  color: #fff; }
button.primary:hover, button[value=accepted]:hover { background: #142842; border-color: #142842; }
button[value=dismissed], button[value=removed] { color: var(--con); }
button[value=dismissed]:hover, button[value=removed]:hover { background: var(--con-bg);
  border-color: var(--con-line); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--ring); }
details summary { color: var(--accent); font-weight: 500; }
details summary::marker { color: var(--muted); }

/* evidence cards and tier badges: small square-cornered labels, color only in the text */
.item { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 14px 18px; margin: 10px 0; }
.item blockquote { background: none; border-left: 2px solid var(--line-strong);
  border-radius: 0; font-size: 14px; }
.badge { display: inline-flex; align-items: center; height: 20px; padding: 0 6px;
  margin: 0 6px 4px 0; border: 0; border-radius: 4px;
  font: 500 12px var(--sans); letter-spacing: 0; text-transform: none;
  color: #3c4555; background: var(--panel); }
.b-ai { color: var(--muted); background: var(--panel); }
.b-conf { color: var(--accent); background: var(--accent-bg); }
.b-open { color: var(--fg); }
.b-against { color: var(--con); background: var(--con-bg); }
.b-flag { color: var(--muted); background: transparent; box-shadow: inset 0 0 0 1px var(--line); }
.b-withheld { color: var(--muted); background: var(--panel); }
.b-challenge { color: var(--muted); background: transparent;
  box-shadow: inset 0 0 0 1px var(--line-strong); }
details.flag { margin-top: 6px; }
details.flag > summary { font-size: 12.5px; color: var(--muted); cursor: pointer; }
ul.flags form.inline button { margin-left: 8px; }

/* verdicts: a small label, no icon and no dashed edge; the words carry the meaning.
   Waiting on the expert is navy (your move), unproven is gray. */
body .verdict { gap: 0; padding: 1px 7px; border: 0; border-radius: 4px;
  font: 500 12px/18px var(--sans); }
body .verdict::before { content: none; }
.v-await { color: var(--accent); background: var(--accent-bg); }
.v-confirm { color: var(--con); background: var(--con-bg); }
.v-supai { color: var(--supai); background: var(--sup-bg); }
body .verdict.v-nt { color: var(--muted); background: var(--panel); border: 0; }

/* claims ledger: the queue, and the column beside a claim */
.tally { display: none; }
.counts { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 14px; }
.counts .verdict { font-size: 12px; }
.counts .verdict b { font-weight: 600; margin-left: 4px; }
.ledger { list-style: none; margin: 0; padding: 0; background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.ledger li { border-bottom: 1px solid var(--line); position: relative; }
.ledger li:last-child { border-bottom: 0; }
.ledger .row { padding: 12px 16px; }
.ledger li:hover { background: var(--hover); }
.ledger .meta a { color: var(--fg); font-weight: 600; text-decoration: none; }
.ledger .meta a::after { content: ""; position: absolute; inset: 0; }
.ledger .head { display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 4px 10px; margin-bottom: 4px; }
.ledger .head .meta { flex: 1 1 150px; min-width: 0; }
.ledger .meta { font: 400 12px var(--sans); color: var(--muted); letter-spacing: 0;
  padding-top: 1px; font-variant-numeric: tabular-nums; }
.ledger .text { font-size: 14px; line-height: 1.5; }
.ledger .needs { margin-top: 4px; font-size: 12.5px; color: var(--muted); }

/* claims overview: progress, one number per group, the next claim up, then the groups */
.overview-head { display: flex; flex-wrap: wrap; align-items: flex-end;
  justify-content: space-between; gap: 16px 40px; }
.overview-head > div:first-child { flex: 1 1 460px; }
.overview-head h1 { font: 600 24px/1.3 var(--sans); letter-spacing: -0.01em; margin: 0 0 8px; }
.progress { flex: 0 1 280px; margin-bottom: 14px; }
.progress .lbl { display: flex; justify-content: space-between; gap: 10px; font-size: 12.5px;
  color: var(--muted); margin-bottom: 6px; }
.progress .lbl b { color: var(--fg); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress .track { height: 4px; border-radius: 999px; background: var(--panel); overflow: hidden; }
.progress .track span { display: block; height: 100%; background: var(--accent);
  border-radius: 999px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px; margin: 24px 0 28px; }
.tile { display: flex; flex-direction: column; gap: 4px; padding: 16px 18px;
  background: var(--card); color: var(--fg); text-decoration: none;
  border: 1px solid var(--line); border-radius: var(--radius); }
.tile:hover { border-color: var(--line-strong); }
.tile.empty, .tile.t-you.empty { color: var(--muted); }
.tile .name { display: flex; align-items: center; gap: 7px; font-size: 12.5px; font-weight: 500;
  color: var(--muted); }
.tile .name::before { content: ""; width: 6px; height: 6px; border-radius: 50%;
  background: var(--line-strong); }
.tile.t-you .name::before { background: var(--accent); }
.tile.t-con .name::before { background: var(--con); }
.tile.t-sup .name::before { background: var(--sup); }
.tile .n { font: 600 30px/1.25 var(--sans); letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums; }
.tile.t-you .n { color: var(--accent); }
.tile .sub { font-size: 12.5px; color: var(--muted); line-height: 1.45; }
.nextup { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 18px 22px; margin: 0 0 36px; }
.nextup .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 12px; }
.nextup .meta a { color: inherit; }
.nextup .meta { font: 500 12.5px var(--sans); letter-spacing: 0; color: var(--muted);
  text-transform: none; }
.nextup blockquote.claimtext { font-size: 17px; margin: 12px 0 8px; }
.nextup p { color: var(--muted); margin: 4px 0 14px; }
a.button { display: inline-flex; align-items: center; min-height: 32px; padding: 0 14px;
  border-radius: 6px; text-decoration: none; font-weight: 500; font-size: 13.5px; }
a.button.primary { background: var(--accent); color: #fff; }
a.button.primary:hover { background: #142842; }
section.group { margin: 36px 0; }
.ghead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 12px;
  margin-bottom: 10px; }
.ghead h2 { font: 600 16px/1.4 var(--sans); margin: 0; border: 0; padding: 0; }
.ghead .muted { font-size: 13px; }
.kinds { display: flex; flex-wrap: wrap; gap: 4px; margin: 0 0 10px; }
/* claim page: what has to be true, the evidence as a conversation, the working folded */
.truths .checklist { list-style: none; padding: 0; margin: 8px 0 20px; background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); }
.checklist li { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 12px;
  align-items: start; padding: 10px 16px; border-top: 1px solid var(--line); }
.checklist li:first-child { border-top: 0; }
.checklist .mark { width: 12px; height: 12px; margin-top: 4px; border-radius: 50%;
  border: 1.5px solid var(--line-strong); }
.checklist li.ok .mark { background: var(--sup); border-color: var(--sup); }
.checklist li.no .mark { border-color: var(--muted); border-style: dashed; }
.checklist .meta { font-size: 12px; color: var(--muted); margin-top: 2px; }
.checklist .said { font: 500 12px var(--sans); color: var(--muted); white-space: nowrap; }
.checklist li.ok .said { color: var(--sup); }
.checklist li.con .mark { background: var(--con); border-color: var(--con); }
.checklist li.con .said { color: var(--con); }
.thread.mini { padding: 10px; margin: 6px 0; gap: 6px; background: var(--side); }
.item .quoted { font-size: 13px; margin: 4px 0; }
details.more summary, details.working summary { font-size: 13px; color: var(--muted); }
details.working { margin: 20px 0; }
.ledger .gap, .nextup .gap, #verdict .gap { margin-top: 4px; font-size: 12.5px;
  color: var(--muted); }
.ledger .gap b, .nextup .gap b, #verdict .gap b {
  color: var(--fg); font-weight: 600; margin-right: 6px; }

.split { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 32px;
  align-items: start; }
aside.side { position: sticky; top: 24px; max-height: calc(100vh - 48px); overflow-y: auto;
  scrollbar-width: thin; }
aside.side .eyebrow { display: flex; justify-content: space-between; margin: 2px 2px 0;
  font-weight: 600; color: var(--fg); }
aside.side .eyebrow span { font-weight: 400; color: var(--muted); }
aside.side .ledger .row { padding: 10px 14px; }
aside.side .ledger .text { font-size: 13px; display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden; }
aside.side .ledger li.on { box-shadow: inset 2px 0 0 var(--accent); background: var(--accent-bg); }

/* one claim */
.claim-head { display: flex; justify-content: space-between; align-items: center; gap: 12px;
  flex-wrap: wrap; }
.claim-head h1 { font: 500 12.5px var(--sans); letter-spacing: 0; color: var(--muted);
  margin: 0; }
.claim-head h1 .muted { color: var(--muted); }
blockquote.claimtext { font: 500 20px/1.45 var(--sans); letter-spacing: -0.005em;
  background: none; border-left: 2px solid var(--accent); border-radius: 0;
  padding: 0 0 0 18px; margin: 14px 0 10px; text-wrap: pretty; max-width: 72ch; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  margin: 20px 0; overflow: hidden; }
.card > .in { padding: 16px 20px; }
.card > .in + .in { border-top: 1px solid var(--line); background: var(--side); }
.card .verdict { font-size: 13px; padding: 2px 8px; margin: 6px 0; }
.card ul { padding-left: 20px; margin: 8px 0; }
.card details form.box { background: #fff; }

/* context around a record, as a conversation */
.thread { background: var(--side); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 16px; display: flex; flex-direction: column; gap: 8px; }
.msg { max-width: 72%; border: 1px solid var(--line); border-radius: 10px; padding: 8px 12px;
  background: #fff; align-self: flex-start; }
.msg.out { align-self: flex-end; background: var(--accent-bg); border-color: #d9e1ec; }
.msg .who2 { font-size: 11.5px; color: var(--muted); }
.msg .body { font-size: 14px; }
.msg .t { font: 400 11px var(--sans); color: var(--muted); text-align: right; margin-top: 2px;
  font-variant-numeric: tabular-nums; }
.msg.target { border: 1.5px solid var(--accent); box-shadow: 0 0 0 3px var(--ring); }
.msg .cited { display: inline-block; font: 600 11px var(--sans); letter-spacing: 0;
  color: var(--accent); background: var(--accent-bg); border-radius: 4px; padding: 1px 6px;
  margin-right: 6px; }

/* identities: a person, and each link with its records for and against */
.lede { font-size: 14px; line-height: 1.6; }
section.person { margin: 36px 0; padding-top: 24px; border-top: 1px solid var(--line); }
h2.pname { font: 600 18px/1.35 var(--sans); letter-spacing: -0.005em; margin: 2px 0 8px; }
.idhead { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
  gap: 6px; }
.idpair { font-size: 15px; font-weight: 600; margin: 10px 0 4px; }
.idpair .arrow { color: var(--muted); font-weight: 400; margin: 0 6px; }
.stpill { display: inline-flex; align-items: center; height: 20px; padding: 0 7px;
  border: 0; border-radius: 4px; font: 500 12px var(--sans);
  color: #3c4555; background: var(--panel); margin: 0 6px 4px 0; white-space: nowrap; }
.stpill b { margin-left: 4px; font-variant-numeric: tabular-nums; }
.st-confirmed.stpill { color: var(--sup); background: var(--sup-bg); }
.st-rejected.stpill { color: var(--con); background: var(--con-bg); }
.st-unresolved.stpill { color: var(--muted); background: var(--panel); }
article.idlink.st-rejected { opacity: 0.8; }
.idgrid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1px;
  background: var(--line); border-top: 1px solid var(--line); }
.idgrid > div { background: var(--card); padding: 14px 20px; }
.idgrid .side { display: flex; align-items: center; gap: 8px; font-size: 12.5px;
  font-weight: 600; margin: 0 0 8px; }
.idgrid .side::before { content: ""; width: 6px; height: 6px; border-radius: 50%; }
.idgrid .side.for::before { background: var(--sup); }
.idgrid .side.against::before { background: var(--con); }
ul.sig { list-style: none; padding: 0; margin: 0; }
ul.sig li { font-size: 13px; line-height: 1.5; margin: 0 0 10px; }
ul.sig .quote { font-size: 13.5px; color: var(--fg); }
ul.sig .ref { font-size: 12px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
button[aria-pressed=true] { box-shadow: inset 0 0 0 2px var(--fg); }
ul.unplaced .head .text { font-weight: 600; }

/* report modules shown inside the app (timeline, gaps, selection): the same quiet cards */
main .gap { border-color: var(--line); border-radius: var(--radius); padding: 14px 18px; }
main .gap .stmt { font: 600 14.5px/1.45 var(--sans); margin: 4px 0 10px; }
main .gap dl { grid-template-columns: 120px minmax(0, 1fr); gap: 6px 16px; font-size: 13px; }
main .gap dd ul { margin: 2px 0 0; padding-left: 18px; }
main .tl > li, main .strips { border-radius: var(--radius); }
main .tl > li.flag { border-color: var(--line); box-shadow: inset 2px 0 0 var(--con); }
main .chip { border: 0; border-radius: 4px; padding: 1px 7px; }
main .bars span { background: #7d8aa0; }
main .bars span.g { background: var(--panel); border: 1px dashed var(--line-strong); }

@media (max-width: 960px) {
  body { padding-left: 0; }
  header.top { position: static; width: auto; border-right: 0; border-bottom: 1px solid var(--line);
    overflow: visible; }
  .brand { padding: 14px 16px 0; }
  .casename { margin: 10px 16px 0; }
  nav.tabs { flex-direction: row; overflow-x: auto; padding: 8px 10px; scrollbar-width: none; }
  nav.tabs .sep { width: 1px; height: 16px; margin: 0 8px; align-self: center; }
  .bar .right { order: 1; margin: 0; flex-direction: row; flex-wrap: wrap; padding: 8px 16px 0;
    border-top: 0; gap: 4px 14px; }
  main { padding: 28px 24px 72px; }
  .split { grid-template-columns: minmax(0, 1fr); }
  aside.side { position: static; max-height: none; order: 2; }
  blockquote.claimtext { font-size: 18px; }
  .msg { max-width: 88%; }
  .idgrid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 600px) {
  main { padding: 24px 16px 64px; }
  h1, .overview-head h1 { font-size: 22px; }
  th, td { padding: 10px; }
  table { display: block; overflow-x: auto; }
  input[type=text], input[type=password] { min-width: 0; width: 100%; }
  main .gap dl { grid-template-columns: minmax(0, 1fr); }
}
"""
