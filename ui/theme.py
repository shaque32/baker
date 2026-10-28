"""The review screen's look: app chrome, ledger, cards and chat-style context on top of the
report's base styles (core/report/html.py CSS).

Same design language as getmabillon.com: IBM Plex Sans for text, Instrument Serif only for the
wordmark and headlines, IBM Plex Mono only for ids and hashes. Fully offline. The fonts (SIL
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
/* Design tokens. The palette is the report's (warm paper, ink, navy, verdict colors), as on
   getmabillon.com. One text face, IBM Plex Sans; Instrument Serif only for the wordmark and
   headlines. IBM Plex Mono only for ids and hashes (.mono), so they compare by eye; labels
   are never monospace or uppercase. */
:root { --mono: "IBM Plex Mono", ui-monospace, Menlo, Consolas, monospace; --hover: #faf8f4;
  --ring: rgb(29 53 87 / 0.16);
  --field: #fff; --amber: #c9a24a; --radius: 12px; }
body { max-width: none; padding: 0; font-size: 15px; line-height: 1.6; }
main { max-width: 1160px; margin: 0 auto; padding: 48px 32px 96px; }
main.wide { max-width: 1360px; }
p { margin: 0 0 14px; }

/* Type: serif only for page titles and big numbers; section heads are plain sans */
h1 { font: 400 44px/1.08 var(--serif); letter-spacing: -0.015em; margin: 0 0 14px;
  text-wrap: balance; }
h2 { font: 600 18px/1.35 var(--sans); letter-spacing: -0.005em; margin: 56px 0 14px;
  padding: 0; border: 0; }
h3 { font: 600 15px/1.4 var(--sans); margin: 28px 0 10px; }
.eyebrow { font: 500 13px/1.4 var(--sans); letter-spacing: 0; text-transform: none;
  color: var(--muted); margin-bottom: 6px; }
.mono { font: 400 12px/1.5 var(--mono);
  color: var(--muted); letter-spacing: 0; word-break: break-all; }
.muted { color: var(--muted); }
a { color: var(--accent); text-decoration-color: rgb(29 53 87 / 0.35);
  text-underline-offset: 3px; }
a:hover { text-decoration-color: currentColor; }

/* Header: one quiet bar with the wordmark, the case and who is reviewing; tabs underneath */
header.top { position: sticky; top: 0; z-index: 5; background: rgb(247 245 240 / 0.92);
  border-bottom: 1px solid var(--line); backdrop-filter: saturate(1.4) blur(10px); }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 20px;
  padding: 14px 32px 6px; }
.brand { display: inline-flex; align-items: center; gap: 9px; text-decoration: none;
  color: var(--fg); }
.brand span { font: 400 24px/1 var(--serif); letter-spacing: -0.01em; }
.casename { display: flex; flex-direction: column; min-width: 0; font-weight: 600;
  font-size: 14px; line-height: 1.3; padding-left: 20px; border-left: 1px solid var(--line); }
.casename small { font: 400 12px var(--sans); color: var(--muted); letter-spacing: 0; }
.pill { display: inline-flex; align-items: center; gap: 7px; border: 0; border-radius: 999px;
  padding: 4px 12px 4px 10px; font: 500 12.5px var(--sans); color: var(--muted);
  background: var(--panel); white-space: nowrap; text-decoration: none; }
.pill::before { content: ""; width: 7px; height: 7px; border-radius: 50%;
  background: var(--sup); }
a.pill::before { background: var(--accent); }
a.pill:hover { color: var(--fg); }
.bar .right { margin-left: auto; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.who { font-size: 13px; color: var(--muted); } .who strong { color: var(--fg); font-weight: 600; }
nav.tabs { display: flex; align-items: center; gap: 2px; padding: 4px 26px 10px; overflow-x: auto;
  font-size: 14px; scrollbar-width: none; }
nav.tabs a { color: var(--muted); text-decoration: none; padding: 6px 10px; border-radius: 8px;
  white-space: nowrap; transition: background-color 0.12s ease, color 0.12s ease; }
nav.tabs a:hover { color: var(--fg); background: rgb(20 20 20 / 0.04); }
nav.tabs a.on { color: var(--fg); font-weight: 500; background: var(--card);
  box-shadow: 0 0 0 1px var(--line), 0 1px 2px rgb(20 20 20 / 0.05); }
nav.tabs .sep { flex: none; width: 1px; height: 16px; margin: 0 10px;
  background: var(--line-strong); }
.casestatus { display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px;
  background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 16px 20px; margin: 0 0 14px; }
.casestatus .findings { display: flex; flex-wrap: wrap; gap: 8px 16px; list-style: none;
  padding: 0; margin: 0; }
.casestatus .verdict { margin: 0 2px 0 0; }
details.custody { margin: 18px 0; }
details.custody > summary { font-size: 14px; color: var(--muted); }

/* Notices. The demo and "not tested" notices stay visible but no longer shout. */
.banner, p.warn { background: #fbf6ea; border: 1px solid #ecdfbf; border-radius: var(--radius);
  padding: 14px 18px; margin: 0 0 18px; color: #4a3a14; font-size: 14px; line-height: 1.55; }
.banner strong, p.warn strong { font-size: inherit; font-weight: 600; color: #3a2c0a; }
.banner .banner { background: var(--card); border-color: var(--line); margin: 10px 0 0;
  box-shadow: inset 3px 0 0 var(--amber); }
.caution { border: 1px solid #ecdfbf; border-left: 3px solid var(--amber); background: #fbf6ea;
  padding: 10px 14px; border-radius: 0 10px 10px 0; font-size: 14px; }
.flash { padding: 12px 16px; margin: 0 0 18px; border: 1px solid var(--line);
  border-radius: var(--radius); background: var(--card); font-size: 14px; }
.flash.err { border-color: var(--con-line); background: var(--con-bg); color: var(--con); }
.flash.toast { position: fixed; right: 24px; bottom: 24px; z-index: 10; margin: 0;
  max-width: min(440px, calc(100vw - 48px)); background: var(--fg); color: var(--bg);
  border-color: var(--fg); box-shadow: 0 12px 32px -12px rgb(20 20 20 / 0.45);
  animation: toast-out 0.4s ease 7s forwards; }
.flash.toast.err { animation: none; background: var(--con-bg); color: var(--con);
  border-color: var(--con-line); }
@keyframes toast-out { to { opacity: 0; visibility: hidden; } }
@media (prefers-reduced-motion: reduce) { .flash.toast { animation: none; } }

/* A source's format notice: one line with an amber dot, not a yellow box */
p.format-notice { position: relative; background: none; border: 0; border-radius: 0;
  padding: 0 0 0 18px; margin: 8px 0; font-size: 13.5px; line-height: 1.5; color: var(--fg); }
p.format-notice::before { content: ""; position: absolute; left: 2px; top: 0.55em; width: 7px;
  height: 7px; border-radius: 50%; background: var(--sup); }
p.format-notice.warn::before { background: var(--amber); }
p.format-notice strong { font-weight: 500; color: var(--fg); }
#formats.banner { background: var(--card); border-color: var(--line); padding: 10px 18px; }
td p.format-notice { font-size: 13px; margin: 8px 0 0; }

/* coming back to the item a form acted on: clear the sticky header, mark it briefly */
[id] { scroll-margin-top: 128px; }
.item:target, .card:target, tr:target td { outline: 2px solid var(--amber); outline-offset: 2px; }
tr:target td { outline: 0; background: #fbf1cf; }

/* Tables: no header band and no capitals; roomy rows that read as a list */
table { border-collapse: separate; border-spacing: 0; width: 100%; margin: 12px 0 18px;
  font-size: 14px; line-height: 1.5; background: var(--card); border: 1px solid var(--line);
  border-radius: var(--radius); overflow: hidden; }
th, td { padding: 14px 18px; border-bottom: 1px solid var(--line); text-align: left;
  vertical-align: top; }
th { background: transparent; font: 500 12.5px/1.4 var(--sans); letter-spacing: 0;
  text-transform: none; color: var(--muted); padding-top: 12px; padding-bottom: 12px;
  white-space: nowrap; }
tbody tr:hover td, table > tr:hover td { background: var(--hover); }
tr:last-child td { border-bottom: 0; }
td .mono { display: inline-block; margin-top: 2px; }
td form.inline button { margin: 0; }
td input[type=text], td input[type=password] { min-width: 0; width: 100%; max-width: 260px;
  height: 36px; font-size: 14px; }
td button { min-height: 34px; padding: 0 12px; font-size: 13.5px; margin: 4px 6px 4px 0; }
.ctx td { font-size: 13px; }
tr.target td { font-weight: 600; background: #fbf1cf; }

/* Forms: labels above fields, 40px controls, one clear focus ring */
form.inline { display: inline; }
form.box { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 22px 24px; margin: 14px 0 18px; font-size: 14px; }
form.box > :last-child { margin-bottom: 0; }
form.box p { margin: 0 0 16px; }
form.box p.muted { font-size: 13px; }
label { font-size: 14px; }
label:has(> input[type=text], > input[type=password], > input[type=number], > select,
  > textarea) { display: inline-grid; gap: 6px; font-weight: 500; font-size: 13.5px;
  color: var(--fg); vertical-align: top; margin: 0 12px 4px 0; }
label:has(> textarea[name]), label:has(> input[type=text].wide) { display: grid;
  margin-right: 0; }
label:has(> input[type=checkbox], > input[type=radio]) { display: inline-flex;
  align-items: center; gap: 8px; margin: 0 16px 6px 0; cursor: pointer; }
input[type=text], input[type=password], input[type=number], input[type=search], select {
  height: 40px; }
input[type=text], input[type=password], input[type=number], input[type=search],
input[type=file], textarea, select {
  font: 400 14.5px/1.4 var(--sans); color: var(--fg); background: var(--field);
  border: 1px solid var(--line-strong); border-radius: 8px; padding: 0 12px;
  max-width: 100%; box-sizing: border-box; margin: 0 6px 6px 0;
  box-shadow: 0 1px 2px rgb(20 20 20 / 0.04);
  transition: border-color 0.12s ease, box-shadow 0.12s ease; }
input[type=text], input[type=password] { min-width: min(280px, 100%); }
textarea { padding: 10px 12px; line-height: 1.55; min-height: 104px; resize: vertical; }
input[type=file] { height: auto; padding: 8px; background: var(--bg); border-style: dashed;
  box-shadow: none; }
input[type=file]::file-selector-button { font: 500 13.5px var(--sans); color: var(--fg);
  background: var(--card); border: 1px solid var(--line-strong); border-radius: 6px;
  padding: 6px 12px; margin-right: 12px; cursor: pointer; }
select { appearance: none; -webkit-appearance: none; padding-right: 34px; cursor: pointer;
  background-image: linear-gradient(45deg, transparent 50%, var(--muted) 50%),
    linear-gradient(135deg, var(--muted) 50%, transparent 50%);
  background-position: calc(100% - 18px) 52%, calc(100% - 13px) 52%;
  background-size: 5px 5px; background-repeat: no-repeat; }
input::placeholder, textarea::placeholder { color: #9a948a; }
input[type=text]:hover, input[type=password]:hover, input[type=number]:hover, textarea:hover,
select:hover { border-color: #b9b2a4; }
input[type=text]:focus, input[type=password]:focus, input[type=number]:focus,
input[type=search]:focus, textarea:focus, select:focus {
  outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--ring); }
input[type=checkbox], input[type=radio] { width: 16px; height: 16px; margin: 0;
  accent-color: var(--accent); cursor: pointer; }
input[type=text].wide, textarea { width: 100%; margin-right: 0; }
input:disabled, select:disabled, textarea:disabled { opacity: 0.55; cursor: not-allowed; }

/* Buttons: quiet by default, navy for the one main action */
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  min-height: 38px; font: 500 14px/1 var(--sans); color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); border-radius: 8px; padding: 0 16px;
  margin: 6px 8px 0 0; cursor: pointer; box-shadow: 0 1px 2px rgb(20 20 20 / 0.05);
  transition: background-color 0.12s ease, border-color 0.12s ease; vertical-align: middle; }
button:hover { background: var(--hover); border-color: #b9b2a4; }
button:active { transform: translateY(0.5px); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button.primary, button[value=accepted] { background: var(--accent); border-color: var(--accent);
  color: #f7f5f0; box-shadow: 0 1px 2px rgb(20 20 20 / 0.12); }
button.primary:hover, button[value=accepted]:hover { background: #142842; border-color: #142842; }
button[value=dismissed], button[value=removed] { color: var(--con); }
button[value=dismissed]:hover, button[value=removed]:hover { background: var(--con-bg);
  border-color: var(--con-line); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--ring); }
details summary { color: var(--accent); font-weight: 500; }
details summary::marker { color: var(--muted); }

/* evidence cards and tier badges */
.item { background: var(--card); border: 1px solid var(--line); border-radius: var(--radius);
  padding: 16px 20px; margin: 12px 0; }
.item blockquote { background: none; border-left: 2px solid var(--line-strong);
  border-radius: 0; font-size: 15px; }
.badge { display: inline-flex; align-items: center; height: 22px; padding: 0 9px;
  margin: 0 6px 4px 0; border: 1px solid var(--line); border-radius: 999px;
  font: 500 12px var(--sans); letter-spacing: 0; text-transform: none;
  color: var(--fg); background: var(--panel); }
.b-ai { color: var(--unp); border: 1px dashed var(--unp-line); background: transparent; }
.b-conf { color: var(--accent); border-color: rgb(29 53 87 / 0.2);
  background: rgb(29 53 87 / 0.07); }
.b-open { color: var(--fg); }
.b-against { color: var(--con); border-color: var(--con-line); background: var(--con-bg); }
.b-flag { color: var(--muted); border-style: dashed; background: transparent; }
.b-withheld { color: var(--unp); border-color: var(--unp-line); background: var(--unp-bg); }
.b-challenge { color: var(--muted); border-style: dotted; background: transparent; }
.b-agent { color: var(--muted); border-style: dashed; background: transparent; }
section.agent { background: var(--card); border: 1px dashed var(--line-strong); border-radius: 12px;
  padding: 12px 16px; margin: 12px 0; }
details.flag { margin-top: 6px; }
details.flag > summary { font-size: 13px; color: var(--muted); cursor: pointer; }
ul.flags form.inline button { margin-left: 8px; }

/* verdicts: soft pills; a dashed edge still means "not settled by the expert" */
.verdict { font-weight: 500; border-color: transparent; }
.v-await, .v-confirm, .v-supai, .verdict.v-nt { border-width: 1px; }
.v-await { border-color: var(--await); } .v-confirm { border-color: var(--con); }
.v-supai { border-color: var(--sup-line); } .verdict.v-nt { border-color: var(--muted); }

/* claims ledger: the queue, and the column beside a claim */
.tally { display: flex; height: 6px; border-radius: 999px; overflow: hidden;
  background: var(--panel); margin: 14px 0 12px; }
.tally span { display: block; border: 0; border-radius: 0; padding: 0; }
.tally span::before { content: none; }
.tally .v-sup { background: var(--sup); } .tally .v-con { background: var(--con); }
.tally .v-confirm { background: #c98a7e; }
.tally .v-unp, .tally .v-await { background: var(--amber); } .tally .other { background: #aaa49a; }
.counts { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.counts .verdict { font-size: 12.5px; }
.counts .verdict b { font-weight: 600; margin-left: 2px; }
.ledger { list-style: none; margin: 0; padding: 0; background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }
.ledger li { border-bottom: 1px solid var(--line); position: relative;
  transition: background-color 0.12s ease; }
.ledger li:last-child { border-bottom: 0; }
.ledger .row { padding: 16px 20px; }
.ledger li:hover { background: var(--hover); }
.ledger .meta a { color: var(--fg); font-weight: 600; text-decoration: none; }
.ledger .meta a::after { content: ""; position: absolute; inset: 0; }
.ledger .head { display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 4px 10px; margin-bottom: 6px; }
.ledger .head .meta { flex: 1 1 150px; min-width: 0; }
.ledger .meta { font: 400 12.5px var(--sans); color: var(--muted); letter-spacing: 0;
  padding-top: 2px; font-variant-numeric: tabular-nums; }
.ledger .text { font-size: 15px; line-height: 1.5; }
.ledger .needs { margin-top: 6px; font-size: 13px; color: var(--muted); }
.ledger .verdict { font-size: 12px; padding: 2px 9px 2px 7px; }
.ledger .verdict::before { width: 12px; height: 12px; font-size: 8px; }

/* claims overview: progress, one tile per group, the next claim up, then the groups */
.overview-head { display: flex; flex-wrap: wrap; align-items: flex-end;
  justify-content: space-between; gap: 18px 40px; }
.overview-head > div:first-child { flex: 1 1 460px; }
.overview-head h1 { font: 400 48px/1.06 var(--serif); letter-spacing: -0.015em;
  margin: 2px 0 12px; }
.progress { flex: 0 1 300px; margin-bottom: 16px; }
.progress .lbl { display: flex; justify-content: space-between; gap: 10px; font-size: 13px;
  color: var(--muted); margin-bottom: 8px; }
.progress .lbl b { color: var(--fg); font-weight: 600; font-variant-numeric: tabular-nums; }
.progress .track { height: 6px; border-radius: 999px; background: var(--panel); overflow: hidden; }
.progress .track span { display: block; height: 100%; background: var(--accent);
  border-radius: 999px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px;
  margin: 28px 0 32px; }
.tile { display: flex; flex-direction: column; gap: 4px; padding: 18px 20px;
  border-radius: var(--radius);
  background: var(--card); border: 1px solid var(--line); color: var(--fg); text-decoration: none;
  transition: border-color 0.12s ease, background-color 0.12s ease; }
.tile:hover { border-color: var(--line-strong); background: #fff; }
.tile.empty, .tile.t-you.empty { background: var(--card); border-color: var(--line);
  color: var(--muted); }
.tile.t-you.empty .sub { color: var(--muted); }
.tile .name { font-size: 13.5px; font-weight: 600; }
.tile .n { font: 600 36px/1.15 var(--sans); letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums; }
.tile .sub { font-size: 13px; color: var(--muted); line-height: 1.45; }
.tile.t-you { background: var(--accent); border-color: var(--accent); color: #f7f5f0; }
.tile.t-you:hover { background: #142842; }
.tile.t-you .sub { color: rgb(247 245 240 / 0.8); }
.tile.t-con .name { color: var(--con); } .tile.t-unp .name { color: var(--unp); }
.tile.t-sup .name { color: var(--sup); }
.nextup { background: var(--card); border: 1px solid var(--line-strong); border-radius: 16px;
  padding: 24px 28px; margin: 0 0 40px; box-shadow: 0 8px 24px -18px rgb(20 20 20 / 0.25); }
.nextup .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 12px; }
.nextup .meta a { color: inherit; }
.nextup .meta { font: 500 13px var(--sans); letter-spacing: 0; color: var(--muted);
  text-transform: none; }
.nextup blockquote.claimtext { font-size: 22px; margin: 16px 0 10px; }
.nextup p { color: var(--muted); margin: 6px 0 18px; }
a.button { display: inline-flex; align-items: center; min-height: 40px; padding: 0 18px;
  border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14.5px; }
a.button.primary { background: var(--accent); color: #f7f5f0; }
a.button.primary:hover { background: #142842; }
section.group { margin: 40px 0; }
.ghead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px;
  margin-bottom: 12px; }
.ghead h2 { font: 400 30px/1.15 var(--serif); letter-spacing: -0.01em; margin: 0; border: 0;
  padding: 0; }
.ghead .muted { font-size: 13.5px; }
.kinds { display: flex; flex-wrap: wrap; gap: 4px; margin: 0 0 12px; }
/* claim page: what has to be true, the evidence as a conversation, the working folded */
.truths .checklist { list-style: none; padding: 0; margin: 10px 0 20px; background: var(--card);
  border: 1px solid var(--line); border-radius: var(--radius); }
.checklist li { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; gap: 12px;
  align-items: start; padding: 12px 18px; border-top: 1px solid var(--line); }
.checklist li:first-child { border-top: 0; }
.checklist .mark { width: 14px; height: 14px; margin-top: 4px; border-radius: 50%;
  border: 1.5px solid var(--line-strong); }
.checklist li.ok .mark { background: var(--sup); border-color: var(--sup); }
.checklist li.no .mark { border-color: var(--unp); border-style: dashed; }
.checklist .meta { font-size: 12.5px; color: var(--muted); margin-top: 2px; }
.checklist .said { font: 500 12.5px var(--sans); color: var(--muted); white-space: nowrap; }
.checklist li.ok .said { color: var(--sup); } .checklist li.no .said { color: var(--unp); }
.thread.mini { padding: 10px; margin: 6px 0; gap: 6px; background: var(--bg); }
.item .quoted { font-size: 13px; margin: 4px 0; }
details.more summary, details.working summary { font-size: 13.5px; color: var(--muted); }
details.working { margin: 22px 0; }
.ledger .gap, .nextup .gap, #verdict .gap { margin-top: 6px; font-size: 13px; color: var(--muted); }
.ledger .gap b, .nextup .gap b, #verdict .gap b {
  color: var(--unp); font-weight: 600; margin-right: 6px; }

.split { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 40px;
  align-items: start; }
aside.side { position: sticky; top: 120px; max-height: calc(100vh - 136px); overflow-y: auto;
  scrollbar-width: thin; }
aside.side .eyebrow { display: flex; justify-content: space-between; margin: 4px 2px 0;
  font-weight: 600; color: var(--fg); }
aside.side .eyebrow span { font-weight: 400; color: var(--muted); }
aside.side .ledger .row { padding: 12px 16px; }
aside.side .ledger .text { font-size: 13.5px; display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden; }
aside.side .ledger li.on { box-shadow: inset 3px 0 0 var(--accent); background: var(--hover); }

/* one claim */
.claim-head { display: flex; justify-content: space-between; align-items: center; gap: 12px;
  flex-wrap: wrap; }
.claim-head h1 { font: 500 13px var(--sans); letter-spacing: 0; color: var(--muted);
  margin: 0; }
.claim-head h1 .muted { color: var(--muted); }
blockquote.claimtext { font: 500 24px/1.4 var(--sans); letter-spacing: -0.01em;
  background: none; border-left: 2px solid var(--accent); border-radius: 0;
  padding: 2px 0 2px 22px; margin: 18px 0 10px; text-wrap: pretty; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  margin: 24px 0; overflow: hidden; }
.card > .in { padding: 20px 24px; }
.card > .in + .in { border-top: 1px solid var(--line); background: var(--hover); }
.card .verdict { font-size: 14.5px; padding: 5px 14px 5px 10px; margin: 8px 0 8px; }
.card ul { padding-left: 20px; margin: 8px 0; }
.card details form.box { background: #fff; }

/* context around a record, as a conversation */
.thread { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
  padding: 18px; display: flex; flex-direction: column; gap: 10px; }
.msg { max-width: 72%; border: 1px solid var(--line); border-radius: 14px; padding: 9px 13px;
  background: #fff; align-self: flex-start; }
.msg.out { align-self: flex-end; background: #e9eef5; border-color: #d3dceb; }
.msg .who2 { font-size: 12px; color: var(--muted); }
.msg .body { font-size: 14.5px; }
.msg .t { font: 400 11.5px var(--sans); color: var(--muted); text-align: right; margin-top: 2px;
  font-variant-numeric: tabular-nums; }
.msg.target { border: 1.5px solid var(--amber); background: #fbf1cf;
  box-shadow: 0 0 0 3px rgb(201 162 74 / 0.18); }
.msg .cited { font: 600 11px var(--sans); letter-spacing: 0.02em; color: #6b4d0c;
  background: #f0dca3; border-radius: 999px; padding: 1px 8px; margin-right: 6px; }

/* identities: a person, and each link with its records for and against */
.lede { font-size: 16px; color: var(--muted); max-width: 68ch; line-height: 1.6; }
section.person { margin: 40px 0; }
h2.pname { font: 400 30px/1.15 var(--serif); letter-spacing: -0.01em; margin: 4px 0 8px; }
.idhead { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
  gap: 6px; }
.idpair { font-size: 17px; font-weight: 600; margin: 10px 0 4px; }
.idpair .arrow { color: var(--muted); font-weight: 400; margin: 0 6px; }
.stpill { display: inline-flex; align-items: center; height: 24px; padding: 0 10px;
  border: 1px solid var(--line); border-radius: 999px; font: 500 12px var(--sans);
  color: var(--fg); background: var(--card); margin: 0 6px 4px 0; white-space: nowrap; }
.stpill b { margin-left: 4px; font-variant-numeric: tabular-nums; }
.st-confirmed.stpill { color: var(--sup); background: var(--sup-bg);
  border-color: var(--sup-line); }
.st-rejected.stpill { color: var(--con); background: var(--con-bg); border-color: var(--con-line); }
.st-unresolved.stpill { color: var(--unp); background: var(--unp-bg);
  border-color: var(--unp-line); }
article.idlink.st-rejected { opacity: 0.8; }
.idgrid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1px;
  background: var(--line); border-top: 1px solid var(--line); }
.idgrid > div { background: var(--card); padding: 16px 22px; }
.idgrid .side { display: flex; align-items: center; gap: 8px; font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px; }
.idgrid .side::before { content: ""; width: 3px; height: 13px; border-radius: 2px; }
.idgrid .side.for::before { background: var(--sup); }
.idgrid .side.against::before { background: var(--con); }
ul.sig { list-style: none; padding: 0; margin: 0; }
ul.sig li { font-size: 13.5px; line-height: 1.5; margin: 0 0 12px; }
ul.sig .quote { font-size: 14px; color: var(--fg); }
ul.sig .ref { font-size: 12px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
button[aria-pressed=true] { box-shadow: inset 0 0 0 2px var(--fg); }
ul.unplaced .head .text { font-weight: 600; }

@media (max-width: 900px) {
  .split { grid-template-columns: minmax(0, 1fr); }
  aside.side { position: static; max-height: none; order: 2; }
  blockquote.claimtext { font-size: 20px; }
  .msg { max-width: 88%; }
  .idgrid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 600px) {
  header.top { position: static; }
  [id] { scroll-margin-top: 12px; }
  main { padding: 28px 16px 64px; }
  .bar { padding: 12px 16px 4px; } nav.tabs { padding: 4px 10px 10px; }
  .casename { padding-left: 0; border-left: 0; flex-basis: 100%; order: 3; }
  h1, .overview-head h1 { font-size: 34px; }
  th, td { padding: 12px 14px; }
  table { display: block; overflow-x: auto; }
  input[type=text], input[type=password] { min-width: 0; width: 100%; }
}
"""
