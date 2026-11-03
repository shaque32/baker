"""Identities (/identities).

This page's own CSS, scoped to its markup (see ui/css/__init__.py). Every rule sits under
.pg-ids, the page's wrapper, so nothing here reaches another page (the claim page's
<aside class='side'> in particular). The shared identity rules in ui/theme.py still apply;
these refine them: one status bar, a person header with the name first, link cards whose
records read as the site's quiet rows, and one decision line per link.
"""

CSS = """
/* Identities: the page wrapper restores the prose measure the theme gives main > p */
.pg-ids > p, .pg-ids > details.more { max-width: 72ch; }
.pg-ids > details.more { margin: 0 0 20px; }
.pg-ids > details.more p { margin: 8px 0 0; font-size: 13.5px; color: var(--ink-2);
  max-width: 72ch; }
.pg-ids h2 { margin: 40px 0 12px; }
.pg-ids form { margin: 0; }
.pg-ids button { margin: 0; }

/* One status bar: the counts, and the one page-wide action beside them */
.pg-ids .idbar { display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: 12px 24px; padding: 12px 0;
  border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); margin: 0 0 8px; }
.pg-ids .idbar .counts { margin: 0; gap: 6px; }
.pg-ids .idbar .stpill { margin: 0; }
.pg-ids .idbar form.look { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 12px; }
.pg-ids .idbar form.look .muted { font-size: 12.5px; }
/* A count of nothing carries no colour: green or red would say something happened */
.pg-ids .stpill.zero { color: var(--muted); background: transparent;
  box-shadow: inset 0 0 0 1px var(--line); }
.pg-ids > .banner { margin: 16px 0 0; }

/* Names with no person yet: name left, its actions on one line at the right */
.pg-ids ul.unplaced .head { display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: 8px 16px; }
.pg-ids ul.unplaced .acts { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.pg-ids ul.unplaced .acts form.inline { display: inline-flex; align-items: center; gap: 8px; }
.pg-ids ul.unplaced .acts select { margin: 0; height: 34px; }
.pg-ids ul.unplaced .needs { font-size: 12.5px; color: var(--muted); margin-top: 4px; }
.pg-ids ul.unplaced li:hover { background: transparent; }

/* Add a person: no box, field and button on one line under the names it belongs to */
.pg-ids form.addp, .pg-ids form.aliasf { display: grid; align-items: end; gap: 6px 8px;
  grid-template-columns: minmax(0, 380px) auto minmax(0, 1fr); }
.pg-ids form.addp { margin: 16px 0 0; }
.pg-ids form.addp label, .pg-ids form.aliasf label { margin: 0; }
.pg-ids form.addp input[type=text], .pg-ids form.aliasf input[type=text] { margin: 0;
  width: 100%; min-width: 0; }
.pg-ids form.addp p.muted, .pg-ids form.aliasf .hint { grid-column: 1 / -1; margin: 0;
  font-size: 12.5px; max-width: 72ch; }

/* A person: the name first, what they are in muted text under it, removal at the right */
.pg-ids section.person { margin: 48px 0 0; padding-top: 28px; }
.pg-ids .phead { display: flex; flex-wrap: wrap; align-items: flex-start;
  justify-content: space-between; gap: 8px 16px; }
.pg-ids h2.pname { margin: 0; }
.pg-ids .pkind { margin: 2px 0 0; font-size: 13px; color: var(--muted); }
.pg-ids .pclaims { margin: 12px 0 14px; font-size: 13.5px; max-width: 78ch; }
.pg-ids button.remove { color: var(--con); min-height: 30px; padding: 0 11px; font-size: 13px; }
.pg-ids button.remove:hover { background: var(--con-bg); border-color: var(--con-line); }
.pg-ids .pnote { font-size: 13px; max-width: 72ch; margin: 12px 0 0; }

/* An absence: one sentence, with what was searched one click under it */
.pg-ids details.absent { margin: 16px 0 0; font-size: 13.5px; }
.pg-ids details.absent > summary { color: var(--ink-2); font-weight: 500; }
.pg-ids details.absent p { margin: 8px 0 0 18px; color: var(--muted); font-size: 13px;
  max-width: 72ch; }
.pg-ids section.person .banner { margin: 16px 0 0; }

/* A link: the pair and its two labels on one row, one muted meta line, the basis */
.pg-ids article.idlink { margin: 16px 0 0; border-radius: var(--radius); }
.pg-ids article.idlink > .in:first-child { padding: 16px 20px 14px; }
.pg-ids .idhead { flex-wrap: nowrap; align-items: flex-start; gap: 12px; }
.pg-ids .idpair { margin: 0; font-size: 15px; line-height: 1.45; }
.pg-ids .idtags { display: inline-flex; flex: none; gap: 6px; margin-top: 2px; }
.pg-ids .idtags .badge, .pg-ids .idtags .stpill { margin: 0; }
.pg-ids .idmeta { margin: 2px 0 10px; font-size: 12.5px; color: var(--muted); }
.pg-ids .idbasis { margin: 0; font-size: 13.5px; max-width: 80ch; }
.pg-ids article.idlink .caution { margin: 12px 0 0; max-width: 80ch; }
.pg-ids article.idlink .in > p.muted:last-child { margin: 10px 0 0; font-size: 12.5px; }

/* Records for and against, as quiet rows: the quote, one note line, the source */
.pg-ids .idgrid > div { padding: 14px 20px 12px; }
.pg-ids .idgrid .side { margin: 0 0 4px; font-weight: 500; color: var(--fg); }
.pg-ids .idgrid .side .n { color: var(--muted); font-weight: 400;
  font-variant-numeric: tabular-nums; }
.pg-ids ul.sig li { margin: 0; padding: 9px 0; border-top: 1px solid var(--line); }
.pg-ids ul.sig li:first-child { border-top: 0; }
.pg-ids ul.sig .quote { font-weight: 500; }
.pg-ids ul.sig .note { color: var(--ink-2); }
.pg-ids ul.sig .ref { margin-top: 3px; }
.pg-ids details.sigmore { border-top: 1px solid var(--line); padding-top: 8px; }
.pg-ids details.sigmore > summary { font-size: 12.5px; }
.pg-ids details.sigmore[open] > summary { margin-bottom: 2px; }
.pg-ids .idgrid > div > p.muted { font-size: 13px; margin: 6px 0 0; }
/* A decided link folds its records; the summary says how many on each side */
.pg-ids details.idrec { border-top: 1px solid var(--line); }
.pg-ids details.idrec > summary { padding: 11px 20px; font-size: 13px; }
.pg-ids details.idrec > .idgrid { border-top: 1px solid var(--line); }
.pg-ids article.idlink > .in:not(:first-child):not(.idact) { background: var(--card);
  border-top: 1px solid var(--line); padding: 11px 20px; font-size: 13px; }

/* The decision: the reason and the three choices on one line */
.pg-ids article.idlink > .in.idact { padding: 14px 20px 16px; background: var(--card);
  border-top: 1px solid var(--line); }
.pg-ids form.decide { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 10px 12px; }
.pg-ids form.decide label { flex: 1 1 320px; margin: 0; }
.pg-ids form.decide input[type=text] { margin: 0; }
.pg-ids form.decide .choices { display: inline-flex; flex-wrap: wrap; gap: 8px; }
.pg-ids form.decide button[value=rejected] { color: var(--con); }
.pg-ids form.decide button[value=rejected]:hover { background: var(--con-bg);
  border-color: var(--con-line); }
/* The current state: a soft navy ring, not a heavy black box */
.pg-ids button[aria-pressed=true] { box-shadow: 0 0 0 3px var(--ring);
  border-color: var(--accent); }
.pg-ids button[aria-pressed=true]:not(.primary) { background: var(--accent-bg);
  color: var(--accent); }
.pg-ids article.idlink.st-rejected { opacity: 1; }
.pg-ids article.idlink.st-rejected .idpair { color: var(--muted); }

/* Link an account yourself: selects shrink to the column instead of widening the page */
.pg-ids form.linkself { margin: 0; }
.pg-ids form.linkself .pick { display: flex; flex-wrap: wrap; gap: 12px 16px; }
.pg-ids form.linkself .pick label { margin: 0; min-width: 0; max-width: 100%;
  grid-template-columns: minmax(0, 1fr); }
.pg-ids form.linkself .pick label:first-child { flex: 1 1 360px; }
.pg-ids form.linkself select { width: 100%; margin: 0; }
.pg-ids form.linkself input[type=text] { margin: 0; }
.pg-ids form.linkself .go { display: flex; flex-wrap: wrap; align-items: center;
  gap: 8px 14px; margin: 0; }
.pg-ids form.linkself .go .muted { font-size: 12.5px; }

@media (max-width: 600px) {
  .pg-ids .idhead { flex-wrap: wrap; }
  .pg-ids .idgrid > div, .pg-ids .idact,
  .pg-ids article.idlink > .in:first-child { padding-left: 16px; padding-right: 16px; }
  .pg-ids form.addp, .pg-ids form.aliasf { grid-template-columns: minmax(0, 1fr) auto; }
  .pg-ids form.decide label { flex-basis: 100%; }
}
"""
