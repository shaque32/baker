"""The review screen's look: app chrome, ledger, cards and chat-style context on top of the
report's base styles (core/report/html.py CSS).

Fully offline. The three fonts (Inter, Instrument Serif, JetBrains Mono, SIL Open Font License)
are vendored in ui/static/fonts and served by this screen at /static/fonts/; the font stacks fall
back to system fonts. The Baker mark is inline SVG, so no image request is ever made.
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
    _face("Inter", "inter-latin-wght-normal.woff2", "100 900", _LATIN)
    + _face("Inter", "inter-cyrillic-wght-normal.woff2", "100 900", _CYRILLIC)
    + _face("Instrument Serif", "instrument-serif-latin-400-normal.woff2", "400", _LATIN)
    + _face("Instrument Serif", "instrument-serif-latin-400-italic.woff2", "400", _LATIN, "italic")
    + _face("JetBrains Mono", "jetbrains-mono-latin-wght-normal.woff2", "100 800", _LATIN)
    + _face("JetBrains Mono", "jetbrains-mono-cyrillic-wght-normal.woff2", "100 800", _CYRILLIC)
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
body { max-width: none; padding: 0; }
main { max-width: 1040px; margin: 0 auto; padding: 28px 24px 80px; }
main.wide { max-width: 1320px; }

/* header: wordmark, case, offline pill, reviewer; tabs underneath */
header.top { position: sticky; top: 0; z-index: 5; background: rgb(247 245 240 / 0.94);
  border-bottom: 1px solid var(--line); backdrop-filter: blur(6px); }
.bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px;
  padding: 12px 24px 4px; }
.brand { display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
  color: var(--fg); }
.brand span { font: 400 23px/1 var(--serif); letter-spacing: -0.01em; }
.casename { display: flex; flex-direction: column; min-width: 0; font-weight: 600;
  font-size: 15px; }
.casename small { font: 400 11px var(--mono); color: var(--muted); letter-spacing: 0.02em; }
.pill { display: inline-flex; align-items: center; gap: 6px; border: 1px dashed var(--line-strong);
  border-radius: 999px; padding: 2px 10px; font: 400 10.5px var(--mono); color: var(--muted);
  background: rgb(253 252 250 / 0.7); white-space: nowrap; }
.pill::before { content: ""; width: 6px; height: 6px; border-radius: 50%;
  background: var(--line-strong); }
.bar .right { margin-left: auto; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.who { font-size: 13px; color: var(--muted); } .who strong { color: var(--fg); }
nav.tabs { display: flex; gap: 4px 22px; padding: 0 24px; overflow-x: auto; font-size: 14px; }
nav.tabs a { color: var(--muted); text-decoration: none; padding: 10px 0 9px;
  border-bottom: 2px solid transparent; white-space: nowrap; }
nav.tabs a:hover { color: var(--fg); }
nav.tabs a.on { color: var(--fg); font-weight: 500; border-bottom-color: var(--fg); }

h1 { font-size: 40px; }
.eyebrow { font: 500 11px var(--mono); letter-spacing: 0.14em; text-transform: uppercase;
  color: var(--muted); }

/* messages */
.flash { padding: 10px 14px; margin: 12px 0; border: 1px solid var(--line); border-radius: 10px;
  background: var(--card); }
.flash.err { border-color: var(--con-line); background: var(--con-bg); color: var(--con); }
.flash.toast { position: fixed; right: 20px; bottom: 20px; z-index: 10; margin: 0;
  max-width: min(440px, calc(100vw - 40px)); box-shadow: 0 10px 30px -10px rgb(20 20 20 / 0.3);
  animation: toast-out 0.4s ease 7s forwards; }
.flash.toast.err { animation: none; }
@keyframes toast-out { to { opacity: 0; visibility: hidden; } }
@media (prefers-reduced-motion: reduce) { .flash.toast { animation: none; } }

/* coming back to the item a form acted on: clear the sticky header, mark it briefly */
[id] { scroll-margin-top: 128px; }
.item:target, .card:target, tr:target td { outline: 2px solid #c9a24a; outline-offset: 2px; }
tr:target td { outline: 0; background: #fbf1cf; }

/* forms and buttons */
form.inline { display: inline; }
form.box { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 12px 14px; margin: 12px 0; font-size: 13px; }
input[type=text], input[type=password], input[type=file], textarea, select {
  font: 14px var(--sans); color: var(--fg);
  background: #fff; border: 1px solid var(--line-strong); border-radius: 8px; padding: 6px 9px;
  max-width: 100%; box-sizing: border-box; }
input[type=text]:focus, input[type=password]:focus, textarea:focus, select:focus {
  outline: 2px solid var(--accent); outline-offset: 1px; }
input[type=text].wide, textarea { width: 100%; }
button { font: 500 13px var(--sans); color: var(--fg); background: var(--card);
  border: 1px solid var(--line-strong); border-radius: 8px; padding: 6px 12px;
  margin: 6px 6px 0 0; cursor: pointer; }
button:hover { background: var(--panel); }
button:disabled { opacity: 0.5; cursor: not-allowed; }
button.primary, button[value=accepted] { background: var(--accent); border-color: var(--accent);
  color: #f7f5f0; }
button.primary:hover, button[value=accepted]:hover { background: #142842; }
button[value=dismissed], button[value=removed] { color: var(--con); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* evidence cards and tier badges */
.item { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
  padding: 12px 16px; margin: 12px 0;
  box-shadow: 0 1px 2px rgb(20 20 20 / 0.04), 0 6px 18px -12px rgb(20 20 20 / 0.12); }
.item blockquote { background: none; border-left: 2px solid var(--line-strong);
  border-radius: 0; font-size: 15px; }
.badge { display: inline-flex; align-items: center; height: 20px; padding: 0 7px;
  margin: 0 6px 4px 0; border: 1px solid var(--line-strong); border-radius: 6px;
  font: 500 10.5px var(--mono); letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--fg); background: var(--card); }
.b-ai { color: var(--unp); border: 1px dashed var(--unp-line); background: transparent; }
.b-conf { color: var(--accent); border-color: rgb(29 53 87 / 0.3);
  background: rgb(29 53 87 / 0.06); }
.b-open { color: var(--fg); }
.b-against { color: var(--con); border-color: var(--con-line); background: var(--con-bg); }
.b-flag { color: var(--muted); border-style: dashed; background: transparent; }
details.flag { margin-top: 6px; }
details.flag > summary { font-size: 13px; color: var(--muted); cursor: pointer; }
ul.flags form.inline button { margin-left: 8px; }

/* claims ledger: the queue, and the column beside a claim */
.tally { display: flex; height: 6px; border-radius: 999px; overflow: hidden;
  background: var(--panel); margin: 14px 0 10px; }
.tally span { display: block; border: 0; border-radius: 0; padding: 0; }
.tally span::before { content: none; }
.tally .v-sup { background: var(--sup); } .tally .v-con { background: var(--con); }
.tally .v-confirm { background: #c98a7e; }
.tally .v-unp, .tally .v-await { background: #c9a24a; } .tally .other { background: #aaa49a; }
.counts { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px; }
.counts .verdict { font-size: 12px; }
.counts .verdict b { font-weight: 600; margin-left: 2px; }
.ledger { list-style: none; margin: 0; padding: 0; background: var(--card);
  border: 1px solid var(--line); border-radius: 14px; overflow: hidden; }
.ledger li { border-bottom: 1px solid var(--line); }
.ledger li:last-child { border-bottom: 0; }
.ledger li { position: relative; }
.ledger .row { padding: 14px 18px; }
.ledger li:hover { background: #faf8f4; }
.ledger .meta a { color: var(--fg); font-weight: 600; text-decoration: none; }
.ledger .meta a::after { content: ""; position: absolute; inset: 0; }
.ledger .head { display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 4px 10px; margin-bottom: 6px; }
.ledger .head .meta { flex: 1 1 150px; min-width: 0; }
.ledger .meta { font: 400 11px var(--mono); color: var(--muted); letter-spacing: 0.02em;
  padding-top: 3px; }
.ledger .text { font-size: 14.5px; line-height: 1.45; }
.ledger .needs { margin-top: 6px; font-size: 12.5px; color: var(--muted); }
.ledger .verdict { font-size: 11.5px; padding: 1px 8px 1px 6px; }
.ledger .verdict::before { width: 12px; height: 12px; font-size: 8px; }

/* claims overview: progress, one tile per group, the next claim up, then the groups */
.overview-head { display: flex; flex-wrap: wrap; align-items: flex-end;
  justify-content: space-between; gap: 18px 32px; }
.overview-head > div:first-child { flex: 1 1 460px; }
.overview-head h1 { font: 400 46px/1.08 var(--serif); letter-spacing: -0.015em; margin: 4px 0 8px; }
.progress { flex: 0 1 300px; margin-bottom: 14px; }
.progress .lbl { display: flex; justify-content: space-between; gap: 10px; font-size: 13px;
  color: var(--muted); margin-bottom: 6px; }
.progress .lbl b { color: var(--fg); font-weight: 600; }
.progress .track { height: 8px; border-radius: 999px; background: var(--panel); overflow: hidden; }
.progress .track span { display: block; height: 100%; background: var(--accent); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px;
  margin: 22px 0 26px; }
.tile { display: flex; flex-direction: column; gap: 2px; padding: 16px 18px; border-radius: 16px;
  background: var(--card); border: 1px solid var(--line); color: var(--fg); text-decoration: none; }
.tile:hover { border-color: var(--line-strong); }
.tile.empty, .tile.t-you.empty { background: var(--card); border-color: var(--line);
  color: var(--muted); }
.tile.t-you.empty .sub { color: var(--muted); }
.tile .name { font-size: 13px; font-weight: 600; }
.tile .n { font: 400 42px/1.05 var(--serif); }
.tile .sub { font-size: 12.5px; color: var(--muted); }
.tile.t-you { background: var(--accent); border-color: var(--accent); color: #f7f5f0; }
.tile.t-you .sub { color: rgb(247 245 240 / 0.82); }
.tile.t-con .name { color: var(--con); } .tile.t-unp .name { color: var(--unp); }
.tile.t-sup .name { color: var(--sup); }
.nextup { background: var(--card); border: 1px solid var(--line-strong); border-radius: 20px;
  padding: 20px 24px; margin: 0 0 30px;
  box-shadow: 0 1px 2px rgb(20 20 20 / 0.04), 0 10px 26px -16px rgb(20 20 20 / 0.2); }
.nextup .head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px 12px; }
.nextup .meta a { color: inherit; }
.nextup .meta { font: 500 11.5px var(--mono); letter-spacing: 0.06em; color: var(--muted);
  text-transform: uppercase; }
.nextup blockquote.claimtext { font-size: 28px; margin: 14px 0 6px; }
.nextup p { color: var(--muted); margin: 6px 0 14px; }
a.button { display: inline-flex; align-items: center; min-height: 40px; padding: 0 18px;
  border-radius: 10px; text-decoration: none; font-weight: 600; }
a.button.primary { background: var(--accent); color: #f7f5f0; }
a.button.primary:hover { background: #142842; }
section.group { margin: 30px 0; }
.ghead { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 14px;
  margin-bottom: 10px; }
.ghead h2 { font: 400 30px/1.15 var(--serif); letter-spacing: -0.01em; margin: 0; border: 0;
  padding: 0; }
.ghead .muted { font-size: 13.5px; }
.kinds { display: flex; flex-wrap: wrap; gap: 4px; margin: 0 0 10px; }
.ledger .gap, .nextup .gap { margin-top: 6px; font-size: 13px; color: var(--muted); }
.ledger .gap b, .nextup .gap b { color: var(--unp); font-weight: 600; margin-right: 6px; }

.split { display: grid; grid-template-columns: 320px minmax(0, 1fr); gap: 32px;
  align-items: start; }
aside.side { position: sticky; top: 112px; max-height: calc(100vh - 128px); overflow-y: auto; }
aside.side .eyebrow { display: flex; justify-content: space-between; margin: 4px 2px 0; }
aside.side .ledger .row { padding: 11px 14px; }
aside.side .ledger .text { font-size: 13px; display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden; }
aside.side .ledger li.on { box-shadow: inset 3px 0 0 var(--fg); background: #faf8f4; }

/* one claim */
.claim-head { display: flex; justify-content: space-between; align-items: center; gap: 12px;
  flex-wrap: wrap; }
.claim-head h1 { font: 500 11.5px var(--mono); letter-spacing: 0.06em; color: var(--muted);
  margin: 0; }
.claim-head h1 .muted { color: var(--muted); }
blockquote.claimtext { font: 400 32px/1.18 var(--serif); letter-spacing: -0.015em;
  background: none; border-left: 2px solid var(--fg); border-radius: 0;
  padding: 2px 0 2px 22px; margin: 18px 0 8px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  margin: 22px 0; overflow: hidden;
  box-shadow: 0 1px 2px rgb(20 20 20 / 0.04), 0 6px 18px -10px rgb(20 20 20 / 0.12); }
.card > .in { padding: 16px 20px; }
.card > .in + .in { border-top: 1px solid var(--line); background: #faf8f4; }
.card .verdict { font-size: 14.5px; padding: 5px 14px 5px 10px; margin: 8px 0 6px; }
.card ul { padding-left: 20px; margin: 8px 0; }
.card details form.box { background: #fff; }

/* context around a record, as a conversation */
.thread { background: var(--card); border: 1px solid var(--line); border-radius: 16px;
  padding: 16px; display: flex; flex-direction: column; gap: 10px; }
.msg { max-width: 72%; border: 1px solid var(--line); border-radius: 14px; padding: 8px 12px;
  background: #fff; align-self: flex-start; }
.msg.out { align-self: flex-end; background: #e9eef5; border-color: #d3dceb; }
.msg .who2 { font-size: 11.5px; color: var(--muted); }
.msg .body { font-size: 14.5px; }
.msg .t { font: 400 10.5px var(--mono); color: var(--muted); text-align: right; margin-top: 2px; }
.msg.target { border: 1.5px solid #c9a24a; background: #fbf1cf;
  box-shadow: 0 0 0 3px rgb(201 162 74 / 0.18); }
.msg .cited { font: 600 9.5px var(--mono); letter-spacing: 0.1em; color: #6b4d0c;
  background: #f0dca3; border-radius: 3px; padding: 1px 4px; margin-right: 6px; }

/* identities: a person, and each link with its records for and against */
.lede { font-size: 15px; color: var(--muted); max-width: 70ch; }
section.person { margin: 34px 0; }
h2.pname { font: 400 30px/1.15 var(--serif); letter-spacing: -0.01em; margin: 4px 0 6px; }
.idhead { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
  gap: 6px; }
.idpair { font-size: 17px; font-weight: 600; margin: 10px 0 4px; }
.idpair .arrow { color: var(--muted); font-weight: 400; margin: 0 6px; }
.stpill { display: inline-flex; align-items: center; height: 20px; padding: 0 9px;
  border: 1px solid var(--line-strong); border-radius: 999px; font: 500 11px var(--sans);
  color: var(--fg); background: var(--card); margin: 0 6px 4px 0; white-space: nowrap; }
.stpill b { margin-left: 4px; }
.st-confirmed.stpill { color: var(--sup); background: var(--sup-bg);
  border-color: var(--sup-line); }
.st-rejected.stpill { color: var(--con); background: var(--con-bg); border-color: var(--con-line); }
.st-unresolved.stpill { color: var(--unp); background: var(--unp-bg);
  border-color: var(--unp-line); }
article.idlink.st-rejected { opacity: 0.8; }
.idgrid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 1px;
  background: var(--line); border-top: 1px solid var(--line); }
.idgrid > div { background: var(--card); padding: 14px 20px; }
.idgrid .side { display: flex; align-items: center; gap: 8px; font-size: 12.5px;
  font-weight: 600;
  margin: 0 0 8px; }
.idgrid .side::before { content: ""; width: 3px; height: 13px; border-radius: 2px; }
.idgrid .side.for::before { background: var(--sup); }
.idgrid .side.against::before { background: var(--con); }
ul.sig { list-style: none; padding: 0; margin: 0; }
ul.sig li { font-size: 13px; line-height: 1.45; margin: 0 0 12px; }
ul.sig .quote { font-size: 14px; color: var(--fg); }
ul.sig .ref { font-size: 10.5px; color: var(--muted); margin-top: 2px; overflow-wrap: anywhere; }
.caution { border-left: 3px solid #c9a24a; background: #fbf1cf; padding: 8px 12px;
  border-radius: 0 8px 8px 0; font-size: 13.5px; }
button[aria-pressed=true] { box-shadow: inset 0 0 0 2px var(--fg); }
ul.unplaced .head .text { font-weight: 600; }

@media (max-width: 900px) {
  .split { grid-template-columns: minmax(0, 1fr); }
  aside.side { position: static; max-height: none; order: 2; }
  blockquote.claimtext { font-size: 26px; }
  .msg { max-width: 88%; }
  .idgrid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 600px) {
  header.top { position: static; }
  [id] { scroll-margin-top: 12px; }
  main { padding: 20px 16px 64px; }
  .bar { padding: 10px 16px 2px; } nav.tabs { padding: 0 16px; }
  h1 { font-size: 32px; }
  table { display: block; overflow-x: auto; }
}
"""
