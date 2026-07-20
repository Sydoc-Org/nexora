# Reporting Simple tab — UX pass 2 (2026-07-16)

User-reported friction on the Simple tab wizard plus one drill-through bug.
All decided interactively with the owner; options chosen are marked.

## 1. Multi-metric measure step

The wizard's "What do you want to count?" step becomes toggle-select
(same idiom as the breakdown chips). Constraint: all selected metrics must
come from one source — the first pick pins the source, chips of other
sources gray out (disabled) until the selection is empty again. A
"Continue" button advances (today: click on a measure advances).

- `state.wiz.measure` → `state.wiz.measures` (array).
- `wizardDefinition()` emits `metrics: measures.map(m => ({metric: m.code}))`.
  Backend `resolve_metrics` already accepts a list; the client chart already
  maps N metrics to datasets for 0–1 breakdowns. With 2 breakdowns the chart
  pivots the first metric and notes it (existing behaviour, table shows all).
- Total strip shows one total per metric.
- `wizardStateFromDefinition()` accepts N same-source metrics so
  Adjust-in-wizard round-trips.

## 2. Process selection becomes its own wizard step

New step 2 "Which processes?" — checkbox list, all pre-checked, shown only
when the source carries processes (docprocessing); table sources skip it.
The collapsed `rsScopeWrap` picker disappears from the breakdown step.
State (`w.scopeProcs`), serialization, and server-side grant clamping are
unchanged. Breakdown chips therefore render already filtered by the chosen
processes when the user reaches step 3.

## 3. Coverage badge colour

The `n/m` badge (shown only when a field's process coverage is partial —
unchanged) gets colour: amber for partial, muted gray for low coverage
(≤ 1/3 of the selected scope). Process names stay on the hover title.
CSS-only: modifier classes on `.reporting-simple-chip-cov`.

## 4. Coverage sort

Breakdown chips sort: full-coverage first (curated `DOCPROC_DIM_ORDER`
within the group), then by descending coverage fraction — `1/5` lands at
the bottom. Re-sorts live when the process selection changes.

## 5. Lift the 16-chip cap

`catFields.slice(0, 16)` removed; the noise hide-list (`bankpk`, `crdno`,
`docbarcode`, `docdate`, `workitem_id`) stays. The pinning test
`test_wizard_caps_category_chips_at_16` is replaced by one pinning the
hide-list.

Rejected: "truly all" fields (`workitem_id` as breakdown = one group per
row); cross-source metric combos (query engine is single-source).

## 6. Drill-through preview lightbox fix (bug)

Reproduced: drill drawer → workitem link → preview panel → click image or
click-to-locate detail = wrecked layout (image squashed at top, values
panel floating mid-page). Root cause: `static/css/source-highlight.css`
scopes the split-lightbox layout to the workitems page shell id —
`#imageModal .src-modal-body { display:flex }`, `#imageModal .modal-close`,
`#srcHlLayer { position:absolute }`. The reporting shell (`#rdWiLightbox`,
`#rdWiHlLayer`) and prepared-documents shell (`#pdocPreviewLightbox`,
`#pdocPreviewHlLayer`) share the markup but not the ids → no flex layout,
no positioned overlay. Prepared documents has the same latent break.

Fix: de-scope `#imageModal` rules to `.modal` (only the three lightbox
shells use that class), and replace the `#srcHlLayer` rules with a shared
class `src-hl-layer-full` added to all three overlay divs. JS id lookups
unchanged. Verify all three surfaces (workitems, prepared documents,
reporting drill) in the browser.

## Chores

i18n (de/fr/it) for the new step strings; CHANGELOG entry; update
`docs/howto/reporting.md` wizard description; adjust unit + e2e tests
touching wizard step order and the chip cap.
