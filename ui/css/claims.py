"""Claims (/claims) and Add a claim (/claim/new).

This page's own CSS, scoped to its markup (see ui/css/__init__.py): `.pg-claims` wraps the claims
overview and `.pg-newclaim` wraps Add a claim. The claim page's side ledger (`_ledger`, compact)
sits outside both wrappers and keeps the shared look in ui/theme.py.

The overview reads like the site's hero ledger: a claim's name in a narrow left column, the
claim, one status at the right, and under it where it sits, the one thing it needs from the expert
and its gap topics as small tags.
"""

CSS = """

/* claims overview: the counts as a plain row of numbers, no frame */
.pg-claims .tiles { display: flex; flex-wrap: wrap; gap: 16px 48px; margin: 28px 0 40px; }
.pg-claims .tile { display: grid; gap: 2px; padding: 0; border: 0; border-radius: 0;
  background: none; }
.pg-claims .tile .n { grid-row: 1; font: 600 26px/1.2 var(--sans); letter-spacing: 0; }
.pg-claims .tile .name { grid-row: 2; font-size: 13px; color: var(--muted);
  transition: color 0.15s var(--ease); }
.pg-claims a.tile:hover .name { color: var(--fg); }
.pg-claims .tile.empty .name, .pg-claims .tile.empty .n { color: var(--muted); }

/* next up: no box; the claim's own accent rule sets it apart, then each thing to do on its
   own short line */
.pg-claims .nextup { padding: 0; margin: 0 0 48px; background: none; border: 0;
  border-radius: 0; }
.pg-claims .nextup .todo { margin: 0 0 16px; max-width: 72ch; }
.pg-claims .nextup .todo p { margin: 0 0 6px; color: var(--ink-2); font-size: 13.5px;
  text-wrap: pretty; }

/* groups: a heading and its count */
.pg-claims section.group { margin: 40px 0; }
.pg-claims .ghead { margin-bottom: 10px; }
.pg-claims details.fold > summary { margin: 0; }
.pg-claims details.fold[open] > summary { margin-bottom: 10px; }

/* a claim row: name | claim | status, then small lines under the claim */
.pg-claims .ledger .row { display: grid; grid-template-columns: 4.2em minmax(0, 1fr) auto;
  align-items: baseline; gap: 2px 14px; padding: 14px 20px; }
.pg-claims .ledger .cid { grid-column: 1; font: 600 12.5px/1.5 var(--sans);
  font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.pg-claims .ledger .cid a { color: var(--fg); text-decoration: none; }
.pg-claims .ledger .cid a::after { content: ""; position: absolute; inset: 0; }
.pg-claims .ledger .cid a:focus-visible { outline: none; }
.pg-claims .ledger li:has(.cid a:focus-visible) { box-shadow: inset 0 0 0 2px var(--accent); }
.pg-claims .ledger .text { grid-column: 2; max-width: 80ch; text-wrap: pretty; }
.pg-claims .ledger .verdict { grid-column: 3; justify-self: end; white-space: nowrap; }
.pg-claims .ledger .sub { grid-column: 2 / -1; max-width: 80ch; font-size: 12.5px;
  line-height: 1.5; color: var(--muted); }
.pg-claims .ledger .sub .meta { display: block; padding: 0; font-size: 12px; }
.pg-claims .ledger .needs { margin-top: 4px; color: var(--ink-2); }

/* gap topics: one plain line under the claim, not chips; the claim page says each in full */
.pg-claims .ledger .gap { display: inline; margin: 0; padding: 0; border: 0; border-radius: 0;
  background: none; color: var(--fg); font-size: 12.5px; }
.pg-claims .ledger .sub > :not(.gap) + .gap::before { content: ""; display: block;
  margin-top: 4px; }
.pg-claims .ledger .gap + .gap::before { content: " · "; color: var(--muted); }
.pg-claims .nextup .gap { margin-top: 4px; }

@media (max-width: 600px) {
  .pg-claims .tiles { gap: 14px 32px; }
  .pg-claims .ledger .row { grid-template-columns: minmax(0, 1fr) auto; padding: 12px 16px; }
  .pg-claims .ledger .cid { grid-column: 1; grid-row: 1; }
  .pg-claims .ledger .verdict { grid-column: 2; grid-row: 1; }
  .pg-claims .ledger .text, .pg-claims .ledger .sub { grid-column: 1 / -1; }
  .pg-claims .ledger .text { margin-top: 2px; }
}

/* add a claim: one form at a readable width */
.pg-newclaim form.box { max-width: 46rem; padding: 20px 24px; }
.pg-newclaim form.box p { margin: 0 0 16px; }
.pg-newclaim label:has(> select[name=paragraph]) { display: grid; margin-right: 0; }
.pg-newclaim select[name=paragraph] { width: 100%; min-width: 0; }
.pg-newclaim p.act { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px;
  margin: 4px 0 0; }
.pg-newclaim p.act .muted { font-size: 12.5px; }
"""
