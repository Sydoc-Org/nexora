# Workitems overview: console redesign

Redesign `templates/workitems_overview.html` to match the dashboard console style shipped
2026-09-05 (`docs/design/Dashboard_redesign/…`).

**Design reference:** `design_handoff_workitems_console/Workitems Redesign.dc.html`
(open in a browser with `support.js` + `image-slot.js` beside it). Full spec in `README.md`
in the same folder — including an itemized "Design intent" list from design review.

Scope, in short:
- Console page head + hairline filter row (scope picker, search, stage select, underline
  "Advanced" toggle); Advanced panel flat, same doc-value-search serialization.
- Status select → underline tabs with counts (All / Ready / In progress / Done).
- Two views: hairline table (two-line rows, quiet status dots, no mono) and a 5-up
  document-card grid; shared selection.
- Inline expanding detail per row: stage stepper, page previews (+ Full mode), extracted
  fields with confidence bar + %, Audit timeline, "Show sources", "In register".
- Floating selection bar; footer pagination; flat export modal.
- No KPI strip on this page. Accent stays `var(--nx-accent)`.

Touches: `workitems_overview.html/.css`, `_workitems_overview_js.html`,
`workitem_detail_panel.js` (shared — keep reporting/prepared_documents consumers working),
workitems API (per-status counts), translations, e2e selectors.
