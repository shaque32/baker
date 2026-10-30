## 2026-10-30: Exhibits, Selection, Timeline and Gaps screens: fixes from a design critique (#PR)
- Changed: review screen only, from an Impeccable critique (design review plus detector). Timeline
  and Gaps load their styles with the other report fragments instead of a page-level style tag,
  drop the eyebrow labels, and fold the case settings into a disclosure under the summary that
  shows the current values. The not-found caveat shows once in the Gaps intro, not on every
  card; each card keeps its own Searched line. Selection: unpicked messages recede by tint instead
  of opacity, so their metadata meets text contrast; metadata text 12px. Exhibits: "Cited in"
  options drop the repeated paragraph number and cut at a word; the empty state links to the
  form. Placeholder text contrast raised; intro paragraphs capped at a readable measure.
  The exported report is unchanged.
- Where: PR #PR
- Verified: make check; impeccable detect on the rendered demo case: low-contrast, tiny-text,
  placeholder and skipped-heading findings cleared on these four screens. No browser
  screenshot (extension not connected).
- Open: Selection's method text, its h3 levels and inline mark styles live in
  core/report/selection.py, shared with the report; left for a change that bumps REPORT_VERSION.
- Affects: none
- Status doc: no change
