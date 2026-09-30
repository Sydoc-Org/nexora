# Redesign Sydoc Finance + Sydoc BPS as a mirrored, Sydoc-branded pair

Both pages are Sydoc's own books, not tenant pages. They should look like it and mirror each other.

**Design:** `docs/design/design_handoff_sydoc_finance_bps/` — option **1a** in `Sydoc Finance.dc.html` and `Sydoc BPS.dc.html`. The spec is in `README.md`.

## Scope
- [ ] Shared ink header band (`nx-sydoc-band`): Sydoc mark, "Sydoc internal" eyebrow, actions, period as a 54px headline with prev/next arrows, status grid.
- [ ] Shared period picker modal (`nx-sydoc-picker`): year switcher, 3×4 month grid with status, plus BPS quick presets and a custom range.
- [ ] Finance: one-row jump index in the band (no wrap, ellipsis, short `nav` labels).
- [ ] Finance: ledger sections (identity left, statement lines right: value / prev / change bar), breakdowns with orange share bars; no section tiles.
- [ ] Finance: Billable services with per-task + per-customer breakdowns and a **timeline** of bookings per customer (replaces the tables).
- [ ] BPS: totals + composition bar in the band; restyled hours-per-day chart with shaded weekends.
- [ ] BPS: zoomable drill-down with **Table (default)** / Treemap, breadcrumb, order switch, filter chips, search, and a vs.-previous-period gain/loss column and pills.
- [ ] BPS: compact per-day bookings list at the leaf (30px rows, 5 per day + "Show n more").
- [ ] Tokens: `--nx-sydoc*`, `--nx-gain/--nx-loss`; sidebar active bar orange on these pages.
- [ ] API: previous-period rows for BPS, per-month hours, close state per month for the pickers.
- [ ] i18n strings, e2e selector updates, print CSS.
